import hashlib
from fastapi.testclient import TestClient
from src.api import create_app
from conftest import record

TOKEN='test-token-do-not-use-in-deployment'


def test_auth_and_source_protection(store):
    store.add(record())
    app=create_app(store,{'expert':hashlib.sha256(TOKEN.encode()).hexdigest()})
    client=TestClient(app)
    assert client.get('/health').status_code==200
    assert client.get('/api/records').status_code==401
    assert client.get('/api/sources/SRC-test/chunks').status_code==401
    h={'Authorization':'Bearer '+TOKEN}
    r=client.get('/api/records',headers=h)
    assert r.status_code==200 and r.json()['total']==1
    assert "script-src 'self'" in r.headers['Content-Security-Policy']
    assert client.post('/api/records/SHB-test/review',headers=h,json={'expected_version':1,'action':'approve'}).status_code==422
    assert client.get('/api/records',headers={**h,'Origin':'https://evil.test'}).status_code==403


def test_no_default_credentials(store):
    import pytest
    with pytest.raises(RuntimeError):create_app(store,{})
