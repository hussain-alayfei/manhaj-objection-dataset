"""Questions about a finished analysis: answered from that analysis only, streamed, kept with it, and limited to its owner."""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from openai import OpenAIError

from src.api import create_app
from src.classification import followup

TOKENS = {'expert': 'a' * 64}
ANALYSIS = {'input_ar': 'كيف يقول سبعين خريفًا ومائة عام؟', 'requested_by': None, 'created_at': '2026-10-07T10:00:00+00:00',
            'analysis': {'primary_pattern': 'جمع بين مختلفين'}, 'mode': 'draft',
            'method': {'steps': {'step11_answer': {'summary': 'العددان للتكثير'}}, 'review': {'holds': True}},
            'library': {'excerpts': [{'label': 'شروح الحديث', 'book': 'فتح الباري', 'vol': '6', 'page': 57, 'text': 'السبعون للتكثير'}]}}


class Stream:
    def __init__(self, parts, error=None): self.parts, self.error = parts, error
    def __enter__(self):
        if self.error: raise self.error
        return self
    def __exit__(self, *_): return False
    def __iter__(self): return (SimpleNamespace(type='response.output_text.delta', delta=p) for p in self.parts)
    def get_final_response(self): return SimpleNamespace(output_text=''.join(self.parts))


class Provider:
    def __init__(self, parts=('### الجواب\n', 'العدد ', 'للتكثير.'), error=None): self.parts, self.error, self.requests = parts, error, []
    def stream(self, **request):
        self.requests.append(request)
        return Stream(self.parts, self.error)


def signed_in(client, email='reader@example.com'):
    return client.post('/api/auth/signup', json={'name': 'باحث', 'email': email, 'password': 'Quiet-River-73'}).json()['token']


def owner(client, token):
    return client.get('/api/me', headers={'Authorization': 'Bearer ' + token}).json()['reviewer_id']


def saved_analysis(store, actor, **changes):
    return store.save_document('diagnoses', {**ANALYSIS, 'requested_by': actor, **changes})


def ask(client, token, did, question='لماذا حُمل العدد على التكثير؟'):
    with client.stream('POST', f'/api/diagnoses/{did}/ask', headers={'Authorization': 'Bearer ' + token}, json={'question': question}) as response:
        return response.status_code, [json.loads(line) for line in response.iter_lines() if line] if response.status_code == 200 else response.read()


def test_the_model_sees_the_analysis_its_sources_and_the_earlier_turns(monkeypatch):
    provider = Provider()
    monkeypatch.setenv('DIAGNOSIS_MODEL', 'gpt-test')
    earlier = {**ANALYSIS, 'conversation': [{'question': 'سؤال أول', 'answer': 'جواب أول'}]}
    deltas = []
    text = followup.answer(earlier, 'سؤال ثان', client=SimpleNamespace(responses=provider), on_delta=deltas.append)
    assert text == '### الجواب\nالعدد للتكثير.' and ''.join(deltas) == text
    sent = provider.requests[0]
    assert sent['store'] is False and sent['model'] == 'gpt-test'
    roles = [m['role'] for m in sent['input']]
    assert roles == ['system', 'user', 'user', 'assistant', 'user'] and sent['input'][-1]['content'] == 'سؤال ثان'
    context = sent['input'][1]['content']
    assert 'فتح الباري' in context and 'العددان للتكثير' in context


def test_unsafe_answers_and_provider_failures_are_not_shown(monkeypatch):
    monkeypatch.setenv('DIAGNOSIS_MODEL', 'gpt-test')
    for provider, reason in ((Provider(parts=('أفتيك بكذا',)), 'safety_gate'), (Provider(error=OpenAIError('down')), 'provider_error')):
        try:
            followup.answer(ANALYSIS, 'سؤال', client=SimpleNamespace(responses=provider))
        except ValueError as error:
            assert str(error).startswith(reason)
        else:
            raise AssertionError('expected a refusal')


def test_the_endpoint_streams_the_answer_and_keeps_it_with_the_analysis(store, monkeypatch):
    provider = Provider()
    monkeypatch.setenv('LLM_PROVIDER', 'openai'); monkeypatch.setenv('OPENAI_API_KEY', 'test'); monkeypatch.setenv('DIAGNOSIS_MODEL', 'gpt-test')
    monkeypatch.setattr(followup, 'openai_client', lambda **_: SimpleNamespace(responses=provider))
    client = TestClient(create_app(store, TOKENS, hosted=False))
    token = signed_in(client)
    did = saved_analysis(store, owner(client, token))
    status, events = ask(client, token, did)
    assert status == 200
    assert ''.join(e['text'] for e in events if e['type'] == 'delta') == '### الجواب\nالعدد للتكثير.'
    assert events[-1]['type'] == 'result' and events[-1]['data']['question'] == 'لماذا حُمل العدد على التكثير؟'
    saved = client.get('/api/diagnoses/' + did, headers={'Authorization': 'Bearer ' + token}).json()
    assert [t['answer'] for t in saved['conversation']] == ['### الجواب\nالعدد للتكثير.']


def test_only_the_owner_can_ask_and_only_about_a_finished_analysis(store, monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'openai'); monkeypatch.setenv('OPENAI_API_KEY', 'test'); monkeypatch.setenv('DIAGNOSIS_MODEL', 'gpt-test')
    monkeypatch.setattr(followup, 'openai_client', lambda **_: SimpleNamespace(responses=Provider()))
    client = TestClient(create_app(store, TOKENS, hosted=False))
    mine, theirs = signed_in(client), signed_in(client, 'other@example.com')
    did = saved_analysis(store, owner(client, mine))
    assert ask(client, theirs, did)[0] == 404
    unfinished = saved_analysis(store, owner(client, mine), method=None)
    assert ask(client, mine, unfinished)[0] == 409
    assert ask(client, mine, did, question='   ')[0] in (400, 422)


def test_a_provider_failure_arrives_as_an_event_and_nothing_is_saved(store, monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'openai'); monkeypatch.setenv('OPENAI_API_KEY', 'test'); monkeypatch.setenv('DIAGNOSIS_MODEL', 'gpt-test')
    monkeypatch.setattr(followup, 'openai_client', lambda **_: SimpleNamespace(responses=Provider(error=OpenAIError('down'))))
    client = TestClient(create_app(store, TOKENS, hosted=False))
    token = signed_in(client)
    did = saved_analysis(store, owner(client, token))
    status, events = ask(client, token, did)
    assert status == 200 and events[-1] == {'type': 'error', 'detail': 'تعذّر الجواب الآن. حاول مرة أخرى بعد قليل.'}
    assert not client.get('/api/diagnoses/' + did, headers={'Authorization': 'Bearer ' + token}).json().get('conversation')
