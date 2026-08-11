"""
Model comparison endpoint: /v1/compare.

Pulled out of chat.py (which was well past the project's 500-line ceiling).
Fans a single prompt to two models concurrently and returns a side-by-side
report with timing, usage and cost.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from database import async_session, _http
from dependencies import _get_user_id
from services.context_injection import get_injection_messages, inject_messages
from middleware.compression import compress_messages
from services.billing import SqlBillingRepo, BillingService, InsufficientBalanceError
from services.money import Money

from chat_common import CompareRequest, _fire_memory_extraction
from chat_billing import _check_quota_pre, _track_usage

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Compare ──────────────────────────────────────────────────────

async def _call_model_once(
    model: str,
    messages: list,
    uid: int,
    request: Request,
) -> dict[str, Any]:
    """Call a single model and return response + timing + usage + cost."""
    import time
    start = time.monotonic()
    payload = {'model': model, 'messages': messages, 'stream': False}

    # Memory + soul injection
    try:
        injs = await get_injection_messages(uid)
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

    try:
        from chat import _resolve_provider
        _provider = await _resolve_provider(model)
        r = await _http.post(
            f'{_provider.v1}/chat/completions',
            json=payload,
            headers={**_provider.headers(), 'Accept': 'application/json'},
        )
        elapsed = round(time.monotonic() - start, 3)
        if r.status_code == 200:
            resp_data = r.json()
            cost_info = await _track_usage(request, payload, resp_data)
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


@router.post('/v1/compare')
async def compare_models(request: Request, payload: CompareRequest) -> Response:
    """Compare two models side-by-side. Non-streaming first."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    model_a = payload.model_a
    model_b = payload.model_b
    messages = payload.messages

    if not model_a or not model_b:
        return JSONResponse(
            {'error': {'message': 'هر دو مدل باید مشخص شوند', 'type': 'invalid_request', 'code': 'missing_models'}},
            status_code=400,
        )

    # Validate both models
    from chat import _is_model_allowed
    if not await _is_model_allowed(model_a):
        return JSONResponse(
            {'error': {'message': f'مدل {model_a} در دسترس نیست', 'type': 'invalid_request', 'code': 'model_not_available'}},
            status_code=400,
        )
    if not await _is_model_allowed(model_b):
        return JSONResponse(
            {'error': {'message': f'مدل {model_b} در دسترس نیست', 'type': 'invalid_request', 'code': 'model_not_available'}},
            status_code=400,
        )

    # P1: Reserve billing for both models (estimate worst-case)
    reservation_a = None
    reservation_b = None
    try:
        async with async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = BillingService(_repo)
            reservation_a = await _bill_svc.reserve(
                uid, Money(1000),
                idempotency_key=f"cmp:{secrets.token_hex(8)}",
                model=model_a,
            )
            reservation_b = await _bill_svc.reserve(
                uid, Money(1000),
                idempotency_key=f"cmp:{secrets.token_hex(8)}",
                model=model_b,
            )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return JSONResponse(
            {'error': {'message': 'insufficient wallet balance | موجودی کیف پول کافی نیست', 'type': 'quota_exceeded', 'code': 'balance'}},
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

    # Release reservations
    for res in (reservation_a, reservation_b):
        if res:
            try:
                async with async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = BillingService(_rel_repo)
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
