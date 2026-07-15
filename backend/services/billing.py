"""Billing repository + wallet credit for Multiai.

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
        return dict(row._mapping) if row else None

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
        return res.fetchone()

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
        return {"balance": row["balance"], "reserved": row["reserved"]}

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


async def credit_wallet(
    repo: Any,
    user_id: int,
    amount: Money,
    reason: str,
    idempotency_key: Optional[str] = None,
) -> None:
    """Atomically credit a wallet and append a ledger effect.

    Works against either :class:`SqlBillingRepo` or :class:`MemoryBillingRepo`.

    Idempotent: if a ledger row with the same ``idempotency_key`` already
    exists (and a key was supplied), no change is made (prevents double-credit
    on payment replay).
    """
    if not isinstance(amount, Money):
        raise TypeError("amount must be a Money instance")

    # Idempotency guard.
    if idempotency_key is not None and await repo.ledger_has_key(idempotency_key):
        return

    row = await repo.get_wallet(user_id)
    if row is None:
        await repo.create_wallet(user_id, amount.irt)
        new_balance = amount.irt
    else:
        new_balance = row["balance"] + amount.irt
        await repo.set_wallet_balance(user_id, new_balance)

    await repo.append_ledger({
        "user_id": user_id,
        "amount": amount.irt,
        "balance_after": new_balance,
        "reason": reason,
        "idempotency_key": idempotency_key,
    })


class MemoryBillingRepo:
    """In-memory billing repository (no database).

    Models the same contract as :class:`SqlBillingRepo` but keeps all state in
    plain dicts/lists and uses :class:`asyncio.Lock` per-row to simulate ``FOR
    UPDATE`` row locks. Intended for tests and as a reference implementation.
    """

    def __init__(self):
        self.wallets: dict[int, dict] = {}        # user_id -> {balance, reserved}
        self.reservations: dict[str, dict] = {}    # reservation_id -> reservation
        self.ledger: list[dict] = []               # list of ledger effect dicts
        self.usage: dict[str, dict] = {}           # request_id -> usage event
        self.payments: dict[str, dict] = {}        # authority -> payment order
        self._wallet_locks: dict[int, asyncio.Lock] = {}
        self._payment_locks: dict[str, asyncio.Lock] = {}

    # ── wallet ──
    async def get_wallet(self, user_id: int) -> Optional[dict]:
        return self.wallets.get(user_id)

    async def ensure_wallet(self, user_id: int) -> dict:
        if user_id not in self.wallets:
            self.wallets[user_id] = {"balance": 0, "reserved": 0}
        return self.wallets[user_id]

    async def create_wallet(self, user_id: int, balance: int) -> None:
        self.wallets[user_id] = {"balance": int(balance), "reserved": 0}

    async def set_wallet_balance(self, user_id: int, balance: int) -> None:
        w = self.wallets.setdefault(user_id, {"balance": 0, "reserved": 0})
        w["balance"] = int(balance)

    async def set_wallet_reserved(self, user_id: int, reserved: int) -> None:
        w = self.wallets.setdefault(user_id, {"balance": 0, "reserved": 0})
        w["reserved"] = int(reserved)

    @asynccontextmanager
    async def lock_wallet_for_update(self, user_id: int):
        lock = self._wallet_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            yield

    async def append_ledger(self, data: dict) -> None:
        self.ledger.append(data)

    async def ledger_has_key(self, idempotency_key: str) -> bool:
        return any(
            e.get("idempotency_key") == idempotency_key for e in self.ledger
        )

    # ── reservations ──
    async def create_reservation(self, data: dict) -> None:
        self.reservations[data["reservation_id"]] = data

    async def get_reservation(self, reservation_id: str) -> Optional[dict]:
        return self.reservations.get(reservation_id)

    async def get_reservation_by_idem(self, idempotency_key: str) -> Optional[dict]:
        for r in self.reservations.values():
            if r.get("idempotency_key") == idempotency_key:
                return r
        return None

    async def mark_reservation_settled(self, reservation_id: str, charged_amount: int) -> None:
        r = self.reservations.get(reservation_id)
        if r is not None:
            r["status"] = "settled"
            r["charged_amount"] = int(charged_amount)

    # ── usage ──
    async def append_usage_event(self, data: dict) -> None:
        self.usage[data["request_id"]] = data

    # ── payment orders (used by payment.handle_payment_callback) ──
    def seed_payment(self, payment_id, *, user_id, amount, authority, status) -> None:
        self.payments[authority] = {
            "id": payment_id,
            "user_id": user_id,
            "amount": amount,
            "authority": authority,
            "status": status,
            "ref_id": None,
        }

    async def lock_pending_payment(self, authority: str) -> Optional[dict]:
        lock = self._payment_locks.setdefault(authority, asyncio.Lock())
        await lock.acquire()
        pay = self.payments.get(authority)
        if pay is None or pay["status"] != "pending":
            return None
        return dict(pay)

    async def mark_payment_failed(self, payment_id: int) -> None:
        for p in self.payments.values():
            if p["id"] == payment_id:
                p["status"] = "failed"
                return

    async def mark_payment_completed(self, payment_id: int, ref_id: str) -> None:
        for p in self.payments.values():
            if p["id"] == payment_id:
                p["status"] = "completed"
                p["ref_id"] = ref_id
                return

    async def release_pending_lock(self, authority: str) -> None:
        lock = self._payment_locks.get(authority)
        if lock is not None and lock.locked():
            lock.release()

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


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
        return amount.irt <= available

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
            if amount.irt > available:
                raise InsufficientBalanceError(
                    f"insufficient balance: available {available}, "
                    f"requested {amount.irt}"
                )
            existing = await self.repo.get_reservation_by_idem(idempotency_key)
            if existing is not None:
                return existing
            reservation_id = uuid4().hex
            reservation = {
                "reservation_id": reservation_id,
                "user_id": user_id,
                "hold_amount": amount.irt,
                "status": "reserved",
                "idempotency_key": idempotency_key,
                "model": model,
                "price_version": price_version,
                "charged_amount": None,
            }
            await self.repo.set_wallet_reserved(
                user_id, wallet["reserved"] + amount.irt
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
        if final_amount.irt > hold:
            raise ReservationError(
                f"final charge {final_amount.irt} exceeds reservation hold {hold}"
            )
        user_id = resv["user_id"]
        wallet = await self.repo.ensure_wallet(user_id)
        new_balance = wallet["balance"] - final_amount.irt
        new_reserved = wallet["reserved"] - hold
        await self.repo.set_wallet_balance(user_id, new_balance)
        await self.repo.set_wallet_reserved(user_id, new_reserved)
        await self.repo.append_ledger({
            "user_id": user_id,
            "amount": -final_amount.irt,
            "balance_after": new_balance,
            "reason": "settlement",
            "idempotency_key": f"settle:{reservation_id}",
        })
        resv["status"] = "settled"
        resv["charged_amount"] = final_amount.irt
        await self.repo.mark_reservation_settled(reservation_id, final_amount.irt)
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
        wallet = await self.repo.ensure_wallet(user_id)
        new_reserved = wallet["reserved"] - hold
        await self.repo.set_wallet_reserved(user_id, new_reserved)
        resv["status"] = "released"
        resv["released_reason"] = reason
        return resv
