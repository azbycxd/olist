-- database: agent

CREATE TABLE task_state (
    task_id uuid PRIMARY KEY REFERENCES tasks(task_id),
    plan jsonb NOT NULL CHECK(jsonb_typeof(plan)='object'),
    subtasks jsonb NOT NULL CHECK(jsonb_typeof(subtasks)='object'),
    report jsonb CHECK(report IS NULL OR jsonb_typeof(report)='object'),
    updated_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT,INSERT,UPDATE ON task_state TO agent_app;
