"""A reviewer's own analyses (history, feedback, delete) and profile edits."""
import hashlib

from fastapi.testclient import TestClient

from src.api import create_app
from conftest import approve, record

TOKEN = 'operator-token-history'
TOKENS = {'operator': hashlib.sha256(TOKEN.encode()).hexdigest()}
A = {'name': 'مراجع أول', 'email': 'first@example.com', 'password': 'river-stone-7'}
B = {'name': 'مراجع ثان', 'email': 'second@example.com', 'password': 'cedar-light-4'}


def bearer(t): return {'Authorization': 'Bearer ' + t}


def test_history_is_private_and_supports_feedback_and_delete(store):
    c = TestClient(create_app(store, TOKENS))
    a = c.post('/api/auth/signup', json=A).json()['token']
    b = c.post('/api/auth/signup', json=B).json()['token']
    first = c.post('/api/diagnose', headers=bearer(a), json={'text': 'شبهة أولى للاختبار'}).json()
    c.post('/api/diagnose', headers=bearer(a), json={'text': 'شبهة ثانية للاختبار'})
    mine = c.get('/api/diagnoses', headers=bearer(a)).json()
    assert mine['total'] == 2 and mine['items'][0]['input_ar'] == 'شبهة ثانية للاختبار'
    assert c.get('/api/diagnoses', headers=bearer(b)).json()['total'] == 0
    assert c.get(f"/api/diagnoses/{first['id']}", headers=bearer(b)).status_code == 404  # never someone else's
    detail = c.get(f"/api/diagnoses/{first['id']}", headers=bearer(a)).json()
    assert detail['input_ar'] == 'شبهة أولى للاختبار'
    fb = c.post(f"/api/diagnoses/{first['id']}/feedback", headers=bearer(a), json={'verdict': 'wrong', 'note': 'القاعدة غير مناسبة'})
    assert fb.status_code == 200 and c.get('/api/diagnoses', headers=bearer(a)).json()['items'][1]['feedback']['verdict'] == 'wrong'
    assert c.delete(f"/api/diagnoses/{first['id']}", headers=bearer(b)).status_code == 404
    assert c.delete(f"/api/diagnoses/{first['id']}", headers=bearer(a)).status_code == 204
    assert c.get('/api/diagnoses', headers=bearer(a)).json()['total'] == 1


def test_profile_name_email_password(store):
    store.add(record())
    c = TestClient(create_app(store, TOKENS))
    a = c.post('/api/auth/signup', json=A).json()['token']
    other = c.post('/api/auth/login', json={'email': A['email'], 'password': A['password']}).json()['token']
    c.post('/api/auth/signup', json=B)
    info = c.get('/api/account', headers=bearer(a)).json()
    assert info['editable'] and info['email'] == 'first@example.com' and info['activity']['analyses'] == 0
    assert c.patch('/api/account', headers=bearer(a), json={'name': 'اسم جديد'}).json()['name'] == 'اسم جديد'
    assert c.get('/api/me', headers=bearer(a)).json()['name'] == 'اسم جديد'
    c.post('/api/records/SHB-test/review', headers=bearer(a), json={'expected_version': 1, 'action': 'edit', 'changes': {'central_claim_ar': 'تعديل'}})
    assert c.get('/api/records/SHB-test/history', headers=bearer(a)).json()[-1]['actor_name'] == 'اسم جديد'
    assert c.get('/api/account', headers=bearer(a)).json()['activity']['edited'] == 1
    # email: needs the current password, and must be free
    assert c.post('/api/account/email', headers=bearer(a), json={'email': 'x@example.com', 'password': 'wrong-pass-1'}).status_code == 403
    assert c.post('/api/account/email', headers=bearer(a), json={'email': B['email'], 'password': A['password']}).status_code == 409
    assert c.post('/api/account/email', headers=bearer(a), json={'email': 'new@example.com', 'password': A['password']}).status_code == 200
    # password: current one required, new one follows the rules, other devices are signed out
    assert c.post('/api/account/password', headers=bearer(a), json={'current_password': 'nope-nope-1', 'new_password': 'brand-new-2'}).status_code == 403
    assert c.post('/api/account/password', headers=bearer(a), json={'current_password': A['password'], 'new_password': 'short'}).status_code == 422
    assert c.post('/api/account/password', headers=bearer(a), json={'current_password': A['password'], 'new_password': 'brand-new-2'}).status_code == 200
    assert c.get('/api/me', headers=bearer(a)).status_code == 200
    assert c.get('/api/me', headers=bearer(other)).status_code == 401
    assert c.post('/api/auth/login', json={'email': 'new@example.com', 'password': 'brand-new-2'}).status_code == 200


def test_operator_profile_is_read_only(store):
    c = TestClient(create_app(store, TOKENS))
    info = c.get('/api/account', headers=bearer(TOKEN)).json()
    assert info['editable'] is False and info['role'] == 'admin'
    assert c.patch('/api/account', headers=bearer(TOKEN), json={'name': 'تغيير'}).status_code == 409


def test_profile_picture_is_validated_and_shown(store):
    import base64
    c = TestClient(create_app(store, TOKENS))
    a = c.post('/api/auth/signup', json=A).json()['token']
    png = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'0' * 64).decode()
    assert c.post('/api/account/avatar', headers=bearer(a), json={'image': png}).status_code == 200
    assert c.get('/api/me', headers=bearer(a)).json()['avatar'] == png
    assert c.get('/api/account', headers=bearer(a)).json()['avatar'] == png
    fake = 'data:image/png;base64,' + base64.b64encode(b'<svg onload=alert(1)>').decode()
    assert c.post('/api/account/avatar', headers=bearer(a), json={'image': fake}).status_code == 422
    assert c.post('/api/account/avatar', headers=bearer(a), json={'image': 'data:image/svg+xml;base64,AAAA'}).status_code == 422
    assert c.delete('/api/account/avatar', headers=bearer(a)).status_code == 204
    assert c.get('/api/me', headers=bearer(a)).json()['avatar'] is None
    assert c.get('/api/account', headers=bearer(a)).json()['name'] == A['name']  # removing the picture keeps the name


def test_book_text_is_given_to_the_analyst_as_printed():
    from src.parsing import printed
    assert printed('قال تعالى}وما قدروا الله حق قدره{ فأصل') == 'قال تعالى﴿وما قدروا الله حق قدره﴾ فأصل'
    assert printed('مختلفين ، فهم') == 'مختلفين، فهم'
    from src.classification.pipeline import SYSTEM
    assert 'لا تُفتي' in SYSTEM and 'methodology_rule_ids' in SYSTEM
