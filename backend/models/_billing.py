"""Billing/wallet ORM models: ledger, payments, wallet + reservations,
usage events, and credit packages.

``Subscription`` and ``Plan`` were removed in migration 0049: the owner
retired the plan/subscription concept entirely and ``CreditPackage`` is now
the only product concept. ``UsageEvent.subscription_id`` survives them on
purpose -- see its own comment.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, _utcnow


class Ledger(Base):
    __tablename__ = 'ledger'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    # `ledger.txn_type` has been `NOT NULL` with no DB-side default since
    # migrations/0001_baseline.sql, but this model never mapped it -- every
    # ORM-built Ledger row (chat usage debits, wallet top-ups, referral
    # bonuses, Hermes renewals) has therefore been failing at INSERT with a
    # NotNullViolationError, silently swallowed by the broad
    # `except Exception: logger.warning(...)` at each call site. That is why
    # `ledger` had exactly one row (a manually-seeded 'initial_credit') and
    # zero real debits despite served chat traffic -- discovered while
    # fixing the billing loss-path audit (see chat.py::_record_usage). No
    # code anywhere reads txn_type today (grepped the whole backend), so a
    # generic default is safe for existing call sites that don't pass one
    # explicitly (e.g. hermes.py); chat.py/services/billing.py now pass an
    # explicit value ('usage' / 'credit' / 'settlement').
    txn_type: Mapped[str] = mapped_column(default='ledger_entry')
    amount: Mapped[int]
    balance_after: Mapped[int]
    reason: Mapped[str]
    meta: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    amount: Mapped[int]
    authority: Mapped[str] = mapped_column(unique=True, index=True)
    ref_id: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default='pending')
    payment_type: Mapped[str] = mapped_column(default='wallet_topup')
    reference_id: Mapped[str | None] = mapped_column(nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Wallet(Base):
    """Authoritative per-user balance row. Locked with FOR UPDATE on writes.

    ``balance`` is committed (spendable + held); ``reserved`` is the sum of open
    holds. Available balance = balance - reserved.
    """
    __tablename__ = 'wallet'
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), primary_key=True)
    balance: Mapped[int] = mapped_column(default=0)
    reserved: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class WalletReservation(Base):
    """A hold taken against the wallet before an upstream (paid) call."""
    __tablename__ = 'wallet_reservations'
    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[str] = mapped_column(unique=True, index=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    amount: Mapped[int]
    currency: Mapped[str] = mapped_column(default='IRT')
    status: Mapped[str] = mapped_column(default='reserved')
    model: Mapped[str | None] = mapped_column(nullable=True)
    price_version: Mapped[str | None] = mapped_column(nullable=True)
    request_id: Mapped[str | None] = mapped_column(nullable=True)
    idempotency_key: Mapped[str] = mapped_column(unique=True, index=True)
    reason: Mapped[str | None] = mapped_column(nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(nullable=True)


class UsageEvent(Base):
    """Immutable record of a single upstream model call / charge."""
    __tablename__ = 'usage_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(unique=True, index=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    model: Mapped[str]
    price_version: Mapped[str | None] = mapped_column(nullable=True)
    provider: Mapped[str | None] = mapped_column(nullable=True)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cached_input_tokens: Mapped[int] = mapped_column(default=0)
    reasoning_tokens: Mapped[int] = mapped_column(default=0)
    reservation_id: Mapped[str | None] = mapped_column(nullable=True)
    charged_amount: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(default='IRT')
    upstream_status: Mapped[str | None] = mapped_column(nullable=True)
    upstream_error: Mapped[str | None] = mapped_column(nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    billing_source: Mapped[str] = mapped_column(default='wallet')
    # Outlived the Subscription model it named (dropped in migration 0049).
    # Kept deliberately: it carries no foreign key, every row holds NULL, and
    # it is the only trace historical usage rows have of the retired concept.
    # Dropping it would rewrite history rather than record it.
    subscription_id: Mapped[int | None] = mapped_column(nullable=True)
    credits_charged: Mapped[int] = mapped_column(default=0)
    payg_charged: Mapped[int] = mapped_column(default=0)
    # ── What this request cost US upstream (migration 0048) ──────────
    # charged_amount above is what the USER paid; these are what we paid.
    # Both integer Toman. Every one of them defaults to NULL rather than 0,
    # and NULL means "unknown", never "free" -- reports may not COALESCE
    # them to zero. The full column semantics, the allowed values of
    # upstream_cost_basis, the revenue-weighted coverage contract the read
    # side is bound by, and the reason the migration MUST be applied before
    # this model deploys, are all in migrations/0048_usage_event_cost.sql.
    upstream_cost_toman: Mapped[int | None] = mapped_column(nullable=True)
    upstream_cost_basis: Mapped[str | None] = mapped_column(nullable=True)
    fx_rate_irt: Mapped[float | None] = mapped_column(nullable=True)
    usd_input_per_million: Mapped[float | None] = mapped_column(nullable=True)
    usd_output_per_million: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class CreditPackage(Base):
    """Pre-paid credit packages with optional bonus.

    ``model_id`` is optional display metadata (which model this bundle is
    framed around, e.g. "20M tokens of mimo") -- it does not change the
    checkout math, which still charges and credits ``total_credits`` 1:1.
    See migrations/0018_credit_package_model_label.sql.
    """
    __tablename__ = 'credit_packages'
    id: Mapped[str] = mapped_column(primary_key=True)
    name_fa: Mapped[str]
    name_en: Mapped[str]
    base_amount: Mapped[int] = mapped_column(default=0)
    bonus_percent: Mapped[int] = mapped_column(default=0)
    total_credits: Mapped[int] = mapped_column(default=0)
    model_id: Mapped[str | None] = mapped_column(sqlalchemy.ForeignKey('model_catalog.id', ondelete='SET NULL'), nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)
