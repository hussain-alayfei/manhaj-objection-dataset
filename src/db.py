"""One transactional storage layer for SQLite development and PostgreSQL production."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
import uuid
from collections import Counter, OrderedDict
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (JSON, BigInteger, Column, ForeignKey, Integer, MetaData, String, Table,
                        UniqueConstraint, create_engine, delete, event, func, insert, literal, or_, select, union_all, update)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool, StaticPool

from .auth import new_token, now_s, token_hash
from .models import Analysis, Record, ReviewRequest, now

metadata = MetaData()
sources = Table('sources', metadata, Column('id', String, primary_key=True), Column('sha256', String, unique=True, nullable=False), Column('payload', JSON, nullable=False))
chunks = Table('source_chunks', metadata, Column('id', String, primary_key=True), Column('source_id', ForeignKey('sources.id'), nullable=False), Column('page_number', Integer), Column('section', String, nullable=False), Column('text', String, nullable=False), Column('raw_text', String, nullable=False), Column('payload', JSON, nullable=False))
tables = {}
for name in ('methodology_rules', 'objections', 'objection_families'):
    tables[name] = Table(name, metadata, Column('id', String, primary_key=True), Column('source_id', ForeignKey('sources.id')), Column('status', String, nullable=False), Column('version', Integer, nullable=False), Column('phase', Integer, nullable=False), Column('payload', JSON, nullable=False))
reviewers = Table('reviewers', metadata, Column('id', String, primary_key=True), Column('payload', JSON, nullable=False))
reviews = Table('reviews', metadata, Column('id', String, primary_key=True), Column('record_id', String, nullable=False), Column('reviewer_id', ForeignKey('reviewers.id'), nullable=False), Column('payload', JSON, nullable=False))
versions = Table('record_versions', metadata, Column('id', String, primary_key=True), Column('record_id', String, nullable=False), Column('version', Integer, nullable=False), Column('payload', JSON, nullable=False), UniqueConstraint('record_id', 'version'))
claims = Table('objection_claims', metadata, Column('id', String, primary_key=True), Column('objection_id', ForeignKey('objections.id'), nullable=False), Column('text', String, nullable=False), Column('claim_type', String, nullable=False))
members = Table('objection_family_members', metadata, Column('family_id', ForeignKey('objection_families.id'), primary_key=True), Column('objection_id', ForeignKey('objections.id'), primary_key=True))
documents = {}
for name in ('diagnoses', 'training_exports', 'evaluation_runs', 'dataset_manifests', 'phase_gates', 'extraction_runs', 'duplicate_runs', 'source_items'):
    documents[name] = Table(name, metadata, Column('id', String, primary_key=True), Column('payload', JSON, nullable=False))
embeddings = Table('embeddings', metadata, Column('id', String, primary_key=True), Column('record_id', String, nullable=False), Column('record_version', Integer, nullable=False), Column('field', String, nullable=False), Column('model', String, nullable=False), Column('content_hash', String, nullable=False), Column('values', JSON, nullable=False))
# Reviewer accounts (supabase/migrations/20261005064602_accounts.sql). Tagged so the generated
# initial migration stays exactly as applied. Times are Unix seconds so SQLite and Postgres compare alike.
LATER = {'migration': '20261005064602_accounts'}
accounts = Table('accounts', metadata, Column('id', String, primary_key=True), Column('email', String, unique=True, nullable=False), Column('password_hash', String, nullable=False), Column('payload', JSON, nullable=False), info=LATER)
sessions = Table('sessions', metadata, Column('token_hash', String, primary_key=True), Column('account_id', ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False), Column('created_at', BigInteger, nullable=False), Column('expires_at', BigInteger, nullable=False), Column('revoked_at', BigInteger), info=LATER)
events = Table('events', metadata, Column('id', String, primary_key=True), Column('kind', String, nullable=False), Column('key', String, nullable=False), Column('at', BigInteger, nullable=False), info=LATER)
KINDS = {'objection': 'objections', 'rule': 'methodology_rules', 'family': 'objection_families'}
CACHE_ENTRIES = 256
PREFIXES = {'SHB-': 'objections', 'RUL-': 'methodology_rules', 'FAM-': 'objection_families'}


def _tables_for(record_id):
    """Record tables to look in, most likely first (ids carry their kind as a prefix)."""
    first = next((name for prefix, name in PREFIXES.items() if str(record_id).startswith(prefix)), None)
    return [tables[first], *(t for n, t in tables.items() if n != first)] if first else list(tables.values())


def _summary_select(table, *extra):
    p = table.c.payload
    return select(table.c.id, table.c.status, table.c.phase, p['kind'].as_string().label('kind'), p['title_ar'].as_string().label('title_ar'),
                  p['primary_pattern'].as_string().label('primary_pattern'), p['sub_patterns'].label('sub_patterns'),
                  p[('source', 'source_name')].as_string().label('source_name'), p[('source', 'page_number')].as_string().label('page_number'), *extra)


def _summary(row):
    subs = row.sub_patterns
    if isinstance(subs, str): subs = json.loads(subs)
    page = row.page_number
    source = None if row.source_name is None and page is None else {'source_name': row.source_name, 'page_number': int(page) if page not in (None, '') else None}
    return {'id': row.id, 'kind': row.kind, 'title_ar': row.title_ar or '', 'primary_pattern': row.primary_pattern, 'sub_patterns': subs or [],
            'review_status': row.status, 'phase': row.phase, 'source': source}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class Conflict(ValueError):
    pass


def normalize_database_url(url):
    """Accept provider-style Postgres URLs and pin the installed psycopg 3 driver."""
    for prefix in ('postgres://', 'postgresql://'):
        if url.startswith(prefix): return 'postgresql+psycopg://' + url[len(prefix):]
    return url


def _json(value):
    # Store Arabic as UTF-8 rather than \u escapes: roughly 2.5x smaller payloads and egress.
    return json.dumps(value, ensure_ascii=False)


class Store:
    def __init__(self, url=None):
        url = normalize_database_url(url or os.getenv('DATABASE_URL', 'sqlite:///data/manhaj.db'))
        opts = {'json_serializer': _json}
        if url.startswith('sqlite'):
            opts['pool_pre_ping'] = True
            opts['connect_args'] = {'check_same_thread': False, 'timeout': 30}
            if ':memory:' in url:
                opts['poolclass'] = StaticPool
            elif url.startswith('sqlite:///'):
                Path(url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
        else:
            parsed = make_url(url)
            host = parsed.host or ''
            # Supavisor transaction mode (and Supabase in general) cannot use server-side prepared statements.
            # TCP keepalives so long CLI jobs survive idle gaps on flaky networks.
            opts['connect_args'] = {'prepare_threshold': None, 'connect_timeout': 15, 'keepalives': 1, 'keepalives_idle': 30, 'keepalives_interval': 10, 'keepalives_count': 5, 'tcp_user_timeout': 10000}
            if host.endswith(('.supabase.com', '.supabase.co')) and 'sslmode' not in parsed.query:
                opts['connect_args']['sslmode'] = 'require'
            if os.getenv('VERCEL'):
                # Fluid compute reuses warm instances: keep one or two pooler connections open instead of
                # paying a new TCP+TLS handshake per request; pre-ping replaces connections the pooler closed.
                opts.update(pool_pre_ping=True, pool_size=2, max_overflow=3, pool_recycle=1800, pool_use_lifo=True)
            elif parsed.port == 6543:
                opts['poolclass'] = NullPool
            else:
                opts.update(pool_pre_ping=True, pool_size=2, max_overflow=3)
        self.engine = create_engine(url, **opts)
        # Plain reads run in autocommit on Postgres: each statement is its own snapshot (READ COMMITTED
        # already behaves so), and psycopg skips the BEGIN/ROLLBACK round trips. Safe on the transaction pooler.
        self.reader = self.engine.execution_options(isolation_level='AUTOCOMMIT') if not url.startswith('sqlite') else self.engine
        self._cache, self._cache_lock, self._generation = OrderedDict(), threading.Lock(), 0
        self._sessions, self._session_lock = {}, threading.Lock()
        self.cache_seconds = float(os.getenv('READ_CACHE_SECONDS', '10'))
        if url.startswith('sqlite'):
            @event.listens_for(self.engine, 'connect')
            def configure(dbapi, _):
                dbapi.execute('PRAGMA foreign_keys=ON')
                dbapi.execute('PRAGMA journal_mode=WAL')
            metadata.create_all(self.engine)
        else:
            # PostgreSQL schema is owned by supabase/migrations; never improvise tables at runtime.
            with self.reader.connect() as c:
                present = c.exec_driver_sql("SELECT to_regclass('public.semantic_vectors') IS NOT NULL AND to_regclass('public.accounts') IS NOT NULL").scalar()
            if not present: raise RuntimeError('Database schema missing: apply supabase/migrations before starting the app')

    def cached(self, key, compute, seconds=None):
        """Short in-process cache for list/summary reads; every write in this process clears it.
        Other server instances see a change within `cache_seconds`."""
        ttl = self.cache_seconds if seconds is None else seconds
        if ttl <= 0: return compute()
        now_ = time.monotonic()
        with self._cache_lock:
            hit = self._cache.get(key)
            if hit and now_ - hit[0] < ttl:
                self._cache.move_to_end(key)
                return copy.deepcopy(hit[1])
            generation = self._generation
        value = compute()
        with self._cache_lock:
            # A read that started before a write finished must not be cached as fresh.
            if generation == self._generation:
                self._cache[key] = (now_, value)
                self._cache.move_to_end(key)
                while len(self._cache) > CACHE_ENTRIES: self._cache.popitem(last=False)
        return copy.deepcopy(value)

    def clear_cache(self):
        with self._cache_lock:
            self._generation += 1
            self._cache.clear()

    @contextmanager
    def transaction(self, lock=731905, clear=True):
        try:
            with self.engine.begin() as conn:
                if self.engine.dialect.name == 'sqlite':
                    conn.exec_driver_sql('BEGIN IMMEDIATE')
                else:
                    # Serialize write/governance operations, including phase and export gates.
                    conn.exec_driver_sql(f'SELECT pg_advisory_xact_lock({int(lock)})')
                yield conn
        finally:
            if clear: self.clear_cache()

    def reserve_usage(self, kind, key, since, per_key, overall=0):
        """Count and record one use atomically, so parallel requests cannot all slip under a limit."""
        with self.transaction(lock=731906, clear=False) as c:
            if per_key and self.count_events(kind, key, since, c) >= per_key: return False
            if overall and self.count_events(kind, None, since, c) >= overall: return False
            self.add_event(kind, key, c)
        return True

    def get(self, record_id, conn=None):
        if conn is None:
            with self.reader.connect() as c:
                return self.get(record_id, c)
        for table in _tables_for(record_id):
            row = conn.execute(select(table.c.payload).where(table.c.id == record_id)).scalar_one_or_none()
            if row is not None:
                return copy.deepcopy(row)
        raise KeyError(record_id)

    def get_many(self, ids, conn):
        """Payloads for many records in at most one query per record table."""
        wanted, found = set(ids), {}
        for table in tables.values():
            if not wanted - set(found): break
            for rid, payload in conn.execute(select(table.c.id, table.c.payload).where(table.c.id.in_(sorted(wanted - set(found))))):
                found[rid] = payload
        return found

    def records(self, kind=None, status=None, phase=None, conn=None):
        if conn is None:
            with self.reader.connect() as c:
                return self.records(kind, status, phase, c)
        result = []
        for table in ([tables[KINDS[kind]]] if kind else tables.values()):
            q = select(table.c.payload).order_by(table.c.id)
            if status: q = q.where(table.c.status.in_([status] if isinstance(status, str) else list(status)))
            if phase: q = q.where(table.c.phase == phase)
            result.extend(conn.execute(q).scalars().all())
        return copy.deepcopy(result)

    def page(self, kind=None, status=None, phase=None, offset=0, limit=50):
        """Count and slice in SQL, returning only the fields list views show (a few hundred bytes per row
        instead of the full ~13 KB record with its source spans)."""
        with self.reader.connect() as c:
            selected = [tables[KINDS[kind]]] if kind else list(tables.values())
            def scoped(table, q):
                if status: q = q.where(table.c.status == status)
                if phase: q = q.where(table.c.phase == phase)
                return q
            counts = [c.execute(scoped(t, select(func.count()).select_from(t))).scalar_one() for t in selected]
            items, skip = [], offset
            for table, count in zip(selected, counts):
                if len(items) >= limit: break
                if skip >= count:
                    skip -= count; continue
                q = scoped(table, _summary_select(table).order_by(table.c.id)).offset(skip).limit(limit - len(items))
                items.extend(_summary(row) for row in c.execute(q))
                skip = 0
            return {'total': sum(counts), 'items': items}

    def search_rows(self, kind=None, status=None, phase=None):
        """Summaries plus normalized searchable text, for the list search box."""
        from .parsing import normalize_arabic
        with self.reader.connect() as c:
            out = []
            for table in ([tables[KINDS[kind]]] if kind else tables.values()):
                p = table.c.payload
                q = _summary_select(table, p['objection_text_ar'].as_string().label('objection_text_ar'), p['central_claim_ar'].as_string().label('central_claim_ar'), p['methodology_rule_ar'].as_string().label('methodology_rule_ar')).order_by(table.c.id)
                if status: q = q.where(table.c.status == status)
                if phase: q = q.where(table.c.phase == phase)
                for row in c.execute(q):
                    item = _summary(row)
                    item['_text'] = normalize_arabic(' '.join(x or '' for x in (row.title_ar, row.objection_text_ar, row.central_claim_ar, row.methodology_rule_ar, row.id)))
                    out.append(item)
            return out

    def counts(self):
        """Status/phase totals per record kind, computed in SQL."""
        parts = [select(literal(kind).label('kind'), t.c.status, t.c.phase, func.count().label('n')).group_by(t.c.status, t.c.phase) for kind, t in ((k, tables[n]) for k, n in KINDS.items())]
        parts.append(select(literal('sources').label('kind'), literal(None).label('status'), literal(None).label('phase'), func.count().label('n')).select_from(sources))
        out = {kind: [] for kind in KINDS}
        with self.reader.connect() as c:
            for row in c.execute(union_all(*parts)):
                if row.kind == 'sources': out['sources'] = row.n
                else: out[row.kind].append({'status': row.status, 'phase': row.phase, 'n': row.n})
        return out

    def source_list(self, conn=None):
        if conn is None:
            with self.reader.connect() as c: return self.source_list(c)
        return conn.execute(select(sources.c.payload)).scalars().all()

    def source_chunks(self, source_id, conn=None):
        if conn is None:
            with self.reader.connect() as c: return self.source_chunks(source_id, c)
        return [dict(r._mapping) for r in conn.execute(select(chunks).where(chunks.c.source_id == source_id).order_by(chunks.c.page_number, chunks.c.id))]

    def chunk_list(self, source_id):
        """Chunks without the raw extraction text (the reading view never shows it)."""
        with self.reader.connect() as c:
            return [dict(r._mapping) for r in c.execute(select(chunks.c.id, chunks.c.source_id, chunks.c.page_number, chunks.c.section, chunks.c.text, chunks.c.payload).where(chunks.c.source_id == source_id).order_by(chunks.c.page_number, chunks.c.id))]

    def verify_source(self, record, conn):
        citation = record.get('source')
        if not citation or not citation.get('spans'): raise ValueError('Missing source spans')
        source = conn.execute(select(sources.c.payload).where(sources.c.id == citation['source_id'])).scalar_one()
        if citation['source_type'] != source['source_type'] or citation['source_name'] != source['source_name'] or citation['author'] != source.get('author', ''):
            raise ValueError('Source metadata mismatch')
        if citation.get('source_url') != source.get('source_url'):
            raise ValueError('Source URL mismatch')
        for span in citation['spans']:
            row = conn.execute(select(chunks).where(chunks.c.id == span['chunk_id'])).mappings().one()
            if row['source_id'] != citation['source_id'] or row['page_number'] != span['page_number']:
                raise ValueError('Page/source mismatch')
            if row['text'][span['start']:span['end']] != span['text']:
                raise ValueError('Excerpt not present at exact offsets')
        if citation['source_excerpt'] != '\n'.join(s['text'] for s in citation['spans']):
            raise ValueError('Excerpt is not the cited evidence')
        if citation['page_number'] != citation['spans'][0]['page_number']:
            raise ValueError('First page mismatch')

    def add(self, record, conn=None):
        r = Record.model_validate(record).model_dump()
        if r['review_status'] not in ('draft', 'needs_review') or r['human_review']:
            raise ValueError('New records must enter human review')
        if conn is None:
            with self.transaction() as c: return self.add(r, c)
        table = tables[KINDS[r['kind']]]
        if conn.execute(select(table.c.id).where(table.c.id == r['id'])).first(): return False
        if r['kind'] != 'family': self.verify_source(r, conn)
        conn.execute(insert(table).values(id=r['id'], source_id=r['source']['source_id'] if r['source'] else None, status=r['review_status'], version=1, phase=r['phase'], payload=r))
        conn.execute(insert(versions).values(id=str(uuid.uuid4()), record_id=r['id'], version=1, payload={'snapshot': r, 'actor': r['added_by'], 'at': now(), 'action': 'create'}))
        self._relations(r, conn)
        return True

    def _relations(self, r, conn):
        if r['kind'] == 'objection':
            conn.execute(delete(claims).where(claims.c.objection_id == r['id']))
            for i, value in enumerate([r['central_claim_ar']] + r['subclaims_ar']):
                if value: conn.execute(insert(claims).values(id=f"{r['id']}:{i}", objection_id=r['id'], text=value, claim_type='central' if i == 0 else 'subclaim'))
        if r['kind'] == 'family':
            conn.execute(delete(members).where(members.c.family_id == r['id']))
            for rid in r['examples']:
                conn.execute(insert(members).values(family_id=r['id'], objection_id=rid))

    def register_reviewer(self, reviewer_id):
        self.register_reviewers([reviewer_id])

    def register_reviewers(self, reviewer_ids):
        ids = set(reviewer_ids)
        with self.engine.connect() as c:
            missing = ids - set(c.execute(select(reviewers.c.id).where(reviewers.c.id.in_(ids))).scalars())
        if not missing: return  # common cold-start path: read only, no global write lock
        with self.transaction() as c:  # serialized by the advisory lock, so concurrent cold starts cannot collide
            missing -= set(c.execute(select(reviewers.c.id).where(reviewers.c.id.in_(missing))).scalars())
            for rid in sorted(missing):
                c.execute(insert(reviewers).values(id=rid, payload={'created_at': now(), 'identity_source': 'operator_configured_token'}))

    def review(self, rid, req: ReviewRequest, reviewer_id):
        with self.transaction() as c:
            if not c.execute(select(reviewers.c.id).where(reviewers.c.id == reviewer_id)).first(): raise ValueError('Unknown reviewer')
            old = self.get(rid, c)
            if old['version'] != req.expected_version: raise Conflict('Record changed; reload before saving')
            allowed = set(Analysis.model_fields) | {'title_ar', 'objection_text_ar', 'reviewer_notes', 'tags', 'duplicate_group_id', 'similarity_type', 'family_id', 'family_title_ar', 'core_claim_ar', 'core_confusion_ar', 'common_variants_ar', 'common_sub_patterns', 'methodology_rules', 'examples'}
            if set(req.changes) - allowed: raise ValueError('Source evidence and provenance are immutable; re-ingest a corrected extraction')
            new = copy.deepcopy(old)
            new.update(req.changes)
            Record.model_validate(new)  # wrong types (e.g. a number where ids are expected) become a 422, not a crash
            from .parsing import normalize_arabic
            if 'objection_text_ar' in req.changes:
                new['normalized_objection_ar'] = normalize_arabic(new['objection_text_ar'])
            if new['kind'] == 'objection' and 'methodology_rule_ids' in req.changes:
                new['methodology_rule_ids'] = list(dict.fromkeys(new['methodology_rule_ids']))
                linked = []
                for rule_id in new['methodology_rule_ids']:
                    try: rule = self.get(rule_id, c)
                    except KeyError: raise ValueError(f'Unknown methodology rule: {rule_id}') from None
                    if rule['kind'] != 'rule': raise ValueError(f'{rule_id} is not a methodology rule')
                    linked.append(rule['methodology_rule_ar'])
                new['methodology_rule_ar'] = '\n'.join(linked)  # stored rule text always mirrors the linked rules
            if 'examples' in req.changes:
                new['examples'] = list(dict.fromkeys(new['examples']))
                for example_id in new['examples']:
                    try: example = self.get(example_id, c)
                    except KeyError: raise ValueError(f'Unknown family example: {example_id}') from None
                    if example['kind'] != 'objection': raise ValueError(f'{example_id} is not an objection')
            new['review_status'] = {'approve': 'approved', 'reject': 'rejected', 'edit': 'needs_review', 'reopen': 'needs_review'}[req.action]
            new['requires_human_review'] = req.action != 'approve' or new['primary_pattern'] in ('unknown', 'mixed_pattern', 'multiple_claims', 'insufficient_evidence', 'requires_human_review')
            new['reviewer_notes'] = req.notes
            new['previous_version'], new['version'], new['updated_at'] = old['version'], old['version'] + 1, now()
            if req.action == 'approve':
                if not req.diagnosis_verified: raise ValueError('Diagnosis attestation required')
                if new['kind'] != 'family':
                    self.verify_source(new, c)
                    if not req.source_verified or not req.page_verified: raise ValueError('Source and page attestation required')
                if new['kind'] == 'objection':
                    from .parsing import normalize_arabic
                    wording = normalize_arabic(new['objection_text_ar'])
                    if not wording or wording not in normalize_arabic(new['source']['source_excerpt']):
                        raise ValueError('Exact objection wording must be selected from the source excerpt; use central claim for paraphrases')
                    if not all(new[k].strip() for k in ('central_claim_ar', 'diagnostic_reason_ar', 'revealing_question_ar', 'treatment_ar')):
                        raise ValueError('Complete diagnosis fields before approval')
                    if new['primary_pattern'] in ('جمع بين مختلفين', 'تفريق بين متماثلين', 'mixed_pattern') and not new['methodology_rule_ids']:
                        raise ValueError('Link approved source methodology rules')
                    for rule_id in new['methodology_rule_ids']:
                        try: rule = self.get(rule_id, c)
                        except KeyError: raise ValueError(f'Unknown methodology rule: {rule_id}') from None
                        if rule['kind'] != 'rule' or rule['phase'] != 1 or rule['review_status'] != 'approved': raise ValueError('Methodology rule is not approved Phase 1 evidence')
                    new['methodology_rule_ar'] = '\n'.join(self.get(x, c)['methodology_rule_ar'] for x in new['methodology_rule_ids'])
                if new['kind'] == 'rule':
                    rule_text = normalize_arabic(new['methodology_rule_ar'])
                    if not rule_text: raise ValueError('Rule text required')
                    # The UI shows this as "the rule as stated in the source", so it must be the author's words.
                    if rule_text not in normalize_arabic(new['source']['source_excerpt']):
                        raise ValueError('Rule text must be quoted from the source excerpt; put paraphrases in the diagnosis fields')
                if new['kind'] == 'family':
                    if not new['core_claim_ar'] or not new['examples']: raise ValueError('Family claim and examples required')
                    if any(self.get(x, c)['review_status'] != 'approved' for x in new['examples']): raise ValueError('Approve family members first')
            new['human_review'] = {'reviewer_id': reviewer_id, 'reviewed_at': now(), 'action': req.action, 'source_verified': req.source_verified, 'page_verified': req.page_verified, 'diagnosis_verified': req.diagnosis_verified, 'notes': req.notes}
            new = Record.model_validate(new).model_dump()
            table = tables[KINDS[new['kind']]]
            result = c.execute(update(table).where(table.c.id == rid, table.c.version == old['version']).values(version=new['version'], status=new['review_status'], payload=new))
            if result.rowcount != 1: raise Conflict('Concurrent update')
            audit = {'before': old, 'after': new, 'changes': req.changes, 'action': req.action, 'at': now()}
            c.execute(insert(reviews).values(id=str(uuid.uuid4()), record_id=rid, reviewer_id=reviewer_id, payload=audit))
            c.execute(insert(versions).values(id=str(uuid.uuid4()), record_id=rid, version=new['version'], payload={'snapshot': new, 'actor': reviewer_id, 'at': now(), 'action': req.action}))
            self._relations(new, c)
            return new

    def eligible(self, kind=None, conn=None):
        if conn is None:
            with self.reader.connect() as c: return self.eligible(kind, c)
        out, approved = [], [r for r in self.records(kind, 'approved', conn=conn) if r['human_review'] and r['human_review']['action'] == 'approve']
        linked = self.get_many({x for r in approved for x in (r['methodology_rule_ids'] if r['kind'] == 'objection' else r['examples'] if r['kind'] == 'family' else [])}, conn)
        for r in approved:
            if r['kind'] == 'objection':
                rules = [linked.get(x) for x in r['methodology_rule_ids']]
                if any(x is None or x['review_status'] != 'approved' for x in rules): continue
                # A rule edited after this objection was approved invalidates the copied rule text.
                if rules and r['methodology_rule_ar'] != '\n'.join(x['methodology_rule_ar'] for x in rules): continue
            if r['kind'] == 'family' and any(linked.get(x) is None or linked[x]['review_status'] != 'approved' for x in r['examples']): continue
            out.append(r)
        return out

    def add_machine_proposal(self, rid, changes, engine):
        """Version machine proposals without impersonating a human or overwriting evidence."""
        allowed = set(Analysis.model_fields) | {'title_ar', 'tags'}
        if set(changes) - allowed: raise ValueError('Machine proposal cannot change evidence or governance')
        with self.transaction() as c:
            old = self.get(rid, c)
            if old['human_review'] or old['review_status'] not in ('draft', 'needs_review'): return False
            if all(old.get(key) == value for key, value in changes.items()): return False
            fingerprint = digest([engine, changes])
            if old['ai_analysis'].get('proposal_hash') == fingerprint: return False
            new = copy.deepcopy(old); new.update(changes)
            new['previous_version'], new['version'], new['updated_at'] = old['version'], old['version']+1, now()
            new['requires_human_review'] = True
            new['ai_analysis'] = {'engine': engine, 'proposal': changes, 'proposal_hash': fingerprint, 'created_at': now(), 'label_ar': 'استنتاج تحليلي'}
            new = Record.model_validate(new).model_dump()
            table = tables[KINDS[new['kind']]]
            c.execute(update(table).where(table.c.id == rid, table.c.version == old['version']).values(version=new['version'], payload=new))
            c.execute(insert(versions).values(id=str(uuid.uuid4()), record_id=rid, version=new['version'], payload={'snapshot': new, 'actor': 'machine:'+engine, 'at': now(), 'action': 'machine_proposal'}))
            self._relations(new, c)
            return True

    def save_document(self, kind, payload, doc_id=None, conn=None):
        if conn is None:
            with self.transaction() as c: return self.save_document(kind, payload, doc_id, c)
        doc_id = doc_id or str(uuid.uuid4())
        conn.execute(insert(documents[kind]).values(id=doc_id, payload=payload))
        return doc_id

    def list_documents(self, kind, conn=None):
        if conn is None:
            with self.reader.connect() as c: return self.list_documents(kind, c)
        return [dict(r._mapping) for r in conn.execute(select(documents[kind]).order_by(documents[kind].c.id))]

    def get_document(self, kind, doc_id):
        with self.reader.connect() as c:
            row = c.execute(select(documents[kind]).where(documents[kind].c.id == doc_id)).mappings().one_or_none()
        if row is None: raise KeyError(doc_id)
        return dict(row)

    def document_ids(self, kind, ids):
        if not ids: return set()
        with self.reader.connect() as c:
            return set(c.execute(select(documents[kind].c.id).where(documents[kind].c.id.in_(list(ids)))).scalars())

    def count_documents(self, kind, field, value, since):
        """Count JSON documents whose payload[field]==value and payload['created_at']>=since."""
        t = documents[kind]
        with self.reader.connect() as c:
            if self.engine.dialect.name == 'postgresql':
                q = select(func.count()).select_from(t).where(t.c.payload[field].as_string() == value, t.c.payload['created_at'].as_string() >= since)
                return c.execute(q).scalar_one()
            return sum(1 for p in c.execute(select(t.c.payload)).scalars() if p.get(field) == value and p.get('created_at', '') >= since)

    # ---------- Accounts and sessions (no global write lock: they never touch review data) ----------
    def create_account(self, name, email, password_hash):
        account_id = 'u-' + uuid.uuid4().hex[:12]
        try:
            with self.engine.begin() as c:
                c.execute(insert(accounts).values(id=account_id, email=email, password_hash=password_hash, payload={'name': name, 'created_at': now()}))
                c.execute(insert(reviewers).values(id=account_id, payload={'created_at': now(), 'identity_source': 'account', 'name': name}))
        except IntegrityError as error:
            raise Conflict('هذا البريد مسجّل من قبل. سجّل الدخول بدلًا من ذلك.') from error
        with self._cache_lock: self._cache.pop('reviewer_names', None)
        return account_id

    def account_by_email(self, email):
        with self.reader.connect() as c:
            row = c.execute(select(accounts.c.id, accounts.c.password_hash, accounts.c.payload['name'].as_string().label('name')).where(accounts.c.email == email)).first()
        return None if row is None else {'id': row.id, 'password_hash': row.password_hash, 'name': row.name or ''}

    def create_session(self, account_id, days):
        token, at = new_token(), now_s()
        with self.engine.begin() as c:
            c.execute(insert(sessions).values(token_hash=token_hash(token), account_id=account_id, created_at=at, expires_at=at + days * 86400))
            c.execute(delete(sessions).where(sessions.c.account_id == account_id, sessions.c.expires_at < at))
        return token

    def session_account(self, token):
        """The account behind a session token, remembered for a minute per server instance."""
        key, clock = token_hash(token), time.monotonic()
        with self._session_lock:
            hit = self._sessions.get(key)
        if hit and hit[0] > clock: return hit[1]
        with self.reader.connect() as c:
            row = c.execute(select(accounts.c.id, accounts.c.email, accounts.c.payload['name'].as_string().label('name')).join(sessions, sessions.c.account_id == accounts.c.id)
                            .where(sessions.c.token_hash == key, sessions.c.revoked_at.is_(None), sessions.c.expires_at > now_s())).first()
        value = None if row is None else {'id': row.id, 'email': row.email, 'name': row.name or row.id}
        with self._session_lock:
            if len(self._sessions) > 1024: self._sessions.clear()
            self._sessions[key] = (clock + (60 if value else 5), value)
        return value

    def revoke_session(self, token):
        key = token_hash(token)
        with self.engine.begin() as c:
            c.execute(update(sessions).where(sessions.c.token_hash == key, sessions.c.revoked_at.is_(None)).values(revoked_at=now_s()))
        with self._session_lock: self._sessions.pop(key, None)

    def add_event(self, kind, key, conn=None):
        if conn is None:
            with self.engine.begin() as c: return self.add_event(kind, key, c)
        at = now_s()
        conn.execute(insert(events).values(id=uuid.uuid4().hex, kind=kind, key=key, at=at))
        conn.execute(delete(events).where(events.c.kind == kind, events.c.key == key, events.c.at < at - 3 * 86400))

    def count_events(self, kind, key, since, conn=None):
        if conn is None:
            with self.reader.connect() as c: return self.count_events(kind, key, since, c)
        q = select(func.count()).select_from(events).where(events.c.kind == kind, events.c.at >= since)
        if key is not None: q = q.where(events.c.key == key)
        return conn.execute(q).scalar_one()

    def reviewer_names(self):
        def load():
            with self.reader.connect() as c:
                return {rid: (payload or {}).get('name') or rid for rid, payload in c.execute(select(reviewers.c.id, reviewers.c.payload))}
        return self.cached('reviewer_names', load, 120)

    # ---------- A reviewer's own analyses (history, feedback) ----------
    def my_diagnoses(self, reviewer_id, offset=0, limit=20):
        t = documents['diagnoses']; p = t.c.payload
        mine = p['requested_by'].as_string() == reviewer_id
        with self.reader.connect() as c:
            total = c.execute(select(func.count()).select_from(t).where(mine)).scalar_one()
            rows = c.execute(select(t.c.id, p['created_at'].as_string(), p['input_ar'].as_string(), p[('analysis', 'primary_pattern')].as_string(),
                                    p['mode'].as_string(), p['abstention_reason'].as_string(), p['feedback']).where(mine)
                             .order_by(p['created_at'].as_string().desc()).offset(offset).limit(limit)).all()
        items = []
        for did, created, text, pattern, mode, abstained, feedback in rows:
            if isinstance(feedback, str): feedback = json.loads(feedback)
            items.append({'id': did, 'created_at': created, 'input_ar': (text or '')[:280], 'primary_pattern': pattern, 'mode': mode,
                          'abstention_reason': abstained, 'feedback': feedback})
        return {'total': total, 'items': items}

    def my_diagnosis(self, reviewer_id, diagnosis_id):
        doc = self.get_document('diagnoses', diagnosis_id)
        if doc['payload'].get('requested_by') != reviewer_id: raise KeyError(diagnosis_id)
        return dict(doc['payload'], id=doc['id'])

    def delete_my_diagnosis(self, reviewer_id, diagnosis_id):
        self.my_diagnosis(reviewer_id, diagnosis_id)
        t = documents['diagnoses']
        with self.engine.begin() as c:
            c.execute(delete(t).where(t.c.id == diagnosis_id))

    def delete_my_diagnoses(self, reviewer_id, ids):
        """Delete several of the reviewer's own analyses; ids that are not theirs are ignored."""
        t = documents['diagnoses']
        with self.engine.begin() as c:
            result = c.execute(delete(t).where(t.c.id.in_(list(ids)), t.c.payload['requested_by'].as_string() == reviewer_id))
        return result.rowcount

    def diagnosis_feedback(self, reviewer_id, diagnosis_id, verdict, note):
        """A reviewer marks their own analysis as correct or wrong; kept with the analysis for later review."""
        payload = self.my_diagnosis(reviewer_id, diagnosis_id)
        payload.pop('id', None)
        payload['feedback'] = {'verdict': verdict, 'note': note, 'at': now()}
        t = documents['diagnoses']
        with self.engine.begin() as c:
            c.execute(update(t).where(t.c.id == diagnosis_id).values(payload=payload))
        return payload['feedback']

    def add_followup(self, reviewer_id, diagnosis_id, question, answer, keep=20):
        """A question the reader asked about their own analysis, and its answer, kept with the analysis (newest last)."""
        payload = self.my_diagnosis(reviewer_id, diagnosis_id)
        payload.pop('id', None)
        turn = {'question': question, 'answer': answer, 'at': now()}
        payload['conversation'] = [*(payload.get('conversation') or []), turn][-keep:]
        t = documents['diagnoses']
        with self.engine.begin() as c:
            c.execute(update(t).where(t.c.id == diagnosis_id).values(payload=payload))
        return turn

    # ---------- Account profile ----------
    def account(self, account_id):
        with self.reader.connect() as c:
            row = c.execute(select(accounts.c.email, accounts.c.payload, accounts.c.password_hash).where(accounts.c.id == account_id)).first()
        if row is None: raise KeyError(account_id)
        return {'id': account_id, 'email': row.email, 'name': row.payload.get('name', ''), 'created_at': row.payload.get('created_at'), 'password_hash': row.password_hash, 'avatar': row.payload.get('avatar')}

    def update_account(self, account_id, name=None, email=None, password_hash=None, keep_session=None, avatar=None):
        with self.engine.begin() as c:
            row = c.execute(select(accounts.c.payload).where(accounts.c.id == account_id)).first()
            if row is None: raise KeyError(account_id)
            values = {}
            payload = dict(row.payload)
            if avatar is not None:
                if avatar: payload['avatar'] = avatar
                else: payload.pop('avatar', None)
                values['payload'] = payload
            if name is not None:
                values['payload'] = dict(payload, name=name)
                reviewer = c.execute(select(reviewers.c.payload).where(reviewers.c.id == account_id)).first()
                if reviewer is not None: c.execute(update(reviewers).where(reviewers.c.id == account_id).values(payload=dict(reviewer.payload or {}, name=name)))
            if email is not None: values['email'] = email
            if password_hash is not None: values['password_hash'] = password_hash
            try:
                if values: c.execute(update(accounts).where(accounts.c.id == account_id).values(**values))
            except IntegrityError as error:
                raise Conflict('هذا البريد مسجّل لحساب آخر.') from error
            if password_hash is not None:
                # a new password signs out every other device
                q = update(sessions).where(sessions.c.account_id == account_id, sessions.c.revoked_at.is_(None))
                if keep_session: q = q.where(sessions.c.token_hash != keep_session)
                c.execute(q.values(revoked_at=now_s()))
        with self._session_lock: self._sessions.clear()
        with self._cache_lock: self._cache.pop('reviewer_names', None)

    def activity(self, reviewer_id):
        t = documents['diagnoses']
        with self.reader.connect() as c:
            analyses = c.execute(select(func.count()).select_from(t).where(t.c.payload['requested_by'].as_string() == reviewer_id)).scalar_one()
            # counted in Python: grouping by a JSON expression repeats its bound key, which Postgres rejects
            actions = Counter(c.execute(select(reviews.c.payload['action'].as_string()).where(reviews.c.reviewer_id == reviewer_id)).scalars())
        return {'analyses': analyses, 'reviews': sum(actions.values()), 'approved': actions.get('approve', 0), 'edited': actions.get('edit', 0), 'rejected': actions.get('reject', 0)}

    def history(self, rid, full=False):
        with self.reader.connect() as c:
            if full: return c.execute(select(versions.c.payload).where(versions.c.record_id == rid).order_by(versions.c.version)).scalars().all()
            p = versions.c.payload
            rows = c.execute(select(versions.c.version, p['action'].as_string(), p['actor'].as_string(), p['at'].as_string()).where(versions.c.record_id == rid).order_by(versions.c.version))
            return [{'snapshot': {'version': v}, 'action': action, 'actor': actor, 'at': at} for v, action, actor, at in rows]
