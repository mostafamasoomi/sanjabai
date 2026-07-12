"""Pure reservation / settlement primitives (Phase 2.3).

These are framework-agnostic, in-memory functions that enforce the billing
invariants from the product contract:

  authorize -> reserve an upper bound
  after response -> settle actual usage, release remainder
  on failure/cancel -> deterministic release/refund

Every effect is append-only; the ledger invariant
  balance_after == previous_balance + amount
is enforced. Duplicate (idempotent) business events produce no duplicate
effect. In production these operations back the SQL wallet/reservation
tables via :class:`services.billing.SqlBillingRepo`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from services.money import Money


@dataclass
class PureWallet:
    available_paid: int = 0       # tomans
    reserved_paid: int = 0        # tomans
    promotional: int = 0          # tomans


@dataclass
class PureLedgerEffect:
    event_id: str
    idempotency_key: str
    currency: str
    amount: int                    # signed integer tomans
    balance_after: int
    source_type: str
    source_id: str
    actor_id: int


@dataclass
class PureBillingState:
    wallet: PureWallet = field(default_factory=PureWallet)
    ledger: list[PureLedgerEffect] = field(default_factory=list)
    reservations: dict[str, int] = field(default_factory=dict)
    _seen: set[str] = field(default_factory=set)


def _net(state: PureBillingState) -> int:
    return sum(e.amount for e in state.ledger)


def _append(state: PureBillingState, *, amount: int, idempotency_key: str,
            source_type: str, source_id: str, actor_id: int,
            currency: str = "IRT") -> Optional[PureLedgerEffect]:
    if idempotency_key in state._seen:
        for e in state.ledger:
            if e.idempotency_key == idempotency_key:
                return e
    balance_after = _net(state) + amount
    effect = PureLedgerEffect(
        event_id=uuid4().hex,
        idempotency_key=idempotency_key,
        currency=currency,
        amount=amount,
        balance_after=balance_after,
        source_type=source_type,
        source_id=source_id,
        actor_id=actor_id,
    )
    state.ledger.append(effect)
    state._seen.add(idempotency_key)
    return effect


def reserve(state: PureBillingState, amount: Money, reservation_id: str,
            actor_id: int, idempotency_key: Optional[str] = None) -> PureBillingState:
    if amount.irt <= 0:
        raise ValueError("reservation amount must be positive")
    if amount.irt > state.wallet.available_paid:
        raise ValueError("insufficient balance")
    if reservation_id in state.reservations:
        if state.reservations[reservation_id] != amount.irt:
            raise ValueError("reservation id reused with different amount")
        return state
    state.wallet.available_paid -= amount.irt
    state.wallet.reserved_paid += amount.irt
    state.reservations[reservation_id] = amount.irt
    _append(
        state, amount=-amount.irt, idempotency_key=idempotency_key or f"reserve:{reservation_id}",
        source_type="reservation", source_id=reservation_id, actor_id=actor_id,
    )
    return state


def settle(state: PureBillingState, reservation_id: str, actual: Money,
           actor_id: int, idempotency_key: Optional[str] = None) -> PureBillingState:
    if reservation_id not in state.reservations:
        raise ValueError("unknown reservation")
    reserved = state.reservations[reservation_id]
    if actual.irt > reserved:
        raise ValueError("settled amount exceeds reservation")
    remainder = reserved - actual.irt
    state.wallet.reserved_paid -= reserved
    state.wallet.available_paid -= actual.irt
    if remainder > 0:
        state.wallet.available_paid += remainder
    del state.reservations[reservation_id]
    _append(
        state, amount=-actual.irt, idempotency_key=idempotency_key or f"settle:{reservation_id}",
        source_type="settlement", source_id=reservation_id, actor_id=actor_id,
    )
    return state


def release(state: PureBillingState, reservation_id: str,
            actor_id: int, idempotency_key: Optional[str] = None) -> PureBillingState:
    if reservation_id not in state.reservations:
        return state
    reserved = state.reservations[reservation_id]
    state.wallet.reserved_paid -= reserved
    state.wallet.available_paid += reserved
    del state.reservations[reservation_id]
    _append(
        state, amount=0, idempotency_key=idempotency_key or f"release:{reservation_id}",
        source_type="release", source_id=reservation_id, actor_id=actor_id,
    )
    return state


def check_invariants(state: PureBillingState) -> None:
    running = 0
    for e in state.ledger:
        running += e.amount
        if e.balance_after != running:
            raise AssertionError(
                f"ledger invariant broken: effect {e.event_id} "
                f"balance_after={e.balance_after} expected={running}"
            )
    if state.wallet.available_paid < 0 or state.wallet.reserved_paid < 0:
        raise AssertionError("wallet balance went negative")
    if sum(state.reservations.values()) != state.wallet.reserved_paid:
        raise AssertionError("reserved total mismatch")
