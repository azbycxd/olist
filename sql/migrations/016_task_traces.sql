-- database: agent
ALTER TABLE tasks ADD COLUMN traceparent text;
ALTER TABLE tasks ADD CONSTRAINT tasks_traceparent_format CHECK (
    traceparent IS NULL OR traceparent ~ '^00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]$');
CREATE INDEX events_type_created_idx ON events(type,created_at);
