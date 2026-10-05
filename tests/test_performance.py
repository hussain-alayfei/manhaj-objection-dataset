"""List views stay slim, search is Arabic-aware, and approval checks do not issue a query per record."""
import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import event

from src.api import create_app
from conftest import CHUNK_TEXT, approve, record

TOKEN = 'perf-token'
AUTH = {'Authorization': 'Bearer ' + TOKEN}
TOKENS = {'expert': hashlib.sha256(TOKEN.encode()).hexdigest()}


def test_list_rows_carry_only_what_the_table_shows(store):
    store.add(record('SHB-a', sub_patterns=['اختلاف المعنى']))
    c = TestClient(create_app(store, TOKENS))
    item = c.get('/api/records?kind=objection', headers=AUTH).json()['items'][0]
    assert set(item) == {'id', 'kind', 'title_ar', 'primary_pattern', 'sub_patterns', 'review_status', 'phase', 'source'}
    assert item['sub_patterns'] == ['اختلاف المعنى'] and item['source'] == {'source_name': 'وثيقة اختبار اصطناعية غير دينية', 'page_number': 1}
    assert 'source_excerpt' not in str(item)


def test_search_ignores_hamza_and_diacritics(store):
    store.add(record('SHB-b', title_ar='شبهة عن الإسلام والعقل'))
    store.add(record('SHB-c'))
    c = TestClient(create_app(store, TOKENS))
    found = c.get('/api/records?q=الاسلام', headers=AUTH).json()
    assert [r['id'] for r in found['items']] == ['SHB-b']
    assert c.get('/api/records?q=تُفَّاحَتين', headers=AUTH).json()['total'] == 2  # matches the objection text too


def test_eligible_uses_a_fixed_number_of_queries(store):
    store.add(record('RUL-x', 'rule', methodology_rule_ar=CHUNK_TEXT)); approve(store, 'RUL-x')
    for n in range(6):
        store.add(record(f'SHB-{n}', primary_pattern='جمع بين مختلفين', sub_patterns=['اختلاف المعنى'], methodology_rule_ids=['RUL-x'], methodology_rule_ar=CHUNK_TEXT))
        approve(store, f'SHB-{n}')
    statements = []
    listener = lambda *args: statements.append(1)
    event.listen(store.engine, 'before_cursor_execute', listener)
    try: eligible = store.eligible('objection')
    finally: event.remove(store.engine, 'before_cursor_execute', listener)
    assert len(eligible) == 6 and len(statements) <= 4


def test_history_lists_versions_without_full_snapshots(store):
    store.add(record())
    approve(store, 'SHB-test')
    items = store.history('SHB-test')
    assert [x['snapshot'] for x in items] == [{'version': 1}, {'version': 2}] and items[-1]['action'] == 'approve' and items[-1]['actor'] == 'expert'
    assert 'title_ar' in store.history('SHB-test', full=True)[-1]['snapshot']


def test_summary_counts_in_one_query(store):
    store.add(record()); store.add(record('RUL-y', 'rule'))
    counts = store.counts()
    assert counts['sources'] == 1 and sum(r['n'] for r in counts['objection']) == 1 and sum(r['n'] for r in counts['rule']) == 1
