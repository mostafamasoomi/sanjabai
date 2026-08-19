"""
SQLAlchemy ORM models for the Sanjabai platform.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import sqlalchemy
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

try:
    from pgvector.sqlalchemy import Vector
    _HAS_PGVECTOR = True
except ImportError:
    Vector = None  # type: ignore
    _HAS_PGVECTOR = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(index=True)
    phone: Mapped[str | None] = mapped_column(unique=True)
    referral_code: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    referred_by: Mapped[int | None] = mapped_column(nullable=True)
    banned: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    display_name: Mapped[str | None] = mapped_column(nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(nullable=True)
    bio: Mapped[str | None] = mapped_column(nullable=True)
    preferences: Mapped[dict | None] = mapped_column(sqlalchemy.JSON, default=dict)
    timezone: Mapped[str | None] = mapped_column(default='Asia/Tehran')
    language: Mapped[str | None] = mapped_column(default='fa')
    totp_secret: Mapped[str | None] = mapped_column(nullable=True)


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
    amount: Mapped[int]
    balance_after: Mapped[int]
    reason: Mapped[str]
    meta: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Quota(Base):
    __tablename__ = 'quota'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    daily_limit: Mapped[int]
    used_today: Mapped[int] = mapped_column(default=0)
    reset_at: Mapped[datetime]
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class ModelAlias(Base):
    __tablename__ = 'model_aliases'
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(unique=True, index=True)
    provider: Mapped[str]
    model_id: Mapped[str]
    priority: Mapped[int] = mapped_column(default=0)
    enabled: Mapped[bool] = mapped_column(default=True)


class Pricing(Base):
    """Versioned model pricing.

    Prices are immutable history: ``set_pricing`` never UPDATEs an existing
    row, it INSERTs a new version (a higher ``price_version``) for the model.
    The active price for a model is the row with the greatest
    ``effective_from`` (see :func:`get_active_price`).
    """
    __tablename__ = 'pricing'
    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(index=True)
    provider: Mapped[str] = mapped_column(default='unknown')
    input_per_million: Mapped[int] = mapped_column(default=0)
    output_per_million: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(default='IRT')
    source: Mapped[str | None] = mapped_column(nullable=True)
    price_version: Mapped[int] = mapped_column(default=1)
    effective_from: Mapped[datetime] = mapped_column(default=_utcnow)
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    __table_args__ = (
        sqlalchemy.UniqueConstraint('model', 'price_version', name='uq_pricing_model_version'),
    )


class Feature(Base):
    __tablename__ = 'features'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(default='')
    icon: Mapped[str] = mapped_column(default='star')
    active: Mapped[bool] = mapped_column(default=True)
    order_idx: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Discount(Base):
    __tablename__ = 'discounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(unique=True)
    percent: Mapped[int] = mapped_column(default=10)
    active: Mapped[bool] = mapped_column(default=True)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class AboutContent(Base):
    __tablename__ = 'about_content'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(default='درباره ما')
    body: Mapped[str] = mapped_column(default='')
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class ProxyConfig(Base):
    __tablename__ = 'proxy_config'
    id: Mapped[int] = mapped_column(primary_key=True)
    proxy_url: Mapped[str] = mapped_column(default='')
    proxy_type: Mapped[str] = mapped_column(default='socks5')
    active: Mapped[bool] = mapped_column(default=True)
    default_model: Mapped[str] = mapped_column(default='')
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Assistant(Base):
    __tablename__ = 'assistants'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(default='New Assistant')
    description: Mapped[str] = mapped_column(default='')
    system_prompt: Mapped[str] = mapped_column(default='')
    model_id: Mapped[str] = mapped_column(default='')
    icon: Mapped[str] = mapped_column(default='chat')
    is_public: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(default='گفتگوی جدید')
    model: Mapped[str] = mapped_column(default='')
    messages: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


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


class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    type: Mapped[str] = mapped_column(default='info')
    title: Mapped[str]
    body: Mapped[str] = mapped_column(default='')
    read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class ApiKey(Base):
    __tablename__ = 'api_keys'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(default='Default')
    key_hash: Mapped[str] = mapped_column(unique=True)
    key_prefix: Mapped[str] = mapped_column(default='sk-')
    active: Mapped[bool] = mapped_column(default=True)
    last_used: Mapped[datetime | None] = mapped_column(nullable=True)
    scopes: Mapped[str] = mapped_column(default='read')
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class AuditLog(Base):
    """Immutable record of privileged/admin actions for compliance + forensics."""
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    admin_user_id: Mapped[int | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(nullable=False)
    target_type: Mapped[str | None] = mapped_column(nullable=True)
    target_id: Mapped[str | None] = mapped_column(nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(nullable=True)
    user_agent: Mapped[str | None] = mapped_column(nullable=True)
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


class UserBillingSetting(Base):
    """Per-user billing preferences (PAYG toggle, limits)."""
    __tablename__ = 'user_billing_settings'
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), primary_key=True)
    payg_enabled: Mapped[bool] = mapped_column(default=True)
    payg_hard_limit: Mapped[int | None] = mapped_column(nullable=True)
    notify_on_usage_pct: Mapped[int] = mapped_column(default=80)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class UserMemory(Base):
    """Persistent user memory entries for memory-augmented chat."""
    __tablename__ = 'user_memories'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    content: Mapped[str] = mapped_column()
    category: Mapped[str] = mapped_column(default='general')
    source: Mapped[str] = mapped_column(default='manual')
    tags: Mapped[list | None] = mapped_column(sqlalchemy.ARRAY(sqlalchemy.Text), default=list)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class SkillTemplate(Base):
    """Skill template for the marketplace."""
    __tablename__ = 'skill_templates'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(sqlalchemy.ForeignKey('users.id'), nullable=True)
    title: Mapped[str]
    title_fa: Mapped[str]
    description: Mapped[str] = mapped_column(default='')
    description_fa: Mapped[str] = mapped_column(default='')
    category: Mapped[str] = mapped_column(default='general')
    prompt_template: Mapped[str]
    variables: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, default=list)
    default_model: Mapped[str] = mapped_column(default='')
    is_public: Mapped[bool] = mapped_column(default=False)
    is_featured: Mapped[bool] = mapped_column(default=False)
    usage_count: Mapped[int] = mapped_column(default=0)
    rating_sum: Mapped[int] = mapped_column(default=0)
    rating_count: Mapped[int] = mapped_column(default=0)
    tags: Mapped[list | None] = mapped_column(sqlalchemy.JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class SkillTemplateRating(Base):
    """Rating for a skill template."""
    __tablename__ = 'skill_template_ratings'
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('skill_templates.id'))
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'))
    rating: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class ScheduledTask(Base):
    __tablename__ = 'scheduled_tasks'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(default='')
    prompt: Mapped[str]
    model: Mapped[str] = mapped_column(default='mimo-v2.5')
    cron_expression: Mapped[str] = mapped_column(default='0 9 * * *')
    is_active: Mapped[bool] = mapped_column(default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    run_count: Mapped[int] = mapped_column(default=0)
    last_result: Mapped[str | None] = mapped_column(nullable=True)
    delivery_channel: Mapped[str] = mapped_column(default='dashboard')
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class TaskExecution(Base):
    __tablename__ = 'task_executions'
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('scheduled_tasks.id'))
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(default='pending')
    result: Mapped[str | None] = mapped_column(nullable=True)
    tokens_used: Mapped[int] = mapped_column(default=0)
    cost_toman: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ── RAG Models ─────────────────────────────────────────────────

class RagDocument(Base):
    __tablename__ = 'rag_documents'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    title: Mapped[str]
    file_name: Mapped[str | None] = mapped_column(nullable=True)
    file_type: Mapped[str | None] = mapped_column(nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(default='upload')
    source_url: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default='pending')
    error_message: Mapped[str | None] = mapped_column(nullable=True)
    chunk_count: Mapped[int] = mapped_column(default=0)
    total_chars: Mapped[int] = mapped_column(default=0)
    content_hash: Mapped[str | None] = mapped_column(nullable=True)
    meta: Mapped[dict | None] = mapped_column('metadata', sqlalchemy.JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class RagChunk(Base):
    __tablename__ = 'rag_chunks'
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('rag_documents.id'))
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'))
    chunk_index: Mapped[int]
    content: Mapped[str]
    token_count: Mapped[int] = mapped_column(default=0)
    embedding = mapped_column(Vector(1536) if _HAS_PGVECTOR else sqlalchemy.JSON, nullable=True)
    embedding_model: Mapped[str] = mapped_column(default='text-embedding-3-small')
    doc_metadata: Mapped[dict | None] = mapped_column('metadata', sqlalchemy.JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class RagEmbeddingUsage(Base):
    __tablename__ = 'rag_embedding_usage'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'))
    document_id: Mapped[int | None] = mapped_column(nullable=True)
    operation: Mapped[str]
    tokens_used: Mapped[int] = mapped_column(default=0)
    charged_amount: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(default='IRT')
    request_id: Mapped[str] = mapped_column(unique=True)
    model: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


# ── Hermes server product ──────────────────────────────────────
# Sells a ready-to-use VPS with the Hermes agent pre-installed, plus a
# catalog of installable "skills" the user picks at checkout or later.
# Pricing is EUR cost-basis (Hetzner) + margin, converted to Toman at read
# time for the live catalog and snapshotted (locked) on orders/servers.
# See backend/migrations/0019_hermes_servers.sql for the DDL these mirror.

class HermesOffering(Base):
    """A purchasable server SKU (a Hetzner instance type + margin)."""
    __tablename__ = 'hermes_offerings'
    id: Mapped[str] = mapped_column(primary_key=True)
    name_fa: Mapped[str]
    name_en: Mapped[str]
    description_fa: Mapped[str] = mapped_column(default='')
    description_en: Mapped[str] = mapped_column(default='')
    hetzner_type: Mapped[str]
    arch: Mapped[str] = mapped_column(default='amd64')
    vcpu: Mapped[int]
    ram_mb: Mapped[int]
    disk_gb: Mapped[int]
    traffic_tb: Mapped[int] = mapped_column(default=20)
    # EUR cost basis, never exposed to end users — see /hermes/offerings.
    provider_cost_eur: Mapped[Decimal] = mapped_column(sqlalchemy.Numeric(8, 2))
    margin_pct: Mapped[int] = mapped_column(default=50)
    setup_fee_irt: Mapped[int] = mapped_column(default=0)
    max_skills: Mapped[int] = mapped_column(default=5)
    included_credit: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class HermesSkillCatalog(Base):
    """A skill that can be installed on a Hermes server."""
    __tablename__ = 'hermes_skill_catalog'
    id: Mapped[str] = mapped_column(primary_key=True)
    name_fa: Mapped[str]
    name_en: Mapped[str]
    description_fa: Mapped[str] = mapped_column(default='')
    description_en: Mapped[str] = mapped_column(default='')
    category: Mapped[str] = mapped_column(default='general')
    manifest: Mapped[dict] = mapped_column(JSONB, default=dict)
    options_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    requires_cron: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class HermesOrder(Base):
    """A purchase of a Hermes server, with price locked at order time."""
    __tablename__ = 'hermes_orders'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    offering_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey('hermes_offerings.id'))
    status: Mapped[str] = mapped_column(default='pending_payment')
    setup_price_irt: Mapped[int]
    monthly_price_irt: Mapped[int]
    eur_rate_at_order: Mapped[Decimal | None] = mapped_column(sqlalchemy.Numeric(12, 2), nullable=True)
    priced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    payment_id: Mapped[int | None] = mapped_column(sqlalchemy.ForeignKey('payments.id'), nullable=True)
    requested_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class HermesServer(Base):
    """A delivered server instance."""
    __tablename__ = 'hermes_servers'
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('hermes_orders.id'), unique=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    offering_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey('hermes_offerings.id'))
    hostname: Mapped[str | None] = mapped_column(nullable=True)
    ip_address: Mapped[str | None] = mapped_column(nullable=True)
    ssh_port: Mapped[int] = mapped_column(default=22)
    region: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default='provisioning')
    monthly_price_irt: Mapped[int]
    paid_through_at: Mapped[datetime | None] = mapped_column(nullable=True)
    agent_token_hash: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    agent_token_prefix: Mapped[str | None] = mapped_column(nullable=True)
    api_key_id: Mapped[int | None] = mapped_column(sqlalchemy.ForeignKey('api_keys.id'), nullable=True)
    desired_state_version: Mapped[int] = mapped_column(default=0)
    applied_state_version: Mapped[int] = mapped_column(default=0)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(nullable=True)
    agent_version: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class HermesServerSkill(Base):
    """Desired-state row: one skill attached to one server."""
    __tablename__ = 'hermes_server_skills'
    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('hermes_servers.id'), index=True)
    skill_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey('hermes_skill_catalog.id'))
    options: Mapped[dict] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(default=True)
    state: Mapped[str] = mapped_column(default='pending')
    error: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class HermesAgentEvent(Base):
    """Append-only telemetry/audit trail reported by the agent daemon."""
    __tablename__ = 'hermes_agent_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('hermes_servers.id'), index=True)
    event: Mapped[str]
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
