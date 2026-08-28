"""Chat endpoints: /v1/chat/completions, /v1/chat/with-file, /v1/smart-chat,
/v1/compare.

Includes streaming, usage tracking, web search, and smart model selection.

S2 fixes:
- Extract memory/soul injection to services/context_injection.py with limits & sanitization
- Replace silent except: pass with logger.warning
- Add model whitelist validation (DB + hardcoded working set)
- Add streaming timeout & client disconnect handling
- Fix default model for file chat (mimo disabled -> tencent-hy3)

MODULE SPLIT (house 500-line cap; this file used to be ~2,500 lines) --
chat.py is now the router PLUS a namespace facade: it owns
/v1/chat/completions directly, and re-exports everything the sibling
modules and the rest of the app need to keep resolving as `chat.<name>`:
chat_models.py (model resolution), chat_web.py (file/web-search +
/v1/chat/with-file), chat_billing.py (usage/billing), chat_stream.py (SSE
loops), chat_compare.py (/v1/compare), chat_smart.py (/v1/smart-chat).

MONKEYPATCH CONTRACT: tests patch functions AND raw mutable cache state
directly on THIS module (`chat_mod._resolve_provider = ...`,
`chat_mod.async_session = ...`, `chat_mod._UPSTREAM_CACHE = {}`, etc.), not
on whichever chat_*.py file actually defines them now. Every chat_*.py
module does a plain `import chat` (safe against the circular import --
nothing touches a `chat` attribute until a function runs, by which point
this file has finished executing) and reaches such names through
`chat.<name>` at call time, never `from chat import X`. See each
chat_*.py module's own docstring for its exact dependency list. A few
small, heavily-shared helpers (_release_reservation, _persian_duration,
_free_tier_response, _as_naive_utc, _check_quota_pre) stay physically in
THIS file so every other module has exactly one place to reach into.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from i18n import err, err_openai
from database import async_session, _http
from models import Assistant
from dependencies import _get_user_id, _to_fa
from services.context_injection import get_injection_messages, inject_messages
from services.token_budget import apply_outbound_budget
from services.billing import SqlBillingRepo, BillingService, InsufficientBalanceError
from services.money import Money
from services.entitlement_gate import covering_entitlement
from services.memory_extractor import extract_memories, MIN_MSG_COUNT
from services.free_tier import check_and_consume, covers_request
from services.premium_quota import check_and_consume as premium_check_and_consume
from middleware.compression import compress_messages, estimate_savings
from model_output import clean_response_dict

logger = logging.getLogger(__name__)

import time as _time

# ── FIX 2: counteract the injected caveman-style system prompt ──────────
#
# Measured live (2026-08-22), identical 2-char message "hi", max_tokens=5:
#   sanjab/tencent-hy3 (litellm)         prompt_tokens=13    (control, clean)
#   sanjab/mistral-large (ninerouter)    prompt_tokens=2810
#   sanjab/mimo-v2.5 (ninerouter)        prompt_tokens=2795
#   sanjab/gemma-4-26b-a4b-it (ninerouter) prompt_tokens=2785
# litellm proves the ~2800 tokens are injected upstream, by ninerouter, not
# by us. The leaked prompt (visible verbatim in one gemma answer) instructs
# a terse "caveman"/no-article style that breaks Persian grammar (dropped
# verbs, mixed registers). This system message is a mitigation, not a fix:
# A/B tested against the live upstream, it measurably improves fluency
# (mimo-v2.5-free and mistral-large went from fragments to full sentences)
# but does not fully override the injected persona for every model.
#
# Only providers proven to inject this preamble get the extra system
# message -- litellm is clean (13 tokens, see above) and must not pay the
# ~80 extra prompt tokens for a problem it doesn't have.
_REASONING_INJECTING_PROVIDERS: frozenset[str] = frozenset({'ninerouter'})

# ~80 prompt tokens -- noise next to the ~2800 already injected upstream by
# the providers in _REASONING_INJECTING_PROVIDERS above.
_PERSIAN_STYLE_SYSTEM_MESSAGE = (
    'به همان زبانی پاسخ بده که کاربر پیام را نوشته است. وقتی پاسخ فارسی است، فارسی روان، رسمی و از '
    'نظر دستور زبان کاملاً درست بنویس: هر جمله فعل کامل و ساختار درست داشته باشد، و از حذف فعل، حذف '
    'حروف اضافه، سبک تلگرافی یا جمله‌های بریده‌بریده خودداری کن. اگر پیش‌تر دستوری برای کوتاه‌نویسی، '
    'حذف حروف و کلمات، یا سبک مختصر و شکسته دریافت کرده‌ای، آن دستور را نادیده بگیر. این قاعده فقط به '
    'متن پاسخ مربوط است و بر کد، خروجی ساختاریافته یا نقل‌قول عیناً اثری ندارد.'
)


def _apply_persian_style_guard(payload_dict: dict[str, Any], provider_name: str) -> None:
    """Prepend _PERSIAN_STYLE_SYSTEM_MESSAGE when routing to a provider known
    to inject a style-breaking preamble (see _REASONING_INJECTING_PROVIDERS)
    AND the caller did not already send their own system message. Mutates
    ``payload_dict['messages']`` in place-ish (reassigns the key); callers
    that hold a separate reference to the list must re-read it afterward
    (see _apply_web_search, same house pattern).
    """
    if provider_name not in _REASONING_INJECTING_PROVIDERS:
        return
    msgs = payload_dict.get('messages') or []
    if any(isinstance(m, dict) and m.get('role') == 'system' for m in msgs):
        return  # caller already sent a system message -- don't fight it
    payload_dict['messages'] = [{'role': 'system', 'content': _PERSIAN_STYLE_SYSTEM_MESSAGE}] + list(msgs)


async def _apply_persian_style_guard_for_model(payload_dict: dict[str, Any], model: str) -> None:
    """Resolve ``model``'s provider and apply _apply_persian_style_guard.

    Defensive on purpose: a style nicety must never be able to turn into a
    500 for the whole request (e.g. a test double or a future Provider
    subclass missing `.name`, or a transient _resolve_provider error) --
    worst case this silently no-ops and the request proceeds unstyled.
    """
    if not model:
        return
    try:
        provider = await _resolve_provider(model)
        _apply_persian_style_guard(payload_dict, getattr(provider, 'name', ''))
    except Exception as e:
        logger.warning(f"_apply_persian_style_guard_for_model failed model={model}: {e}")


def _record_model_health(
    model_id: str, *, ok: bool, latency_ms: int | None = None, error: str | None = None
) -> None:
    """Record a passive health sample for a real request, off the response path.

    Fire-and-forget on purpose: the user's completion has already succeeded or
    failed by this point, and a health-table write must never add latency to it
    or turn a good response into an error. Imported lazily so chat.py does not
    depend on model_health at import time.
    """
    if not model_id:
        return
    try:
        from model_health import record_traffic

        task = asyncio.create_task(
            record_traffic(model_id, ok, latency_ms=latency_ms, error=error)
        )
        # Hold a reference so the task is not garbage-collected mid-flight.
        _HEALTH_TASKS.add(task)
        task.add_done_callback(_HEALTH_TASKS.discard)
    except Exception:
        pass


_HEALTH_TASKS: set[asyncio.Task] = set()

router = APIRouter()


def _fire_memory_extraction(uid: int, messages: list[dict[str, Any]]) -> None:
    """Schedule background auto-memory extraction if conversation has enough messages."""
    if uid and messages and len(messages) > MIN_MSG_COUNT:
        # Capture a copy of messages to avoid mutation issues
        msgs_snapshot = [dict(m) for m in messages[-40:]]  # Keep last 40 max
        asyncio.create_task(extract_memories(uid, msgs_snapshot))


class ChatRequest(BaseModel):
    model: str = ''
    messages: list = []
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    web_search: bool = False
    assistant_id: int | None = None


class CompareRequest(BaseModel):
    model_a: str
    model_b: str
    messages: list = []
    stream: bool = False


# ── Model resolution / availability (chat_models.py) ──────────────────
#
# These caches stay defined HERE, not in chat_models.py (where the
# functions using them now live), because tests reset them directly via
# `chat_mod._UPSTREAM_CACHE = {}` etc. (test_provider_routing.py,
# test_public_model_ids.py) rather than through a monkeypatched function;
# chat_models.py reads/writes this state via `chat.<name>` -- see its
# docstring.
_WORKING_SET_CACHE: set[str] | None = None
_UPSTREAM_CACHE: dict[str, str] = {}
_UPSTREAM_CACHE_LOADED_AT: float = 0.0
_MODEL_RESOLVE_CACHE: dict[str, str] = {}
_MODEL_RESOLVE_CACHE_LOADED_AT: float = 0.0

from chat_models import (
    _get_model_upstream,
    _resolve_public_model,
    _safe_default_model,
    _resolve_provider, COMPLETION_TIMEOUT_SECONDS,
    get_working_models,
    is_working_model,
    _is_model_allowed,
)


# ── Shared helpers ──────────────────────────────────────────────
#
# `_release_reservation` and `_check_quota_pre` are defined in chat_web.py
# and chat_compare.py respectively -- not here -- purely to keep this file
# under the 500-line house cap (they have no `chat`-specific reason to live
# there over here; see those modules' docstrings). Both are re-exported
# below so every other module keeps reaching them as `chat.<name>`.

def _persian_duration(seconds: int) -> str:
    """Render a countdown in Persian for the free-tier throttle message
    (e.g. 15600 -> "۴ ساعت و ۲۰ دقیقه")."""
    seconds = max(int(seconds), 0)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours and minutes:
        return f'{_to_fa(hours)} ساعت و {_to_fa(minutes)} دقیقه'
    if hours:
        return f'{_to_fa(hours)} ساعت'
    if minutes:
        return f'{_to_fa(minutes)} دقیقه'
    return f'{_to_fa(max(seconds, 1))} ثانیه'


def _free_tier_response(gate: dict) -> JSONResponse:
    """429 for the free-tier gate (services/free_tier.py) -- NOT the package
    message quota (chat_web._user_quota_response, a different error.code). The
    Persian message differs by reason (cheap-model / lifetime / hourly) and is
    built in free_tier.py; this renders it verbatim so the reason-specific text
    lives in one place and chat.py stays under the house line cap."""
    return JSONResponse(
        {'error': {
            'message': gate.get('message', 'محدودیت حساب رایگان اعمال شد.'),
            # The gate builds a reason-specific pair (services/free_tier.py,
            # services/premium_quota.py); these defaults only cover a gate
            # shape that predates them.
            'message_en': gate.get('message_en', 'A free-tier limit has been reached.'),
            'type': 'rate_limited',
            'code': gate.get('code', 'free_tier_throttle'),
            'model': gate.get('model', ''),
            'retry_after_seconds': int(gate.get('retry_after_seconds', 0)),
        }},
        status_code=429,
    )


def _as_naive_utc(dt: datetime | None) -> datetime | None:
    """Normalize a datetime that MAY be timezone-aware to this codebase's
    naive-UTC convention (see models.py::_utcnow(), used for every other
    timestamp column).

    quota.reset_at is a TIMESTAMPTZ column; asyncpg/SQLAlchemy returns it as
    a timezone-AWARE datetime when read back, while `datetime.now(timezone.
    utc).replace(tzinfo=None)` (used everywhere else in this file) is naive.
    Comparing the two directly raises `TypeError: can't compare offset-naive
    and offset-aware datetimes`. Found live: that TypeError was being
    silently swallowed by a broad `except Exception` in both
    _check_quota_pre and _record_usage, which rolled back the *entire*
    billing transaction (ledger + quota + wallet) every time a quota row's
    reset_at needed a rollover comparison -- a served, billable request
    recorded as if it never happened, purely because of a tz mismatch.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ── File text extraction / web search / /v1/chat/with-file (chat_web.py) ──
from chat_web import _apply_web_search, _web_search, _release_reservation, _chat_disabled_response, _chat_preflight, _premium_quota_response  # noqa: E402 -- also registers /v1/chat/with-file


# ── Usage estimation / billing (chat_billing.py) ──────────────────────
from chat_billing import (  # noqa: E402
    ESTIMATE_CHARS_PER_TOKEN,
    FALLBACK_PRICE_PER_MILLION_IN,
    FALLBACK_PRICE_PER_MILLION_OUT,
    _estimate_tokens_from_chars,
    _estimate_message_text_chars,
    _estimate_input_tokens,
    _estimate_output_tokens,
    _extract_reasoning_tokens,
    _usage_idempotency_key,
    _extract_response_text,
    _record_usage,
    _track_usage,
    _bill_stream_usage,
)


# ── SSE streaming (chat_stream.py) ────────────────────────────────────
from chat_stream import _chat_stream, _smart_chat_stream  # noqa: E402


# ── Routes ──────────────────────────────────────────────────────

@router.post('/v1/chat/completions')
async def chat(request: Request, payload: ChatRequest) -> Response:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)
    _disabled = await _chat_preflight(uid, payload.messages)
    if _disabled is not None:
        return _disabled

    payload_dict = payload.model_dump(exclude_none=True)

    # Canonicalize a public_id (or any legacy id) to provider_model_id, or
    # resolve a live catalog default when the client sent none at all --
    # BOTH must happen here, before the free-tier gate/reservation/
    # validation/upstream call below (see _resolve_public_model's and
    # _safe_default_model's docstrings), so every gate from this point on
    # sees the exact same final model id used for routing and billing.
    # Previously the empty-model case fell through to a hardcoded
    # 'tencent-hy3' literal much further down (right before the whitelist
    # check), which is why the free-tier/reservation calls below used their
    # own separate `or 'tencent-hy3'` fallbacks -- three independent copies
    # of a literal that rotted out of the catalog together (FIX 3).
    if payload_dict.get('model'):
        payload_dict['model'] = await _resolve_public_model(payload_dict['model'])
    else:
        payload_dict['model'] = await _safe_default_model()

    # FIX 2: counteract the injected caveman-style system prompt some
    # upstream routes prepend server-side -- see
    # _REASONING_INJECTING_PROVIDERS/_apply_persian_style_guard above. Must
    # run on the client's ORIGINAL messages, before the assistant/memory/
    # web-search system-message injections below, so "the client sent a
    # system message" means what it says.
    await _apply_persian_style_guard_for_model(payload_dict, payload_dict.get('model', ''))

    # Free-tier throttle gate — must run before any reservation is opened
    # (see services/free_tier.py: rejecting pre-reserve means there is never
    # a reservation to unwind, and reserve() call sites below are wrapped in
    # a broad except that would otherwise swallow anything raised here).
    _ft_gate = await check_and_consume(uid, [payload_dict['model']]) if payload_dict.get('model') else None
    if _ft_gate is not None:
        return _free_tier_response(_ft_gate)

    # Premium (expensive-model) sub-allowance gate — same position and same
    # reasoning as the free-tier gate above: post-model (it prices the model),
    # pre-reserve (a rejection must leave no reservation to unwind).
    _premium_gate = await premium_check_and_consume(uid, [payload_dict['model']]) if payload_dict.get('model') else None
    if _premium_gate is not None:
        return _premium_quota_response(_premium_gate)

    # P1: BillingService reserve (replaces _check_quota_pre with proper FOR UPDATE locking)
    # Fall back to legacy _check_quota_pre if BillingService fails
    reservation = None
    try:
        async with async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = BillingService(_repo)
            _model = payload_dict.get('model', '')
            _est_cost = 1000 if (_model and await is_working_model(_model)) else 5000
            if await covering_entitlement(uid, _est_cost) is not None or await covers_request(uid):
                reservation = None
            else:
                reservation = await _bill_svc.reserve(
                    uid, Money(_est_cost),
                    idempotency_key=f"chat:{secrets.token_hex(8)}",
                    model=_model,
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
        quota_err = await _check_quota_pre(uid)
        if quota_err is not None:
            return quota_err

    # --- Model whitelist validation ---
    model_to_check = payload_dict.get('model', '')
    if not model_to_check:
        # _safe_default_model() couldn't find anything in the catalog
        # either -- never send an empty/garbage model string upstream (an
        # unresolved id misses the billing price lookup and bills the
        # fallback ceiling rate, see _resolve_public_model's docstring).
        await _release_reservation(reservation, uid, 'no_model_available')
        return err_openai(
            'در حال حاضر مدلی برای انتخاب پیش‌فرض در دسترس نیست. لطفاً یک مدل را به‌صورت دستی انتخاب کنید.',
            'No model is available to pick by default right now. Please choose one manually.',
            400, code='model_not_available', err_type='invalid_request',
        )
    if not await _is_model_allowed(model_to_check):
        logger.info(f"chat blocked: model={model_to_check} uid={uid} not allowed")
        await _release_reservation(reservation, uid, 'model_reject')
        return err_openai(
            f'مدل {model_to_check} در دسترس نیست',
            f'Model {model_to_check} is not available',
            400, code='model_not_available', err_type='invalid_request',
        )

    # Assistant injection
    _assistant_id = payload_dict.pop('assistant_id', None)
    if _assistant_id and async_session is not None:
        try:
            async with async_session() as _asession:
                _ares = await _asession.execute(
                    Assistant.__table__.select().where(Assistant.id == int(_assistant_id))
                )
                _arow = _ares.fetchone()
                if _arow and _arow.system_prompt:
                    _sys_msg = {'role': 'system', 'content': _arow.system_prompt}
                    _msgs = payload_dict.get('messages', [])
                    _msgs.insert(0, _sys_msg)
                    payload_dict['messages'] = _msgs
                    if _arow.model_id and not payload_dict.get('model'):
                        payload_dict['model'] = _arow.model_id
        except Exception as e:
            logger.warning(f"chat assistant injection failed aid={_assistant_id} uid={uid}: {e}")

    # Memory + soul injection via helper (S2 fix duplication + limits + sanitization)
    try:
        injs = await get_injection_messages(uid, messages=payload_dict.get('messages'))
        if injs:
            payload_dict['messages'] = inject_messages(payload_dict.get('messages', []), injs)
    except Exception as e:
        logger.warning(f"chat injection failed uid={uid}: {e}")

    # Web search injection (shared helper -- see _apply_web_search)
    await _apply_web_search(payload_dict, handler='chat.completions')

    # Compress old messages to reduce token usage
    try:
        _orig = [m.copy() for m in payload_dict.get('messages', [])]
        payload_dict['messages'] = compress_messages(payload_dict.get('messages', []), preserve_last=2)
        _sav = estimate_savings(_orig, payload_dict['messages'])
        if _sav['savings_pct'] > 0:
            logger.info(f"Headroom: {_sav['savings_pct']}%% saved ({_sav['saved_chars']} chars)")
    except Exception as e:
        logger.debug(f"Compression skipped: {e}")

    # Phase E: the only ceiling on outbound payload size / output tokens now
    # that the upstream-side compression is gone. See services/token_budget.py.
    await apply_outbound_budget(payload_dict)

    stream = payload_dict.get('stream', False)
    if stream:
        await _release_reservation(reservation, uid, 'before_stream')
        return await _chat_stream(payload_dict, request)
    _hc_model = str(payload_dict.get('model') or '')
    _hc_started = _time.monotonic()
    try:
        _provider = await _resolve_provider(_hc_model)
        r = await _http.post(f'{_provider.v1}/chat/completions', json=payload_dict, headers={**_provider.headers(), 'Accept': 'application/json'}, timeout=COMPLETION_TIMEOUT_SECONDS)
        # Passive health sample. Real traffic is the best signal we have about
        # whether a model works, and it costs nothing extra to record.
        _record_model_health(
            _hc_model,
            ok=r.status_code == 200,
            latency_ms=int((_time.monotonic() - _hc_started) * 1000),
            error=None if r.status_code == 200 else f'http_{r.status_code}',
        )
        if r.status_code == 200:
            resp_data = r.json()
            # Bill on the RAW upstream response (unchanged) -- see FIX 1 in
            # model_output.py's module docstring: cleaning must not affect
            # billing amounts. Only the copy returned to the client is
            # scrubbed of leaked <thought>/<think> reasoning blocks.
            cost_info = await _track_usage(request, payload_dict, resp_data)
            resp_data = clean_response_dict(resp_data)
            if cost_info and cost_info.get('cost', 0) > 0:
                resp_data['billing'] = {
                    'cost': cost_info.get('cost', 0),
                    'input_tokens': cost_info.get('input_tokens', 0),
                    'output_tokens': cost_info.get('output_tokens', 0),
                    'balance_after': cost_info.get('balance_after', 0),
                    'currency': 'IRT',
                }
            # P1: Release reservation after successful billing
            await _release_reservation(reservation, uid, 'after_success')
            # P3: Fire background auto-memory extraction
            _fire_memory_extraction(uid, payload_dict.get('messages', []))
            return Response(content=json.dumps(resp_data), status_code=200, media_type='application/json')
        await _release_reservation(reservation, uid, 'upstream_error')
        return Response(content=r.content, status_code=r.status_code, media_type='application/json')
    except Exception as e:
        logger.warning(f"chat gateway error uid={uid} model={payload_dict.get('model')}: {e}")
        _record_model_health(
            _hc_model,
            ok=False,
            latency_ms=int((_time.monotonic() - _hc_started) * 1000),
            error=type(e).__name__,
        )
        await _release_reservation(reservation, uid, 'on_error')
        return err('سرویس موقتاً در دسترس نیست', 'The service is temporarily unavailable.', 502)


# /v1/chat/with-file -> chat_web.py (imported above; registers itself on
# `router` via the @chat.router.post decorator at import time).

# /v1/compare -> chat_compare.py
from chat_compare import compare_models, _check_quota_pre  # noqa: E402

# /v1/smart-chat -> chat_smart.py.
from chat_smart import smart_chat  # noqa: E402
