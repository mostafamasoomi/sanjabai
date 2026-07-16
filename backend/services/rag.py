"""
RAG query service — semantic search over user documents.

Generates query embedding, finds similar chunks via pgvector cosine
similarity, then calls LLM with grounded context.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy
from sqlalchemy import select

from database import async_session, _http, LITELLM_HOST
from models import RagDocument, RagChunk
from services.embeddings import embed_single

logger = logging.getLogger(__name__)

MIN_SIMILARITY = 0.0  # Lowered for hash-based embedding fallback
DEFAULT_TOP_K = 5


async def query_documents(
    user_id: int,
    question: str,
    document_id: int | None = None,
    top_k: int = DEFAULT_TOP_K,
    model: str = 'tencent-hy3',
) -> dict:
    """Query user's documents with RAG.

    1. Generate embedding for question
    2. Find similar chunks via pgvector cosine distance
    3. Build context from top chunks
    4. Call LLM with grounded prompt
    5. Return answer + source citations

    Returns: {"answer": str, "sources": [{"chunk_text": str, "filename": str, "similarity": float}]}
    """
    if not question or not question.strip():
        return {'answer': 'لطفاً سوال خود را وارد کنید.', 'sources': []}

    if async_session is None:
        return {'answer': 'پایگاه داده در دسترس نیست.', 'sources': []}

    # 1. Generate query embedding
    try:
        query_embedding = await embed_single(question, user_id)
    except Exception as e:
        logger.error(f'Query embedding failed uid={user_id}: {e}')
        return {'answer': 'خطا در پردازش سوال. لطفاً دوباره تلاش کنید.', 'sources': []}

    if not query_embedding:
        return {'answer': 'خطا در تولید بردار جستجو.', 'sources': []}

    # 2. Search for similar chunks using pgvector cosine similarity
    embedding_str = '[' + ','.join(str(f) for f in query_embedding) + ']'

    try:
        async with async_session() as session:
            # Build query with optional document_id filter
            doc_filter = ''
            params: dict[str, Any] = {
                'uid': user_id,
                'emb': embedding_str,
                'top_k': top_k,
            }
            if document_id:
                doc_filter = 'AND rc.document_id = :doc_id'
                params['doc_id'] = document_id

            res = await session.execute(sqlalchemy.text(f"""
                SELECT rc.content, rc.chunk_index, rd.title, rd.file_name,
                       1 - (rc.embedding <=> :emb\:\:vector) AS similarity
                FROM rag_chunks rc
                JOIN rag_documents rd ON rc.document_id = rd.id
                WHERE rc.user_id = :uid
                  {doc_filter}
                  AND rd.status = 'indexed'
                ORDER BY rc.embedding <=> :emb\:\:vector
                LIMIT :top_k
            """), params)

            rows = res.fetchall()
    except Exception as e:
        logger.error(f'Vector search failed uid={user_id}: {e}')
        return {'answer': 'خطا در جستجوی اسناد.', 'sources': []}

    if not rows:
        return {
            'answer': 'محتوای مرتبطی در اسناد شما پیدا نشد.',
            'sources': [],
        }

    # Filter by minimum similarity
    relevant = [r for r in rows if float(r._mapping['similarity']) >= MIN_SIMILARITY]

    if not relevant:
        return {
            'answer': 'محتوای مرتبطی با سوال شما در اسناد پیدا نشد. لطفاً سوال خود را دقیق‌تر مطرح کنید.',
            'sources': [],
        }

    # 3. Build context
    context_parts = []
    sources = []
    for r in relevant:
        filename = r._mapping['file_name'] or r._mapping['title'] or 'unknown'
        context_parts.append(
            f"Document: {filename}\nChunk {r._mapping['chunk_index']}:\n{r._mapping['content']}\n---"
        )
        sources.append({
            'chunk_text': r._mapping['content'][:300] + ('...' if len(r._mapping['content']) > 300 else ''),
            'filename': filename,
            'similarity': round(float(r._mapping['similarity']), 3),
        })

    context = '\n'.join(context_parts)

    # 4. Call LLM with grounded prompt
    system_prompt = (
        "Answer the user's question based ONLY on the following document excerpts. "
        "If the documents don't contain the answer, say so clearly. "
        "Always cite which document you're referencing.\n\n"
        f"Documents:\n{context}"
    )

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': question},
    ]

    try:
        resp = await _http.post(
            f'{LITELLM_HOST}/v1/chat/completions',
            json={
                'model': model,
                'messages': messages,
                'temperature': 0.3,
                'max_tokens': 2000,
            },
            timeout=30,
        )

        if resp.status_code == 200:
            data = resp.json()
            answer = data['choices'][0]['message']['content']
        else:
            logger.error(f'LLM call failed: {resp.status_code} {resp.text[:200]}')
            answer = 'خطا در تولید پاسخ. لطفاً دوباره تلاش کنید.'

    except Exception as e:
        logger.error(f'LLM call error: {e}')
        answer = 'خطا در ارتباط با سرویس هوش مصنوعی.'

    return {'answer': answer, 'sources': sources}
