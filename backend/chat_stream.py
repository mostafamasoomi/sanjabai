"""SSE streaming for chat completions -- split out of chat.py (see chat.py's
module docstring for why). Holds `_chat_stream` (used by
`/v1/chat/completions` and `/v1/chat/with-file`) and `_smart_chat_stream`
(used by `/v1/smart-chat`) -- both share the same reasoning-filter /
trailing-usage-chunk / billing shape, documented once in `_chat_stream`.

MONKEYPATCH CONTRACT: test_stream_billing_neutrality.py patches
`chat_mod._bill_stream_usage`, `chat_mod._fire_memory_extraction`,
`chat_mod.async_session`, `chat_mod._resolve_provider`,
`chat_mod._get_user_id`, and `database._real_http` (the last one flows
through unchanged since `chat._http` is database.py's lazy proxy object,
imported once and shared everywhere). Every one of the chat-owned names is
resolved through `chat.<name>` at call time below, never via
`from chat import X`. `chat` is imported plainly at module scope, which is
safe against the chat.py <-> chat_stream.py circular import: nothing here
touches a `chat` attribute until a function actually runs, by which point
chat.py has finished executing.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from services.context_injection import get_injection_messages, inject_messages
from services.token_budget import apply_outbound_budget
from middleware.compression import compress_messages, estimate_savings
from model_output import ReasoningStreamFilter

import chat

logger = logging.getLogger('chat')  # keep all chat_*.py logs under the pre-split 'chat' logger name


def _sse_error_event(code: str, message: str) -> str:
    """Build the one mid-stream SSE error payload shape shared by
    `_chat_stream` and `_smart_chat_stream`: `{"error": {"code", "message"}}`.

    `message` must always be a safe, Persian, user-facing string -- never an
    interpolated exception. Callers log the real exception server-side
    (`logger.warning`/`logger.exception`) before calling this.
    """
    return f'data: {json.dumps({"error": {"code": code, "message": message}})}\n\n'


async def _chat_stream(payload: dict[str, Any], request: Request):
    """Stream chat completion via SSE, collecting usage for billing."""
    uid = await chat._get_user_id(request)

    if uid:
        try:
            injs = await get_injection_messages(uid, messages=payload.get('messages'))
            if injs:
                payload['messages'] = inject_messages(payload.get('messages', []), injs)
        except Exception as e:
            logger.warning(f"_chat_stream injection failed uid={uid}: {e}")

    # Compress old messages to reduce token usage
    try:
        _orig = [m.copy() for m in payload.get("messages", [])]
        payload["messages"] = compress_messages(payload.get("messages", []), preserve_last=2)
        _sav = estimate_savings(_orig, payload["messages"])
        if _sav["savings_pct"] > 0:
            logger.info(f"Headroom stream: {_sav['savings_pct']}% saved ({_sav['saved_chars']} chars)")
    except Exception as e:
        logger.debug(f"Compression skipped: {e}")

    # Phase E ceiling -- idempotent, so the chat.py path that already applied
    # it before calling here is not penalized twice.
    await apply_outbound_budget(payload)

    async def event_stream():
        usage_data = None
        accum_text: list[str] = []
        chunk_count = 0
        client_gone = False
        drain_after_disconnect = 0
        # FIX 1: strip leaked <thought>/<think> reasoning blocks from the
        # visible stream. A tag can be split across arbitrary SSE chunk
        # boundaries, so per-chunk string checks don't work -- see
        # ReasoningStreamFilter's docstring in model_output.py.
        reasoning_filter = ReasoningStreamFilter()
        # Shallow template (id/object/created/model) from the most recent
        # real chunk, reused so a trailing flush() chunk (emitted below,
        # after the loop ends) looks like a normal SSE chunk to the client
        # instead of a bare, unidentified one.
        last_chunk_template: dict[str, Any] | None = None
        # Root-cause note (loss-path audit, 2026-08-21 incident): a live
        # probe of this exact upstream/model combination showed the usage
        # block arrives as its OWN trailing SSE chunk, one line AFTER the
        # chunk carrying finish_reason='stop' -- not merged into it. Many
        # SSE clients (browsers included) stop reading as soon as they see
        # finish_reason and close their connection to us before that
        # trailing chunk is ever read. request.is_disconnected() then goes
        # true and the old code `break`-ed immediately, discarding a usage
        # chunk the upstream was about to send (or had already sent) --
        # billing zero for a fully-served response with no upstream fault
        # at all. Fix: once the client is gone, stop yielding to them
        # (nothing is listening) but keep draining a bounded number of
        # further lines from upstream so a same-request trailing usage
        # chunk still gets captured for billing.
        MAX_DRAIN_LINES_AFTER_DISCONNECT = 20
        try:
            payload['stream'] = True
            payload.setdefault('stream_options', {})
            if isinstance(payload['stream_options'], dict):
                payload['stream_options']['include_usage'] = True
            import httpx
            _provider = await chat._resolve_provider(payload.get('model', ''))
            # Streaming timeout: 90s total, 10s connect
            async with chat._http.stream(
                'POST',
                f'{_provider.v1}/chat/completions',
                json=payload,
                headers={**_provider.headers(), 'Accept': 'text/event-stream'},
                timeout=httpx.Timeout(90, connect=10, read=90),
            ) as r:
                async for line in r.aiter_lines():
                    if not client_gone and await request.is_disconnected():
                        client_gone = True
                        logger.info(
                            f"_chat_stream client disconnected uid={uid} model={payload.get('model')} "
                            f"-- draining up to {MAX_DRAIN_LINES_AFTER_DISCONNECT} more lines for a trailing usage chunk"
                        )
                    if client_gone:
                        drain_after_disconnect += 1
                        if drain_after_disconnect > MAX_DRAIN_LINES_AFTER_DISCONNECT:
                            break
                    if line:
                        chunk_count += 1
                        stripped = line.strip()
                        if stripped.startswith('data:'):
                            data_str = stripped[5:].strip()
                            if data_str == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data_str)
                                if isinstance(chunk.get('usage'), dict) and chunk['usage']:
                                    usage_data = chunk['usage']
                                    if client_gone:
                                        break  # got what we needed; stop draining
                                if chunk.get('choices'):
                                    last_chunk_template = {
                                        k: chunk[k] for k in ('id', 'object', 'created', 'model') if k in chunk
                                    }
                                # FIX 1 + L1: run every visible text piece
                                # through the reasoning filter BEFORE it is
                                # forwarded or accumulated -- accum_text
                                # (used below for the L1 output-token
                                # estimate) must reflect what was actually
                                # SERVED to the user, not the raw upstream
                                # text (which can still contain a leaked
                                # <thought> block). Only rewrite the SSE
                                # line when the filter actually changed
                                # something, so the untouched common case
                                # (no tags at all) forwards byte-identical.
                                chunk_changed = False
                                for _c in chunk.get('choices') or []:
                                    _delta = (_c or {}).get('delta') or {}
                                    _piece = _delta.get('content')
                                    if isinstance(_piece, str):
                                        _clean_piece = reasoning_filter.feed(_piece)
                                        # Deliberately the RAW piece, not the
                                        # cleaned one. accum_text feeds the L1
                                        # output-token ESTIMATE, which only runs
                                        # when the upstream sent no usage block
                                        # at all, and which is already
                                        # documented as a known lower bound.
                                        # Estimating from the cleaned text would
                                        # make stripping a reasoning block also
                                        # shrink the bill -- a model that
                                        # answers with nothing but a thought
                                        # block (observed: gemma-4-26b returned
                                        # exactly '<thought>*   </thought>' and
                                        # nothing else) would then estimate zero
                                        # output tokens for work the upstream
                                        # actually did. Whether we pay that
                                        # upstream per token is not knowable
                                        # from here, so the product rule that no
                                        # request may be loss-making decides it:
                                        # estimate from raw. This also keeps the
                                        # change provably billing-neutral --
                                        # cleaning affects only what the user
                                        # sees, never an amount.
                                        accum_text.append(_piece)
                                        if _clean_piece != _piece:
                                            _delta['content'] = _clean_piece
                                            chunk_changed = True
                                if chunk_changed:
                                    line = f'data: {json.dumps(chunk)}'
                            except (json.JSONDecodeError, ValueError):
                                pass
                        if not client_gone:
                            yield f"{line}\n\n"
        except Exception as e:
            logger.warning(f"_chat_stream error uid={uid} model={payload.get('model')}: {e}")
            if not client_gone:
                yield _sse_error_event('upstream_failed', 'سرویس موقتاً در دسترس نیست. لطفاً دوباره تلاش کنید.')
        finally:
            # FIX 1: flush any text the filter was still holding back to
            # disambiguate a possible tag (e.g. the stream ended right after
            # a bare '<') -- see ReasoningStreamFilter.flush()'s docstring.
            # Must run before the billing text below is assembled so a
            # trailing served-but-buffered fragment is still counted.
            _leftover = reasoning_filter.flush()
            if _leftover:
                # NOT appended to accum_text: that list now holds the RAW
                # pieces (see the comment at the feed() call above), and the
                # leftover is a fragment of raw text the filter was merely
                # holding back -- it is already in accum_text. Appending it
                # here would double-count it in the billing estimate.
                if not client_gone:
                    _flush_chunk = {
                        'id': (last_chunk_template or {}).get('id', ''),
                        'object': (last_chunk_template or {}).get('object', 'chat.completion.chunk'),
                        'created': (last_chunk_template or {}).get('created', 0),
                        'model': (last_chunk_template or {}).get('model', payload.get('model', '')),
                        'choices': [{'index': 0, 'delta': {'content': _leftover}, 'finish_reason': None}],
                    }
                    yield f'data: {json.dumps(_flush_chunk)}\n\n'
            # L1: bill even when usage_data is None, as long as something
            # was actually served (real usage chunk OR accumulated text) --
            # previously `usage_data` being falsy skipped billing entirely,
            # which is exactly the "served for free" bug when an upstream
            # never sends a usage chunk at all.
            if uid and chat.async_session is not None and not usage_data and not accum_text:
                logger.warning(
                    f"_chat_stream: no usage and no content captured uid={uid} "
                    f"model={payload.get('model')!r} chunk_count={chunk_count} "
                    f"client_gone={client_gone} -- nothing to bill"
                )
            if uid and chat.async_session is not None and (usage_data or accum_text):
                try:
                    cost_info = await chat._bill_stream_usage(uid, payload, usage_data or {}, response_text=''.join(accum_text))
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
                    logger.warning(f"_chat_stream billing emit failed uid={uid}: {e}")
            # P3: Fire background auto-memory extraction (streaming)
            if uid:
                chat._fire_memory_extraction(uid, payload.get('messages', []))

    return StreamingResponse(event_stream(), media_type='text/event-stream')


async def _smart_chat_stream(
    payload: dict[str, Any],
    request: Request,
    selected_model: str,
    category: str,
    display_model: str | None = None,
    smart_mode: str | None = None,
):
    """Stream smart chat completion via SSE.

    ``selected_model`` is the canonical provider_model_id used for routing
    and billing; ``display_model`` (defaults to ``selected_model`` when not
    given) is what's echoed back to the client in the `smart_info` SSE event
    and the `X-Smart-Model` response header -- kept separate so a forced
    `X-Smart-Model: sanjab/...` request never gets the resolved
    provider_model_id leaked back to it (see smart_chat()).
    """
    uid = await chat._get_user_id(request)
    display_model = display_model if display_model is not None else selected_model

    # Dedup guard + helper (previously duplicated)
    if uid:
        try:
            injs = await get_injection_messages(uid, messages=payload.get('messages'))
            if injs:
                payload['messages'] = inject_messages(payload.get('messages', []), injs)
        except Exception as e:
            logger.warning(f"_smart_chat_stream injection failed uid={uid}: {e}")

    # Phase E ceiling -- see _chat_stream above.
    await apply_outbound_budget(payload)

    async def event_stream():
        usage_data = None
        accum_text: list[str] = []
        chunk_count = 0
        client_gone = False
        drain_after_disconnect = 0
        # FIX 1: see _chat_stream for the full rationale/docstring pointer.
        reasoning_filter = ReasoningStreamFilter()
        last_chunk_template: dict[str, Any] | None = None
        # See _chat_stream for the root-cause rationale: usage arrives as
        # its own trailing SSE chunk, after finish_reason -- a client that
        # stops reading right after finish_reason otherwise causes us to
        # discard a usage chunk the upstream already sent/was sending.
        MAX_DRAIN_LINES_AFTER_DISCONNECT = 20
        try:
            payload['stream'] = True
            payload.setdefault('stream_options', {})
            if isinstance(payload['stream_options'], dict):
                payload['stream_options']['include_usage'] = True
            import httpx
            _provider = await chat._resolve_provider(selected_model)
            async with chat._http.stream(
                'POST',
                f'{_provider.v1}/chat/completions',
                json=payload,
                headers={**_provider.headers(), 'Accept': 'text/event-stream'},
                timeout=httpx.Timeout(90, connect=10, read=90),
            ) as r:
                # `mode` is what actually produced the pick (auto / router /
                # combo:<id>), never what the client asked for -- a router or
                # combo that declined and fell back reports `auto`. The
                # non-stream path says the same thing in its X-Smart-Mode
                # response header, but the browser only ever takes this path:
                # the frontend reads no response headers at all, and the Next
                # proxy rebuilds the response without them anyway. Omitted
                # entirely when the caller passes nothing, so an older caller
                # keeps producing the exact event it produced before.
                _info = {"type": "smart_info", "model": display_model, "category": category}
                if smart_mode is not None:
                    _info["mode"] = smart_mode
                yield f'data: {json.dumps(_info)}\n\n'
                async for line in r.aiter_lines():
                    if not client_gone and await request.is_disconnected():
                        client_gone = True
                        logger.info(
                            f"_smart_chat_stream disconnected uid={uid} model={selected_model} "
                            f"-- draining up to {MAX_DRAIN_LINES_AFTER_DISCONNECT} more lines for a trailing usage chunk"
                        )
                    if client_gone:
                        drain_after_disconnect += 1
                        if drain_after_disconnect > MAX_DRAIN_LINES_AFTER_DISCONNECT:
                            break
                    if line:
                        chunk_count += 1
                        stripped = line.strip()
                        if stripped.startswith('data:'):
                            data_str = stripped[5:].strip()
                            if data_str == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data_str)
                                if isinstance(chunk.get('usage'), dict) and chunk['usage']:
                                    usage_data = chunk['usage']
                                    if client_gone:
                                        break
                                if chunk.get('choices'):
                                    last_chunk_template = {
                                        k: chunk[k] for k in ('id', 'object', 'created', 'model') if k in chunk
                                    }
                                # FIX 1 + L1: clean before accumulating/
                                # forwarding (see _chat_stream for the
                                # rationale).
                                chunk_changed = False
                                for _c in chunk.get('choices') or []:
                                    _delta = (_c or {}).get('delta') or {}
                                    _piece = _delta.get('content')
                                    if isinstance(_piece, str):
                                        _clean_piece = reasoning_filter.feed(_piece)
                                        # Deliberately the RAW piece, not the
                                        # cleaned one. accum_text feeds the L1
                                        # output-token ESTIMATE, which only runs
                                        # when the upstream sent no usage block
                                        # at all, and which is already
                                        # documented as a known lower bound.
                                        # Estimating from the cleaned text would
                                        # make stripping a reasoning block also
                                        # shrink the bill -- a model that
                                        # answers with nothing but a thought
                                        # block (observed: gemma-4-26b returned
                                        # exactly '<thought>*   </thought>' and
                                        # nothing else) would then estimate zero
                                        # output tokens for work the upstream
                                        # actually did. Whether we pay that
                                        # upstream per token is not knowable
                                        # from here, so the product rule that no
                                        # request may be loss-making decides it:
                                        # estimate from raw. This also keeps the
                                        # change provably billing-neutral --
                                        # cleaning affects only what the user
                                        # sees, never an amount.
                                        accum_text.append(_piece)
                                        if _clean_piece != _piece:
                                            _delta['content'] = _clean_piece
                                            chunk_changed = True
                                if chunk_changed:
                                    line = f'data: {json.dumps(chunk)}'
                            except (json.JSONDecodeError, ValueError):
                                pass
                        if not client_gone:
                            yield f'{line}\n\n'
        except Exception as e:
            logger.warning(f"_smart_chat_stream error uid={uid} model={selected_model}: {e}")
            if not client_gone:
                yield _sse_error_event('upstream_failed', 'سرویس موقتاً در دسترس نیست. لطفاً دوباره تلاش کنید.')
        finally:
            # FIX 1: flush any held-back text -- see _chat_stream for the
            # rationale/docstring pointer.
            _leftover = reasoning_filter.flush()
            if _leftover:
                # NOT appended to accum_text: that list now holds the RAW
                # pieces (see the comment at the feed() call above), and the
                # leftover is a fragment of raw text the filter was merely
                # holding back -- it is already in accum_text. Appending it
                # here would double-count it in the billing estimate.
                if not client_gone:
                    _flush_chunk = {
                        'id': (last_chunk_template or {}).get('id', ''),
                        'object': (last_chunk_template or {}).get('object', 'chat.completion.chunk'),
                        'created': (last_chunk_template or {}).get('created', 0),
                        'model': (last_chunk_template or {}).get('model', selected_model),
                        'choices': [{'index': 0, 'delta': {'content': _leftover}, 'finish_reason': None}],
                    }
                    yield f'data: {json.dumps(_flush_chunk)}\n\n'
            # L1: bill even when usage_data is None, as long as something
            # was actually served -- see _chat_stream for the rationale.
            if uid and chat.async_session is not None and not usage_data and not accum_text:
                logger.warning(
                    f"_smart_chat_stream: no usage and no content captured uid={uid} "
                    f"model={selected_model!r} chunk_count={chunk_count} "
                    f"client_gone={client_gone} -- nothing to bill"
                )
            if uid and chat.async_session is not None and (usage_data or accum_text):
                try:
                    cost_info = await chat._bill_stream_usage(uid, payload, usage_data or {}, response_text=''.join(accum_text))
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
                chat._fire_memory_extraction(uid, payload.get('messages', []))

    response = StreamingResponse(event_stream(), media_type='text/event-stream')
    response.headers['X-Smart-Model'] = display_model
    response.headers['X-Smart-Category'] = category
    return response
