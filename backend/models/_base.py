"""
Shared imports and helpers for the SQLAlchemy ORM model package.

Every model submodule imports its common building blocks (``Base``,
``_utcnow``, the SQLAlchemy/typing re-exports, and the optional pgvector
``Vector`` type) from this module, so there is a single place that decides
how those are constructed. This avoids circular imports between the
domain-grouped model modules.
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
