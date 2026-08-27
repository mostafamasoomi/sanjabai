"""Guards the models.py -> models/ package split.

Asserts the package's public import surface and Base.metadata table/column
set are exactly what the pre-split single-file models.py exposed. See the
session report for the captured before/after values this was verified
against.

Migration 0049 is the first DELIBERATE divergence from the captured
baseline: ``Plan`` and ``Subscription`` were removed from the surface, and
the ``plans``/``subscriptions`` tables from the metadata, when the owner
retired the plan/subscription concept. The four dead ``credit_packages``
columns (name/price/credits/bonus_credits) went with them. The expected
values below were re-captured after that change -- they are no longer the
pre-split numbers, and the docstring above is kept for the history.
"""
import hashlib
import json

import models

EXPECTED_SURFACE = [
    'AboutContent', 'Any', 'ApiKey', 'Assistant', 'AuditLog', 'Base',
    'Conversation', 'CreditPackage', 'Decimal', 'Discount', 'Feature',
    'HermesAgentEvent', 'HermesOffering', 'HermesOrder', 'HermesServer',
    'HermesServerSkill', 'HermesSkillCatalog', 'JSONB', 'Ledger', 'Mapped',
    'ModelAlias', 'Notification', 'Payment', 'Pricing',
    'ProxyConfig', 'Quota', 'RagChunk', 'RagDocument', 'RagEmbeddingUsage',
    'ScheduledTask', 'SkillTemplate', 'SkillTemplateRating',
    'StatusIncident', 'TaskExecution', 'UsageEvent',
    'User', 'UserBillingSetting', 'UserMemory', 'UserSkillActivation',
    'Vector', 'Wallet', 'WalletReservation', 'annotations', 'datetime',
    'func', 'mapped_column', 'select', 'sqlalchemy', 'timezone',
]

# sha256 of sorted (table_name, sorted(column_names)) tuples captured from
# the original single-file backend/models.py via Base.metadata.tables
# (sorted_tables can't be used: it raises NoReferencedTableError for
# credit_packages.model_id -> model_catalog, a pre-existing condition
# unrelated to this split -- that table is defined in a module not
# imported by this test).
# Re-captured after migration 0049 dropped `plans` and `subscriptions` from
# the metadata. The pre-0049 value was
# da62bdbb1147e948223ec86d8bcb2d1e1894d92559a724ada6a973944b56b65e -- kept
# here so a future session can tell a deliberate change from a drift.
EXPECTED_TABLES_HASH = "485f233e482f10dc322a53b84d0af116289cb852cc8d90b7d326871dd37937e6"


def test_public_surface_unchanged():
    names = sorted(n for n in dir(models) if not n.startswith('_'))
    assert names == EXPECTED_SURFACE


def test_metadata_tables_unchanged():
    tables = sorted(
        (t.name, tuple(sorted(c.name for c in t.columns)))
        for t in models.Base.metadata.tables.values()
    )
    digest = hashlib.sha256(json.dumps(tables).encode()).hexdigest()
    assert digest == EXPECTED_TABLES_HASH
