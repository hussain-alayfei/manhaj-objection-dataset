"""Audit follow-ups: bounded inputs, atomic usage limits, cache safety, clear 4xx errors."""
import hashlib
import threading

import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.storage import object_key
from conftest import record

TOKEN = 'hardening-token'
AUTH = {'Authorization': 'Bearer ' + TOKEN}
TOKENS = {'expert': hashlib.sha256(TOKEN.encode()).hexdigest()}


def client(store, **options):
    return TestClient(create_app(store, TOKENS, **options))


def test_wrong_types_and_oversized_reviews_are_rejected_cleanly(store):
    store.add(record())
    c = client(store)
    for changes in ({'methodology_rule_ids': 5}, {'examples': 5}, {'objection_text_ar': 5}, {'methodology_rule_ids': [['x']]}):
        r = c.post('/api/records/SHB-test/review', headers=AUTH, json={'expected_version': 1, 'action': 'edit', 'changes': changes})
        assert r.status_code == 422, (changes, r.status_code)
    huge = c.post('/api/records/SHB-test/review', headers=AUTH, json={'expected_version': 1, 'action': 'edit', 'changes': {'title_ar': 'ن' * 70000}})
    assert huge.status_code == 422
    notes = c.post('/api/records/SHB-test/review', headers=AUTH, json={'expected_version': 1, 'action': 'edit', 'notes': 'ن' * 6000})
    assert notes.status_code == 422
    body = c.post('/api/diagnose', headers={**AUTH, 'Content-Type': 'application/json'}, content=b'{"text":"' + b'a' * 300000 + b'"}')
    assert body.status_code == 413
    assert c.get('/api/records?status=bogus', headers=AUTH).status_code == 422
    assert c.get('/api/records?q=' + 'x' * 300, headers=AUTH).status_code == 422


def test_daily_limit_holds_under_parallel_requests(tmp_path, monkeypatch):
    from src.db import Store
    monkeypatch.setenv('DIAGNOSE_DAILY_LIMIT', '1')
    c = client(Store(f'sqlite:///{tmp_path}/parallel.db'))  # separate connections per thread, like production
    codes = []
    def call(): codes.append(c.post('/api/diagnose', headers=AUTH, json={'text': 'مثال'}).status_code)
    threads = [threading.Thread(target=call) for _ in range(6)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert sorted(codes) == [200] + [429] * 5


def test_overall_daily_limit_covers_every_account(store, monkeypatch):
    monkeypatch.setenv('DIAGNOSE_GLOBAL_DAILY_LIMIT', '2')
    c = client(store)
    a = c.post('/api/auth/signup', json={'name': 'أول', 'email': 'a@example.com', 'password': 'passphrase-a'}).json()['token']
    b = c.post('/api/auth/signup', json={'name': 'ثان', 'email': 'b@example.com', 'password': 'passphrase-b'}).json()['token']
    codes = [c.post('/api/diagnose', headers={'Authorization': 'Bearer ' + t}, json={'text': 'مثال'}).status_code for t in (a, b, a)]
    assert codes == [200, 200, 429]


def test_read_cache_is_bounded_and_never_stores_stale_reads(store):
    for n in range(400): store.cached(('k', n), lambda n=n: n)
    assert len(store._cache) <= 256
    def racing():
        store.clear_cache()  # a write lands while this read is in flight
        return 'old'
    assert store.cached('race', racing) == 'old'
    assert 'race' not in store._cache


def test_source_ids_cannot_escape_storage():
    assert object_key('SRC-abc_1') == 'SRC-abc_1/original.pdf'
    for bad in (r'C:\Windows', '../x', 'a/b', '', 'x' * 81):
        with pytest.raises(ValueError): object_key(bad)


def test_early_rejections_keep_security_headers(store):
    r = client(store).get('/api/me', headers={**AUTH, 'Origin': 'https://evil.test'})
    assert r.status_code == 403 and 'Content-Security-Policy' in r.headers and r.headers['X-Content-Type-Options'] == 'nosniff'
    assert "form-action 'self'" in r.headers['Content-Security-Policy']
