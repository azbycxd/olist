-- database: agent
CREATE TABLE rate_buckets (
    provider text PRIMARY KEY,
    rpm_capacity double precision NOT NULL CHECK (rpm_capacity >= 0),
    tpm_capacity double precision NOT NULL CHECK (tpm_capacity >= 0),
    rpm_tokens double precision NOT NULL,
    tpm_tokens double precision NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    inflight integer NOT NULL DEFAULT 0 CHECK (inflight >= 0)
);
CREATE TABLE rate_leases (
    call_id uuid PRIMARY KEY,
    provider text NOT NULL REFERENCES rate_buckets(provider),
    expires_at timestamptz NOT NULL
);
CREATE INDEX rate_leases_expiry_idx ON rate_leases(provider,expires_at);
ALTER TABLE model_reservations ADD COLUMN rate_held boolean NOT NULL DEFAULT false;
GRANT SELECT,INSERT,UPDATE ON rate_buckets TO agent_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON rate_leases TO agent_app;
