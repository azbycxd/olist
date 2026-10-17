-- database: agent
ALTER TABLE tasks ADD COLUMN cancel_requested_at timestamptz;
ALTER TABLE tasks ADD COLUMN deadline_at timestamptz;

CREATE TABLE user_token_days (
    user_id uuid NOT NULL REFERENCES users(user_id),
    usage_day date NOT NULL,
    used_tokens bigint NOT NULL DEFAULT 0 CHECK (used_tokens>=0),
    held_tokens bigint NOT NULL DEFAULT 0 CHECK (held_tokens>=0),
    PRIMARY KEY(user_id,usage_day)
);
CREATE TABLE model_reservations (
    call_id uuid PRIMARY KEY,
    task_id uuid NOT NULL REFERENCES tasks(task_id),
    user_id uuid NOT NULL REFERENCES users(user_id),
    usage_day date NOT NULL,
    reserved_tokens bigint NOT NULL CHECK (reserved_tokens>0),
    actual_tokens bigint CHECK (actual_tokens>=0),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','settled','unknown')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX model_reservations_task_idx ON model_reservations(task_id);
CREATE INDEX tasks_deadline_idx ON tasks(deadline_at) WHERE background AND status IN ('pending','planning','running','awaiting_confirmation');
GRANT SELECT,INSERT,UPDATE ON user_token_days,model_reservations TO agent_app;
