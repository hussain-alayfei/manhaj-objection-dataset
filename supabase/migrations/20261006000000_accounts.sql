-- 20261006000000: reviewer accounts (name, email, password) with server-side sessions,
-- plus a small events table used for sign-in throttling and usage limits.
-- Times are Unix seconds. Passwords are scrypt hashes; only SHA-256 digests of session tokens are stored.

CREATE TABLE accounts (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    payload JSON NOT NULL
);

CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    created_at BIGINT NOT NULL,
    expires_at BIGINT NOT NULL,
    revoked_at BIGINT
);
CREATE INDEX sessions_account ON sessions(account_id);

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    at BIGINT NOT NULL
);
CREATE INDEX events_lookup ON events(kind, key, at);
CREATE INDEX events_kind_at ON events(kind, at);

-- Same lockdown as every other table: the app connects as the owner; the Data API roles get nothing.
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON accounts, sessions, events FROM anon, authenticated;
  END IF;
END $$;
