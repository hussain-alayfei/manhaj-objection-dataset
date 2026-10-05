-- 20261005065946: performance indexes.
-- Indexes for queries the app actually runs; drop ones nothing reads but every write maintains.
-- objection_claims rows are deleted by objection_id on every objection write (foreign key had no index).
CREATE INDEX IF NOT EXISTS objection_claims_objection ON objection_claims(objection_id);
-- embedding refresh and semantic search filter by model first.
CREATE INDEX IF NOT EXISTS embeddings_model_record ON embeddings(model, record_id);
CREATE INDEX IF NOT EXISTS semantic_vectors_model_record ON semantic_vectors(model, record_id);
-- duplicate of the UNIQUE (record_id, version) index on the fastest-growing table.
DROP INDEX IF EXISTS record_versions_lookup;
-- full-text indexes no query uses (search runs over a cached, normalized list instead).
DROP INDEX IF EXISTS objections_keywords;
DROP INDEX IF EXISTS methodology_rules_keywords;
DROP INDEX IF EXISTS objection_families_keywords;
