"""One payment grants a package's quota exactly once.

An adversarial review of the entitlements feature found that
``grant_entitlement()`` was a bare INSERT with no unique constraint behind
it, so a replayed payment-gateway callback would grant a SECOND full quota
for a single payment. Measured on a throwaway copy of the production
database, before the fix: two calls with the same ``source_payment_id``
produced 2 rows totalling 1,000 requests for a 500-request package. After
the fix: 1 row, 500 requests, and the replay returns the entitlement that
already exists rather than None.

``handle_payment_callback()`` locks the payment row and rejects a replayed
callback before any grant is reached, so this is the second lock, not the
first -- deliberately, and consistent with payment_endpoints.py's Hermes
branch, which re-checks the order status even though that same callback
lock makes it "unnecessary". The caller that will grant entitlements on
the request path has not been written yet, so its care cannot be reviewed;
the database's cannot be forgotten.

── Why this is a TEXT guard and not a behavioural test ──────────────────
The behaviour needs a real Postgres engine: a unique index cannot be
modelled by the fake session in test_entitlements.py, and ON CONFLICT DO
NOTHING is a no-op without the index to conflict against. That real-engine
proof was run against a throwaway copy of production (both directions --
with the index 1 row, with the index dropped 2 rows) and is recorded above.
What this file protects is that BOTH HALVES stay in the tree, because
either half alone is useless:

  * the index without ON CONFLICT  -> IntegrityError on a replay
  * ON CONFLICT without the index  -> no conflict, two grants, silent loss

The canaries at the bottom exist because a guard that has been narrowed
until it matches nothing is worse than no guard at all -- this repo has
shipped exactly that before (see test_frontend_claims).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
MIGRATION = BACKEND / 'migrations' / '0034_package_entitlements.sql'
SERVICE = BACKEND / 'services' / 'entitlements.py'


def _strip_sql_comments(sql: str) -> str:
    """Drop ``--`` line comments so a guard can never be satisfied by prose.

    The migration file explains this index at length in comments; matching
    the explanation instead of the DDL would make every assertion here
    vacuous.
    """
    return '\n'.join(line.split('--', 1)[0] for line in sql.splitlines())


def _unique_index_ddl(sql: str) -> str | None:
    body = _strip_sql_comments(sql)
    for stmt in body.split(';'):
        if 'CREATE UNIQUE INDEX' in stmt.upper() and 'package_entitlement' in stmt:
            return ' '.join(stmt.split())
    return None


class TestMigrationHalf:
    def test_unique_index_exists(self):
        ddl = _unique_index_ddl(MIGRATION.read_text())
        assert ddl is not None, (
            'migration 0034 has no CREATE UNIQUE INDEX on package_entitlement. '
            'Without it a replayed payment callback grants a second quota.'
        )

    def test_index_is_keyed_on_package_and_payment(self):
        ddl = _unique_index_ddl(MIGRATION.read_text()) or ''
        cols = re.search(r'\(([^)]*)\)', ddl)
        assert cols is not None, f'could not read index columns from: {ddl}'
        listed = [c.strip() for c in cols.group(1).split(',')]
        assert listed == ['package_id', 'source_payment_id'], (
            f'index key changed to {listed}. Keying on source_payment_id alone '
            'would block a future bundle payment granting two different '
            'packages; dropping source_payment_id would block a user from '
            'ever buying the same package twice.'
        )

    def test_index_is_partial_so_admin_grants_are_not_deduped(self):
        ddl = _unique_index_ddl(MIGRATION.read_text()) or ''
        assert 'WHERE source_payment_id IS NOT NULL' in ddl, (
            'the unique index must be partial. An admin-issued grant carries '
            'source_payment_id NULL, and an admin may deliberately hand the '
            'same user the same package twice.'
        )


class TestServiceHalf:
    """Assert against the SQL OBJECTS, never against the file's text.

    A first draft of this class scanned ``entitlements.py`` for the string
    'ON CONFLICT DO NOTHING'. Deleting the clause from the real statement
    left the guard green, because the sentence explaining the clause in a
    nearby code comment still matched. Reading the statement the module
    actually built is the only version of this assertion that can fail.
    """

    def test_insert_tolerates_the_conflict(self):
        from services.entitlements import _INSERT_ENTITLEMENT_SQL

        sql = ' '.join(str(_INSERT_ENTITLEMENT_SQL).split())
        assert 'ON CONFLICT DO NOTHING' in sql, (
            "grant_entitlement()'s INSERT no longer carries ON CONFLICT DO "
            'NOTHING. With the unique index in place, a replayed callback now '
            f'raises IntegrityError instead of being absorbed. SQL is: {sql}'
        )

    def test_conflict_returns_the_existing_grant_not_none(self):
        from services.entitlements import _EXISTING_ENTITLEMENT_SQL

        sql = ' '.join(str(_EXISTING_ENTITLEMENT_SQL).split())
        # Returning None on a duplicate is indistinguishable from "this
        # package grants no quota", so a caller could report failure for a
        # payment that was in fact honoured.
        assert 'FROM package_entitlement' in sql, sql
        assert 'package_id = :package_id' in sql, sql
        assert 'source_payment_id = :source_payment_id' in sql, (
            'the read-back must match on the payment id too, or a replay '
            f'returns some other purchase of the same package. SQL is: {sql}'
        )

    def test_read_back_is_gated_on_a_real_payment_id(self):
        src = SERVICE.read_text()
        assert re.search(
            r'source_payment_id\s+is\s+not\s+None', src, re.IGNORECASE
        ), 'the duplicate read-back must be gated on a non-NULL payment id'


class TestGuardCanaries:
    """Prove the scanners above can actually fail.

    Each canary feeds doctored text through the same helper the real
    assertions use and asserts it is rejected. If a later narrowing turns a
    scanner into something that matches everything, these fail first.
    """

    def test_canary_missing_index_is_detected(self):
        assert _unique_index_ddl('CREATE TABLE package_entitlement (id BIGSERIAL);') is None

    def test_canary_index_in_a_comment_does_not_count(self):
        doctored = (
            '-- CREATE UNIQUE INDEX uq_x ON package_entitlement(package_id, '
            'source_payment_id) WHERE source_payment_id IS NOT NULL;\n'
            'CREATE TABLE package_entitlement (id BIGSERIAL);'
        )
        assert _unique_index_ddl(doctored) is None, (
            'a commented-out index satisfied the guard -- comment stripping is broken'
        )

    def test_canary_non_unique_index_does_not_count(self):
        doctored = 'CREATE INDEX idx_x ON package_entitlement(package_id, source_payment_id);'
        assert _unique_index_ddl(doctored) is None

    def test_canary_wrong_columns_are_detected(self):
        ddl = _unique_index_ddl(
            'CREATE UNIQUE INDEX uq_x ON package_entitlement(user_id) '
            'WHERE source_payment_id IS NOT NULL;'
        ) or ''
        cols = re.search(r'\(([^)]*)\)', ddl)
        assert cols is not None
        assert [c.strip() for c in cols.group(1).split(',')] != [
            'package_id', 'source_payment_id'
        ]

    def test_canary_prose_cannot_satisfy_the_service_half(self):
        # The bug this canary locks down: the first draft of
        # TestServiceHalf scanned the module's TEXT, and a code comment
        # mentioning the clause kept the guard green after the clause
        # itself was deleted. Reading the built statement cannot be fooled
        # that way -- prove the two really are different things.
        from services.entitlements import _INSERT_ENTITLEMENT_SQL

        assert 'ON CONFLICT DO NOTHING' in SERVICE.read_text(), (
            'precondition for this canary'
        )
        prose_only = SERVICE.read_text().count('ON CONFLICT DO NOTHING')
        in_statement = str(_INSERT_ENTITLEMENT_SQL).count('ON CONFLICT DO NOTHING')
        assert prose_only > in_statement, (
            'this canary assumes the phrase appears in a comment as well as '
            'in the statement; if that stops being true the canary is inert '
            'but the guard it protects is still sound'
        )
        assert in_statement == 1

    def test_canary_the_files_this_guard_reads_still_exist(self):
        # A renamed or moved file would make every assertion above pass
        # against an empty string on some future refactor.
        assert MIGRATION.is_file(), f'{MIGRATION} is gone -- this guard is now vacuous'
        assert SERVICE.is_file(), f'{SERVICE} is gone -- this guard is now vacuous'
        assert 'grant_entitlement' in SERVICE.read_text()


if __name__ == '__main__':  # pragma: no cover
    pytest.main([__file__, '-v'])
