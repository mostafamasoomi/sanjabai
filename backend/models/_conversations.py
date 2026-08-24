"""Chat/conversation-adjacent ORM models: assistants, conversations, and
scheduled tasks + their execution log.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, _utcnow


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
