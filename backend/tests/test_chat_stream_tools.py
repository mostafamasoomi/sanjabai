"""Tests for the SSE tool-calling loop (chat_stream_tools.py, Phase 8 packet
B5).

MONKEYPATCH CONTRACT: `chat_stream_tools.py` does a plain `import chat` and
reaches every seam as `chat.<name>` at call time (same convention as
chat_tool_loop.py/chat_stream.py), so this file patches those seams on
`chat_mod`. `BillingService`, `autonomy_level_for`, `max_cost_per_message_toman`
are imported BY NAME into `chat_stream_tools` (again mirroring
chat_tool_loop.py's own test file), so those three are patched on
`chat_stream_tools` directly.

`pytest-asyncio` IS installed (see chat_tool_loop.py's test file) -- every
async test carries an explicit `@pytest.mark.asyncio`.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import chat as chat_mod
import chat_stream as chat_stream_mod
import chat_stream_tools as cst
from services.chat_tools import dispatch as real_dispatch_tool


# ── Fakes shared by every test below ───────────────────────────────────────

class _FakeRequest:
    """`is_disconnected()` returns False for the first `disconnect_after`
    calls, then True forever -- the streaming loop calls this MANY more
    times per round than the non-streaming loop (once per SSE line), so a
    call-count threshold is far less fragile than a hand-written sequence.
    `sequence`, when given, takes priority and is popped in order (kept for
    the couple of tests where an exact hand-count is clearer than a
    threshold)."""

    def __init__(self, sequence: list[bool] | None = None, disconnect_after: int | None = None):
        self._sequence = list(sequence) if sequence is not None else None
        self._disconnect_after = disconnect_after
        self.calls = 0

    async def is_disconnected(self) -> bool:
        self.calls += 1
        if self._sequence is not None:
            return self._sequence.pop(0) if self._sequence else False
        if self._disconnect_after is not None:
            return self.calls > self._disconnect_after
        return False


class _FakeProvider:
    v1 = 'http://fake-upstream'

    def headers(self) -> dict[str, str]:
        return {}


class _FakeSSEStream:
    """Minimal stand-in for `httpx.AsyncClient.stream(...)`'s context manager
    (same shape as test_stream_billing_neutrality.py's `_FakeStream`)."""

    def __init__(self, lines: list[str]):
        self._lines = lines
        self.status_code = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeHttp:
    """`chat._http` double: `.stream(...)` returns the NEXT queued
    `_FakeSSEStream`, one per round, and records every call's `json` body so
    tests can inspect what a round actually sent upstream (e.g. the
    reconstructed `messages`/`tools`)."""

    def __init__(self, round_lines: list[list[str]] | None = None):
        self._streams = [_FakeSSEStream(lines) for lines in (round_lines or [])]
        self.calls: list[dict] = []

    def stream(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append({'method': method, 'url': url, 'json': json, 'headers': headers, 'timeout': timeout})
        return self._streams.pop(0)


def _make_fake_billing_service(record: dict):
    class _Svc:
        def __init__(self, repo):
            self.repo = repo

        async def reserve(self, uid, amount, idempotency_key=None, model=None, price_version=None):
            record['reserve_calls'] = record.get('reserve_calls', 0) + 1
            record['reserve_amount'] = amount
            return {'reservation_id': 'resv-1', 'user_id': uid, 'hold_amount': amount.toman, 'status': 'reserved'}

    return _Svc


def _fake_async_session_factory():
    class _Ctx:
        async def __aenter__(self):
            self.session = MagicMock()
            self.session.commit = AsyncMock()
            return self.session

        async def __aexit__(self, *args):
            return False

    return MagicMock(side_effect=lambda: _Ctx())


@pytest.fixture
def stream_env(monkeypatch):
    """Common seam wiring, mirroring chat_tool_loop.py's `loop_env` fixture."""
    record: dict[str, Any] = {}

    monkeypatch.setattr(chat_mod, 'async_session', _fake_async_session_factory())
    monkeypatch.setattr(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider()))
    monkeypatch.setattr(chat_mod, '_fire_memory_extraction', MagicMock())
    monkeypatch.setattr(chat_mod, '_release_reservation', AsyncMock())
    # Healthy-by-default: an empty/zero cost_info would leave `balance_after`
    # at its 0 initial value and spuriously trip the `balance_after <= 0`
    # ceiling on the very first tool-calling round. Tests that specifically
    # exercise the ceiling override this explicitly.
    monkeypatch.setattr(chat_mod, '_bill_stream_usage', AsyncMock(
        return_value={'cost': 10, 'input_tokens': 1, 'output_tokens': 1, 'balance_after': 9_000}))
    monkeypatch.setattr(chat_mod, 'is_working_model', AsyncMock(return_value=True))

    monkeypatch.setattr(cst, 'BillingService', _make_fake_billing_service(record))
    monkeypatch.setattr(cst, 'autonomy_level_for', AsyncMock(return_value='high'))
    monkeypatch.setattr(cst, 'max_cost_per_message_toman', AsyncMock(return_value=15_000))
    monkeypatch.setattr(cst, 'dispatch_tool', AsyncMock(return_value={'ok': True, 'models': []}))

    return record


def _payload(model: str = 'working-model', **extra) -> dict:
    base = {'model': model, 'messages': [{'role': 'user', 'content': 'سلام'}]}
    base.update(extra)
    return base


def _set_bill_stream_usage(monkeypatch, *cost_infos: dict):
    monkeypatch.setattr(chat_mod, '_bill_stream_usage', AsyncMock(side_effect=list(cost_infos)))


async def _drive(monkeypatch, round_lines: list[list[str]], *, request=None, payload=None, **kwargs):
    """Wire `chat._http` to `round_lines` (one list of raw SSE lines per
    round), run `stream_tool_loop`, and return `(out_lines, fake_http)` --
    `out_lines` is the exact list of strings the generator yielded, in
    order."""
    fake_http = _FakeHttp(round_lines)
    monkeypatch.setattr(chat_mod, '_http', fake_http)
    resp = await cst.stream_tool_loop(request or _FakeRequest(), 7, payload or _payload(), **kwargs)
    out = []
    async for chunk in resp.body_iterator:
        out.append(chunk)
    return out, fake_http


def _sse(**chunk) -> str:
    return f'data: {json.dumps(chunk)}'


def _content_chunk(text: str, finish_reason: str | None = None, resp_id='c1', model='m') -> str:
    return _sse(id=resp_id, object='chat.completion.chunk', created=1, model=model,
                choices=[{'index': 0, 'delta': {'content': text}, 'finish_reason': finish_reason}])


def _tool_call_fragment(index: int, *, id: str | None = None, name: str | None = None,
                         arguments: str | None = None, resp_id='c1', model='m') -> str:
    fn: dict = {}
    if name is not None:
        fn['name'] = name
    if arguments is not None:
        fn['arguments'] = arguments
    tc: dict = {'index': index}
    if id is not None:
        tc['id'] = id
        tc['type'] = 'function'
    if fn:
        tc['function'] = fn
    return _sse(id=resp_id, object='chat.completion.chunk', created=1, model=model,
                choices=[{'index': 0, 'delta': {'tool_calls': [tc]}, 'finish_reason': None}])


def _finish_reason_chunk(reason: str, resp_id='c1', model='m') -> str:
    return _sse(id=resp_id, object='chat.completion.chunk', created=1, model=model,
                choices=[{'index': 0, 'delta': {}, 'finish_reason': reason}])


def _usage_chunk(prompt_tokens=10, completion_tokens=5, resp_id='c1', model='m') -> str:
    return _sse(id=resp_id, object='chat.completion.chunk', created=1, model=model, choices=[],
                usage={'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens,
                       'total_tokens': prompt_tokens + completion_tokens})


_DONE = 'data: [DONE]'


def _tool_call_round(*, index=0, call_id='call1', name='list_models', arguments='{}') -> list[str]:
    """One round's worth of SSE lines: a single tool_calls fragment (id/name/
    arguments all in one chunk), then the finish_reason chunk, then usage,
    then DONE -- the common real-world shape."""
    return [
        _tool_call_fragment(index, id=call_id, name=name, arguments=arguments),
        _finish_reason_chunk('tool_calls'),
        _usage_chunk(),
        _DONE,
    ]


def _final_answer_round(text: str) -> list[str]:
    return [_content_chunk(text), _finish_reason_chunk('stop'), _usage_chunk(), _DONE]


def _events_of_type(out: list[str], type_: str) -> list[dict]:
    result = []
    for line in out:
        body = line.strip()
        if not body.startswith('data:'):
            continue
        raw = body[5:].strip()
        if raw == '[DONE]':
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if obj.get('type') == type_:
            result.append(obj)
    return result


def _forwarded_content_text(out: list[str]) -> str:
    """Reconstruct the visible answer text from ordinary (untyped) chunks --
    mirrors test_stream_billing_neutrality.py's `_drive`. `json.dumps`
    ascii-escapes non-ASCII by default (same as chat_stream.py's own flush
    chunk), so a raw substring check against `out` would never match Persian
    text -- this parses each line back to text first."""
    text = ''
    for line in out:
        body = line.strip()
        if not body.startswith('data:'):
            continue
        raw = body[5:].strip()
        if raw == '[DONE]':
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if obj.get('type'):
            continue  # our own typed events (tool_call/tool_result/tool_confirm/billing)
        for choice in obj.get('choices') or []:
            piece = (choice.get('delta') or {}).get('content')
            if isinstance(piece, str):
                text += piece
    return text


# ── 1. Additive proof: no tool_calls => byte-identical to today's _chat_stream ──

class TestNoToolCallsIsByteIdenticalToTodaysStream:
    @pytest.mark.asyncio
    async def test_single_round_no_tool_calls_matches_chat_stream_plus_done(self, stream_env, monkeypatch):
        """Drives BOTH `_chat_stream` (today's SSE loop) and `stream_tool_loop`
        (this packet) over the exact same upstream chunk sequence and asserts
        the tool loop's output equals the plain loop's output with exactly one
        extra line appended: `data: [DONE]\\n\\n`. This is the proof the
        change is additive."""
        lines = [
            _content_chunk('سلام '), _content_chunk('دنیا'),
            _content_chunk(None, finish_reason='stop'), _usage_chunk(), _DONE,
        ]
        cost_info = {'cost': 500, 'input_tokens': 10, 'output_tokens': 5, 'balance_after': 9_500}

        # -- side A: today's _chat_stream --
        monkeypatch.setattr(chat_mod, '_bill_stream_usage', AsyncMock(return_value=cost_info))
        monkeypatch.setattr(chat_mod, '_get_user_id', AsyncMock(return_value=7))
        monkeypatch.setattr(chat_mod, '_http', _FakeHttp([lines]))
        old_resp = await chat_stream_mod._chat_stream({'model': 'm', 'messages': []}, _FakeRequest())
        old_out = [c async for c in old_resp.body_iterator]

        # -- side B: the tool loop, same chunks, no tool_calls ever appear --
        monkeypatch.setattr(chat_mod, '_bill_stream_usage', AsyncMock(return_value=cost_info))
        new_out, fake_http = await _drive(monkeypatch, [lines])

        assert new_out == old_out + ['data: [DONE]\n\n']
        assert fake_http.calls[0]['json']['tools'], 'the loop must still announce tools upstream'


# ── 2/3. The two chunk shapes that must never reach the client ─────────────

class TestDeltaToolCallsNeverForwarded:
    @pytest.mark.asyncio
    async def test_tool_calls_fragment_chunks_never_appear_in_client_bytes(self, stream_env, monkeypatch):
        out, _ = await _drive(monkeypatch, [_tool_call_round(), _final_answer_round('باشه')])
        for line in out:
            assert '"tool_calls"' not in line, f'a raw tool_calls delta leaked: {line!r}'


class TestFinishReasonToolCallsChunkNeverForwarded:
    @pytest.mark.asyncio
    async def test_finish_reason_tool_calls_chunk_never_appears_in_client_bytes(self, stream_env, monkeypatch):
        out, _ = await _drive(monkeypatch, [_tool_call_round(), _final_answer_round('باشه')])
        for line in out:
            assert 'tool_calls' not in line or '"type": "tool_call"' in line or '"type":"tool_call"' in line
            assert '"finish_reason": "tool_calls"' not in line
            assert '"finish_reason":"tool_calls"' not in line


# ── 4/5. Fragment reassembly ────────────────────────────────────────────────

class TestFragmentedArgumentsReassemble:
    @pytest.mark.asyncio
    async def test_arguments_split_across_many_chunks_reassemble_exactly(self, stream_env, monkeypatch):
        round1 = [
            _tool_call_fragment(0, id='call1', name='create_task'),
            _tool_call_fragment(0, arguments='{"tit'),
            _tool_call_fragment(0, arguments='le": '),
            _tool_call_fragment(0, arguments='"X"}'),
            _finish_reason_chunk('tool_calls'),
            _usage_chunk(),
            _DONE,
        ]
        dispatch_mock = AsyncMock(return_value={'ok': True})
        monkeypatch.setattr(cst, 'dispatch_tool', dispatch_mock)

        await _drive(monkeypatch, [round1, _final_answer_round('باشه')])

        dispatch_mock.assert_awaited_once_with(7, 'high', 'create_task', '{"title": "X"}')

    @pytest.mark.asyncio
    async def test_name_comes_from_the_first_fragment_not_a_later_redundant_one(self, stream_env, monkeypatch):
        """MUTATION 6 GUARD: a fragment stream where MORE THAN ONE fragment
        carries `function.name` -- the common single-name-only-once shape
        used by the other reassembly tests above cannot tell first-wins
        apart from last-wins (there is only one candidate value either way).
        Real upstreams can repeat the name on a later fragment; first-wins
        must still win."""
        round1 = [
            _tool_call_fragment(0, id='call1', name='create_task'),
            # A later fragment carrying a DIFFERENT name -- not a realistic
            # upstream shape by itself, but the only way to make first-wins
            # and last-wins produce different, observable outcomes.
            _tool_call_fragment(0, name='create_assistant', arguments='{}'),
            _finish_reason_chunk('tool_calls'),
            _usage_chunk(),
            _DONE,
        ]
        dispatch_mock = AsyncMock(return_value={'ok': True})
        monkeypatch.setattr(cst, 'dispatch_tool', dispatch_mock)

        await _drive(monkeypatch, [round1, _final_answer_round('باشه')])

        assert dispatch_mock.await_args.args[2] == 'create_task'


class TestTwoToolCallsInOneRoundInterleavedFragments:
    @pytest.mark.asyncio
    async def test_two_interleaved_tool_calls_both_reassemble_correctly(self, stream_env, monkeypatch):
        round1 = [
            _tool_call_fragment(0, id='call0', name='create_task', arguments='{"a'),
            _tool_call_fragment(1, id='call1', name='create_assistant', arguments='{"b'),
            _tool_call_fragment(0, arguments='":1}'),
            _tool_call_fragment(1, arguments='":2}'),
            _finish_reason_chunk('tool_calls'),
            _usage_chunk(),
            _DONE,
        ]
        dispatch_mock = AsyncMock(return_value={'ok': True})
        monkeypatch.setattr(cst, 'dispatch_tool', dispatch_mock)

        await _drive(monkeypatch, [round1, _final_answer_round('باشه')])

        assert dispatch_mock.await_count == 2
        first_call, second_call = dispatch_mock.await_args_list
        assert first_call.args == (7, 'high', 'create_task', '{"a":1}')
        assert second_call.args == (7, 'high', 'create_assistant', '{"b":2}')


# ── 6. tool_call before dispatch, tool_result after ─────────────────────────

class TestToolCallEventBeforeDispatchAndResultAfter:
    @pytest.mark.asyncio
    async def test_tool_call_event_precedes_dispatch_and_tool_result_follows(self, stream_env, monkeypatch):
        out, _ = await _drive(monkeypatch, [_tool_call_round(name='list_models'), _final_answer_round('باشه')])

        call_events = _events_of_type(out, 'tool_call')
        result_events = _events_of_type(out, 'tool_result')
        assert len(call_events) == 1 and call_events[0]['name'] == 'list_models'
        assert call_events[0]['status'] == 'running'
        assert len(result_events) == 1 and result_events[0]['name'] == 'list_models'
        assert result_events[0]['ok'] is True

        call_idx = next(i for i, line in enumerate(out) if '"type": "tool_call"' in line or '"type":"tool_call"' in line)
        result_idx = next(i for i, line in enumerate(out) if '"type": "tool_result"' in line or '"type":"tool_result"' in line)
        assert call_idx < result_idx

    @pytest.mark.asyncio
    async def test_needs_confirmation_emits_tool_confirm_not_tool_result(self, stream_env, monkeypatch):
        monkeypatch.setattr(cst, 'dispatch_tool', AsyncMock(return_value={
            'ok': False, 'needs_confirmation': True, 'preview': {'title': 'X', 'cron_expression': '0 9 * * *'},
        }))
        out, _ = await _drive(monkeypatch, [
            _tool_call_round(name='create_task'), _final_answer_round('لطفاً تأیید کنید'),
        ])

        assert _events_of_type(out, 'tool_result') == []
        confirm_events = _events_of_type(out, 'tool_confirm')
        assert len(confirm_events) == 1
        assert confirm_events[0]['name'] == 'create_task'
        assert confirm_events[0]['preview'] == {'title': 'X', 'cron_expression': '0 9 * * *'}


# ── 7. Disconnect contract ──────────────────────────────────────────────────

class TestDisconnectContract:
    @pytest.mark.asyncio
    async def test_disconnect_before_dispatch_the_tool_does_not_run(self, stream_env, monkeypatch):
        # round 1 = [combined tool_calls+finish_reason chunk, usage, DONE] -> 3 lines.
        # is_disconnected() calls: 1 (top-of-round) + 3 (one per line) = 4, all False;
        # the 5th call is the "before dispatch" check -> True.
        round1 = [
            _sse(id='c1', object='chat.completion.chunk', created=1, model='m', choices=[{
                'index': 0,
                'delta': {'tool_calls': [{'index': 0, 'id': 'call1', 'type': 'function',
                                           'function': {'name': 'list_models', 'arguments': '{}'}}]},
                'finish_reason': 'tool_calls',
            }]),
            _usage_chunk(),
            _DONE,
        ]
        dispatch_mock = AsyncMock()
        monkeypatch.setattr(cst, 'dispatch_tool', dispatch_mock)
        request = _FakeRequest(disconnect_after=4)

        out, fake_http = await _drive(monkeypatch, [round1], request=request)

        assert len(fake_http.calls) == 1, 'round 1 was metered'
        dispatch_mock.assert_not_awaited()
        assert _events_of_type(out, 'tool_call') == []
        assert out[-1] == 'data: [DONE]\n\n'
        assert chat_mod._release_reservation.await_count == 1

    @pytest.mark.asyncio
    async def test_disconnect_after_dispatch_side_effect_stands_no_further_round(self, stream_env, monkeypatch):
        # Same round-1 shape as above (4 is_disconnected calls to complete it
        # cleanly), plus 1 more for the "before dispatch" check (still False,
        # so dispatch DOES run) -> 5 calls total complete round 1 through
        # dispatch; the 6th call is round 2's top-of-loop check -> True.
        round1 = [
            _sse(id='c1', object='chat.completion.chunk', created=1, model='m', choices=[{
                'index': 0,
                'delta': {'tool_calls': [{'index': 0, 'id': 'call1', 'type': 'function',
                                           'function': {'name': 'list_models', 'arguments': '{}'}}]},
                'finish_reason': 'tool_calls',
            }]),
            _usage_chunk(),
            _DONE,
        ]
        dispatch_mock = AsyncMock(return_value={'ok': True, 'models': []})
        monkeypatch.setattr(cst, 'dispatch_tool', dispatch_mock)
        request = _FakeRequest(disconnect_after=5)

        out, fake_http = await _drive(monkeypatch, [round1, _final_answer_round('never reached')], request=request)

        dispatch_mock.assert_awaited_once()
        assert len(fake_http.calls) == 1, 'round 2 never opened an upstream stream'
        assert out[-1] == 'data: [DONE]\n\n'


# ── 8. Release exactly once, every exit path ────────────────────────────────

class TestReleaseCalledExactlyOnce:
    @pytest.mark.asyncio
    async def test_release_runs_on_the_ordinary_success_path(self, stream_env, monkeypatch):
        await _drive(monkeypatch, [_final_answer_round('ok')])
        assert chat_mod._release_reservation.await_count == 1

    @pytest.mark.asyncio
    async def test_release_runs_when_a_rounds_upstream_call_raises(self, stream_env, monkeypatch):
        fake_http = MagicMock()
        fake_http.stream = MagicMock(side_effect=ConnectionError('upstream unreachable'))
        monkeypatch.setattr(chat_mod, '_http', fake_http)

        resp = await cst.stream_tool_loop(_FakeRequest(), 7, _payload())
        out = [c async for c in resp.body_iterator]

        assert out[-1] == 'data: [DONE]\n\n'
        assert chat_mod._release_reservation.await_count == 1

    @pytest.mark.asyncio
    async def test_release_runs_even_when_dispatch_itself_raises(self, stream_env, monkeypatch):
        monkeypatch.setattr(cst, 'dispatch_tool', AsyncMock(side_effect=RuntimeError('boom')))
        fake_http = _FakeHttp([_tool_call_round()])
        monkeypatch.setattr(chat_mod, '_http', fake_http)

        resp = await cst.stream_tool_loop(_FakeRequest(), 7, _payload())
        with pytest.raises(RuntimeError):
            async for _ in resp.body_iterator:
                pass

        assert chat_mod._release_reservation.await_count == 1


# ── 9. Cost ceiling / balance exhausted end the loop independently ─────────

class TestCostCeilingAndBalanceExhaustedIndependentlyEndTheLoop:
    @pytest.mark.asyncio
    async def test_cost_ceiling_ends_loop_and_notice_reaches_client(self, stream_env, monkeypatch):
        monkeypatch.setattr(cst, 'max_cost_per_message_toman', AsyncMock(return_value=100))
        monkeypatch.setattr(chat_mod, '_bill_stream_usage', AsyncMock(
            return_value={'cost': 200, 'input_tokens': 10, 'output_tokens': 5, 'balance_after': 50_000}))
        dispatch_mock = AsyncMock()
        monkeypatch.setattr(cst, 'dispatch_tool', dispatch_mock)

        out, fake_http = await _drive(monkeypatch, [_tool_call_round()])

        assert len(fake_http.calls) == 1
        dispatch_mock.assert_not_awaited()
        assert cst.CEILING_NOTICE_FA in _forwarded_content_text(out)
        assert out[-1] == 'data: [DONE]\n\n'

    @pytest.mark.asyncio
    async def test_balance_after_zero_ends_loop_even_though_ceiling_not_hit(self, stream_env, monkeypatch):
        monkeypatch.setattr(chat_mod, '_bill_stream_usage', AsyncMock(
            return_value={'cost': 100, 'input_tokens': 10, 'output_tokens': 5, 'balance_after': 0}))
        dispatch_mock = AsyncMock()
        monkeypatch.setattr(cst, 'dispatch_tool', dispatch_mock)

        out, fake_http = await _drive(monkeypatch, [_tool_call_round()])

        assert len(fake_http.calls) == 1
        dispatch_mock.assert_not_awaited()
        assert cst.CEILING_NOTICE_FA in _forwarded_content_text(out)


# ── 10. Billing event sums every round ──────────────────────────────────────

class TestBillingEventSumsEveryRound:
    @pytest.mark.asyncio
    async def test_billing_event_is_the_sum_across_both_rounds(self, stream_env, monkeypatch):
        _set_bill_stream_usage(
            monkeypatch,
            {'cost': 200, 'input_tokens': 10, 'output_tokens': 5, 'balance_after': 9_800},
            {'cost': 300, 'input_tokens': 20, 'output_tokens': 8, 'balance_after': 9_500},
        )

        out, _ = await _drive(monkeypatch, [_tool_call_round(), _final_answer_round('این مدل‌ها موجودند.')])

        billing_events = _events_of_type(out, 'billing')
        assert len(billing_events) == 1
        assert billing_events[0]['cost'] == 500
        assert billing_events[0]['input_tokens'] == 30
        assert billing_events[0]['output_tokens'] == 13
        assert billing_events[0]['balance_after'] == 9_500
        assert billing_events[0]['currency'] == 'IRT'


# ── 11. [DONE] is always the last line ──────────────────────────────────────

class TestDoneIsAlwaysLastLine:
    @pytest.mark.asyncio
    async def test_done_is_last_line_no_tool_calls(self, stream_env, monkeypatch):
        out, _ = await _drive(monkeypatch, [_final_answer_round('ok')])
        assert out[-1] == 'data: [DONE]\n\n'

    @pytest.mark.asyncio
    async def test_done_is_last_line_after_a_tool_round(self, stream_env, monkeypatch):
        out, _ = await _drive(monkeypatch, [_tool_call_round(), _final_answer_round('باشه')])
        assert out[-1] == 'data: [DONE]\n\n'

    @pytest.mark.asyncio
    async def test_done_is_last_line_at_max_tool_rounds_ceiling(self, stream_env, monkeypatch):
        always_wants_a_tool = [_tool_call_round() for _ in range(cst.MAX_TOOL_ROUNDS)]
        _set_bill_stream_usage(monkeypatch, *[
            {'cost': 10, 'input_tokens': 1, 'output_tokens': 1, 'balance_after': 9_000}
            for _ in range(cst.MAX_TOOL_ROUNDS)
        ])
        monkeypatch.setattr(cst, 'dispatch_tool', AsyncMock(return_value={'ok': True, 'models': []}))

        out, fake_http = await _drive(monkeypatch, always_wants_a_tool)

        assert len(fake_http.calls) == cst.MAX_TOOL_ROUNDS
        assert cst.CEILING_NOTICE_FA in _forwarded_content_text(out)
        assert out[-1] == 'data: [DONE]\n\n'


# ── Insufficient balance is refused before any upstream call ───────────────

class TestInsufficientBalanceRefusedBeforeUpstream:
    @pytest.mark.asyncio
    async def test_raises_before_the_streaming_response_is_even_built(self, stream_env, monkeypatch):
        from services.billing import InsufficientBalanceError

        class _RaisingSvc:
            def __init__(self, repo):
                pass

            async def reserve(self, *a, **k):
                raise InsufficientBalanceError('insufficient balance: available 0, requested 999')

        monkeypatch.setattr(cst, 'BillingService', _RaisingSvc)
        fake_http = _FakeHttp([])
        monkeypatch.setattr(chat_mod, '_http', fake_http)

        with pytest.raises(InsufficientBalanceError):
            await cst.stream_tool_loop(_FakeRequest(), 7, _payload())

        assert fake_http.calls == []


# ── Real dispatch() survives an unknown tool name without breaking the loop ─

class TestUnknownToolNameDoesNotBreakTheLoop:
    @pytest.mark.asyncio
    async def test_unknown_tool_result_is_appended_and_the_loop_continues(self, stream_env, monkeypatch):
        monkeypatch.setattr(cst, 'dispatch_tool', real_dispatch_tool)
        round1 = _tool_call_round(name='delete_everything')

        out, fake_http = await _drive(monkeypatch, [round1, _final_answer_round('باشه، انجام نمی‌شود.')])

        assert len(fake_http.calls) == 2
        round2_messages = fake_http.calls[1]['json']['messages']
        assert json.loads(round2_messages[-1]['content']) == {'ok': False, 'error': 'unknown_tool'}
        result_events = _events_of_type(out, 'tool_result')
        assert result_events[0]['ok'] is False


# ── Reservation is rounds x estimate, covered requests reserve nothing ──────

class TestReservationIsRoundsTimesEstimate:
    @pytest.mark.asyncio
    async def test_known_working_model_reserves_rounds_times_1000(self, stream_env, monkeypatch):
        from services.money import Money

        await _drive(monkeypatch, [_final_answer_round('ok')])

        assert stream_env['reserve_amount'] == Money(1_000 * cst.MAX_TOOL_ROUNDS)

    @pytest.mark.asyncio
    async def test_covered_request_reserves_nothing(self, stream_env, monkeypatch):
        await _drive(monkeypatch, [_final_answer_round('ok')], covered=True)

        assert stream_env.get('reserve_calls', 0) == 0
