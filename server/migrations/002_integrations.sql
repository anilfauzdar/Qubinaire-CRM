-- Apply once to an existing Qubinaire PostgreSQL database.
ALTER TABLE devices ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id);
ALTER TABLE sync_changes ALTER COLUMN device_id DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_devices_user_id ON devices(user_id);
-- Old device registrations cannot be safely attributed; disable them and re-register.
UPDATE devices SET active=FALSE WHERE user_id IS NULL;
CREATE TABLE IF NOT EXISTS lead_hunter_runs (
 id BIGSERIAL PRIMARY KEY, requested_by BIGINT NOT NULL REFERENCES users(id),
 query TEXT NOT NULL, provider TEXT NOT NULL, results_count INTEGER NOT NULL DEFAULT 0,
 imported_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, details JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS lead_hunter_candidates (
 id BIGSERIAL PRIMARY KEY, run_id BIGINT REFERENCES lead_hunter_runs(id),
 source_url TEXT NOT NULL UNIQUE, title TEXT NOT NULL, description TEXT,
 status TEXT NOT NULL DEFAULT 'new', lead_id VARCHAR(100) REFERENCES leads(id),
 created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lead_hunter_candidates_status ON lead_hunter_candidates(status,created_at DESC);
