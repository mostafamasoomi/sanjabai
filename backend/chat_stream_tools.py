"""The SSE (streaming) tool-calling loop (Phase 8, packet B5).

Streaming sibling of `chat_tool_loop.py` (packet B4, non-streaming). Same
gates, same numbers, same reserve-x-rounds/release-once shape -- see that
module's docstring for the full rationale; this one does not re-derive a
single one of `MAX_TOOL_ROUNDS`, `CEILING_NOTICE_FA`, `autonomy_level_for`,
`max_cost_per_message_toman`, or `_build_upstream_tools`, all imported
straight from it below. The only genuinely new problem here is streaming
itself: one SSE response spans several upstream rounds, and two upstream
chunk shapes must never reach the client raw (design doc §ب‑۲):

- `delta.tool_calls` fragments -- accumulated by `delta.tool_calls[i].index`
  (`id`/`function.name` from the FIRST fragment that carries them,
  `function.arguments` the CONCATENATION of every fragment), never
  forwarded.
- the chunk carrying `finish_reason='tool_calls'` -- chat_stream.py's own
  module docstring (lines 91-104) documents the real incident this guards
  against: a client disconnects the instant it sees ANY `finish_reason`,
  dropping a trailing usage chunk. Forwarding this one specifically would
  additionally hang the client mid-loop, since it looks exactly like "the
  answer is done" when two more rounds may still run.

Instead we emit our own typed SSE lines (`tool_call`/`tool_result`/
`tool_confirm`) that the frontend already dispatches on `obj.type`
(useChatStream.ts) -- see ToolCallChip.strings.ts / ToolConfirmCard.strings.ts
for the exact shapes it parses. Ordinary `delta.content` forwards exactly as
`chat_stream.py::_chat_stream` forwards it today (same reasoning-filter
cleanup, same chunk-template/flush-chunk shape, same usage-chunk capture) --
`TestNoToolCallsIsByteIdenticalToTodaysStream` in the test file is the proof
this is additive, not a rewrite.

NEW MODULE, NOT ADDED TO chat_stream.py: chat_stream.py is already 452 of
its 500-line budget; this surface (tool-call accumulation, per-round direct-
debit billing, the three new SSE event types, the disconnect contract below)
does not fit in the 48 lines left. The packet anticipates exactly this
("if it would cross the cap, put the new surface in a new module and say
so"). chat_stream.py itself is UNTOUCHED by this packet -- zero risk to its
already-reviewed behaviour -- and this module only imports its one small
public-shaped helper, `_sse_error_event`.

BILLING (§ب‑۴, unchanged pattern from chat_tool_loop.py): reserve once for
`MAX_TOOL_ROUNDS x estimate` before the first upstream call; each round
direct-debits the wallet for its OWN usage via `chat._bill_stream_usage`
(the streaming counterpart of chat_tool_loop.py's `chat._track_usage`) in
that round's own `finally`, so a round that already ran gets billed even if
the round after it never happens; release the reservation exactly once, in
the outer `finally`, through `chat._release_reservation` (which goes through
`BillingService.release()`, never `mark_reservation_released` alone).
Integer tomans only, nothing multiplies or divides by 10.

DISCONNECT CONTRACT (§ب‑۲, implemented exactly, not re-derived):

| when                                             | behaviour                                   |
|---------------------------------------------------|----------------------------------------------|
| mid-round, before `finish_reason`                  | existing drain (~20 lines, same as chat_stream.py) captures usage; loop STOPS, round k+1 never starts |
| after `finish_reason='tool_calls'`, BEFORE dispatch | the tool does NOT run; round k is metered; done |
| AFTER dispatch                                     | the side effect is NOT rolled back; round k+1 never starts |

Enforced by exactly two `await request.is_disconnected()` checks per
iteration: once at the TOP of the round loop (before opening a new upstream
stream -- covers both "mid-round drain already ended the loop" and "after
dispatch, no next round"), and once immediately before the tool-dispatch
loop (covers "before dispatch, tool does not run").

CONFIRMATION HOLDS NO STATE (§ب‑۶): when `dispatch()` returns
`{"needs_confirmation": true, "preview": {...}}` (autonomy `low`/`medium`),
this loop does exactly what it does for any other tool result -- emits
`tool_confirm` instead of `tool_result`, appends the tool message, and lets
the loop continue on its own normal terms. The model's next round then
explains in Persian that the user needs to confirm, finishes with an
ordinary `finish_reason='stop'`, and the existing "no more tool_calls ->
break" path ends the loop -- no special early-exit invented here, matching
the design doc's own transcript (§ب‑۶: "مدل دور بعد ... حلقه تمام می‌شود").

NO NEW PERSISTENT STATE. A restart mid-loop loses in-memory progress only;
every round's billing and every dispatched tool's write already committed in
their own transactions. See chat_tool_loop.py's docstring for the same point
in full.
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse

from chat_stream import _sse_error_event
from chat_tool_loop import (
    CEILING_NOTICE_FA,
    MAX_TOOL_ROUNDS,
    _build_upstream_tools,
    _EST_COST_UNKNOWN_MODEL,
    _EST_COST_WORKING_MODEL,
    autonomy_level_for,
    max_cost_per_message_toman,
)
from model_output import ReasoningStreamFilter
from services.billing import BillingService, SqlBillingRepo
from services.chat_tools import dispatch as dispatch_tool
from services.money import Money

import chat  # noqa: F401 -- late-bound; see chat_tool_loop.py's MONKEYPATCH CONTRACT note, identical here

logger = logging.getLogger('chat')  # same logger namespace as chat_stream.py/chat_tool_loop.py

# `_MAX_DRAIN_LINES_AFTER_DISCONNECT` matches chat_stream.py's own constant --
# the same trailing-usage-chunk rationale applies per round here.
_MAX_DRAIN_LINES_AFTER_DISCONNECT = 20

# Fixed Persian label map for the `label_fa` field the three SSE event types
# carry (§ب‑۲'s exact shapes). NOTE: the frontend deliberately never reads
# this field (ToolCallChip.strings.ts's block comment: "never falls back to
# the raw name ... an event's label_fa field is not even looked at anywhere
# in this product") -- its own fixed map is what actually renders. This one
# is kept anyway, word-for-word matched to that map, for any OTHER consumer
# (logs, support tooling) and because the packet's exact event shapes call
# for it. Never the raw tool name, never raw arguments -- fixed map only.
_LABEL_RUNNING_FA = {
    'create_task': 'در حال ساخت وظیفه…',
    'create_assistant': 'در حال ساخت دستیار…',
    'list_models': 'در حال جستجوی مدل‌ها…',
}
_LABEL_OK_FA = {
    'create_task': 'وظیفه ساخته شد',
    'create_assistant': 'دستیار ساخته شد',
    'list_models': 'فهرست مدل‌ها آماده شد',
}
_LABEL_FAIL_FA = {
    'create_task': 'ساخت وظیفه ناموفق بود',
    'create_assistant': 'ساخت دستیار ناموفق بود',
    'list_models': 'جستجوی مدل‌ها ناموفق بود',
}
_LABEL_CONFIRM_FA = {
    'create_task': 'می‌خواهید این وظیفه ساخته شود؟',
    'create_assistant': 'می‌خواهید این دستیار ساخته شود؟',
}
_GENERIC_RUNNING_FA = 'در حال انجام یک عملیات…'
_GENERIC_OK_FA = 'عملیات انجام شد'
_GENERIC_FAIL_FA = 'عملیات ناموفق بود'


def _tool_call_line(name: str) -> str:
    label = _LABEL_RUNNING_FA.get(name, _GENERIC_RUNNING_FA)
    payload = {'type': 'tool_call', 'name': name, 'status': 'running', 'label_fa': label}
    return f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'


def _tool_result_line(name: str, ok: bool) -> str:
    label = (_LABEL_OK_FA if ok else _LABEL_FAIL_FA).get(name, _GENERIC_OK_FA if ok else _GENERIC_FAIL_FA)
    payload = {'type': 'tool_result', 'name': name, 'ok': ok, 'label_fa': label}
    return f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'


def _tool_confirm_line(name: str, preview: dict) -> str:
    label = _LABEL_CONFIRM_FA.get(name, _GENERIC_OK_FA)
    payload = {'type': 'tool_confirm', 'name': name, 'preview': preview, 'label_fa': label}
    return f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'


def _ceiling_notice_line(last_chunk_template: dict | None, model: str, prior_content: bool) -> str:
    """Synthetic content chunk carrying the honest Persian ceiling notice
    (§ب‑۴) -- the streaming equivalent of chat_tool_loop.py's
    `_apply_ceiling_notice`, which mutates a JSON response body in place.
    Streaming already sent whatever content this round had, so the notice
    is a NEW trailing chunk instead, same shape as chat_stream.py's own
    flush chunk. `prior_content` decides the leading '\\n\\n' the same way
    `_apply_ceiling_notice` does."""
    notice = ('\n\n' if prior_content else '') + CEILING_NOTICE_FA
    chunk = {
        'id': (last_chunk_template or {}).get('id', ''),
        'object': (last_chunk_template or {}).get('object', 'chat.completion.chunk'),
        'created': (last_chunk_template or {}).get('created', 0),
        'model': (last_chunk_template or {}).get('model', model),
        'choices': [{'index': 0, 'delta': {'content': notice}, 'finish_reason': 'stop'}],
    }
    return f'data: {json.dumps(chunk)}\n\n'


def _accumulate_tool_call_fragments(tool_calls_acc: dict[int, dict], fragments: list[dict]) -> None:
    """`delta.tool_calls[i].index` -> accumulated entry. `id`/`function.name`
    are taken from the FIRST fragment that carries them (never overwritten
    by a later, emptier one); `function.arguments` is the concatenation of
    every fragment, in arrival order -- the OpenAI streaming
    function-calling contract. `type` is not accumulated from fragments at
    all: every tool this loop can ever announce is a `function` (§ب‑۵
    boundary 4 -- the action space is exactly `TOOL_SCHEMAS`), so the fixed
    default below is never wrong and needs no first-wins tracking."""
    for frag in fragments:
        idx = frag.get('index', 0)
        entry = tool_calls_acc.setdefault(idx, {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
        if not entry['id'] and frag.get('id'):
            entry['id'] = frag['id']
        frag_fn = frag.get('function') or {}
        if not entry['function']['name'] and frag_fn.get('name'):
            entry['function']['name'] = frag_fn['name']
        if frag_fn.get('arguments'):
            entry['function']['arguments'] += frag_fn['arguments']


def _finalized_tool_calls(tool_calls_acc: dict[int, dict]) -> list[dict]:
    return [tool_calls_acc[idx] for idx in sorted(tool_calls_acc)]


async def stream_tool_loop(request: Request, uid: int, payload_dict: dict[str, Any], *, covered: bool = False):
    """The whole reserve -> up-to-`MAX_TOOL_ROUNDS` -> release cycle for one
    streaming `/v1/chat/completions` request, returned as ONE SSE
    `StreamingResponse` that does not close until the loop is done.

    `payload_dict` is the same fully-prepared dict chat.py builds today
    (model resolved, whitelist-checked, assistant/memory/web-search
    injected, compressed, budgeted) -- same contract as
    `chat_tool_loop.run_tool_loop`.

    The reservation happens HERE, before the `StreamingResponse` is built,
    so `InsufficientBalanceError` propagates to the caller synchronously
    (same as `run_tool_loop`) instead of surfacing as a broken SSE stream --
    the caller gets an honest 429, not a truncated stream.
    """
    model = str(payload_dict.get('model') or '')
    est_cost = _EST_COST_WORKING_MODEL if (model and await chat.is_working_model(model)) else _EST_COST_UNKNOWN_MODEL
    autonomy_level = await autonomy_level_for(uid)
    upstream_tools = _build_upstream_tools(autonomy_level)
    max_cost = await max_cost_per_message_toman()

    reservation = None
    if not covered:
        async with chat.async_session() as _bill_session:
            _bill_svc = BillingService(SqlBillingRepo(_bill_session))
            reservation = await _bill_svc.reserve(
                uid, Money(est_cost * MAX_TOOL_ROUNDS),
                idempotency_key=f"chattoolstream:{secrets.token_hex(8)}",
                model=model,
            )
            await _bill_session.commit()

    async def event_stream():
        messages: list[dict] = list(payload_dict.get('messages') or [])
        spent = 0
        total_input_tokens = 0
        total_output_tokens = 0
        balance_after = 0

        try:
            for round_no in range(1, MAX_TOOL_ROUNDS + 1):
                # Disconnect check #1/2: before opening a NEW upstream stream.
                # Covers both "mid-round drain already ended the loop" (below)
                # and "after dispatch, round k+1 never starts".
                if await request.is_disconnected():
                    break

                round_payload = dict(payload_dict)
                round_payload['messages'] = messages
                round_payload['tools'] = upstream_tools
                round_payload['stream'] = True
                round_payload.setdefault('stream_options', {})
                if isinstance(round_payload['stream_options'], dict):
                    round_payload['stream_options']['include_usage'] = True

                usage_data: dict | None = None
                accum_text: list[str] = []
                tool_calls_acc: dict[int, dict] = {}
                finish_reason: str | None = None
                last_chunk_template: dict[str, Any] | None = None
                reasoning_filter = ReasoningStreamFilter()
                client_gone = False
                drain_after_disconnect = 0
                round_upstream_failed = False

                try:
                    provider = await chat._resolve_provider(model)
                    async with chat._http.stream(
                        'POST', f'{provider.v1}/chat/completions', json=round_payload,
                        headers={**provider.headers(), 'Accept': 'text/event-stream'},
                        timeout=httpx.Timeout(90, connect=10, read=90),
                    ) as r:
                        async for line in r.aiter_lines():
                            # Disconnect check: mid-round, before finish_reason
                            # -- existing drain (chat_stream.py's own pattern)
                            # captures a trailing usage chunk; loop stops after
                            # this round (checked via `client_gone` below).
                            if not client_gone and await request.is_disconnected():
                                client_gone = True
                                logger.info(
                                    f"chat_stream_tools round={round_no} disconnected uid={uid} model={model!r} "
                                    f"-- draining up to {_MAX_DRAIN_LINES_AFTER_DISCONNECT} more lines"
                                )
                            if client_gone:
                                drain_after_disconnect += 1
                                if drain_after_disconnect > _MAX_DRAIN_LINES_AFTER_DISCONNECT:
                                    break
                            if not line:
                                continue
                            stripped = line.strip()
                            if not stripped.startswith('data:'):
                                continue
                            data_str = stripped[5:].strip()
                            if data_str == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data_str)
                            except (json.JSONDecodeError, ValueError):
                                continue
                            if isinstance(chunk.get('usage'), dict) and chunk['usage']:
                                usage_data = chunk['usage']
                                if client_gone:
                                    break

                            choices = chunk.get('choices') or []
                            suppress = False
                            for c in choices:
                                delta = (c or {}).get('delta') or {}
                                if delta.get('tool_calls'):
                                    suppress = True  # NEVER forwarded -- accumulate only
                                    _accumulate_tool_call_fragments(tool_calls_acc, delta['tool_calls'])
                                fr = c.get('finish_reason')
                                if fr is not None:
                                    finish_reason = fr
                                    if fr == 'tool_calls':
                                        suppress = True  # NEVER forwarded -- see module docstring
                            if suppress:
                                continue

                            if choices:
                                last_chunk_template = {k: chunk[k] for k in ('id', 'object', 'created', 'model') if k in chunk}
                            chunk_changed = False
                            for c in choices:
                                delta = (c or {}).get('delta') or {}
                                piece = delta.get('content')
                                if isinstance(piece, str):
                                    clean_piece = reasoning_filter.feed(piece)
                                    accum_text.append(piece)  # RAW, for the L1 estimate -- see chat_stream.py's rationale
                                    if clean_piece != piece:
                                        delta['content'] = clean_piece
                                        chunk_changed = True
                            if chunk_changed:
                                line = f'data: {json.dumps(chunk)}'
                            if not client_gone:
                                yield f'{line}\n\n'
                except Exception as e:
                    logger.warning(f"chat_stream_tools: round {round_no} upstream error uid={uid} model={model!r}: {e}")
                    round_upstream_failed = True
                    if round_no == 1 and not accum_text and usage_data is None and not client_gone:
                        yield _sse_error_event('upstream_failed', 'سرویس موقتاً در دسترس نیست. لطفاً دوباره تلاش کنید.')
                finally:
                    leftover = reasoning_filter.flush()
                    if leftover and not client_gone:
                        flush_chunk = {
                            'id': (last_chunk_template or {}).get('id', ''),
                            'object': (last_chunk_template or {}).get('object', 'chat.completion.chunk'),
                            'created': (last_chunk_template or {}).get('created', 0),
                            'model': (last_chunk_template or {}).get('model', model),
                            'choices': [{'index': 0, 'delta': {'content': leftover}, 'finish_reason': None}],
                        }
                        yield f'data: {json.dumps(flush_chunk)}\n\n'
                    if uid and chat.async_session is not None and (usage_data or accum_text):
                        try:
                            cost_info = await chat._bill_stream_usage(
                                uid, round_payload, usage_data or {}, response_text=''.join(accum_text),
                            ) or {}
                        except Exception as e:
                            logger.warning(f"chat_stream_tools: billing round {round_no} failed uid={uid}: {e}")
                            cost_info = {}
                        spent += int(cost_info.get('cost') or 0)
                        total_input_tokens += int(cost_info.get('input_tokens') or 0)
                        total_output_tokens += int(cost_info.get('output_tokens') or 0)
                        balance_after = int(cost_info.get('balance_after') or balance_after)

                if round_upstream_failed:
                    break
                if client_gone:
                    # Mid-round disconnect (table row 1): round already
                    # metered above; loop STOPS, round k+1 never starts.
                    break

                tool_calls = _finalized_tool_calls(tool_calls_acc)
                if finish_reason != 'tool_calls' or not tool_calls:
                    break
                if spent >= max_cost:
                    yield _ceiling_notice_line(last_chunk_template, model, bool(accum_text))
                    break
                if balance_after <= 0:
                    yield _ceiling_notice_line(last_chunk_template, model, bool(accum_text))
                    break
                # Disconnect check #2/2: immediately before dispatch (table
                # row 2) -- the tool does NOT run if the client left here.
                if await request.is_disconnected():
                    break
                if round_no >= MAX_TOOL_ROUNDS:
                    # No round left to hand the dispatch result back to the
                    # model -- same reasoning as chat_tool_loop.py's own
                    # round_no >= MAX_TOOL_ROUNDS branch.
                    yield _ceiling_notice_line(last_chunk_template, model, bool(accum_text))
                    break

                messages.append({'role': 'assistant', 'content': None, 'tool_calls': tool_calls})
                for tc in tool_calls:
                    fn = tc.get('function') or {}
                    name = fn.get('name', '')
                    args_json = fn.get('arguments') or '{}'
                    yield _tool_call_line(name)
                    result = await dispatch_tool(uid, autonomy_level, name, args_json)
                    if result.get('needs_confirmation'):
                        yield _tool_confirm_line(name, result.get('preview') or {})
                    else:
                        yield _tool_result_line(name, bool(result.get('ok')))
                    messages.append({
                        'role': 'tool', 'tool_call_id': tc.get('id', ''), 'name': name,
                        'content': json.dumps(result, ensure_ascii=False),
                    })
        finally:
            await chat._release_reservation(reservation, uid, 'tool_loop_stream')

        if spent > 0:
            billing_event = json.dumps({
                'type': 'billing', 'cost': spent, 'input_tokens': total_input_tokens,
                'output_tokens': total_output_tokens, 'balance_after': balance_after, 'currency': 'IRT',
            })
            yield f'data: {billing_event}\n\n'
        chat._fire_memory_extraction(uid, messages)
        yield 'data: [DONE]\n\n'

    return StreamingResponse(event_stream(), media_type='text/event-stream')
