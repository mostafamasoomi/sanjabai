"""Behaviour tests for the aggregate per-user message quota
(services/user_quota.py): limit resolution, boundaries, windowing, fail-open,
and status reporting.

Split out of the original tests/test_user_quota.py (which grew past the
500-line cap) -- the SQL-contract, wiring, and end-to-end HTTP tests now live
in tests/test_user_quota_wiring.py, and the fakes both files share live in
tests/_user_quota_fakes.py. See that module's docstring for why the fake
session re-implements the real WHERE clause in Python rather than returning
a canned row.

has_paid()/has_balance() are NOT stubbed for the default-tier tests: with no
database bound (the default in this environment) both fall through to False
on their own, which is precisely the "never paid, no balance" user. The
paid-user tests stub them explicitly on the user_quota module, because
user_quota does `from services.free_tier import has_paid` -- a module-level
binding, so patching services.free_tier.has_paid would not reach it.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from services import user_quota
from tests._user_quota_fakes import FakeRedis, _FakePackageDB, _session_factory, _utcnow


def _run(coro):
    return asyncio.run(coro)


# ── fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr(user_quota, 'rds', fr)
    return fr


@pytest.fixture
def pkg_db(monkeypatch):
    db = _FakePackageDB()
    monkeypatch.setattr(user_quota, 'async_session', _session_factory(db))
    return db


def _pkg_user(pkg_db, uid: int, quota: int) -> None:
    """Give ``uid`` an active package granting ``quota`` requests/window.
    Since the free/paid/balance tiers are all exempt from THIS gate now (the
    free tier moved to services/free_tier.py), a package holder is the only
    user this gate actually caps -- so the boundary and window tests below use
    one."""
    pkg_db.add_package(f'pkg{uid}', rate_limit_per_window=quota)
    pkg_db.add_entitlement(uid, f'pkg{uid}')


# ── 1. limit resolution ──────────────────────────────────────────────────

class TestResolveLimit:
    def test_no_package_is_exempt(self, fake_redis, pkg_db):
        """Never paid, no balance, no package = the free tier, which is now
        handled entirely by services/free_tier.py. THIS gate exempts it."""
        assert _run(user_quota.resolve_limit(101)) == (None, user_quota.SOURCE_EXEMPT)

    def test_active_package_quota_wins(self, fake_redis, pkg_db):
        pkg_db.add_package('pro', rate_limit_per_window=200)
        pkg_db.add_entitlement(102, 'pro')
        assert _run(user_quota.resolve_limit(102)) == (200, user_quota.SOURCE_PACKAGE)

    def test_highest_package_wins(self, fake_redis, pkg_db):
        pkg_db.add_package('small', rate_limit_per_window=80)
        pkg_db.add_package('big', rate_limit_per_window=500)
        pkg_db.add_entitlement(104, 'small')
        pkg_db.add_entitlement(104, 'big')
        assert _run(user_quota.resolve_limit(104))[0] == 500

    def test_expired_package_is_exempt(self, fake_redis, pkg_db):
        pkg_db.add_package('pro', rate_limit_per_window=200)
        pkg_db.add_entitlement(105, 'pro', expires_at=_utcnow() - timedelta(days=1))
        assert _run(user_quota.resolve_limit(105)) == (None, user_quota.SOURCE_EXEMPT)

    def test_inactive_package_is_exempt(self, fake_redis, pkg_db):
        pkg_db.add_package('pro', rate_limit_per_window=200)
        pkg_db.add_entitlement(106, 'pro', active=False)
        assert _run(user_quota.resolve_limit(106)) == (None, user_quota.SOURCE_EXEMPT)

    def test_null_rate_limit_is_exempt_not_unlimited(self, fake_redis, pkg_db):
        """Every live package today has rate_limit_per_window NULL. NULL
        must mean 'grants no window quota' -> fall through to exempt, never
        'no limit' read as unlimited-but-counted."""
        pkg_db.add_package('starter-credits', rate_limit_per_window=None)
        pkg_db.add_entitlement(107, 'starter-credits')
        assert _run(user_quota.resolve_limit(107)) == (None, user_quota.SOURCE_EXEMPT)


# ── 2. boundaries (a PACKAGE user is the only one this gate caps) ─────────

class TestBoundary:
    def test_package_user_allowed_just_below_limit(self, fake_redis, pkg_db):
        _pkg_user(pkg_db, 201, 50)
        fake_redis.seed(201, 49)
        assert _run(user_quota.check_and_consume(201)) is None
        assert fake_redis.used(201) == 50

    def test_package_user_blocked_at_limit(self, fake_redis, pkg_db):
        _pkg_user(pkg_db, 202, 50)
        fake_redis.seed(202, 50, ttl=777)
        gate = _run(user_quota.check_and_consume(202))
        assert gate is not None
        assert gate['limit'] == 50
        assert gate['used'] == 50
        assert gate['source'] == user_quota.SOURCE_PACKAGE
        assert gate['retry_after_seconds'] == 777

    def test_rejection_consumes_nothing(self, fake_redis, pkg_db):
        _pkg_user(pkg_db, 203, 50)
        fake_redis.seed(203, 50)
        _run(user_quota.check_and_consume(203))
        assert fake_redis.used(203) == 50, "a blocked request must not INCR"

    def test_n_messages_then_the_next_is_blocked(self, fake_redis, pkg_db):
        uid = 204
        _pkg_user(pkg_db, uid, 50)
        for i in range(50):
            assert _run(user_quota.check_and_consume(uid)) is None, f"message {i + 1}"
        assert _run(user_quota.check_and_consume(uid)) is not None

    def test_bigger_package_allows_more(self, fake_redis, pkg_db):
        _pkg_user(pkg_db, 206, 200)
        fake_redis.seed(206, 200, ttl=60)
        gate = _run(user_quota.check_and_consume(206))
        assert gate is not None
        assert gate['limit'] == 200
        assert gate['source'] == user_quota.SOURCE_PACKAGE
        assert gate['retry_after_seconds'] == 60

    def test_no_package_user_is_never_counted(self, fake_redis, pkg_db):
        """An exempt (free/paid/balance) user's window is never touched here --
        the free tier's counters live in services/free_tier.py."""
        for _ in range(55):
            assert _run(user_quota.check_and_consume(301)) is None
        assert fake_redis.used(301) == 0

    def test_aggregate_not_per_model(self, fake_redis, pkg_db):
        """The whole point of this gate: one counter for the user, whatever
        model the message went to."""
        uid = 302
        _pkg_user(pkg_db, uid, 50)
        for _ in range(50):
            assert _run(user_quota.check_and_consume(uid)) is None
        assert fake_redis.used(uid) == 50
        assert len([k for k in fake_redis.store if k.startswith('userquota:')]) == 1

    def test_cost_greater_than_one_cannot_straddle_the_limit(self, fake_redis, pkg_db):
        _pkg_user(pkg_db, 303, 50)
        fake_redis.seed(303, 49)
        gate = _run(user_quota.check_and_consume(303, cost=2))
        assert gate is not None, "49 + 2 > 50 must be refused, not clamped"
        assert fake_redis.used(303) == 49


# ── 3. windowing ─────────────────────────────────────────────────────────

class TestWindow:
    def test_first_message_anchors_the_five_hour_window(self, fake_redis, pkg_db):
        _pkg_user(pkg_db, 401, 50)
        assert _run(user_quota.check_and_consume(401)) is None
        assert fake_redis.ttls[user_quota._msg_key(401)] == user_quota.WINDOW_SECONDS
        assert user_quota.WINDOW_SECONDS == 18000

    def test_expiry_resets_the_allowance(self, fake_redis, pkg_db):
        uid = 402
        _pkg_user(pkg_db, uid, 50)
        fake_redis.seed(uid, 50)
        assert _run(user_quota.check_and_consume(uid)) is not None
        fake_redis.expire_now(uid)
        assert _run(user_quota.check_and_consume(uid)) is None

    def test_at_cap_with_no_ttl_fails_open_rather_than_trapping(self, fake_redis, pkg_db):
        uid = 403
        _pkg_user(pkg_db, uid, 50)
        fake_redis.store[user_quota._msg_key(uid)] = '50'
        # no TTL entry -> ttl() returns -1, a bucket that would never reset
        assert _run(user_quota.check_and_consume(uid)) is None

    def test_a_key_that_lost_its_ttl_gets_one_back(self, fake_redis, pkg_db):
        uid = 404
        _pkg_user(pkg_db, uid, 50)
        fake_redis.store[user_quota._msg_key(uid)] = '3'
        assert _run(user_quota.check_and_consume(uid)) is None
        assert fake_redis.ttls[user_quota._msg_key(uid)] == user_quota.WINDOW_SECONDS


# ── 4. fail-open ─────────────────────────────────────────────────────────

class TestFailOpen:
    def test_redis_outage_allows_the_request(self, fake_redis, pkg_db):
        _pkg_user(pkg_db, 501, 50)
        fake_redis.seed(501, 999)
        fake_redis.fail = True
        assert _run(user_quota.check_and_consume(501)) is None

    def test_database_outage_is_exempt_not_a_crash(self, fake_redis, pkg_db):
        """A DB error must not raise. The package lookup returns None, so the
        user resolves to exempt (uncapped) rather than trapping them -- money
        is still guarded by BillingService.reserve regardless."""
        pkg_db.fail = True
        assert _run(user_quota.resolve_limit(502)) == (None, user_quota.SOURCE_EXEMPT)
        fake_redis.seed(502, 999)
        assert _run(user_quota.check_and_consume(502)) is None

    def test_database_outage_on_the_whole_gate_still_serves(self, fake_redis, pkg_db):
        pkg_db.fail = True
        assert _run(user_quota.check_and_consume(503)) is None

    def test_package_lookup_error_returns_none_not_raise(self, fake_redis, pkg_db):
        pkg_db.fail = True
        assert _run(user_quota.package_window_limit(504)) is None

    def test_garbage_counter_value_fails_open(self, fake_redis, pkg_db):
        _pkg_user(pkg_db, 505, 50)
        fake_redis.store[user_quota._msg_key(505)] = 'not-a-number'
        assert _run(user_quota.check_and_consume(505)) is None


# ── 5. status ────────────────────────────────────────────────────────────

class TestStatus:
    def test_status_reports_used_and_remaining_without_consuming(self, fake_redis, pkg_db):
        _pkg_user(pkg_db, 601, 50)
        fake_redis.seed(601, 12, ttl=900)
        st = _run(user_quota.get_status(601))
        assert st['limited'] is True
        assert st['limit'] == 50
        assert st['used'] == 12
        assert st['remaining'] == 38
        assert st['reset_in_seconds'] == 900
        assert fake_redis.used(601) == 12

    def test_status_for_an_exempt_user(self, fake_redis, pkg_db):
        # no package -> exempt
        st = _run(user_quota.get_status(602))
        assert st['limited'] is False
        assert st['limit'] is None
