import copy
import pytest
from pydantic import ValidationError

from src.db import Conflict
from src.models import Analysis, ReviewRequest
from src.classification import diagnose
from src.retrieval import HybridRetriever
from src.research.pipeline import require_phase_two, certify_phase_one
from conftest import record, approve


def test_new_records_cannot_be_approved(store):
    with pytest.raises(ValueError):store.add(record(review_status='approved'))


def test_exact_span_validation(store):
    r=record();r['source']['spans'][0]['text']='اختلاق'
    with pytest.raises(ValueError):store.add(r)


def test_page_validation(store):
    r=record();r['source']['spans'][0]['page_number']=99
    with pytest.raises(ValueError):store.add(r)


def test_source_metadata_validation(store):
    r=record();r['source']['author']='unknown fake author'
    with pytest.raises(ValueError):store.add(r)


def test_pending_excluded_from_rag_and_abstention(store):
    store.add(record());store.add(record('RUL-test','rule'))
    assert HybridRetriever(store).search('تفاحتين')['results']==[]
    result=diagnose(store,'هل هاتان التفاحتان متماثلتان؟')
    assert result['analysis']['primary_pattern']=='insufficient_evidence'
    assert result['source_evidence']==[]


def test_attestation_required(store):
    store.add(record())
    with pytest.raises(ValueError):store.review('SHB-test',ReviewRequest(expected_version=1,action='approve'),'expert')


def test_edit_invalidation_and_history(store):
    store.add(record());approve(store,'SHB-test')
    original=store.get('SHB-test')
    edited=store.review('SHB-test',ReviewRequest(expected_version=2,action='edit',changes={'central_claim_ar':'تحرير آخر'}),'expert')
    assert edited['review_status']=='needs_review'
    assert edited['ai_analysis']==original['ai_analysis']
    assert edited['source_evidence']==original['source_evidence']
    assert len(store.history('SHB-test'))==3
    assert store.eligible()==[]


def test_concurrent_review_conflict(store):
    store.add(record());approve(store,'SHB-test')
    with pytest.raises(Conflict):store.review('SHB-test',ReviewRequest(expected_version=1,action='edit'),'expert')


@pytest.mark.parametrize('key', ['source','source_evidence','ai_analysis','human_review','review_status','version','phase','added_by'])
def test_protected_fields(store,key):
    store.add(record())
    with pytest.raises(ValueError):store.review('SHB-test',ReviewRequest(expected_version=1,action='edit',changes={key:None}),'expert')


def test_classified_case_requires_approved_rule(store):
    store.add(record(primary_pattern='جمع بين مختلفين'))
    with pytest.raises(ValueError):approve(store,'SHB-test')
    store.add(record('RUL-test','rule'));approve(store,'RUL-test')
    approve(store,'SHB-test',methodology_rule_ids=['RUL-test'])
    assert len(store.eligible('objection'))==1
    store.review('RUL-test',ReviewRequest(expected_version=2,action='reopen'),'expert')
    assert store.eligible('objection')==[]


def test_unknown_and_mixed_are_legal():
    for p in ['unknown','mixed_pattern','multiple_claims','insufficient_evidence','requires_human_review']:assert Analysis(primary_pattern=p)
    with pytest.raises(ValidationError):Analysis(primary_pattern='تفريق بين متماثلين',sub_patterns=['اختلاف الزمن'])


def test_phase_gate_locked(store):
    store.add(record());store.add(record('RUL-test','rule'))
    with pytest.raises(ValueError):require_phase_two(store)
    with pytest.raises(ValueError):certify_phase_one(store,'expert',True,'checked')


def test_phase_gate_invalidated_by_new_data(store):
    store.add(record());store.add(record('RUL-test','rule'));approve(store,'SHB-test');approve(store,'RUL-test')
    store.save_document('extraction_runs',{'source_id':'SRC-test','kind':'all'})
    certify_phase_one(store,'expert',True,'Full source coverage checked')
    require_phase_two(store)
    store.add(record('SHB-new'))
    with pytest.raises(ValueError):require_phase_two(store)


def test_fabricated_model_reference_abstains(store):
    store.add(record('RUL-test','rule'));approve(store,'RUL-test')
    class Fake:
        def analyze(self,*_):return Analysis(primary_pattern='جمع بين مختلفين',methodology_rule_ids=['FAKE']).model_dump()
    result=diagnose(store,'تفاحتين',analyst=Fake())
    assert result['abstention_reason']=='model_or_grounding_validation_failed'
    assert result['analysis']['primary_pattern']=='insufficient_evidence'


def test_model_rule_text_replaced_by_canonical(store):
    store.add(record('RUL-test','rule'));approve(store,'RUL-test')
    class Fake:
        def analyze(self,*_):return Analysis(primary_pattern='جمع بين مختلفين',methodology_rule_ids=['RUL-test'],methodology_rule_ar='fabricated text',requires_human_review=False).model_dump()
    result=diagnose(store,'تفاحتين',analyst=Fake())
    assert result['analysis']['methodology_rule_ar']=='افحص الفارق المؤثر'
    assert result['requires_human_review'] is True
    assert result['source_evidence'][0]['source']['page_number']==1


def test_invented_objection_cannot_be_approved(store):
    store.add(record())
    with pytest.raises(ValueError):approve(store,'SHB-test',objection_text_ar='نص غير موجود في المصدر')


def test_machine_proposal_cannot_edit_approved_case(store):
    store.add(record());approve(store,'SHB-test')
    assert not store.add_machine_proposal('SHB-test',{'central_claim_ar':'تغيير آلي'},'test')
    assert store.get('SHB-test')['version']==2


def test_retrieval_outage_abstains(store):
    import httpx
    class Unavailable:
        def search(self,*args,**kwargs):raise httpx.ConnectError('offline')
    assert diagnose(store,'مثال',retriever=Unavailable())['abstention_reason']=='retrieval_unavailable'
