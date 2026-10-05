import hashlib

from fastapi.testclient import TestClient

from src import auth
from src.api import create_app
from conftest import record

TOKEN = 'operator-token-for-tests'
TOKENS = {'operator': hashlib.sha256(TOKEN.encode()).hexdigest()}
PERSON = {'name': 'أحمد المراجع', 'email': 'Ahmad@Example.com', 'password': 'a-long-passphrase'}


def client(store, **options):
    return TestClient(create_app(store, TOKENS, **options))


def bearer(token): return {'Authorization': 'Bearer ' + token}


def test_password_hashing_round_trip():
    stored = auth.hash_password('correct horse')
    assert stored.startswith('scrypt$') and 'correct horse' not in stored
    assert auth.check_password('correct horse', stored) and not auth.check_password('wrong', stored)
    assert not auth.check_password('x', 'garbage')


def test_signup_login_logout_and_roles(store):
    store.add(record())
    c = client(store)
    made = c.post('/api/auth/signup', json=PERSON)
    assert made.status_code == 201, made.text
    token = made.json()['token']
    me = c.get('/api/me', headers=bearer(token)).json()
    assert me['name'] == 'أحمد المراجع' and me['role'] == 'reviewer' and me['reviewer_id'].startswith('u-')
    # reviewers can review; project-wide actions stay with the operator
    edit = c.post('/api/records/SHB-test/review', headers=bearer(token), json={'expected_version': 1, 'action': 'edit', 'changes': {'central_claim_ar': 'تحرير'}})
    assert edit.status_code == 200, edit.text
    assert c.post('/api/benchmark', headers=bearer(token), json={'test_ids': ['SHB-test']}).status_code == 403
    history = c.get('/api/records/SHB-test/history', headers=bearer(token)).json()
    assert history[-1]['actor_name'] == 'أحمد المراجع'
    # the same email cannot register twice (case-insensitive)
    assert c.post('/api/auth/signup', json=dict(PERSON, email='ahmad@example.com')).status_code == 409
    # sign in again, then sign out ends that session only
    login = c.post('/api/auth/login', json={'email': 'ahmad@example.com', 'password': PERSON['password']})
    assert login.status_code == 200
    second = login.json()['token']
    assert c.post('/api/auth/logout', headers=bearer(second)).status_code == 204
    assert c.get('/api/me', headers=bearer(second)).status_code == 401
    assert c.get('/api/me', headers=bearer(token)).status_code == 200
    # the password is never stored in clear text
    with store.engine.connect() as conn:
        assert PERSON['password'] not in str(conn.exec_driver_sql('select password_hash from accounts').fetchall())


def test_signup_validation_and_admin_emails(store, monkeypatch):
    c = client(store)
    assert c.post('/api/auth/signup', json=dict(PERSON, email='not-an-email')).status_code == 422
    assert c.post('/api/auth/signup', json=dict(PERSON, password='short')).status_code == 422
    assert c.post('/api/auth/signup', json=dict(PERSON, name='x')).status_code == 422
    assert c.post('/api/auth/signup', json=dict(PERSON, extra='nope')).status_code == 422
    monkeypatch.setenv('ADMIN_EMAILS', 'ahmad@example.com')
    c = client(store)
    token = c.post('/api/auth/signup', json=PERSON).json()['token']
    assert c.get('/api/me', headers=bearer(token)).json()['role'] == 'admin'


def test_failed_logins_are_throttled_and_uniform(store):
    c = client(store)
    c.post('/api/auth/signup', json=PERSON)
    unknown = c.post('/api/auth/login', json={'email': 'nobody@example.com', 'password': 'whatever-123'})
    wrong = c.post('/api/auth/login', json={'email': 'ahmad@example.com', 'password': 'whatever-123'})
    assert unknown.status_code == wrong.status_code == 401 and unknown.json() == wrong.json()
    for _ in range(7): c.post('/api/auth/login', json={'email': 'ahmad@example.com', 'password': 'nope-nope'})
    assert c.post('/api/auth/login', json={'email': 'ahmad@example.com', 'password': PERSON['password']}).status_code == 429


def test_signups_per_client_are_limited_and_can_be_closed(store, monkeypatch):
    c = client(store)
    for n in range(5):
        assert c.post('/api/auth/signup', json=dict(PERSON, email=f'p{n}@example.com')).status_code == 201
    assert c.post('/api/auth/signup', json=dict(PERSON, email='p9@example.com')).status_code == 429
    monkeypatch.setenv('SIGNUP_ENABLED', '0')
    assert client(store).post('/api/auth/signup', json=dict(PERSON, email='late@example.com')).status_code == 403


def test_read_only_preview_still_allows_sign_in(store):
    rw = client(store)
    rw.post('/api/auth/signup', json=PERSON)
    ro = client(store, read_only=True)
    assert ro.post('/api/auth/signup', json=dict(PERSON, email='new@example.com')).status_code == 403
    assert ro.post('/api/auth/login', json={'email': 'ahmad@example.com', 'password': PERSON['password']}).status_code == 200
