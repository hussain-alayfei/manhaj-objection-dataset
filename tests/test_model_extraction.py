from src.parsing.model_extraction import ExtractionBatch, ExtractedItem, extract_with_model


def test_source_model_cannot_invent_quote(store):
    class Extractor:
        model='test-only'
        def extract(self,text):return ExtractionBatch(items=[ExtractedItem(item_type='objection_example',title_ar='غير مدعوم',exact_quote='اقتباس مختلق لا يوجد في المصدر')])
    run=extract_with_model(store,'SRC-test',Extractor())
    assert not run['candidate_ids']
    assert run['errors'][0]['reason']=='quote_absent_or_ambiguous'
    assert not store.records()


def test_all_six_source_item_types_are_traceable_and_unapproved(store):
    class Extractor:
        model='test-only'
        def extract(self,text):return ExtractionBatch(items=[ExtractedItem(item_type=k,title_ar=k,exact_quote='اختبار مقارنة تفاحتين مختلفتين في الوزن.') for k in ['methodology_rule','objection_example','comparison','reasoning_pattern','diagnostic_question','response_methodology']])
    run=extract_with_model(store,'SRC-test',Extractor())
    assert len(run['source_item_ids'])==6
    assert len(run['candidate_ids'])==2
    assert all(r['review_status']=='needs_review' for r in store.records())
    assert all(r['source']['spans'][0]['start']==0 for r in store.records())
    repeat=extract_with_model(store,'SRC-test',Extractor())
    assert len(store.records())==2
    assert len(store.list_documents('source_items'))==6
