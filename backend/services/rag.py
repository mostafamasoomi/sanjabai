"""
RAG query service — semantic search over user documents.

Generates query embedding, finds similar chunks via pgvector cosine
similarity, then calls LLM with grounded context.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import sqlalchemy
from sqlalchemy import select

from database import async_session, _http, LITELLM_HOST
from models import RagDocument, RagChunk
from services.embeddings import embed_single, _hash_embedding
from services.chunking import CHARS_PER_TOKEN, estimate_tokens

logger = logging.getLogger(__name__)

# Hash embeddings can only produce exact-match collisions, so similarity of a
# non-matching chunk is effectively < 0; keep the floor at 0 in hash mode.
MIN_SIMILARITY_HASH = -1.0    # accept all results for hash-based embeddings (similarity ~0)
# Real (semantic) embeddings should clear this to drop irrelevant chunks.
MIN_SIMILARITY_SEMANTIC = 0.5

DEFAULT_TOP_K = 8          # over-fetch for re-ranking
RERANK_K = 5               # final chunks sent to the LLM
MAX_CONTEXT_TOKENS = 4000  # truncate context to avoid overwhelming the model
DEFAULT_RAG_MODEL = 'mimo-v2.5'
# Fallback chain when the requested model is rate-limited / unavailable.
LLM_FALLBACK_MODELS = (
    'mimo-v2.5',
    'kwaipilot/kat-coder-air-v2.5',
    'deepseek-v4-pro',
    'tencent-hy3',
)

# Persian Unicode ranges used for language detection.
_PERSIAN_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]')


def _is_persian(text: str) -> bool:
    """Detect whether a query is predominantly Persian."""
    if not text:
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    persian = sum(1 for c in letters if _PERSIAN_RE.match(c))
    return persian > len(letters) / 2


def _embedding_is_hash(embedding: list[float], text: str = '') -> bool:
    """Heuristic: the local hash fallback produces deterministic vectors.

    We re-generate the hash embedding for the given text and compare;
    this is cheap and reliably distinguishes the fallback from a real model.
    """
    try:
        if not text:
            return True  # assume hash if no text to compare
        return embedding == _hash_embedding(text)
    except Exception:
        return True  # assume hash on error


_STOPWORDS = {
    'و', 'در', 'به', 'از', 'که', 'این', 'آن', 'با', 'برای', 'تا', 'یا', 'یک',
    'را', 'می', 'ها', 'های', 'است', 'هست', 'چیست', 'چی', 'کدام', 'چگونه',
    'the', 'a', 'an', 'of', 'to', 'in', 'is', 'and', 'for', 'on', 'with',
    'what', 'which', 'how', 'are', 'was', 'were', 'be', 'as', 'by', 'or',
}


def _tokens(text: str) -> set[str]:
    """Normalize and tokenize mixed FA/EN text."""
    cleaned = re.sub(r'[^\w\u0600-\u06FF]+', ' ', (text or '').lower(), flags=re.UNICODE)
    return {t for t in cleaned.split() if t and t not in _STOPWORDS and len(t) > 1}


def _keyword_score(question: str, content: str) -> float:
    """Lexical overlap score in [0, 1] using normalized token sets."""
    q_tokens = _tokens(question)
    if not q_tokens:
        return 0.0
    c_tokens = _tokens(content)
    if not c_tokens:
        return 0.0
    overlap = q_tokens & c_tokens
    return len(overlap) / len(q_tokens)


def _rerank(rows: list, question: str, min_similarity: float, *, keyword_primary: bool = False) -> list:
    """Filter by min similarity, then blend vector + keyword score.

    In hash/fallback mode (`keyword_primary=True`) lexical overlap dominates
    because hash vectors have no semantic meaning.
    """
    scored = []
    for r in rows:
        sim = float(r._mapping['similarity'])
        if sim < min_similarity:
            continue
        kw = _keyword_score(question, r._mapping['content'])
        if keyword_primary:
            # Require at least some lexical signal when vectors are meaningless.
            if kw <= 0:
                continue
            blended = 0.85 * kw + 0.15 * max(sim, 0.0)
        else:
            blended = 0.7 * sim + 0.3 * kw
        scored.append((blended, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored]


async def _keyword_search(
    user_id: int,
    question: str,
    document_id: int | None,
    top_k: int,
) -> list:
    """Lexical fallback search for when embeddings are hash-based."""
    tokens = sorted(_tokens(question), key=len, reverse=True)[:8]
    if not tokens:
        return []

    # Prefer longer tokens; score with simple presence count in SQL, re-rank in Python.
    params: dict[str, Any] = {'uid': user_id, 'top_k': max(top_k * 4, 20)}
    doc_filter = ''
    if document_id:
        doc_filter = 'AND rc.document_id = :doc_id'
        params['doc_id'] = document_id

    like_clauses = []
    for i, tok in enumerate(tokens):
        key = f't{i}'
        params[key] = f'%{tok}%'
        like_clauses.append(f'rc.content ILIKE :{key}')

    where_likes = ' OR '.join(like_clauses)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(f"""
            SELECT rc.content, rc.chunk_index, rd.title, rd.file_name,
                   0.0 AS similarity
            FROM rag_chunks rc
            JOIN rag_documents rd ON rc.document_id = rd.id
            WHERE rc.user_id = :uid
              {doc_filter}
              AND rd.status = 'indexed'
              AND ({where_likes})
            ORDER BY rc.id DESC
            LIMIT :top_k
        """), params)
        return list(res.fetchall())


async def _call_llm(messages: list[dict], model: str) -> str:
    """Call LiteLLM with a small fallback chain for rate-limit resilience."""
    candidates: list[str] = []
    for m in [model, *LLM_FALLBACK_MODELS]:
        if m and m not in candidates:
            candidates.append(m)

    last_err = None
    for m in candidates:
        try:
            resp = await _http.post(
                f'{LITELLM_HOST}/v1/chat/completions',
                json={
                    'model': m,
                    'messages': messages,
                    'temperature': 0.3,
                    'max_tokens': 2000,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data['choices'][0]['message']['content']
            last_err = f'{resp.status_code} {resp.text[:200]}'
            logger.warning(f'LLM model {m} failed: {last_err}')
            # Only rotate on rate-limit / unavailable model errors.
            if resp.status_code not in (400, 403, 404, 429, 500, 502, 503):
                break
        except Exception as e:
            last_err = str(e)
            logger.warning(f'LLM model {m} error: {e}')
            continue

    logger.error(f'All LLM candidates failed: {last_err}')
    return 'خطا در تولید پاسخ. لطفاً دوباره تلاش کنید.'


def _build_context(relevant: list) -> tuple[str, list[dict]]:
    """Build truncated context string with metadata and return sources."""
    context_parts = []
    sources = []
    used_tokens = 0

    for idx, r in enumerate(relevant, start=1):
        content = r._mapping['content']
        filename = r._mapping['file_name'] or r._mapping['title'] or 'unknown'
        title = r._mapping['title'] or ''
        chunk_idx = r._mapping['chunk_index']

        # Estimate tokens for this chunk before adding (overlap guard).
        chunk_tokens = estimate_tokens(content)
        if context_parts and used_tokens + chunk_tokens > MAX_CONTEXT_TOKENS:
            break

        header = f"[منبع {idx}] {filename}"
        if title and title != filename:
            header += f" — {title}"
        context_parts.append(f"{header}\n{content}\n---")
        used_tokens += chunk_tokens

        sources.append({
            'chunk_text': content[:300] + ('...' if len(content) > 300 else ''),
            'filename': filename,
            'title': title,
            'chunk_index': chunk_idx,
            'similarity': round(float(r._mapping['similarity']), 3),
        })

    return '\n\n'.join(context_parts), sources


def _system_prompt(context: str, is_persian: bool) -> str:
    """Return a grounded, citation-enforcing system prompt.

    The prompt instructs the model to answer ONLY from the provided excerpts
    and to cite sources with [1], [2], ... markers matching the context blocks.
    """
    if is_persian:
        return (
            "شما یک دستیار پاسخگوی مبتنی بر اسناد (RAG) هستید. "
            "به سوال کاربر فقط و فقط بر اساس قطعه‌های سند زیر پاسخ دهید. "
            "اگر پاسخ در اسناد نیست، صراحتاً بگویید که اطلاعات کافی در اسناد موجود نیست "
            "و هرگز از دانش خود استفاده نکنید.\n\n"
            "قوانین بسیار مهم:\n"
            "۱. پاسخ را به زبان فارسی بنویسید.\n"
            "۲. در انتهای هر جمله‌ای که از اسناد استفاده می‌کند، شماره منبع را به صورت "
            "[۱]، [۲] و غیره درج کنید (مطابق شماره [منبع n] در بالای هر قطعه).\n"
            "۳. اگر چند منبع مرتبط بود، به همه آن‌ها ارجاع دهید.\n"
            "۴. خلاصه و دقیق پاسخ دهید.\n\n"
            f"اسناد:\n{context}"
        )
    return (
        "You are a document-grounded (RAG) assistant. Answer the user's question "
        "based ONLY on the document excerpts below. If the answer is not in the "
        "documents, state clearly that the provided documents do not contain the "
        "answer, and never use your own knowledge.\n\n"
        "Strict rules:\n"
        "1. Answer in the same language as the user's question.\n"
        "2. After every statement drawn from the documents, cite the source as "
        "[1], [2], etc., matching the [Source n] header above each excerpt.\n"
        "3. If multiple sources are relevant, cite all of them.\n"
        "4. Be concise and accurate.\n\n"
        f"Documents:\n{context}"
    )


async def query_documents(
    user_id: int,
    question: str,
    document_id: int | None = None,
    top_k: int = RERANK_K,
    model: str = DEFAULT_RAG_MODEL,
) -> dict:
    """Query user's documents with RAG.

    1. Generate embedding for question
    2. Find similar chunks via pgvector cosine distance
    3. If embeddings are hash-based, fall back to lexical keyword search
    4. Re-rank by blending vector similarity + keyword overlap
    5. Build truncated context with document metadata
    6. Call LLM with grounded prompt + model fallback chain
    7. Return answer + source citations
    """
    if not question or not question.strip():
        return {'answer': 'لطفاً سوال خود را وارد کنید.', 'sources': []}

    if async_session is None:
        return {'answer': 'پایگاه داده در دسترس نیست.', 'sources': []}

    is_persian = _is_persian(question)

    # Normalize / bound inputs before they touch any SQL
    top_k = max(1, min(int(top_k), 20))  # clamp to a sane range
    if document_id is not None:
        try:
            document_id = int(document_id)
        except (TypeError, ValueError):
            return {'answer': 'شناسه سند نامعتبر است.', 'sources': []}

    model = model or DEFAULT_RAG_MODEL

    # 1. Generate query embedding
    try:
        query_embedding = await embed_single(question, user_id)
    except Exception as e:
        logger.error(f'Query embedding failed uid={user_id}: {e}')
        return {'answer': 'خطا در پردازش سوال. لطفاً دوباره تلاش کنید.', 'sources': []}

    if not query_embedding:
        return {'answer': 'خطا در تولید بردار جستجو.', 'sources': []}

    # Adaptive similarity floor: real embeddings vs hash fallback.
    is_hash = _embedding_is_hash(query_embedding, question)
    min_similarity = MIN_SIMILARITY_HASH if is_hash else MIN_SIMILARITY_SEMANTIC

    rows: list = []

    # 2a. Hash mode: keyword search is the real retrieval signal.
    if is_hash:
        try:
            rows = await _keyword_search(user_id, question, document_id, top_k)
        except Exception as e:
            logger.error(f'Keyword search failed uid={user_id}: {e}')
            rows = []

    # 2b. Semantic (or keyword empty): pgvector cosine search
    if not rows:
        embedding_str = '[' + ','.join(str(float(f)) for f in query_embedding) + ']'
        try:
            async with async_session() as session:
                # doc_filter is a fixed constant; values are bound parameters.
                params: dict[str, Any] = {
                    'uid': user_id,
                    'emb': embedding_str,
                    'top_k': max(top_k, DEFAULT_TOP_K),
                }
                doc_filter = ''
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
                rows = list(res.fetchall())
        except Exception as e:
            logger.error(f'Vector search failed uid={user_id}: {e}')
            return {'answer': 'خطا در جستجوی اسناد.', 'sources': []}

    if not rows:
        return {
            'answer': 'محتوای مرتبطی در اسناد شما پیدا نشد.',
            'sources': [],
        }

    # 3. Re-rank by blended score and apply adaptive similarity floor.
    ranked = _rerank(rows, question, min_similarity, keyword_primary=is_hash)
    relevant = ranked[:top_k]

    # If semantic re-rank emptied results in hash mode, keep keyword hits.
    if not relevant and is_hash and rows:
        relevant = rows[:top_k]

    if not relevant:
        return {
            'answer': 'محتوای مرتبطی با سوال شما در اسناد پیدا نشد. لطفاً سوال خود را دقیقتر مطرح کنید.',
            'sources': [],
        }

    # 4. Build truncated context with metadata.
    context, sources = _build_context(relevant)

    # 5. Call LLM with grounded, citation-enforcing prompt + fallback chain.
    system_prompt = _system_prompt(context, is_persian)
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': question},
    ]
    answer = await _call_llm(messages, model)

    return {'answer': answer, 'sources': sources}
