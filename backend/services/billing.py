"""Billing repository + wallet credit for Sanjabai.

Provides repository implementations:

* :class:`SqlBillingRepo` — the concrete repo the API and payment gateway
  delegate to in production (SQLAlchemy-backed).
* :class:`MemoryBillingRepo` — an in-memory repo used by tests and as a
  reference implementation of the same contract.

And :func:`credit_wallet`, the atomic wallet + ledger credit with idempotency,
which works against either repository implementation.

Model imports are lazy (inside methods) to avoid a circular import with
``app`` (``app`` imports this module at startup).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from services.money import Money

# MemoryBillingRepo split out to services/billing_memory.py purely to stay
# under the house 500-line cap (pure move, no behaviour change -- see that
# module's docstring). Re-exported here so every existing
# `from services.billing import MemoryBillingRepo` keeps working unchanged.
from services.billing_memory import MemoryBillingRepo  # noqa: F401


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Exceptions ───────────────────────────────────────────────────────────────
class InsufficientBalanceError(Exception):
    """Raised when a reserve/authorize request exceeds the available balance."""


class ReservationNotFoundError(Exception):
    """Raised when an operation references a reservation that does not exist."""


class ReservationError(Exception):
    """Raised for invalid reservation state transitions (e.g. overcharge)."""


class SqlBillingRepo:
    """SQLAlchemy-backed billing repository."""

    def __init__(self, session):
        self.session = session

    # ── payment order lifecycle (used by payment.handle_payment_callback) ──
    async def lock_pending_payment(self, authority: str) -> Optional[dict]:
        from models import Payment
        from sqlalchemy import select
        res = await self.session.execute(
            select(Payment)
            .where(Payment.authority == authority, Payment.status == "pending")
            .with_for_update()
        )
        row = res.fetchone()
        if row is None:
            return None
        p = row[0]
        return {
            "id": p.id,
            "user_id": p.user_id,
            "amount": p.amount,
            "status": p.status,
            "authority": p.authority,
            "ref_id": p.ref_id,
            "verified_at": p.verified_at,
        }

    async def mark_payment_failed(self, payment_id: int) -> None:
        from models import Payment
        await self.session.execute(
            Payment.__table__.update()
            .where(Payment.id == payment_id)
            .values(status="failed")
        )

    async def mark_payment_completed(self, payment_id: int, ref_id: str) -> None:
        from models import Payment
        await self.session.execute(
            Payment.__table__.update()
            .where(Payment.id == payment_id)
            .values(status="completed", ref_id=ref_id, verified_at=_now())
        )

    async def release_pending_lock(self, authority: str) -> None:
        # FOR UPDATE lock is released by commit()/rollback().
        return None

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    # ── usage metering (used by services.metering.record_usage) ──
    async def append_usage_event(self, data: dict) -> None:
        from models import UsageEvent
        self.session.add(UsageEvent(**data))

    # ── wallet helpers (used by credit_wallet / BillingService) ──
    async def get_wallet(self, user_id: int):
        from models import Wallet
        from sqlalchemy import select
        res = await self.session.execute(select(Wallet).where(Wallet.user_id == user_id))
        row = res.fetchone()
        if row is None:
            return None
        wallet = row[0]
        return {"balance": wallet.balance, "reserved": wallet.reserved}

    async def create_wallet(self, user_id: int, balance: int) -> None:
        from models import Wallet
        self.session.add(Wallet(user_id=user_id, balance=int(balance), reserved=0))

    async def ensure_wallet(self, user_id: int):
        from models import Wallet
        from sqlalchemy import select
        res = await self.session.execute(select(Wallet).where(Wallet.user_id == user_id))
        row = res.fetchone()
        if row is None:
            await self.create_wallet(user_id, 0)
            return {"balance": 0, "reserved": 0}
        wallet = row[0]
        return {"balance": wallet.balance, "reserved": wallet.reserved}

    async def set_wallet_balance(self, user_id: int, balance: int) -> None:
        from models import Wallet
        from sqlalchemy import select
        res = await self.session.execute(select(Wallet).where(Wallet.user_id == user_id))
        row = res.fetchone()
        if row is None:
            self.session.add(Wallet(user_id=user_id, balance=int(balance), reserved=0))
        else:
            await self.session.execute(
                Wallet.__table__.update()
                .where(Wallet.user_id == user_id)
                .values(balance=int(balance))
            )

    async def set_wallet_reserved(self, user_id: int, reserved: int) -> None:
        from models import Wallet
        from sqlalchemy import select
        res = await self.session.execute(select(Wallet).where(Wallet.user_id == user_id))
        row = res.fetchone()
        if row is None:
            self.session.add(Wallet(user_id=user_id, balance=0, reserved=int(reserved)))
        else:
            await self.session.execute(
                Wallet.__table__.update()
                .where(Wallet.user_id == user_id)
                .values(reserved=int(reserved))
            )

    async def append_ledger(self, data: dict) -> None:
        from models import Ledger
        self.session.add(Ledger(**data))

    async def ledger_has_key(self, idempotency_key: str) -> bool:
        from models import Ledger
        from sqlalchemy import select
        res = await self.session.execute(
            select(Ledger.id).where(Ledger.idempotency_key == idempotency_key)
        )
        return res.fetchone() is not None

    # ── reservation lifecycle (used by BillingService.reserve/settle/release) ──
    @asynccontextmanager
    async def lock_wallet_for_update(self, user_id: int):
        """Acquire FOR UPDATE lock on the wallet row (async context manager)."""
        from models import Wallet
        from sqlalchemy import select
        await self.session.execute(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update()
        )
        yield

    async def create_reservation(self, data: dict) -> None:
        from models import WalletReservation
        self.session.add(WalletReservation(
            reservation_id=data["reservation_id"],
            user_id=data["user_id"],
            amount=data["hold_amount"],
            currency="IRT",
            status=data.get("status", "reserved"),
            model=data.get("model"),
            price_version=data.get("price_version"),
            idempotency_key=data["idempotency_key"],
        ))

    async def get_reservation(self, reservation_id: str):
        from models import WalletReservation
        from sqlalchemy import select
        res = await self.session.execute(
            select(WalletReservation).where(
                WalletReservation.reservation_id == reservation_id
            )
        )
        row = res.fetchone()
        if row is None:
            return None
        r = row[0]
        return {
            "reservation_id": r.reservation_id,
            "user_id": r.user_id,
            "hold_amount": r.amount,
            "status": r.status,
            "idempotency_key": r.idempotency_key,
            "model": r.model,
            "price_version": r.price_version,
            "charged_amount": None,
        }

    async def get_reservation_by_idem(self, idempotency_key: str):
        from models import WalletReservation
        from sqlalchemy import select
        res = await self.session.execute(
            select(WalletReservation).where(
                WalletReservation.idempotency_key == idempotency_key
            )
        )
        row = res.fetchone()
        if row is None:
            return None
        r = row[0]
        return {
            "reservation_id": r.reservation_id,
            "user_id": r.user_id,
            "hold_amount": r.amount,
            "status": r.status,
            "idempotency_key": r.idempotency_key,
            "model": r.model,
            "price_version": r.price_version,
            "charged_amount": None,
        }

    async def mark_reservation_settled(self, reservation_id: str, charged_amount: int) -> None:
        from models import WalletReservation
        from sqlalchemy import update
        await self.session.execute(
            update(WalletReservation)
            .where(WalletReservation.reservation_id == reservation_id)
            .values(status="settled", settled_at=_now())
        )

    async def mark_reservation_released(self, reservation_id: str, reason: Optional[str] = None) -> bool:
        from models import WalletReservation
        from sqlalchemy import update
        result = await self.session.execute(
            update(WalletReservation)
            .where(
                WalletReservation.reservation_id == reservation_id,
                WalletReservation.status == "reserved",
            )
            .values(status="released", released_at=_now(), reason=reason)
        )
        return result.rowcount > 0


async def credit_wallet(
    repo: Any,
    user_id: int,
    amount: Money,
    reason: str,
    idempotency_key: Optional[str] = None,
    txn_type: str = "credit",
) -> None:
    """Atomically credit a wallet and append a ledger effect.

    Works against either :class:`SqlBillingRepo` or :class:`MemoryBillingRepo`.

    Idempotent: if a ledger row with the same ``idempotency_key`` already
    exists (and a key was supplied), no change is made (prevents double-credit
    on payment replay).

    ``txn_type`` labels the ledger row (defaults to ``"credit"``, preserving
    prior behaviour). Callers that need a distinguishable ledger category
    (e.g. ``"signup_bonus"``, ``"referral_bonus"``) should pass it explicitly
    so downstream reporting never mistakes a promotional credit for a real
    payment (``"topup"``).
    """
    if not isinstance(amount, Money):
        raise TypeError("amount must be a Money instance")

    # Idempotency guard.
    if idempotency_key is not None and await repo.ledger_has_key(idempotency_key):
        return

    async with repo.lock_wallet_for_update(user_id):
        row = await repo.get_wallet(user_id)
        if row is None:
            await repo.create_wallet(user_id, amount.toman)
            new_balance = amount.toman
        else:
            new_balance = row["balance"] + amount.toman
            await repo.set_wallet_balance(user_id, new_balance)

        await repo.append_ledger({
            "user_id": user_id,
            "txn_type": txn_type,
            "amount": amount.toman,
            "balance_after": new_balance,
            "reason": reason,
            "idempotency_key": idempotency_key,
        })



class BillingService:
    """High-level billing operations over a repository.

    All monetary amounts are :class:`services.money.Money` instances. Every
    mutating operation is idempotent on its ``idempotency_key`` / reservation
    id and enforces the available-balance invariant::

        available = balance - reserved
    """

    def __init__(self, repo: Any):
        self.repo = repo

    async def authorize(self, user_id: int, amount: Money) -> bool:
        """Return True iff ``amount`` can be covered by available balance."""
        wallet = await self.repo.get_wallet(user_id) or {"balance": 0, "reserved": 0}
        available = wallet["balance"] - wallet["reserved"]
        return amount.toman <= available

    async def reserve(
        self,
        user_id: int,
        amount: Money,
        idempotency_key: str,
        model: Optional[str] = None,
        price_version: Optional[str] = None,
    ) -> dict:
        async with self.repo.lock_wallet_for_update(user_id):
            wallet = await self.repo.ensure_wallet(user_id)
            available = wallet["balance"] - wallet["reserved"]
            if amount.toman > available:
                raise InsufficientBalanceError(
                    f"insufficient balance: available {available}, "
                    f"requested {amount.toman}"
                )
            existing = await self.repo.get_reservation_by_idem(idempotency_key)
            if existing is not None:
                return existing
            reservation_id = uuid4().hex
            reservation = {
                "reservation_id": reservation_id,
                "user_id": user_id,
                "hold_amount": amount.toman,
                "status": "reserved",
                "idempotency_key": idempotency_key,
                "model": model,
                "price_version": price_version,
                "charged_amount": None,
            }
            await self.repo.set_wallet_reserved(
                user_id, wallet["reserved"] + amount.toman
            )
            await self.repo.create_reservation(reservation)
            return reservation

    async def settle(
        self,
        reservation_id: str,
        final_amount: Money,
        request_id: Optional[str] = None,
        price_version: Optional[str] = None,
    ) -> dict:
        resv = await self.repo.get_reservation(reservation_id)
        if resv is None:
            raise ReservationNotFoundError(
                f"reservation {reservation_id} not found"
            )
        if resv["status"] == "settled":
            return resv
        if resv["status"] != "reserved":
            raise ReservationError(
                f"reservation {reservation_id} is '{resv['status']}', cannot settle"
            )
        hold = resv["hold_amount"]
        if final_amount.toman > hold:
            raise ReservationError(
                f"final charge {final_amount.toman} exceeds reservation hold {hold}"
            )
        user_id = resv["user_id"]
        wallet = await self.repo.ensure_wallet(user_id)
        new_balance = wallet["balance"] - final_amount.toman
        new_reserved = wallet["reserved"] - hold
        await self.repo.set_wallet_balance(user_id, new_balance)
        await self.repo.set_wallet_reserved(user_id, new_reserved)
        await self.repo.append_ledger({
            "user_id": user_id,
            "txn_type": "settlement",
            "amount": -final_amount.toman,
            "balance_after": new_balance,
            "reason": "settlement",
            "idempotency_key": f"settle:{reservation_id}",
        })
        resv["status"] = "settled"
        resv["charged_amount"] = final_amount.toman
        await self.repo.mark_reservation_settled(reservation_id, final_amount.toman)
        return resv

    async def release(self, reservation_id: str, reason: Optional[str] = None) -> dict:
        resv = await self.repo.get_reservation(reservation_id)
        if resv is None:
            raise ReservationNotFoundError(
                f"reservation {reservation_id} not found"
            )
        if resv["status"] == "released":
            return resv
        if resv["status"] != "reserved":
            raise ReservationError(
                f"reservation {reservation_id} is '{resv['status']}', cannot release"
            )
        hold = resv["hold_amount"]
        user_id = resv["user_id"]
        async with self.repo.lock_wallet_for_update(user_id):
            released = await self.repo.mark_reservation_released(reservation_id, reason)
            if released:
                wallet = await self.repo.ensure_wallet(user_id)
                new_reserved = wallet["reserved"] - hold
                await self.repo.set_wallet_reserved(user_id, new_reserved)
        resv["status"] = "released"
        resv["released_reason"] = reason
        return resv
