"""Runs in CI against real PostgreSQL/pgvector, not a SQLite substitute."""
import os
import uuid
import pytest
from sqlalchemy import text
from src.db import Store

@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_URL'),reason='PostgreSQL integration requires TEST_POSTGRES_URL')
def test_postgres_vector_and_immutable_history():
    store=Store(os.environ['TEST_POSTGRES_URL'])
    with store.engine.connect() as c:
        assert c.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'")).scalar_one()=='vector'
        distance=c.execute(text("SELECT '[1,0,0]'::vector <=> '[1,0,0]'::vector")).scalar_one()
        assert distance==0
        names=c.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")).scalars().all()
        assert {'sources','source_chunks','semantic_vectors','reviews','record_versions','training_exports'}<=set(names)
    rid='integration-'+uuid.uuid4().hex
    with store.transaction() as c:
        c.execute(text("INSERT INTO record_versions(id,record_id,version,payload) VALUES (:id,:id,1,'{}')"),{'id':rid})
    with pytest.raises(Exception):
        with store.transaction() as c:c.execute(text('DELETE FROM record_versions WHERE id=:id'),{'id':rid})


@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_URL'),reason='PostgreSQL integration requires TEST_POSTGRES_URL')
def test_postgres_accounts_sessions_and_events():
    from src import auth
    from src.db import Conflict
    store=Store(os.environ['TEST_POSTGRES_URL'])
    email=f'pg-{uuid.uuid4().hex[:8]}@example.com'
    account=store.create_account('مراجع', email, auth.hash_password('pg-passphrase'))
    with pytest.raises(Conflict): store.create_account('مكرر', email, auth.hash_password('pg-passphrase'))
    token=store.create_session(account, 1)
    assert store.session_account(token)['id']==account
    store.revoke_session(token)
    assert store.session_account(token) is None
    store.add_event('login_failed', 'pg-key')
    assert store.count_events('login_failed', 'pg-key', auth.now_s()-60)==1


@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_URL'),reason='PostgreSQL integration requires TEST_POSTGRES_URL')
def test_postgres_slim_lists_counts_and_history():
    from sqlalchemy import insert
    from src.db import sources, chunks
    from conftest import CHUNK_TEXT, approve, record
    store=Store(os.environ['TEST_POSTGRES_URL'])
    with store.transaction() as c:
        if not c.execute(text("SELECT 1 FROM sources WHERE id='SRC-test'")).first():
            source={'id':'SRC-test','source_type':'book','source_name':'وثيقة اختبار اصطناعية غير دينية','author':'test','sha256':'test','page_count':1}
            c.execute(insert(sources).values(id='SRC-test',sha256='test',payload=source))
            c.execute(insert(chunks).values(id='CH-1',source_id='SRC-test',page_number=1,section='اختبار',text=CHUNK_TEXT,raw_text=CHUNK_TEXT,payload={}))
    rid='SHB-pg'+uuid.uuid4().hex[:8]
    store.add(record(rid, sub_patterns=['اختلاف المعنى']))
    approve(store, rid)
    page=store.page('objection', 'approved', None, 0, 200)
    item=next(x for x in page['items'] if x['id']==rid)
    assert item['sub_patterns']==['اختلاف المعنى'] and item['source']['page_number']==1 and item['review_status']=='approved'
    assert any(r['n']>=1 for r in store.counts()['objection'])
    assert store.history(rid)[-1]['snapshot']=={'version':2}
    assert store.get(rid)['id']==rid
    with store.engine.connect() as c: assert rid in store.get_many([rid], c)
