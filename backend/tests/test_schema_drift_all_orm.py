"""Schema-drift guard derived from ``Base.metadata`` -- not a hand-maintained
list of models.

tests/test_schema_drift.py pins specific models (Feature, Discount,
AboutContent, Assistant, CreditPackage -- Plan was among them too until
migration 0049 retired plans/subscriptions and removed the ORM class
entirely) because those were the models known to have drifted *at the time
each fix shipped*. That is precisely why
it missed two more: ``Notification`` (models.py line 282, ``__tablename__ =
'notifications'``) had no backing table in production at all -- confirmed
2026-08-22 via ``SELECT to_regclass('public.notifications')`` returning null
and ``grep -rln notifications migrations/`` returning nothing -- and
``UserBillingSetting`` was missing two columns
(``payg_hard_limit``, ``notify_on_usage_pct``) that production genuinely
never had, which pricing.py's GET /me/billing selected unconditionally and
therefore 500'd on for every authenticated caller. Nothing in this repo said
so for either one, because nothing had ever added them to the hand-written
list. migrations/0038_notifications_table.sql and migrations/
0039_user_billing_settings_drift.sql are the fixes; this file is what makes
a further occurrence of the same bug class structurally impossible instead
of relying on someone remembering to extend a list again.

Approach: iterate every table SQLAlchemy actually knows about
(``Base.metadata.tables``, populated by importing ``models`` once at module
scope) and, for each one, check it against the real migration corpus using
the exact same static SQL parsers tests/test_schema_drift.py already has
(``_actual_sql_columns``, which is first-create-wins -- see that module's
comment on why a naive "any CREATE TABLE mentions this column" scan produces
false negatives on tables re-declared by a later no-op migration, as
0023_schema_drift_fix.sql does for ``plans``/``credit_packages``).

Tables that exist in the live database but are NOT ORM-mapped are raw-SQL
managed and are correctly excluded with no allowlist needed, because they
simply never appear in ``Base.metadata.tables``: app_setting,
exchange_rate_overrides, logical_model, logical_model_candidate,
model_availability_change, model_catalog, model_health_event,
model_health_state, package_entitlement, payment_orders, provider,
schema_migrations, sessions (13 tables, measured 2026-08-22 by diffing every
ORM ``__tablename__`` against a live ``\\dt``).

This file does not replace tests/test_schema_drift.py -- that file's pinned
tests document specific historical incidents and stay. This file is the
general net underneath them.
"""
from __future__ import annotations

import pathlib

import pytest

import models  # noqa: F401  -- importing registers every ORM class on Base.metadata
from database import Base

from tests.test_schema_drift import _actual_sql_columns, MIGRATIONS_DIR

# Sorted once at import time so both the parametrize list and any ad-hoc
# reporting below iterate tables in a stable, readable order.
_ORM_TABLE_NAMES = sorted(Base.metadata.tables.keys())

# ── history: a second drift instance this guard found and 0039 fixed ──────
#
# Running this file's column-backing test over every ORM table (2026-08-22,
# while building migrations/0038_notifications_table.sql) turned up a SECOND
# gap beyond notifications: user_billing_settings.payg_hard_limit and
# .notify_on_usage_pct (models.py UserBillingSetting) had no backing column
# anywhere in migrations/, and unlike the 0037 precedent this was NOT
# psql-created drift -- `\d user_billing_settings` on production (read-only,
# 2026-08-22) showed neither column existed there either. It was a live,
# currently-broken endpoint, not a hypothetical: pricing.py's GET
# /me/billing ran a SELECT naming both columns with no try/except, so the
# route 500'd for every authenticated caller.
#
# This was reported to the coordinator rather than guessed at here (the fix
# could have been a migration, or a models.py rollback, and models.py is out
# of scope for this guard's owner). Coordinator decision: fix migration-side
# -- production code, not merely the ORM, actively selects both columns and
# returns them in the route's response contract, so migrations/
# 0039_user_billing_settings_drift.sql adds the two columns (idempotent,
# non-destructive, table had 0 rows so no backfill was needed). See that
# file's header for the full record, including the DB-ahead-of-ORM reverse
# drift on the same table (auto_recharge, recharge_threshold,
# recharge_amount, spend_limit_monthly, current_spend) which is harmless and
# intentionally out of scope.
#
# No xfail marker remains for this table: with 0039 applied, the parametrized
# tests below cover it at full strength like every other ORM table, and
# test_user_billing_settings_specifically_is_fixed pins the specific
# regression.


def test_orm_has_the_expected_number_of_mapped_tables():
    """Canary for the discovery mechanism itself: if this drops to 0 (e.g.
    ``models`` failed to import, or ``Base.metadata`` got swapped by a
    mocking fixture) every test below would vacuously pass by iterating an
    empty parametrize list, hiding real drift instead of catching it. Pin a
    floor rather than an exact count so new models don't need this test
    edited every time -- 37 were mapped when this file was written
    (2026-08-22).

    Deliberately lowered to 36 (migration 0049, session 23): `plans` and
    `subscriptions` were retired and their ORM classes (`Plan`,
    `Subscription`) removed entirely -- this is exactly the "models.py
    legitimately shrank" case this docstring already anticipated, not a
    silent drop of the discovery mechanism."""
    assert len(_ORM_TABLE_NAMES) >= 36, (
        f"only {len(_ORM_TABLE_NAMES)} ORM tables discovered via "
        "Base.metadata.tables -- expected at least 36. If models.py legitimately "
        "shrank, lower this floor deliberately; if not, Base.metadata is not "
        "being populated the way this guard assumes and every other test in "
        "this file is passing vacuously."
    )


@pytest.mark.parametrize('table_name', _ORM_TABLE_NAMES)
def test_orm_table_is_created_by_some_migration(table_name):
    """(a) from the task spec: every ORM-mapped table must be created by at
    least one migration file, using first-create-wins semantics so a later
    no-op re-declaration (the 0023-on-plans case) doesn't count."""
    sql_columns = _actual_sql_columns(table_name)
    assert sql_columns, (
        f"ORM table {table_name!r} is declared in models.py but no migration "
        f"in {MIGRATIONS_DIR} creates it (first-create-wins scan found zero "
        "columns) -- add a numbered migration before this ships, or every "
        "query against it will 500 in production with UndefinedTable. See "
        "migrations/0038_notifications_table.sql for the pattern."
    )


@pytest.mark.parametrize('table_name', _ORM_TABLE_NAMES)
def test_orm_table_columns_have_migration_backing(table_name):
    """(b) from the task spec: every column the ORM declares on a mapped
    table must actually be produced by the migration corpus (CREATE TABLE
    on first creation, or a later ADD COLUMN, minus anything DROP COLUMN'd
    since) -- not merely that the table itself exists."""
    table = Base.metadata.tables[table_name]
    orm_columns = set(table.columns.keys())
    sql_columns = _actual_sql_columns(table_name)
    missing = orm_columns - sql_columns
    assert not missing, (
        f"{table_name!r} declares column(s) in models.py with no backing SQL "
        f"anywhere in {MIGRATIONS_DIR}: {sorted(missing)} -- add a migration "
        "before this ships, or any ORM query touching these columns will 500 "
        "in production with UndefinedColumn."
    )


def test_notifications_table_specifically_is_fixed():
    """Pinned regression for the exact bug this file exists because of --
    keeps the parametrized tests above from being the only thing standing
    between a future revert of 0038 and a live outage."""
    from models import Notification
    orm_columns = set(Notification.__table__.columns.keys())
    assert orm_columns == {'id', 'user_id', 'type', 'title', 'body', 'read', 'created_at'}
    sql_columns = _actual_sql_columns('notifications')
    assert orm_columns <= sql_columns, (
        "notifications table is missing migration backing for column(s) "
        f"{sorted(orm_columns - sql_columns)} -- migrations/"
        "0038_notifications_table.sql should cover all of Notification's columns."
    )


def test_user_billing_settings_specifically_is_fixed():
    """Pinned regression for the second drift instance this file's guard
    found (payg_hard_limit, notify_on_usage_pct) -- fixed by
    migrations/0039_user_billing_settings_drift.sql per the coordinator's
    decision to add the columns rather than roll back the ORM. Keeps the
    parametrized tests above from being the only thing standing between a
    future revert of 0039 and pricing.py's GET /me/billing 500ing again for
    every authenticated caller."""
    from models import UserBillingSetting
    orm_columns = set(UserBillingSetting.__table__.columns.keys())
    assert {'payg_hard_limit', 'notify_on_usage_pct'} <= orm_columns
    sql_columns = _actual_sql_columns('user_billing_settings')
    assert orm_columns <= sql_columns, (
        "user_billing_settings table is missing migration backing for "
        f"column(s) {sorted(orm_columns - sql_columns)} -- migrations/"
        "0039_user_billing_settings_drift.sql should cover all of "
        "UserBillingSetting's columns."
    )


def test_guard_goes_red_without_0038_notifications_migration(tmp_path):
    """Mandatory red-proof mutation, made permanent: copy migrations/ to a
    throwaway directory with 0038 removed, point the exact same
    _actual_sql_columns helper at that copy, and prove the guard actually
    flags 'notifications' as unbacked rather than passing by accident (e.g.
    an empty-set-equals-empty-set bug on both sides). This is a *static*
    check of the SQL-parsing logic -- it does not touch a real database --
    which is why it can safely run as part of the normal suite instead of
    only as a one-off manual step."""
    import shutil

    mutated_dir = tmp_path / 'migrations_without_0038'
    mutated_dir.mkdir()
    removed_any = False
    for path in sorted(MIGRATIONS_DIR.glob('*.sql')):
        if path.name.startswith('0038_'):
            removed_any = True
            continue
        shutil.copy2(path, mutated_dir / path.name)
    assert removed_any, (
        "expected to find and exclude a migrations/0038_*.sql file while "
        "building the mutated copy -- none was found, so this test cannot "
        "prove anything and would pass vacuously."
    )

    sql_columns_without_0038 = _actual_sql_columns('notifications', migrations_dir=mutated_dir)
    assert not sql_columns_without_0038, (
        "expected the guard to see ZERO backing columns for 'notifications' "
        "once 0038 is excluded from the migration corpus -- instead it saw "
        f"{sorted(sql_columns_without_0038)}, meaning some other migration "
        "creates this table and 0038 may be redundant or misnumbered."
    )

    # And with the real, unmutated directory it must be green again.
    sql_columns_with_0038 = _actual_sql_columns('notifications')
    orm_columns = set(Base.metadata.tables['notifications'].columns.keys())
    assert orm_columns <= sql_columns_with_0038, (
        "the real migrations/ directory (with 0038 present) still fails to "
        f"back every Notification column: missing {sorted(orm_columns - sql_columns_with_0038)}"
    )
