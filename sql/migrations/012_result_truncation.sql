-- database: agent
-- Historical capped results cannot be retrospectively classified; NULL = unknown.
ALTER TABLE query_results ADD COLUMN truncated boolean;
