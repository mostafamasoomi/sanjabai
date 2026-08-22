"""Tests for services/entitlements.py -- package request/token quotas.

No live Postgres is available (see tests/conftest.py), so these tests drive
services.entitlements against a small in-memory fake standing in for
``credit_packages`` and ``package_entitlement``. Every statement in
entitlements.py is a raw ``sqlalchemy.text()`` clause (there is no ORM
Table to introspect via ``.table.name`` the way test_billing_loss_paths.py
does for its ORM Update/Select statements), so the fake session dispatches
on a distinctive substring of the compiled SQL text instead.

The fake's dispatch logic for each query intentionally mirrors the WHERE
clause of the real SQL (active / not-expired / not-exhausted / ceiling
covers the estimate) so that these tests exercise the *contract* --
selection rules, atomicity, no-op semantics, grant-time copying -- the same
way a real Postgres row would enforce it. Migration syntax itself is
covered separately by test_migration_bind_params.py and (against a real
schema) test_migrations_real.py.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import services.entitlements as ent_mod


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _row(d: dict):
    """Mimic a SQLAlchemy Row well enough for `dict(row._mapping)`."""
    m = MagicMock()
    m._mapping = dict(d)
    return m


class _FakeEntitlementDB:
    """In-memory stand-in for the two tables entitlements.py touches."""

    def __init__(self):
        self.packages: dict[str, dict] = {}
        self.entitlements: dict[int, dict] = {}
        self._next_id = 1
        self.commits = 0

    def add_package(self, package_id: str, **cols) -> None:
        row = {
            'request_quota': None,
            'token_quota': None,
            'validity_days': None,
            'max_cost_per_request_toman': None,
        }
        row.update(cols)
        self.packages[package_id] = row

    def add_entitlement(self, **cols) -> int:
        eid = cols.pop('id', None) or self._next_id
        self._next_id = max(self._next_id, eid + 1)
        row = {
            'id': eid,
            'user_id': 1,
            'package_id': 'pkg',
            'requests_remaining': None,
            'tokens_remaining': None,
            'max_cost_per_request_toman': None,
            'expires_at': None,
            'active': True,
            'source_payment_id': None,
            'created_at': _utcnow(),
        }
        row.update(cols)
        self.entitlements[eid] = row
        return eid


class _FakeSession:
    """Dispatches services.entitlements' raw SQL against a _FakeEntitlementDB."""

    def __init__(self, db: _FakeEntitlementDB):
        self.db = db

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        params = params or {}
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []

        if 'FROM credit_packages WHERE id' in sql:
            pkg = self.db.packages.get(params['package_id'])
            result.fetchone.return_value = _row(pkg) if pkg is not None else None
            return result

        if sql.strip().startswith('INSERT INTO package_entitlement'):
            eid = self.db.add_entitlement(
                user_id=params['user_id'],
                package_id=params['package_id'],
                requests_remaining=params['requests_remaining'],
                tokens_remaining=params['tokens_remaining'],
                max_cost_per_request_toman=params['max_cost_per_request_toman'],
                expires_at=params['expires_at'],
                active=True,
                source_payment_id=params['source_payment_id'],
            )
            result.fetchone.return_value = _row(self.db.entitlements[eid])
            return result

        if sql.strip().startswith('UPDATE package_entitlement'):
            row = self.db.entitlements.get(params['id'])
            ok = row is not None
            now = _utcnow()
            if ok and not row['active']:
                ok = False
            if ok and row['expires_at'] is not None and row['expires_at'] <= now:
                ok = False
            if ok and row['requests_remaining'] is not None and row['requests_remaining'] < params['requests']:
                ok = False
            if ok and row['tokens_remaining'] is not None and row['tokens_remaining'] < params['tokens']:
                ok = False
            if ok:
                if row['requests_remaining'] is not None:
                    row['requests_remaining'] -= params['requests']
                if row['tokens_remaining'] is not None:
                    row['tokens_remaining'] -= params['tokens']
                result.fetchone.return_value = _row({'id': row['id']})
            return result

        if 'max_cost_per_request_toman >=' in sql:
            # find_covering_entitlement
            uid = params['uid']
            est = params['est_cost_toman']
            now = _utcnow()
            candidates = [
                r for r in self.db.entitlements.values()
                if r['user_id'] == uid
                and r['active']
                and (r['expires_at'] is None or r['expires_at'] > now)
                and (r['requests_remaining'] is None or r['requests_remaining'] > 0)
                and (r['tokens_remaining'] is None or r['tokens_remaining'] > 0)
                and r['max_cost_per_request_toman'] is not None
                and r['max_cost_per_request_toman'] >= est
            ]
            candidates.sort(key=lambda r: (r['expires_at'] is None, r['expires_at'] or datetime.max, r['id']))
            if candidates:
                result.fetchone.return_value = _row(candidates[0])
            return result

        if 'FROM package_entitlement' in sql:
            # list_entitlements
            uid = params['uid']
            now = _utcnow()
            rows = [
                r for r in self.db.entitlements.values()
                if r['user_id'] == uid
                and r['active']
                and (r['expires_at'] is None or r['expires_at'] > now)
            ]
            rows.sort(key=lambda r: r['created_at'], reverse=True)
            result.fetchall.return_value = [_row(r) for r in rows]
            return result

        raise AssertionError(f'unrecognized SQL in fake session: {sql}')

    async def commit(self):
        self.db.commits += 1


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def db():
    return _FakeEntitlementDB()


@pytest.fixture
def patched(monkeypatch, db):
    """Point services.entitlements.async_session at the fake DB."""
    monkeypatch.setattr(ent_mod, 'async_session', lambda: _Ctx(_FakeSession(db)))
    return db


# ── find_covering_entitlement ──────────────────────────────────────────────

class TestFindCoveringEntitlement:
    @pytest.mark.asyncio
    async def test_ceiling_excludes_over_budget_request(self, patched):
        patched.add_entitlement(
            user_id=1, requests_remaining=10, max_cost_per_request_toman=1000,
        )
        assert await ent_mod.find_covering_entitlement(1, 1500) is None
        found = await ent_mod.find_covering_entitlement(1, 900)
        assert found is not None
        assert found['max_cost_per_request_toman'] == 1000

    @pytest.mark.asyncio
    async def test_null_ceiling_covers_nothing(self, patched):
        """A NULL ceiling is fail-closed, never treated as 'unlimited'."""
        patched.add_entitlement(
            user_id=1, requests_remaining=10, max_cost_per_request_toman=None,
        )
        assert await ent_mod.find_covering_entitlement(1, 1) is None

    @pytest.mark.asyncio
    async def test_expired_inactive_and_exhausted_are_skipped(self, patched):
        now = _utcnow()
        patched.add_entitlement(
            id=1, user_id=1, requests_remaining=10, max_cost_per_request_toman=1000,
            expires_at=now - timedelta(days=1),  # expired
        )
        patched.add_entitlement(
            id=2, user_id=1, requests_remaining=10, max_cost_per_request_toman=1000,
            active=False,  # inactive
        )
        patched.add_entitlement(
            id=3, user_id=1, requests_remaining=0, max_cost_per_request_toman=1000,
        )  # exhausted (requests)
        patched.add_entitlement(
            id=4, user_id=1, requests_remaining=10, tokens_remaining=0,
            max_cost_per_request_toman=1000,
        )  # exhausted (tokens)
        assert await ent_mod.find_covering_entitlement(1, 500) is None

        patched.add_entitlement(
            id=5, user_id=1, requests_remaining=10, max_cost_per_request_toman=1000,
        )  # the one valid entitlement
        found = await ent_mod.find_covering_entitlement(1, 500)
        assert found is not None
        assert found['id'] == 5

    @pytest.mark.asyncio
    async def test_soonest_expiry_is_preferred(self, patched):
        now = _utcnow()
        patched.add_entitlement(
            id=1, user_id=1, requests_remaining=10, max_cost_per_request_toman=1000,
            expires_at=None,  # never expires -- least urgent
        )
        patched.add_entitlement(
            id=2, user_id=1, requests_remaining=10, max_cost_per_request_toman=1000,
            expires_at=now + timedelta(days=10),
        )
        patched.add_entitlement(
            id=3, user_id=1, requests_remaining=10, max_cost_per_request_toman=1000,
            expires_at=now + timedelta(days=1),  # soonest -- must win
        )
        found = await ent_mod.find_covering_entitlement(1, 500)
        assert found is not None
        assert found['id'] == 3

    @pytest.mark.asyncio
    async def test_no_entitlements_returns_none(self, patched):
        assert await ent_mod.find_covering_entitlement(1, 100) is None

    @pytest.mark.asyncio
    async def test_other_users_entitlement_is_not_selected(self, patched):
        patched.add_entitlement(user_id=2, requests_remaining=10, max_cost_per_request_toman=1000)
        assert await ent_mod.find_covering_entitlement(1, 100) is None


# ── consume_entitlement ─────────────────────────────────────────────────────

class TestConsumeEntitlement:
    @pytest.mark.asyncio
    async def test_consume_decrements_only_metered_dimensions(self, patched):
        eid = patched.add_entitlement(requests_remaining=5, tokens_remaining=None)
        ok = await ent_mod.consume_entitlement(eid, requests=1, tokens=100)
        assert ok is True
        row = patched.entitlements[eid]
        assert row['requests_remaining'] == 4
        assert row['tokens_remaining'] is None  # stays NULL, never drifts

    @pytest.mark.asyncio
    async def test_consume_fails_when_insufficient_remaining(self, patched):
        eid = patched.add_entitlement(requests_remaining=1)
        ok = await ent_mod.consume_entitlement(eid, requests=2)
        assert ok is False
        assert patched.entitlements[eid]['requests_remaining'] == 1  # untouched

    @pytest.mark.asyncio
    async def test_consume_fails_on_inactive_entitlement(self, patched):
        eid = patched.add_entitlement(requests_remaining=10, active=False)
        assert await ent_mod.consume_entitlement(eid, requests=1) is False
        assert patched.entitlements[eid]['requests_remaining'] == 10

    @pytest.mark.asyncio
    async def test_consume_fails_on_expired_entitlement(self, patched):
        eid = patched.add_entitlement(
            requests_remaining=10, expires_at=_utcnow() - timedelta(minutes=1),
        )
        assert await ent_mod.consume_entitlement(eid, requests=1) is False
        assert patched.entitlements[eid]['requests_remaining'] == 10

    @pytest.mark.asyncio
    async def test_consume_missing_entitlement_returns_false(self, patched):
        assert await ent_mod.consume_entitlement(999, requests=1) is False

    @pytest.mark.asyncio
    async def test_concurrent_consumption_cannot_drive_counter_below_zero(self, patched):
        """Two racing consumers, only one unit left: exactly one must win,
        and the counter must land at exactly zero, never negative."""
        eid = patched.add_entitlement(requests_remaining=1)
        results = await asyncio.gather(
            ent_mod.consume_entitlement(eid, requests=1),
            ent_mod.consume_entitlement(eid, requests=1),
        )
        assert sorted(results) == [False, True]
        assert patched.entitlements[eid]['requests_remaining'] == 0

    @pytest.mark.asyncio
    async def test_concurrent_token_consumption_cannot_go_negative(self, patched):
        eid = patched.add_entitlement(requests_remaining=None, tokens_remaining=100)
        results = await asyncio.gather(
            ent_mod.consume_entitlement(eid, requests=0, tokens=60),
            ent_mod.consume_entitlement(eid, requests=0, tokens=60),
        )
        assert sorted(results) == [False, True]
        assert patched.entitlements[eid]['tokens_remaining'] == 40


# ── grant_entitlement ────────────────────────────────────────────────────────

class TestGrantEntitlement:
    @pytest.mark.asyncio
    async def test_quota_less_package_is_a_clean_noop(self, patched):
        patched.add_package('starter-credits')  # all four columns NULL
        result = await ent_mod.grant_entitlement(1, 'starter-credits')
        assert result is None
        assert patched.entitlements == {}

    @pytest.mark.asyncio
    async def test_unknown_package_returns_none(self, patched):
        assert await ent_mod.grant_entitlement(1, 'no-such-package') is None
        assert patched.entitlements == {}

    @pytest.mark.asyncio
    async def test_grant_copies_quota_and_computes_expiry(self, patched):
        patched.add_package(
            'pro-quota', request_quota=500, token_quota=None,
            validity_days=30, max_cost_per_request_toman=2000,
        )
        before = _utcnow()
        result = await ent_mod.grant_entitlement(1, 'pro-quota', source_payment_id='pay-1')
        after = _utcnow()

        assert result is not None
        assert result['requests_remaining'] == 500
        assert result['tokens_remaining'] is None
        assert result['max_cost_per_request_toman'] == 2000
        assert result['source_payment_id'] == 'pay-1'
        assert before + timedelta(days=30) <= result['expires_at'] <= after + timedelta(days=30)

    @pytest.mark.asyncio
    async def test_grant_with_no_validity_days_never_expires(self, patched):
        patched.add_package('forever-quota', request_quota=100, max_cost_per_request_toman=500)
        result = await ent_mod.grant_entitlement(1, 'forever-quota')
        assert result is not None
        assert result['expires_at'] is None

    @pytest.mark.asyncio
    async def test_later_package_edit_does_not_change_already_granted_entitlement(self, patched):
        """max_cost_per_request_toman (and quota) are copied at grant time --
        a later admin edit to the package must not retroactively change what
        a user already bought."""
        patched.add_package(
            'edited-later', request_quota=500, max_cost_per_request_toman=1000,
        )
        result = await ent_mod.grant_entitlement(1, 'edited-later')
        eid = result['id']

        # Owner edits the package after the purchase.
        patched.packages['edited-later']['request_quota'] = 999999
        patched.packages['edited-later']['max_cost_per_request_toman'] = 1

        row = patched.entitlements[eid]
        assert row['requests_remaining'] == 500
        assert row['max_cost_per_request_toman'] == 1000

    @pytest.mark.asyncio
    async def test_grant_creates_a_row_consume_can_immediately_use(self, patched):
        patched.add_package('both-quota', request_quota=10, token_quota=1000, max_cost_per_request_toman=5000)
        result = await ent_mod.grant_entitlement(1, 'both-quota')
        eid = result['id']
        found = await ent_mod.find_covering_entitlement(1, 4000)
        assert found is not None and found['id'] == eid
        assert await ent_mod.consume_entitlement(eid, requests=1, tokens=100) is True
        row = patched.entitlements[eid]
        assert row['requests_remaining'] == 9
        assert row['tokens_remaining'] == 900


# ── list_entitlements ────────────────────────────────────────────────────────

class TestListEntitlements:
    @pytest.mark.asyncio
    async def test_lists_only_active_nonexpired_for_the_user(self, patched):
        now = _utcnow()
        patched.add_entitlement(id=1, user_id=1, requests_remaining=5)  # keep
        patched.add_entitlement(id=2, user_id=1, active=False)  # drop: inactive
        patched.add_entitlement(id=3, user_id=1, expires_at=now - timedelta(days=1))  # drop: expired
        patched.add_entitlement(id=4, user_id=2, requests_remaining=5)  # drop: other user

        result = await ent_mod.list_entitlements(1)
        assert [r['id'] for r in result] == [1]

    @pytest.mark.asyncio
    async def test_exhausted_but_active_entitlement_still_shown(self, patched):
        """Display should not hide a fully-used package -- only the request
        path's find_covering_entitlement excludes exhausted entitlements."""
        patched.add_entitlement(id=1, user_id=1, requests_remaining=0)
        result = await ent_mod.list_entitlements(1)
        assert [r['id'] for r in result] == [1]

    @pytest.mark.asyncio
    async def test_empty_for_user_with_no_entitlements(self, patched):
        assert await ent_mod.list_entitlements(1) == []
