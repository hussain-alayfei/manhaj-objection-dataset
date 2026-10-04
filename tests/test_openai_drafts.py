import typing
from types import SimpleNamespace

import pytest
from openai import OpenAIError
from openai.lib._pydantic import to_strict_json_schema

from src.classification import diagnose
from src.classification.pipeline import OpenAIAnalyst, analyst_payload, get_analyst
from src.models import SUBPATTERNS, AnalysisProposal, ReviewRequest, SubPattern
from src.parsing.model_extraction import ExtractionBatchStrict, OpenAISourceExtractor
from src.retrieval import HybridRetriever, refresh_embeddings
from src.retrieval.hybrid import SemanticEncoder
from conftest import approve, record


def proposal(**changes):
    data = dict(central_claim_ar='الفاكهتان متماثلتان', subclaims_ar=[], key_terms_ar=['الوزن'], compared_entities_ar=[{'entity_a': 'تفاحة', 'entity_b': 'تفاحة'}],
                primary_pattern='جمع بين مختلفين', sub_patterns=['اختلاف الحال'], diagnostic_reason_ar='سوى بين حالتين مختلفتين', revealing_question_ar='ما الفارق المؤثر؟',
                treatment_ar='بيّن الفارق', response_path_ar=['حرر الدعوى'], methodology_rule_ids=['RUL-test'], confidence=1.4)
    data.update(changes)
    return AnalysisProposal.model_validate(data)


class FakeResponses:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def parse(self, **request):
        self.calls.append(request)
        if self.error: raise self.error
        return SimpleNamespace(output_parsed=self.result)


def openai_analyst(monkeypatch, result=None, error=None):
    monkeypatch.setenv('DIAGNOSIS_MODEL', 'gpt-test')
    responses = FakeResponses(result, error)
    return OpenAIAnalyst(client=SimpleNamespace(responses=responses)), responses


def test_strict_schemas_are_accepted_by_openai_sdk():
    for model in (AnalysisProposal, ExtractionBatchStrict):
        schema = to_strict_json_schema(model)
        assert schema['additionalProperties'] is False
        assert set(schema['required']) == set(schema['properties'])
    assert set(typing.get_args(SubPattern)) == set(sum(SUBPATTERNS.values(), []))


def test_openai_analyst_success_is_grounded(store, monkeypatch):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    analyst, responses = openai_analyst(monkeypatch, proposal())
    monkeypatch.setenv('DIAGNOSIS_REASONING_EFFORT', 'low')
    result = diagnose(store, 'تفاحتين', analyst=analyst, requested_by='expert')
    assert result['abstention_reason'] is None and result['mode'] == 'approved'
    assert result['analysis']['methodology_rule_ar'] == 'افحص الفارق المؤثر'  # canonical text, not model text
    assert result['analysis']['confidence'] == 1.0  # clamped
    assert result['analysis_model'] == 'gpt-test' and result['requested_by'] == 'expert'
    call = responses.calls[0]
    assert call['store'] is False and call['text_format'] is AnalysisProposal and call['reasoning'] == {'effort': 'low'}


@pytest.mark.parametrize('result,error', [(None, None), (proposal(), OpenAIError('boom')), (proposal(methodology_rule_ids=['RUL-invented']), None)])
def test_openai_failures_abstain(store, monkeypatch, result, error):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    analyst, _ = openai_analyst(monkeypatch, result, error)
    out = diagnose(store, 'تفاحتين', analyst=analyst)
    assert out['abstention_reason'] == 'model_or_grounding_validation_failed'
    assert out['analysis']['primary_pattern'] == 'insufficient_evidence'
    assert out['analysis_model'] is None and out['abstention_detail']


def test_missing_key_abstains_instead_of_crashing(store, monkeypatch):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    monkeypatch.setenv('LLM_PROVIDER', 'openai'); monkeypatch.setenv('DIAGNOSIS_MODEL', 'gpt-test')
    assert isinstance(get_analyst(), OpenAIAnalyst)
    assert diagnose(store, 'تفاحتين')['abstention_reason'] == 'model_or_grounding_validation_failed'


def test_draft_mode_is_opt_in_and_labelled(store, monkeypatch):
    store.add(record('RUL-test', 'rule')); store.add(record('SHB-pending'))
    analyst, _ = openai_analyst(monkeypatch, proposal())
    strict = diagnose(store, 'تفاحتين', analyst=analyst)
    assert strict['abstention_reason'] == 'no_approved_methodology' and strict['mode'] == 'approved'
    assert HybridRetriever(store).search('تفاحتين', 'rule')['results'] == []
    draft = diagnose(store, 'تفاحتين', analyst=analyst, include_drafts=True)
    assert draft['mode'] == 'draft' and draft['abstention_reason'] is None
    assert draft['evidence_label_ar'].startswith('مسودة')
    assert draft['source_evidence'][0]['review_status'] == 'needs_review'
    assert {r['review_status'] for r in draft['retrieved_rules']} == {'needs_review'}


def test_draft_payload_hides_machine_analysis(store):
    store.add(record('RUL-test', 'rule')); store.add(record('SHB-pending'))
    rules, examples = store.records('rule'), store.records('objection')
    payload, system = analyst_payload('نص', rules, examples)
    assert 'candidate_rules' in payload and 'approved_rules' not in payload
    assert 'analysis' not in payload['candidate_examples'][0]
    assert 'مرشحة' in system
    approve(store, 'RUL-test')
    payload, _ = analyst_payload('نص', store.records('rule'), [])
    assert 'approved_rules' in payload


def test_rejected_records_never_used_even_in_draft_mode(store):
    store.add(record('RUL-test', 'rule'))
    store.review('RUL-test', ReviewRequest(expected_version=1, action='reject'), 'expert')
    assert HybridRetriever(store).search('تفاحتين', 'rule', include_drafts=True)['results'] == []


class FakeEmbeddings:
    def __init__(self, dim=4): self.dim, self.batches = dim, []

    def create(self, model, input, dimensions):
        assert all(t.strip() for t in input) and dimensions == self.dim
        self.batches.append(len(input))
        return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=[1.0] + [0.0] * (dimensions - 1)) for i in reversed(range(len(input)))])


def test_openai_encoder_batches_and_keys_by_dimension(monkeypatch):
    monkeypatch.setenv('EMBEDDING_PROVIDER', 'openai'); monkeypatch.setenv('EMBEDDING_DIM', '4')
    fake = FakeEmbeddings()
    encoder = SemanticEncoder('text-embedding-3-small', client=SimpleNamespace(embeddings=fake))
    assert encoder.model == 'text-embedding-3-small@4'
    vectors = encoder.encode(['نص'] * 200 + ['', '  '])
    assert fake.batches == [128, 72]
    assert vectors[0] == [1.0, 0.0, 0.0, 0.0] and vectors[-1] == [0.0] * 4


def test_refresh_embeddings_is_incremental(store, monkeypatch):
    class Counting:
        model = 'counting'
        def __init__(self): self.texts = 0
        def encode(self, texts):
            self.texts += len(texts)
            return [[1.0, 0.0, 0.0] for _ in texts]
    store.add(record('RUL-test', 'rule')); store.add(record('SHB-pending'))
    enc = Counting()
    assert refresh_embeddings(store, enc) == 0  # nothing approved yet
    first = refresh_embeddings(store, enc, include_drafts=True)
    assert first > 0 and enc.texts == first
    assert refresh_embeddings(store, enc, include_drafts=True) == 0  # unchanged: no provider call
    calls = enc.texts
    approve(store, 'RUL-test')  # new version, same text: vectors reused without calling the provider
    assert refresh_embeddings(store, enc, include_drafts=True) > 0 and enc.texts == calls


def test_openai_extractor_converts_strict_batch(monkeypatch):
    monkeypatch.setenv('EXTRACTOR_MODEL', 'gpt-test')
    item = {'item_type': 'methodology_rule', 'title_ar': 'قاعدة', 'exact_quote': 'افحص الفارق المؤثر', 'analysis': proposal().model_dump()}
    responses = FakeResponses(ExtractionBatchStrict.model_validate({'items': [item]}))
    batch = OpenAISourceExtractor(client=SimpleNamespace(responses=responses)).extract('نص')
    assert batch.items[0].analysis.methodology_rule_ar == '' and responses.calls[0]['store'] is False
