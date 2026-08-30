"""
SQLAlchemy ORM models for the Sanjabai platform.

This is a package, not a single module: the models are grouped by domain
into submodules (users, billing, catalog, content, conversations, skills,
rag, hermes) that all build on the shared ``Base``/``_utcnow``/pgvector
setup in ``.base``. This file re-exports the full public surface so
``from models import X`` keeps working exactly as it did when this was a
single ``models.py`` file -- nothing here should be imported directly by
other modules; import from the package root as before.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import sqlalchemy
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, Vector, _HAS_PGVECTOR, _utcnow

from ._users import (
    User,
    Quota,
    Notification,
    ApiKey,
    AuditLog,
    UserBillingSetting,
    UserMemory,
)
from ._billing import (
    Ledger,
    Payment,
    Wallet,
    WalletReservation,
    UsageEvent,
    CreditPackage,
)
from ._catalog import (
    ModelAlias,
    Pricing,
    StatusIncident,
)
from ._content import (
    Feature,
    Discount,
    AboutContent,
    ProxyConfig,
)
from ._conversations import (
    Assistant,
    CompareSession,
    Conversation,
    ScheduledTask,
    TaskExecution,
)
from ._skills import (
    SkillTemplate,
    SkillTemplateRating,
    UserSkillActivation,
)
from ._rag import (
    RagDocument,
    RagChunk,
    RagEmbeddingUsage,
)
from ._hermes import (
    HermesOffering,
    HermesSkillCatalog,
    HermesOrder,
    HermesServer,
    HermesServerSkill,
    HermesAgentEvent,
)

__all__ = [
    'AboutContent', 'Any', 'ApiKey', 'Assistant', 'AuditLog', 'Base',
    'CompareSession', 'Conversation', 'CreditPackage', 'Decimal', 'Discount', 'Feature',
    'HermesAgentEvent', 'HermesOffering', 'HermesOrder', 'HermesServer',
    'HermesServerSkill', 'HermesSkillCatalog', 'JSONB', 'Ledger', 'Mapped',
    'ModelAlias', 'Notification', 'Payment', 'Pricing',
    'ProxyConfig', 'Quota', 'RagChunk', 'RagDocument', 'RagEmbeddingUsage',
    'ScheduledTask', 'SkillTemplate', 'SkillTemplateRating',
    'StatusIncident', 'TaskExecution', 'UsageEvent',
    'User', 'UserBillingSetting', 'UserMemory', 'UserSkillActivation',
    'Vector', 'Wallet', 'WalletReservation', 'datetime', 'func',
    'mapped_column', 'select', 'sqlalchemy', 'timezone',
]
