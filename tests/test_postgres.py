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
