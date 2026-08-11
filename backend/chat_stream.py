"""
SSE streaming helper for chat.

Pulled out of chat.py (which was well past the project's 500-line ceiling).
``_chat_stream`` proxies a streaming completion to the resolved provider,
collects the usage trailer for billing, and emits the billing event and
background memory extraction in the generator's ``finally`` block.

``_resolve_provider`` is imported lazily from the chat aggregator (this module
is imported by chat.py, and the model-selection core deliberately lives in the
aggregator so tests can keep patching ``chat.async_session``).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from database import async_session, _http
from dependencies import _get_user_id
from services.context_injection import get_injection_messages, inject_messages
from middleware.compression import compress_messages, estimate_savings

from chat_billing import _bill_stream_usage
from chat_common import _fire_memory_extraction

logger = logging.getLogger(__name__)


async def _chat_stream(payload: dict[str, Any], request: Request):
    """Stream chat completion via SSE, collecting usage for billing."""
    uid = await _get_user_id(request)

    if uid:
        try:
            injs = await get_injection_messages(uid)
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

    async def event_stream():
        usage_data = None
        try:
            payload['stream'] = True
            payload.setdefault('stream_options', {})
            if isinstance(payload['stream_options'], dict):
                payload['stream_options']['include_usage'] = True
            import httpx
            from chat import _resolve_provider
            _provider = await _resolve_provider(payload.get('model', ''))
            # Streaming timeout: 90s total, 10s connect
            async with _http.stream(
                'POST',
                f'{_provider.v1}/chat/completions',
                json=payload,
                headers={**_provider.headers(), 'Accept': 'text/event-stream'},
                timeout=httpx.Timeout(90, connect=10, read=90),
            ) as r:
                async for line in r.aiter_lines():
                    # Disconnect handling
                    if await request.is_disconnected():
                        logger.info(f"_chat_stream client disconnected uid={uid} model={payload.get('model')}")
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
                        yield f"{line}\n\n"
        except Exception as e:
            logger.warning(f"_chat_stream error uid={uid} model={payload.get('model')}: {e}")
            yield f'data: {json.dumps({"error": "سرویس موقتاً در دسترس نیست", "code": "gateway_error"})}\n\n'
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
                    logger.warning(f"_chat_stream billing emit failed uid={uid}: {e}")
            # P3: Fire background auto-memory extraction (streaming)
            if uid:
                _fire_memory_extraction(uid, payload.get('messages', []))

    return StreamingResponse(event_stream(), media_type='text/event-stream')
