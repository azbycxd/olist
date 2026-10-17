-- database: agent
ALTER TABLE memories ADD CONSTRAINT memories_type_check CHECK (type IN ('preference','finding'));
ALTER TABLE memories ADD COLUMN evidence jsonb;
ALTER TABLE memories ADD COLUMN data_version text;
ALTER TABLE memories ADD COLUMN embedding vector;
ALTER TABLE memories ADD COLUMN embedding_model text;
ALTER TABLE memories ADD COLUMN embedding_revision text;
ALTER TABLE memories ADD COLUMN source_task_id uuid REFERENCES tasks(task_id);
ALTER TABLE memories ADD CONSTRAINT finding_required_fields CHECK (type <> 'finding' OR
    (evidence IS NOT NULL AND jsonb_typeof(evidence)='array' AND jsonb_array_length(evidence)>0
     AND data_version IS NOT NULL AND embedding IS NOT NULL AND embedding_model IS NOT NULL
     AND embedding_revision IS NOT NULL AND source_task_id IS NOT NULL));
CREATE UNIQUE INDEX memories_finding_key_idx ON memories(user_id,key) WHERE type='finding' AND superseded_at IS NULL;
ALTER TABLE query_results ADD COLUMN source_result_id uuid REFERENCES query_results(result_id);
