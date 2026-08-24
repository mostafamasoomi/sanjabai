"""User/account/auth-adjacent ORM models: identity, quota, API keys, audit,
per-user billing preferences, long-term memory, and notifications.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, _utcnow


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


class Quota(Base):
    __tablename__ = 'quota'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    daily_limit: Mapped[int]
    used_today: Mapped[int] = mapped_column(default=0)
    reset_at: Mapped[datetime]
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


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
