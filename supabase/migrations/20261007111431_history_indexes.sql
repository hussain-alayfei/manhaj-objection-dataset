-- 20261007111431: indexes for a reader's history and activity.
-- The «حلّل شبهة» list and the profile counts filter analyses by their owner and sort them by date; without an index
-- every load parsed every analysis of every user (each 50 to 200 KB of JSON). Postgres matches these expression
-- indexes to the app's queries because the JSON keys reach the planner as constants (unnamed statements).
CREATE INDEX IF NOT EXISTS diagnoses_owner_created ON diagnoses ((payload->>'requested_by'), (payload->>'created_at') DESC);
-- the profile's review count scans reviews by reviewer.
CREATE INDEX IF NOT EXISTS reviews_reviewer ON reviews(reviewer_id);
