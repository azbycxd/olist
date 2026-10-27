-- database: agent
CREATE TABLE provider_health (
    provider text NOT NULL,
    model text NOT NULL,
    state text NOT NULL DEFAULT 'closed' CHECK (state IN ('closed','open','half_open')),
    failure_count integer NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    generation bigint NOT NULL DEFAULT 0,
    open_until timestamptz,
    probe_call_id uuid,
    probe_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(provider, model)
);
ALTER TABLE model_reservations ADD COLUMN provider text;
ALTER TABLE model_reservations ADD COLUMN model text;
ALTER TABLE model_reservations ADD COLUMN provider_generation bigint;
ALTER TABLE model_reservations ADD COLUMN health_recorded boolean NOT NULL DEFAULT false;
GRANT SELECT,INSERT,UPDATE ON provider_health TO agent_app;
