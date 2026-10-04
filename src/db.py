"""One transactional storage layer for SQLite development and PostgreSQL production."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (JSON, Column, ForeignKey, Integer, MetaData, String, Table,
                        UniqueConstraint, create_engine, delete, event, func, insert, inspect, or_, select, update)
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool, StaticPool

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
KINDS = {'objection': 'objections', 'rule': 'methodology_rules', 'family': 'objection_families'}


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
            opts['connect_args'] = {'prepare_threshold': None, 'connect_timeout': 15, 'keepalives': 1, 'keepalives_idle': 30, 'keepalives_interval': 10, 'keepalives_count': 5}
            if host.endswith(('.supabase.com', '.supabase.co')) and 'sslmode' not in parsed.query:
                opts['connect_args']['sslmode'] = 'require'
            if parsed.port == 6543 or os.getenv('VERCEL'):
                opts['poolclass'] = NullPool  # the external pooler owns connection reuse
            else:
                opts.update(pool_pre_ping=True, pool_size=2, max_overflow=3)
        self.engine = create_engine(url, **opts)
        if url.startswith('sqlite'):
            @event.listens_for(self.engine, 'connect')
            def configure(dbapi, _):
                dbapi.execute('PRAGMA foreign_keys=ON')
                dbapi.execute('PRAGMA journal_mode=WAL')
            metadata.create_all(self.engine)
        else:
            # PostgreSQL schema is owned by supabase/migrations; never improvise tables at runtime.
            with self.engine.connect() as c:
                if not inspect(c).has_table('semantic_vectors'):
                    raise RuntimeError('Database schema missing: apply supabase/migrations before starting the app')

    @contextmanager
    def transaction(self):
        with self.engine.begin() as conn:
            if self.engine.dialect.name == 'sqlite':
                conn.exec_driver_sql('BEGIN IMMEDIATE')
            else:
                # Serialize write/governance operations, including phase and export gates.
                conn.exec_driver_sql('SELECT pg_advisory_xact_lock(731905)')
            yield conn

    def get(self, record_id, conn=None):
        if conn is None:
            with self.engine.connect() as c:
                return self.get(record_id, c)
        for table in tables.values():
            row = conn.execute(select(table.c.payload).where(table.c.id == record_id)).scalar_one_or_none()
            if row is not None:
                return copy.deepcopy(row)
        raise KeyError(record_id)

    def records(self, kind=None, status=None, phase=None, conn=None):
        if conn is None:
            with self.engine.connect() as c:
                return self.records(kind, status, phase, c)
        result = []
        for table in ([tables[KINDS[kind]]] if kind else tables.values()):
            q = select(table.c.payload).order_by(table.c.id)
            if status: q = q.where(table.c.status.in_([status] if isinstance(status, str) else list(status)))
            if phase: q = q.where(table.c.phase == phase)
            result.extend(conn.execute(q).scalars().all())
        return copy.deepcopy(result)

    def page(self, kind=None, status=None, phase=None, offset=0, limit=50):
        """Count and slice in SQL so list views never move the whole corpus over the network."""
        with self.engine.connect() as c:
            selected = [tables[KINDS[kind]]] if kind else list(tables.values())
            def scoped(table, q):
                if status: q = q.where(table.c.status == status)
                if phase: q = q.where(table.c.phase == phase)
                return q
            total = sum(c.execute(scoped(t, select(func.count()).select_from(t))).scalar_one() for t in selected)
            items, skip = [], offset
            for table in selected:
                if len(items) >= limit: break
                count = c.execute(scoped(table, select(func.count()).select_from(table))).scalar_one()
                if skip >= count:
                    skip -= count; continue
                q = scoped(table, select(table.c.payload).order_by(table.c.id)).offset(skip).limit(limit - len(items))
                items.extend(c.execute(q).scalars().all())
                skip = 0
            return {'total': total, 'items': copy.deepcopy(items)}

    def counts(self):
        """Status/phase totals per record kind, computed in SQL."""
        out = {}
        with self.engine.connect() as c:
            for kind, name in KINDS.items():
                t = tables[name]
                out[kind] = [dict(r._mapping) for r in c.execute(select(t.c.status, t.c.phase, func.count().label('n')).group_by(t.c.status, t.c.phase))]
            out['sources'] = c.execute(select(func.count()).select_from(sources)).scalar_one()
        return out

    def source_list(self, conn=None):
        if conn is None:
            with self.engine.connect() as c: return self.source_list(c)
        return conn.execute(select(sources.c.payload)).scalars().all()

    def source_chunks(self, source_id, conn=None):
        if conn is None:
            with self.engine.connect() as c: return self.source_chunks(source_id, c)
        return [dict(r._mapping) for r in conn.execute(select(chunks).where(chunks.c.source_id == source_id).order_by(chunks.c.page_number, chunks.c.id))]

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
            if 'objection_text_ar' in req.changes:
                from .parsing import normalize_arabic
                new['normalized_objection_ar'] = normalize_arabic(new['objection_text_ar'])
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
                    if normalize_arabic(new['objection_text_ar']) not in normalize_arabic(new['source']['source_excerpt']):
                        raise ValueError('Exact objection wording must be selected from the source excerpt; use central claim for paraphrases')
                    if not all(new[k].strip() for k in ('central_claim_ar', 'diagnostic_reason_ar', 'revealing_question_ar', 'treatment_ar')):
                        raise ValueError('Complete diagnosis fields before approval')
                    if new['primary_pattern'] in ('جمع بين مختلفين', 'تفريق بين متماثلين', 'mixed_pattern') and not new['methodology_rule_ids']:
                        raise ValueError('Link approved source methodology rules')
                    for rule_id in new['methodology_rule_ids']:
                        rule = self.get(rule_id, c)
                        if rule['kind'] != 'rule' or rule['phase'] != 1 or rule['review_status'] != 'approved': raise ValueError('Methodology rule is not approved Phase 1 evidence')
                    new['methodology_rule_ar'] = '\n'.join(self.get(x, c)['methodology_rule_ar'] for x in new['methodology_rule_ids'])
                if new['kind'] == 'rule' and not new['methodology_rule_ar'].strip(): raise ValueError('Rule text required')
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
            with self.engine.connect() as c: return self.eligible(kind, c)
        out = []
        for r in self.records(kind, 'approved', conn=conn):
            if not r['human_review'] or r['human_review']['action'] != 'approve': continue
            if r['kind'] == 'objection' and any(self.get(x, conn)['review_status'] != 'approved' for x in r['methodology_rule_ids']): continue
            if r['kind'] == 'family' and any(self.get(x, conn)['review_status'] != 'approved' for x in r['examples']): continue
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
            with self.engine.connect() as c: return self.list_documents(kind, c)
        return [dict(r._mapping) for r in conn.execute(select(documents[kind]).order_by(documents[kind].c.id))]

    def get_document(self, kind, doc_id):
        with self.engine.connect() as c:
            row = c.execute(select(documents[kind]).where(documents[kind].c.id == doc_id)).mappings().one_or_none()
        if row is None: raise KeyError(doc_id)
        return dict(row)

    def document_ids(self, kind, ids):
        if not ids: return set()
        with self.engine.connect() as c:
            return set(c.execute(select(documents[kind].c.id).where(documents[kind].c.id.in_(list(ids)))).scalars())

    def count_documents(self, kind, field, value, since):
        """Count JSON documents whose payload[field]==value and payload['created_at']>=since."""
        t = documents[kind]
        with self.engine.connect() as c:
            if self.engine.dialect.name == 'postgresql':
                q = select(func.count()).select_from(t).where(t.c.payload[field].as_string() == value, t.c.payload['created_at'].as_string() >= since)
                return c.execute(q).scalar_one()
            return sum(1 for p in c.execute(select(t.c.payload)).scalars() if p.get(field) == value and p.get('created_at', '') >= since)

    def history(self, rid):
        with self.engine.connect() as c:
            return c.execute(select(versions.c.payload).where(versions.c.record_id == rid).order_by(versions.c.version)).scalars().all()
