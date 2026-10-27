-- database: agent
ALTER TABLE tasks ADD COLUMN provider_requeues integer NOT NULL DEFAULT 0
    CHECK (provider_requeues >= 0 AND provider_requeues + released_count <= claim_count);
