"""Tests for services/reservation_sweeper.py -- the repair for the live
"one wallet_reservations row stuck in status='reserved' since 2026-08-23"
bug (id=160, user_id=1, amount=1000, model tencent-hy3-free). See that
module's docstring for the root-cause writeup and why the sweep MUST go
through :meth:`services.billing.BillingService.release` rather than
``SqlBillingRepo.mark_reservation_released`` directly (the latter only
flips the reservation row and never decrements ``wallet.reserved``, which
would leave the money held while the row no longer looks stuck).

Uses the in-memory :class:`MemoryBillingRepo` (same pattern as
tests/test_billing.py) so these run with no database. The sweeper's
:func:`services.reservation_sweeper._find_stale_reservation_ids` is
repo-agnostic: against :class:`MemoryBillingRepo` it reads ``repo.reservations``
directly (a plain dict of plain dicts, so a test can seed a ``created_at``
key on a reservation the same way tests/test_billing.py pokes at
``repo.wallets``/``repo.reservations`` directly), and against
:class:`SqlBillingRepo` in production it queries the table directly for
``created_at`` (not part of the repo contract).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from services.billing import MemoryBillingRepo
from services.reservation_sweeper import (
    STALE_RESERVATION_AGE_SECONDS,
    SWEEP_REASON,
    sweep_stale_reservations,
)


def _run(coro):
    return asyncio.run(coro)


NOW = datetime(2026, 8, 28, 12, 0, 0)


def _seed_reservation(repo, *, reservation_id, user_id, amount, age_seconds, status="reserved"):
    """Seed a reservation + its matching wallet hold, mirroring what
    BillingService.reserve() would have produced (repo.wallets['reserved']
    already includes this hold, same as a real reserve() call leaves it)."""
    wallet = repo.wallets.setdefault(user_id, {"balance": 0, "reserved": 0})
    wallet["reserved"] += amount
    repo.reservations[reservation_id] = {
        "reservation_id": reservation_id,
        "user_id": user_id,
        "hold_amount": amount,
        "status": status,
        "idempotency_key": f"idem-{reservation_id}",
        "model": "tencent-hy3-free",
        "price_version": "v1",
        "charged_amount": None,
        "created_at": NOW - timedelta(seconds=age_seconds),
    }


# ── 1: the whole point of the packet ────────────────────────────────────────
def test_stale_reservation_released_and_wallet_reserved_drops():
    async def run():
        repo = MemoryBillingRepo()
        _seed_reservation(
            repo, reservation_id="r-stale", user_id=1, amount=1000,
            age_seconds=STALE_RESERVATION_AGE_SECONDS + 60,
        )
        result = await sweep_stale_reservations(repo, now=NOW)

        assert result.examined == 1
        assert result.swept == 1
        assert result.failed == 0
        assert repo.reservations["r-stale"]["status"] == "released"
        assert repo.reservations["r-stale"]["released_reason"] == SWEEP_REASON
        # The assertion that matters: wallet.reserved actually dropped by
        # the held amount, not just the row's status flipping.
        assert repo.wallets[1]["reserved"] == 0

    _run(run())


# ── 2: young reservations are untouched ─────────────────────────────────────
def test_young_reservation_left_alone():
    async def run():
        repo = MemoryBillingRepo()
        _seed_reservation(
            repo, reservation_id="r-young", user_id=1, amount=500,
            age_seconds=STALE_RESERVATION_AGE_SECONDS - 60,
        )
        result = await sweep_stale_reservations(repo, now=NOW)

        assert result.examined == 0
        assert result.swept == 0
        assert repo.reservations["r-young"]["status"] == "reserved"
        assert repo.wallets[1]["reserved"] == 500

    _run(run())


# ── 3: idempotent -- a second run is a no-op ────────────────────────────────
def test_sweeping_twice_changes_nothing_the_second_time():
    async def run():
        repo = MemoryBillingRepo()
        _seed_reservation(
            repo, reservation_id="r-stale", user_id=1, amount=1000,
            age_seconds=STALE_RESERVATION_AGE_SECONDS + 60,
        )
        first = await sweep_stale_reservations(repo, now=NOW)
        assert first.swept == 1
        assert repo.wallets[1]["reserved"] == 0

        second = await sweep_stale_reservations(repo, now=NOW)
        assert second.examined == 0
        assert second.swept == 0
        assert second.failed == 0
        # Still released, still zero -- nothing moved twice.
        assert repo.reservations["r-stale"]["status"] == "released"
        assert repo.wallets[1]["reserved"] == 0

    _run(run())


# ── 4: one bad reservation must not abort the sweep of the others ──────────
class _FlakyRepo(MemoryBillingRepo):
    """MemoryBillingRepo subclass (test-only, not a change to
    services/billing_memory.py) that raises for one specific reservation id,
    simulating a real-world failure (e.g. a transient DB error) partway
    through the sweep."""

    def __init__(self, bad_id):
        super().__init__()
        self._bad_id = bad_id

    async def get_reservation(self, reservation_id):
        if reservation_id == self._bad_id:
            raise RuntimeError("boom: simulated failure releasing this one")
        return await super().get_reservation(reservation_id)


def test_one_bad_reservation_does_not_stop_the_others():
    async def run():
        repo = _FlakyRepo(bad_id="r-bad")
        _seed_reservation(
            repo, reservation_id="r-bad", user_id=1, amount=1000,
            age_seconds=STALE_RESERVATION_AGE_SECONDS + 60,
        )
        _seed_reservation(
            repo, reservation_id="r-ok", user_id=2, amount=250,
            age_seconds=STALE_RESERVATION_AGE_SECONDS + 60,
        )

        result = await sweep_stale_reservations(repo, now=NOW)

        assert result.examined == 2
        assert result.swept == 1
        assert result.failed == 1
        # The bad one is untouched (still reserved, wallet unchanged) --
        # release() raised before mutating anything.
        assert repo.reservations["r-bad"]["status"] == "reserved"
        assert repo.wallets[1]["reserved"] == 1000
        # The good one still got swept.
        assert repo.reservations["r-ok"]["status"] == "released"
        assert repo.wallets[2]["reserved"] == 0

    _run(run())


# ── crash-safety: the sweep itself must never raise out of the function ────
def test_find_failure_does_not_raise_out_of_sweep():
    """If listing stale reservations itself blows up (e.g. a real DB error
    on the SqlBillingRepo path), the sweep must return a safe empty result,
    not raise -- a caller in app.py's lifespan or a background loop tick
    must never see an exception from this function."""

    class _BrokenFindRepo(MemoryBillingRepo):
        @property
        def reservations(self):
            raise RuntimeError("boom: simulated storage failure")

        @reservations.setter
        def reservations(self, value):
            self._reservations = value

    async def run():
        repo = _BrokenFindRepo()
        result = await sweep_stale_reservations(repo, now=NOW)
        assert result.examined == 0
        assert result.swept == 0
        assert result.failed == 0

    _run(run())


# ── cancellation must propagate, never be swallowed ─────────────────────────
def test_cancelled_error_propagates_out_of_sweep():
    class _CancellingRepo(MemoryBillingRepo):
        @property
        def reservations(self):
            raise asyncio.CancelledError()

        @reservations.setter
        def reservations(self, value):
            self._reservations = value

    async def run():
        repo = _CancellingRepo()
        with pytest.raises(asyncio.CancelledError):
            await sweep_stale_reservations(repo, now=NOW)

    _run(run())
