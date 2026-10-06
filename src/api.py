import hashlib
import hmac
import json
import logging
import os
import queue
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.engine import make_url

import time

from . import auth
from .messages import arabic
from .classification import diagnose
from .db import Conflict, Store, normalize_database_url, sources
from .llm import llm_provider, validate_config
from .models import ReviewRequest, SUBPATTERNS
from .parsing import normalize_arabic
from .retrieval import HybridRetriever, refresh_embeddings
from .retrieval.hybrid import SemanticEncoder
from .storage import get_storage, page_key

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger('manhaj.api')
CLI_ONLY = 'متاح من سطر الأوامر فقط في النسخة المستضافة'
# Heavy summary fields stay out of list responses (Vercel caps responses at 4.5 MB); fetch details by id.
HEAVY_DOCUMENT_FIELDS = {'dataset_manifests': ('records',), 'extraction_runs': ('inventory',), 'duplicate_runs': ('suggestions', 'pairs'), 'evaluation_runs': ('predictions', 'per_case'), 'training_exports': ('records',)}
IMMUTABLE = 'public, max-age=31536000, immutable'


def asset_version(path):
    import hashlib as _h
    return _h.sha256(path.read_bytes()).hexdigest()[:12]


class CompressExceptStreams:
    """Gzip for every response except the live analysis, whose small updates must reach the page as they happen."""

    def __init__(self, app):
        self.app, self.gzip = app, GZipMiddleware(app, minimum_size=1024)

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope['path'] == '/api/diagnose/stream': return await self.app(scope, receive, send)
        return await self.gzip(scope, receive, send)


DOCUMENT_KINDS = ('dataset_manifests', 'evaluation_runs', 'extraction_runs', 'duplicate_runs', 'training_exports', 'phase_gates', 'source_items')


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(max_length=200)
    email: str = Field(max_length=320)
    password: str = Field(max_length=400)


class BulkDeleteRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ids: list[Annotated[str, Field(max_length=80)]] = Field(min_length=1, max_length=100)


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    verdict: Literal['correct', 'wrong']
    note: str = Field(default='', max_length=1000)


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(max_length=200)


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(max_length=320)
    password: str = Field(max_length=400)


class PasswordRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_password: str = Field(max_length=400)
    new_password: str = Field(max_length=400)


class AvatarRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    image: str = Field(max_length=220_000)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(max_length=320)
    password: str = Field(max_length=400)


def bearer(authorization):
    return authorization[7:].strip() if authorization and authorization.startswith('Bearer ') else ''


def client_key(request):
    """Who is asking, for throttling only: the client address, hashed so raw IPs are never stored."""
    ip = request.headers.get('x-real-ip') or request.headers.get('x-forwarded-for', '').split(',')[0] or (request.client.host if request.client else '')
    return 'ip:' + hashlib.sha256(ip.strip().encode()).hexdigest()[:24]


class DiagnoseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    include_drafts: bool = False
    deep_search: bool = True  # every analysis also searches a few trusted sites; kept for older pages


class BenchmarkRequest(BaseModel):
    test_ids: list[Annotated[str, Field(max_length=80)]] = Field(default=[], max_length=2000)
    validation_ids: list[Annotated[str, Field(max_length=80)]] = Field(default=[], max_length=2000)
    auto: bool = False


class GateRequest(BaseModel):
    coverage_verified: bool
    notes: str = Field(max_length=5000)


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=50)


class RefreshRequest(BaseModel):
    include_drafts: bool = True


class EvaluateRequest(BaseModel):
    predictions: dict[str, dict] = {}
    human_scores: dict[str, dict] = {}
    split: Literal['test', 'validation'] = 'test'


def _flag(name):
    return os.getenv(name, '').strip().lower() in ('1', 'true', 'yes')


def same_origin(request, origin):
    """Same-origin check that also works behind a TLS-terminating proxy such as Vercel."""
    if not origin or origin == 'null': return False
    parsed = urlsplit(origin)
    host = (request.headers.get('x-forwarded-host') or request.headers.get('host') or request.url.netloc).split(',')[0].strip()
    scheme = (request.headers.get('x-forwarded-proto') or request.url.scheme).split(',')[0].strip()
    if (parsed.scheme, parsed.netloc) == (scheme, host): return True
    allowed = {o.strip().rstrip('/') for o in os.getenv('ALLOWED_ORIGINS', '').split(',') if o.strip()}
    allowed |= {'https://' + os.environ[v] for v in ('VERCEL_URL', 'VERCEL_PROJECT_PRODUCTION_URL', 'VERCEL_BRANCH_URL') if os.getenv(v)}
    return origin.rstrip('/') in allowed


def remote_database(url):
    if not url or url.startswith('sqlite'): return False
    return (make_url(url).host or '') not in ('localhost', '127.0.0.1', '::1')


PUBLIC_REVIEWER = 'visitor'
MAX_BODY = 256 * 1024  # JSON requests only; PDF ingest is local and separate


def create_app(store=None, token_map=None, *, hosted=None, read_only=None, storage=None, public_access=None):
    # Validate configuration before touching the database or the (read-only, when hosted) filesystem.
    token_map = token_map if token_map is not None else json.loads(os.getenv('REVIEWER_TOKEN_HASHES', '{}'))
    # PUBLIC_ACCESS=1 opens the site without a login: requests without a valid token act as one shared
    # "visitor" reviewer (the daily diagnosis limit then caps everyone together).
    public_access = _flag('PUBLIC_ACCESS') if public_access is None else public_access
    if not token_map and not public_access: raise RuntimeError('Configure reviewer tokens with python scripts/create_reviewer.py; no default credentials exist')
    token_map = {rid: str(v).strip().lower() for rid, v in token_map.items()}
    if any(not re.fullmatch(r'[0-9a-f]{64}', v) for v in token_map.values()): raise RuntimeError('Reviewer secrets must be SHA-256 hex digests')
    hosted = bool(os.getenv('VERCEL')) if hosted is None else hosted
    url = normalize_database_url(os.getenv('DATABASE_URL', ''))
    if read_only is None:
        # A local copy pointed at a remote (production) database is read-only unless explicitly allowed,
        # because approvals and history written there are permanent.
        read_only = _flag('READ_ONLY') or (store is None and not hosted and remote_database(url) and not _flag('ALLOW_REMOTE_WRITES'))
    heavy_allowed = not hosted or _flag('ENABLE_HEAVY_ENDPOINTS')
    if store is None:
        validate_config()
        if hosted and (not url or url.startswith('sqlite')) and not _flag('ALLOW_SQLITE_SMOKE'):
            raise RuntimeError('Hosted deployments require a PostgreSQL DATABASE_URL (Supabase transaction pooler)')
        store = Store(url or None)
    storage = storage or get_storage()
    store.register_reviewers([*token_map, *([PUBLIC_REVIEWER] if public_access else [])])
    daily_limit = int(os.getenv('DIAGNOSE_DAILY_LIMIT', '0') or 0)
    overall_limit = int(os.getenv('DIAGNOSE_GLOBAL_DAILY_LIMIT', '0') or 0)  # all accounts together (OpenAI spend)
    # Accounts: anyone may sign up as a reviewer. Project-wide actions (exports, benchmarks, phase gates,
    # index rebuilds) stay with operator tokens and with accounts listed in ADMIN_EMAILS.
    signup_open = os.getenv('SIGNUP_ENABLED', '1').strip().lower() not in ('0', 'false', 'no')
    admin_emails = {e.strip().lower() for e in os.getenv('ADMIN_EMAILS', '').split(',') if e.strip()}
    # Book pages load straight from private storage through short-lived signed URLs.
    image_sources = "'self' blob: data:" + (f' {storage.url}' if storage.backend == 'supabase' else '')
    csp = f"default-src 'self'; style-src 'self'; script-src 'self'; img-src {image_sources}; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    app = FastAPI(title='مَنْهَج', version='0.2.0', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    def identity(request: Request, authorization: Annotated[str | None, Header()] = None):
        token = bearer(authorization)
        if token:
            digest = hashlib.sha256(token.encode()).hexdigest()
            for rid, expected in token_map.items():
                if hmac.compare_digest(expected, digest):
                    request.state.role, request.state.name = 'admin', rid
                    return rid
            account = store.session_account(token) if len(token) <= 256 else None
            if account:
                request.state.role = 'admin' if account['email'] in admin_emails else 'reviewer'
                request.state.name = account['name']
                return account['id']
            if not public_access: raise HTTPException(401, 'انتهت الجلسة. سجّل الدخول من جديد.')
        if public_access:
            request.state.role, request.state.name = 'visitor', 'زائر'
            return PUBLIC_REVIEWER
        raise HTTPException(401, 'سجّل الدخول للمتابعة.')

    def reviewer(request: Request, actor=Depends(identity)):
        if request.state.role == 'visitor': raise HTTPException(403, 'أنشئ حسابًا لتتمكن من الحفظ.')
        return actor

    def admin(request: Request, actor=Depends(identity)):
        if request.state.role != 'admin': raise HTTPException(403, 'هذا الإجراء لمسؤول المشروع فقط.')
        return actor

    def heavy():
        if not heavy_allowed: raise HTTPException(409, CLI_ONLY)

    def local_only():
        # Uploads exceed Vercel's 4.5 MB body limit and need a writable disk: never on hosted deployments.
        if hosted: raise HTTPException(409, CLI_ONLY)

    @app.middleware('http')
    async def security_headers(request, call_next):
        # Explicit bearer authentication, same-origin UI, and no cookie sessions.
        origin = request.headers.get('origin')
        started = time.perf_counter()
        size = request.headers.get('content-length')
        if origin is not None and not same_origin(request, origin):
            response = JSONResponse({'detail': 'Cross-origin request blocked'}, status_code=403)
        elif read_only and request.method not in ('GET', 'HEAD', 'OPTIONS') and request.url.path not in ('/api/diagnose', '/api/diagnose/stream', '/api/auth/login', '/api/auth/logout'):
            response = JSONResponse({'detail': 'نسخة معاينة للقراءة فقط'}, status_code=403)
        elif request.url.path != '/api/ingest' and size and (not size.isdigit() or int(size) > MAX_BODY):
            response = JSONResponse({'detail': 'الطلب أكبر من المسموح.'}, status_code=413)
        else:
            response = await call_next(request)
        response.headers['Server-Timing'] = f'app;dur={(time.perf_counter() - started) * 1000:.1f}'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        # Fonts, images and versioned JS/CSS never change at a given URL; API data is private and never cached.
        path = request.url.path
        if path.startswith('/static/') and (request.query_params.get('v') or path.startswith(('/static/fonts/', '/static/img/'))):
            response.headers['Cache-Control'] = IMMUTABLE
        elif path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-cache'
        else:
            response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = csp
        return response

    app.add_middleware(CompressExceptStreams)

    # Reviewers read every error in Arabic; the English originals stay in code, logs and tests.
    @app.exception_handler(Conflict)
    async def conflict_error(_, exc): return JSONResponse({'detail': arabic(str(exc))}, status_code=409)

    @app.exception_handler(ValueError)
    async def value_error(_, exc): return JSONResponse({'detail': arabic(str(exc))}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing_error(_, exc): return JSONResponse({'detail': arabic('Record not found')}, status_code=404)

    @app.exception_handler(HTTPException)
    async def http_error(_, exc):
        detail = arabic(exc.detail) if isinstance(exc.detail, str) else exc.detail
        return JSONResponse({'detail': detail}, status_code=exc.status_code, headers=getattr(exc, 'headers', None))

    @app.get('/health')
    def health():
        with store.engine.connect() as c: c.execute(select(1))
        return {'status': 'ok', 'service': 'manhaj'}

    @app.post('/api/auth/signup', status_code=201)
    def signup(body: SignupRequest, request: Request):
        if not signup_open: raise HTTPException(403, 'التسجيل مغلق حاليًا. تواصل مع مسؤول المشروع.')
        name, email = auth.clean_name(body.name), auth.clean_email(body.email)
        auth.check_new_password(body.password, email)
        who = client_key(request)
        if store.count_events('signup', who, auth.now_s() - 3600) >= 5: raise HTTPException(429, 'محاولات كثيرة من هذا الجهاز. حاول بعد ساعة.')
        account_id = store.create_account(name, email, auth.hash_password(body.password))
        store.add_event('signup', who)
        return {'token': store.create_session(account_id, auth.SESSION_DAYS), 'name': name}

    @app.post('/api/auth/login')
    def login(body: LoginRequest, request: Request):
        email = (body.email or '').strip().lower()
        by_email, by_client, since = 'email:' + hashlib.sha256(email.encode()).hexdigest()[:24], client_key(request), auth.now_s() - 900
        if store.count_events('login_failed', by_email, since) >= 8 or store.count_events('login_failed', by_client, since) >= 40:
            raise HTTPException(429, 'محاولات كثيرة. حاول بعد ربع ساعة.')
        account = store.account_by_email(email)
        valid = auth.check_password(body.password, account['password_hash'] if account else auth.DUMMY_HASH)
        if not (account and valid):
            store.add_event('login_failed', by_email); store.add_event('login_failed', by_client)
            raise HTTPException(401, 'البريد أو كلمة المرور غير صحيحة.')
        return {'token': store.create_session(account['id'], auth.SESSION_DAYS), 'name': account['name']}

    @app.post('/api/auth/logout', status_code=204)
    def logout(authorization: Annotated[str | None, Header()] = None):
        token = bearer(authorization)
        if token and len(token) <= 256: store.revoke_session(token)
        return Response(status_code=204)

    # ---------- My analyses ----------
    @app.get('/api/diagnoses')
    def my_diagnoses(offset: int = 0, limit: int = 20, actor=Depends(reviewer)):
        if offset < 0 or offset > 100000 or not 1 <= limit <= 50: raise ValueError('Invalid pagination')
        return store.my_diagnoses(actor, offset, limit)

    @app.get('/api/diagnoses/{did}')
    def my_diagnosis(did: str, actor=Depends(reviewer)): return store.my_diagnosis(actor, did)

    @app.delete('/api/diagnoses/{did}', status_code=204)
    def delete_diagnosis(did: str, actor=Depends(reviewer)):
        store.delete_my_diagnosis(actor, did)
        return Response(status_code=204)

    @app.post('/api/diagnoses/delete')
    def delete_diagnoses(body: BulkDeleteRequest, actor=Depends(reviewer)):
        return {'deleted': store.delete_my_diagnoses(actor, set(body.ids))}

    @app.post('/api/diagnoses/{did}/feedback')
    def diagnosis_feedback(did: str, body: FeedbackRequest, actor=Depends(reviewer)):
        return store.diagnosis_feedback(actor, did, body.verdict, body.note.strip())

    # ---------- Profile ----------
    def own_account(request: Request, actor=Depends(reviewer)):
        if not str(actor).startswith('u-'): raise HTTPException(409, 'حساب التشغيل لا يُعدَّل من هنا.')
        return actor

    @app.get('/api/account')
    def account(request: Request, actor=Depends(identity)):
        info = {'name': request.state.name, 'role': request.state.role, 'editable': False, 'email': None, 'created_at': None}
        if str(actor).startswith('u-'):
            acc = store.account(actor)
            info.update(email=acc['email'], created_at=acc['created_at'], editable=True, name=acc['name'], avatar=acc.get('avatar') or None)
        info['activity'] = store.activity(actor) if request.state.role != 'visitor' else None
        return info

    @app.post('/api/account/avatar')
    def set_avatar(body: AvatarRequest, actor=Depends(own_account)):
        store.update_account(actor, avatar=auth.clean_avatar(body.image))
        return {'avatar': body.image}

    @app.delete('/api/account/avatar', status_code=204)
    def remove_avatar(actor=Depends(own_account)):
        store.update_account(actor, avatar='')
        return Response(status_code=204)

    @app.patch('/api/account')
    def update_profile(body: ProfileRequest, actor=Depends(own_account)):
        name = auth.clean_name(body.name)
        store.update_account(actor, name=name)
        return {'name': name}

    @app.post('/api/account/email')
    def change_email(body: EmailRequest, actor=Depends(own_account)):
        acc = store.account(actor)
        if not auth.check_password(body.password, acc['password_hash']): raise HTTPException(403, 'كلمة المرور الحالية غير صحيحة.')
        email = auth.clean_email(body.email)
        store.update_account(actor, email=email)
        return {'email': email}

    @app.post('/api/account/password')
    def change_password(body: PasswordRequest, request: Request, authorization: Annotated[str | None, Header()] = None, actor=Depends(own_account)):
        acc = store.account(actor)
        if not auth.check_password(body.current_password, acc['password_hash']): raise HTTPException(403, 'كلمة المرور الحالية غير صحيحة.')
        auth.check_new_password(body.new_password, acc['email'])
        store.update_account(actor, password_hash=auth.hash_password(body.new_password), keep_session=auth.token_hash(bearer(authorization)))
        return {'changed': True}

    @app.get('/api/me')
    def me(request: Request, actor=Depends(identity)):
        avatar = None
        if str(actor).startswith('u-'):
            try: avatar = store.account(actor).get('avatar') or None
            except KeyError: avatar = None
        return {'reviewer_id': actor, 'name': request.state.name, 'role': request.state.role, 'avatar': avatar, 'taxonomy': SUBPATTERNS, 'capabilities': {'heavy_jobs': heavy_allowed, 'read_only': read_only, 'hosted': hosted, 'storage': storage.backend, 'semantic': bool(os.getenv('EMBEDDING_MODEL')), 'llm': llm_provider(), 'draft_mode': True, 'public_access': public_access, 'diagnose_daily_limit': daily_limit or None}}

    @app.get('/api/summary')
    def summary(actor=Depends(identity)):
        counts = store.cached('counts', store.counts)
        rows = [dict(r, kind=k) for k in ('objection', 'rule', 'family') for r in counts[k]]
        total = lambda pred: sum(r['n'] for r in rows if pred(r))
        return {'sources': counts['sources'], 'objections': total(lambda r: r['kind'] == 'objection'), 'rules': total(lambda r: r['kind'] == 'rule'),
                'rules_approved': total(lambda r: r['kind'] == 'rule' and r['status'] == 'approved'), 'families': total(lambda r: r['kind'] == 'family'), 'approved': total(lambda r: r['status'] == 'approved'), 'pending': total(lambda r: r['status'] in ('draft', 'needs_review')), 'external': total(lambda r: r['phase'] == 2), 'semantic_enabled': bool(os.getenv('EMBEDDING_MODEL'))}

    @app.get('/api/records')
    def records(kind: str | None = None, status: str | None = None, phase: int | None = None, q: str = '', offset: int = 0, limit: int = 50, actor=Depends(identity)):
        if kind not in (None, 'rule', 'objection', 'family'): raise ValueError('Invalid kind')
        if status not in (None, '', 'draft', 'needs_review', 'approved', 'rejected') or phase not in (None, 1, 2): raise ValueError('Invalid filter')
        if offset < 0 or offset > 100000 or not 1 <= limit <= 200 or len(q) > 200: raise ValueError('Invalid pagination')
        status = status or None
        if not q.strip(): return store.cached(('page', kind, status, phase, offset, limit), lambda: store.page(kind, status, phase, offset, limit))
        # Arabic-aware search (hamza and diacritics ignored) over a cached, slim index of the list.
        needle = normalize_arabic(q)
        rows = [{k: v for k, v in r.items() if k != '_text'} for r in store.cached(('search', kind, status, phase), lambda: store.search_rows(kind, status, phase), 30) if needle in r['_text']]
        return {'total': len(rows), 'items': rows[offset:offset+limit]}

    @app.get('/api/records/{rid}')
    def record(rid: str, actor=Depends(identity)): return store.get(rid)

    @app.get('/api/records/{rid}/history')
    def history(rid: str, actor=Depends(identity)):
        names = store.reviewer_names()
        return [dict(item, actor_name=names.get(item.get('actor'), item.get('actor'))) for item in store.history(rid)]

    @app.post('/api/records/{rid}/review')
    def review(rid: str, request: ReviewRequest, actor=Depends(reviewer)):
        result = store.review(rid, request, actor)
        if os.getenv('EMBEDDING_MODEL'):
            try:  # best effort, after the review committed; never fails the review itself
                refresh_embeddings(store, include_drafts=True, record_ids=[rid])
            except Exception as error:  # noqa: BLE001 - logged and surfaced through the index refresh button
                log.warning('embedding refresh after review failed: %s', type(error).__name__)
        return result

    @app.get('/api/sources')
    def source_list(actor=Depends(identity)):
        return store.cached('sources', lambda: [{k: v for k, v in s.items() if k != 'pdf_path'} for s in store.source_list()])

    @app.get('/api/sources/{sid}/chunks')
    def source_chunks(sid: str, actor=Depends(identity)):
        source_payload(sid)  # 404 for unknown ids before anything is cached
        # raw_text duplicates whole pages and is not shown in the UI.
        return store.cached(('chunks', sid), lambda: store.chunk_list(sid), 300)

    @app.post('/api/sources/{sid}/model-extract')
    def model_extract(sid: str, actor=Depends(admin), _=Depends(heavy)):
        from .parsing.model_extraction import extract_with_model
        return extract_with_model(store, sid)

    def source_payload(sid):
        with store.engine.connect() as c: src = c.execute(select(sources.c.payload).where(sources.c.id == sid)).scalar_one_or_none()
        if not src: raise HTTPException(404, 'Original PDF not available')
        return src

    @app.get('/api/sources/{sid}/pdf-url')
    def source_pdf_url(sid: str, actor=Depends(identity)):
        source_payload(sid)
        if storage.backend != 'supabase': return {'url': None}
        try: return {'url': storage.signed_url(sid, 600), 'expires_in': 600}
        except KeyError: raise HTTPException(404, 'Original PDF not uploaded to storage')

    @app.get('/api/sources/{sid}/pages')
    def source_pages(sid: str, start: int = 1, count: int = 6, actor=Depends(identity)):
        """Rendered page images for the in-site book viewer (signed for 15 minutes when stored remotely)."""
        total = int(source_payload(sid).get('page_count') or 0)
        if total < 1: raise HTTPException(404, 'Book pages are not available')
        start, count = max(1, min(start, total)), max(1, min(count, 12))
        numbers = list(range(start, min(total, start + count - 1) + 1))
        if storage.backend == 'supabase':
            signed = storage.signed_urls([page_key(sid, n) for n in numbers], 900)
            pages = [{'number': n, 'url': signed.get(page_key(sid, n))} for n in numbers]
        else:
            pages = [{'number': n, 'url': f'/api/sources/{sid}/page-image/{n}' if storage.page_path(sid, n).is_file() else None} for n in numbers]
        return {'page_count': total, 'pages': pages}

    @app.get('/api/sources/{sid}/page-image/{number}')
    def page_image(sid: str, number: int, actor=Depends(identity)):
        if storage.backend != 'local': raise HTTPException(409, 'Use /pages for stored page images')
        path = storage.page_path(sid, number)
        if not path.is_file(): raise HTTPException(404, 'Page image not rendered; run scripts/render_source_pages.py')
        return FileResponse(path, media_type='image/webp')

    @app.get('/api/sources/{sid}/pdf')
    def source_pdf(sid: str, actor=Depends(identity)):
        src = source_payload(sid)
        if storage.backend != 'local': raise HTTPException(409, 'Use /pdf-url for stored originals')
        path = storage.path(sid, src.get('pdf_path', ''))
        if not path.is_file(): raise HTTPException(404, 'Original PDF not available')
        return FileResponse(path, media_type='application/pdf', filename='source.pdf', content_disposition_type='inline')

    @app.post('/api/ingest')
    def ingest(file: UploadFile = File(), title: str = Form('كتاب وليد'), author: str = Form(''), profile: str = Form('standard'), actor=Depends(admin), _=Depends(local_only)):
        folder = ROOT / 'data' / 'raw'
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=folder, suffix='.pdf', delete=False) as out:
            path = Path(out.name)
            size = 0
            try:
                while block := file.file.read(1024*1024):
                    size += len(block)
                    if size > 50*1024*1024: raise ValueError('PDF exceeds 50 MB')
                    out.write(block)
            except Exception:
                out.close(); path.unlink(missing_ok=True); raise
        try:
            with path.open('rb') as inp:
                if inp.read(5) != b'%PDF-': raise ValueError('Expected a PDF file')
            from .ingestion import ingest_pdf
            from .parsing.extraction import extract_source
            src = ingest_pdf(store, path, title, author, profile, ROOT/'data')
            run = extract_source(store, src['id'], data_dir=ROOT/'data')
            return {'source_id': src['id'], 'candidate_count': run['new_records']}
        finally: path.unlink(missing_ok=True)

    def reserve_diagnosis(actor):
        if (daily_limit or overall_limit) and not read_only:
            day_start = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
            if not store.reserve_usage('diagnose', actor, day_start, daily_limit, overall_limit):
                raise HTTPException(429, 'بلغت الحد اليومي للتحليل. يتجدد غدًا.')

    @app.post('/api/diagnose')
    def diagnosis(request: DiagnoseRequest, actor=Depends(identity)):
        reserve_diagnosis(actor)
        return diagnose(store, request.text, include_drafts=request.include_drafts, requested_by=actor, persist=not read_only, deep_search=request.deep_search)

    @app.post('/api/diagnose/stream')
    def diagnosis_stream(request: DiagnoseRequest, actor=Depends(identity)):
        """The same analysis, reported step by step as newline-delimited JSON while it is written."""
        reserve_diagnosis(actor)
        events = queue.Queue()

        def work():
            try:
                result = diagnose(store, request.text, include_drafts=request.include_drafts, requested_by=actor, persist=not read_only, deep_search=request.deep_search,
                                  progress=lambda kind, **data: events.put({'type': kind, **data}))
                events.put({'type': 'result', 'data': result})
            except ValueError as error:
                events.put({'type': 'error', 'detail': arabic(str(error))})
            except Exception:
                log.exception('streamed diagnosis failed')
                events.put({'type': 'error', 'detail': 'تعذّر إكمال التحليل. حاول مرة أخرى.'})

        threading.Thread(target=work, daemon=True).start()

        def lines():
            while True:
                try: event = events.get(timeout=10)
                except queue.Empty: event = {'type': 'ping'}  # keeps proxies from closing a quiet connection
                yield json.dumps(event, ensure_ascii=False) + '\n'
                if event['type'] in ('result', 'error'): return

        return StreamingResponse(lines(), media_type='application/x-ndjson', headers={'X-Accel-Buffering': 'no'})

    @app.get('/api/search')
    def search(q: str, kind: str | None = None, actor=Depends(reviewer)):
        if kind not in (None, 'rule', 'objection', 'family'): raise ValueError('Invalid kind')
        if not 1 <= len(q) <= 2000: raise ValueError('Search text must be 1 to 2000 characters')
        return HybridRetriever(store).search(q, kind)

    @app.post('/api/embeddings/refresh')
    def embeddings_refresh(request: RefreshRequest, actor=Depends(admin)):
        if not os.getenv('EMBEDDING_MODEL'): raise ValueError('Semantic index is not configured (EMBEDDING_MODEL)')
        limit = int(os.getenv('EMBED_REFRESH_LIMIT', '400'))
        return {'embedded_fields': refresh_embeddings(store, include_drafts=request.include_drafts, limit=limit), 'limit': limit}

    @app.post('/api/duplicates')
    def duplicates(actor=Depends(admin), _=Depends(heavy)):
        from .duplicate_detection import detect_duplicates
        run = detect_duplicates(store, SemanticEncoder() if os.getenv('EMBEDDING_MODEL') else None)
        return {'id': run['id'], 'mode': run['mode'], 'pairs': len(run['pairs'])}

    @app.post('/api/families')
    def families(actor=Depends(admin), _=Depends(heavy)):
        runs = store.list_documents('duplicate_runs')
        if not runs: raise ValueError('Run duplicate analysis first')
        latest = max(runs, key=lambda d: d['payload'].get('at', ''))
        run = latest['payload']; run['id'] = latest['id']
        from .family_detection import create_families
        return {'created': create_families(store, run)}

    @app.get('/api/documents/{kind}')
    def documents(kind: str, actor=Depends(identity)):
        if kind not in DOCUMENT_KINDS: raise HTTPException(404)
        heavy_fields = HEAVY_DOCUMENT_FIELDS.get(kind, ())
        def slim():
            out = []
            for d in store.list_documents(kind):
                payload = {k: v for k, v in d['payload'].items() if k not in heavy_fields}
                for k in heavy_fields:
                    if k in d['payload']: payload[k + '_count'] = len(d['payload'][k])
                out.append({'id': d['id'], 'payload': payload})
            return out
        return store.cached(('documents', kind), slim)

    @app.get('/api/documents/{kind}/{doc_id}')
    def document(kind: str, doc_id: str, actor=Depends(identity)):
        if kind not in DOCUMENT_KINDS: raise HTTPException(404)
        return store.get_document(kind, doc_id)

    @app.post('/api/benchmark')
    def benchmark(request: BenchmarkRequest, actor=Depends(admin)):
        from .evaluation import create_benchmark
        manifest = create_benchmark(store, request.test_ids, request.validation_ids, request.auto, reviewer_id=actor)
        # Snapshots of every eligible record stay in the database; the response stays small.
        return {**{k: v for k, v in manifest.items() if k != 'records'}, 'record_count': len(manifest.get('records', []))}

    @app.post('/api/evaluate/{manifest_id}')
    def evaluate(manifest_id: str, body: EvaluateRequest, actor=Depends(admin)):
        from .evaluation import evaluate_predictions
        return evaluate_predictions(store, manifest_id, body.predictions, body.human_scores, body.split)

    @app.post('/api/export/{manifest_id}')
    def training_export(manifest_id: str, actor=Depends(admin)):
        from .export import build_training_export
        content, result = build_training_export(store, manifest_id)
        return Response(content, media_type='application/x-ndjson', headers={'Content-Disposition': 'attachment; filename="manhaj-training.jsonl"', 'X-Export-Id': result['export_id'], 'X-Content-SHA256': result['sha256']})

    @app.get('/api/export-json')
    def json_export(actor=Depends(reviewer)):
        # Cases held out for evaluation are flagged so nobody trains on them by accident.
        reserved = {x for m in store.list_documents('dataset_manifests') for k in ('test_ids', 'validation_ids') for x in m['payload'].get(k, [])}
        records = [{**r, 'reserved_for_evaluation': r['id'] in reserved} for r in store.eligible()]
        return Response(json.dumps(records, ensure_ascii=False, indent=2), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="manhaj-approved.json"'})

    @app.post('/api/phase-two/enable')
    def enable(request: GateRequest, actor=Depends(admin)):
        from .research import certify_phase_one
        return {'gate_id': certify_phase_one(store, actor, request.coverage_verified, request.notes)}

    @app.post('/api/research')
    def research(request: ResearchRequest, actor=Depends(admin), _=Depends(heavy)):
        from .research import research_common_objections
        return research_common_objections(request.topic, request.limit, store, ROOT/'config/external_sources.json')

    app.mount('/static', StaticFiles(directory=ROOT/'web'), name='static')
    index_html = (ROOT/'web/index.html').read_text(encoding='utf-8')
    for asset in ('style.css', 'app.js'):
        index_html = index_html.replace(f'/static/{asset}"', f'/static/{asset}?v={asset_version(ROOT/"web"/asset)}"')

    @app.get('/')
    def index(): return Response(index_html, media_type='text/html; charset=utf-8')

    return app
