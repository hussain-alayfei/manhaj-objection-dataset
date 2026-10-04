import pytest
from sqlalchemy import insert

from src.db import Store, sources, chunks
from src.models import Record, ReviewRequest


PROVIDER_ENV = ('OPENAI_API_KEY', 'LLM_PROVIDER', 'DIAGNOSIS_MODEL', 'DIAGNOSIS_REASONING_EFFORT', 'EXTRACTOR_MODEL', 'EMBEDDING_PROVIDER', 'EMBEDDING_MODEL', 'EMBEDDING_DIM',
                'STORAGE_BACKEND', 'SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'READ_ONLY', 'VERCEL', 'VERCEL_URL', 'VERCEL_PROJECT_PRODUCTION_URL', 'VERCEL_BRANCH_URL',
                'ALLOWED_ORIGINS', 'DIAGNOSE_DAILY_LIMIT', 'ENABLE_HEAVY_ENDPOINTS', 'ALLOW_SQLITE_SMOKE', 'DATABASE_URL', 'REVIEWER_TOKEN_HASHES')


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    """Tests never inherit provider, hosting, or database settings from a developer's .env."""
    for name in PROVIDER_ENV: monkeypatch.delenv(name, raising=False)


@pytest.fixture
def store():
    store = Store('sqlite:///:memory:')
    with store.transaction() as c:
        source = {'id':'SRC-test','source_type':'book','source_name':'وثيقة اختبار اصطناعية غير دينية','author':'test','sha256':'test','page_count':1}
        c.execute(insert(sources).values(id=source['id'],sha256='test',payload=source))
        c.execute(insert(chunks).values(id='CH-1',source_id='SRC-test',page_number=1,section='اختبار',text='اختبار مقارنة تفاحتين مختلفتين في الوزن. افحص الفارق المؤثر.',raw_text='اختبار مقارنة تفاحتين مختلفتين في الوزن. افحص الفارق المؤثر.',payload={}))
    store.register_reviewer('expert')
    return store


def record(rid='SHB-test', kind='objection', **changes):
    text='اختبار مقارنة تفاحتين مختلفتين في الوزن.'
    citation={'source_id':'SRC-test','source_name':'وثيقة اختبار اصطناعية غير دينية','author':'test','page_number':1,'source_excerpt':text,'spans':[{'chunk_id':'CH-1','page_number':1,'start':0,'end':len(text),'text':text}]}
    r=Record(id=rid,kind=kind,title_ar='مثال اصطناعي للاختبار',objection_text_ar=text,source=citation,central_claim_ar='الفاكهتان متماثلتان في الوزن',primary_pattern='unknown',diagnostic_reason_ar='المعيار غير محدد',revealing_question_ar='ما الوزن؟',treatment_ar='قارن الوزن',methodology_rule_ar='افحص الفارق المؤثر',source_evidence={'original':'immutable'},ai_analysis={'original':'immutable'}).model_dump()
    r.update(changes)
    return r


def approve(store, rid, **changes):
    return store.review(rid,ReviewRequest(expected_version=store.get(rid)['version'],action='approve',changes=changes,source_verified=True,page_verified=True,diagnosis_verified=True), 'expert')
