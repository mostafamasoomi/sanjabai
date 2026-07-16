# RAG Architecture Analysis for Multiai Production Platform

**Date**: 2026-07-16  
**Author**: Senior Backend Engineer Review  
**Context**: Adding RAG (document search, vector search, embeddings) to a production LLM platform with paying users.

---

## 1. Platform Architecture Summary

### Current Stack
| Component | Technology | Details |
|-----------|-----------|---------|
| Web Framework | FastAPI 0.139 | Async, lifespan-managed, with middleware stack |
| Database | PostgreSQL | Via asyncpg + SQLAlchemy 2.0 async |
| Cache | Redis 8.0 | aioredis, session/token storage |
| LLM Proxy | LiteLLM | Runs on port 4000, handles all model routing |
| Billing | Wallet + Ledger | `FOR UPDATE` locks, reservations, idempotency keys |
| Multi-tenancy | `user_id` FK | Every table scoped to user_id |
| File Handling | pypdf | PDF extraction, 10MB cap, 100-page limit |
| Migration | SQL files | Idempotent runner in `migrate.py` |

### Existing Patterns to Leverage
- **Idempotency keys** on Ledger, Payments, WalletReservations — must extend to embedding/indexing operations
- **`FOR UPDATE` wallet locking** — same pattern needed for document status state machines
- **Memory injection** via `context_injection.py` — RAG retrieval is the natural successor
- **`user_id` scoping** — every RAG table must be tenant-isolated
- **UsageEvent recording** — embedding API calls must be metered/billed

---

## 2. BEST Architecture: pgvector + PostgreSQL

### Recommendation: **Use pgvector, NOT a separate vector DB**

#### Why pgvector over Qdrant/Chroma/Pinecone/Weaviate:

| Factor | pgvector | Separate DB (Qdrant/Chroma/etc.) |
|--------|----------|----------------------------------|
| **Operational Simplicity** | Zero new infrastructure. One `CREATE EXTENSION` | New service to deploy, monitor, backup, scale |
| **Consistency** | Same transaction as metadata. Atomic document+chunk+vector writes | Two-phase commit or eventual consistency nightmares |
| **Multi-tenancy** | `WHERE user_id = $1` — native, identical to rest of platform | Qdrant has collections but different model; Chroma's tenancy is awkward |
| **Billing Integration** | Ledger and usage_events in same DB — billing is transactional | External DB means async billing reconciliation |
| **Backup/DR** | pg_dump covers everything. One recovery procedure | Two separate backup pipelines |
| **Team Familiarity** | Same SQL, same ORM, same connection pool | New API, new SDK, new debugging |
| **Cost** | Free (PG extension). No additional hosting | Separate service = separate costs |
| **pgvector Performance** | HNSW index, IVFFlat, 1M+ vectors at <10ms | Qdrant is faster at 10M+ scale |

**The only reason to use Qdrant/Weaviate would be if you expect >10M document chunks within 12 months.** For a SaaS platform starting RAG, pgvector will handle 1-5M vectors easily and you can migrate later if needed.

---

## 3. Minimal Production-Grade Architecture

### 3.1 Database Schema (Migration 0013)

```sql
-- 0013_rag_core.sql
-- RAG document storage with pgvector

BEGIN;

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Documents ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rag_documents (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    file_name       TEXT,
    file_type       TEXT,               -- 'pdf', 'txt', 'md', 'csv', 'json'
    file_size       BIGINT,             -- bytes
    source          TEXT NOT NULL DEFAULT 'upload',  -- 'upload', 'url', 'paste', 'api'
    source_url      TEXT,               -- original URL if source='url'
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','processing','indexed','error','deleted')),
    error_message   TEXT,
    chunk_count     INTEGER DEFAULT 0,
    total_chars     INTEGER DEFAULT 0,
    metadata        JSONB DEFAULT '{}', -- flexible: language, author, tags, etc.
    idempotency_key TEXT UNIQUE,        -- replay protection
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_rag_docs_user ON rag_documents(user_id, status);
CREATE INDEX idx_rag_docs_user_created ON rag_documents(user_id, created_at DESC);

-- ── Chunks ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rag_chunks (
    id              BIGSERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,   -- order within document
    content         TEXT NOT NULL,
    token_count     INTEGER DEFAULT 0,  -- estimate for context window budgeting
    embedding       vector(1536),       -- OpenAI text-embedding-3-small dimension
    -- Or: vector(768) for nomic-embed-text / multilingual-e5
    embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small',
    metadata        JSONB DEFAULT '{}', -- page_number, heading, etc.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, chunk_index)
);

CREATE INDEX idx_rag_chunks_doc ON rag_chunks(document_id, chunk_index);
CREATE INDEX idx_rag_chunks_user ON rag_chunks(user_id);

-- HNSW index for fast ANN search (build after data exists)
-- Parameters: m=16 (connections per layer), ef_construction=200
-- For 1536-d vectors at <500K scale, this gives <5ms queries
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
    ON rag_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- ── Usage tracking for embedding API calls ─────────────────────
CREATE TABLE IF NOT EXISTS rag_embedding_usage (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    document_id     INTEGER REFERENCES rag_documents(id),
    operation       TEXT NOT NULL,       -- 'embed_document', 'embed_query'
    tokens_used     INTEGER NOT NULL DEFAULT 0,
    charged_amount  INTEGER NOT NULL DEFAULT 0,  -- Tomans
    currency        TEXT NOT NULL DEFAULT 'IRT',
    request_id      TEXT UNIQUE NOT NULL,
    model           TEXT NOT NULL,       -- embedding model used
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_rag_embedding_usage_user ON rag_embedding_usage(user_id, created_at);

-- ── Assistant ↔ Document association ───────────────────────────
CREATE TABLE IF NOT EXISTS rag_assistant_documents (
    id              BIGSERIAL PRIMARY KEY,
    assistant_id    INTEGER NOT NULL REFERENCES assistants(id) ON DELETE CASCADE,
    document_id     INTEGER NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(assistant_id, document_id)
);

COMMIT;
```

### 3.2 Python Dependencies (add to requirements.txt)

```
# RAG / Embeddings
openai==1.82.0              # Already likely used? If not, for embeddings API
pgvector==0.3.6             # SQLAlchemy + pgvector integration
tiktoken==0.8.0             # Token counting for chunk sizing
langchain-text-splitters==0.3.4  # Or write your own — see below
```

**Critical note**: Do NOT install the full `langchain` package. It's 500MB+ of dependencies. Use only `langchain-text-splitters` for the `RecursiveCharacterTextSplitter`, or better yet, write your own chunker (see §3.4).

### 3.3 ORM Models (add to `models.py`)

```python
from pgvector.sqlalchemy import Vector  # new import

class RagDocument(Base):
    __tablename__ = 'rag_documents'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    title: Mapped[str]
    file_name: Mapped[str | None] = mapped_column(nullable=True)
    file_type: Mapped[str | None] = mapped_column(nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(default='upload')
    source_url: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default='pending')
    error_message: Mapped[str | None] = mapped_column(nullable=True)
    chunk_count: Mapped[int] = mapped_column(default=0)
    total_chars: Mapped[int] = mapped_column(default=0)
    metadata: Mapped[dict | None] = mapped_column(sqlalchemy.JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class RagChunk(Base):
    __tablename__ = 'rag_chunks'
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('rag_documents.id'))
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'))
    chunk_index: Mapped[int]
    content: Mapped[str]
    token_count: Mapped[int] = mapped_column(default=0)
    embedding = mapped_column(Vector(1536))  # pgvector type
    embedding_model: Mapped[str] = mapped_column(default='text-embedding-3-small')
    metadata: Mapped[dict | None] = mapped_column(sqlalchemy.JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
```

### 3.4 Chunking Strategy (Write Your Own — Don't Use LangChain)

LangChain's `RecursiveCharacterTextSplitter` is 200KB of indirection for what's essentially 20 lines of Python. Here's the production-grade approach:

```python
# backend/services/chunking.py
"""Document chunking with overlap for RAG. No LangChain dependency."""

import re
from typing import List

# Approximate token count: ~4 chars per token for English, ~2 chars for Persian
# Use tiktoken for exact counts on English, char-based estimate for Persian
CHARS_PER_TOKEN_ESTIMATE = 3  # Conservative for mixed Persian/English

def chunk_text(
    text: str,
    chunk_size: int = 500,       # tokens
    chunk_overlap: int = 50,     # tokens
    separators: List[str] = None,
) -> List[dict]:
    """
    Split text into overlapping chunks. Returns list of {content, token_estimate, index}.
    
    For Persian text: chunk_size=300 tokens (shorter because Persian is more 
    token-efficient per semantic unit).
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", "? ", "! ", "، ", " ", ""]
    
    char_size = chunk_size * CHARS_PER_TOKEN_ESTIMATE
    char_overlap = chunk_overlap * CHARS_PER_TOKEN_ESTIMATE
    
    chunks = _split_recursive(text, separators, char_size, char_overlap)
    
    return [
        {
            "content": chunk.strip(),
            "token_estimate": len(chunk) // CHARS_PER_TOKEN_ESTIMATE,
            "index": i,
        }
        for i, chunk in enumerate(chunks)
        if chunk.strip()
    ]


def _split_recursive(text: str, separators: List[str], chunk_size: int, overlap: int) -> List[str]:
    """Recursively split by separators, trying each until chunk fits."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    
    sep = separators[0]
    remaining_seps = separators[1:]
    
    if sep == "":
        # Force split at character level
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - overlap
        return chunks
    
    splits = re.split(f"({re.escape(sep)})", text)
    # Rejoin sep with its preceding split
    merged = []
    i = 0
    while i < len(splits):
        if i + 1 < len(splits) and splits[i + 1] == sep:
            merged.append(splits[i] + sep)
            i += 2
        else:
            merged.append(splits[i])
            i += 1
    
    result = []
    current = ""
    for part in merged:
        if len(current) + len(part) <= chunk_size:
            current += part
        else:
            if current.strip():
                if remaining_seps:
                    result.extend(_split_recursive(current, remaining_seps, chunk_size, overlap))
                else:
                    result.append(current)
            current = part
    
    if current.strip():
        if remaining_seps and len(current) > chunk_size:
            result.extend(_split_recursive(current, remaining_seps, chunk_size, overlap))
        else:
            result.append(current)
    
    return result
```

### 3.5 Embedding Service

```python
# backend/services/embeddings.py
"""Embedding generation via OpenAI-compatible API (LiteLLM proxy)."""

import hashlib
import logging
from typing import List

from database import _http, LITELLM_HOST

logger = logging.getLogger(__name__)

# Embedding model — use OpenAI text-embedding-3-small (1536-d)
# Cost: $0.02/1M tokens. Cheap enough for RAG.
# For Persian: consider multilingual-e5-large-instruct but 3-small works well enough
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
MAX_BATCH_SIZE = 50  # OpenAI allows up to 2048 inputs but 50 is safe for timeouts


async def embed_texts(texts: List[str], model: str = EMBEDDING_MODEL) -> List[List[float]]:
    """
    Generate embeddings for a batch of texts via LiteLLM proxy.
    Returns list of embedding vectors.
    """
    if not texts:
        return []
    
    # Truncate long texts (OpenAI max tokens per input is 8191 for 3-small)
    truncated = [t[:30000] for t in texts]  # ~7500 tokens max
    
    try:
        r = await _http.post(
            f"{LITELLM_HOST}/v1/embeddings",
            json={
                "model": model,
                "input": truncated,
                "encoding_format": "float",
            },
            headers={"Accept": "application/json"},
            timeout=60,
        )
        if r.status_code != 200:
            logger.error(f"embed_texts failed: {r.status_code} {r.text[:500]}")
            raise RuntimeError(f"Embedding API error: {r.status_code}")
        
        data = r.json()
        # Sort by index to preserve order
        embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [e["embedding"] for e in embeddings]
    
    except Exception as e:
        logger.error(f"embed_texts exception: {e}")
        raise


async def embed_text(text: str, model: str = EMBEDDING_MODEL) -> List[float]:
    """Single-text convenience wrapper."""
    results = await embed_texts([text], model=model)
    return results[0]


def compute_content_hash(content: str) -> str:
    """Content hash for deduplication / idempotency."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
```

### 3.6 Retrieval Service

```python
# backend/services/retrieval.py
"""Vector search and RAG retrieval."""

import logging
from typing import List, Optional

import sqlalchemy
from sqlalchemy import text

from database import async_session
from services.embeddings import embed_text, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

MAX_RETRIEVED_CHUNKS = 10
MIN_SIMILARITY = 0.65  # Cosine similarity threshold


async def retrieve_relevant_chunks(
    user_id: int,
    query: str,
    top_k: int = 5,
    document_ids: Optional[List[int]] = None,
    similarity_threshold: float = MIN_SIMILARITY,
) -> List[dict]:
    """
    Retrieve the most relevant chunks for a query.
    
    Args:
        user_id: Tenant isolation
        query: Search query text
        top_k: Max chunks to return
        document_ids: Optional filter to specific documents (e.g., assistant-linked docs)
        similarity_threshold: Minimum cosine similarity (0-1)
    
    Returns:
        List of {content, document_title, chunk_index, similarity, document_id}
    """
    if async_session is None:
        return []
    
    # Generate query embedding
    try:
        query_embedding = await embed_text(query, model=EMBEDDING_MODEL)
    except Exception as e:
        logger.error(f"retrieve_relevant_chunks: embedding failed: {e}")
        return []
    
    embedding_str = f"[{','.join(str(v) for v in query_embedding)}]"
    
    async with async_session() as session:
        # Build query with optional document filter
        doc_filter = ""
        params = {
            "user_id": user_id,
            "embedding": embedding_str,
            "limit": top_k,
            "threshold": similarity_threshold,
        }
        
        if document_ids:
            doc_filter = "AND c.document_id = ANY(:doc_ids)"
            params["doc_ids"] = document_ids
        
        sql = text(f"""
            SELECT
                c.id,
                c.content,
                c.chunk_index,
                c.document_id,
                d.title AS document_title,
                1 - (c.embedding <=> :embedding::vector) AS similarity
            FROM rag_chunks c
            JOIN rag_documents d ON c.document_id = d.id
            WHERE c.user_id = :user_id
              AND d.status = 'indexed'
              {doc_filter}
              AND 1 - (c.embedding <=> :embedding::vector) > :threshold
            ORDER BY c.embedding <=> :embedding::vector
            LIMIT :limit
        """)
        
        try:
            result = await session.execute(sql, params)
            rows = result.fetchall()
        except Exception as e:
            logger.error(f"retrieve_relevant_chunks: query failed: {e}")
            return []
        
        return [
            {
                "content": row.content,
                "document_title": row.document_title,
                "chunk_index": row.chunk_index,
                "document_id": row.document_id,
                "similarity": round(float(row.similarity), 4),
            }
            for row in rows
        ]


def format_rag_context(chunks: List[dict], max_chars: int = 6000) -> str:
    """
    Format retrieved chunks into a context string for injection into LLM prompt.
    Includes document source attribution.
    """
    if not chunks:
        return ""
    
    lines = ["[Retrieved Documents — use this information to answer the user's question]\n"]
    total_chars = 0
    
    for i, chunk in enumerate(chunks, 1):
        source = f"[{chunk['document_title']}]"
        prefix = f"--- Source {i}: {source} (relevance: {chunk['similarity']:.0%}) ---\n"
        content = chunk["content"].strip()
        
        if total_chars + len(prefix) + len(content) > max_chars:
            # Truncate last chunk to fit
            remaining = max_chars - total_chars - len(prefix)
            if remaining > 200:
                lines.append(prefix + content[:remaining] + "...")
            break
        
        lines.append(prefix + content + "\n")
        total_chars += len(prefix) + len(content) + 1
    
    lines.append("--- End of Retrieved Documents ---")
    return "\n".join(lines)
```

### 3.7 Integration with Chat Pipeline

The key integration point is in `chat.py`. After memory/soul injection but before sending to LiteLLM, inject RAG context:

```python
# In /v1/chat/completions endpoint, after line 448 (memory injection):

# RAG injection — if assistant has linked documents
if _assistant_id:
    try:
        # Find user's last message as query
        user_query = ''
        _msgs = payload_dict.get('messages', [])
        for _m in reversed(_msgs):
            if isinstance(_m, dict) and _m.get('role') == 'user':
                user_query = _m.get('content', '')
                break
        
        if user_query:
            from services.retrieval import retrieve_relevant_chunks, format_rag_context
            
            # Get document IDs linked to this assistant
            async with async_session() as _asession:
                _doc_res = await _asession.execute(
                    sqlalchemy.text(
                        "SELECT document_id FROM rag_assistant_documents "
                        "WHERE assistant_id = :aid AND user_id = :uid AND enabled = true"
                    ),
                    {"aid": int(_assistant_id), "uid": uid},
                )
                _doc_ids = [r[0] for r in _doc_res.fetchall()]
            
            if _doc_ids:
                rag_chunks = await retrieve_relevant_chunks(
                    user_id=uid,
                    query=user_query,
                    document_ids=_doc_ids,
                    top_k=5,
                )
                if rag_chunks:
                    rag_context = format_rag_context(rag_chunks)
                    _sys_msg = {'role': 'system', 'content': rag_context}
                    _msgs = payload_dict.get('messages', [])
                    _msgs.insert(0, _sys_msg)
                    payload_dict['messages'] = _msgs
    except Exception as e:
        logger.warning(f"chat RAG injection failed uid={uid} aid={_assistant_id}: {e}")
```

### 3.8 Document Upload & Indexing Pipeline

```python
# backend/rag.py (new file — RAG endpoints)
"""
RAG document management endpoints: upload, index, search, delete.
"""

from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

# POST /rag/documents — upload a document
# GET  /rag/documents — list user's documents
# GET  /rag/documents/{id} — document details
# DELETE /rag/documents/{id} — soft-delete
# POST /rag/documents/{id}/reindex — re-index after status change
# POST /rag/search — direct search (bypass assistant)

# Indexing flow:
# 1. Upload → extract text (use existing _extract_file_text from chat.py)
# 2. Store document row with status='pending'
# 3. Chunk (chunking.chunk_text) 
# 4. Embed chunks in batches of 50 (embeddings.embed_texts)
# 5. Insert chunks + embeddings into rag_chunks
# 6. Update document status='indexed', chunk_count
# 7. Record embedding usage in rag_embedding_usage
# 8. Deduct from wallet (embedding calls cost money)
```

---

## 4. Common Pitfalls in Payment/Financial RAG Platforms

### 4.1 PITFALL: Embedding Costs Are Invisible
**Problem**: Embedding API calls are billed but often untracked. A user uploads 100 PDFs → 10,000 chunks → 10,000 embedding calls → significant cost.
**Fix**: 
- Bill embedding calls through the same `usage_events` pipeline
- Show "embedding usage" in the analytics endpoint
- Set per-user document limits (e.g., max 50 docs, 100MB total)
- Estimate cost upfront before indexing: `(estimated_chunks * embedding_cost_per_call)`

### 4.2 PITFALL: Stale Embeddings After Document Update
**Problem**: User uploads v1, then uploads v2. Old chunks still in DB polluting search results.
**Fix**:
- Documents are immutable in the vector store
- On "update", delete old chunks + embeddings, re-index new content
- Use `status='deleted'` for soft-delete, cascade to chunks
- Add `idempotency_key` to prevent duplicate indexing

### 4.3 PITFALL: Vector Search Without Tenant Isolation
**Problem**: `ORDER BY embedding <=> query_vector LIMIT 5` without `WHERE user_id = $1` returns other users' data.
**Fix**: Every query MUST include `WHERE user_id = $1`. Add an integration test that verifies cross-tenant isolation.

### 4.4 PITFALL: Token Budget Exhaustion
**Problem**: RAG chunks + system prompt + conversation history + user query exceeds model context window.
**Fix**:
- `format_rag_context()` already has `max_chars` parameter
- Dynamically compute: `context_window - (system_prompt_tokens + conversation_tokens + 500)`
- Truncate chunks to fit
- Use `tiktoken` for accurate token counting

### 4.5 PITFALL: Embedding Model Drift
**Problem**: You change from `text-embedding-3-small` (1536-d) to `text-embedding-3-large` (3072-d). All existing vectors are wrong dimension.
**Fix**:
- Store `embedding_model` per chunk
- Write migration that adds new column for new dimension
- Re-index is a background job flagged by `status='pending_reindex'`

### 4.6 PITFALL: Rate Limiting on Embedding API
**Problem**: OpenAI rate-limits embedding calls. Batch of 500 chunks can hit limits.
**Fix**:
- Batch with MAX_BATCH_SIZE=50
- Add exponential backoff with jitter
- Use Redis to track rate limits per user

### 4.7 PITFALL: Persian/Farsi Text Quality
**Problem**: Most embedding models are trained on English. Persian semantic search may suck.
**Fix**:
- Test with `text-embedding-3-small` (OpenAI) — it claims multilingual support
- Fallback: `intfloat/multilingual-e5-large-instruct` via LiteLLM
- Add a `language` field to `rag_documents.metadata`
- Consider hybrid search: vector + BM25 keyword fallback for Persian

### 4.8 PITFALL: Large PDFs Blocking the Request Loop
**Problem**: Indexing a 100-page PDF takes 30+ seconds, blocking the HTTP request.
**Fix**:
- Return immediately with `status='processing'`
- Index in a background task (`asyncio.create_task` or proper task queue)
- Polling endpoint: `GET /rag/documents/{id}/status`
- WebSocket notification when indexing completes

### 4.9 PITFALL: Duplicate Content = Duplicate Vectors
**Problem**: User uploads same document twice → identical chunks → redundant search results.
**Fix**:
- Compute content hash on document text
- `idempotency_key` based on `hash(user_id + content_hash)`
- Deduplicate chunks by content hash before embedding

---

## 5. Multi-Tenant Document Chunk Management

### 5.1 Tenant Isolation Strategy

Every table has `user_id` as a mandatory FK. This is already the platform pattern. Key rules:

```sql
-- Every query MUST include:
WHERE user_id = :current_user_id

-- Every index should include user_id as leading column:
CREATE INDEX idx_rag_chunks_user_embedding ON rag_chunks 
    USING hnsw (embedding vector_cosine_ops) 
    WHERE user_id = :uid;  -- partial index per tenant

-- But pgvector HNSW doesn't support partial indexes well.
-- Instead, use the WHERE clause in queries and rely on:
CREATE INDEX idx_rag_chunks_user ON rag_chunks(user_id);
-- PostgreSQL will bitmap-scan both indexes.
```

### 5.2 Per-Tenant Limits

```python
# In rag.py endpoints:
MAX_DOCUMENTS_PER_USER = 50
MAX_DOCUMENT_SIZE_MB = 20
MAX_TOTAL_STORAGE_MB = 200  # Sum of file_size across all documents
MAX_CHUNKS_PER_DOCUMENT = 500

# Check limits before accepting upload:
async def _check_rag_limits(user_id: int) -> str | None:
    """Return error message if limits exceeded, None if OK."""
    async with async_session() as session:
        # Count documents
        count_res = await session.execute(
            text("SELECT COUNT(*) FROM rag_documents WHERE user_id = :uid AND status != 'deleted'"),
            {"uid": user_id},
        )
        doc_count = count_res.scalar()
        if doc_count >= MAX_DOCUMENTS_PER_USER:
            return f"حداکثر {MAX_DOCUMENTS_PER_USER} سند مجاز است"
        
        # Total storage
        size_res = await session.execute(
            text("SELECT COALESCE(SUM(file_size), 0) FROM rag_documents WHERE user_id = :uid AND status != 'deleted'"),
            {"uid": user_id},
        )
        total_mb = size_res.scalar() / (1024 * 1024)
        if total_mb >= MAX_TOTAL_STORAGE_MB:
            return f"حداکثر فضای مجاز {MAX_TOTAL_STORAGE_MB} مگابایت است"
    
    return None
```

### 5.3 Chunk Lifecycle State Machine

```
upload → pending → processing → indexed
                    ↓
                  error → (retry) → processing
                    
indexed → deleted (soft-delete, chunks preserved for audit)
deleted → (cascade cleanup after 30 days via cron)
```

### 5.4 Cleanup Cron Job

```python
# In lifespan() or a scheduled task:
async def _rag_cleanup_loop():
    """Delete soft-deleted documents older than 30 days."""
    while True:
        try:
            async with async_session() as session:
                await session.execute(text("""
                    DELETE FROM rag_documents 
                    WHERE status = 'deleted' 
                      AND updated_at < NOW() - INTERVAL '30 days'
                """))
                await session.commit()
        except Exception as e:
            logger.warning(f"rag_cleanup error: {e}")
        await asyncio.sleep(86400)  # Daily
```

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Week 1)
1. Migration 0013: `rag_documents`, `rag_chunks`, `rag_embedding_usage`, `rag_assistant_documents`
2. `pgvector` extension + `pgvector` Python package
3. `services/chunking.py` — text splitter
4. `services/embeddings.py` — embedding API client
5. `services/retrieval.py` — vector search + context formatting

### Phase 2: Upload & Index (Week 2)
6. `rag.py` endpoints: upload, list, get, delete documents
7. Background indexing with status polling
8. Idempotency key + content hash deduplication
9. Per-tenant limits enforcement
10. Embedding usage tracking + billing

### Phase 3: Chat Integration (Week 3)
11. RAG injection in `chat.py` (assistant-linked documents)
12. Direct `/rag/search` endpoint
13. Assistant ↔ document linking UI backend
14. Integration tests for cross-tenant isolation

### Phase 4: Polish (Week 4)
15. WebSocket notifications for indexing completion
16. Analytics: RAG usage stats in `/conversations/analytics`
17. Admin endpoints for document management
18. Re-index endpoint for embedding model migration
19. Cleanup cron for soft-deleted documents

---

## 7. Cost Estimate

| Item | Cost Driver | Estimate |
|------|------------|----------|
| `text-embedding-3-small` | $0.02/1M tokens | ~$0.0001 per page |
| PostgreSQL storage | 1536 × 4 bytes = 6KB per chunk | 10K chunks = 60MB |
| HNSW index overhead | ~2x vector storage | 10K chunks = 120MB total |
| Additional PG memory | HNSW build needs `maintenance_work_mem` | Set to 256MB during index build |

**For 100 users × 50 documents × 100 chunks each = 500K chunks**: ~30MB vectors, ~$5 embedding cost.

---

## 8. Key Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector DB | **pgvector** | Same DB, transactional, no new infra |
| Embedding model | **text-embedding-3-small** (1536-d) | Cheap, multilingual, via LiteLLM |
| Chunking | **Custom** (no LangChain) | 20 lines, zero bloat, full control |
| Multi-tenancy | **user_id FK on every table** | Existing platform pattern |
| Indexing | **Background async** | Non-blocking HTTP, status polling |
| Billing | **Same usage_events pipeline** | Unified billing, existing wallet system |
| Search | **Cosine similarity + threshold** | HNSW index, <5ms queries |
| Persian support | **Test with 3-small first** | Fallback to multilingual-e5 if needed |

---

*End of analysis. This document should be reviewed by the team before any implementation begins.*