"""The /v1/smart-chat path -- split out of chat.py (see chat.py's module
docstring for why). The streaming half (`_smart_chat_stream`) lives in
chat_stream.py alongside `_chat_stream` (both SSE loops share the same
shape/rationale); this file holds message classification, model selection,
and the non-streaming request/response cycle.

MONKEYPATCH CONTRACT: tests patch `chat_mod._get_user_id`,
`chat_mod._resolve_public_model`, `chat_mod._is_model_allowed`,
`chat_mod._resolve_provider`, `chat_mod._safe_default_model`,
`chat_mod.check_and_consume`, `chat_mod.BillingService`,
`chat_mod.async_session`, `chat_mod._http`, `chat_mod._track_usage`,
`chat_mod.get_injection_messages`, and `chat_mod.is_working_model` directly
on the `chat` module (see chat.py's module docstring for the full
contract). Every one of those names is resolved through `chat.<name>` at
call time below, never via `from chat import X`. `chat` is imported plainly
at module scope, which is safe against the chat.py <-> chat_smart.py
circular import: nothing here touches a `chat` attribute until a function
actually runs, by which point chat.py has finished executing.
"""
from __future__ import annotations

import json
import logging
import re as _re
import secrets
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from models import Subscription
from services.context_injection import inject_messages
from services.token_budget import apply_outbound_budget
from services.billing import SqlBillingRepo, InsufficientBalanceError
from services.money import Money
from services.entitlement_gate import covering_entitlement
from middleware.compression import compress_messages, estimate_savings
from model_output import clean_response_dict
from i18n import err, err_openai

import chat
from providers import COMPLETION_TIMEOUT_SECONDS
from chat import ChatRequest

logger = logging.getLogger('chat')  # keep all chat_*.py logs under the pre-split 'chat' logger name

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
    if chat.async_session is None:
        return 0
    try:
        async with chat.async_session() as session:
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
    if chat.async_session is None:
        return 'free'
    try:
        async with chat.async_session() as session:
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
    if not await chat.is_working_model(model):
        return _DEFAULT_MODEL
    return model, provider

# Working model set (confirmed via live test 2026-07-16)
# _WORKING_SET moved to top of file (near WORKING_MODELS)

@chat.router.post('/v1/smart-chat')
async def smart_chat(request: Request, payload: ChatRequest) -> Response:
    """Smart Mode: auto-selects the cheapest model capable of handling the request."""
    uid = await chat._get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    _disabled = await chat._chat_preflight(uid, payload.messages)
    if _disabled is not None:
        return _disabled

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
        # Canonicalize to provider_model_id FIRST -- see _resolve_public_model's
        # docstring. This REPLACES the old `force_model.split('/', 1)[1]`
        # slash-split: that produced a bare model name (e.g. "mistral-large"
        # from "sanjab/mistral-large") which is a DIFFERENT physical
        # model_catalog row (a degraded litellm one) with its own route and
        # price -- wrong route AND wrong billing row. The resolver looks up
        # the real provider_model_id instead of guessing from string shape.
        selected_model = await chat._resolve_public_model(force_model)
        if not await chat._is_model_allowed(selected_model):
            logger.info(f"smart_chat blocked forced model={force_model} uid={uid}")
            return err_openai(
            f'مدل {force_model} در دسترس نیست',
            f'Model {force_model} is not available',
            400, code='model_not_available', err_type='invalid_request',
        )
        selected_provider = selected_model.split('/', 1)[0] if '/' in selected_model else 'bynara2'
        # Display label: echo back exactly what the caller sent in the
        # X-Smart-Model request header, never the resolved provider_model_id
        # -- a normal user must never see which upstream route a model
        # resolved to (see content.py's no-provider-leak rule). Only the
        # forced-model path needs this: the auto-selection branch below
        # already returns bare/hardcoded ids that predate public_id and were
        # never gated behind this rule.
        smart_model_label = force_model
    else:
        selected_model, selected_provider = await _select_smart_model_safe(category, balance, plan)
        smart_model_label = selected_model

    # FIX 2: counteract the injected caveman-style system prompt -- see
    # chat()'s comment / _REASONING_INJECTING_PROVIDERS docstring. Runs on
    # `messages` (the client's original list, untouched so far) before the
    # memory/web-search injections below; `messages` is kept in sync with
    # payload_dict['messages'] afterward since later code still reads the
    # local variable.
    await chat._apply_persian_style_guard_for_model(payload_dict, selected_model)
    messages = payload_dict.get('messages', messages)

    # Free-tier throttle gate — before any reservation is opened.
    _ft_gate = await chat.check_and_consume(uid, [selected_model])
    if _ft_gate is not None:
        return chat._free_tier_response(_ft_gate)

    # Premium (expensive-model) sub-allowance gate — same position and same
    # reasoning as the free-tier gate above: post-model, pre-reserve.
    _premium_gate = await chat.premium_check_and_consume(uid, [selected_model])
    if _premium_gate is not None:
        return chat._premium_quota_response(_premium_gate)

    # P1: BillingService reserve (replaces _check_quota_pre with proper FOR UPDATE locking)
    # Fall back to legacy _check_quota_pre if BillingService fails
    reservation = None
    try:
        async with chat.async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = chat.BillingService(_repo)
            _est_cost = 1000 if await chat.is_working_model(selected_model) else 5000
            # Package quota covers this request -> skip the wallet reservation
            # (reservation stays None; the release/settle code below already
            # treats None as a no-op). See services/entitlement_gate.py.
            if await covering_entitlement(uid, _est_cost) is not None:
                reservation = None
            else:
                reservation = await _bill_svc.reserve(
                    uid, Money(_est_cost),
                    idempotency_key=f"smart:{secrets.token_hex(8)}",
                    model=selected_model,
                )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return err_openai(
            'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.',
            'Your wallet balance is not enough. Please top up your account.',
            429, code='balance', err_type='quota_exceeded',
        )
    except Exception as e:
        import traceback
        logger.warning(f"BillingService.reserve failed uid={uid}, falling back to legacy _check_quota_pre: {e}\n{traceback.format_exc()}")
        quota_err = await chat._check_quota_pre(uid)
        if quota_err is not None:
            return quota_err

    payload_dict['model'] = selected_model

    # Use helper for injection (S2 deduplication)
    try:
        injs = await chat.get_injection_messages(uid, messages=messages)
        if injs:
            messages = inject_messages(messages, injs)
            payload_dict['messages'] = messages
    except Exception as e:
        logger.warning(f"smart_chat injection failed uid={uid}: {e}")

    # Web search injection (shared helper -- see _apply_web_search). Previously
    # smart-chat never read `web_search` at all: the flag was silently dropped
    # AND the stray key was forwarded upstream in the JSON body unread.
    await chat._apply_web_search(payload_dict, handler='smart-chat')

    # Compress old messages to reduce token usage (smart_chat)
    try:
        _orig = [m.copy() for m in payload_dict.get('messages', [])]
        payload_dict['messages'] = compress_messages(payload_dict.get('messages', []), preserve_last=2)
        _sav = estimate_savings(_orig, payload_dict['messages'])
        if _sav['savings_pct'] > 0:
            logger.info(f"Headroom smart: {_sav['savings_pct']}%% saved ({_sav['saved_chars']} chars)")
    except Exception as e:
        logger.debug(f"Compression skipped: {e}")

    # Phase E ceiling -- see services/token_budget.py.
    await apply_outbound_budget(payload_dict)

    stream = payload_dict.get('stream', False)
    if stream:
        # P1: Release reservation before streaming (stream billing handles actual cost in finally)
        if reservation:
            try:
                async with chat.async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = chat.BillingService(_rel_repo)
                    await _rel_svc.release(reservation['reservation_id'])
                    await _rel_session.commit()
            except Exception as _rel_e:
                logger.warning(f"BillingService.release before stream failed uid={uid}: {_rel_e}")
        return await chat._smart_chat_stream(payload_dict, request, selected_model, category, display_model=smart_model_label)

    try:
        _provider = await chat._resolve_provider(selected_model)
        r = await chat._http.post(
            f'{_provider.v1}/chat/completions',
            json=payload_dict,
            headers={**_provider.headers(), 'Accept': 'application/json'},
            timeout=COMPLETION_TIMEOUT_SECONDS,
        )
        if r.status_code == 200:
            resp_data = r.json()
            # Bill on the RAW upstream response -- see the identical
            # comment in chat() above.
            cost_info = await chat._track_usage(request, payload_dict, resp_data)
            resp_data = clean_response_dict(resp_data)
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
                    async with chat.async_session() as _rel_session:
                        _rel_repo = SqlBillingRepo(_rel_session)
                        _rel_svc = chat.BillingService(_rel_repo)
                        await _rel_svc.release(reservation['reservation_id'])
                        await _rel_session.commit()
                except Exception as _rel_e:
                    logger.warning(f"BillingService.release after success failed uid={uid}: {_rel_e}")
            resp = Response(content=json.dumps(resp_data), status_code=200, media_type='application/json')
        else:
            if reservation:
                try:
                    async with chat.async_session() as _rel_session:
                        _rel_repo = SqlBillingRepo(_rel_session)
                        _rel_svc = chat.BillingService(_rel_repo)
                        await _rel_svc.release(reservation['reservation_id'])
                        await _rel_session.commit()
                except Exception as _rel_e:
                    logger.warning(f"BillingService.release on upstream error failed uid={uid}: {_rel_e}")
            resp = Response(content=r.content, status_code=r.status_code, media_type='application/json')
        # P3: Fire background auto-memory extraction
        chat._fire_memory_extraction(uid, payload_dict.get('messages', []))
        resp.headers['X-Smart-Model'] = smart_model_label
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
                async with chat.async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = chat.BillingService(_rel_repo)
                    await _rel_svc.release(reservation['reservation_id'])
                    await _rel_session.commit()
            except Exception as _rel_e:
                logger.warning(f"BillingService.release on error failed uid={uid}: {_rel_e}")
        # Same site as chat.py's identical gateway-error handler (already
        # converted) -- matches that precedent, including dropping the
        # unused 'code': 'gateway_error' key (nothing reads it; the frontend
        # only special-cases code == 'balance', see useChatStream.ts).
        return err('سرویس موقتاً در دسترس نیست', 'The service is temporarily unavailable.', 502)
