\connect agent

CREATE TABLE users (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username text NOT NULL UNIQUE,
    password_hash text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tasks (
    task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(user_id),
    question text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN
        ('pending', 'planning', 'awaiting_confirmation', 'running', 'completed', 'failed', 'canceled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tasks_user_created_idx ON tasks (user_id, created_at DESC);
CREATE INDEX tasks_status_created_idx ON tasks (status, created_at);

CREATE TABLE events (
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

CREATE FUNCTION reject_event_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'events is append-only' USING ERRCODE = '42501';
END;
$$;
CREATE TRIGGER events_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON events
    FOR EACH STATEMENT EXECUTE FUNCTION reject_event_mutation();

CREATE TABLE query_results (
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
CREATE INDEX query_results_task_idx ON query_results (task_id, created_at);

CREATE TABLE memories (
    memory_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(user_id),
    type text NOT NULL DEFAULT 'preference',
    key text NOT NULL,
    value jsonb NOT NULL,
    source_quote text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    superseded_at timestamptz
);
CREATE INDEX memories_user_active_idx ON memories (user_id) WHERE superseded_at IS NULL;
CREATE UNIQUE INDEX memories_preference_key_idx ON memories (user_id, key)
    WHERE type = 'preference' AND superseded_at IS NULL;

GRANT SELECT, INSERT, UPDATE, DELETE ON users, tasks, memories TO agent_app;
GRANT SELECT, INSERT ON events, query_results TO agent_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agent_app;
REVOKE ALL ON FUNCTION reject_event_mutation() FROM PUBLIC;
