"""The non-streaming tool-calling loop (Phase 8, packet B4).

Owns exactly steps 3-5 of the design (``docs/design-phase8.md`` §ب‑۴):
``reserve(MAX_TOOL_ROUNDS × est_cost)`` → up to ``MAX_TOOL_ROUNDS`` rounds of
upstream call + direct-debit billing + (maybe) one tool dispatch → release
the reservation exactly once. Steps 1-2 (model resolution, the free-tier →
premium gate order) are `chat.py`'s job, UNCHANGED, and stay there -- this
module never touches a gate and is proven not to by
``test_module_never_touches_the_gates_gate_order_stays_chatpys_job`` below.

WHEN THIS RUNS AT ALL: `run_tool_loop` is only meant to be called for a
request where the client set ``ChatRequest.tools`` to something non-None --
i.e. asked to opt into the loop. `payload_dict['tools']` (a caller-supplied
value) is read for exactly that yes/no signal and NEVER for its content:
the array actually sent upstream always comes from
``services.chat_tools.TOOL_SCHEMAS``, filtered through
``announced_tools(autonomy_level)`` -- see `_build_upstream_tools` and
`test_caller_supplied_tool_definition_never_reaches_the_upstream_payload`.
Passing a caller's schema through would hand an API caller an open dispatch
surface (the "closed action space, not filtered" line in §ب‑۵). For the
99% of traffic that never sets `tools` at all, `chat.py`'s existing
single-round reserve-and-call code is untouched and this module is never
invoked -- a true no-op, matching the senior's note that
`exclude_none=True` already makes the bare field addition inert.

MONKEYPATCH CONTRACT (matches chat_billing.py / chat_web.py / chat_stream.py
/ chat_style_guard.py / task_execution.py): `import chat` plainly at module
scope, every access is `chat.<name>` AT CALL TIME (never `from chat import
X`), so a test (or, once wired, an existing chat.py-level test) that patches
`chat_mod.async_session`, `chat_mod._resolve_provider`, `chat_mod._http`,
`chat_mod._track_usage`, `chat_mod._release_reservation`,
`chat_mod._record_model_health`, `chat_mod._fire_memory_extraction`, or
`chat_mod.is_working_model` is observed here too. Safe against the
chat.py <-> chat_tool_loop.py circular import for the same reason those
other modules document: nothing at THIS module's top level touches a `chat`
attribute, only inside functions that run after chat.py has finished
executing.

RESERVE x ROUNDS, WHY (§ب‑۴): if the reservation covered only one call but
the loop can debit up to `MAX_TOOL_ROUNDS` times, the only thing standing
between us and a real loss is `chat_billing.py`'s L4 branch ("take whatever
is left, don't go negative, log the shortfall") -- and that shortfall is
real money. Reserving for all the rounds up front means a user who cannot
afford them gets `InsufficientBalanceError` (propagated to the caller,
uncaught here -- same shape as chat.py's own `try/except
InsufficientBalanceError` around its reserve call) BEFORE a single upstream
call runs.

`balance_after <= 0` IS A SEPARATE CONDITION FROM THE COST CEILING, on
purpose (§ب‑۴): the reservation is a pre-flight estimate on a fixed
representative shape (see `_EST_COST` below); a real oversized message can
make round 1 alone exceed its share of the hold, at which point
`chat_billing._record_usage`'s L4 branch zeroes the wallet. Without this
condition, round 2 is *guaranteed* to run at a loss. Do not fold it into
the `spent >= max_cost` check -- they guard different failure shapes and
the mutation protocol in the packet requires them independently testable.

`release(reservation)` -- through `BillingService.release()`, via
`chat._release_reservation` (which already goes through `BillingService`,
never `mark_reservation_released` alone) -- runs from exactly one `finally`
wrapping the whole round loop. A stray second call site was how a
reservation got stranded for five days earlier this month; see
`test_release_called_exactly_once_*` below for every exit path this covers.

NO NEW PERSISTENT STATE. A restart mid-loop loses in-memory progress, but
every completed round's billing already committed in its own transaction
and any dispatched tool's write already committed in its own transaction
(`services/chat_tools.py` wraps `task_service.create_task`/
`assistant_service.create_assistant`, both single-transaction). The user
sees a partial answer and resends -- acceptable by design (§ب‑۲), not a
gap this module needs to paper over.
"""
from __future__ import annotations

import json
import logging
import secrets
import time as _time
from typing import Any

from fastapi import Request
from fastapi.responses import Response

from i18n import err
from models import User
from services.billing import BillingService, InsufficientBalanceError, SqlBillingRepo
from services.chat_tools import TOOL_SCHEMAS, announced_tools
from services.chat_tools import dispatch as dispatch_tool
from services.money import Money
from chat_models import COMPLETION_TIMEOUT_SECONDS
from model_output import clean_response_dict

import chat  # noqa: F401 -- late-bound, see the MONKEYPATCH CONTRACT note above

logger = logging.getLogger('chat')  # same logger namespace as chat_billing.py/chat_web.py

# ── Numbers (§ب‑۴) ──────────────────────────────────────────────────────

MAX_TOOL_ROUNDS = 3  # a healthy loop is 2 (call, then answer); the 3rd is one retry

# A single round's pre-flight reservation estimate -- the SAME flat
# heuristic chat.py's own reserve block uses today (`1000 if working else
# 5000`), reused rather than re-derived so the two never drift apart.
_EST_COST_WORKING_MODEL = 1000
_EST_COST_UNKNOWN_MODEL = 5000

DEFAULT_MAX_COST_TOMAN = 15_000
_MAX_COST_SETTING_KEY = 'tool_loop_max_cost_toman'
_MAX_COST_CACHE_TTL = 60  # seconds -- same idiom as services/free_tier_config.py

CEILING_NOTICE_FA = 'پاسخ برای رعایت سقف هزینهٔ هر پیام کوتاه شد.'

_VALID_AUTONOMY_LEVELS = ('low', 'medium', 'high')
_DEFAULT_AUTONOMY_LEVEL = 'medium'  # matches auth_profile.py's own default

_max_cost_cache: int | None = None
_max_cost_cache_at: float = 0.0


def invalidate_max_cost_cache() -> None:
    """Drop the cached `tool_loop_max_cost_toman` value. Call after an admin
    edits it (no admin surface ships in this packet; here for the next
    owner and for tests)."""
    global _max_cost_cache, _max_cost_cache_at
    _max_cost_cache = None
    _max_cost_cache_at = 0.0


async def max_cost_per_message_toman() -> int:
    """`tool_loop_max_cost_toman` app_setting, cached 60s, fail-safe default
    `DEFAULT_MAX_COST_TOMAN` -- same idiom as
    `services/free_tier_config.py::get_config`. Never raises."""
    global _max_cost_cache, _max_cost_cache_at
    now = _time.monotonic()
    if _max_cost_cache is not None and (now - _max_cost_cache_at) < _MAX_COST_CACHE_TTL:
        return _max_cost_cache
    value = DEFAULT_MAX_COST_TOMAN
    try:
        if chat.async_session is not None:
            import sqlalchemy

            async with chat.async_session() as session:
                res = await session.execute(
                    sqlalchemy.text('SELECT value FROM app_setting WHERE key = :key'),
                    {'key': _MAX_COST_SETTING_KEY},
                )
                row = res.fetchone()
                if row is not None:
                    raw = row[0]
                    if isinstance(raw, str):
                        raw = json.loads(raw)
                    n = int(raw)
                    if n > 0:
                        value = n
    except Exception as e:
        logger.warning(f"chat_tool_loop: max_cost_per_message_toman load failed, using default: {e}")
        value = DEFAULT_MAX_COST_TOMAN
    _max_cost_cache = value
    _max_cost_cache_at = now
    return value


async def autonomy_level_for(uid: int) -> str:
    """`users.preferences->>'autonomy_level'`, defaulting/falling back to
    `medium` exactly like `auth_profile.py::get_profile` does. Never
    raises."""
    if chat.async_session is None:
        return _DEFAULT_AUTONOMY_LEVEL
    try:
        async with chat.async_session() as session:
            res = await session.execute(User.__table__.select().where(User.id == uid))
            row = res.fetchone()
    except Exception as e:
        logger.warning(f"chat_tool_loop: autonomy_level_for lookup failed uid={uid}: {e}")
        return _DEFAULT_AUTONOMY_LEVEL
    if row is None:
        return _DEFAULT_AUTONOMY_LEVEL
    prefs = row.preferences or {}
    level = prefs.get('autonomy_level', _DEFAULT_AUTONOMY_LEVEL)
    return level if level in _VALID_AUTONOMY_LEVELS else _DEFAULT_AUTONOMY_LEVEL


def _build_upstream_tools(autonomy_level: str) -> list[dict[str, Any]]:
    """OUR schemas only, filtered by autonomy -- never the caller's `tools`
    value (see module docstring). `announced_tools` always returns at least
    `{'list_models'}`, so this is never empty when called."""
    names = announced_tools(autonomy_level)
    return [TOOL_SCHEMAS[name] for name in sorted(names)]


def _apply_ceiling_notice(resp_data: dict, message: dict) -> None:
    """Honest Persian notice, never silence (§ب‑۴). Also clears the
    now-abandoned `tool_calls` so a client never renders a tool card for a
    call that will never run."""
    content = message.get('content') or ''
    message['content'] = content + ('\n\n' if content else '') + CEILING_NOTICE_FA
    message['tool_calls'] = None
    choices = resp_data.get('choices') or []
    if choices and isinstance(choices[0], dict):
        choices[0]['message'] = message
        choices[0]['finish_reason'] = 'stop'


async def run_tool_loop(
    request: Request, uid: int, payload_dict: dict[str, Any], *, covered: bool = False,
) -> Response:
    """The whole reserve → up-to-`MAX_TOOL_ROUNDS` → release cycle for one
    non-streaming `/v1/chat/completions` request. `payload_dict` is the
    SAME fully-prepared dict chat.py builds today (model resolved,
    whitelist-checked, assistant/memory/web-search injected, compressed,
    budgeted) -- this function only ever mutates its own round-local copy's
    `messages`/`tools` keys, never the caller's dict.

    `covered=True` means chat.py already established that a package
    entitlement or the free-tier allowance pays for this request, so no
    wallet reservation is taken. chat.py owns that determination; see the
    comment at the reserve step for why it is not re-derived here.

    `InsufficientBalanceError` from the reserve step propagates uncaught --
    the caller is expected to catch it exactly like chat.py's own reserve
    block does today (`err_openai(..., 429, code='balance', ...)`).
    """
    model = str(payload_dict.get('model') or '')
    est_cost = _EST_COST_WORKING_MODEL if (model and await chat.is_working_model(model)) else _EST_COST_UNKNOWN_MODEL
    autonomy_level = await autonomy_level_for(uid)
    upstream_tools = _build_upstream_tools(autonomy_level)
    max_cost = await max_cost_per_message_toman()

    # `covered` is decided by chat.py, not here, and that division is
    # deliberate: this module must never re-derive a gate, or there would be
    # two places that answer "does this user pay for this request" and one
    # day they would disagree. (The module's own source-scan guard,
    # TestGateOrderStaysChatPysJob, fails if this file so much as imports one.)
    #
    # What it buys: without it a user whose package or free-tier allowance
    # already covers the request would have MAX_TOOL_ROUNDS x est_cost taken
    # out of their wallet for something they had already paid for -- charged
    # twice for one message, and by a factor of three. The loop is opt-in and
    # no client sets `tools` today, so this was never reachable in
    # production; it was still the wrong shape to ship.
    #
    # _release_reservation already no-ops on None (chat_web.py:215), so the
    # finally below stays unchanged for the covered case.
    reservation = None
    if not covered:
        async with chat.async_session() as _bill_session:
            _bill_svc = BillingService(SqlBillingRepo(_bill_session))
            reservation = await _bill_svc.reserve(
                uid, Money(est_cost * MAX_TOOL_ROUNDS),
                idempotency_key=f"chattool:{secrets.token_hex(8)}",
                model=model,
            )
            await _bill_session.commit()

    messages: list[dict] = list(payload_dict.get('messages') or [])
    spent = 0
    total_input_tokens = 0
    total_output_tokens = 0
    balance_after = 0
    final_resp_data: dict | None = None
    final_error_response: Response | None = None

    try:
        for round_no in range(1, MAX_TOOL_ROUNDS + 1):
            if await request.is_disconnected():
                break

            round_payload = dict(payload_dict)
            round_payload['messages'] = messages
            round_payload['tools'] = upstream_tools

            _started = _time.monotonic()
            try:
                provider = await chat._resolve_provider(model)
                r = await chat._http.post(
                    f'{provider.v1}/chat/completions', json=round_payload,
                    headers={**provider.headers(), 'Accept': 'application/json'},
                    timeout=COMPLETION_TIMEOUT_SECONDS,
                )
            except Exception as e:
                logger.warning(f"chat_tool_loop: upstream call failed uid={uid} model={model!r} round={round_no}: {e}")
                chat._record_model_health(
                    model, ok=False, latency_ms=int((_time.monotonic() - _started) * 1000),
                    error=type(e).__name__,
                )
                if round_no == 1:
                    final_error_response = err(
                        'سرویس موقتاً در دسترس نیست', 'The service is temporarily unavailable.', 502,
                    )
                break

            chat._record_model_health(
                model, ok=r.status_code == 200,
                latency_ms=int((_time.monotonic() - _started) * 1000),
                error=None if r.status_code == 200 else f'http_{r.status_code}',
            )
            if r.status_code != 200:
                if round_no == 1:
                    final_error_response = Response(
                        content=r.content, status_code=r.status_code, media_type='application/json',
                    )
                break

            resp_data = r.json()
            cost_info = await chat._track_usage(request, round_payload, resp_data) or {}
            spent += int(cost_info.get('cost') or 0)
            total_input_tokens += int(cost_info.get('input_tokens') or 0)
            total_output_tokens += int(cost_info.get('output_tokens') or 0)
            balance_after = int(cost_info.get('balance_after') or balance_after)

            resp_data = clean_response_dict(resp_data)
            final_resp_data = resp_data

            choices = resp_data.get('choices') or []
            choice = choices[0] if choices and isinstance(choices[0], dict) else {}
            message = choice.get('message') or {}
            finish_reason = choice.get('finish_reason')
            tool_calls = message.get('tool_calls') or []

            if finish_reason != 'tool_calls' or not tool_calls:
                break
            if spent >= max_cost:
                _apply_ceiling_notice(resp_data, message)
                break
            if balance_after <= 0:
                _apply_ceiling_notice(resp_data, message)
                break
            if await request.is_disconnected():
                # Tool does NOT run; round is already metered above. Done.
                break
            if round_no >= MAX_TOOL_ROUNDS:
                # No round left to hand the dispatch result back to the
                # model. Dispatching anyway would fire a real write
                # (create_task/create_assistant at `high` autonomy) that
                # the user is never told about in the visible answer --
                # worse than the honest ceiling notice. The `for...else`
                # below stays as defence in depth; this is the path that
                # actually fires today since it runs inside the last
                # iteration, before the `for` loop's natural exit.
                _apply_ceiling_notice(resp_data, message)
                break

            messages.append(message)
            for tc in tool_calls:
                fn = tc.get('function') or {}
                name = fn.get('name', '')
                args_json = fn.get('arguments') or '{}'
                result = await dispatch_tool(uid, autonomy_level, name, args_json)
                messages.append({
                    'role': 'tool',
                    'tool_call_id': tc.get('id', ''),
                    'name': name,
                    'content': json.dumps(result, ensure_ascii=False),
                })
        else:
            # MAX_TOOL_ROUNDS exhausted with the model still wanting another
            # round -- never leave the user in silence (§ب‑۴).
            if final_resp_data is not None:
                choices = final_resp_data.get('choices') or []
                if choices and isinstance(choices[0], dict) and choices[0].get('finish_reason') == 'tool_calls':
                    _apply_ceiling_notice(final_resp_data, choices[0].get('message') or {})
    finally:
        await chat._release_reservation(reservation, uid, 'tool_loop')

    if final_error_response is not None:
        return final_error_response
    if final_resp_data is None:
        return err('سرویس موقتاً در دسترس نیست', 'The service is temporarily unavailable.', 502)

    if spent > 0:
        final_resp_data['billing'] = {
            'cost': spent, 'input_tokens': total_input_tokens, 'output_tokens': total_output_tokens,
            'balance_after': balance_after, 'currency': 'IRT',
        }
    chat._fire_memory_extraction(uid, messages)
    return Response(content=json.dumps(final_resp_data), status_code=200, media_type='application/json')
