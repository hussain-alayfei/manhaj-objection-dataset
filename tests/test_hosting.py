import hashlib
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.db import Store, normalize_database_url
from src.evaluation import create_benchmark
from src.storage import SupabaseStorage, object_key
from conftest import approve, record

TOKEN = 'test-token-do-not-use-in-deployment'
AUTH = {'Authorization': 'Bearer ' + TOKEN}
TOKENS = {'expert': hashlib.sha256(TOKEN.encode()).hexdigest()}


def client(store, **options):
    return TestClient(create_app(store, TOKENS, **options))


def test_hosted_mode_blocks_long_jobs_but_not_review(store):
    store.add(record())
    c = client(store, hosted=True)
    assert c.get('/api/me', headers=AUTH).json()['capabilities']['heavy_jobs'] is False
    for path in ('/api/duplicates', '/api/families', '/api/sources/SRC-test/model-extract'):
        assert c.post(path, headers=AUTH).status_code == 409
    assert c.post('/api/research', headers=AUTH, json={'topic': 'x'}).status_code == 409
    edit = c.post('/api/records/SHB-test/review', headers=AUTH, json={'expected_version': 1, 'action': 'edit', 'changes': {'central_claim_ar': 'تحرير'}})
    assert edit.status_code == 200


def test_read_only_preview_rejects_writes_and_does_not_persist(store):
    store.add(record())
    c = client(store, read_only=True)
    assert c.post('/api/records/SHB-test/review', headers=AUTH, json={'expected_version': 1, 'action': 'edit'}).status_code == 403
    r = c.post('/api/diagnose', headers=AUTH, json={'text': 'تفاحتين'})
    assert r.status_code == 200 and 'id' not in r.json()
    assert store.list_documents('diagnoses') == []


def test_daily_diagnosis_limit(store, monkeypatch):
    monkeypatch.setenv('DIAGNOSE_DAILY_LIMIT', '2')
    c = client(store)
    assert [c.post('/api/diagnose', headers=AUTH, json={'text': 'مثال'}).status_code for _ in range(3)] == [200, 200, 429]


def test_origin_check_behind_proxy(store):
    c = client(store)
    proxy = {**AUTH, 'Host': 'internal:8080', 'X-Forwarded-Host': 'manhaj.vercel.app', 'X-Forwarded-Proto': 'https'}
    assert c.post('/api/diagnose', headers={**proxy, 'Origin': 'https://manhaj.vercel.app'}, json={'text': 'مثال'}).status_code == 200
    assert c.post('/api/diagnose', headers={**proxy, 'Origin': 'https://evil.test'}, json={'text': 'مثال'}).status_code == 403
    assert c.get('/api/me', headers={**AUTH, 'Origin': 'null'}).status_code == 403
    assert c.get('/api/me', headers={**AUTH, 'Origin': 'http://testserver'}).status_code == 200


def test_allowed_origins_env(store, monkeypatch):
    monkeypatch.setenv('ALLOWED_ORIGINS', 'https://manhaj.example')
    assert client(store).get('/api/me', headers={**AUTH, 'Origin': 'https://manhaj.example'}).status_code == 200


def test_sql_summary_and_pagination_match_python(store):
    for i in range(5): store.add(record(f'SHB-{i}'))
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    c = client(store)
    s = c.get('/api/summary', headers=AUTH).json()
    assert (s['objections'], s['rules'], s['approved'], s['pending'], s['sources']) == (5, 1, 1, 5, 1)
    page = c.get('/api/records?offset=4&limit=2', headers=AUTH).json()
    everything = store.records()
    assert page['total'] == 6 and [r['id'] for r in page['items']] == [r['id'] for r in everything[4:6]]
    assert c.get('/api/records?kind=objection&status=needs_review&limit=2', headers=AUTH).json()['total'] == 5


def test_chunks_and_documents_are_slim(store):
    c = client(store)
    assert 'raw_text' not in c.get('/api/sources/SRC-test/chunks', headers=AUTH).json()[0]
    store.save_document('duplicate_runs', {'at': '1', 'pairs': [{'a': 'x'}] * 3, 'suggestions': {}}, 'RUN-1')
    listed = c.get('/api/documents/duplicate_runs', headers=AUTH).json()[0]
    assert 'pairs' not in listed['payload'] and listed['payload']['pairs_count'] == 3
    assert len(c.get('/api/documents/duplicate_runs/RUN-1', headers=AUTH).json()['payload']['pairs']) == 3


def test_export_is_built_in_memory(store):
    for rid, word in [('A', 'اختبار'), ('B', 'مقارنة'), ('C', 'الوزن')]:
        store.add(record(rid, objection_text_ar=word)); approve(store, rid)
    manifest = create_benchmark(store, ['A'], ['B'])
    r = client(store).post(f"/api/export/{manifest['id']}", headers=AUTH)
    assert r.status_code == 200 and r.headers['content-type'].startswith('application/x-ndjson')
    assert json.loads(r.text.splitlines()[0])['messages'][1]['content'] == 'الوزن'
    exported = store.list_documents('training_exports')[0]['payload']
    assert exported['path'] is None and exported['content_sha256'] == r.headers['x-content-sha256']


def test_local_pdf_url_falls_back_to_file_endpoint(store):
    assert client(store).get('/api/sources/SRC-test/pdf-url', headers=AUTH).json() == {'url': None}


def test_supabase_storage_uses_apikey_and_absolute_signed_urls():
    seen = []

    def handler(request):
        seen.append(request)
        if '/object/sign/' in request.url.path:
            return httpx.Response(200, json={'signedURL': '/object/sign/sources/SRC-x/original.pdf?token=abc'})
        return httpx.Response(200, json={'Key': 'sources/SRC-x/original.pdf'})

    storage = SupabaseStorage('https://ref.supabase.co', 'sb_secret_test', 'sources', httpx.Client(transport=httpx.MockTransport(handler)))
    storage.upload('SRC-x', b'%PDF-1.7')
    url = storage.signed_url('SRC-x', 60)
    assert url == 'https://ref.supabase.co/storage/v1/object/sign/sources/SRC-x/original.pdf?token=abc'
    assert all(r.headers['apikey'] == 'sb_secret_test' and 'authorization' not in r.headers for r in seen)
    assert seen[0].headers['content-type'] == 'application/pdf'
    with pytest.raises(ValueError): object_key('../escape')


def test_config_validation_fails_fast(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('LLM_PROVIDER', 'openai'); monkeypatch.setenv('DIAGNOSIS_MODEL', 'gpt-test')
    with pytest.raises(RuntimeError, match='OPENAI_API_KEY'): create_app(None, TOKENS)
    monkeypatch.delenv('LLM_PROVIDER')
    with pytest.raises(RuntimeError, match='PostgreSQL'): create_app(None, TOKENS, hosted=True)
    with pytest.raises(RuntimeError, match='reviewer tokens'): create_app(None, {}, hosted=True)


def test_database_url_normalization():
    assert normalize_database_url('postgres://u:p@h:6543/db') == 'postgresql+psycopg://u:p@h:6543/db'
    assert normalize_database_url('postgresql://u:p@h/db') == 'postgresql+psycopg://u:p@h/db'
    assert normalize_database_url('sqlite:///x.db') == 'sqlite:///x.db'


def test_arabic_payloads_are_stored_as_utf8(store):
    store.add(record())
    with store.engine.connect() as c:
        raw = c.exec_driver_sql("SELECT payload FROM objections WHERE id='SHB-test'").scalar_one()
    assert 'تفاحتين' in raw and '\\u' not in raw


def test_reviewers_registered_idempotently(store):
    store.register_reviewers(['expert', 'reviewer-02'])
    store.register_reviewers(['expert', 'reviewer-02'])
    from src.db import reviewers
    with store.engine.connect() as c:
        assert sorted(c.execute(reviewers.select()).scalars()) == ['expert', 'reviewer-02']


def test_create_reviewer_token_out_never_prints_token(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'create_reviewer.py'
    env_file, token_file = tmp_path / '.env.production.local', tmp_path / 'token.txt'
    out = subprocess.run([sys.executable, str(script), 'reviewer-02', '--env-file', str(env_file), '--token-out', str(token_file)], capture_output=True, text=True, check=True)
    token = token_file.read_text(encoding='utf-8').strip()
    assert token and token not in out.stdout
    hashes = json.loads(env_file.read_text(encoding='utf-8').split('=', 1)[1])
    assert hashes == {'reviewer-02': hashlib.sha256(token.encode()).hexdigest()}


def test_assets_are_cacheable_but_api_data_is_not(store):
    c = client(store)
    html = c.get('/').text
    assert '/static/app.js?v=' in html and '/static/style.css?v=' in html
    assert c.get('/static/fonts/amiri-400-arabic.woff2').headers['cache-control'] == 'public, max-age=31536000, immutable'
    assert c.get('/static/app.js?v=abc').headers['cache-control'] == 'public, max-age=31536000, immutable'
    api = c.get('/api/me', headers=AUTH)
    assert api.headers['cache-control'] == 'no-store' and api.headers['server-timing'].startswith('app;dur=')
