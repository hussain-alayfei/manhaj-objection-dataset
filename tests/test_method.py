"""The eleven-step method: the steps arrive in order, texts are checked, and the critical reviewer can send the analysis back."""
import json
import random
from types import SimpleNamespace

from fastapi.testclient import TestClient
from openai import OpenAIError
from openai.lib._pydantic import to_strict_json_schema

from src.api import create_app
from src.classification import diagnose
from src.classification import pipeline
from src.classification.pipeline import OpenAIAnalyst, StepWatcher
from src.models import METHOD_STEPS, CriticReport, MethodProposal
from conftest import approve, method_data, record

CHECKS = ('misunderstood', 'evidence_proves', 'contrary_text', 'unsourced_attribution', 'possibility_as_certainty', 'stronger_explanation')
TOKENS = {'expert': 'a' * 64}


def review(holds=True, revision='', failing=()):
    return CriticReport.model_validate({**{k: {'ok': k not in failing, 'note': 'ملاحظة' if k in failing else ''} for k in CHECKS}, 'holds': holds, 'revision': revision})


class Stream:
    """Plays the analysis back as the provider streams it: small text deltas, then the parsed response."""

    def __init__(self, parsed):
        text = json.dumps(parsed.model_dump(), ensure_ascii=False)
        cuts = sorted(random.Random(7).sample(range(1, len(text)), 60))
        self.deltas = [text[a:b] for a, b in zip([0, *cuts], [*cuts, len(text)])]
        self.parsed = parsed

    def __enter__(self): return self
    def __exit__(self, *_): return False
    def __iter__(self): return (SimpleNamespace(type='response.output_text.delta', delta=d) for d in self.deltas)
    def get_final_response(self): return SimpleNamespace(output_parsed=self.parsed)


class Provider:
    def __init__(self, analyses, reviews=(review(),), critic_error=None):
        self.analyses, self.reviews, self.critic_error, self.calls = list(analyses), list(reviews), critic_error, []

    def stream(self, **request):
        self.calls.append(('stream', request))
        return Stream(self.analyses.pop(0) if len(self.analyses) > 1 else self.analyses[0])

    def parse(self, **request):
        self.calls.append(('parse', request))
        assert request['text_format'] is CriticReport
        if self.critic_error: raise self.critic_error
        return SimpleNamespace(output_parsed=self.reviews.pop(0) if len(self.reviews) > 1 else self.reviews[0])


def analyst_with(monkeypatch, provider):
    monkeypatch.setenv('DIAGNOSIS_MODEL', 'gpt-test')
    return OpenAIAnalyst(client=SimpleNamespace(responses=provider))


def fake_checks(refs):
    return [{'state': 'verified', 'label': 'وُجد في مصدره', 'reference': f"{r['collection']} ({r['number']})"} for r in refs]


def method(**steps):
    return MethodProposal.model_validate(method_data(**steps))


def run(store, analyst, **options):
    events = []
    # the test book's only rule is about two apples, so the question names them to be retrieved
    out = diagnose(store, 'تفاحتين: كيف يقول ﷺ سبعين خريفًا، وفي حديث آخر مائة عام؟', analyst=analyst, check_sources=fake_checks,
                   progress=lambda kind, **data: events.append((kind, data)), **options)
    return out, events


def test_method_schema_is_strict_and_keeps_the_steps_in_order():
    schema = to_strict_json_schema(MethodProposal)
    assert list(schema['properties']) == list(METHOD_STEPS) and set(schema['required']) == set(METHOD_STEPS)
    critic = to_strict_json_schema(CriticReport)
    assert list(critic['properties'])[:6] == list(CHECKS) and critic['additionalProperties'] is False


def test_steps_map_to_the_record_shape():
    a = method(governing_rules={'sub_patterns': ['اختلاف المعنى', 'لا يوجد فارق مؤثر']}, step11_answer={'confidence': 3}).to_analysis()
    assert a.central_claim_ar == 'الحديثان متعارضان' and a.subclaims_ar[-1] == 'العددان يُقارنان حسابيًا'
    assert a.compared_entities_ar[0].entity_b == '«مائة عام»' and a.primary_pattern == 'جمع بين مختلفين'
    assert a.sub_patterns == ['اختلاف المعنى']  # a sub-pattern of the other root is dropped instead of failing
    assert a.response_path_ar == ['تحرير الدعوى', 'ثبوت الروايتين', 'دلالة العدد على التكثير'] and a.confidence == 1.0


def test_watcher_reports_each_step_once_and_in_order():
    seen = []
    text = json.dumps(method_data(), ensure_ascii=False)
    watcher = StepWatcher(lambda kind, key, value: seen.append((kind, key, value)))
    for i in range(0, len(text), 37): watcher.feed(text[i:i + 37])
    watcher.finish(method_data())
    done = [(key, value) for kind, key, value in seen if kind == 'step']
    assert [key for key, _ in done] == list(METHOD_STEPS)
    assert dict(done)['step1_framing'] == method_data()['step1_framing'] and dict(done)['step11_answer']['confidence'] == 0.7
    assert [key for kind, key, _ in seen if kind == 'active'] == list(METHOD_STEPS)


def test_streamed_analysis_checks_sources_and_passes_review(store, monkeypatch):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    provider = Provider([method()])
    out, events = run(store, analyst_with(monkeypatch, provider))
    assert out['abstention_reason'] is None and out['analysis']['primary_pattern'] == 'جمع بين مختلفين'
    steps = [data['key'] for kind, data in events if kind == 'step']
    assert steps == list(METHOD_STEPS)
    kinds = [kind for kind, _ in events]
    assert kinds.index('verified') < kinds.index('critic') and kinds[0] == 'stage'
    texts = out['method']['steps']['step3_sources']['texts']
    assert [t['check']['reference'] for t in texts] == ['bukhari (2840)', 'nasai (2254)']
    assert out['method']['review'] == {'available': True, 'rounds': [review().model_dump()], 'holds': True, 'revised': False}
    assert [c for c, _ in provider.calls] == ['stream', 'parse']
    assert store.get_document('diagnoses', out['id'])['payload']['method']['review']['holds'] is True


def test_an_answer_that_does_not_hold_goes_back_to_the_analysis_once(store, monkeypatch):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    first, second = method(step11_answer={'summary': 'المسودة الأولى'}), method(step11_answer={'summary': 'بعد التصحيح'})
    provider = Provider([first, second], reviews=[review(False, 'الدليل لا يثبت النتيجة', failing=('evidence_proves',)), review()])
    out, events = run(store, analyst_with(monkeypatch, provider))
    assert [c for c, _ in provider.calls] == ['stream', 'parse', 'stream', 'parse']
    revision = json.loads(provider.calls[2][1]['input'][1]['content'])
    assert revision['critic']['revision'] == 'الدليل لا يثبت النتيجة' and revision['previous_draft']['step11_answer']['summary'] == 'المسودة الأولى'
    assert 'مراجعة ثانية' in provider.calls[2][1]['input'][0]['content']
    assert ('stage', {'stage': 'revise', 'notes': 'الدليل لا يثبت النتيجة'}) in events
    assert out['method']['steps']['step11_answer']['summary'] == 'بعد التصحيح'
    assert out['method']['review']['revised'] is True and out['method']['review']['holds'] is True and len(out['method']['review']['rounds']) == 2


def test_objections_that_remain_lower_the_confidence(store, monkeypatch):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    provider = Provider([method(step11_answer={'confidence': 0.9, 'confidence_label': 'راجح'})], reviews=[review(False, 'يوجد تفسير أقوى', failing=('stronger_explanation',))])
    out, _ = run(store, analyst_with(monkeypatch, provider))
    assert out['method']['review']['holds'] is False and out['method']['review']['revised'] is True
    assert out['analysis']['confidence'] == 0.5 and out['method']['steps']['step11_answer']['confidence_label'] == 'محتمل يحتاج نظرًا'


def test_an_unavailable_reviewer_keeps_the_analysis(store, monkeypatch):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    out, _ = run(store, analyst_with(monkeypatch, Provider([method()], critic_error=OpenAIError('down'))))
    assert out['abstention_reason'] is None and out['method']['review'] == {'available': False, 'rounds': [], 'holds': None, 'revised': False}


def test_attributing_words_in_the_explanation_is_sent_back_then_stopped(store, monkeypatch):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    quoted = method(governing_rules={'explanation': 'قال رسول الله كذا'})
    fixed = Provider([quoted, method()])
    out, _ = run(store, analyst_with(monkeypatch, fixed))
    first = out['method']['review']['rounds'][0]
    assert first['holds'] is False and 'بصيغة «قال»' in first['revision'] and out['abstention_reason'] is None
    stubborn = Provider([quoted])
    assert run(store, analyst_with(monkeypatch, stubborn))[0]['abstention_reason'] == 'safety_gate'


def test_unsafe_words_anywhere_in_the_steps_stop_the_result(store, monkeypatch):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    out, _ = run(store, analyst_with(monkeypatch, Provider([method(step4_related={'scholars': ['أفتيك بكذا']})])))
    assert out['abstention_reason'] == 'safety_gate' and out['method'] is None


def test_the_live_endpoint_streams_every_step_and_saves_the_result(store, monkeypatch):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    provider = Provider([method()])
    monkeypatch.setattr(pipeline, 'get_analyst', lambda: analyst_with(monkeypatch, provider))
    monkeypatch.setattr(pipeline.sources, 'check_texts', fake_checks)
    client = TestClient(create_app(store, TOKENS, hosted=False))
    with client.stream('POST', '/api/diagnose/stream', headers={'Authorization': 'Bearer ' + 'x'}, json={'text': 'شبهة'}) as response:
        assert response.status_code == 401
    token = client.post('/api/auth/signup', json={'name': 'باحث', 'email': 'reader@example.com', 'password': 'Quiet-River-73'}).json()['token']
    with client.stream('POST', '/api/diagnose/stream', headers={'Authorization': 'Bearer ' + token}, json={'text': 'تفاحتين: كيف يقول سبعين خريفًا ومائة عام؟'}) as response:
        assert response.status_code == 200 and response.headers['content-type'].startswith('application/x-ndjson')
        assert 'content-encoding' not in response.headers  # never buffered by compression
        events = [json.loads(line) for line in response.iter_lines() if line]
    assert [e['key'] for e in events if e['type'] == 'step'] == list(METHOD_STEPS)
    result = events[-1]
    assert result['type'] == 'result' and result['data']['method']['review']['holds'] is True
    saved = client.get('/api/diagnoses/' + result['data']['id'], headers={'Authorization': 'Bearer ' + token}).json()
    assert saved['method']['steps']['governing_rules']['fault'] == 'جمعٌ بين مختلفين'


def test_the_live_endpoint_reports_failures_as_an_event(store, monkeypatch):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    def broken(*_, **__): raise RuntimeError('unexpected')
    monkeypatch.setattr('src.api.diagnose', broken)
    client = TestClient(create_app(store, TOKENS, hosted=False))
    token = client.post('/api/auth/signup', json={'name': 'باحث', 'email': 'reader@example.com', 'password': 'Quiet-River-73'}).json()['token']
    with client.stream('POST', '/api/diagnose/stream', headers={'Authorization': 'Bearer ' + token}, json={'text': 'شبهة'}) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]
    assert events == [{'type': 'error', 'detail': 'تعذّر إكمال التحليل. حاول مرة أخرى.'}]
