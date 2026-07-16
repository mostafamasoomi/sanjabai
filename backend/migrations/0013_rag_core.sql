-- 0013: RAG core tables + pgvector extension
BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    file_name       TEXT,
    file_type       TEXT,
    file_size       BIGINT,
    source          TEXT NOT NULL DEFAULT 'upload',
    source_url      TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','processing','indexed','error','deleted')),
    error_message   TEXT,
    chunk_count     INTEGER DEFAULT 0,
    total_chars     INTEGER DEFAULT 0,
    content_hash    TEXT,
    metadata        JSONB DEFAULT '{}',
    idempotency_key TEXT UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rag_docs_user ON rag_documents(user_id, status);
CREATE INDEX IF NOT EXISTS idx_rag_docs_user_created ON rag_documents(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS rag_chunks (
    id              BIGSERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    token_count     INTEGER DEFAULT 0,
    embedding       vector(1536),
    embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks(document_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_user ON rag_chunks(user_id);

-- HNSW index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
    ON rag_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

CREATE TABLE IF NOT EXISTS rag_embedding_usage (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    document_id     INTEGER REFERENCES rag_documents(id),
    operation       TEXT NOT NULL,
    tokens_used     INTEGER NOT NULL DEFAULT 0,
    charged_amount  INTEGER NOT NULL DEFAULT 0,
    currency        TEXT NOT NULL DEFAULT 'IRT',
    request_id      TEXT UNIQUE NOT NULL,
    model           TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
