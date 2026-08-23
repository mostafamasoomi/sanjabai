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

from models import Quota
from services.context_injection import get_injection_messages, inject_messages
from services.token_budget import apply_outbound_budget
from services.billing import SqlBillingRepo, InsufficientBalanceError
from services.money import Money
from services.entitlement_gate import covering_entitlement
from middleware.compression import compress_messages
from model_output import clean_response_dict

import chat
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
                return JSONResponse(
                    {'error': {'message': 'insufficient wallet balance | موجودی کیف پول کافی نیست', 'type': 'quota_exceeded', 'code': 'balance'}},
                    status_code=429,
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
    payload = {'model': model, 'messages': messages, 'stream': False}

    # Memory + soul injection
    try:
        injs = await get_injection_messages(uid, messages=payload.get('messages'))
        if injs:
            payload['messages'] = inject_messages(payload.get('messages', []), injs)
    except Exception as e:
        logger.warning(f"_call_model_once injection failed uid={uid} model={model}: {e}")

    # Compress
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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    _disabled = await chat._chat_preflight(uid, payload.messages)
    if _disabled is not None:
        return _disabled

    model_a = payload.model_a
    model_b = payload.model_b
    messages = payload.messages

    if not model_a or not model_b:
        return JSONResponse(
            {'error': {'message': 'هر دو مدل باید مشخص شوند', 'type': 'invalid_request', 'code': 'missing_models'}},
            status_code=400,
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
        return JSONResponse(
            {'error': {'message': f'مدل {model_a_requested} در دسترس نیست', 'type': 'invalid_request', 'code': 'model_not_available'}},
            status_code=400,
        )
    if not await chat._is_model_allowed(model_b):
        return JSONResponse(
            {'error': {'message': f'مدل {model_b_requested} در دسترس نیست', 'type': 'invalid_request', 'code': 'model_not_available'}},
            status_code=400,
        )

    # Free-tier throttle gate — both models checked together in one call so
    # a rejection on the second model never burns the first one's budget.
    _ft_gate = await chat.check_and_consume(uid, [model_a, model_b])
    if _ft_gate is not None:
        return chat._free_tier_response(_ft_gate)

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
            reservation_a = None if await covering_entitlement(uid, 1000) is not None else await _bill_svc.reserve(
                uid, Money(1000),
                idempotency_key=f"cmp:{secrets.token_hex(8)}",
                model=model_a,
            )
            reservation_b = None if await covering_entitlement(uid, 1000) is not None else await _bill_svc.reserve(
                uid, Money(1000),
                idempotency_key=f"cmp:{secrets.token_hex(8)}",
                model=model_b,
            )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return JSONResponse(
            {'error': {'message': 'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.', 'type': 'quota_exceeded', 'code': 'balance'}},
            status_code=429,
        )
    except Exception as e:
        logger.warning(f"Compare BillingService.reserve failed uid={uid}: {e}")
        quota_err = await _check_quota_pre(uid)
        if quota_err is not None:
            return quota_err

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

    return JSONResponse({
        'model_a': result_a,
        'model_b': result_b,
        'faster': faster,
        'cheaper': cheaper,
        'messages': messages,
    })
