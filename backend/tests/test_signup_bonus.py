"""Tests for services/referral.py::credit_invitee_signup_reward() -- the
INVITEE-side referral bonus paid IMMEDIATELY at signup (owner decision,
2026-08-30; see services/referral.py's module docstring for the full
reasoning, and tests/test_referral_rewards.py's module docstring for the
companion INVITER-side contract, unaffected by this change).

Split out of tests/test_referral_rewards.py purely to stay under the house
500-line cap -- that file already carried the full settle_on_first_payment
suite and was close to the limit before this feature. Reuses that file's
fake `referral_reward`/`app_setting` stand-in
(`_FakeReferralDB`/`_FakeSession`/`_Ctx`) and fixtures (`db`, `patched`,
`credit`, the autouse `_reset_cache`) via import rather than duplicating
them -- same pattern already used elsewhere in this test suite (e.g.
test_entitlement_gate.py importing from test_entitlements.py-style
modules) for tests that share fixture-heavy infrastructure with a sibling
file.

Covers, per the implementation packet's acceptance gate:
  (a) credit_invitee_signup_reward() credits exactly the configured amount
      once, is a no-op at 0, and never raises (DB error AND credit_wallet
      error).
  (b) SINGLE-PAY: signup credit then settle_on_first_payment() for the same
      invitee credits the wallet exactly once, proven against REAL
      credit_wallet + a shared MemoryBillingRepo (not a mock call count).
  (c) the inviter leg is completely unaffected when the invitee's leg was
      already paid at signup.
  (d) a wiring guard for auth.py (senior-owned -- this packet cannot edit
      it) that is EXPECTED TO FAIL until the senior wires the call in.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import services.referral as referral_mod
from services.money import Money
from tests.test_referral_rewards import (  # noqa: F401 -- fixtures re-used by pytest
    _FakeSession,
    _reset_cache,
    credit,
    db,
    patched,
)

_BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _awaited_call_names(path: pathlib.Path) -> set[str]:
    """Every function name that is actually awaited somewhere in `path`.
    Same helper as tests/test_referral_rewards.py -- duplicated rather than
    imported so this file's wiring-guard intent reads standalone."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Await):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        fn = call.func
        if isinstance(fn, ast.Name):
            names.add(fn.id)
        elif isinstance(fn, ast.Attribute):
            names.add(fn.attr)
    return names


# ── (a) credit_invitee_signup_reward() ───────────────────────────────────

@pytest.mark.asyncio
async def test_signup_bonus_credits_exactly_the_configured_amount_once(patched, credit):
    patched.seed_config(inviter=5000, invitee=10000, cap=10)
    patched.add_pending(inviter_id=1, invitee_id=2)
    session = _FakeSession(patched)

    result = await referral_mod.credit_invitee_signup_reward(session, invitee_id=2)

    assert result == {'invitee_id': 2, 'invitee_amount_toman': 10000}
    credit.assert_awaited_once()
    args, kwargs = credit.await_args
    assert args[1] == 2                       # invitee_id
    assert args[2] == Money(10000)            # amount
    assert kwargs.get('txn_type') == 'referral_bonus'
    assert kwargs.get('idempotency_key') == 'referral:invitee:2'

    # Row is stamped but NOT flipped to 'paid' -- the inviter leg is still
    # open and settle_on_first_payment must still find this row 'pending'.
    assert patched.rows[2]['status'] == 'pending'
    assert patched.rows[2]['invitee_amount_toman'] == 10000


@pytest.mark.asyncio
async def test_signup_bonus_is_a_noop_when_setting_is_zero(patched, credit):
    patched.seed_config(inviter=5000, invitee=0, cap=10)
    patched.add_pending(inviter_id=1, invitee_id=2)
    session = _FakeSession(patched)

    result = await referral_mod.credit_invitee_signup_reward(session, invitee_id=2)

    assert result is None
    credit.assert_not_called()
    assert patched.rows[2]['invitee_amount_toman'] == 0
    assert patched.rows[2]['status'] == 'pending'


@pytest.mark.asyncio
async def test_signup_bonus_never_raises_on_db_error(patched):
    """A failing session (DB down) must not surface as an exception -- this
    runs on the signup hot path, same contract as record_attribution.

    The invitee amount is seeded NON-ZERO so the function gets PAST the
    `if amount <= 0` early-return and actually enters the crediting body,
    where the boom session raises. (A prior version left the setting at 0,
    so config() returned 0, the function early-returned, and the except path
    was never exercised -- the test looked green but proved nothing; the
    `except: raise` mutation could not flip it. qa finding 2026-08-30.)
    config() reads through the patched module session, so it still resolves
    10000 even though the session PASSED to the credit call is the failing
    one."""
    patched.seed_config(inviter=0, invitee=10000, cap=10)
    patched.add_pending(inviter_id=1, invitee_id=2)

    class _BoomSession:
        async def execute(self, *a, **k):
            raise RuntimeError('db down')

        async def commit(self):
            raise RuntimeError('db down')

    result = await referral_mod.credit_invitee_signup_reward(_BoomSession(), invitee_id=2)
    assert result is None


@pytest.mark.asyncio
async def test_signup_bonus_never_raises_when_credit_wallet_itself_fails(monkeypatch, patched):
    """Even if the wallet-credit call itself blows up (not just the DB read
    of config), credit_invitee_signup_reward must still fail open."""
    patched.seed_config(inviter=0, invitee=10000, cap=10)
    patched.add_pending(inviter_id=1, invitee_id=2)
    session = _FakeSession(patched)

    async def _boom(*a, **k):
        raise RuntimeError('wallet write failed')

    monkeypatch.setattr(referral_mod, 'credit_wallet', _boom)
    result = await referral_mod.credit_invitee_signup_reward(session, invitee_id=2)

    assert result is None
    # Nothing was stamped -- the failure happened before the row update.
    assert patched.rows[2]['invitee_amount_toman'] == 0


# ── (b) SINGLE-PAY: signup credit then settle credits the invitee once ───
# This is the highest-risk test in this packet. It deliberately does NOT
# use the `credit` AsyncMock fixture -- it exercises the REAL
# services.billing.credit_wallet against a shared MemoryBillingRepo, so the
# "not double-credited" claim is proven against actual wallet-balance math,
# not a call-count assertion on a mock that could itself hide a bug.

@pytest.mark.asyncio
async def test_single_pay_signup_then_settle_credits_invitee_exactly_once(monkeypatch, patched):
    from services.billing import MemoryBillingRepo

    patched.seed_config(inviter=3000, invitee=10000, cap=10)
    patched.add_pending(inviter_id=1, invitee_id=2)

    shared_repo = MemoryBillingRepo()
    # Both credit_invitee_signup_reward (called with an auth.py-style
    # explicit session) and settle_on_first_payment (which opens its own
    # via async_session()) construct `SqlBillingRepo(session)` -- route
    # both to the SAME in-memory repo regardless of which session object
    # they were built from, so both real credit_wallet calls act on one
    # ledger/wallet state, exactly like production (one Postgres).
    monkeypatch.setattr(referral_mod, 'SqlBillingRepo', lambda session: shared_repo)

    # 1) signup credits the invitee immediately.
    signup_result = await referral_mod.credit_invitee_signup_reward(
        _FakeSession(patched), invitee_id=2,
    )
    assert signup_result == {'invitee_id': 2, 'invitee_amount_toman': 10000}
    assert shared_repo.wallets[2]['balance'] == 10000

    # 2) the invitee's first payment later triggers settle. The invitee leg
    #    must NOT be paid again; the inviter (a separate wallet) still gets
    #    credited normally.
    settle_result = await referral_mod.settle_on_first_payment(2)
    assert settle_result is not None and settle_result['capped'] is False
    assert settle_result['invitee_amount_toman'] == 10000  # preserved from signup
    assert settle_result['inviter_amount_toman'] == 3000

    assert shared_repo.wallets[2]['balance'] == 10000  # invitee: NOT 20000
    assert shared_repo.wallets[1]['balance'] == 3000    # inviter: unaffected, own leg

    # Exactly one ledger row ever landed under the invitee's idempotency
    # key -- the sharpest possible proof of single-pay.
    invitee_ledger_rows = [
        e for e in shared_repo.ledger if e.get('idempotency_key') == 'referral:invitee:2'
    ]
    assert len(invitee_ledger_rows) == 1


# ── (c) inviter leg unaffected ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_settle_still_credits_inviter_when_invitee_already_signup_paid(patched, credit):
    """Even though the invitee's leg was already paid at signup, the
    inviter still gets credited normally when referral_reward_toman > 0."""
    patched.seed_config(inviter=5000, invitee=10000, cap=10)
    patched.add_pending(inviter_id=1, invitee_id=2)
    # Simulate credit_invitee_signup_reward() having already stamped the
    # row (directly, rather than through credit_wallet, since `credit` is
    # mocked here and we only want to observe settle()'s own behaviour).
    patched.rows[2]['invitee_amount_toman'] = 10000

    result = await referral_mod.settle_on_first_payment(2)

    assert result is not None and result['capped'] is False
    assert result['inviter_amount_toman'] == 5000
    assert result['invitee_amount_toman'] == 10000  # preserved, not re-read from config
    credit.assert_awaited_once()  # inviter only -- invitee leg already paid at signup
    args, kwargs = credit.await_args
    assert args[1] == 1  # inviter_id
    assert args[2] == Money(5000)
    assert kwargs.get('idempotency_key') == 'referral:inviter:1:2'
    assert patched.rows[2]['status'] == 'paid'


# ── (d) WIRING GUARD: auth.py must call credit_invitee_signup_reward() ───
#
# auth.py is senior-owned (backend-specialist packets never edit it -- see
# the hoshyar profile's "Shared files" section). This packet implements
# services/referral.py::credit_invitee_signup_reward() but cannot wire its
# one caller itself.
#
# ⚠️ THIS TEST IS EXPECTED TO FAIL (RED) RIGHT NOW. That red is correct and
# by design -- auth.py has not been wired to call the new function yet. The
# senior wires auth.py next (adding a call to
# services.referral.credit_invitee_signup_reward() right after the existing
# services.referral.record_attribution() call, inside the same
# referrer-exists branch, on the same session `s2`); once that lands, this
# test goes green. Per the profile's "Wiring is part of the work" section:
# any packet that builds something the senior must wire up ships a guard
# that fails when the wiring is absent, so the feature can never ship
# silently unreachable.

def test_signup_credits_the_invitee_bonus_after_recording_attribution():
    text = (_BACKEND / 'auth.py').read_text(encoding='utf-8')
    awaited = _awaited_call_names(_BACKEND / 'auth.py')
    assert 'credit_invitee_signup_reward' in awaited, (
        "auth.py does not (yet) await credit_invitee_signup_reward() -- "
        "expected-red-until-senior-wires-auth.py"
    )
    rec_pos = text.find('record_attribution(')
    bonus_pos = text.find('credit_invitee_signup_reward(')
    assert rec_pos != -1 and bonus_pos != -1 and bonus_pos > rec_pos, (
        "credit_invitee_signup_reward( must appear AFTER record_attribution( "
        "in auth.py's source -- expected-red-until-senior-wires-auth.py"
    )
