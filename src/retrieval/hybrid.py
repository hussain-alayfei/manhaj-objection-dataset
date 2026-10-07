import math
import os
from collections import Counter

import httpx
from sqlalchemy import delete, insert, select, text as sqltext

from ..db import digest, embeddings
from ..llm import embedding_dim, embedding_provider, openai_client
from ..parsing import tokens

FIELDS = ['objection_text_ar', 'central_claim_ar', 'methodology_rule_ar', 'source_excerpt', 'family_summary']
DRAFT_STATUSES = ('needs_review', 'draft')  # usable only when a reviewer explicitly asks for draft mode
OPENAI_BATCH = 128


def field_text(r, field):
    if field == 'source_excerpt': return (r.get('source') or {}).get('source_excerpt', '')
    if field == 'family_summary': return ' '.join([r['family_title_ar'], r['core_claim_ar'], r['core_confusion_ar']])
    return r.get(field, '')


def _check(vectors, expected, dim=None):
    if len(vectors) != expected: raise ValueError('Embedding count mismatch')
    if any(not v or not all(math.isfinite(x) for x in v) for v in vectors): raise ValueError('Invalid embeddings')
    if dim and any(len(v) != dim for v in vectors): raise ValueError('Embedding dimension mismatch')
    return vectors


class SemanticEncoder:
    def __init__(self, model=None, client=None, interactive=False):
        self.interactive = interactive  # inside a web request: short timeout, no retries
        self.provider = embedding_provider()
        self.api_model = model or os.getenv('EMBEDDING_MODEL', '')
        if not self.api_model: raise ValueError('Set EMBEDDING_MODEL for semantic retrieval; lexical fallback is explicitly labelled')
        self.dim = embedding_dim()
        # The storage key carries the dimension so vectors of different sizes are never compared.
        self.model = f'{self.api_model}@{self.dim}' if self.provider == 'openai' else self.api_model
        self.client = client

    def encode(self, texts):
        if self.provider == 'sentence_transformers':
            if self.client is None:
                from sentence_transformers import SentenceTransformer
                self.client = SentenceTransformer(self.api_model)
            return self.client.encode(texts, normalize_embeddings=True).tolist()
        if self.provider == 'openai': return self._openai(texts)
        response = httpx.post(os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434') + '/api/embed', json={'model': self.api_model, 'input': texts}, timeout=120)
        response.raise_for_status()
        return _check(response.json()['embeddings'], len(texts))

    def _openai(self, texts):
        from openai import OpenAIError
        vectors = [[0.0] * self.dim for _ in texts]  # empty text carries no signal: zero vector, cosine 0
        wanted = [i for i, t in enumerate(texts) if t and t.strip()]
        try:
            self.client = self.client or (openai_client(timeout=20, max_retries=0) if self.interactive else openai_client(timeout=60))
            for start in range(0, len(wanted), OPENAI_BATCH):
                batch = wanted[start:start + OPENAI_BATCH]
                response = self.client.embeddings.create(model=self.api_model, input=[texts[i] for i in batch], dimensions=self.dim)
                data = sorted(response.data, key=lambda d: d.index)
                for i, vector in zip(batch, _check([list(d.embedding) for d in data], len(batch), self.dim)):
                    vectors[i] = vector
        except OpenAIError as error:
            raise ValueError(f'embedding_provider_error: {type(error).__name__}') from error
        return vectors


def cosine(a, b):
    if len(a) != len(b): raise ValueError('Embedding dimension mismatch')
    den = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return sum(x*y for x, y in zip(a,b))/den if den else 0


def embedding_candidates(store, include_drafts=False, kind=None):
    records = store.eligible(kind)
    if include_drafts:
        seen = {r['id'] for r in records}
        records += [r for r in store.records(kind, DRAFT_STATUSES) if r['id'] not in seen]
    return records


def refresh_embeddings(store, encoder=None, include_drafts=False, record_ids=None, limit=None):
    """Embed only missing (record, version, field, model) combinations.

    Provider calls happen before the write transaction so the global write lock is held briefly.
    Unchanged text on a new record version reuses its stored vector instead of calling the provider."""
    encoder = encoder or SemanticEncoder(interactive=record_ids is not None)
    if record_ids is not None:
        # Targeted refresh (after a review): touch only these records, not the whole corpus.
        wanted = {'approved', *DRAFT_STATUSES} if include_drafts else {'approved'}
        records = []
        for rid in dict.fromkeys(record_ids):
            try: r = store.get(rid)
            except KeyError: continue
            if r['review_status'] in wanted: records.append(r)
    else:
        records = embedding_candidates(store, include_drafts)
    e = embeddings.c
    query = select(e.id, e.record_id, e.record_version, e.field, e.content_hash).where(e.model == encoder.model)
    if record_ids is not None: query = query.where(e.record_id.in_([r['id'] for r in records] or ['']))
    with store.engine.connect() as c:
        existing = {(row['record_id'], row['field']): dict(row) for row in c.execute(query).mappings()}
    todo, reuse = [], []
    for r in records:
        for field in FIELDS:
            value = field_text(r, field)
            if not value.strip(): continue
            row = existing.get((r['id'], field))
            if row and row['record_version'] == r['version'] and row['content_hash'] == digest(value): continue
            (reuse if row and row['content_hash'] == digest(value) else todo).append((r, field, value, row))
    if limit is not None: todo = todo[:limit]
    if reuse:  # only rows whose text is unchanged need their stored vector
        with store.engine.connect() as c:
            stored = dict(c.execute(select(e.id, e['values']).where(e.id.in_([row['id'] for *_, row in reuse]))).all())
        for *_, row in reuse: row['values'] = stored[row['id']]
    vectors = encoder.encode([value for _, _, value, _ in todo]) if todo else []
    planned = [(r, f, v, vec) for (r, f, v, _), vec in zip(todo, vectors)] + [(r, f, v, list(row['values'])) for r, f, v, row in reuse]
    if not planned: return 0
    postgres = store.engine.dialect.name == 'postgresql'
    with store.transaction() as c:
        for r, field, value, vector in planned:
            if postgres and len(vector) != embedding_dim(): raise ValueError('Vector dimension differs from database migration')
            eid = digest([r['id'], field, encoder.model])
            c.execute(delete(embeddings).where(embeddings.c.id == eid))
            c.execute(insert(embeddings).values(id=eid, record_id=r['id'], record_version=r['version'], field=field, model=encoder.model, content_hash=digest(value), values=vector))
            if postgres:
                c.execute(sqltext('INSERT INTO semantic_vectors (id,record_id,record_version,model,embedding) VALUES (:id,:rid,:version,:model,CAST(:vec AS vector))'), {'id': eid, 'rid': r['id'], 'version': r['version'], 'model': encoder.model, 'vec': str(vector)})
    return len(planned)


def build_embeddings(store, encoder=None, include_drafts=False):
    return refresh_embeddings(store, encoder, include_drafts)


class HybridRetriever:
    def __init__(self, store, encoder=None):
        self.store = store
        self.encoder = encoder or (SemanticEncoder(interactive=True) if os.getenv('EMBEDDING_MODEL') else None)

    def encode_query(self, query):
        return self.encoder.encode([query])[0] if self.encoder else None

    def search(self, query, kind=None, limit=8, filters=None, exclude_ids=None, *, include_drafts=False, query_vector=None):
        filters, exclude_ids = filters or {}, set(exclude_ids or [])
        if set(filters) - {'primary_pattern', 'phase', 'source_id', 'tags'}: raise ValueError('Unsupported metadata filter')
        candidates = embedding_candidates(self.store, include_drafts, kind)
        candidates = [r for r in candidates if r['id'] not in exclude_ids and all((r.get('source') or {}).get('source_id') == v if k == 'source_id' else all(x in r['tags'] for x in v) if k == 'tags' else r.get(k) == v for k, v in filters.items())]
        if not candidates: return {'mode': 'hybrid' if self.encoder else 'lexical_only', 'results': []}
        documents = [tokens(' '.join(field_text(r, f) for f in FIELDS)) for r in candidates]
        query_tokens = tokens(query)
        avg = sum(map(len, documents))/len(documents) or 1
        df = Counter(t for doc in documents for t in set(doc))
        lexical = {}
        for r, doc in zip(candidates, documents):
            tf = Counter(doc)
            lexical[r['id']] = sum(math.log(1 + (len(documents)-df[t]+.5)/(df[t]+.5)) * tf[t]*2.5/(tf[t]+1.5*(.25+.75*len(doc)/avg)) for t in query_tokens if tf[t])
        semantic = {}
        if self.encoder:
            qv = query_vector if query_vector is not None else self.encoder.encode([query])[0]
            allowed = {r['id']: r['version'] for r in candidates}
            with self.store.reader.connect() as c:
                if self.store.engine.dialect.name == 'postgresql':
                    # Exact distance over current, metadata-filtered candidate IDs.
                    from sqlalchemy import bindparam
                    query_sql = sqltext('SELECT record_id,record_version,1-(embedding <=> CAST(:v AS vector)) AS score FROM semantic_vectors WHERE model=:m AND record_id IN :ids ORDER BY embedding <=> CAST(:v AS vector)').bindparams(bindparam('ids', expanding=True))
                    rows = c.execute(query_sql, {'v': str(qv), 'm': self.encoder.model, 'ids': list(allowed)}).mappings()
                    for row in rows:
                        if allowed.get(row['record_id']) == row['record_version']:
                            semantic[row['record_id']] = max(semantic.get(row['record_id'], -1), float(row['score']))
                else:
                    for row in c.execute(select(embeddings).where(embeddings.c.model == self.encoder.model)).mappings():
                        if allowed.get(row['record_id']) == row['record_version']:
                            semantic[row['record_id']] = max(semantic.get(row['record_id'], -1), cosine(qv, row['values']))
        # RRF candidate fusion, followed by deterministic query coverage reranking.
        fused = Counter()
        for scores in (lexical, semantic):
            for rank, (rid, value) in enumerate(sorted(scores.items(), key=lambda x: -x[1]), 1):
                if value > 0: fused[rid] += 1/(60+rank)
        by_id = {r['id']: r for r in candidates}
        result = []
        for rid, score in fused.items():
            words = set(tokens(field_text(by_id[rid], 'central_claim_ar') + ' ' + field_text(by_id[rid], 'methodology_rule_ar')))
            coverage = len(set(query_tokens) & words)/max(1, len(set(query_tokens)))
            result.append({'record': by_id[rid], 'score': score*(1+.2*coverage), 'bm25': lexical.get(rid, 0), 'semantic': semantic.get(rid), 'reranker': 'query_coverage_v1'})
        result.sort(key=lambda r: (-r['score'], r['record']['id']))
        return {'mode': 'hybrid' if semantic else 'lexical_only_no_current_vectors', 'results': result[:limit]}
