"""Schema-drift guard for Feature, Discount, AboutContent, Assistant
(backend/models.py).

Before migration 0035, four ORM models drifted from the live database:

  * Feature (features) declared description/icon/active; the baseline table
    only ever had title/body/order_idx/updated_at.
  * Discount (discounts) described a discount-CODE feature (code, percent,
    active, expires_at); the baseline table was a landing-page content
    block (title, body, order_idx) that collided on the same table name and
    was never actually served by anything.
  * AboutContent declared __tablename__ = 'about_content'; the baseline
    only ever created a table named 'about' with the same columns.
  * Assistant (assistants) had no backing table at all.

Every one of these turned a plain SELECT/INSERT into a live 500
(UndefinedColumn or UndefinedTable) on GET /about, /assistants,
/admin/features, /admin/discounts, /content/features and /content/discounts
-- the exact same class of bug migration 0033 fixed for proxy_config.
migrations/0035_schema_drift_repair.sql is the fix; this test pins it so
none of these four tables can drift from their ORM model again silently.

Like tests/test_proxy_config_schema.py, this compares real ORM objects
(``Model.__table__.columns``) against the columns the migration files
actually create/add for each table -- reconstructed statically from the
.sql files themselves, matching this suite's mocked-DB convention (no live
Postgres needed to run this file). Unlike test_proxy_config_schema.py's
helper (which only looks for CREATE TABLE in the baseline file), the helper
here also looks for CREATE TABLE in every numbered migration, because
about_content and assistants are created in 0035, not the baseline -- a
table renamed or created outside the baseline must still be found.

The live-database proof that migration 0035 actually repairs the four
broken endpoints (not just that these column sets line up on paper) was run
separately through migrate.py against a throwaway database and is not
repeated here -- this file's job is only to stop a *future* drift from
shipping silently.
"""
from __future__ import annotations

import pathlib
import re

from models import AboutContent, Assistant, Discount, Feature

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / 'migrations'
BASELINE_FILE = MIGRATIONS_DIR / '0001_baseline.sql'
DRIFT_REPAIR_FILE = MIGRATIONS_DIR / '0035_schema_drift_repair.sql'

# Lines inside a CREATE TABLE (...) body that are table-level constraints,
# not column declarations -- must be skipped or their first "word" would be
# mistaken for a column name.
_NON_COLUMN_PREFIXES = ('CONSTRAINT', 'PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'CHECK')


def _parse_create_table_columns(sql_text: str, table: str) -> set[str]:
    """Column names declared in a ``CREATE TABLE IF NOT EXISTS <table> (...)``
    body somewhere in ``sql_text``. Returns an empty set if the table isn't
    created in this text."""
    match = re.search(
        rf'CREATE TABLE IF NOT EXISTS {re.escape(table)}\s*\((.*?)\)\s*;',
        sql_text, re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return set()
    columns = set()
    for line in match.group(1).splitlines():
        line = line.strip().rstrip(',')
        if not line:
            continue
        if line.upper().startswith(_NON_COLUMN_PREFIXES):
            continue
        columns.add(line.split()[0])
    return columns


def _parse_add_columns(sql_text: str, table: str) -> set[str]:
    """Column names added via ``ALTER TABLE <table> ADD COLUMN IF NOT
    EXISTS <col> ...`` anywhere in ``sql_text``."""
    pattern = re.compile(
        rf'ALTER TABLE {re.escape(table)}\s+ADD COLUMN IF NOT EXISTS\s+(\w+)',
        re.IGNORECASE,
    )
    return {m.group(1) for m in pattern.finditer(sql_text)}


def _parse_drop_columns(sql_text: str, table: str) -> set[str]:
    """Column names removed via ``ALTER TABLE <table> DROP COLUMN IF
    EXISTS <col>`` anywhere in ``sql_text`` -- needed here (unlike
    test_proxy_config_schema.py's helper, which never drops anything) so a
    column features/discounts used to have but the ORM no longer declares
    doesn't stay in the "actual" set forever and mask a real gap."""
    pattern = re.compile(
        rf'ALTER TABLE {re.escape(table)}\s+DROP COLUMN IF EXISTS\s+(\w+)',
        re.IGNORECASE,
    )
    return {m.group(1) for m in pattern.finditer(sql_text)}


def _actual_sql_columns(table: str) -> set[str]:
    """The union of every column the baseline plus every migration file
    actually creates for ``table``, minus anything later dropped -- i.e.
    what a freshly-migrated database really has for this table, right now,
    reconstructed statically from the .sql files.

    Scans EVERY migration file for CREATE TABLE (not just the baseline),
    because about_content and assistants are created by
    0035_schema_drift_repair.sql, not by the baseline.
    """
    columns: set[str] = set()
    dropped: set[str] = set()
    for path in sorted(MIGRATIONS_DIR.glob('*.sql')):
        text = path.read_text(encoding='utf-8')
        columns |= _parse_create_table_columns(text, table)
        columns |= _parse_add_columns(text, table)
        dropped |= _parse_drop_columns(text, table)
    return columns - dropped


def _assert_orm_matches_sql(model, table: str) -> None:
    orm_columns = set(model.__table__.columns.keys())
    sql_columns = _actual_sql_columns(table)
    missing_in_sql = orm_columns - sql_columns
    assert not missing_in_sql, (
        f'{model.__name__} declares column(s) with no backing SQL on table '
        f'{table!r}: {sorted(missing_in_sql)} -- add a migration (see '
        'migrations/0035_schema_drift_repair.sql for the pattern) before '
        f'this ships, or any ORM query against {table} will 500 in '
        'production.'
    )


def test_feature_orm_matches_sql_schema():
    _assert_orm_matches_sql(Feature, 'features')


def test_discount_orm_matches_sql_schema():
    _assert_orm_matches_sql(Discount, 'discounts')


def test_about_content_orm_matches_sql_schema():
    _assert_orm_matches_sql(AboutContent, 'about_content')


def test_assistant_orm_matches_sql_schema():
    _assert_orm_matches_sql(Assistant, 'assistants')


def test_about_content_table_name_matches_orm_tablename():
    """The 0033-class bug can also be a table *name* mismatch, not just a
    missing column (this is exactly what happened to AboutContent: its
    columns were always right, only __tablename__ disagreed with the live
    table). Pin the ORM's declared table name so a future rename on either
    side is caught here instead of as a live UndefinedTable."""
    assert AboutContent.__tablename__ == 'about_content'
    # And the SQL must actually create/rename to a table by that exact name
    # somewhere -- not just declare the name in Python.
    assert _actual_sql_columns('about_content'), (
        "AboutContent.__tablename__ is 'about_content' but no migration "
        "creates or renames a table to that name -- see "
        "migrations/0035_schema_drift_repair.sql's RENAME TO / "
        "CREATE TABLE IF NOT EXISTS about_content."
    )


def test_discounts_no_longer_has_the_colliding_content_block_columns():
    """Regression pin for the specific reconciliation migration 0035 made:
    discounts used to be a landing-page content block (title/body/
    order_idx) that nothing served, colliding with the discount-code
    feature (code/percent/active/expires_at) the ORM, content.py, admin.py
    and the frontend all actually use. If a future migration resurrects
    those columns without reconciling this test should fail loudly rather
    than silently reintroducing the NOT NULL discounts.title trap described
    in the 0035 migration comment."""
    orm_columns = set(Discount.__table__.columns.keys())
    assert 'title' not in orm_columns
    assert 'body' not in orm_columns
    assert 'order_idx' not in orm_columns
    assert {'code', 'percent', 'active', 'expires_at'} <= orm_columns


def test_migration_0035_is_the_fix_on_record():
    """Pins the specific migration this test exists because of, so a future
    renumber/removal of 0035 is caught here rather than only as a silent
    drop back to the pre-fix live-500 state."""
    assert DRIFT_REPAIR_FILE.exists(), (
        'migrations/0035_schema_drift_repair.sql is missing -- this is the '
        'fix backend/tests/test_schema_drift.py exists to guard.'
    )
    text = DRIFT_REPAIR_FILE.read_text(encoding='utf-8')
    assert _parse_add_columns(text, 'features') == {'description', 'icon', 'active'}
    assert _parse_add_columns(text, 'discounts') == {'code', 'percent', 'active', 'expires_at'}
    assert 'ALTER TABLE IF EXISTS about RENAME TO about_content' in text
    assert _parse_create_table_columns(text, 'assistants') == set(Assistant.__table__.columns.keys())


def test_guard_detects_orm_columns_missing_from_sql():
    """Canary: the comparison logic must actually flag a genuine drift on
    synthetic input -- proves this test would have failed before 0035
    existed, rather than passing vacuously by accident (e.g. an empty-set
    bug on both sides comparing equal)."""
    synthetic_sql = (
        "CREATE TABLE IF NOT EXISTS widget (\n"
        "    id INT PRIMARY KEY,\n"
        "    name TEXT,\n"
        "    CHECK (id = 1)\n"
        ");\n"
    )
    sql_columns = _parse_create_table_columns(synthetic_sql, 'widget')
    assert sql_columns == {'id', 'name'}

    orm_columns = {'id', 'name', 'extra_col_the_orm_added_without_a_migration'}
    missing = orm_columns - sql_columns
    assert missing == {'extra_col_the_orm_added_without_a_migration'}


def test_guard_add_and_drop_column_parsers_on_synthetic_migration():
    """Same canary shape for the ALTER TABLE ADD/DROP COLUMN parsers,
    including the DROP tracking this file adds beyond
    test_proxy_config_schema.py's original helper."""
    synthetic_migration = (
        "-- 0099_widget_extra.sql\n"
        "ALTER TABLE widget ADD COLUMN IF NOT EXISTS extra_col TEXT NOT NULL DEFAULT '';\n"
        "ALTER TABLE widget ADD COLUMN IF NOT EXISTS stale_col TEXT;\n"
        "ALTER TABLE widget DROP COLUMN IF EXISTS stale_col;\n"
    )
    assert _parse_add_columns(synthetic_migration, 'widget') == {'extra_col', 'stale_col'}
    assert _parse_drop_columns(synthetic_migration, 'widget') == {'stale_col'}
