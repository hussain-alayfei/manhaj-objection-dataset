import hashlib
import hmac
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select

from .classification import diagnose
from .db import Conflict, Store, normalize_database_url, sources
from .duplicate_detection import detect_duplicates
from .evaluation import create_benchmark, evaluate_predictions
from .export import build_training_export
from .family_detection import create_families
from .ingestion import ingest_pdf
from .llm import llm_provider, validate_config
from .models import ReviewRequest, SUBPATTERNS
from .parsing.extraction import extract_source
from .research import certify_phase_one, research_common_objections
from .retrieval import HybridRetriever, refresh_embeddings
from .retrieval.hybrid import SemanticEncoder
from .storage import get_storage

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger('manhaj.api')
CLI_ONLY = 'متاح من سطر الأوامر فقط في النسخة المستضافة'
# Heavy summary fields stay out of list responses (Vercel caps responses at 4.5 MB); fetch details by id.
HEAVY_DOCUMENT_FIELDS = {'dataset_manifests': ('records',), 'extraction_runs': ('inventory',), 'duplicate_runs': ('suggestions', 'pairs'), 'evaluation_runs': ('predictions',)}
DOCUMENT_KINDS = ('dataset_manifests', 'evaluation_runs', 'extraction_runs', 'duplicate_runs', 'training_exports', 'phase_gates', 'source_items')


class DiagnoseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    include_drafts: bool = False


class BenchmarkRequest(BaseModel):
    test_ids: list[str] = []
    validation_ids: list[str] = []
    auto: bool = False


class GateRequest(BaseModel):
    coverage_verified: bool
    notes: str


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=50)


class RefreshRequest(BaseModel):
    include_drafts: bool = True


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


def create_app(store=None, token_map=None, *, hosted=None, read_only=None, storage=None):
    # Validate configuration before touching the database or the (read-only, when hosted) filesystem.
    token_map = token_map if token_map is not None else json.loads(os.getenv('REVIEWER_TOKEN_HASHES', '{}'))
    if not token_map: raise RuntimeError('Configure reviewer tokens with python scripts/create_reviewer.py; no default credentials exist')
    if any(len(v) != 64 for v in token_map.values()): raise RuntimeError('Reviewer secrets must be SHA-256 digests')
    hosted = bool(os.getenv('VERCEL')) if hosted is None else hosted
    read_only = _flag('READ_ONLY') if read_only is None else read_only
    heavy_allowed = not hosted or _flag('ENABLE_HEAVY_ENDPOINTS')
    if store is None:
        validate_config()
        url = normalize_database_url(os.getenv('DATABASE_URL', ''))
        if hosted and (not url or url.startswith('sqlite')) and not _flag('ALLOW_SQLITE_SMOKE'):
            raise RuntimeError('Hosted deployments require a PostgreSQL DATABASE_URL (Supabase transaction pooler)')
        store = Store(url or None)
    storage = storage or get_storage()
    store.register_reviewers(token_map)
    daily_limit = int(os.getenv('DIAGNOSE_DAILY_LIMIT', '0') or 0)
    app = FastAPI(title='مَنْهَج', version='0.2.0', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    def identity(authorization: Annotated[str | None, Header()] = None):
        if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401, 'Reviewer authentication required')
        digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
        for rid, expected in token_map.items():
            if hmac.compare_digest(expected, digest): return rid
        raise HTTPException(401, 'Invalid reviewer token')

    def heavy():
        if not heavy_allowed: raise HTTPException(409, CLI_ONLY)

    @app.middleware('http')
    async def security_headers(request, call_next):
        # Explicit bearer authentication, same-origin UI, and no cookie sessions.
        origin = request.headers.get('origin')
        if origin is not None and not same_origin(request, origin):
            return JSONResponse({'detail': 'Cross-origin request blocked'}, status_code=403)
        if read_only and request.method not in ('GET', 'HEAD', 'OPTIONS') and request.url.path != '/api/diagnose':
            return JSONResponse({'detail': 'نسخة معاينة للقراءة فقط'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' blob: data:; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.exception_handler(Conflict)
    async def conflict_error(_, exc): return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def value_error(_, exc): return JSONResponse({'detail': str(exc)}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing_error(_, exc): return JSONResponse({'detail': 'Record not found'}, status_code=404)

    @app.get('/health')
    def health():
        with store.engine.connect() as c: c.execute(select(1))
        return {'status': 'ok', 'service': 'manhaj'}

    @app.get('/api/me')
    def me(actor=Depends(identity)):
        return {'reviewer_id': actor, 'taxonomy': SUBPATTERNS, 'capabilities': {'heavy_jobs': heavy_allowed, 'read_only': read_only, 'hosted': hosted, 'storage': storage.backend, 'semantic': bool(os.getenv('EMBEDDING_MODEL')), 'llm': llm_provider(), 'draft_mode': True, 'diagnose_daily_limit': daily_limit or None}}

    @app.get('/api/summary')
    def summary(actor=Depends(identity)):
        counts = store.counts()
        rows = [dict(r, kind=k) for k in ('objection', 'rule', 'family') for r in counts[k]]
        total = lambda pred: sum(r['n'] for r in rows if pred(r))
        return {'sources': counts['sources'], 'objections': total(lambda r: r['kind'] == 'objection'), 'rules': total(lambda r: r['kind'] == 'rule'), 'families': total(lambda r: r['kind'] == 'family'), 'approved': total(lambda r: r['status'] == 'approved'), 'pending': total(lambda r: r['status'] in ('draft', 'needs_review')), 'external': total(lambda r: r['phase'] == 2), 'semantic_enabled': bool(os.getenv('EMBEDDING_MODEL'))}

    @app.get('/api/records')
    def records(kind: str | None = None, status: str | None = None, phase: int | None = None, q: str = '', offset: int = 0, limit: int = 50, actor=Depends(identity)):
        if kind not in (None, 'rule', 'objection', 'family'): raise ValueError('Invalid kind')
        if offset < 0 or not 1 <= limit <= 200: raise ValueError('Invalid pagination')
        if not q: return store.page(kind, status, phase, offset, limit)
        rows = [r for r in store.records(kind, status, phase) if q in r['title_ar'] or q in r['objection_text_ar'] or q in r['central_claim_ar']]
        return {'total': len(rows), 'items': rows[offset:offset+limit]}

    @app.get('/api/records/{rid}')
    def record(rid: str, actor=Depends(identity)): return store.get(rid)

    @app.get('/api/records/{rid}/history')
    def history(rid: str, actor=Depends(identity)): return store.history(rid)

    @app.post('/api/records/{rid}/review')
    def review(rid: str, request: ReviewRequest, actor=Depends(identity)):
        result = store.review(rid, request, actor)
        if os.getenv('EMBEDDING_MODEL'):
            try:  # best effort, after the review committed; never fails the review itself
                refresh_embeddings(store, include_drafts=True, record_ids=[rid])
            except Exception as error:  # noqa: BLE001 - logged and surfaced through the index refresh button
                log.warning('embedding refresh after review failed: %s', type(error).__name__)
        return result

    @app.get('/api/sources')
    def source_list(actor=Depends(identity)):
        return [{k: v for k,v in s.items() if k != 'pdf_path'} for s in store.source_list()]

    @app.get('/api/sources/{sid}/chunks')
    def source_chunks(sid: str, actor=Depends(identity)):
        # raw_text duplicates whole pages and is not shown in the UI.
        return [{k: v for k, v in c.items() if k != 'raw_text'} for c in store.source_chunks(sid)]

    @app.post('/api/sources/{sid}/model-extract')
    def model_extract(sid: str, actor=Depends(identity), _=Depends(heavy)):
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
        try: return {'url': storage.signed_url(sid, 60), 'expires_in': 60}
        except KeyError: raise HTTPException(404, 'Original PDF not uploaded to storage')

    @app.get('/api/sources/{sid}/pdf')
    def source_pdf(sid: str, actor=Depends(identity)):
        src = source_payload(sid)
        if storage.backend != 'local': raise HTTPException(409, 'Use /pdf-url for stored originals')
        path = storage.path(sid, src.get('pdf_path', ''))
        if not path.is_file(): raise HTTPException(404, 'Original PDF not available')
        return FileResponse(path, media_type='application/pdf', filename='source.pdf', content_disposition_type='inline')

    @app.post('/api/ingest')
    def ingest(file: UploadFile = File(), title: str = Form('كتاب وليد'), author: str = Form(''), profile: str = Form('standard'), actor=Depends(identity), _=Depends(heavy)):
        folder = ROOT / 'data' / 'raw'
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=folder, suffix='.pdf', delete=False) as out:
            path = Path(out.name)
            size = 0
            try:
                while block := file.file.read(1024*1024):
                    size += len(block)
                    if size > 100*1024*1024: raise ValueError('PDF exceeds 100 MB')
                    out.write(block)
            except Exception:
                out.close(); path.unlink(missing_ok=True); raise
        try:
            with path.open('rb') as inp:
                if inp.read(5) != b'%PDF-': raise ValueError('Expected a PDF file')
            src = ingest_pdf(store, path, title, author, profile, ROOT/'data')
            run = extract_source(store, src['id'], data_dir=ROOT/'data')
            return {'source_id': src['id'], 'candidate_count': run['new_records']}
        finally: path.unlink(missing_ok=True)

    @app.post('/api/diagnose')
    def diagnosis(request: DiagnoseRequest, actor=Depends(identity)):
        if daily_limit and not read_only:
            since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            if store.count_documents('diagnoses', 'requested_by', actor, since) >= daily_limit:
                raise HTTPException(429, 'تجاوزت الحد اليومي للتشخيص')
        return diagnose(store, request.text, include_drafts=request.include_drafts, requested_by=actor, persist=not read_only)

    @app.get('/api/search')
    def search(q: str, kind: str | None = None, actor=Depends(identity)): return HybridRetriever(store).search(q, kind)

    @app.post('/api/embeddings/refresh')
    def embeddings_refresh(request: RefreshRequest, actor=Depends(identity)):
        if not os.getenv('EMBEDDING_MODEL'): raise ValueError('Semantic index is not configured (EMBEDDING_MODEL)')
        limit = int(os.getenv('EMBED_REFRESH_LIMIT', '400'))
        return {'embedded_fields': refresh_embeddings(store, include_drafts=request.include_drafts, limit=limit), 'limit': limit}

    @app.post('/api/duplicates')
    def duplicates(actor=Depends(identity), _=Depends(heavy)):
        run = detect_duplicates(store, SemanticEncoder() if os.getenv('EMBEDDING_MODEL') else None)
        return {'id': run['id'], 'mode': run['mode'], 'pairs': len(run['pairs'])}

    @app.post('/api/families')
    def families(actor=Depends(identity), _=Depends(heavy)):
        runs = store.list_documents('duplicate_runs')
        if not runs: raise ValueError('Run duplicate analysis first')
        latest = max(runs, key=lambda d: d['payload'].get('at', ''))
        run = latest['payload']; run['id'] = latest['id']
        return {'created': create_families(store, run)}

    @app.get('/api/documents/{kind}')
    def documents(kind: str, actor=Depends(identity)):
        if kind not in DOCUMENT_KINDS: raise HTTPException(404)
        heavy_fields = HEAVY_DOCUMENT_FIELDS.get(kind, ())
        out = []
        for d in store.list_documents(kind):
            payload = {k: v for k, v in d['payload'].items() if k not in heavy_fields}
            for k in heavy_fields:
                if k in d['payload']: payload[k + '_count'] = len(d['payload'][k])
            out.append({'id': d['id'], 'payload': payload})
        return out

    @app.get('/api/documents/{kind}/{doc_id}')
    def document(kind: str, doc_id: str, actor=Depends(identity)):
        if kind not in DOCUMENT_KINDS: raise HTTPException(404)
        return store.get_document(kind, doc_id)

    @app.post('/api/benchmark')
    def benchmark(request: BenchmarkRequest, actor=Depends(identity)):
        return create_benchmark(store, request.test_ids, request.validation_ids, request.auto, reviewer_id=actor)

    @app.post('/api/evaluate/{manifest_id}')
    def evaluate(manifest_id: str, body: dict, actor=Depends(identity)):
        return evaluate_predictions(store, manifest_id, body.get('predictions', {}), body.get('human_scores', {}), body.get('split', 'test'))

    @app.post('/api/export/{manifest_id}')
    def training_export(manifest_id: str, actor=Depends(identity)):
        content, result = build_training_export(store, manifest_id)
        return Response(content, media_type='application/x-ndjson', headers={'Content-Disposition': 'attachment; filename="manhaj-training.jsonl"', 'X-Export-Id': result['export_id'], 'X-Content-SHA256': result['sha256']})

    @app.get('/api/export-json')
    def json_export(actor=Depends(identity)):
        return Response(json.dumps(store.eligible(), ensure_ascii=False, indent=2), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="manhaj-approved.json"'})

    @app.post('/api/phase-two/enable')
    def enable(request: GateRequest, actor=Depends(identity)):
        return {'gate_id': certify_phase_one(store, actor, request.coverage_verified, request.notes)}

    @app.post('/api/research')
    def research(request: ResearchRequest, actor=Depends(identity), _=Depends(heavy)):
        return research_common_objections(request.topic, request.limit, store, ROOT/'config/external_sources.json')

    app.mount('/static', StaticFiles(directory=ROOT/'web'), name='static')

    @app.get('/')
    def index(): return FileResponse(ROOT/'web/index.html')

    return app
