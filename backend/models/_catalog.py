"""Model-catalog / pricing ORM models: model aliases, versioned pricing, and
the public status-page incident banner.
"""
from __future__ import annotations

from datetime import datetime

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, _utcnow


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


class StatusIncident(Base):
    """Public status-page incident banner (see 0027_status_incident.sql).

    Admin-managed via POST/DELETE /admin/status/incident (status_page.py).
    At most one row is expected to be `active` at a time; /status/summary
    surfaces it alongside the Kuma heartbeat data.
    """
    __tablename__ = 'status_incident'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(nullable=False)
    body: Mapped[str] = mapped_column(default='')
    severity: Mapped[str] = mapped_column(default='warning')
    active: Mapped[bool] = mapped_column(default=True)
    started_at: Mapped[datetime] = mapped_column(default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)
