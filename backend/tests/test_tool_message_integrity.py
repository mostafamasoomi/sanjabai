"""Phase 8, group 2, step B1 -- outbound tool-message safety.

Two independent guards, tested together because they answer the same
report ("the model silently gets a malformed tool turn"):

  1. services/token_budget.py apply_history_window() must never split an
     assistant{tool_calls} / tool{tool_call_id} pair across the trim
     boundary -- a lone `role='tool'` reaching an OpenAI-compatible
     upstream is a guaranteed 400 on the whole request.
  2. middleware/compression.py compress_messages() must never rewrite a
     tool message's string content, nor an assistant message carrying
     tool_calls -- headroom's "smart" mode hands the model malformed JSON
     or silently altered data.

Both guards must be a strict no-op for every conversation that has no
tool messages -- today's traffic -- which several tests below pin
explicitly.

Tests are named after the failure they prevent, not after the function.
"""
from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from middleware.compression import compress_messages
from services.token_budget import MAX_HISTORY_MESSAGES, apply_history_window


# ── Helpers ──────────────────────────────────────────────────────────────

def _assistant_tool_call(call_id: str, content: str | None = None) -> dict:
    return {
        'role': 'assistant',
        'content': content,
        'tool_calls': [
            {'id': call_id, 'type': 'function',
             'function': {'name': 'lookup', 'arguments': '{}'}},
        ],
    }


def _tool_result(call_id: str, content: str = '{"ok": true}') -> dict:
    return {'role': 'tool', 'tool_call_id': call_id, 'content': content}


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


def _old_apply_history_window(messages: list[dict], limit: int) -> list[dict]:
    """The pre-fix algorithm (plain index slice, no tool-group awareness),
    reproduced here only to pin that the new code is byte-identical to it
    on tool-free input -- the required no-op.
    """
    def is_system(m):
        return isinstance(m, dict) and m.get('role') == 'system'

    body = [i for i, m in enumerate(messages) if not is_system(m)]
    if len(body) <= limit:
        return list(messages)
    dropped = set(body[: len(body) - limit])
    kept = [m for i, m in enumerate(messages) if i not in dropped]
    from services.token_budget import HISTORY_TRIM_NOTE
    if not any(
        isinstance(m, dict) and m.get('content') == HISTORY_TRIM_NOTE for m in kept
    ):
        first_body = next((i for i, m in enumerate(kept) if not is_system(m)), len(kept))
        kept.insert(first_body, {'role': 'system', 'content': HISTORY_TRIM_NOTE})
    return kept


def _tool_msgs_without_matching_assistant(messages: list[dict]) -> list[dict]:
    """Every role='tool' message in `messages` whose tool_call_id has no
    assistant{tool_calls} counterpart also present in `messages`.
    """
    owned_ids = set()
    for m in messages:
        if isinstance(m, dict) and m.get('role') == 'assistant':
            for tc in (m.get('tool_calls') or []):
                if isinstance(tc, dict) and tc.get('id'):
                    owned_ids.add(tc['id'])
    return [
        m for m in messages
        if isinstance(m, dict) and m.get('role') == 'tool'
        and m.get('tool_call_id') not in owned_ids
    ]


# ── Trap 1: apply_history_window must not split a tool_calls pair ────────

class TestHistoryWindowKeepsToolGroupsAtomic:
    def test_21_message_boundary_scenario_does_not_orphan_the_tool_reply(self):
        # Exact scenario from the handoff: 21 non-system messages, msg 1 and
        # 2 (0-indexed 0/1) are an assistant{tool_calls} / tool pair,
        # MAX_HISTORY_MESSAGES=20. The old index-slice algorithm dropped
        # only message 0, leaving message 1 (role='tool') orphaned.
        assert MAX_HISTORY_MESSAGES == 20, 'scenario is pinned to the default of 20'
        msgs = [
            _assistant_tool_call('call_x'),
            _tool_result('call_x'),
        ] + [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'm{i}'}
             for i in range(19)]
        assert len(msgs) == 21

        out = apply_history_window(msgs)

        assert _tool_msgs_without_matching_assistant(out) == []
        non_system = [m for m in out if m.get('role') != 'system']
        assert len(non_system) <= MAX_HISTORY_MESSAGES

    def test_group_ending_exactly_at_the_cut_needs_no_push_and_is_fully_dropped(self):
        # Boundary direction 1: the naive cut already lands exactly at the
        # end of the group (drop_count == group's last position + 1), so no
        # push-back is needed -- the group is cleanly, entirely dropped as
        # part of the ordinary oldest-first trim, and nothing extra is lost.
        # 2 pad + 2-message group + 18 trailing = 22 non-system; limit=20
        # => drop_count=2, which is exactly hi+1 for a group at [0,1].
        msgs = (
            [_assistant_tool_call('call_y'), _tool_result('call_y')]
            + [{'role': 'user', 'content': f'trail-{i}'} for i in range(20)]
        )
        assert len(msgs) == 22
        out = apply_history_window(msgs, max_messages=20)
        assert _tool_msgs_without_matching_assistant(out) == []
        assert all(m.get('tool_call_id') != 'call_y' for m in out if m.get('role') == 'tool')
        non_system = [m for m in out if m.get('role') != 'system']
        assert len(non_system) == 20, 'clean boundary must not over-drop beyond the group'

    def test_group_starting_exactly_at_the_cut_needs_no_push_and_is_fully_kept(self):
        # Boundary direction 2: the naive cut lands exactly at the start of
        # the group (drop_count == group's first position), so the group is
        # already entirely on the kept side and the push-back is a no-op.
        # 5 pad + 2-message group + 18 trailing = 25 non-system; limit=20
        # => drop_count=5, which is exactly the group's first position.
        msgs = (
            [{'role': 'user', 'content': f'pad-{i}'} for i in range(5)]
            + [_assistant_tool_call('call_z'), _tool_result('call_z')]
            + [{'role': 'user', 'content': f'trail-{i}'} for i in range(18)]
        )
        assert len(msgs) == 25
        out = apply_history_window(msgs, max_messages=20)
        assert _tool_msgs_without_matching_assistant(out) == []
        assert any(m.get('role') == 'tool' and m.get('tool_call_id') == 'call_z'
                   for m in out)
        assert any(
            m.get('role') == 'assistant'
            and any(tc.get('id') == 'call_z' for tc in (m.get('tool_calls') or []))
            for m in out
        )
        non_system = [m for m in out if m.get('role') != 'system']
        assert len(non_system) == 20, 'clean boundary must not over-drop when no push is needed'

    def test_two_tool_calls_answered_by_two_tool_messages_move_as_one_unit(self):
        # Precisely placed so the *naive* index-slice cut (drop_count =
        # len(body) - limit = 25 - 20 = 5) lands strictly inside the group
        # (positions 3-5): 3 pad messages, then the 3-message group at
        # positions 3/4/5, then 19 trailing messages. The old algorithm
        # would drop only the assistant (position 3/4) and orphan a tool
        # reply; the fix must push the whole group to the dropped side.
        assistant = {
            'role': 'assistant',
            'content': None,
            'tool_calls': [
                {'id': 'call_a', 'type': 'function', 'function': {'name': 'f1', 'arguments': '{}'}},
                {'id': 'call_b', 'type': 'function', 'function': {'name': 'f2', 'arguments': '{}'}},
            ],
        }
        msgs = (
            [{'role': 'user', 'content': f'pad-before-{i}'} for i in range(3)]
            + [assistant, _tool_result('call_a'), _tool_result('call_b')]
            + [{'role': 'user', 'content': f'pad-after-{i}'} for i in range(19)]
        )
        assert len([m for m in msgs if m.get('role') != 'system']) == 25

        out = apply_history_window(msgs, max_messages=20)
        assert _tool_msgs_without_matching_assistant(out) == []
        group_present = [
            m for m in out
            if (m.get('role') == 'assistant' and m.get('tool_calls'))
            or (m.get('role') == 'tool' and m.get('tool_call_id') in ('call_a', 'call_b'))
        ]
        # All three or none -- never one or two. In this precise placement
        # the naive cut would have kept the assistant but dropped the tool
        # replies (or vice-versa); the fix drops the whole group together.
        assert len(group_present) in (0, 3)
        assert len(group_present) == 0, 'group sits inside the naive drop range in this scenario'

    def test_orphan_tool_message_with_no_matching_assistant_is_dropped(self):
        # Malformed input, not something windowing created: no assistant
        # anywhere in the conversation owns this tool_call_id.
        msgs = [
            {'role': 'user', 'content': 'hi'},
            _tool_result('call_ghost'),
            {'role': 'assistant', 'content': 'hello'},
        ]
        out = apply_history_window(msgs, max_messages=20)
        assert all(m.get('role') != 'tool' for m in out)

    def test_zero_tool_messages_is_returned_exactly_as_the_old_code_did(self):
        # Pin the no-op: the new union-find machinery must not perturb
        # ordinary traffic at all, byte-for-byte, including the trimmed case.
        for msgs in (_thread(3), _thread(60), []):
            old = _old_apply_history_window(copy.deepcopy(msgs), MAX_HISTORY_MESSAGES)
            new = apply_history_window(copy.deepcopy(msgs))
            assert new == old


# ── Mutation-proof helper: reproduces the plain index-slice bug ──────────

def _plain_index_slice_window(messages: list[dict], limit: int) -> list[dict]:
    """Mutation (a) from the packet: the boundary push-back reverted to the
    original plain index slice, with no tool-group awareness at all.
    """
    def is_system(m):
        return isinstance(m, dict) and m.get('role') == 'system'

    body = [i for i, m in enumerate(messages) if not is_system(m)]
    if len(body) <= limit:
        return list(messages)
    dropped = set(body[: len(body) - limit])
    return [m for i, m in enumerate(messages) if i not in dropped]


class TestMutationBoundaryPushBackReverted:
    def test_plain_slice_reproduces_the_orphan_tool_message_bug(self):
        # This documents the RED behaviour the guard prevents: without the
        # push-back, the 21-message scenario orphans a tool message.
        msgs = [
            _assistant_tool_call('call_x'),
            _tool_result('call_x'),
        ] + [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'm{i}'}
             for i in range(19)]
        broken = _plain_index_slice_window(msgs, 20)
        assert _tool_msgs_without_matching_assistant(broken) != [], (
            'expected the naive slice to orphan a tool message -- if this '
            'assertion fails the scenario itself stopped exercising the bug'
        )


# ── Trap 2: compress_messages must not rewrite tool output ───────────────
#
# IMPORTANT, discovered while writing these tests (not part of the packet's
# two named traps, not fixed here -- see the session report): the installed
# `headroom` package's compress() signature is
# `compress(messages: list[dict], model=..., **kwargs)`; it has no `mode`
# parameter and does not accept a raw string. middleware/compression.py
# calls `hr_compress(content, mode='smart')` with `content` a plain string,
# which headroom's own pipeline rejects internally ('str' object has no
# attribute 'get'), caught by compress_messages()'s `except Exception`, so
# TODAY every call silently no-ops and leaves content unchanged -- for
# every role, not just 'tool'. That means asserting against the *real*
# hr_compress cannot distinguish "skipped by our guard" from "hr_compress
# is broken for everyone right now" -- a mutation that removes the guard
# would stay green against real headroom (proven below, restored
# afterwards). These tests patch `headroom.compress` with a deterministic
# stand-in so they test compress_messages()'s *routing* logic (which
# messages reach hr_compress at all), independent of that separate bug.

def _fake_hr_compress(content, mode='smart', **kwargs):
    """Deterministic stand-in for headroom.compress: halves a string. Lets
    these tests prove whether compress_messages() routed a message into
    the compress call, without depending on headroom's real (currently
    broken for this call shape) internal behaviour.
    """
    return content[: len(content) // 2]


class TestCompressMessagesSkipsToolAndToolCalls:
    def test_tool_message_content_is_byte_identical_even_when_long(self):
        big_json = '{"result": "' + ('x' * 4000) + '"}'
        msgs = [
            {'role': 'user', 'content': 'pad ' * 100},
            {'role': 'assistant', 'content': 'pad ' * 100},
            {'role': 'tool', 'tool_call_id': 'call_1', 'content': big_json},
        ]
        with patch('headroom.compress', new=_fake_hr_compress):
            out = compress_messages(msgs, preserve_last=0)
        tool_out = next(m for m in out if m.get('role') == 'tool')
        assert tool_out['content'] == big_json
        assert len(tool_out['content']) == 4000 + len('{"result": "' + '"}')

    def test_assistant_message_with_tool_calls_is_left_untouched(self):
        long_content = 'ز' * 500  # long enough to normally trigger compression
        assistant = _assistant_tool_call('call_2', content=long_content)
        msgs = [
            {'role': 'user', 'content': 'pad ' * 100},
            assistant,
        ]
        with patch('headroom.compress', new=_fake_hr_compress):
            out = compress_messages(msgs, preserve_last=0)
        out_assistant = next(m for m in out if m.get('role') == 'assistant')
        assert out_assistant['content'] == long_content
        assert out_assistant['tool_calls'] == assistant['tool_calls']

    def test_a_long_ordinary_user_message_is_still_compressed(self):
        # Do not condemn the case the guard was added beside: a genuinely
        # long, ordinary string message with no tool involvement must still
        # reach hr_compress and come back shorter.
        long_content = 'سلام این یک پیام بلند تستی است. ' * 30
        assert len(long_content) >= 300
        msgs = [
            {'role': 'user', 'content': long_content},
            {'role': 'assistant', 'content': 'ok'},
        ]
        with patch('headroom.compress', new=_fake_hr_compress):
            out = compress_messages(msgs, preserve_last=1)
        user_out = next(m for m in out if m.get('role') == 'user')
        assert len(user_out['content']) < len(long_content)
        assert user_out['content'] == long_content[: len(long_content) // 2]

    def test_conversation_with_no_tool_messages_is_unaffected_by_the_guard(self):
        # No-op requirement: adding the tool/tool_calls skip must not change
        # behaviour for a conversation that never touches either branch.
        # (These messages are all under the 300-char threshold, so this is
        # a true no-op path -- hr_compress is never reached either way --
        # exercised against the *real* headroom import, not the fake.)
        msgs = [
            {'role': 'system', 'content': 'instructions'},
            {'role': 'user', 'content': 'short'},
            {'role': 'assistant', 'content': 'short reply'},
        ]
        out = compress_messages(copy.deepcopy(msgs), preserve_last=2)
        assert out == msgs


# ── Senior additions after review (2026-08-28) ───────────────────────────
#
# Independent review probed the guards' EDGES rather than their happy paths
# and found two things the eleven tests above did not cover. Neither is
# reachable in production today; both are pinned here so that stays true by
# test rather than by luck.

class TestARoleTheGuardDidNotKnowAbout:
    def test_a_legacy_function_role_payload_is_also_left_alone(self):
        """`function` is the pre-2023.7 OpenAI spelling of `tool` and carries
        the same structural JSON. The guard originally listed only
        ('system', 'tool'), so a `function` message with a 4,000-character
        JSON body was compressed -- verified by review against the mocked
        compressor. Nothing in this repository emits the role today, which is
        exactly why it would have gone unnoticed until the day something did.
        """
        big_json = '{"result": "' + ('y' * 4000) + '"}'
        msgs = [
            {'role': 'user', 'content': 'pad ' * 100},
            {'role': 'function', 'name': 'lookup', 'content': big_json},
        ]
        with patch('headroom.compress', new=_fake_hr_compress):
            out = compress_messages(msgs, preserve_last=0)
        fn_out = next(m for m in out if m.get('role') == 'function')
        assert fn_out['content'] == big_json, 'a legacy function payload was rewritten'


class TestAToolGroupTooBigForTheWindow:
    """A single assistant turn answered by more tool messages than the whole
    window can hold has no correct answer: the group is indivisible, so it
    either goes entirely (blowing the token budget the window exists to
    protect) or stays entirely (taking the conversation with it).

    The implementation drops it, and review measured the consequence: the
    window can come back EMPTY. That is worse output but not a broken
    request -- the old index-slice code, in this same input, emitted an
    orphaned `role='tool'` message, which is a guaranteed 400 on the whole
    request from any OpenAI-compatible upstream.

    Our own loop caps at three rounds over three tools, so it cannot build a
    group this large; a client posting its own conversation can. These tests
    pin the chosen trade-off so a future reader cannot mistake it for an
    accident, and pin the two properties that must hold no matter what.
    """

    @staticmethod
    def _oversized_tail(pad_turns: int, group_size: int) -> list[dict]:
        msgs = _thread(pad_turns)
        msgs.append(_assistant_tool_call('call_big'))
        msgs.extend(_tool_result('call_big') for _ in range(group_size))
        return msgs

    def test_an_oversized_group_never_leaves_an_orphan_behind(self):
        """The one property that must never break: whatever else gets
        dropped, no `role='tool'` may survive without its assistant."""
        msgs = self._oversized_tail(pad_turns=15, group_size=MAX_HISTORY_MESSAGES + 5)
        out = apply_history_window(msgs, max_messages=MAX_HISTORY_MESSAGES)
        assistants = [m for m in out if m.get('tool_calls')]
        tools = [m for m in out if m.get('role') == 'tool']
        assert not tools or assistants, 'a tool message outlived its assistant turn'

    def test_an_oversized_group_never_blows_the_window_it_could_not_fit_in(self):
        """The other direction of the same trade-off: keeping the group whole
        would defeat the entire purpose of the function."""
        msgs = self._oversized_tail(pad_turns=15, group_size=MAX_HISTORY_MESSAGES + 5)
        out = apply_history_window(msgs, max_messages=MAX_HISTORY_MESSAGES)
        body = [m for m in out if m.get('role') != 'system']
        assert len(body) <= MAX_HISTORY_MESSAGES

    def test_a_user_message_after_the_oversized_group_still_survives(self):
        """The realistic shape. A conversation does not end on a tool result;
        the user asks something next. That newest message is the whole point
        of the request and must not be dropped with the group in front of it.
        """
        msgs = self._oversized_tail(pad_turns=15, group_size=MAX_HISTORY_MESSAGES + 5)
        msgs.append({'role': 'user', 'content': 'newest-question'})
        out = apply_history_window(msgs, max_messages=MAX_HISTORY_MESSAGES)
        contents = [m.get('content') for m in out]
        assert 'newest-question' in contents, (
            'the newest user message was dropped along with the oversized group; '
            f'window returned {contents!r}'
        )
