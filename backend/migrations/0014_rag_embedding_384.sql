-- 0014: Switch RAG embedding dimension to 384 for the local
-- sentence-transformers model (paraphrase-multilingual-MiniLM-L12-v2),
-- which is now the PRIMARY embedding method (supports Persian + English).
--
-- The previous column was vector(1536) for the OpenAI-style API embeddings.
-- Existing rows hold non-semantic hash fallback vectors (the external APIs
-- were blocked from Iran), so they are cleared before resizing the column.
BEGIN;

-- Clear stale chunks that were stored with the old 1536-dim vectors.
-- Their parent documents are reset to 'pending' so they can be re-indexed
-- with the new 384-dim local model on next upload/query cycle.
DELETE FROM rag_chunks;

UPDATE rag_documents
SET status = 'pending', chunk_count = 0, total_chars = 0, error_message = NULL
WHERE status = 'indexed';

-- Resize the embedding column to 384. Postgres automatically rebuilds the
-- HNSW index (idx_rag_chunks_embedding) for the new vector type.
ALTER TABLE rag_chunks
    ALTER COLUMN embedding TYPE vector(384);

-- Update the column default for embedding_model to the local model name.
ALTER TABLE rag_chunks
    ALTER COLUMN embedding_model
    SET DEFAULT 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2';

COMMIT;
