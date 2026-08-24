"""Billing/wallet/subscription ORM models: subscriptions, ledger, payments,
wallet + reservations, usage events, plans, and credit packages.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, _utcnow


class Subscription(Base):
    __tablename__ = 'subscriptions'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    plan: Mapped[str] = mapped_column(sqlalchemy.String(32))
    # Column has existed in the DB since migrations/0005_pricing_system.sql;
    # it was never mapped here, so payment_endpoints.py's paid-subscription
    # checkout completion (Subscription(..., plan_id=plan.id, ...)) raised
    # TypeError on every successful payment ("plan_id is an invalid keyword
    # argument for Subscription") before this was added.
    plan_id: Mapped[str | None] = mapped_column(sqlalchemy.ForeignKey('plans.id'), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(default=_utcnow)
    ends_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default='active')
    monthly_token_quota: Mapped[int] = mapped_column(default=0)
    tokens_used_this_period: Mapped[int] = mapped_column(default=0)
    auto_renew: Mapped[bool] = mapped_column(default=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    price_paid: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
    subscription_id: Mapped[int | None] = mapped_column(nullable=True)
    credits_charged: Mapped[int] = mapped_column(default=0)
    payg_charged: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Plan(Base):
    """Subscription plan definitions."""
    __tablename__ = 'plans'
    id: Mapped[str] = mapped_column(primary_key=True)
    name_fa: Mapped[str]
    name_en: Mapped[str]
    price_monthly: Mapped[int] = mapped_column(default=0)
    monthly_token_quota: Mapped[int] = mapped_column(default=0)
    daily_token_limit: Mapped[int] = mapped_column(default=0)
    models_allowed: Mapped[list | None] = mapped_column(sqlalchemy.JSON, default=list)
    priority_queue: Mapped[bool] = mapped_column(default=False)
    features: Mapped[list | None] = mapped_column(sqlalchemy.JSON, default=list)
    active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
