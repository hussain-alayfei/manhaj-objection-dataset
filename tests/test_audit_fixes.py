"""Regression tests for the October 2026 code audit."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from src.api import create_app, remote_database
from src.evaluation import create_benchmark
from src.models import ReviewRequest
from conftest import approve, record

TOKEN = 'audit-token-not-for-deployment'
AUTH = {'Authorization': 'Bearer ' + TOKEN}


def client(store, **options):
    return TestClient(create_app(store, {'expert': hashlib.sha256(TOKEN.encode()).hexdigest()}, **options))


def test_empty_objection_wording_cannot_be_approved(store):
    store.add(record())
    with pytest.raises(ValueError, match='Exact objection wording'):
        approve(store, 'SHB-test', objection_text_ar='   ')


def test_approved_rule_text_must_quote_the_source(store):
    store.add(record('RUL-test', 'rule'))
    with pytest.raises(ValueError, match='quoted from the source'):
        approve(store, 'RUL-test', methodology_rule_ar='نص قاعدة مختلق لا يوجد في المصدر')
    assert approve(store, 'RUL-test')['review_status'] == 'approved'


def test_rule_links_recompute_rule_text_and_reject_unknown_ids(store):
    store.add(record('RUL-test', 'rule')); store.add(record())
    edited = store.review('SHB-test', ReviewRequest(expected_version=1, action='edit', changes={'methodology_rule_ids': ['RUL-test', 'RUL-test']}), 'expert')
    assert edited['methodology_rule_ids'] == ['RUL-test'] and edited['methodology_rule_ar'] == 'افحص الفارق المؤثر'
    with pytest.raises(ValueError, match='Unknown methodology rule'):
        store.review('SHB-test', ReviewRequest(expected_version=2, action='edit', changes={'methodology_rule_ids': ['RUL-missing']}), 'expert')


def test_family_examples_are_validated(store):
    from src.family_detection import create_families
    from src.duplicate_detection import detect_duplicates
    store.add(record('A')); store.add(record('RUL-test', 'rule'))
    family = create_families(store, detect_duplicates(store))[0]
    for bad in (['A', 'A', 'RUL-test'], ['missing']):
        with pytest.raises(ValueError):
            store.review(family, ReviewRequest(expected_version=1, action='edit', changes={'examples': bad}), 'expert')


def test_edited_rule_text_invalidates_approved_objection(store):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    store.add(record(primary_pattern='جمع بين مختلفين')); approve(store, 'SHB-test', methodology_rule_ids=['RUL-test'])
    assert [r['id'] for r in store.eligible('objection')] == ['SHB-test']
    store.review('RUL-test', ReviewRequest(expected_version=2, action='edit', changes={'methodology_rule_ar': 'اختبار مقارنة'}), 'expert')
    approve(store, 'RUL-test')
    assert store.eligible('objection') == []  # copied rule text is stale until the objection is re-reviewed


def test_bad_requests_get_clear_4xx(store):
    c = client(store)
    assert c.get('/api/search?q=x&kind=bogus', headers=AUTH).status_code == 422
    assert c.post('/api/evaluate/MANIFEST', headers=AUTH, json={'predictions': ['not', 'a', 'map']}).status_code == 422
    assert c.post('/api/sources/SRC-missing/model-extract', headers=AUTH).status_code in (404, 422)


def test_ingest_is_never_available_when_hosted(store, monkeypatch):
    monkeypatch.setenv('ENABLE_HEAVY_ENDPOINTS', '1')
    files = {'file': ('a.pdf', b'%PDF-1.4', 'application/pdf')}
    assert client(store, hosted=True).post('/api/ingest', headers=AUTH, files=files).status_code == 409


def test_uppercase_token_hash_still_logs_in(store):
    app = create_app(store, {'expert': hashlib.sha256(TOKEN.encode()).hexdigest().upper()})
    assert TestClient(app).get('/api/me', headers=AUTH).status_code == 200
    with pytest.raises(RuntimeError): create_app(store, {'expert': 'z' * 64})


def test_benchmark_response_is_small_and_export_flags_holdouts(store):
    for rid, word in [('A', 'اختبار'), ('B', 'مقارنة'), ('C', 'الوزن')]:
        store.add(record(rid, objection_text_ar=word)); approve(store, rid)
    c = client(store)
    manifest = c.post('/api/benchmark', headers=AUTH, json={'test_ids': ['A'], 'validation_ids': ['B']}).json()
    assert 'records' not in manifest and manifest['record_count'] == 3
    exported = {r['id']: r['reserved_for_evaluation'] for r in json.loads(c.get('/api/export-json', headers=AUTH).text)}
    assert exported == {'A': True, 'B': True, 'C': False}


def test_remote_database_detection():
    assert remote_database('postgresql+psycopg://u:p@aws-1-eu-central-1.pooler.supabase.com:5432/postgres')
    assert not remote_database('postgresql+psycopg://u:p@localhost:5432/manhaj')
    assert not remote_database('sqlite:///data/manhaj.db')
