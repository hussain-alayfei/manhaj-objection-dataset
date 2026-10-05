"""Step 3, checked for real: verses against the Mushaf, hadiths against their books, with nothing but numbers sent out."""
import httpx
import pytest

from src.classification import sources

AYAH_6_103 = {'data': [
    {'text': 'لا تدركه الأبصار وهو يدرك الأبصار ۖ وهو اللطيف الخبير', 'numberInSurah': 103, 'surah': {'number': 6, 'name': 'سُورَةُ الأَنۡعَامِ'}},
    {'text': 'لَّا تُدْرِكُهُ ٱلْأَبْصَٰرُ وَهُوَ يُدْرِكُ ٱلْأَبْصَٰرَ', 'numberInSurah': 103, 'surah': {'number': 6, 'name': 'سُورَةُ الأَنۡعَامِ'}}]}
AYAH_6_104 = {'data': [
    {'text': 'قد جاءكم بصائر من ربكم', 'numberInSurah': 104, 'surah': {'number': 6, 'name': 'سُورَةُ الأَنۡعَامِ'}},
    {'text': 'قَدْ جَآءَكُم بَصَآئِرُ مِن رَّبِّكُمْ', 'numberInSurah': 104, 'surah': {'number': 6, 'name': 'سُورَةُ الأَنۡعَامِ'}}]}
SEARCH = {'data': {'count': 2, 'matches': [
    {'text': 'قد كان لكم آية في فئتين التقتا', 'numberInSurah': 13, 'surah': {'number': 3}},
    {'text': 'لا تدركه الأبصار وهو يدرك الأبصار ۖ وهو اللطيف الخبير', 'numberInSurah': 103, 'surah': {'number': 6}}]}}
NASAI = {'hadiths': [{'hadithnumber': 2254, 'arabicnumber': 2254, 'text': 'عن ابي سعيد قال قال رسول الله من صام يوما في سبيل الله باعد الله منه جهنم مسيرة مائة عام',
                      'grades': [{'name': 'Zubair Ali Zai', 'grade': 'Isnaad Hasan'}, {'name': 'Al-Albani', 'grade': 'Hasan'}, {'name': 'Abu Ghuddah', 'grade': 'Hasan'}]}]}
BUKHARI = {'hadiths': [{'hadithnumber': 2840, 'arabicnumber': 2840, 'grades': [],
                        'text': 'سمعت النبي صلى الله عليه وسلم يقول من صام يوما في سبيل الله بعد الله وجهه عن النار سبعين خريفا'}]}
MUSLIM_BOOK_13 = {'hadiths': [{'hadithnumber': 2700, 'arabicnumber': 1153.01, 'text': 'ما من عبد يصوم يوما في سبيل الله الا باعد الله بذلك اليوم وجهه عن النار سبعين خريفا'},
                              {'hadithnumber': 2701, 'arabicnumber': 1153.02, 'text': 'رواية اخرى بالاسناد نفسه'}]}


def serve(routes):
    seen = []

    def handler(request):
        url = str(request.url)
        seen.append(url)
        for part, (status, body) in routes.items():
            if part in url: return httpx.Response(status, json=body)
        return httpx.Response(404, json={})
    return httpx.Client(transport=httpx.MockTransport(handler)), seen


@pytest.fixture
def web(monkeypatch):
    def use(routes):
        client, seen = serve(routes)
        monkeypatch.setattr(sources, '_client', client)
        sources._get_json.cache_clear()
        return seen
    return use


def verse(quote, surah, ayah): return {'kind': 'آية', 'quote': quote, 'surah': surah, 'ayah': ayah, 'collection': 'none', 'number': 0}
def hadith(quote, collection, number): return {'kind': 'حديث', 'quote': quote, 'surah': 0, 'ayah': 0, 'collection': collection, 'number': number}


def test_a_verse_is_matched_against_the_mushaf(web):
    web({'/ayah/6:103/': (200, AYAH_6_103)})
    out = sources.check_text(verse('لا تُدرِكُهُ الأبصارُ', 6, 103))
    assert out['state'] == 'verified' and out['reference'] == 'سورة الأنعام، الآية 103'
    assert out['mushaf_text'].startswith('لَّا تُدْرِكُهُ') and out['url'] == 'https://quran.com/6/103' and out['corrected'] is False


def test_a_wrong_reference_is_found_by_searching_the_mushaf(web):
    seen = web({'/ayah/6:104/': (200, AYAH_6_104), '/search/': (200, SEARCH), '/ayah/6:103/': (200, AYAH_6_103)})
    out = sources.check_text(verse('لا تدركه الأبصار وهو يدرك الأبصار', 6, 104))
    assert out['state'] == 'verified' and (out['surah'], out['ayah']) == (6, 103) and out['corrected'] is True
    searched = [u for u in seen if '/search/' in u]
    assert len(searched) == 1 and 'quran-simple-clean' in searched[0]  # one word of the verse, nothing else


def test_words_not_in_the_mushaf_are_flagged(web):
    web({'/ayah/6:103/': (200, AYAH_6_103), '/search/': (200, {'data': {'count': 0, 'matches': []}})})
    assert sources.check_text(verse('كلام ليس من القرآن أبدا', 6, 103))['state'] == 'mismatch'


def test_a_hadith_is_found_in_its_book_with_grades_in_arabic(web):
    web({'ara-nasai1/2254.json': (200, NASAI)})
    out = sources.check_text(hadith('باعد الله منه جهنم مسيرة مائة عام', 'nasai', 2254))
    assert out['state'] == 'verified' and out['reference'] == 'سنن النسائي (2254)' and out['url'] == 'https://sunnah.com/nasai:2254'
    assert out['grades'] == [{'by': 'الألباني', 'grade': 'حسن'}, {'by': 'عبد الفتاح أبو غدة', 'grade': 'حسن'}]


def test_the_two_sahihs_need_no_later_grading(web):
    web({'ara-bukhari1/2840.json': (200, BUKHARI)})
    out = sources.check_text(hadith('من صام يومًا في سبيل الله بعّد الله وجهه عن النار سبعين خريفًا', 'bukhari', 2840))
    assert out['state'] == 'verified' and out['grades'] == [{'by': '', 'grade': 'صحيح، أخرجه البخاري في صحيحه'}]


def test_muslim_is_cited_by_abd_al_baqi_numbers(web):
    seen = web({'ara-muslim1/sections/13.json': (200, MUSLIM_BOOK_13)})
    out = sources.check_text(hadith('باعد الله بذلك اليوم وجهه عن النار سبعين خريفا', 'muslim', 1153))
    assert out['state'] == 'verified' and out['reference'] == 'صحيح مسلم (1153)' and 'url' not in out
    assert seen == ['https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/ara-muslim1/sections/13.json']


def test_a_mirror_outage_falls_back_to_github(web):
    seen = web({'cdn.jsdelivr.net': (503, {}), 'raw.githubusercontent.com/fawazahmed0/hadith-api/1/editions/ara-nasai1/2254.json': (200, NASAI)})
    assert sources.check_text(hadith('مسيرة مائة عام', 'nasai', 2254))['state'] == 'verified' and len(seen) == 2


@pytest.mark.parametrize('ref,routes,state', [
    (hadith('سبعين خريفا', 'nasai', 2254), {'ara-nasai1/2254.json': (200, {'hadiths': [{'text': 'حديث آخر في الطهارة', 'grades': []}]})}, 'mismatch'),
    (hadith('سبعين خريفا', 'nasai', 99999), {}, 'mismatch'),  # no such number on either mirror
    (hadith('سبعين خريفا', 'none', 0), {}, 'unchecked'),
    (hadith('سبعين خريفا', 'tirmidhi', 1624), {'ara-tirmidhi1': (503, {})}, 'unavailable'),
    ({'kind': 'قول عالم', 'quote': 'قول', 'surah': 0, 'ayah': 0, 'collection': 'none', 'number': 0}, {}, 'unchecked'),
])
def test_what_cannot_be_confirmed_is_never_shown_as_confirmed(web, ref, routes, state):
    web(routes)
    assert sources.check_text(ref)['state'] == state


def test_several_texts_keep_their_order(web):
    web({'ara-nasai1/2254.json': (200, NASAI), 'ara-bukhari1/2840.json': (200, BUKHARI)})
    out = sources.check_texts([hadith('سبعين خريفا', 'bukhari', 2840), hadith('مسيرة مائة عام', 'nasai', 2254), hadith('x', 'none', 0)])
    assert [o['state'] for o in out] == ['verified', 'verified', 'unchecked'] and sources.check_texts([]) == []


@pytest.mark.parametrize('english,arabic', [('Sahih - Agreed Upon', 'صحيح متفق عليه'), ('Isnaad Hasan', 'إسناده حسن'), ('Hasan Sahih', 'حسن صحيح'),
                                            ('Very Daif', 'ضعيف جدًا'), ('Sahih Lighairihi', 'صحيح لغيره'), ('Daif Isnaad', 'ضعيف الإسناد'),
                                            ('Sahih Bukhari (1023) Sahih Muslim (894)', 'صحيح البخاري (1023)، وصحيح مسلم (894)'), ('-', ''), ('Odd wording', '')])
def test_grades_read_in_arabic(english, arabic):
    assert sources.grade_ar(english) == arabic


def test_matching_ignores_diacritics_and_attached_particles():
    assert sources.coverage('وَهُوَ يُدْرِكُ ٱلْأَبْصَٰرَ', 'وهو يدرك الأبصار') == 1.0
    assert sources.coverage('بالأبصار', 'لا تدركه الأبصار') == 1.0
    assert sources.coverage('سبعين خريفًا', 'مسيرة مائة عام') == 0.0
