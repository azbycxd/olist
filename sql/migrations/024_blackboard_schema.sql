-- database: agent
-- Preexisting boards lack an explicit contract and must be replanned.
ALTER TABLE task_state ADD COLUMN schema_version integer NOT NULL DEFAULT 0;
ALTER TABLE task_state ALTER COLUMN schema_version SET DEFAULT 1;
