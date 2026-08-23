"""Phase E — token economy: outbound payload budget (services/token_budget.py).

Covers the three limits that keep an unbounded thread from being sent
upstream verbatim now that the upstream-side `caveman` compression is off:
E1 history window, E2 default max_tokens ceiling, E3 injection gating.

No live Postgres: the catalog read goes through the shared
``mock_async_session`` fixture from tests/conftest.py (same style as
tests/test_skill_injection.py).
"""
import pytest

from services.token_budget import (
    MAX_HISTORY_MESSAGES,
    apply_history_window,
)


def _turn(i: int) -> list[dict]:
    return [
        {'role': 'user', 'content': f'user-{i}'},
        {'role': 'assistant', 'content': f'assistant-{i}'},
    ]


def _thread(n_turns: int) -> list[dict]:
    out: list[dict] = []
    for i in range(n_turns):
        out.extend(_turn(i))
    return out


class TestHistoryWindow:
    def test_short_thread_is_untouched(self):
        msgs = _thread(3)
        assert apply_history_window([dict(m) for m in msgs]) == msgs

    def test_caps_non_system_message_count(self):
        msgs = _thread(60)  # 120 non-system messages
        out = apply_history_window(msgs)
        non_system = [m for m in out if m.get('role') != 'system']
        assert len(non_system) == MAX_HISTORY_MESSAGES

    def test_keeps_the_most_recent_turns_not_the_oldest(self):
        msgs = _thread(60)
        out = apply_history_window(msgs)
        contents = [m.get('content') for m in out]
        assert 'assistant-59' in contents
        assert 'user-0' not in contents

    def test_preserves_every_system_message(self):
        msgs = (
            [{'role': 'system', 'content': 'assistant prompt'},
             {'role': 'system', 'content': '[User Memories]\n- x'}]
            + _thread(60)
        )
        out = apply_history_window(msgs)
        systems = [m for m in out if m.get('role') == 'system']
        assert [m['content'] for m in systems][:2] == ['assistant prompt', '[User Memories]\n- x']

    def test_adds_a_deterministic_trim_note_when_it_drops_turns(self):
        out = apply_history_window(_thread(60))
        # Deterministic: no model is called to build it.
        notes = [m for m in out if m.get('role') == 'system' and 'گفتگو' in (m.get('content') or '')]
        assert len(notes) == 1

    def test_no_trim_note_when_nothing_was_dropped(self):
        out = apply_history_window(_thread(2))
        assert all(m.get('role') != 'system' for m in out)

    def test_is_idempotent(self):
        once = apply_history_window(_thread(60))
        twice = apply_history_window([dict(m) for m in once])
        assert twice == once

    def test_does_not_mutate_the_caller_list(self):
        msgs = _thread(60)
        before = len(msgs)
        apply_history_window(msgs)
        assert len(msgs) == before

    @pytest.mark.parametrize('bad', [None, [], 'not-a-list', [None, 3, 'x']])
    def test_degrades_to_send_what_we_had_on_garbage(self, bad):
        # Never raise on the hot path.
        assert apply_history_window(bad) is not None


# ── E2: default max_tokens ceiling ────────────────────────────────────
from unittest.mock import AsyncMock, patch  # noqa: E402

from tests.conftest import make_result, make_row  # noqa: E402

import services.token_budget as tb  # noqa: E402


def _catalog(value):
    """Patch the per-model catalog lookup with a fixed max_output_tokens."""
    return patch.object(tb, '_get_model_max_output_tokens', new=AsyncMock(return_value=value))


class TestMaxTokensCeiling:
    @pytest.mark.asyncio
    async def test_applies_default_when_client_sent_nothing(self):
        with _catalog(None):
            assert await tb.resolve_max_tokens('m', None) == tb.DEFAULT_MAX_OUTPUT_TOKENS

    @pytest.mark.asyncio
    async def test_default_is_clamped_by_a_smaller_catalog_limit(self):
        with _catalog(512):
            assert await tb.resolve_max_tokens('m', None) == 512

    @pytest.mark.asyncio
    async def test_large_catalog_limit_does_not_raise_the_default(self):
        with _catalog(131072):
            assert await tb.resolve_max_tokens('m', None) == tb.DEFAULT_MAX_OUTPUT_TOKENS

    @pytest.mark.asyncio
    async def test_never_raises_a_lower_client_value(self):
        with _catalog(131072):
            assert await tb.resolve_max_tokens('m', 128) == 128

    @pytest.mark.asyncio
    async def test_client_value_is_clamped_by_the_catalog_limit(self):
        with _catalog(64000):
            assert await tb.resolve_max_tokens('m', 500000) == 64000

    @pytest.mark.asyncio
    async def test_zero_or_negative_client_value_is_treated_as_absent(self):
        with _catalog(None):
            assert await tb.resolve_max_tokens('m', 0) == tb.DEFAULT_MAX_OUTPUT_TOKENS
            assert await tb.resolve_max_tokens('m', -5) == tb.DEFAULT_MAX_OUTPUT_TOKENS

    @pytest.mark.asyncio
    async def test_catalog_failure_degrades_to_the_default(self):
        with patch.object(tb, '_get_model_max_output_tokens',
                          new=AsyncMock(side_effect=RuntimeError('db down'))):
            assert await tb.resolve_max_tokens('m', None) == tb.DEFAULT_MAX_OUTPUT_TOKENS


class TestCatalogLookup:
    @pytest.mark.asyncio
    async def test_reads_max_output_tokens_from_model_catalog(self, mock_async_session):
        tb._MAX_OUT_CACHE, tb._MAX_OUT_CACHE_LOADED_AT = {}, 0.0
        mock_async_session._execute_result = make_result(fetchall=[
            make_row(id='tencent-hy3', provider_model_id='sanjab/tencent-hy3', max_output_tokens=8192),
        ])
        assert await tb._get_model_max_output_tokens('tencent-hy3') == 8192
        # provider_model_id is the id that actually reaches the hot path
        assert await tb._get_model_max_output_tokens('sanjab/tencent-hy3') == 8192
        assert await tb._get_model_max_output_tokens('unknown-model') is None

    @pytest.mark.asyncio
    async def test_db_failure_keeps_previous_cache_instead_of_raising(self, mock_async_session):
        tb._MAX_OUT_CACHE, tb._MAX_OUT_CACHE_LOADED_AT = {'m': 4096}, 0.0

        async def boom(*a, **k):
            raise RuntimeError('db down')

        mock_async_session.execute = boom
        assert await tb._get_model_max_output_tokens('m') == 4096


# ── E3: gating the ~9.5k-char injection block ─────────────────────────
from services.context_injection import get_injection_messages  # noqa: E402


def _payload_at_turn(n: int) -> list[dict]:
    """Payload the client sends on its n-th turn: n user messages, n-1 replies."""
    out: list[dict] = []
    for i in range(n - 1):
        out.append({'role': 'user', 'content': f'u{i}'})
        out.append({'role': 'assistant', 'content': f'a{i}'})
    out.append({'role': 'user', 'content': f'u{n - 1}'})
    return out


class TestInjectionGate:
    def test_injects_on_the_first_turn(self):
        assert tb.should_inject_context(_payload_at_turn(1)) is True

    def test_skips_the_turns_in_between(self):
        skipped = [n for n in range(2, tb.INJECT_CONTEXT_EVERY_N_TURNS + 1)
                   if not tb.should_inject_context(_payload_at_turn(n))]
        assert skipped == list(range(2, tb.INJECT_CONTEXT_EVERY_N_TURNS + 1))

    def test_re_injects_every_n_turns(self):
        n = tb.INJECT_CONTEXT_EVERY_N_TURNS
        assert tb.should_inject_context(_payload_at_turn(n + 1)) is True
        assert tb.should_inject_context(_payload_at_turn(2 * n + 1)) is True

    def test_system_messages_do_not_count_as_turns(self):
        msgs = [{'role': 'system', 'content': 'x'}] * 10 + _payload_at_turn(1)
        assert tb.should_inject_context(msgs) is True

    @pytest.mark.parametrize('bad', [None, [], 'nope', [None, 1]])
    def test_degrades_to_injecting_on_garbage(self, bad):
        assert tb.should_inject_context(bad) is True

    def test_small_injections_bypass_the_turn_gate(self):
        gated_turn = _payload_at_turn(3)
        assert tb.should_inject_context(gated_turn) is False  # turn-only view
        assert tb.should_inject_context(gated_turn, injection_chars=102) is True

    def test_large_injections_still_obey_the_turn_gate(self):
        big = tb.INJECT_ALWAYS_UNDER_CHARS
        assert tb.should_inject_context(_payload_at_turn(3), injection_chars=big) is False
        assert tb.should_inject_context(_payload_at_turn(1), injection_chars=big) is True

    def test_threshold_is_inclusive_at_the_top(self):
        n = tb.INJECT_ALWAYS_UNDER_CHARS
        assert tb.should_inject_context(_payload_at_turn(3), injection_chars=n - 1) is True
        assert tb.should_inject_context(_payload_at_turn(3), injection_chars=n) is False

    def test_unknown_size_keeps_the_turn_only_behaviour(self):
        assert tb.should_inject_context(_payload_at_turn(3), injection_chars=None) is False


def _no_user_context():
    """Patch every source get_injection_messages reads, with a soul set."""
    return [
        patch('dependencies._get_user_memories', new=AsyncMock(return_value=['fact'])),
        patch('dependencies._get_user_soul', new=AsyncMock(return_value='لحن رسمی')),
        patch('dependencies._get_user_pinned_context', new=AsyncMock(return_value='')),
        patch('services.skill_injection.get_active_skill_messages', new=AsyncMock(return_value=[])),
    ]


class TestGetInjectionMessagesGating:
    @pytest.mark.asyncio
    async def test_still_injects_when_no_messages_are_passed(self):
        # Back-compat: a caller that does not opt in keeps the old behaviour.
        with _no_user_context()[0], _no_user_context()[1], _no_user_context()[2], _no_user_context()[3]:
            injs = await get_injection_messages(uid=1)
        assert injs

    @pytest.mark.asyncio
    async def test_injects_on_the_first_turn(self):
        with _no_user_context()[0], _no_user_context()[1], _no_user_context()[2], _no_user_context()[3]:
            injs = await get_injection_messages(uid=1, messages=_payload_at_turn(1))
        assert injs

    @pytest.mark.asyncio
    async def test_small_context_is_still_injected_on_a_gated_turn(self):
        # Injections are ephemeral per request: a gated turn means the model
        # sees NO memory at all, not "it already saw it". For a context this
        # cheap that is pure quality loss for ~no saving.
        with _no_user_context()[0], _no_user_context()[1], _no_user_context()[2], _no_user_context()[3]:
            injs = await get_injection_messages(uid=1, messages=_payload_at_turn(3))
        assert injs

    @pytest.mark.asyncio
    async def test_large_context_is_gated(self):
        big = 'ب' * tb.INJECT_ALWAYS_UNDER_CHARS
        with patch('dependencies._get_user_memories', new=AsyncMock(return_value=[])), \
             patch('dependencies._get_user_soul', new=AsyncMock(return_value='')), \
             patch('dependencies._get_user_pinned_context', new=AsyncMock(return_value=big)), \
             patch('services.skill_injection.get_active_skill_messages', new=AsyncMock(return_value=[])):
            gated = await get_injection_messages(uid=1, messages=_payload_at_turn(3))
            first = await get_injection_messages(uid=1, messages=_payload_at_turn(1))
        assert gated == []
        assert first


# ── Wiring: one call per outbound payload, all six chat paths ─────────
import re  # noqa: E402
from pathlib import Path  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[1]
_CHAT_MODULES = ['chat.py', 'chat_stream.py', 'chat_web.py', 'chat_smart.py', 'chat_compare.py']


class TestApplyOutboundBudget:
    @pytest.mark.asyncio
    async def test_windows_history_and_sets_a_max_tokens_ceiling(self):
        payload = {'model': 'm', 'messages': _thread(60)}
        with _catalog(None):
            out = await tb.apply_outbound_budget(payload)
        assert len([m for m in out['messages'] if m.get('role') != 'system']) == MAX_HISTORY_MESSAGES
        assert out['max_tokens'] == tb.DEFAULT_MAX_OUTPUT_TOKENS

    @pytest.mark.asyncio
    async def test_keeps_a_lower_client_max_tokens(self):
        payload = {'model': 'm', 'messages': _thread(1), 'max_tokens': 64}
        with _catalog(None):
            out = await tb.apply_outbound_budget(payload)
        assert out['max_tokens'] == 64

    @pytest.mark.asyncio
    async def test_is_idempotent_across_two_chat_modules(self):
        payload = {'model': 'm', 'messages': _thread(60)}
        with _catalog(None):
            once = dict(await tb.apply_outbound_budget(payload))
            once['messages'] = list(once['messages'])
            twice = await tb.apply_outbound_budget(payload)
        assert twice['messages'] == once['messages']
        assert twice['max_tokens'] == once['max_tokens']

    @pytest.mark.asyncio
    async def test_never_raises_on_a_broken_payload(self):
        with _catalog(None):
            assert await tb.apply_outbound_budget(None) is None
            assert await tb.apply_outbound_budget({'messages': 'nope'}) is not None


class TestChatPathsAreWired:
    @pytest.mark.parametrize('module', _CHAT_MODULES)
    def test_every_injection_call_site_passes_the_payload_for_gating(self, module):
        src = (_BACKEND / module).read_text()
        calls = re.findall(r'get_injection_messages\((.*?)\)', src, re.S)
        calls = [c for c in calls if 'uid' in c]  # skip the def / docstring mentions
        assert calls, f'{module}: no get_injection_messages call found'
        for c in calls:
            assert 'messages=' in c, f'{module}: ungated injection call -> get_injection_messages({c})'

    @pytest.mark.parametrize('module', _CHAT_MODULES)
    def test_every_module_applies_the_outbound_budget(self, module):
        src = (_BACKEND / module).read_text()
        assert 'apply_outbound_budget(' in src, f'{module}: outbound payload has no budget ceiling'
