"""The Shamela library is read before the analysis is written; a deep search may look up a few trusted sites."""
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from src.classification import diagnose, library, sources
from src.classification.pipeline import WEB_DOMAINS, OpenAIAnalyst, _web_trail
from src.models import CriticReport, MethodProposal
from conftest import approve, method_data, record

SHARH = {'count': 1, 'data': [{'book_id': '148870', 'cat_id': '7', 'meta': json.dumps({'page_id': 12595, 'page': 383, 'vol': '21', 'book_name': 'البحر المحيط الثجاج', 'author_name': 'محمد آدم الإتيوبي'}, ensure_ascii=False),
                               'text': 'قوله: "<em>سبعين</em> <em>خريفًا</em>" ليس للتحديد، وإنما هو للتكثير بدليل روايته بلفظ: "مائة عام".', 'snip': ''}]}
HADITH = {'count': 1, 'data': [{'book_id': '1147', 'cat_id': '6', 'meta': json.dumps({'page_id': 488, 'page': 480, 'vol': '2', 'book_name': 'صحيح سنن النسائي', 'author_name': 'الألباني'}, ensure_ascii=False),
                                'text': 'مَنْ صَامَ يَوْمًا فِي سَبِيلِ اللهِ بَاعَدَ اللهُ مِنْهُ جَهَنَّمَ مَسِيرَةَ <em>مِائَةِ</em> <em>عَامٍ</em>', 'snip': ''}]}
LUGHA = {'count': 1, 'data': [{'book_id': '1687', 'cat_id': '30', 'meta': json.dumps({'page_id': 4370, 'page': 63, 'vol': '9', 'book_name': 'لسان العرب', 'author_name': 'ابن منظور'}, ensure_ascii=False),
                               'text': 'لَيْسَ <em>الخَرِيفُ</em> فِي الأَصل بِاسْمِ الْفَصْلِ', 'snip': ''}]}
BY_CAT = {'7': SHARH, '6': HADITH, '30': LUGHA}
QUESTION = 'كيف يقول ﷺ: «سبعين خريفًا»، وفي حديث آخر: «مائة عام»؟ أليس هذا تناقضًا؟'


@pytest.fixture
def turath(monkeypatch):
    asked = []

    def handler(request):
        query = parse_qs(urlsplit(str(request.url)).query)
        asked.append((query['q'][0], query.get('cat', [''])[0]))
        return httpx.Response(200, json=BY_CAT.get(query.get('cat', [''])[0], {'data': []}))
    monkeypatch.setattr(sources, '_client', httpx.Client(transport=httpx.MockTransport(handler)))
    sources._get_json.cache_clear()
    return asked


def test_quoted_words_and_lexicon_words_are_taken_from_the_question():
    assert library.quotes(QUESTION) == ['سبعين خريفًا', 'مائة عام']
    assert library.lexicon_words(['سبعين خريفًا', 'مائة عام']) == ['خريف', 'عام']  # numbers only when nothing else
    assert library.quotes('سؤال بلا علامات تنصيص') == []


def test_the_library_is_searched_in_commentaries_collections_and_lexicons(turath):
    found = library.gather(QUESTION)
    assert ('سبعين خريفًا مائة عام', '7') in turath  # both texts together, where the scholars reconcile them
    assert {cat for _, cat in turath} == {'6', '7', '30'}
    first = found['excerpts'][0]
    assert first['kind'] == 'sharh' and 'للتكثير' in first['text'] and '<em>' not in first['text']
    assert first['url'] == 'https://shamela.ws/book/148870/12595' and first['vol'] == '21' and first['page'] == 383
    assert [e['kind'] for e in found['excerpts']] == ['sharh', 'hadith', 'lugha']  # one page each: repeats are dropped
    assert library.for_analyst(found)[0]['source'] == 'البحر المحيط الثجاج، ج21 ص383'


def test_an_unreachable_library_gives_no_excerpts():
    assert library.gather(QUESTION)['excerpts'] == []  # the offline test transport answers 503


def test_a_hadith_without_a_number_is_found_in_the_shamela_collections(turath):
    out = sources.check_text({'kind': 'حديث', 'quote': 'من صام يوما في سبيل الله باعد الله منه جهنم مسيرة مائة عام', 'surah': 0, 'ayah': 0, 'collection': 'none', 'number': 0})
    assert out['state'] == 'verified' and out['label'] == 'وُجد في المكتبة الشاملة'
    assert out['reference'] == 'صحيح سنن النسائي، ج2 ص480' and out['url'] == 'https://shamela.ws/book/1147/488'


class Provider:
    def __init__(self): self.calls = []

    def parse(self, **request):
        self.calls.append(request)
        if request['text_format'] is CriticReport:
            checks = {k: {'ok': True, 'note': ''} for k in ('misunderstood', 'evidence_proves', 'contrary_text', 'unsourced_attribution', 'possibility_as_certainty', 'stronger_explanation')}
            return SimpleNamespace(output_parsed=CriticReport.model_validate({**checks, 'holds': True, 'revision': ''}))
        search = SimpleNamespace(type='web_search_call', action=SimpleNamespace(query='site:sunnah.com مائة عام'))
        cite = SimpleNamespace(type='url_citation', url='https://sunnah.com/nasai:2254', title='Sunan an-Nasa\'i 2254')
        message = SimpleNamespace(type='message', content=[SimpleNamespace(annotations=[cite])])
        return SimpleNamespace(output_parsed=MethodProposal.model_validate(method_data()), output=[search, message])


def analyst(monkeypatch, provider):
    monkeypatch.setenv('DIAGNOSIS_MODEL', 'gpt-test')
    a = OpenAIAnalyst(client=SimpleNamespace(responses=provider))
    a.streams = False
    return a


def test_the_analyst_and_the_critic_read_the_library(store, monkeypatch, turath):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    provider, events = Provider(), []
    out = diagnose(store, 'تفاحتين: ' + QUESTION, analyst=analyst(monkeypatch, provider), check_sources=lambda refs: [{'state': 'unchecked'} for _ in refs],
                   progress=lambda kind, **data: events.append(kind))
    analysis, critic = (json.loads(c['input'][1]['content']) for c in provider.calls)
    assert analysis['library_excerpts'][0]['source'] == 'البحر المحيط الثجاج، ج21 ص383' and 'للتكثير' in analysis['library_excerpts'][0]['text']
    assert critic['library_excerpts'] == analysis['library_excerpts']
    assert 'tools' not in provider.calls[0] and provider.calls[0]['prompt_cache_key'] == 'manhaj-method'
    assert events.index('library') < events.index('step') and out['library']['excerpts'][0]['book'] == 'البحر المحيط الثجاج'
    assert out['web_search'] is None and out['deep_search'] is False


def test_deep_search_is_limited_to_trusted_sites_and_keeps_its_trail(store, monkeypatch, turath):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    provider = Provider()
    out = diagnose(store, 'تفاحتين: ' + QUESTION, analyst=analyst(monkeypatch, provider), check_sources=lambda refs: [{'state': 'unchecked'} for _ in refs], deep_search=True)
    tools = provider.calls[0]['tools']
    assert tools == [{'type': 'web_search', 'filters': {'allowed_domains': WEB_DOMAINS}}] and 'shamela.ws' in WEB_DOMAINS
    assert 'بحث موسّع' in provider.calls[0]['input'][0]['content'] and 'tools' not in provider.calls[1]  # the critic does not search
    assert out['deep_search'] is True and out['web_search'] == {'queries': ['site:sunnah.com مائة عام'], 'sources': [{'url': 'https://sunnah.com/nasai:2254', 'title': "Sunan an-Nasa'i 2254"}]}


def test_web_trail_tolerates_responses_without_searches():
    assert _web_trail(SimpleNamespace(output=None)) == {'queries': [], 'sources': []}


def test_deep_search_counts_twice_against_the_daily_limit(store, monkeypatch):
    from fastapi.testclient import TestClient
    from src.api import create_app
    monkeypatch.setenv('DIAGNOSE_DAILY_LIMIT', '3')
    client = TestClient(create_app(store, {'expert': 'a' * 64}, hosted=False))
    token = client.post('/api/auth/signup', json={'name': 'باحث', 'email': 'reader@example.com', 'password': 'Quiet-River-73'}).json()['token']
    auth = {'Authorization': 'Bearer ' + token}
    assert client.post('/api/diagnose', headers=auth, json={'text': 'شبهة', 'deep_search': True}).status_code == 200
    assert client.post('/api/diagnose', headers=auth, json={'text': 'شبهة'}).status_code == 200
    assert client.post('/api/diagnose', headers=auth, json={'text': 'شبهة'}).status_code == 429


def test_deep_search_links_are_kept_out_of_the_text(store, monkeypatch, turath):
    store.add(record('RUL-test', 'rule')); approve(store, 'RUL-test')
    provider = Provider()
    linked = method_data(step11_answer={'origin': 'افتراض الحصر. ([islamweb.net](https://www.islamweb.net/ar/x))', 'sources': ['[فتح الباري](https://shamela.ws/book/1673/3242)']})
    original = provider.parse
    provider.parse = lambda **request: SimpleNamespace(output_parsed=MethodProposal.model_validate(linked), output=[]) if request['text_format'] is MethodProposal else original(**request)
    out = diagnose(store, 'تفاحتين: ' + QUESTION, analyst=analyst(monkeypatch, provider), check_sources=lambda refs: [{'state': 'unchecked'} for _ in refs], deep_search=True)
    answer = out['method']['steps']['step11_answer']
    assert answer['origin'] == 'افتراض الحصر.' and answer['sources'] == ['فتح الباري']
