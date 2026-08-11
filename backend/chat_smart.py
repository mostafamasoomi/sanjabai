"""
Smart Mode chat: automatic model selection + the /v1/smart-chat endpoint.

Pulled out of chat.py (which was well past the project's 500-line ceiling).
Contains the message-category analysis, balance/plan lookups, the model
selection tables, the ``smart_chat`` route and its SSE stream.

``_get_user_plan`` is re-exported from the chat aggregator because
``security.py`` lazy-imports it (``from chat import _get_user_plan``) to keep
its own rate-limiter logic in sync with the user's plan.

Model-selection helpers that read ``chat.async_session`` (``_is_model_allowed``,
``is_working_model``, ``_resolve_provider``) are imported lazily from the chat
aggregator so test patches of ``chat.async_session`` keep reaching them.
"""
from __future__ import annotations

import json
import logging
import re as _re
import secrets
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import select

from database import async_session, _http
from models import Subscription
from dependencies import _get_user_id
from services.context_injection import get_injection_messages, inject_messages
from middleware.compression import compress_messages, estimate_savings
from services.billing import SqlBillingRepo, BillingService, InsufficientBalanceError
from services.money import Money

from chat_billing import _check_quota_pre, _track_usage, _bill_stream_usage
from chat_common import ChatRequest, _fire_memory_extraction

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Smart Chat ──────────────────────────────────────────────────

_GREETING_PATTERNS = _re.compile(
    r'^[\s]*(hi|hello|hey|salam|سلام|سلامت|สวัสดี|hallo|ciao|bonjour|hola|'
    r'good\s*(morning|afternoon|evening|night)|สวัสดี|merhaba|selam|hej|'
    r'howdy|yo|how\s*are\s*you|what\'?\s*up|sup|khubi|chetori|khobi)',
    _re.IGNORECASE,
)

_CODE_KEYWORDS = _re.compile(
    r'(```|def\s|class\s|function\s|import\s|from\s+\w+\s+import|'
    r'async\s+def|const\s|let\s|var\s|=>|return\s|if\s*\(|for\s*\(|'
    r'while\s*\(|try\s*{|except\s|raise\s|throw\s|new\s+\w+|'
    r'print\(|console\.log|SELECT\s|INSERT\s|UPDATE\s|DELETE\s)',
    _re.IGNORECASE,
)

_REASONING_KEYWORDS = _re.compile(
    r'(analyze|analyse|explain|compare|contrast|evaluate|reason|prove|'
    r'derive|derive|optimize|strategy|trade-?off|pros?\s*and\s*cons?|'
    r'logic|argument|hypothesis|theorem|algorithm|proof|'
    r'چرا|چگونه|تحلیل|مقایسه|ارزیابی|استراتژی)',
    _re.IGNORECASE,
)

_Creative_KEYWORDS = _re.compile(
    r'(write\s+a\s+(story|poem|essay|song|novel|article)|'
    r'creative|imagine|fiction|creative\s+writing|'
    r'داستان|شعر|خلاقیت)',
    _re.IGNORECASE,
)

# S1 verified live test 2026-07-16 (354 models, 3 working):
#   WORKING: mistral-large, mistral-medium-3-5, tencent-hy3 (all bynara)
#   kimi-k2.7-code-free -> 429 free daily quota (UNRELIABLE; do not route as primary)
# S1 Fix 2026-07-16: Only WORKING models (8 total: 3 mistral, 1 tencent, 2 deepseek, 2 mimo)
# See audit-v2/S1_MODEL_REPORT.md for live test results
_FREE_MODELS = [('tencent-hy3', 'bynara'), ('deepseek-v4-flash-bynara', 'bynara')]
_CODING_MODELS = [('deepseek-v4-pro', 'bynara'), ('mistral-large', 'bynara')]
_REASONING_MODELS = [('deepseek-v4-pro', 'bynara'), ('mimo-v2.5-pro', 'bynara')]
_CREATIVE_MODELS = [('mistral-large', 'bynara'), ('mistral-medium-3-5', 'bynara')]
_DEFAULT_MODEL = ('tencent-hy3', 'bynara')            # cheapest, 1M ctx, reliable
_ADVANCED_MODEL = ('deepseek-v4-pro', 'bynara')        # best reasoning
_PREMIUM_MODEL = ('mimo-v2.5-pro', 'bynara')           # premium coding


def _analyze_message(text: str) -> str:
    if not text or not text.strip():
        return 'simple'
    if _GREETING_PATTERNS.search(text):
        return 'greeting'
    if _CODE_KEYWORDS.search(text):
        return 'code'
    if _REASONING_KEYWORDS.search(text):
        return 'reasoning'
    if _Creative_KEYWORDS.search(text):
        return 'creative'
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    if len(text) > 500 or len(sentences) > 4:
        return 'complex'
    if len(text) > 200:
        return 'medium'
    return 'simple'


async def _get_user_balance(uid: int) -> int:
    if async_session is None:
        return 0
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
                {'uid': uid},
            )
            row = res.fetchone()
            return int(row.balance) if row else 0
    except Exception as e:
        logger.warning(f"_get_user_balance failed uid={uid}: {e}")
        return 0


async def _get_user_plan(uid: int) -> str:
    if async_session is None:
        return 'free'
    try:
        async with async_session() as session:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            res = await session.execute(
                select(Subscription)
                .where(
                    Subscription.user_id == uid,
                    Subscription.status == 'active',
                    (Subscription.ends_at.is_(None)) | (Subscription.ends_at > now),
                )
                .order_by(Subscription.created_at.desc())
                .limit(1)
            )
            sub = res.scalar_one_or_none()
            return sub.plan if sub else 'free'
    except Exception as e:
        logger.warning(f"_get_user_plan failed uid={uid}: {e}")
        return 'free'


def _select_smart_model(category: str, balance: int, plan: str) -> tuple[str, str]:
    if balance < 10000:
        return _FREE_MODELS[0]
    if category in ('greeting', 'simple'):
        return _FREE_MODELS[0]
    if plan in ('pro', 'enterprise', 'unlimited'):
        if category == 'complex':
            return _ADVANCED_MODEL
        if category == 'reasoning':
            return _REASONING_MODELS[1]
        if category == 'code':
            return _CODING_MODELS[0]
        if category == 'creative':
            return _CREATIVE_MODELS[1]
        return _DEFAULT_MODEL
    if category == 'complex':
        return _REASONING_MODELS[0]
    if category == 'reasoning':
        return _REASONING_MODELS[0]
    if category == 'code':
        return _CODING_MODELS[0]
    if category == 'creative':
        return _CREATIVE_MODELS[0]
    if category == 'medium':
        return _DEFAULT_MODEL
    return _DEFAULT_MODEL



async def _select_smart_model_safe(category: str, balance: int, plan: str) -> tuple[str, str]:
    model, provider = _select_smart_model(category, balance, plan)
    from chat import is_working_model
    if not await is_working_model(model):
        return _DEFAULT_MODEL
    return model, provider


@router.post('/v1/smart-chat')
async def smart_chat(request: Request, payload: ChatRequest) -> Response:
    """Smart Mode: auto-selects the cheapest model capable of handling the request."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    payload_dict = payload.model_dump(exclude_none=True)

    messages = payload_dict.get('messages', [])
    last_user_msg = ''
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get('role') == 'user':
            last_user_msg = msg.get('content', '')
            if isinstance(last_user_msg, list):
                parts = []
                for part in last_user_msg:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        parts.append(part.get('text', ''))
                last_user_msg = ' '.join(parts)
            break

    category = _analyze_message(last_user_msg)
    balance = await _get_user_balance(uid)
    plan = await _get_user_plan(uid)

    original_model = payload_dict.get('model', '')
    force_model = request.headers.get('X-Smart-Model', '').strip()
    if force_model and force_model.lower() != 'auto':
        # Whitelist validation for forced model
        from chat import _is_model_allowed
        if not await _is_model_allowed(force_model if '/' not in force_model else force_model.split('/', 1)[1]):
            logger.info(f"smart_chat blocked forced model={force_model} uid={uid}")
            return JSONResponse(
                {'error': {'message': f'مدل {force_model} در دسترس نیست', 'type': 'invalid_request', 'code': 'model_not_available'}},
                status_code=400,
            )
        if '/' in force_model:
            selected_provider, selected_model = force_model.split('/', 1)
        else:
            selected_model = force_model
            selected_provider = 'bynara2'
    else:
        selected_model, selected_provider = await _select_smart_model_safe(category, balance, plan)

    # P1: BillingService reserve (replaces _check_quota_pre with proper FOR UPDATE locking)
    # Fall back to legacy _check_quota_pre if BillingService fails
    reservation = None
    try:
        async with async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = BillingService(_repo)
            from chat import is_working_model
            _est_cost = 1000 if await is_working_model(selected_model) else 5000
            reservation = await _bill_svc.reserve(
                uid, Money(_est_cost),
                idempotency_key=f"smart:{secrets.token_hex(8)}",
                model=selected_model,
            )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return JSONResponse(
            {'error': {'message': 'insufficient wallet balance | موجودی کیف پول کافی نیست', 'type': 'quota_exceeded', 'code': 'balance'}},
            status_code=429,
        )
    except Exception as e:
        import traceback
        logger.warning(f"BillingService.reserve failed uid={uid}, falling back to legacy _check_quota_pre: {e}\n{traceback.format_exc()}")
        quota_err = await _check_quota_pre(uid)
        if quota_err is not None:
            return quota_err

    payload_dict['model'] = selected_model

    # Use helper for injection (S2 deduplication)
    try:
        injs = await get_injection_messages(uid)
        if injs:
            messages = inject_messages(messages, injs)
            payload_dict['messages'] = messages
    except Exception as e:
        logger.warning(f"smart_chat injection failed uid={uid}: {e}")

    # Compress old messages to reduce token usage (smart_chat)
    try:
        _orig = [m.copy() for m in payload_dict.get('messages', [])]
        payload_dict['messages'] = compress_messages(payload_dict.get('messages', []), preserve_last=2)
        _sav = estimate_savings(_orig, payload_dict['messages'])
        if _sav['savings_pct'] > 0:
            logger.info(f"Headroom smart: {_sav['savings_pct']}%% saved ({_sav['saved_chars']} chars)")
    except Exception as e:
        logger.debug(f"Compression skipped: {e}")

    stream = payload_dict.get('stream', False)
    if stream:
        # P1: Release reservation before streaming (stream billing handles actual cost in finally)
        if reservation:
            try:
                async with async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = BillingService(_rel_repo)
                    await _rel_svc.release(reservation['reservation_id'])
                    await _rel_session.commit()
            except Exception as _rel_e:
                logger.warning(f"BillingService.release before stream failed uid={uid}: {_rel_e}")
        return await _smart_chat_stream(payload_dict, request, selected_model, category)

    try:
        from chat import _resolve_provider
        _provider = await _resolve_provider(selected_model)
        r = await _http.post(
            f'{_provider.v1}/chat/completions',
            json=payload_dict,
            headers={**_provider.headers(), 'Accept': 'application/json'},
        )
        if r.status_code == 200:
            cost_info = await _track_usage(request, payload_dict, r.json())
            resp_data = r.json()
            if cost_info and cost_info.get('cost', 0) > 0:
                resp_data['billing'] = {
                    'cost': cost_info.get('cost', 0),
                    'input_tokens': cost_info.get('input_tokens', 0),
                    'output_tokens': cost_info.get('output_tokens', 0),
                    'balance_after': cost_info.get('balance_after', 0),
                    'currency': 'IRT',
                }
            # P1: Release reservation after successful billing (track_usage already wrote ledger)
            if reservation:
                try:
                    async with async_session() as _rel_session:
                        _rel_repo = SqlBillingRepo(_rel_session)
                        _rel_svc = BillingService(_rel_repo)
                        await _rel_svc.release(reservation['reservation_id'])
                        await _rel_session.commit()
                except Exception as _rel_e:
                    logger.warning(f"BillingService.release after success failed uid={uid}: {_rel_e}")
            resp = Response(content=json.dumps(resp_data), status_code=200, media_type='application/json')
        else:
            if reservation:
                try:
                    async with async_session() as _rel_session:
                        _rel_repo = SqlBillingRepo(_rel_session)
                        _rel_svc = BillingService(_rel_repo)
                        await _rel_svc.release(reservation['reservation_id'])
                        await _rel_session.commit()
                except Exception as _rel_e:
                    logger.warning(f"BillingService.release on upstream error failed uid={uid}: {_rel_e}")
            resp = Response(content=r.content, status_code=r.status_code, media_type='application/json')
        # P3: Fire background auto-memory extraction
        _fire_memory_extraction(uid, payload_dict.get('messages', []))
        resp.headers['X-Smart-Model'] = selected_model
        resp.headers['X-Smart-Category'] = category
        resp.headers['X-Smart-Provider'] = selected_provider
        if original_model and original_model != selected_model:
            resp.headers['X-Smart-Original-Model'] = original_model
        return resp
    except Exception as e:
        logger.warning(f"smart_chat gateway error uid={uid} model={selected_model}: {e}")
        # P1: Release reservation on error
        if reservation:
            try:
                async with async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = BillingService(_rel_repo)
                    await _rel_svc.release(reservation['reservation_id'])
                    await _rel_session.commit()
            except Exception as _rel_e:
                logger.warning(f"BillingService.release on error failed uid={uid}: {_rel_e}")
        return JSONResponse(
            {'detail': 'سرویس موقتاً در دسترس نیست', 'code': 'gateway_error'},
            status_code=502,
        )


async def _smart_chat_stream(
    payload: dict[str, Any],
    request: Request,
    selected_model: str,
    category: str,
):
    """Stream smart chat completion via SSE."""
    uid = await _get_user_id(request)

    # Dedup guard + helper (previously duplicated)
    if uid:
        try:
            injs = await get_injection_messages(uid)
            if injs:
                payload['messages'] = inject_messages(payload.get('messages', []), injs)
        except Exception as e:
            logger.warning(f"_smart_chat_stream injection failed uid={uid}: {e}")

    async def event_stream():
        usage_data = None
        try:
            payload['stream'] = True
            payload.setdefault('stream_options', {})
            if isinstance(payload['stream_options'], dict):
                payload['stream_options']['include_usage'] = True
            import httpx
            from chat import _resolve_provider
            _provider = await _resolve_provider(selected_model)
            async with _http.stream(
                'POST',
                f'{_provider.v1}/chat/completions',
                json=payload,
                headers={**_provider.headers(), 'Accept': 'text/event-stream'},
                timeout=httpx.Timeout(90, connect=10, read=90),
            ) as r:
                yield f'data: {json.dumps({"type": "smart_info", "model": selected_model, "category": category})}\n\n'
                async for line in r.aiter_lines():
                    if await request.is_disconnected():
                        logger.info(f"_smart_chat_stream disconnected uid={uid} model={selected_model}")
                        break
                    if line:
                        stripped = line.strip()
                        if stripped.startswith('data:'):
                            data_str = stripped[5:].strip()
                            if data_str == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data_str)
                                if isinstance(chunk.get('usage'), dict) and chunk['usage']:
                                    usage_data = chunk['usage']
                            except (json.JSONDecodeError, ValueError):
                                pass
                        yield f'{line}\n\n'
        except Exception as e:
            logger.warning(f"_smart_chat_stream error uid={uid} model={selected_model}: {e}")
            yield f'data: {json.dumps({"error": f"upstream unavailable: {e}"})}\n\n'
        finally:
            if uid and usage_data and async_session is not None:
                try:
                    cost_info = await _bill_stream_usage(uid, payload, usage_data)
                    if cost_info and cost_info.get('cost', 0) > 0:
                        billing_event = json.dumps({
                            'type': 'billing',
                            'cost': cost_info.get('cost', 0),
                            'input_tokens': cost_info.get('input_tokens', 0),
                            'output_tokens': cost_info.get('output_tokens', 0),
                            'balance_after': cost_info.get('balance_after', 0),
                            'currency': 'IRT',
                        })
                        yield f'data: {billing_event}\n\n'
                except Exception as e:
                    logger.warning(f"_smart_chat_stream billing emit failed uid={uid}: {e}")
            # P3: Fire background auto-memory extraction (streaming)
            if uid:
                _fire_memory_extraction(uid, payload.get('messages', []))

    response = StreamingResponse(event_stream(), media_type='text/event-stream')
    response.headers['X-Smart-Model'] = selected_model
    response.headers['X-Smart-Category'] = category
    return response
