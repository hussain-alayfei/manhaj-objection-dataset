import pytest
from sqlalchemy import insert

from src.db import Store, sources, chunks
from src.models import Record, ReviewRequest


CHUNK_TEXT = 'اختبار مقارنة تفاحتين مختلفتين في الوزن. افحص الفارق المؤثر.'
PROVIDER_ENV = ('OPENAI_API_KEY', 'LLM_PROVIDER', 'DIAGNOSIS_MODEL', 'DIAGNOSIS_REASONING_EFFORT', 'EXTRACTOR_MODEL', 'EMBEDDING_PROVIDER', 'EMBEDDING_MODEL', 'EMBEDDING_DIM',
                'STORAGE_BACKEND', 'SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'READ_ONLY', 'VERCEL', 'VERCEL_URL', 'VERCEL_PROJECT_PRODUCTION_URL', 'VERCEL_BRANCH_URL',
                'ALLOWED_ORIGINS', 'DIAGNOSE_DAILY_LIMIT', 'ENABLE_HEAVY_ENDPOINTS', 'ALLOW_SQLITE_SMOKE', 'DATABASE_URL', 'REVIEWER_TOKEN_HASHES',
                'CRITIC_MODEL', 'DIAGNOSIS_MAX_OUTPUT_TOKENS', 'DIAGNOSIS_TIMEOUT', 'SOURCE_CHECK_TIMEOUT')


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    """Tests never inherit provider, hosting, or database settings from a developer's .env."""
    for name in PROVIDER_ENV: monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def offline_source_checks(monkeypatch):
    """Verse and hadith checks never reach the network in tests; tests of the checks bring their own transport."""
    import httpx
    from src.classification import sources as text_sources
    text_sources._get_json.cache_clear()
    monkeypatch.setattr(text_sources, '_client', httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503))))
    yield
    text_sources._get_json.cache_clear()


@pytest.fixture
def store():
    store = Store('sqlite:///:memory:')
    with store.transaction() as c:
        source = {'id':'SRC-test','source_type':'book','source_name':'وثيقة اختبار اصطناعية غير دينية','author':'test','sha256':'test','page_count':1}
        c.execute(insert(sources).values(id=source['id'],sha256='test',payload=source))
        c.execute(insert(chunks).values(id='CH-1',source_id='SRC-test',page_number=1,section='اختبار',text=CHUNK_TEXT,raw_text=CHUNK_TEXT,payload={}))
    store.register_reviewer('expert')
    return store


def record(rid='SHB-test', kind='objection', **changes):
    text='اختبار مقارنة تفاحتين مختلفتين في الوزن.'
    # A rule quotes the author's own wording, so its cited excerpt covers the whole chunk.
    quoted=CHUNK_TEXT if kind=='rule' else text
    citation={'source_id':'SRC-test','source_name':'وثيقة اختبار اصطناعية غير دينية','author':'test','page_number':1,'source_excerpt':quoted,'spans':[{'chunk_id':'CH-1','page_number':1,'start':0,'end':len(quoted),'text':quoted}]}
    r=Record(id=rid,kind=kind,title_ar='مثال اصطناعي للاختبار',objection_text_ar=text,source=citation,central_claim_ar='الفاكهتان متماثلتان في الوزن',primary_pattern='unknown',diagnostic_reason_ar='المعيار غير محدد',revealing_question_ar='ما الوزن؟',treatment_ar='قارن الوزن',methodology_rule_ar='افحص الفارق المؤثر',source_evidence={'original':'immutable'},ai_analysis={'original':'immutable'}).model_dump()
    r.update(changes)
    return r


def approve(store, rid, **changes):
    return store.review(rid,ReviewRequest(expected_version=store.get(rid)['version'],action='approve',changes=changes,source_verified=True,page_verified=True,diagnosis_verified=True), 'expert')


def method_data(rule_id='RUL-test', **steps):
    """The eleven steps for the seventy-autumns example, as the analyst returns them."""
    def text(quote, collection, number, source, grade):
        return {'kind': 'حديث', 'quote': quote, 'surah': 0, 'ayah': 0, 'collection': collection, 'number': number, 'source_ar': source, 'grade_ar': grade, 'status': 'ثابت'}
    data = {
        'step1_framing': {'claim': 'الحديثان متعارضان', 'evidence': ['«سبعين خريفًا»', '«مائة عام»'], 'conclusion': 'في النصوص تناقض',
                          'premises': ['العددان مختلفان'], 'hidden_assumption': 'العددان يُقارنان حسابيًا'},
        'step2_entities': {'verses': [], 'hadiths': ['حديثان'], 'key_words': ['خريف', 'في سبيل الله'], 'numbers': ['70', '100'], 'persons': ['الرواة والصحابة'],
                           'events': [], 'rulings': ['فضل الصيام'], 'terms': ['الخريف = العام'], 'claims': []},
        'step3_sources': {'texts': [text('من صام يوما في سبيل الله بعد الله وجهه عن النار سبعين خريفا', 'bukhari', 2840, 'رواه البخاري ومسلم', 'صحيح'),
                                    text('باعد الله منه جهنم مسيرة مائة عام', 'nasai', 2254, 'رواه النسائي', 'حسن')],
                          'variants': 'رواية «سبعين خريفًا» في الصحيحين، ورواية «مائة عام» عند النسائي.'},
        'step4_related': {'issue': 'فضل الصيام في سبيل الله', 'other_texts': [], 'narrations': ['اختلفت الروايات في العدد'], 'scholars': ['حمل أهل العلم العدد على التكثير'],
                          'language': ['الخريف يُطلق على العام'], 'usul': ['مفهوم العدد لا يُعمل به إذا عارضه ما هو أقوى'], 'context': []},
        'step5_language': {'findings': [{'dimension': 'دلالات الأعداد', 'finding': 'العدد هنا لا يُراد به الحصر'}, {'dimension': 'التكثير والمبالغة', 'finding': 'السبعون والمائة تُذكر للتكثير'}]},
        'step6_comparison': {'side_a': '«سبعين خريفًا»', 'side_b': '«مائة عام»', 'same_thing': {'answer': 'نعم', 'why': 'كلاهما في فضل صوم يوم في سبيل الله'},
                             'same_aspect': {'answer': 'محتمل', 'why': 'قد يختلف باختلاف الصائم'}, 'same_meaning': {'answer': 'لا', 'why': 'العدد للتكثير لا للحساب'},
                             'checks': [{'check': 'حصر أم تكثير', 'finding': 'العددان للتكثير'}], 'conclusion': 'لا تعارض بين الحديثين'},
        'governing_rules': {'primary_pattern': 'جمع بين مختلفين', 'sub_patterns': ['اختلاف المعنى'], 'fault': 'جمعٌ بين مختلفين',
                            'explanation': 'سوّى بين عدد قد يُراد به التكثير وعدد آخر، ثم قارنهما حسابيًا.', 'methodology_rule_ids': [rule_id]},
        'step7_hypotheses': [{'id': 'H1', 'title': 'المشكلة لغوية', 'basis': 'دلالة العدد'}, {'id': 'H2', 'title': 'المشكلة حديثية', 'basis': 'اختلاف الروايات'},
                             {'id': 'H3', 'title': 'جمع بين مختلفين', 'basis': 'قورن العددان حسابيًا'}],
        'step8_tests': [{'id': 'H1', 'verdict': 'مدعوم بالدليل', 'evidence': 'كلام أهل اللغة'}, {'id': 'H2', 'verdict': 'مرفوض', 'evidence': 'الروايتان ثابتتان'},
                        {'id': 'H3', 'verdict': 'مدعوم بالدليل', 'evidence': 'العدد للتكثير'}],
        'step9_map': {'objection': 'تعارض العددين', 'hidden_assumption': 'المقارنة الحسابية', 'fault': 'جمع بين مختلفين', 'evidence': 'دلالة العدد على التكثير',
                      'rule': 'الشريعة لا تجمع بين المختلفات', 'resolution': 'العددان للتكثير فلا تعارض', 'conclusion': 'لا تناقض'},
        'step11_answer': {'summary': 'تعارضٌ ظاهري بين «سبعين خريفًا» و«مائة عام»', 'origin': 'مقارنة حسابية بين عدد يُراد به التكثير وعدد آخر',
                          'dismantling': [{'step': 'تحرير الدعوى', 'evidence': 'لفظ الحديثين'}, {'step': 'ثبوت الروايتين', 'evidence': 'البخاري والنسائي'},
                                          {'step': 'دلالة العدد على التكثير', 'evidence': 'كلام أهل اللغة'}],
                          'sources': ['صحيح البخاري', 'سنن النسائي'], 'disagreement': '', 'revealing_question': 'هل يلزم من ذكر عددين للتكثير أن يكون أحدهما خطأ؟',
                          'confidence': 0.7, 'confidence_label': 'توجيه معتبر غير قطعي'},
    }
    for key, changes in steps.items(): data[key] = dict(data[key], **changes) if isinstance(data[key], dict) else changes
    return data
