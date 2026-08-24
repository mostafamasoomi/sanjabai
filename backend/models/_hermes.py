"""Hermes server product ORM models.

Sells a ready-to-use VPS with the Hermes agent pre-installed, plus a
catalog of installable "skills" the user picks at checkout or later.
Pricing is EUR cost-basis (Hetzner) + margin, converted to Toman at read
time for the live catalog and snapshotted (locked) on orders/servers.
See backend/migrations/0019_hermes_servers.sql for the DDL these mirror.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import sqlalchemy
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, _utcnow


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
