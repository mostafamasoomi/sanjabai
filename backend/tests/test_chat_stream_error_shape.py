"""Mid-stream SSE error payloads from _chat_stream / _smart_chat_stream must
share one shape and must never leak a raw exception string to the client.

Before this fix the two sites disagreed:
  _chat_stream:       {"error": "سرویس موقتاً در دسترس نیست", "code": "gateway_error"}
  _smart_chat_stream:  {"error": f"upstream unavailable: {e}"}   <- leaks the exception

Both now emit the same shape via _sse_error_event(): {"error": {"code", "message"}},
with a safe Persian message and a stable code -- the real exception only ever
goes to the server log (logger.warning), never into the yielded chunk.
"""
import json

import pytest
from unittest.mock import AsyncMock, patch


class _Req:
    async def is_disconnected(self):
        return False


def _parse_sse_events(chunks: list[str]) -> list[dict]:
    events = []
    for block in ''.join(chunks).split('\n\n'):
        block = block.strip()
        if not block.startswith('data:'):
            continue
        body = block[5:].strip()
        if body == '[DONE]':
            continue
        try:
            events.append(json.loads(body))
        except ValueError:
            continue
    return events


@pytest.mark.asyncio
async def test_chat_stream_error_event_shape_and_no_leak(monkeypatch):
    import chat as chat_mod
    import chat_stream

    monkeypatch.setattr(chat_mod, '_get_user_id', AsyncMock(return_value=1))
    monkeypatch.setattr(chat_mod, 'async_session', None)  # skip billing path entirely

    async def _boom(*a, **k):
        raise RuntimeError("secret upstream connection string leaked-if-shipped")

    monkeypatch.setattr(chat_mod, '_resolve_provider', _boom)

    response = await chat_stream._chat_stream({'model': 'm', 'messages': []}, _Req())
    served = [out async for out in response.body_iterator]

    events = _parse_sse_events(served)
    error_events = [e for e in events if 'error' in e]
    assert len(error_events) == 1, f'expected exactly one error event, got {events!r}'
    err = error_events[0]['error']

    assert isinstance(err, dict), f'error must be an object, got {err!r}'
    assert set(err.keys()) == {'code', 'message'}
    assert err['code'] == 'upstream_failed'
    assert isinstance(err['message'], str) and err['message']
    # The raw exception text must never reach the client.
    full_payload = json.dumps(events)
    assert 'secret upstream connection string' not in full_payload


@pytest.mark.asyncio
async def test_smart_chat_stream_error_event_shape_and_no_leak(monkeypatch):
    import chat as chat_mod
    import chat_stream

    monkeypatch.setattr(chat_mod, '_get_user_id', AsyncMock(return_value=1))
    monkeypatch.setattr(chat_mod, 'async_session', None)

    async def _boom(*a, **k):
        raise RuntimeError("another secret detail that must not leak")

    monkeypatch.setattr(chat_mod, '_resolve_provider', _boom)

    response = await chat_stream._smart_chat_stream(
        {'model': 'm', 'messages': []}, _Req(), selected_model='m', category='general')
    served = [out async for out in response.body_iterator]

    events = _parse_sse_events(served)
    error_events = [e for e in events if 'error' in e]
    assert len(error_events) == 1, f'expected exactly one error event, got {events!r}'
    err = error_events[0]['error']

    assert isinstance(err, dict), f'error must be an object, got {err!r}'
    assert set(err.keys()) == {'code', 'message'}
    assert err['code'] == 'upstream_failed'
    assert isinstance(err['message'], str) and err['message']
    full_payload = json.dumps(events)
    assert 'another secret detail' not in full_payload


def test_both_streams_use_the_same_error_shape_helper():
    # Direct check that both call sites funnel through the one helper (see
    # chat_stream.py source) -- a static guard against a future edit
    # reintroducing a bespoke shape at one of the two sites.
    import inspect
    import chat_stream

    src_chat = inspect.getsource(chat_stream._chat_stream)
    src_smart = inspect.getsource(chat_stream._smart_chat_stream)
    assert '_sse_error_event(' in src_chat
    assert '_sse_error_event(' in src_smart
