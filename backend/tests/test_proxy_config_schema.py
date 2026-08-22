"""Schema-drift guard for ProxyConfig (backend/models.py).

Before migration 0033, the ORM model declared five columns
(id, proxy_url, proxy_type, active, default_model, updated_at) while the
live table -- created by migrations/0001_baseline.sql and never touched
again -- only ever had three (id, proxy_url, updated_at). Every SELECT the
ORM issued (``ProxyConfig.__table__.select()``, used by content.py's
``GET /org/default-model`` and every ``/admin/proxy*`` route in admin.py)
therefore 500'd in production with:

    column proxy_config.proxy_type does not exist

This went unnoticed because the Next.js proxy in front of the API swallows
that 500 and returns 200 with an empty body.

This test parses (statically, no live database) the ORM's declared columns
for ProxyConfig and compares them against the union of what the baseline
SQL plus every migration file actually creates for the ``proxy_config``
table, so this exact class of drift cannot recur silently -- a new column
added to the ORM without a matching migration fails this test instead of
waiting to be discovered as a live 500.
"""
from __future__ import annotations

import pathlib
import re

from models import ProxyConfig

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / 'migrations'
BASELINE_FILE = MIGRATIONS_DIR / '0001_baseline.sql'

# Lines inside a CREATE TABLE (...) body that are table-level constraints,
# not column declarations -- must be skipped or their first "word" would be
# mistaken for a column name.
_NON_COLUMN_PREFIXES = ('CONSTRAINT', 'PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'CHECK')


def _parse_create_table_columns(sql_text: str, table: str) -> set[str]:
    """Column names declared in a ``CREATE TABLE IF NOT EXISTS <table> (...)``
    body somewhere in ``sql_text``. Returns an empty set if the table isn't
    created in this text (the baseline is expected to be the only place
    that creates ``proxy_config``, but this stays generic on purpose so the
    canary test below can exercise it against synthetic input)."""
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


def _actual_sql_columns(table: str) -> set[str]:
    """The union of every column the baseline plus every migration file
    actually creates for ``table`` -- i.e. what a freshly-migrated database
    really has, reconstructed statically from the .sql files themselves
    (no live Postgres needed, matching this suite's mocked-DB convention)."""
    columns = _parse_create_table_columns(BASELINE_FILE.read_text(encoding='utf-8'), table)
    for path in sorted(MIGRATIONS_DIR.glob('*.sql')):
        columns |= _parse_add_columns(path.read_text(encoding='utf-8'), table)
    return columns


def test_proxy_config_orm_matches_sql_schema():
    """Every column ProxyConfig declares must be backed by real SQL.

    A mismatch here means ``ProxyConfig.__table__.select()`` (and any other
    ORM query touching the missing column) will 500 the moment it runs
    against a real database -- exactly the bug migration 0033 fixed.
    """
    orm_columns = set(ProxyConfig.__table__.columns.keys())
    sql_columns = _actual_sql_columns('proxy_config')

    missing_in_sql = orm_columns - sql_columns
    assert not missing_in_sql, (
        f'ProxyConfig declares column(s) with no backing SQL: {sorted(missing_in_sql)} -- '
        'add a migration (see migrations/0033_proxy_config_columns.sql for the pattern) '
        'before this ships, or every ORM SELECT against proxy_config will 500 in production.'
    )


def test_migration_0033_is_the_fix_on_record():
    """Pins the specific migration this test exists because of, so a future
    renumber/removal of 0033 is caught here rather than only as a silent
    drop back to the pre-fix live-500 state."""
    added = _parse_add_columns(
        (MIGRATIONS_DIR / '0033_proxy_config_columns.sql').read_text(encoding='utf-8'),
        'proxy_config',
    )
    assert added == {'proxy_type', 'active', 'default_model'}


def test_guard_detects_orm_columns_missing_from_sql():
    """Canary: the comparison logic must actually flag a genuine drift on
    synthetic input -- proves this test would have failed before 0033
    existed, rather than passing vacuously by accident (e.g. an empty-set
    bug on both sides comparing equal)."""
    synthetic_baseline = (
        "CREATE TABLE IF NOT EXISTS widget (\n"
        "    id INT PRIMARY KEY,\n"
        "    name TEXT,\n"
        "    CHECK (id = 1)\n"
        ");\n"
    )
    sql_columns = _parse_create_table_columns(synthetic_baseline, 'widget')
    assert sql_columns == {'id', 'name'}

    orm_columns = {'id', 'name', 'extra_col_the_orm_added_without_a_migration'}
    missing = orm_columns - sql_columns
    assert missing == {'extra_col_the_orm_added_without_a_migration'}


def test_guard_add_column_parser_on_synthetic_migration():
    """Same canary shape for the ALTER TABLE ADD COLUMN parser."""
    synthetic_migration = (
        "-- 0099_widget_extra.sql\n"
        "ALTER TABLE widget ADD COLUMN IF NOT EXISTS extra_col_the_orm_added_without_a_migration TEXT NOT NULL DEFAULT '';\n"
    )
    assert _parse_add_columns(synthetic_migration, 'widget') == {
        'extra_col_the_orm_added_without_a_migration'
    }
