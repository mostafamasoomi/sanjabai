"""In-memory billing repository -- split out of services/billing.py purely
to stay under the house 500-line cap. Nothing here changed in the move.

:class:`MemoryBillingRepo` implements the same duck-typed repo contract as
:class:`services.billing.SqlBillingRepo` (see that module's
:func:`services.billing.credit_wallet` and :class:`services.billing.BillingService`,
both of which work against either) but keeps all state in plain dicts/lists
with per-row :class:`asyncio.Lock` objects instead of a database. It has no
dependency on SqlBillingRepo/BillingService/credit_wallet and nothing in
those depends on it, so it moves cleanly on its own.

Re-exported from services/billing.py (`from services.billing_memory import
MemoryBillingRepo  # noqa: F401`) so every existing
``from services.billing import MemoryBillingRepo`` (tests/test_billing.py,
tests/test_admin_user_ops.py) keeps working unchanged.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Optional


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

    async def mark_reservation_released(self, reservation_id: str, reason: Optional[str] = None) -> bool:
        r = self.reservations.get(reservation_id)
        if r is None or r.get("status") != "reserved":
            return False
        r["status"] = "released"
        r["released_reason"] = reason
        return True

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
