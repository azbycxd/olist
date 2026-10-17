-- database: agent

-- Old vectors have no verified revision recorded in the table. Keep that fact
-- explicit and require a rebuild; never backfill an inferred model revision.
ALTER TABLE knowledge_chunks ADD COLUMN embedding_revision text NOT NULL DEFAULT 'unrecorded';
ALTER TABLE knowledge_chunks ALTER COLUMN embedding_revision DROP DEFAULT;
