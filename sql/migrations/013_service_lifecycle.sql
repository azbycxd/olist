-- database: agent
ALTER TABLE tasks ADD COLUMN released_count integer NOT NULL DEFAULT 0
    CHECK (released_count >= 0 AND released_count <= claim_count);
CREATE TABLE worker_heartbeats (
    worker_id text PRIMARY KEY,
    last_seen timestamptz NOT NULL DEFAULT clock_timestamp(),
    status text NOT NULL CHECK (status IN ('ready','draining','stopped'))
);
GRANT SELECT,INSERT,UPDATE ON worker_heartbeats TO agent_app;
