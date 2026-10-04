from src.duplicate_detection import detect_duplicates
from src.family_detection import create_families
from src.retrieval import build_embeddings, HybridRetriever
from src.models import ReviewRequest
from conftest import record, approve


class Encoder:
    model='test-semantic-model'
    def encode(self,texts):return [[1.,0.,0.] for _ in texts]


def test_exact_duplicate_is_distinct_from_pattern(store):
    store.add(record('A'));store.add(record('B'))
    store.add(record('C',objection_text_ar='نص مختلف تماما',primary_pattern='جمع بين مختلفين'))
    run=detect_duplicates(store)
    assert run['suggestions']['A']['similarity_type']=='exact_duplicate'
    assert run['suggestions']['A']['duplicate_group_id']==run['suggestions']['B']['duplicate_group_id']
    assert run['suggestions']['C']['duplicate_group_id'] is None
    assert store.get('A')['duplicate_group_id'] is None


def test_semantic_paraphrase_candidate(store):
    store.add(record('A'));store.add(record('B',objection_text_ar='هل الفاكهتان لهما كتلة واحدة؟'))
    run=detect_duplicates(store,Encoder())
    assert run['pairs'][0]['similarity_type']=='paraphrase'
    assert run['pairs'][0]['review_status']=='needs_review'


def test_new_family_for_low_similarity(store):
    store.add(record('A'));store.add(record('B',objection_text_ar='حالة جديدة بلا تشابه'))
    ids=create_families(store,detect_duplicates(store))
    assert len(ids)==2
    assert all(store.get(x)['review_status']=='needs_review' for x in ids)


def test_hybrid_search_filters_and_stale_embeddings(store):
    store.add(record('A'));approve(store,'A');store.add(record('B'))
    assert build_embeddings(store,Encoder())>0
    retriever=HybridRetriever(store,Encoder())
    result=retriever.search('تفاحتين')
    assert result['mode']=='hybrid'
    assert [x['record']['id'] for x in result['results']]==['A']
    assert retriever.search('تفاحتين',filters={'phase':2})['results']==[]
    assert retriever.search('تفاحتين',exclude_ids=['A'])['results']==[]
    store.review('A',ReviewRequest(expected_version=2,action='edit',changes={'central_claim_ar':'تغيير'}),'expert')
    approve(store,'A')
    assert retriever.search('تفاحتين')['mode']=='lexical_only_no_current_vectors'
