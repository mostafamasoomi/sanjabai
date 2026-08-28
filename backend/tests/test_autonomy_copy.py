"""The autonomy setting's user-facing copy must match what the gate does.

Until phase 8, `autonomy_level` was stored, validated in auth_profile.py, and
read by nothing outside the profile page -- so its three descriptions in
`frontend/app/profile/types.ts` described a product that did not exist. "Only
irreversible actions require confirmation" asked about nothing, because nothing
ever asked. `services/chat_tools.announced_tools()` gave it a real consumer, and
the copy was rewritten to say what that consumer does.

This test is what keeps the two from drifting apart again. Copy and behaviour
live in different languages, in different directories, with no compiler and no
type between them; the failure mode is silent, and its shape is a user who
picked "low" because the page told them nothing would be created.

Pinned in both directions, because the direction that rots is the second:
  * every level the page offers is one the gate really accepts
  * every level the gate accepts is one the page explains
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from services.chat_tools import TOOL_NAMES, announced_tools

_FRONTEND = Path(__file__).resolve().parents[2] / 'frontend'
_LEVELS_TS = _FRONTEND / 'app' / 'profile' / 'types.ts'
_VALIDATOR_PY = Path(__file__).resolve().parents[1] / 'auth_profile.py'

_ACCEPTED = ('low', 'medium', 'high')


def _levels_block() -> str:
    assert _LEVELS_TS.exists(), f'the autonomy levels are gone: {_LEVELS_TS}'
    src = _LEVELS_TS.read_text(encoding='utf-8')
    start = src.index('export const AUTONOMY_LEVELS = [')
    end = src.index('export const TIMEZONES = [')
    return src[start:end]


def _offered_levels() -> list[str]:
    return re.findall(r"value:\s*'([a-z]+)'", _levels_block())


def test_the_page_offers_exactly_the_levels_the_validator_accepts():
    """auth_profile.py rejects anything outside low|medium|high, so a level
    offered here that it does not accept is a setting the user can pick and
    never save."""
    validator_src = _VALIDATOR_PY.read_text(encoding='utf-8')
    for level in _ACCEPTED:
        assert f"'{level}'" in validator_src, f'{level} is no longer in the validator'
    assert _offered_levels() == list(_ACCEPTED)


@pytest.mark.parametrize('level', _ACCEPTED)
def test_every_accepted_level_is_explained_on_the_page(level):
    """A level the gate honours but the page never describes is a behaviour
    the user cannot discover and did not choose."""
    assert f"value: '{level}'" in _levels_block()


def test_low_really_is_suggests_only_and_the_copy_says_so():
    """The whole promise of `low` is that the creating tools are not offered
    to the model at all. If announced_tools ever started offering them, the
    page would still be telling the user nothing can be created."""
    assert announced_tools('low') == frozenset({'list_models'})
    block = _levels_block()
    low = block[block.index("value: 'low'"):block.index("value: 'medium'")]
    assert 'هیچ چیزی ساخته نمی‌شود' in low, 'the low copy no longer promises nothing is created'
    assert 'Nothing is created' in low


def test_medium_and_high_both_offer_every_tool_and_differ_only_in_confirmation():
    """The difference between them is dispatch-time confirmation, not which
    tools the model is told about -- so the copy must not claim `medium`
    withholds a tool."""
    assert announced_tools('medium') == TOOL_NAMES
    assert announced_tools('high') == TOOL_NAMES


def test_high_still_promises_the_two_invariants_that_never_relax():
    """A user choosing the most permissive level is entitled to know what it
    does NOT hand over. Both of these are enforced in services/chat_tools.py
    at every level; the copy states them where the user is deciding."""
    block = _levels_block()
    high = block[block.index("value: 'high'"):]
    assert 'غیرفعال است' in high, 'the high copy stopped promising a created task is inactive'
    assert 'خصوصی' in high, 'the high copy stopped promising a created assistant is private'
    assert 'stays inactive' in high
    assert 'stays private' in high


def test_an_unknown_level_is_treated_as_medium_not_as_high():
    """Failing open here would mean a corrupted or future preference value
    silently granting the most permissive behaviour. It must land on the
    default the page calls the default, not above it."""
    assert announced_tools('nonsense') == announced_tools('medium')
