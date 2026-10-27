-- database: agent
-- W3C trace flags include bits beyond sampled (e.g. SDK random-trace-id flag).
ALTER TABLE tasks DROP CONSTRAINT tasks_traceparent_format;
ALTER TABLE tasks ADD CONSTRAINT tasks_traceparent_format CHECK (
    traceparent IS NULL OR traceparent ~ '^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$');
