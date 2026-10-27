-- database: agent
CREATE TABLE tool_calls (
    key text PRIMARY KEY,
    task_id uuid NOT NULL REFERENCES tasks(task_id),
    request_hash text NOT NULL,
    status text NOT NULL CHECK(status IN ('running','done')),
    owner_token uuid NOT NULL,
    result_id uuid REFERENCES query_results(result_id),
    response jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX tool_calls_task_idx ON tool_calls(task_id);
ALTER TABLE query_results ADD COLUMN sql_hash text;
ALTER TABLE query_results ADD COLUMN tool_response jsonb;
CREATE UNIQUE INDEX query_results_content_key ON query_results(task_id,sql_hash,data_version) WHERE sql_hash IS NOT NULL;
GRANT SELECT,INSERT,UPDATE,DELETE ON tool_calls TO agent_app;
