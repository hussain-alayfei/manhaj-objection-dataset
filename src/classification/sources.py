"""Step 3 of the method, done for real: every quoted verse and hadith is checked against a published text.

Verses are matched against the Mushaf (alquran.cloud); hadiths against the six books and the Muwatta
(the open hadith-api dataset, served by jsDelivr with GitHub as a fallback). Only a surah/ayah or a
collection/number leaves the server, plus a single word when a verse has to be searched for; never the
objection itself. Any failure degrades to "not checked automatically" and never fails the analysis.
"""
import concurrent.futures
import functools
import logging
import os
import re

import httpx

from ..parsing import normalize_arabic

log = logging.getLogger('manhaj.sources')
QURAN_API = 'https://api.alquran.cloud/v1'
HADITH_MIRRORS = ('https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1', 'https://raw.githubusercontent.com/fawazahmed0/hadith-api/1')
COLLECTIONS = {'bukhari': 'صحيح البخاري', 'muslim': 'صحيح مسلم', 'abudawud': 'سنن أبي داود', 'tirmidhi': 'جامع الترمذي',
               'nasai': 'سنن النسائي', 'ibnmajah': 'سنن ابن ماجه', 'malik': 'موطأ مالك'}
SAHIHAYN = ('bukhari', 'muslim')
# Sahih Muslim is cited by Muhammad Fuad Abd al-Baqi's numbers, while the dataset numbers it in sequence.
# Each of its 57 books with its first and last Abd al-Baqi number lets us open the right book and find the hadith.
MUSLIM_BOOKS = ((0, 1, 7), (1, 8.01, 222.02), (2, 223, 292.02), (3, 293.01, 376.04), (4, 377, 519.02), (5, 520.01, 684.04), (6, 685.01, 843.02),
                (7, 844.01, 883.02), (8, 884.01, 893), (9, 894.01, 900.02), (10, 901.01, 915), (11, 916.01, 978), (12, 979.01, 1078.02),
                (13, 1079.01, 1170), (14, 1171.01, 1176.02), (15, 1177.01, 1399.09), (16, 1400.01, 1443), (17, 1444.01, 1470.02),
                (18, 1471.01, 1491), (19, 1492.01, 1500.04), (20, 1501.01, 1510.02), (21, 1511.01, 1550.05), (22, 1551.01, 1613),
                (23, 1614, 1619.06), (24, 1620.01, 1626.02), (25, 1627.01, 1637.03), (26, 1638.01, 1645), (27, 1646.01, 1668.03),
                (28, 1669.01, 1683), (29, 1684.01, 1710.05), (30, 1711.01, 1721), (31, 1722.01, 1729), (32, 1730.01, 1817),
                (33, 1818.01, 1928.02), (34, 1929.01, 1959), (35, 1960.01, 1978.03), (36, 1979.02, 2064.04), (37, 2065.01, 2130.02),
                (38, 2131, 2159.02), (39, 2160, 2245.02), (40, 2246.01, 2254), (41, 2255.03, 2260), (42, 2261.01, 2275), (43, 2276, 2380.06),
                (44, 2381, 2547), (45, 2548.01, 2642.02), (46, 2643.01, 2664), (47, 2665, 2674), (48, 2675.01, 2735.03), (49, 2736, 2743.03),
                (50, 2744.01, 2771), (51, 2772, 2784.02), (52, 2785, 2821.03), (53, 2822, 2879), (54, 2880.01, 2955.03), (55, 2956, 3014),
                (56, 3015, 3033.02))
GRADERS = {'Al-Albani': 'الألباني', 'Shuaib Al Arnaut': 'شعيب الأرناؤوط', 'Ahmad Muhammad Shakir': 'أحمد شاكر', 'Bashar Awad Maarouf': 'بشار عواد معروف',
           'Abu Ghuddah': 'عبد الفتاح أبو غدة', 'Muhammad Muhyi Al-Din Abdul Hamid': 'محمد محيي الدين عبد الحميد',
           'Muhammad Fouad Abd al-Baqi': 'محمد فؤاد عبد الباقي', 'Salim al-Hilali': 'سليم الهلالي', 'Zubair Ali Zai': 'زبير علي زئي'}
GRADE_WORDS = {'Sahih': 'صحيح', 'Hasan': 'حسن', 'Daif': 'ضعيف'}
GRADE_PHRASES = ((r'\bSahih Bukhari\b', 'صحيح البخاري'), (r'\bSahih Muslim\b', 'صحيح مسلم'), (r'\bBukhari And Muslim\b', 'البخاري ومسلم'),
                 (r'\bAgreed Upon\b', 'متفق عليه'), (r'\bVery Daif\b', 'ضعيف جدًا'), (r'\bHasan Sahih\b', 'حسن صحيح'),
                 (r'\b(?:Isnaad|Isnad|Sanad)\s+(Sahih|Hasan|Daif)\b', lambda m: 'إسناده ' + GRADE_WORDS[m.group(1)]),
                 (r'\b(Sahih|Hasan|Daif)\s+(?:Isnaad|Isnad|Sanad)\b', lambda m: GRADE_WORDS[m.group(1)] + ' الإسناد'),
                 (r'\bSahih\b', 'صحيح'), (r'\bHasan\b', 'حسن'), (r'\bDaif\b', 'ضعيف'), (r'\bLighairihi\b', 'لغيره'),
                 (r'\b(?:Mauquf|Muquf|Mawquf)\b', 'موقوف'), (r'\bMaqtu\b', 'مقطوع'), (r'\bMursal\b', 'مرسل'), (r'\bShadh\b', 'شاذ'),
                 (r'\bMunkar\b', 'منكر'), (r'\bMawdu\b', 'موضوع'), (r'\bBatil\b', 'باطل'), (r'\bMutawatir\b', 'متواتر'),
                 (r'\bMatn\b', 'المتن'), (r'\bHadith\b', ''))
PREFIXES = ('و', 'ف', 'ب', 'ل', 'ك')


def _span(first, last): return f'{chr(first)}-{chr(last)}'


ARABIC_WORD = re.compile(f'[{_span(0x621, 0x64A)}]+')


def grade_ar(text):
    """The dataset's English grading in Arabic; unknown wording is dropped rather than guessed."""
    t = re.sub(r'\s*-\s*', ' ', (text or '').strip())
    if not t: return ''
    for pattern, repl in GRADE_PHRASES: t = re.sub(pattern, repl, t)
    t = re.sub(r'\)\s+(?=صحيح)', ')، و', t)
    t = re.sub(r'\s{2,}', ' ', t).strip()
    return '' if re.search('[A-Za-z]', t) else t


def tokens(text):
    t = normalize_arabic(text or '').translate(str.maketrans({'ة': 'ه', 'ؤ': 'و', 'ئ': 'ي', 'ء': ''}))
    return [w for w in ARABIC_WORD.findall(t) if len(w) > 1]


def _forms(word):
    """A word without its alefs (the Uthmani and plain spellings differ in them), with and without
    the article and an attached particle, so «بالأبصار» and «ٱلْأَبْصَٰر» both meet «الأبصار»."""
    w = word.replace('ا', '')
    forms = {w}
    if w[:1] in PREFIXES and len(w) > 3: forms.add(w[1:])
    forms |= {f[1:] for f in forms if f.startswith('ل') and len(f) > 3}
    return forms


def coverage(quote, text):
    """Share of the quote's words found in the text (a quote is usually a fragment of it)."""
    q = tokens(quote)
    if not q: return 0.0
    words = set().union(*(_forms(w) for w in tokens(text)))
    return sum(bool(_forms(w) & words) for w in q) / len(q)


@functools.lru_cache(maxsize=128)
def _get_json(url):
    response = _http().get(url)
    response.raise_for_status()
    return response.json()


_client = None


def _http():
    global _client
    if _client is None:
        _client = httpx.Client(timeout=float(os.getenv('SOURCE_CHECK_TIMEOUT', '6')), follow_redirects=True, headers={'User-Agent': 'manhaj-source-check'})
    return _client


def _hadith_json(path):
    error = None
    for base in HADITH_MIRRORS:
        try: return _get_json(f'{base}/{path}')
        except (httpx.HTTPError, ValueError) as e: error = e
    # every mirror answering "no such file" means there is no hadith with that number
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 404: return {'hadiths': []}
    raise error


DIACRITICS = re.compile(f'[{_span(0x610, 0x61A)}{_span(0x64B, 0x65F)}{chr(0x670)}{_span(0x6D6, 0x6ED)}]')


def _ayah(surah, ayah):
    data = _get_json(f'{QURAN_API}/ayah/{surah}:{ayah}/editions/quran-simple-clean,quran-uthmani')['data']
    return data[0]['surah']['number'], data[0]['numberInSurah'], data[0]['text'], data[1]['text'], DIACRITICS.sub('', data[0]['surah']['name'])


def check_verse(ref):
    quote, surah, ayah = ref.get('quote', ''), int(ref.get('surah') or 0), int(ref.get('ayah') or 0)
    best = None
    if 1 <= surah <= 114 and ayah >= 1:
        try: best = _ayah(surah, ayah)
        except httpx.HTTPStatusError: best = None  # no such ayah: search for the words instead
    if best is None or coverage(quote, best[2]) < 0.8:
        # the reference was missing or wrong: search the Mushaf by the quote's longest word
        word = max(tokens(quote), key=len, default='')
        if len(word) >= 3:
            try: matches = _get_json(f'{QURAN_API}/search/{word}/all/quran-simple-clean')['data']['matches']
            except (httpx.HTTPError, ValueError, KeyError, TypeError): matches = []
            found = max(matches[:40], key=lambda m: coverage(quote, m['text']), default=None)
            if found and coverage(quote, found['text']) >= 0.8: best = _ayah(found['surah']['number'], found['numberInSurah'])
    if best is None or coverage(quote, best[2]) < 0.8:
        return {'state': 'mismatch', 'label': 'لم يطابق نص المصحف', 'detail': 'لم يُعثر على هذا اللفظ في المصحف بالموضع المذكور؛ يحتاج تحققًا.'}
    s, a, _, uthmani, name = best
    moved = (s, a) != (surah, ayah)
    return {'state': 'verified', 'label': 'مطابق للمصحف', 'reference': f'{name}، الآية {a}', 'surah': s, 'ayah': a,
            'mushaf_text': uthmani, 'corrected': moved and bool(surah), 'url': f'https://quran.com/{s}/{a}'}


def _muslim_entries(number):
    book = next((b for b, first, last in MUSLIM_BOOKS if int(first) <= number <= int(last)), None)
    if book is None: return []
    data = _hadith_json(f'editions/ara-muslim1/sections/{book}.json')
    return [h for h in data.get('hadiths', []) if int(float(h.get('arabicnumber') or 0)) == number]


def check_hadith(ref):
    collection, number, quote = ref.get('collection'), int(ref.get('number') or 0), ref.get('quote', '')
    if collection not in COLLECTIONS or number <= 0:
        from .library import find_hadith  # no number to check: look for the wording in the Shamela collections instead
        hit = find_hadith(quote)
        if hit:
            where = f"{hit['book']}، ج{hit['vol']} ص{hit['page']}" if hit['vol'] else f"{hit['book']}، ص{hit['page']}"
            return {'state': 'verified', 'label': 'وُجد في المكتبة الشاملة', 'reference': where, 'url': hit['url'], 'grades': []}
        return {'state': 'unchecked', 'label': 'لم يُتحقق آليًا', 'detail': 'لم يُذكر له كتاب ورقم، ولم يُعثر على لفظه في المكتبة الشاملة؛ يحتاج تخريجًا من المختص.'}
    entries = _muslim_entries(number) if collection == 'muslim' else _hadith_json(f'editions/ara-{collection}1/{number}.json').get('hadiths', [])
    best = max(entries, key=lambda h: coverage(quote, h.get('text', '')), default=None)
    name = COLLECTIONS[collection]
    if best is None or coverage(quote, best.get('text', '')) < 0.6:
        return {'state': 'mismatch', 'label': 'لم يطابق الرقم المذكور', 'detail': f'لم يُعثر على هذا اللفظ في {name} برقم {number}؛ يحتاج تخريجًا من المختص.'}
    order = list(GRADERS)
    grades = sorted((g for g in best.get('grades') or [] if g.get('name') in GRADERS and grade_ar(g.get('grade'))), key=lambda g: order.index(g['name']))
    result = {'state': 'verified', 'label': 'وُجد في مصدره', 'reference': f'{name} ({number})', 'collection': collection, 'number': number,
              'grades': [{'by': GRADERS[g['name']], 'grade': grade_ar(g['grade'])} for g in grades[:2]]}
    if collection in SAHIHAYN: result['grades'] = [{'by': '', 'grade': f"صحيح، أخرجه {'البخاري' if collection == 'bukhari' else 'مسلم'} في صحيحه"}]
    if collection != 'muslim': result['url'] = f'https://sunnah.com/{collection}:{number}'
    return result


def check_text(ref):
    try:
        if ref.get('kind') == 'آية': return check_verse(ref)
        if ref.get('kind') == 'حديث': return check_hadith(ref)
        return {'state': 'unchecked', 'label': 'لم يُتحقق آليًا', 'detail': 'التحقق الآلي للآيات والأحاديث وحدها؛ يُراجع هذا النقل من مصدره.'}
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
        log.warning('source check unavailable: %s', type(error).__name__)
        return {'state': 'unavailable', 'label': 'تعذّر التحقق الآن', 'detail': 'تعذّر الوصول إلى مصدر التحقق في هذه اللحظة.'}


def check_texts(refs, workers=6):
    """Check several texts at once; the results keep the order of ``refs``."""
    if not refs: return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(refs))) as pool:
        return list(pool.map(check_text, refs))
