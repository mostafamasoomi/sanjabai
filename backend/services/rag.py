"""
RAG query service — semantic search over user documents.

Generates query embedding, finds similar chunks via pgvector cosine
similarity, then calls LLM with grounded context. Pure retrieval helpers
(language detection, reranking, keyword search, context/prompt building)
live in services/rag_retrieval.py -- split out solely to keep this file
under the house 500-line cap once the Phase J moderation + free-tier/quota
gates + billing bracket were added below; see that file's module docstring.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any

import sqlalchemy

from database import async_session, _http, LITELLM_HOST
from dependencies import _to_fa
from services.billing import SqlBillingRepo, BillingService, InsufficientBalanceError
from services.embeddings import embed_single
from services.free_tier import check_and_consume as _free_tier_check
from services.moderation import screen_request, BLOCK_MESSAGE_FA
from services.money import Money
from services.rag_retrieval import (
    DEFAULT_TOP_K,
    MIN_SIMILARITY_HASH,
    MIN_SIMILARITY_SEMANTIC,
    _build_context,
    _embedding_is_hash,
    _is_persian,
    _keyword_search,
    _rerank,
    _system_prompt,
)
from services.premium_quota import check_and_consume as _premium_quota_check
from services.user_quota import check_and_consume as _user_quota_check
from site_settings import get_site_flag

logger = logging.getLogger(__name__)

RERANK_K = 5               # final chunks sent to the LLM
DEFAULT_RAG_MODEL = 'mimo-v2.5'
# Fallback chain when the requested model is rate-limited / unavailable.
LLM_FALLBACK_MODELS = (
    'mimo-v2.5',
    'kwaipilot/kat-coder-air-v2.5',
    'deepseek-v4-pro',
    'tencent-hy3',
)

# ── Billed / gated query path (Phase J + billing gap closure) ──────────────
#
# Before this, query_documents() reached `{LITELLM_HOST}/v1/chat/completions`
# with zero content screening and zero billing -- the request's question was
# never checked against services/moderation.py, never counted against the
# free tier or the aggregate package quota, and the completion itself was
# never reserved/settled (only the query EMBEDDING is billed, separately,
# via services/embeddings.py's usage_events write -- that part was already
# correct and is untouched here). Order mirrors task_execution.py's
# _execute_task exactly: kill switch -> moderation -> free-tier -> quota ->
# reserve -> call -> settle -> release, and all five gates run before the
# embedding call too (also a billed upstream request) so a blocked question
# costs nothing at all, not even an embedding.
_CHAT_DISABLED_MESSAGE = 'گفتگو موقتاً در دسترس نیست'
_FREE_TIER_MESSAGE = (
    'سقف پیام رایگان این مدل برای اکنون پر شده است؛ کمی بعد دوباره تلاش کنید '
    'یا با شارژ حساب این محدودیت را برای همیشه بردارید.'
)
_INSUFFICIENT_BALANCE_MESSAGE = 'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.'
_RESERVE_GATEWAY_ERROR_MESSAGE = 'سرویس موقتاً در دسترس نیست.'
# Same shape as task_execution.py's reserve estimate: a cheap pre-flight
# hold, not a prediction of the real cost -- the real charge is whatever
# chat._bill_stream_usage computes from actual (or L1-estimated) tokens
# after the fact.
_RESERVE_ESTIMATE_WORKING = 1000
_RESERVE_ESTIMATE_UNKNOWN = 5000


async def _call_llm(messages: list[dict], model: str) -> tuple[str, str, dict]:
    """Call LiteLLM with a small fallback chain for rate-limit resilience.

    Returns ``(answer_text, model_used, usage)``. ``model_used`` is the
    RESOLVED (``model_catalog.provider_model_id``) model that actually
    produced the answer, and '' when every candidate failed -- the caller's
    signal that nothing was served and nothing should be billed. Every
    candidate is canonicalized via ``chat._resolve_public_model`` exactly
    once each, here, before it is tried or returned (the financial rule --
    see chat_models.py's ``_resolve_public_model`` docstring and
    images.py's module docstring): downstream billing
    (``chat_billing._record_usage``) prices strictly off
    ``model_catalog.provider_model_id``, so returning an unresolved public
    id here would make the settle step miss the price lookup.
    """
    import chat as chat_mod

    candidates: list[str] = []
    for m in [model, *LLM_FALLBACK_MODELS]:
        if not m:
            continue
        resolved = await chat_mod._resolve_public_model(m)
        if resolved not in candidates:
            candidates.append(resolved)

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
                answer = data['choices'][0]['message']['content']
                usage = data.get('usage') or {}
                return answer, m, usage
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
    return 'خطا در تولید پاسخ. لطفاً دوباره تلاش کنید.', '', {}


async def query_documents(
    user_id: int,
    question: str,
    document_id: int | None = None,
    top_k: int = RERANK_K,
    model: str = DEFAULT_RAG_MODEL,
) -> dict:
    """Query user's documents with RAG.

    0. Kill switch, content moderation, free-tier gate, package quota gate,
       premium (expensive-model) sub-allowance gate
       (all before any billed upstream call -- see the module-level "Billed
       / gated query path" note above _CHAT_DISABLED_MESSAGE)
    1. Generate embedding for question
    2. Find similar chunks via pgvector cosine distance
    3. If embeddings are hash-based, fall back to lexical keyword search
    4. Re-rank by blending vector similarity + keyword overlap
    5. Build truncated context with document metadata
    6. Reserve -> call LLM with grounded prompt + model fallback chain ->
       settle -> release (see chat._bill_stream_usage / task_execution.py's
       identical bracket)
    7. Return answer + source citations
    """
    if not question or not question.strip():
        return {'answer': 'لطفاً سوال خود را وارد کنید.', 'sources': []}

    if async_session is None:
        return {'answer': 'پایگاه داده در دسترس نیست.', 'sources': []}

    # Gate 0: chat kill switch. RAG queries end up on the same
    # `{LITELLM_HOST}/v1/chat/completions` surface every chat entry point
    # uses, so they must not keep spending while an admin has turned chat
    # off. Reuses the SAME registered flag chat_web._chat_disabled_response
    # reads (site_settings.get_site_flag fails a call for any UNREGISTERED
    # flag key closed to False -- there is no separate 'rag_enabled' flag
    # registered, so inventing a new key here would silently disable RAG
    # forever; reusing 'chat_enabled' is the only correct choice available
    # to this file). Never raises: get_site_flag fails open to its
    # registered default on any Redis/DB error.
    if not await get_site_flag('chat_enabled'):
        return {'answer': _CHAT_DISABLED_MESSAGE, 'sources': []}

    # Gate 1: content moderation (Phase J) -- the SAME detector engine
    # every chat entry point uses (services/moderation.py), called directly
    # as screen_request (not the JSONResponse-returning moderation_preflight)
    # because this function returns a plain dict, never an HTTP response --
    # identical reasoning to task_execution.py's module docstring. Chosen as
    # the seam here (services/rag.py) rather than rag_endpoints.py because
    # this is the ONE place every current and future caller of
    # query_documents funnels through -- covering the endpoint would only
    # cover the endpoint. Run BEFORE the embedding call below (itself a
    # billed upstream request, see services/embeddings.py) and BEFORE any
    # wallet reservation, so a blocked question costs nothing at all, not
    # even an embedding. Never raises (fail-safe: allow + flag + alert on a
    # detector failure) and the block message is used byte-for-byte, never
    # rewritten, never naming a rule/model/provider.
    verdict = await screen_request(user_id, [{'role': 'user', 'content': question}])
    if verdict.decision == 'block':
        return {'answer': verdict.message_fa or BLOCK_MESSAGE_FA, 'sources': []}

    is_persian = _is_persian(question)

    # Normalize / bound inputs before they touch any SQL
    top_k = max(1, min(int(top_k), 20))  # clamp to a sane range
    if document_id is not None:
        try:
            document_id = int(document_id)
        except (TypeError, ValueError):
            return {'answer': 'شناسه سند نامعتبر است.', 'sources': []}

    model = model or DEFAULT_RAG_MODEL

    # Gate 2 (financial rule): canonicalize the model to
    # model_catalog.provider_model_id exactly once here, before the
    # free-tier/quota gates that need to check pricing on it and before the
    # reservation below -- see chat_models.py's _resolve_public_model
    # docstring and images.py's identical rule. `chat` is imported late
    # (inside the function, not at module scope) because chat.py is being
    # restructured by other agents concurrently and the test suite
    # monkeypatches names ON THE CHAT MODULE -- see task_execution.py's
    # "LATE BINDING IS MANDATORY" note, which applies verbatim here.
    import chat as chat_mod
    resolved_model = await chat_mod._resolve_public_model(model)

    # Gate 3: free tier (per-model cheap-models-only / lifetime / hourly).
    # No-ops (returns None) for anyone who has paid or holds wallet credit
    # or a package -- see services/free_tier.py's module docstring.
    ft_gate = await _free_tier_check(user_id, [resolved_model])
    if ft_gate is not None:
        return {'answer': ft_gate.get('message', _FREE_TIER_MESSAGE), 'sources': []}

    # Gate 4: aggregate package quota -- the SAME gate
    # chat_web._chat_preflight runs, so a RAG query counts against the same
    # package window an interactive chat message does rather than escaping
    # it. No-ops for the free tier and for a balance/pay-per-use user.
    q_gate = await _user_quota_check(user_id)
    if q_gate is not None:
        return {'answer': _quota_message(q_gate), 'sources': []}

    # Gate 5: premium (expensive-model) sub-allowance -- the same gate the
    # four chat routes run at their own post-model point, so a RAG query on
    # an expensive model counts against the package's premium sub-allowance
    # rather than escaping it. Runs before the embedding call below and well
    # before reserve(), so a rejection costs nothing.
    p_gate = await _premium_quota_check(user_id, [resolved_model])
    if p_gate is not None:
        return {'answer': p_gate.get('message', _FREE_TIER_MESSAGE), 'sources': []}

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
                           1 - (rc.embedding <=> :emb\\:\\:vector) AS similarity
                    FROM rag_chunks rc
                    JOIN rag_documents rd ON rc.document_id = rd.id
                    WHERE rc.user_id = :uid
                      {doc_filter}
                      AND rd.status = 'indexed'
                    ORDER BY rc.embedding <=> :emb\\:\\:vector
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

    # 5. Reserve BEFORE the upstream completion call -- a pre-flight
    # availability hold, not a prediction of the final cost. Mirrors
    # task_execution.py's reserve -> call -> settle -> release bracket
    # exactly (modeled on backend/images.py lines 136-291 and
    # backend/chat.py's non-streaming handler, per that module's own
    # docstring). Money is an integer number of Toman throughout -- see
    # services/money.py; never multiply/divide by 10 anywhere in this file.
    try:
        is_working = await chat_mod.is_working_model(resolved_model)
    except Exception as e:
        logger.warning(f'RAG: is_working_model failed model={resolved_model}: {e}')
        is_working = False
    est_cost = _RESERVE_ESTIMATE_WORKING if is_working else _RESERVE_ESTIMATE_UNKNOWN

    reservation: dict | None = None
    try:
        async with async_session() as bill_session:
            repo = SqlBillingRepo(bill_session)
            bill_svc = BillingService(repo)
            reservation = await bill_svc.reserve(
                user_id, Money(est_cost),
                idempotency_key=f"rag:{secrets.token_hex(8)}",
                model=resolved_model,
            )
            await bill_session.commit()
    except InsufficientBalanceError:
        return {'answer': _INSUFFICIENT_BALANCE_MESSAGE, 'sources': []}
    except Exception as e:
        logger.warning(f'RAG: reserve failed uid={user_id} model={resolved_model}: {e}')
        return {'answer': _RESERVE_GATEWAY_ERROR_MESSAGE, 'sources': []}

    # 6. Call LLM with grounded, citation-enforcing prompt + fallback chain.
    system_prompt = _system_prompt(context, is_persian)
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': question},
    ]
    answer, model_used, usage = await _call_llm(messages, resolved_model)

    # 7. Settle -> release. A real charge, if any, is applied DIRECTLY
    # against wallet.balance inside chat._bill_stream_usage (never
    # "settled" against the reservation object itself -- reserve() exists
    # only to gate availability up front); the pre-flight hold from step 5
    # is then released either way. `model_used` is '' when every fallback
    # candidate failed (see _call_llm's docstring) -- nothing was served,
    # so nothing is billed, and only the hold is released.
    cost_info: dict = {}
    if model_used:
        try:
            cost_info = await chat_mod._bill_stream_usage(
                user_id, {'model': model_used, 'messages': messages}, usage,
                response_text=answer,
            )
        except Exception as e:
            # The answer was already generated and is about to be returned
            # to the user -- a settle failure here is a reconciliation
            # problem, not a reason to withhold an already-served answer
            # (same reasoning as images.py's / task_execution.py's
            # identical settle-failure comment). Logged loudly.
            logger.error(
                f'RAG: settle FAILED after a successful upstream response '
                f'uid={user_id} model={model_used}: {e}'
            )
    await _release_reservation(reservation, user_id, 'rag_query')

    result: dict[str, Any] = {'answer': answer, 'sources': sources}
    cost = int((cost_info or {}).get('cost') or 0)
    if cost > 0:
        result['billing'] = {'cost': cost, 'currency': 'IRT'}
    return result


async def _release_reservation(reservation: dict | None, uid: int, label: str = '') -> None:
    """Release a billing reservation; fire-and-forget, logs on failure.

    Deliberately self-contained (mirrors task_execution.py's local
    `_release`, not a late-bound call into chat.py/chat_web.py): this
    module's only intentional dependencies on chat.py are the symbols named
    in the coordinator's brief (`_resolve_public_model`, `is_working_model`,
    `_bill_stream_usage`) -- keeping the release path self-contained means a
    rename inside chat.py's ongoing concurrent restructuring can't silently
    break reservation cleanup here.
    """
    if not reservation or async_session is None:
        return
    try:
        async with async_session() as s:
            repo = SqlBillingRepo(s)
            svc = BillingService(repo)
            await svc.release(reservation['reservation_id'])
            await s.commit()
    except Exception as e:
        logger.warning(f"RAG: release_reservation failed uid={uid} {label}: {e}")


def _quota_message(gate: dict) -> str:
    """Persian message for the aggregate package quota gate -- mirrors
    chat_web._user_quota_response's wording so the two surfaces read
    consistently, adapted for RAG's plain-dict response shape (no HTTP
    status/type fields here, just Persian text). `chat` is imported late
    for the same monkeypatch/concurrent-editing reason documented on
    query_documents' Gate 2 above."""
    import chat as chat_mod
    retry = int(gate.get('retry_after_seconds', 0))
    limit = int(gate.get('limit', 0))
    tail = (
        'برای سقف بالاتر، بستهٔ بزرگ‌تری تهیه کنید.'
        if gate.get('source') == 'package'
        else 'با تهیهٔ بسته یا شارژ حساب، سقف شما افزایش می‌یابد.'
    )
    return (
        f'سقف {_to_fa(limit)} پیام در هر ۵ ساعت پر شده است. '
        f'حدود {chat_mod._persian_duration(retry)} دیگر دوباره فعال می‌شود. {tail}'
    )
