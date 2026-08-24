"""Every path that runs the free-tier gate must also run the premium gate.

Session 17 found four authenticated paths reaching an upstream model while
skipping the moderation chokepoint, and the reason it could happen is that
each path wires its own gates by hand. The premium sub-allowance
(services/premium_quota.py, migration 0046) has exactly the same shape and
therefore exactly the same failure mode: it CANNOT live in the shared,
pre-model chat_web._chat_preflight, because it needs the resolved model in
order to price it. So it sits at each route's own post-model point --
which is precisely the kind of hand-wiring a new route forgets.

This test is the guard. It does not check that the gate WORKS
(tests/test_premium_quota.py does that); it checks that nobody added or
kept a billed path that runs one gate and not the other. It is a source
scan on purpose: a mock-driven test cannot prove a call site exists, and
the whole class of bug here is a missing call site.

The rule is deliberately expressed as "free-tier implies premium" rather
than as a hardcoded module list, so a NEW route added next month is caught
the day it is written instead of the day someone audits it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]

# The three gate modules DEFINE `check_and_consume`; matching their own
# definition would make every one of them look like an ungated call site.
# services/free_tier_config.py and admin_free_tier.py only read settings.
_GATE_MODULES = {
    'services/free_tier.py',
    'services/user_quota.py',
    'services/premium_quota.py',
}

# `premium_check_and_consume` CONTAINS `check_and_consume` as a substring,
# so the free-tier pattern must refuse to match it -- otherwise a file that
# only calls the premium gate would count as calling the free-tier gate and
# the implication would hold vacuously.
#
# Two call spellings are in use and both must be recognised: the plain
# `check_and_consume(uid, ...)` (imported directly, or reached as
# `chat.check_and_consume`) and the aliased `_free_tier_check(user_id, ...)`
# that services/rag.py imports. Missing the alias is not a harmless gap --
# it would silently drop rag.py out of the scan and let this whole file
# pass while one real path stayed ungated, which is exactly what happened
# on the first draft of this test.
_FREE_TIER_CALL = re.compile(
    r'(?<!premium_)(?<!def )check_and_consume\(\s*(?:uid|user_id)'
    r'|_free_tier_check\(\s*(?:uid|user_id)'
)
_PREMIUM_CALL = re.compile(
    r'(?:premium_check_and_consume|_premium_quota_check)\s*\(\s*(?:uid|user_id)'
)


def _billed_modules() -> list[str]:
    """Every backend module that gates a request through the free tier."""
    found = []
    for path in sorted(_BACKEND.rglob('*.py')):
        rel = path.relative_to(_BACKEND).as_posix()
        if rel.startswith(('tests/', 'migrations/', 'scripts/')):
            continue
        if rel in _GATE_MODULES:
            continue
        if _FREE_TIER_CALL.search(path.read_text()):
            found.append(rel)
    return found


def test_the_scan_actually_finds_the_known_paths():
    """Guards the guard: if the regex silently stops matching, every other
    assertion in this file passes vacuously over an empty list."""
    found = set(_billed_modules())
    expected = {
        'chat.py',
        'chat_smart.py',
        'chat_compare.py',
        'chat_web.py',
        'task_execution.py',
        'services/rag.py',
        'document_generator.py',
    }
    missing = expected - found
    assert not missing, f'free-tier call sites no longer detected in: {sorted(missing)}'


@pytest.mark.parametrize('module', _billed_modules())
def test_every_free_tier_call_site_also_runs_the_premium_gate(module):
    src = (_BACKEND / module).read_text()
    assert _PREMIUM_CALL.search(src), (
        f'{module} gates on the free tier but never calls the premium '
        f'sub-allowance gate (services/premium_quota.py). A package holder '
        f'can spend an expensive model through this path without it '
        f'counting against their premium allowance.'
    )


@pytest.mark.parametrize('module', _billed_modules())
def test_the_premium_gate_runs_before_the_reservation(module):
    """A rejection must leave no wallet reservation to unwind, which is the
    same ordering rule the free-tier gate follows and the reason both sit
    above reserve() rather than below it."""
    src = (_BACKEND / module).read_text()
    lines = src.splitlines()

    premium_at = next(
        (i for i, ln in enumerate(lines) if _PREMIUM_CALL.search(ln)), None
    )
    assert premium_at is not None, f'{module}: no premium gate call'

    # Only a real reserve() invocation counts -- prose in a docstring and the
    # release/refund helpers mention BillingService too, and those legitimately
    # appear elsewhere in the file.
    reserve_at = next(
        (i for i, ln in enumerate(lines)
         if re.search(r'\.reserve\(', ln) and i > premium_at),
        None,
    )
    if reserve_at is None:
        pytest.skip(f'{module} opens no reservation of its own')
    assert premium_at < reserve_at, (
        f'{module}: premium gate at line {premium_at + 1} runs AFTER '
        f'reserve() at line {reserve_at + 1}'
    )
