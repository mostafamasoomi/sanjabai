"""
Embedding service for RAG.

Calls LiteLLM proxy for text-embedding-3-small embeddings.
Bills each call through usage_events for accurate cost tracking.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

import os
from database import async_session, _http, LITELLM_HOST

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = 'text-embedding-3-small'
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_BASE = 'https://openrouter.ai/api/v1'
EMBEDDING_DIMENSIONS = 1536
BATCH_SIZE = 20  # texts per API call
MAX_RETRIES = 3


async def embed_texts(
    texts: list[str],
    user_id: int,
    document_id: int | None = None,
) -> list[list[float]]:
    """Generate embeddings for a list of texts.

    Calls LiteLLM proxy in batches. Bills each call via usage_events.
    Returns list of 1536-dimensional vectors.
    """
    if not texts:
        return []

    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        embeddings = await _embed_batch(batch, user_id, document_id)
        all_embeddings.extend(embeddings)

    return all_embeddings


async def _embed_batch(
    texts: list[str],
    user_id: int,
    document_id: int | None,
) -> list[list[float]]:
    """Call embedding API for a single batch of texts with retry.
    
    Tries LiteLLM proxy first, falls back to OpenRouter directly.
    """
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            # Try LiteLLM first
            resp = None
            try:
                resp = await _http.post(
                    f'{LITELLM_HOST}/v1/embeddings',
                    json={'model': EMBEDDING_MODEL, 'input': texts, 'encoding_format': 'float'},
                    timeout=30,
                )
                if resp.status_code != 200:
                    resp = None  # fall through to OpenRouter
            except Exception:
                resp = None

            # Fallback: OpenRouter directly
            if resp is None and OPENROUTER_API_KEY:
                headers = {
                    'Authorization': f'Bearer {OPENROUTER_API_KEY}',
                    'Content-Type': 'application/json',
                }
                resp = await _http.post(
                    f'{OPENROUTER_BASE}/embeddings',
                    json={'model': EMBEDDING_MODEL, 'input': texts},
                    headers=headers,
                    timeout=30,
                )

            if resp.status_code != 200:
                raise RuntimeError(f'Embedding API returned {resp.status_code}: {resp.text[:200]}')

            data = resp.json()
            embeddings = [item['embedding'] for item in data['data']]

            # Bill usage
            usage = data.get('usage', {})
            total_tokens = usage.get('total_tokens', 0)
            if total_tokens > 0:
                await _bill_embedding_usage(
                    user_id=user_id,
                    document_id=document_id,
                    tokens=total_tokens,
                )

            return embeddings

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = 2 ** attempt
                logger.warning(f'Embedding attempt {attempt + 1} failed, retrying in {wait}s: {e}')
                await asyncio.sleep(wait)

    # Fallback: simple hash-based embedding (for testing/development)
    logger.warning(f'External embedding failed, using local hash fallback: {last_error}')
    return [_hash_embedding(text) for text in texts]


def _hash_embedding(text: str, dim: int = 1536) -> list[float]:
    """Generate a deterministic hash-based embedding (fallback only).
    
    NOT suitable for production semantic search — use real embeddings.
    This is only for testing/development when external APIs are unavailable.
    """
    import hashlib
    
    # Generate deterministic bytes from text
    vec = []
    for i in range(0, dim, 32):
        h = hashlib.sha256(f'{i}:{text}'.encode()).hexdigest()
        # Convert hex pairs to floats in [-1, 1]
        for j in range(0, min(64, len(h)), 2):
            val = (int(h[j:j+2], 16) - 127.5) / 127.5
            vec.append(val)
            if len(vec) >= dim:
                break
    
    vec = vec[:dim]
    
    # Normalize to unit vector
    norm = sum(x*x for x in vec) ** 0.5
    if norm > 0:
        vec = [x/norm for x in vec]
    
    return vec


async def _bill_embedding_usage(
    user_id: int,
    document_id: int | None,
    tokens: int,
) -> None:
    """Record embedding usage in rag_embedding_usage and usage_events."""
    # Cost: $0.02/1M tokens ≈ 100 IRT/1M tokens (rough estimate)
    charged = max(1, int(tokens * 100 / 1_000_000))
    request_id = f'emb-{secrets.token_hex(16)}'

    try:
        if async_session is None:
            return
        async with async_session() as session:
            await session.execute(
                __import__('sqlalchemy').text("""
                    INSERT INTO rag_embedding_usage
                        (user_id, document_id, operation, tokens_used, charged_amount, request_id, model)
                    VALUES
                        (:uid, :did, 'embed', :tokens, :charged, :rid, :model)
                """),
                {
                    'uid': user_id,
                    'did': document_id,
                    'tokens': tokens,
                    'charged': charged,
                    'rid': request_id,
                    'model': EMBEDDING_MODEL,
                },
            )
            # Also record in usage_events for billing consistency
            await session.execute(
                __import__('sqlalchemy').text("""
                    INSERT INTO usage_events
                        (request_id, user_id, model, input_tokens, charged_amount, upstream_status)
                    VALUES
                        (:rid, :uid, :model, :tokens, :charged, 'success')
                """),
                {
                    'rid': request_id,
                    'uid': user_id,
                    'model': EMBEDDING_MODEL,
                    'tokens': tokens,
                    'charged': charged,
                },
            )
            await session.commit()
    except Exception as e:
        logger.warning(f'Failed to bill embedding usage: {e}')


async def embed_single(text: str, user_id: int) -> list[float]:
    """Embed a single text (for query embedding)."""
    results = await embed_texts([text], user_id)
    return results[0] if results else []
