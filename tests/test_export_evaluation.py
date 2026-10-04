import json
import pytest

from src.evaluation import create_benchmark,evaluate_predictions
from src.evaluation.benchmark import reviewer_agreement
from src.export import export_training
from src.models import ReviewRequest
from conftest import record,approve


def cases(store):
    for rid,word in [('A','اختبار'),('B','مقارنة'),('C','الوزن')]:
        store.add(record(rid,objection_text_ar=word));approve(store,rid)


def test_small_auto_split_rejected(store):
    cases(store)
    with pytest.raises(ValueError):create_benchmark(store,auto=True)


def test_only_approved_and_no_benchmark_leakage(store,tmp_path):
    cases(store);store.add(record('PENDING'))
    m=create_benchmark(store,['A'],['B'])
    out=tmp_path/'train.jsonl';result=export_training(store,m['id'],out)
    assert result['count']==1
    line=json.loads(out.read_text(encoding='utf-8'))
    assert line['messages'][1]['content']=='الوزن'
    assert isinstance(line['messages'][2]['content'],str)
    json.loads(line['messages'][2]['content'])


def test_family_transitive_split(store):
    cases(store)
    approve(store,'A',family_id='FAM-shared')
    approve(store,'B',family_id='FAM-shared',duplicate_group_id='GRP-shared')
    approve(store,'C',duplicate_group_id='GRP-shared')
    m=create_benchmark(store,['A'])
    assert set(m['test_ids'])=={'A','B','C'}
    assert m['training_ids']==[]


def test_old_test_never_returns_to_training(store,tmp_path):
    cases(store);create_benchmark(store,['A'])
    m=create_benchmark(store,['B'])
    assert 'A' not in m['training_ids']
    export_training(store,m['id'],tmp_path/'t.jsonl')
    with pytest.raises(ValueError):create_benchmark(store,['C'])


def test_changed_record_blocks_export(store,tmp_path):
    cases(store);m=create_benchmark(store,['A'],['B'])
    store.review('C',ReviewRequest(expected_version=2,action='reopen'),'expert')
    with pytest.raises(ValueError):export_training(store,m['id'],tmp_path/'t.jsonl')


def test_new_duplicate_link_blocks_export(store,tmp_path):
    cases(store);m=create_benchmark(store,['A'])
    store.save_document('duplicate_runs',{'pairs':[{'a':'A','b':'B','similarity_type':'same_underlying_objection'}]})
    result=export_training(store,m['id'],tmp_path/'t.jsonl')
    assert result['count']==1


def test_metrics_not_fabricated_when_unrated(store):
    cases(store);m=create_benchmark(store,['A'])
    r=evaluate_predictions(store,m['id'],{'A':{'primary_pattern':'unknown','sub_patterns':[],'requires_human_review':True}})
    assert r['metrics']['primary_pattern_accuracy']['value']==1
    assert r['metrics']['central_claim_accuracy']['value'] is None
    assert r['metrics']['unsupported_diagnosis_rate']['status']=='not_measured'
    assert len(r['metrics'])==9


def test_missing_prediction_counts_as_failure(store):
    cases(store);m=create_benchmark(store,['A'])
    r=evaluate_predictions(store,m['id'],{})
    assert r['metrics']['primary_pattern_accuracy']['value']==0


def test_agreement():
    r=reviewer_agreement({'a':'A','b':'B'},{'a':'A','b':'B'})
    assert r['cohen_kappa']==1


def test_withdrawn_holdout_still_blocks_new_family_member(store,tmp_path):
    cases(store);m=create_benchmark(store,['A'])
    store.review('A',ReviewRequest(expected_version=2,action='reject'),'expert')
    store.save_document('duplicate_runs',{'pairs':[{'a':'A','b':'B','similarity_type':'same_underlying_objection'}]})
    result=export_training(store,m['id'],tmp_path/'t.jsonl')
    assert result['count']==1
