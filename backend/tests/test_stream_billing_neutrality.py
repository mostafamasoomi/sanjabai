"""Stripping a leaked reasoning block must not change what the user is billed.

`_chat_stream` scrubs `<thought>`/`<think>` blocks out of the SSE it forwards,
so the user stops seeing a model's raw scratchpad. That scrub must stay purely
cosmetic. `accum_text` -- the list the stream builds while forwarding -- feeds
the L1 output-token ESTIMATE, which runs only when the upstream sent no usage
block at all, and which `_record_usage` already documents as a known lower
bound.

If the estimate were built from the CLEANED text, removing a reasoning block
would also shrink the bill, and a model that replies with nothing but a
thought block would estimate zero output tokens for work the upstream really
did. That is not hypothetical: `sanjab/gemma-4-26b-a4b-it` answered the prompt
"hi" with exactly `<thought>*   </thought>` and nothing else. Whether we pay
that upstream per token is not knowable from inside this process, so the
product rule that no request may be loss-making settles it -- estimate from
raw.

These tests pin that down from both directions: the client must receive the
cleaned text, and the billing path must receive the raw text, from one and the
same stream.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


class _FakeStream:
    """Minimal stand-in for `httpx.AsyncClient.stream(...)`'s context manager."""

    def __init__(self, lines):
        self._lines = lines
        self.status_code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _sse(**chunk):
    return f'data: {json.dumps(chunk)}'


def _delta(text):
    return _sse(id='c1', object='chat.completion.chunk', created=1, model='m',
                choices=[{'index': 0, 'delta': {'content': text},
                          'finish_reason': None}])


async def _drive(monkeypatch, pieces):
    """Run _chat_stream over `pieces` and return (served_text, billed_text).

    No usage chunk is emitted on purpose -- that is exactly the condition
    under which accum_text is used at all.
    """
    import chat as chat_mod

    lines = [_delta(p) for p in pieces] + ['data: [DONE]']

    captured = {}

    async def _fake_bill(uid, payload, usage, response_text=''):
        captured['billed'] = response_text
        return None

    class _Req:
        async def is_disconnected(self):
            return False

    monkeypatch.setattr(chat_mod, '_bill_stream_usage', _fake_bill)
    monkeypatch.setattr(chat_mod, '_fire_memory_extraction', lambda *a, **k: None)
    monkeypatch.setattr(chat_mod, 'async_session', object())
    monkeypatch.setattr(chat_mod, '_resolve_provider',
                        AsyncMock(return_value=type('P', (), {
                            'v1': 'http://up/v1', 'name': 'ninerouter',
                            'headers': lambda self: {}})()))
    # `chat._http` is database.py's lazy proxy; it raises until the lifespan
    # sets the real client, so the fake has to be installed underneath it.
    import database as _db

    monkeypatch.setattr(
        _db, '_real_http',
        type('H', (), {'stream': lambda self, *a, **k: _FakeStream(lines)})())

    served = []
    with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)):
        response = await chat_mod._chat_stream({'model': 'm', 'messages': []}, _Req())
        async for out in response.body_iterator:
            served.append(out)

    text = ''
    for block in ''.join(served).split('\n\n'):
        block = block.strip()
        if not block.startswith('data:'):
            continue
        body = block[5:].strip()
        if body == '[DONE]':
            continue
        try:
            parsed = json.loads(body)
        except ValueError:
            continue
        for choice in parsed.get('choices') or []:
            piece = (choice.get('delta') or {}).get('content')
            if isinstance(piece, str):
                text += piece
    return text, captured.get('billed')


@pytest.mark.asyncio
async def test_thought_block_is_hidden_from_the_user_but_still_billed(monkeypatch):
    served, billed = await _drive(
        monkeypatch, ['<thought>', 'internal scratch', '</thought>', 'سلام'])
    assert 'thought' not in served, f'reasoning leaked to the user: {served!r}'
    assert 'internal scratch' not in served
    assert 'سلام' in served
    # The raw text -- including the scratchpad -- is what the estimate sees.
    assert billed is not None and 'internal scratch' in billed


@pytest.mark.asyncio
async def test_a_thought_only_reply_still_has_something_to_bill(monkeypatch):
    """The observed gemma-4-26b case: the whole answer was a thought block."""
    served, billed = await _drive(monkeypatch, ['<thought>*   </thought>'])
    assert served.strip() == '', f'expected nothing visible, got {served!r}'
    assert billed, 'a thought-only reply billed nothing -- served-for-free path'


@pytest.mark.asyncio
async def test_clean_text_is_unchanged_in_both_directions(monkeypatch):
    served, billed = await _drive(monkeypatch, ['سلام ', 'دنیا'])
    assert served == 'سلام دنیا'
    assert billed == 'سلام دنیا'
