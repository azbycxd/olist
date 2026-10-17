-- database: agent
ALTER TABLE tasks ADD COLUMN background boolean NOT NULL DEFAULT false;
ALTER TABLE tasks ADD COLUMN confirmed_at timestamptz;
ALTER TABLE tasks ADD COLUMN lease_token uuid;
ALTER TABLE tasks ADD COLUMN lease_expires_at timestamptz;
ALTER TABLE tasks ADD COLUMN heartbeat_at timestamptz;
ALTER TABLE tasks ADD COLUMN claim_count integer NOT NULL DEFAULT 0 CHECK(claim_count>=0);
ALTER TABLE tasks ADD COLUMN result jsonb;
ALTER TABLE tasks ADD COLUMN error text;
ALTER TABLE tasks ADD COLUMN run_config jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX tasks_background_claim_idx ON tasks(created_at) WHERE background AND status IN ('pending','planning','running');
