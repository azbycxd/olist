-- database: agent

CREATE TABLE IF NOT EXISTS users (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username text NOT NULL UNIQUE,
    password_hash text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(user_id),
    question text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN
        ('pending', 'planning', 'awaiting_confirmation', 'running', 'completed', 'failed', 'canceled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tasks_user_created_idx ON tasks (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS tasks_status_created_idx ON tasks (status, created_at);

CREATE TABLE IF NOT EXISTS events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id uuid NOT NULL REFERENCES tasks(task_id),
    seq integer NOT NULL CHECK (seq > 0),
    type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    tokens integer NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    latency_ms double precision NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (task_id, seq)
);

CREATE OR REPLACE FUNCTION reject_event_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'events is append-only' USING ERRCODE = '42501';
END;
$$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = 'events'::regclass AND tgname = 'events_append_only') THEN
        CREATE TRIGGER events_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON events
            FOR EACH STATEMENT EXECUTE FUNCTION reject_event_mutation();
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS query_results (
    result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id uuid NOT NULL REFERENCES tasks(task_id),
    sql text NOT NULL,
    columns jsonb NOT NULL DEFAULT '[]'::jsonb,
    rows jsonb NOT NULL CHECK (jsonb_typeof(rows) = 'array'),
    row_count integer NOT NULL CHECK (row_count >= 0),
    data_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_array_length(rows) = row_count)
);
CREATE INDEX IF NOT EXISTS query_results_task_idx ON query_results (task_id, created_at);

CREATE TABLE IF NOT EXISTS memories (
    memory_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(user_id),
    type text NOT NULL DEFAULT 'preference',
    key text NOT NULL,
    value jsonb NOT NULL,
    source_quote text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    superseded_at timestamptz
);
CREATE INDEX IF NOT EXISTS memories_user_active_idx ON memories (user_id) WHERE superseded_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS memories_preference_key_idx ON memories (user_id, key)
    WHERE type = 'preference' AND superseded_at IS NULL;

GRANT SELECT, INSERT, UPDATE, DELETE ON users, tasks, memories TO agent_app;
GRANT SELECT, INSERT ON events, query_results TO agent_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agent_app;
REVOKE ALL ON FUNCTION reject_event_mutation() FROM PUBLIC;
