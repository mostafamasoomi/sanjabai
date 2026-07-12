"""Tests for financial correctness: billing reservations/settlements, payment
callback hardening, and usage metering.

All tests use the in-memory :class:`MemoryBillingRepo` (and a fake verify
function) so they run with no database.  The production SQL path
(:class:`SqlBillingRepo`) is exercised separately by the real-DB migration
tests when a disposable PostgreSQL is available.

Money is always represented by :class:`services.money.Money` (integer Tomans);
there is no floating point anywhere.
"""
from __future__ import annotations

import asyncio

import pytest

from services.billing import (
    BillingService,
    MemoryBillingRepo,
    InsufficientBalanceError,
    ReservationNotFoundError,
    ReservationError,
    credit_wallet,
)
from services.money import Money
from services.metering import compute_charge, record_usage, UPSTREAM_SUCCESS
from payment import handle_payment_callback


def _run(coro):
    return asyncio.run(coro)


async def _verify_ok(amount, authority):
    return {"status": "verified", "ref_id": "REF123"}


async def _verify_fail(amount, authority):
    return {"status": "failed", "error": "gateway said no"}


# ── Authorize / reserve / settle ─────────────────────────────────────────────
def test_reserve_insufficient_balance_rejected():
    async def run():
        repo = MemoryBillingRepo()
        svc = BillingService(repo)
        with pytest.raises(InsufficientBalanceError):
            await svc.reserve(user_id=1, amount=Money(100), idempotency_key="k1")
        # No money moved, no reservation created.
        assert repo.reservations == {}
        # ensure_wallet created a zero wallet row but nothing reserved.
        assert repo.wallets.get(1, {"reserved": 0})["reserved"] == 0

    _run(run())


def test_reserve_and_settle_charges_final_amount():
    async def run():
        repo = MemoryBillingRepo()
        svc = BillingService(repo)
        await credit_wallet(repo, 1, Money(500), "topup")
        resv = await svc.reserve(
            user_id=1, amount=Money(100), idempotency_key="k1",
            model="gpt", price_version="v1",
        )
        assert resv["status"] == "reserved"
        assert repo.wallets[1]["balance"] == 500
        assert repo.wallets[1]["reserved"] == 100
        # Available balance is 400.
        assert await svc.authorize(1, Money(400)) is True
        assert await svc.authorize(1, Money(401)) is False

        # Final charge is less than the hold (fewer tokens than estimated).
        settled = await svc.settle(
            reservation_id=resv["reservation_id"], final_amount=Money(60),
            request_id="req-1", price_version="v1",
        )
        assert settled["status"] == "settled"
        assert settled["charged_amount"] == 60
        assert repo.wallets[1]["balance"] == 440
        assert repo.wallets[1]["reserved"] == 0
        # Exactly one debit of 60 was posted to the ledger.
        debits = [e for e in repo.ledger if e["amount"] < 0]
        assert debits and debits[-1]["amount"] == -60
        assert debits[-1]["balance_after"] == 440

    _run(run())


def test_reserve_is_idempotent_on_idempotency_key():
    async def run():
        repo = MemoryBillingRepo()
        svc = BillingService(repo)
        await credit_wallet(repo, 1, Money(500), "topup")
        r1 = await svc.reserve(user_id=1, amount=Money(100), idempotency_key="same")
        r2 = await svc.reserve(user_id=1, amount=Money(100), idempotency_key="same")
        assert r1["reservation_id"] == r2["reservation_id"]
        # Hold taken only once.
        assert repo.wallets[1]["reserved"] == 100

    _run(run())


def test_settle_rejects_overcharge():
    async def run():
        repo = MemoryBillingRepo()
        svc = BillingService(repo)
        await credit_wallet(repo, 1, Money(500), "topup")
        resv = await svc.reserve(user_id=1, amount=Money(100), idempotency_key="k1")
        with pytest.raises(ReservationError):
            await svc.settle(reservation_id=resv["reservation_id"], final_amount=Money(150))

    _run(run())


def test_settle_is_idempotent():
    async def run():
        repo = MemoryBillingRepo()
        svc = BillingService(repo)
        await credit_wallet(repo, 1, Money(500), "topup")
        resv = await svc.reserve(user_id=1, amount=Money(100), idempotency_key="k1")
        await svc.settle(reservation_id=resv["reservation_id"], final_amount=Money(60))
        await svc.settle(reservation_id=resv["reservation_id"], final_amount=Money(60))
        # Charged only once.
        assert repo.wallets[1]["balance"] == 440

    _run(run())


def test_settle_of_missing_reservation_raises():
    async def run():
        repo = MemoryBillingRepo()
        svc = BillingService(repo)
        with pytest.raises(ReservationNotFoundError):
            await svc.settle(reservation_id="does-not-exist", final_amount=Money(1))

    _run(run())


# ── Release (upstream failure / cancellation) ────────────────────────────────
def test_upstream_failure_refunds_the_hold():
    async def run():
        repo = MemoryBillingRepo()
        svc = BillingService(repo)
        await credit_wallet(repo, 1, Money(500), "topup")
        resv = await svc.reserve(user_id=1, amount=Money(100), idempotency_key="k1")
        # Upstream call fails before any charge -> release the hold.
        released = await svc.release(
            reservation_id=resv["reservation_id"], reason="upstream failure"
        )
        assert released["status"] == "released"
        # Funds are returned to available balance; nothing was charged.
        assert repo.wallets[1]["reserved"] == 0
        assert repo.wallets[1]["balance"] == 500
        # No debit posted.
        assert all(e["amount"] >= 0 for e in repo.ledger)

    _run(run())


def test_cancellation_release_is_idempotent():
    async def run():
        repo = MemoryBillingRepo()
        svc = BillingService(repo)
        await credit_wallet(repo, 1, Money(500), "topup")
        resv = await svc.reserve(user_id=1, amount=Money(100), idempotency_key="k1")
        r1 = await svc.release(reservation_id=resv["reservation_id"], reason="cancel")
        # Releasing an already-released reservation is a safe no-op.
        r2 = await svc.release(reservation_id=resv["reservation_id"], reason="cancel")
        assert r1["status"] == "released"
        assert r2["status"] == "released"
        assert repo.wallets[1]["reserved"] == 0

    _run(run())


def test_release_blocks_settle_afterwards():
    async def run():
        repo = MemoryBillingRepo()
        svc = BillingService(repo)
        await credit_wallet(repo, 1, Money(500), "topup")
        resv = await svc.reserve(user_id=1, amount=Money(100), idempotency_key="k1")
        await svc.release(reservation_id=resv["reservation_id"])
        with pytest.raises(ReservationError):
            await svc.settle(reservation_id=resv["reservation_id"], final_amount=Money(10))

    _run(run())


# ── Payment callback hardening ───────────────────────────────────────────────
def test_callback_credits_wallet_and_is_replay_protected():
    async def run():
        repo = MemoryBillingRepo()
        repo.seed_payment(1, user_id=1, amount=1000, authority="AUTH1", status="pending")
        r1 = await handle_payment_callback(
            repo, authority="AUTH1", status="OK", verify_fn=_verify_ok
        )
        assert r1.ok and r1.amount == 1000
        assert repo.wallets[1]["balance"] == 1000

        # Replay: same authority again must be rejected (order already completed).
        r2 = await handle_payment_callback(
            repo, authority="AUTH1", status="OK", verify_fn=_verify_ok
        )
        assert r2.ok is False and r2.code == 409
        # Wallet credited exactly once.
        assert repo.wallets[1]["balance"] == 1000

    _run(run())


def test_concurrent_callbacks_credit_exactly_once():
    async def run():
        repo = MemoryBillingRepo()
        repo.seed_payment(1, user_id=1, amount=1000, authority="AUTH1", status="pending")

        async def call():
            return await handle_payment_callback(
                repo, authority="AUTH1", status="OK", verify_fn=_verify_ok
            )

        results = await asyncio.gather(call(), call())
        ok_count = sum(1 for r in results if r.ok)
        assert ok_count == 1, f"expected exactly one successful credit, got {ok_count}"
        # The per-order lock guarantees no double credit.
        assert repo.wallets[1]["balance"] == 1000

    _run(run())


def test_callback_rejects_unknown_or_completed_order():
    async def run():
        repo = MemoryBillingRepo()
        # Never-seeded authority.
        r = await handle_payment_callback(
            repo, authority="NOPE", status="OK", verify_fn=_verify_ok
        )
        assert r.ok is False and r.code == 409

        # Already-completed order.
        repo.seed_payment(2, user_id=1, amount=500, authority="DONE", status="completed")
        r2 = await handle_payment_callback(
            repo, authority="DONE", status="OK", verify_fn=_verify_ok
        )
        assert r2.ok is False and r2.code == 409

    _run(run())


def test_callback_rejects_amount_mismatch():
    async def run():
        repo = MemoryBillingRepo()
        repo.seed_payment(1, user_id=1, amount=1000, authority="AUTH1", status="pending")
        # Tampered expected amount -> rejected before any gateway call.
        r = await handle_payment_callback(
            repo, authority="AUTH1", status="OK",
            verify_fn=_verify_ok, expected_amount=Money(999),
        )
        assert r.ok is False and r.code == 400
        assert repo.payments["AUTH1"]["status"] == "pending"

    _run(run())


def test_callback_marks_failed_on_gateway_failure_and_credits_nothing():
    async def run():
        repo = MemoryBillingRepo()
        repo.seed_payment(1, user_id=1, amount=1000, authority="AUTH1", status="pending")
        r = await handle_payment_callback(
            repo, authority="AUTH1", status="OK", verify_fn=_verify_fail
        )
        assert r.ok is False and r.code == 400
        # No wallet credit; order marked failed.
        assert repo.wallets.get(1, {"balance": 0})["balance"] == 0
        assert repo.payments["AUTH1"]["status"] == "failed"

    _run(run())


def test_callback_rejects_cancelled_status():
    async def run():
        repo = MemoryBillingRepo()
        repo.seed_payment(1, user_id=1, amount=1000, authority="AUTH1", status="pending")
        r = await handle_payment_callback(
            repo, authority="AUTH1", status="NOK", verify_fn=_verify_ok
        )
        assert r.ok is False and r.code == 400
        assert repo.payments["AUTH1"]["status"] == "pending"

    _run(run())


# ── Metering ─────────────────────────────────────────────────────────────────
def test_compute_charge_is_exact_integer_math():
    price = {
        "input_per_million": 10,
        "output_per_million": 20,
        "cached_input_per_million": 5,
        "reasoning_per_million": 30,
    }
    # 1M input -> 10, 2M output -> 40, 1M cached -> 5, 0 reasoning -> 0 => 55
    charge = compute_charge(
        price,
        input_tokens=1_000_000,
        output_tokens=2_000_000,
        cached_input_tokens=1_000_000,
        reasoning_tokens=0,
    )
    assert isinstance(charge, Money)
    assert charge.amount == 55

    # Half-up rounding: 1.5M tokens at 3/M => (1_500_000*3 + 500_000)//1_000_000 = 5
    assert compute_charge({"input_per_million": 3}, input_tokens=1_500_000).amount == 5


def test_record_usage_persists_event():
    async def run():
        repo = MemoryBillingRepo()
        await record_usage(
            repo,
            request_id="req-9",
            user_id=1,
            model="gpt-4o",
            charge=Money(55),
            upstream_status=UPSTREAM_SUCCESS,
            price_version="v1",
            provider="openai",
            input_tokens=1_000_000,
            output_tokens=2_000_000,
            reservation_id="resv_x",
        )
        assert len(repo.usage) == 1
        ev = list(repo.usage.values())[0]
        assert ev["request_id"] == "req-9"
        assert ev["model"] == "gpt-4o"
        assert ev["charged_amount"] == 55
        assert ev["input_tokens"] == 1_000_000
        assert ev["output_tokens"] == 2_000_000
        assert ev["reservation_id"] == "resv_x"
        assert ev["upstream_status"] == UPSTREAM_SUCCESS

    _run(run())
