-- database: agent

CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE knowledge_chunks (
    chunk_id text PRIMARY KEY,
    source text NOT NULL,
    content text NOT NULL,
    content_sha256 text NOT NULL,
    embedding vector NOT NULL,
    embedding_model text NOT NULL,
    dimensions integer NOT NULL CHECK(dimensions>0),
    indexed_at timestamptz NOT NULL DEFAULT now(),
    CHECK(vector_dims(embedding)=dimensions)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_chunks TO agent_app;
