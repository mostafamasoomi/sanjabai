"""The /v1/compare path -- split out of chat.py (see chat.py's module
docstring for why).

MONKEYPATCH CONTRACT: tests patch `chat_mod._get_user_id`,
`chat_mod._resolve_provider`, `chat_mod._resolve_public_model`,
`chat_mod._is_model_allowed`, `chat_mod.check_and_consume`,
`chat_mod.BillingService`, `chat_mod.async_session`, `chat_mod._http`, and
`chat_mod._track_usage` directly on the `chat` module (see
test_public_model_ids.py and the shared contract documented in chat.py's
module docstring). Every one of those names is resolved through
`chat.<name>` at call time below, never via `from chat import X`. `chat` is
imported plainly at module scope, which is safe against the chat.py <->
chat_compare.py circular import: nothing here touches a `chat` attribute
until a function actually runs, by which point chat.py has finished
executing.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import Request
from fastapi.responses import JSONResponse, Response

from models import CompareSession, Quota
from services.context_injection import get_injection_messages, inject_messages
from services.token_budget import apply_outbound_budget
from services.billing import SqlBillingRepo, InsufficientBalanceError
from services.money import Money
from services.entitlement_gate import covering_entitlement
from services.free_tier import covers_request
from middleware.compression import compress_messages, compression_enabled_for
from model_output import clean_response_dict
from i18n import err, err_openai
# Reused verbatim (not reimplemented) so title generation can never drift
# between /conversations and /v1/compare -- see conversations.py's docstring.
from conversations import _auto_generate_title

import chat
from providers import COMPLETION_TIMEOUT_SECONDS
from chat import CompareRequest

logger = logging.getLogger('chat')  # keep all chat_*.py logs under the pre-split 'chat' logger name


async def _check_quota_pre(uid: int) -> JSONResponse | None:
    """Pre-flight quota and balance check before calling LiteLLM.

    Lives here (not chat.py) purely to keep chat.py under the house
    500-line cap -- this file's own except-fallback below is one of its
    callers. Every other module reaches it as `chat._check_quota_pre`
    (re-exported by chat.py).
    """
    if chat.async_session is None:
        return None
    try:
        async with chat.async_session() as session:
            res = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
            quota = res.fetchone()
            if quota:
                limit = quota.daily_limit
                used = quota.used_today
                reset_at = chat._as_naive_utc(quota.reset_at)
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if reset_at and now >= reset_at:
                    await session.execute(
                        Quota.__table__.update().where(Quota.user_id == uid),
                        {'used_today': 0, 'updated_at': now},
                    )
                    await session.commit()
                    used = 0
                if limit > 0 and used >= limit:
                    return JSONResponse(
                        {'error': {'message': 'daily token quota exceeded', 'type': 'quota_exceeded', 'code': 'daily_limit'}},
                        status_code=429,
                    )
            res = await session.execute(
                sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
                {'uid': uid},
            )
            row = res.fetchone()
            balance = row.balance if row else 0
            if balance <= 0:
                return err_openai(
            # Was one string with both languages either side of a pipe --
            # the hand-rolled version of what err_openai does properly.
            'موجودی کیف پول کافی نیست',
            'Insufficient wallet balance.',
            429, code='balance', err_type='quota_exceeded',
        )
    except Exception as e:
        logger.warning(f"_check_quota_pre failed uid={uid}: {e}")
    return None


async def _call_model_once(
    model: str,
    messages: list,
    uid: int,
    request: Request,
) -> dict[str, Any]:
    """Call a single model and return response + timing + usage + cost."""
    start = time.monotonic()
    # Per-model copy -- `messages` is the SAME list object shared with the
    # sibling model's concurrent _call_model_once() call (asyncio.gather in
    # compare_models), so mutating it in place here (injection/compression
    # below) would leak this model's system messages into the other model's
    # request. list(...) breaks that aliasing; the shared elements are dicts
    # and stay unmodified by anything below (only insert/replace happen).
    payload = {'model': model, 'messages': list(messages), 'stream': False}

    # Honest model identity injection (see services/model_identity.py)
    await chat.apply_model_identity(payload)

    # Memory + soul injection
    try:
        injs = await get_injection_messages(uid, messages=payload.get('messages'))
        if injs:
            payload['messages'] = inject_messages(payload.get('messages', []), injs)
    except Exception as e:
        logger.warning(f"_call_model_once injection failed uid={uid} model={model}: {e}")

    # Compress -- opt-in only; see the gate's rationale in chat.py.
    if await compression_enabled_for(uid):
        try:
            _orig = [m.copy() for m in payload.get('messages', [])]
            payload['messages'] = compress_messages(payload.get('messages', []), preserve_last=2)
        except Exception as e:
            logger.debug(f"Compression skipped in compare: {e}")

    # Phase E ceiling -- compare fans one prompt out to two models, so an
    # unbounded payload/answer is paid twice here.
    await apply_outbound_budget(payload)

    try:
        _provider = await chat._resolve_provider(model)
        r = await chat._http.post(
            f'{_provider.v1}/chat/completions',
            json=payload,
            headers={**_provider.headers(), 'Accept': 'application/json'},
            timeout=COMPLETION_TIMEOUT_SECONDS,
        )
        elapsed = round(time.monotonic() - start, 3)
        if r.status_code == 200:
            resp_data = r.json()
            # Bill on the RAW upstream response -- see the identical
            # comment in chat() above.
            cost_info = await chat._track_usage(request, payload, resp_data)
            resp_data = clean_response_dict(resp_data)
            usage = resp_data.get('usage', {})
            content = ''
            choices = resp_data.get('choices', [])
            if choices:
                content = choices[0].get('message', {}).get('content', '')
            return {
                'model': model,
                'content': content,
                'elapsed': elapsed,
                'input_tokens': usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0) or 0,
                'output_tokens': usage.get('completion_tokens', 0) or usage.get('output_tokens', 0) or 0,
                'cost': cost_info.get('cost', 0) if cost_info else 0,
                'error': None,
            }
        else:
            return {
                'model': model,
                'content': '',
                'elapsed': elapsed,
                'input_tokens': 0,
                'output_tokens': 0,
                'cost': 0,
                'error': f'upstream error {r.status_code}',
            }
    except Exception as e:
        elapsed = round(time.monotonic() - start, 3)
        logger.warning(f"_call_model_once failed uid={uid} model={model}: {e}")
        return {
            'model': model,
            'content': '',
            'elapsed': elapsed,
            'input_tokens': 0,
            'output_tokens': 0,
            'cost': 0,
            'error': str(e),
        }


@chat.router.post('/v1/compare')
async def compare_models(request: Request, payload: CompareRequest) -> Response:
    """Compare two models side-by-side. Non-streaming first."""
    uid = await chat._get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    _disabled = await chat._chat_preflight(uid, payload.messages)
    if _disabled is not None:
        return _disabled

    if payload.stream:
        return err_openai(
            'مقایسه هم‌زمان دو مدل فعلاً به‌صورت جریانی پشتیبانی نمی‌شود.',
            'Streaming is not supported for model comparison yet.',
            400, code='stream_unsupported', err_type='invalid_request',
        )

    model_a = payload.model_a
    model_b = payload.model_b
    messages = payload.messages

    if not model_a or not model_b:
        return err_openai(
            'هر دو مدل باید مشخص شوند',
            'Both models must be specified.',
            400, code='missing_models', err_type='invalid_request',
        )

    # Canonicalize both public_id(s)/legacy id(s) to provider_model_id FIRST
    # -- see _resolve_public_model's docstring in this file. The ORIGINAL
    # request strings are kept (model_a_requested/model_b_requested) purely
    # to echo back in the response below -- a normal user must never see
    # which upstream route a model resolved to (see content.py), so the
    # response must report exactly what the caller sent, not the canonical
    # provider_model_id used internally for routing/billing.
    model_a_requested, model_b_requested = model_a, model_b
    model_a = await chat._resolve_public_model(model_a)
    model_b = await chat._resolve_public_model(model_b)

    # Validate both models (error text echoes what the caller sent, not the
    # resolved provider_model_id -- same route-hiding rule as everywhere else).
    if not await chat._is_model_allowed(model_a):
        return err_openai(
            f'مدل {model_a_requested} در دسترس نیست',
            f'Model {model_a_requested} is not available',
            400, code='model_not_available', err_type='invalid_request',
        )
    if not await chat._is_model_allowed(model_b):
        return err_openai(
            f'مدل {model_b_requested} در دسترس نیست',
            f'Model {model_b_requested} is not available',
            400, code='model_not_available', err_type='invalid_request',
        )

    # Free-tier throttle gate — both models checked together in one call so
    # a rejection on the second model never burns the first one's budget.
    _ft_gate = await chat.check_and_consume(uid, [model_a, model_b])
    if _ft_gate is not None:
        return chat._free_tier_response(_ft_gate)

    # Premium (expensive-model) sub-allowance gate — both models in ONE call
    # for the same reason the free-tier gate above does it: a rejection on the
    # second model must never burn the first one's allowance. Post-model,
    # pre-reserve, exactly like the gate above.
    _premium_gate = await chat.premium_check_and_consume(uid, [model_a, model_b])
    if _premium_gate is not None:
        return chat._premium_quota_response(_premium_gate)

    # P1: Reserve billing for both models (estimate worst-case)
    reservation_a = None
    reservation_b = None
    try:
        async with chat.async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = chat.BillingService(_repo)
            # Each model is billed independently at its own eventual charge
            # point (_call_model_once -> _record_usage, once per model), so
            # each reservation is pre-authorized against the entitlement
            # independently too -- this is a read-only check (it consumes
            # nothing), so both calls seeing the same entitlement is correct:
            # the real spend happens later, atomically, per model, in
            # consume_for_usage. If the entitlement only has one request left,
            # the first actual consume wins and the second falls through to
            # the wallet on its own, same as any other race on consume.
            if await covering_entitlement(uid, 1000) is not None or await covers_request(uid):
                reservation_a = None
            else:
                reservation_a = await _bill_svc.reserve(
                    uid, Money(1000),
                    idempotency_key=f"cmp:{secrets.token_hex(8)}",
                    model=model_a,
                )
            if await covering_entitlement(uid, 1000) is not None or await covers_request(uid):
                reservation_b = None
            else:
                reservation_b = await _bill_svc.reserve(
                    uid, Money(1000),
                    idempotency_key=f"cmp:{secrets.token_hex(8)}",
                    model=model_b,
                )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return err_openai(
            'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.',
            'Your wallet balance is not enough. Please top up your account.',
            429, code='balance', err_type='quota_exceeded',
        )
    except Exception as e:
        logger.warning(f"Compare BillingService.reserve failed uid={uid}: {e}")
        quota_err = await _check_quota_pre(uid)
        if quota_err is not None:
            return quota_err

    # Web search injection (shared helper -- see _apply_web_search), run ONCE
    # here on the shared prompt -- not inside _call_model_once -- so a
    # search is never fetched (and never paid for) twice for the same
    # comparison. Both models below then see the identical grounded
    # `messages`, same as chat.py's single-model path.
    _ws = {'messages': messages, 'web_search': payload.web_search}
    await chat._apply_web_search(_ws, handler='compare')
    messages = _ws['messages']

    # Run both models in parallel
    results = await asyncio.gather(
        _call_model_once(model_a, messages, uid, request),
        _call_model_once(model_b, messages, uid, request),
    )

    result_a, result_b = results
    # Echo back exactly what the caller requested, never the resolved
    # provider_model_id -- a normal user must never see which upstream route
    # a model resolved to (see content.py's no-provider-leak rule).
    result_a['model'] = model_a_requested
    result_b['model'] = model_b_requested

    # Release reservations
    for res in (reservation_a, reservation_b):
        if res:
            try:
                async with chat.async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = chat.BillingService(_rel_repo)
                    await _rel_svc.release(res['reservation_id'])
                    await _rel_session.commit()
            except Exception as _rel_e:
                logger.warning(f"Compare BillingService.release failed uid={uid}: {_rel_e}")

    # Determine winner stats
    faster = None
    cheaper = None
    if not result_a.get('error') and not result_b.get('error'):
        if result_a['elapsed'] < result_b['elapsed']:
            faster = 'model_a'
        elif result_b['elapsed'] < result_a['elapsed']:
            faster = 'model_b'
        if result_a['cost'] < result_b['cost']:
            cheaper = 'model_a'
        elif result_b['cost'] < result_a['cost']:
            cheaper = 'model_b'

    # Persist a compare_sessions row (migration 0054) so this comparison can
    # be reopened/continued later -- see chat_compare.py's module docstring
    # and CompareSession's docstring in models/_conversations.py. Additive
    # only: session_id is a NEW response field, everything above is
    # unchanged. Best-effort -- a persistence failure must not turn an
    # otherwise-successful comparison into a 500 (same fail-open shape as
    # the reservation fallback above), it just means this comparison has no
    # history entry.
    session_id = None
    try:
        title = await _auto_generate_title(payload.messages)
        thread_a = list(messages) + [{'role': 'assistant', 'content': result_a['content']}]
        thread_b = list(messages) + [{'role': 'assistant', 'content': result_b['content']}]
        async with chat.async_session() as _cs_session:
            _cs = CompareSession(
                user_id=uid, model_a=model_a, model_b=model_b,
                model_a_requested=model_a_requested, model_b_requested=model_b_requested,
                title=title, thread_a=thread_a, thread_b=thread_b,
            )
            _cs_session.add(_cs)
            await _cs_session.commit()
            await _cs_session.refresh(_cs)
            session_id = _cs.id
    except Exception as e:
        logger.warning(f"Compare session persistence failed uid={uid}: {e}")

    return JSONResponse({
        'model_a': result_a,
        'model_b': result_b,
        'faster': faster,
        'cheaper': cheaper,
        'messages': messages,
        'session_id': session_id,
    })


# Side-effecting import -- registers the four /v1/compare/sessions* routes
# (POST .../continue, GET list, GET .../{id}, DELETE .../{id}) on
# `chat.router`. They live in chat_compare_sessions.py, a separate file
# purely to keep THIS file under the house 500-line cap (same reason
# chat.py itself split into chat_web.py/chat_models.py/chat_search.py/
# chat_billing.py/chat_stream.py/this file, chat_smart.py) -- see that
# module's docstring. `_call_model_once` above is imported back from there,
# not duplicated, so the reserve/gather/release + billing/error shape stays
# defined in exactly one place.
from chat_compare_sessions import (  # noqa: F401,E402
    continue_compare_session,
    list_compare_sessions,
    get_compare_session,
    delete_compare_session,
)
