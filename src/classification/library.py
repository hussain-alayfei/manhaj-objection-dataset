"""The Shamela library, read before the analysis is written.

The objection's quoted words are looked up (through the Turath API, which serves the Shamela books) in the
hadith collections, their commentaries and the Arabic lexicons, so the analyst reads the scholars' and the
lexicographers' own words with book, volume and page. Only the quoted words leave the server. Any failure
returns fewer excerpts or none; it never fails the analysis.
"""
import concurrent.futures
import html
import json
import logging
import re
from urllib.parse import urlencode

import httpx

from ..parsing import normalize_arabic
from . import sources

log = logging.getLogger('manhaj.library')
SEARCH = 'https://api.turath.io/search'
# Shamela categories: the hadith collections, their commentaries, the lexicons
KINDS = {'hadith': (6, 'متون الحديث'), 'sharh': (7, 'شروح الحديث'), 'lugha': (30, 'معاجم اللغة')}
LIMITS = {'sharh': 5, 'hadith': 4, 'lugha': 3}
NUMBERS = {'ثلاث', 'ثلاثه', 'سبع', 'سبعه', 'سبعين', 'سبعون', 'اربعين', 'اربعون', 'مائه', 'ميه', 'الف', 'الفا', 'عشر', 'عشره', 'عشرين', 'ستين', 'ثمانين'}
QUOTED = re.compile(r'[«“"﴿]([^»”"﴾]{2,120})[»”"﴾]')
WORD = re.compile(f'[{chr(0x621)}-{chr(0x64A)}]+')


def quotes(text):
    """The words the asker quotes (between quotation marks or Quranic brackets), at most three."""
    found = []
    for q in QUOTED.findall(text or ''):
        q = re.sub(r'\s+', ' ', q).strip(' .،,؛:')
        if 1 <= len(q.split()) <= 14 and q not in found: found.append(q)
    return found[:3]


def _plain_word(word):
    w = normalize_arabic(word)
    if w.startswith('ال') and len(w) > 4: w = w[2:]
    if w.endswith('ا') and len(w) > 4: w = w[:-1]  # the alef of the accusative ending: خريفا -> خريف
    return w


def lexicon_words(found):
    """For each quote, its most telling word to look up in the lexicons (numbers only when nothing else)."""
    words = []
    for q in found:
        plain = [_plain_word(w) for w in WORD.findall(normalize_arabic(q)) if len(w) > 2]
        if not plain: continue
        best = max([w for w in plain if w.replace('ة', 'ه') not in NUMBERS] or plain, key=len)
        if best not in words: words.append(best)
    return words[:2]


def _excerpt(item, kind, query):
    meta = json.loads(item.get('meta') or '{}')
    raw = item.get('text') or item.get('snip') or ''
    at = raw.find('<em>')
    window = raw[max(0, at - 260):at + 420] if at >= 0 else raw[:600]
    text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', window))).strip()
    if at > 260: text = '… ' + text
    if len(raw) > at + 420: text += ' …'
    book, page_id = item.get('book_id'), meta.get('page_id')
    return {'kind': kind, 'label': KINDS[kind][1], 'book': meta.get('book_name', ''), 'author': meta.get('author_name', ''),
            'vol': str(meta.get('vol') or ''), 'page': meta.get('page'), 'text': text, 'query': query, 'book_id': book, 'page_id': page_id,
            'url': f'https://shamela.ws/book/{book}/{page_id}' if book and page_id else None}


def _search(query, kind, limit):
    params = {'q': query, 'ver': 3, 'cat': KINDS[kind][0]}
    try:
        data = sources._get_json(f'{SEARCH}?{urlencode(params)}')
    except (httpx.HTTPError, ValueError) as error:
        log.warning('library search unavailable: %s', type(error).__name__)
        return []
    return [_excerpt(item, kind, query) for item in (data.get('data') or [])[:limit]]


def gather(objection):
    """Excerpts from the commentaries, the collections and the lexicons for the objection's quoted words."""
    found = quotes(objection)
    if not found:
        words = [w for w in WORD.findall(normalize_arabic(objection)) if len(w) > 2][:8]
        if len(words) < 3: return {'queries': [], 'excerpts': []}
        found = [' '.join(words)]
    plan = []
    if len(found) > 1: plan.append((' '.join(found), 'sharh', 4))  # both texts together: where the scholars reconcile them
    plan += [(q, 'sharh', 2) for q in found] + [(q, 'hadith', 2) for q in found] + [(w, 'lugha', 2) for w in lexicon_words(found)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(plan))) as pool:
        results = list(pool.map(lambda job: _search(*job), plan))
    excerpts, seen, counts = [], set(), {k: 0 for k in KINDS}
    for batch in results:
        for e in batch:
            key = (e['book_id'], e['page_id'])
            if key in seen or counts[e['kind']] >= LIMITS[e['kind']] or not e['text']: continue
            seen.add(key); counts[e['kind']] += 1; excerpts.append(e)
    order = {'sharh': 0, 'hadith': 1, 'lugha': 2}
    excerpts.sort(key=lambda e: order[e['kind']])
    return {'queries': [q for q, _, _ in plan], 'excerpts': excerpts}


def for_analyst(library):
    """The excerpts as the analyst reads them: kind, source, text."""
    return [{'kind': e['label'], 'source': f"{e['book']}، ج{e['vol']} ص{e['page']}" if e['vol'] else f"{e['book']}، ص{e['page']}", 'text': e['text']}
            for e in (library or {}).get('excerpts', [])]


def find_hadith(quote):
    """Where a hadith with no reference can be read in the Shamela collections (best match, or None)."""
    words = ' '.join(WORD.findall(normalize_arabic(quote))[:9])
    if len(words.split()) < 2: return None
    hits = _search(words, 'hadith', 5)
    best = max(hits, key=lambda e: sources.coverage(quote, e['text']), default=None)
    return best if best and sources.coverage(quote, best['text']) >= 0.7 else None
