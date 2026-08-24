"""Tests for the aggregate per-user message quota (services/user_quota.py).

Two kinds of check, deliberately:

1. BEHAVIOUR, against an in-memory fake Redis and a fake session, in the
   same spirit as tests/test_free_tier.py and tests/test_entitlements.py.
   The fake session does NOT hand back a canned fetchall(): it evaluates the
   real predicate (active / not expired / request_quota IS NOT NULL AND > 0
   / MAX across packages) against in-memory rows, so a test that says "the
   expired package must not count" is actually exercising that rule rather
   than a hardcoded answer.

2. SQL CONTRACT, asserting the literal clause text of _PACKAGE_LIMIT_SQL --
   following tests/test_entitlements_sql_contract.py and for exactly the
   reason its docstring gives: there is no live Postgres here (conftest.py
   mocks asyncpg at import time), so a fake that re-implements the WHERE
   clause in Python would keep enforcing the OLD rule even if someone
   silently deleted that clause from the real SQL. The Python fake proves
   the semantics are right; the text assertions prove the shipped SQL still
   says so.

has_paid()/has_balance() are NOT stubbed for the default-tier tests: with no
database bound (the default in this environment) both fall through to False
on their own, which is precisely the "never paid, no balance" user. The
paid-user tests stub them explicitly on the user_quota module, because
user_quota does `from services.free_tier import has_paid` -- a module-level
binding, so patching services.free_tier.has_paid would not reach it.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from services import free_tier, user_quota


def _run(coro):
    return asyncio.run(coro)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── fakes ────────────────────────────────────────────────────────────────

class FakeRedis:
    """Exactly the commands services.user_quota issues: get, ttl, incrby,
    expire. TTLs do not count down with wall-clock time; ``expire_now``
    simulates a window running out."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.fail = False

    def _check(self):
        if self.fail:
            raise ConnectionError("simulated redis outage")

    async def get(self, key):
        self._check()
        return self.store.get(key)

    async def incrby(self, key, amount):
        self._check()
        cur = int(self.store.get(key, '0')) + int(amount)
        self.store[key] = str(cur)
        return cur

    async def expire(self, key, seconds):
        self._check()
        if key in self.store:
            self.ttls[key] = int(seconds)
            return True
        return False

    async def ttl(self, key):
        self._check()
        if key not in self.store:
            return -2
        return self.ttls.get(key, -1)

    # ── test-only helpers ──
    def seed(self, uid: int, used: int, ttl: int = 1234):
        self.store[user_quota._msg_key(uid)] = str(used)
        self.ttls[user_quota._msg_key(uid)] = ttl

    def used(self, uid: int) -> int:
        return int(self.store.get(user_quota._msg_key(uid), '0'))

    def expire_now(self, uid: int):
        self.store.pop(user_quota._msg_key(uid), None)
        self.ttls.pop(user_quota._msg_key(uid), None)


def _row(d: dict):
    m = MagicMock()
    m._mapping = dict(d)
    return m


class _FakePackageDB:
    """In-memory stand-in for package_entitlement JOIN credit_packages."""

    def __init__(self):
        self.packages: dict[str, dict] = {}
        self.entitlements: list[dict] = []
        self.fail = False

    def add_package(self, package_id: str, request_quota=None):
        self.packages[package_id] = {'id': package_id, 'request_quota': request_quota}

    def add_entitlement(self, uid: int, package_id: str, *, active=True, expires_at=None):
        self.entitlements.append({
            'user_id': uid, 'package_id': package_id,
            'active': active, 'expires_at': expires_at,
        })

    def max_request_quota(self, uid: int):
        """The real WHERE clause, re-implemented -- see module docstring for
        why this is paired with the SQL-text assertions below."""
        now = _utcnow()
        best = None
        for e in self.entitlements:
            if e['user_id'] != uid:
                continue
            if not e['active']:
                continue
            if e['expires_at'] is not None and e['expires_at'] <= now:
                continue
            pkg = self.packages.get(e['package_id'])
            if pkg is None:
                continue  # the JOIN drops it
            q = pkg['request_quota']
            if q is None or q <= 0:
                continue
            best = q if best is None else max(best, q)
        return best


class _FakeSession:
    def __init__(self, db: _FakePackageDB):
        self.db = db

    async def execute(self, stmt, params=None):
        if self.db.fail:
            raise RuntimeError("simulated database outage")
        params = params or {}
        sql = str(stmt)
        result = MagicMock()
        result.fetchone.return_value = None
        if 'FROM package_entitlement pe' in sql:
            result.fetchone.return_value = _row(
                {'limit_value': self.db.max_request_quota(params['uid'])}
            )
        return result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _session_factory(db: _FakePackageDB):
    def factory():
        return _FakeSession(db)
    return factory


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


def _stub_paid(monkeypatch, paid=False, balance=False):
    async def _paid(uid):
        return paid

    async def _bal(uid):
        return balance

    monkeypatch.setattr(user_quota, 'has_paid', _paid)
    monkeypatch.setattr(user_quota, 'has_balance', _bal)


# ── 1. limit resolution ──────────────────────────────────────────────────

class TestResolveLimit:
    def test_no_package_no_payment_gets_the_default(self, fake_redis, pkg_db):
        limit, source = _run(user_quota.resolve_limit(101))
        assert limit == user_quota.DEFAULT_LIMIT
        assert source == user_quota.SOURCE_DEFAULT

    def test_active_package_quota_wins(self, fake_redis, pkg_db, monkeypatch):
        _stub_paid(monkeypatch, paid=True)  # a package buyer HAS paid
        pkg_db.add_package('pro', request_quota=200)
        pkg_db.add_entitlement(102, 'pro')
        limit, source = _run(user_quota.resolve_limit(102))
        assert (limit, source) == (200, user_quota.SOURCE_PACKAGE)

    def test_package_is_resolved_before_the_paid_exemption(self, fake_redis, pkg_db, monkeypatch):
        """If has_paid() were consulted first, every package's request_quota
        would be unreachable dead code -- a package buyer has paid."""
        _stub_paid(monkeypatch, paid=True, balance=True)
        pkg_db.add_package('pro', request_quota=200)
        pkg_db.add_entitlement(103, 'pro')
        assert _run(user_quota.resolve_limit(103)) == (200, user_quota.SOURCE_PACKAGE)

    def test_highest_package_wins(self, fake_redis, pkg_db, monkeypatch):
        _stub_paid(monkeypatch, paid=True)
        pkg_db.add_package('small', request_quota=80)
        pkg_db.add_package('big', request_quota=500)
        pkg_db.add_entitlement(104, 'small')
        pkg_db.add_entitlement(104, 'big')
        assert _run(user_quota.resolve_limit(104))[0] == 500

    def test_expired_package_does_not_count(self, fake_redis, pkg_db):
        pkg_db.add_package('pro', request_quota=200)
        pkg_db.add_entitlement(105, 'pro', expires_at=_utcnow() - timedelta(days=1))
        assert _run(user_quota.resolve_limit(105)) == (
            user_quota.DEFAULT_LIMIT, user_quota.SOURCE_DEFAULT)

    def test_inactive_package_does_not_count(self, fake_redis, pkg_db):
        pkg_db.add_package('pro', request_quota=200)
        pkg_db.add_entitlement(106, 'pro', active=False)
        assert _run(user_quota.resolve_limit(106))[0] == user_quota.DEFAULT_LIMIT

    def test_null_request_quota_falls_through_not_unlimited(self, fake_redis, pkg_db):
        """Every live package today has request_quota NULL. NULL must mean
        'grants no window quota' -> the default, never 'no limit'."""
        pkg_db.add_package('starter-credits', request_quota=None)
        pkg_db.add_entitlement(107, 'starter-credits')
        assert _run(user_quota.resolve_limit(107)) == (
            user_quota.DEFAULT_LIMIT, user_quota.SOURCE_DEFAULT)

    def test_paid_wallet_user_without_a_package_is_exempt(self, fake_redis, pkg_db, monkeypatch):
        _stub_paid(monkeypatch, paid=True)
        limit, source = _run(user_quota.resolve_limit(108))
        assert limit is None
        assert source == user_quota.SOURCE_EXEMPT

    def test_wallet_balance_alone_is_exempt(self, fake_redis, pkg_db, monkeypatch):
        """The 9,954,787-toman account that was once told its credit had run
        out. A balance holder must never be capped."""
        _stub_paid(monkeypatch, paid=False, balance=True)
        assert _run(user_quota.resolve_limit(109))[0] is None


# ── 2. boundaries ────────────────────────────────────────────────────────

class TestBoundary:
    def test_default_user_allowed_at_forty_nine(self, fake_redis, pkg_db):
        fake_redis.seed(201, 49)
        assert _run(user_quota.check_and_consume(201)) is None
        assert fake_redis.used(201) == 50

    def test_default_user_blocked_at_fifty(self, fake_redis, pkg_db):
        fake_redis.seed(202, 50, ttl=777)
        gate = _run(user_quota.check_and_consume(202))
        assert gate is not None
        assert gate['limit'] == 50
        assert gate['used'] == 50
        assert gate['source'] == user_quota.SOURCE_DEFAULT
        assert gate['retry_after_seconds'] == 777

    def test_rejection_consumes_nothing(self, fake_redis, pkg_db):
        fake_redis.seed(203, 50)
        _run(user_quota.check_and_consume(203))
        assert fake_redis.used(203) == 50, "a blocked request must not INCR"

    def test_fifty_messages_then_the_fifty_first_is_blocked(self, fake_redis, pkg_db):
        uid = 204
        for i in range(user_quota.DEFAULT_LIMIT):
            assert _run(user_quota.check_and_consume(uid)) is None, f"message {i + 1}"
        assert _run(user_quota.check_and_consume(uid)) is not None

    def test_package_user_allowed_at_fifty_one(self, fake_redis, pkg_db, monkeypatch):
        _stub_paid(monkeypatch, paid=True)
        pkg_db.add_package('pro', request_quota=200)
        pkg_db.add_entitlement(205, 'pro')
        fake_redis.seed(205, 50)
        assert _run(user_quota.check_and_consume(205)) is None
        assert fake_redis.used(205) == 51

    def test_package_user_blocked_at_two_hundred(self, fake_redis, pkg_db, monkeypatch):
        _stub_paid(monkeypatch, paid=True)
        pkg_db.add_package('pro', request_quota=200)
        pkg_db.add_entitlement(206, 'pro')
        fake_redis.seed(206, 200, ttl=60)
        gate = _run(user_quota.check_and_consume(206))
        assert gate is not None
        assert gate['limit'] == 200
        assert gate['source'] == user_quota.SOURCE_PACKAGE
        assert gate['retry_after_seconds'] == 60

    def test_exempt_user_is_never_counted(self, fake_redis, pkg_db, monkeypatch):
        _stub_paid(monkeypatch, paid=True)
        for _ in range(user_quota.DEFAULT_LIMIT + 5):
            assert _run(user_quota.check_and_consume(301)) is None
        assert fake_redis.used(301) == 0, "an exempt user's window is never touched"

    def test_aggregate_not_per_model(self, fake_redis, pkg_db):
        """The whole point of this gate: one counter for the user, whatever
        model the message went to. services/free_tier.py is the per-model one."""
        uid = 302
        for _ in range(user_quota.DEFAULT_LIMIT):
            assert _run(user_quota.check_and_consume(uid)) is None
        assert fake_redis.used(uid) == user_quota.DEFAULT_LIMIT
        assert len([k for k in fake_redis.store if k.startswith('userquota:')]) == 1

    def test_cost_greater_than_one_cannot_straddle_the_limit(self, fake_redis, pkg_db):
        fake_redis.seed(303, 49)
        gate = _run(user_quota.check_and_consume(303, cost=2))
        assert gate is not None, "49 + 2 > 50 must be refused, not clamped"
        assert fake_redis.used(303) == 49


# ── 3. windowing ─────────────────────────────────────────────────────────

class TestWindow:
    def test_first_message_anchors_the_five_hour_window(self, fake_redis, pkg_db):
        assert _run(user_quota.check_and_consume(401)) is None
        assert fake_redis.ttls[user_quota._msg_key(401)] == user_quota.WINDOW_SECONDS
        assert user_quota.WINDOW_SECONDS == 18000

    def test_expiry_resets_the_allowance(self, fake_redis, pkg_db):
        uid = 402
        fake_redis.seed(uid, user_quota.DEFAULT_LIMIT)
        assert _run(user_quota.check_and_consume(uid)) is not None
        fake_redis.expire_now(uid)
        assert _run(user_quota.check_and_consume(uid)) is None

    def test_at_cap_with_no_ttl_fails_open_rather_than_trapping(self, fake_redis, pkg_db):
        uid = 403
        fake_redis.store[user_quota._msg_key(uid)] = str(user_quota.DEFAULT_LIMIT)
        # no TTL entry -> ttl() returns -1, a bucket that would never reset
        assert _run(user_quota.check_and_consume(uid)) is None

    def test_a_key_that_lost_its_ttl_gets_one_back(self, fake_redis, pkg_db):
        uid = 404
        fake_redis.store[user_quota._msg_key(uid)] = '3'
        assert _run(user_quota.check_and_consume(uid)) is None
        assert fake_redis.ttls[user_quota._msg_key(uid)] == user_quota.WINDOW_SECONDS


# ── 4. fail-open ─────────────────────────────────────────────────────────

class TestFailOpen:
    def test_redis_outage_allows_the_request(self, fake_redis, pkg_db):
        fake_redis.seed(501, 999)
        fake_redis.fail = True
        assert _run(user_quota.check_and_consume(501)) is None

    def test_database_outage_does_not_grant_a_package_limit(self, fake_redis, pkg_db):
        """A DB error must not raise, and must not be mistaken for 'has a
        package'. It falls through to the default cap, still enforced."""
        pkg_db.fail = True
        limit, source = _run(user_quota.resolve_limit(502))
        assert (limit, source) == (user_quota.DEFAULT_LIMIT, user_quota.SOURCE_DEFAULT)
        fake_redis.seed(502, user_quota.DEFAULT_LIMIT)
        assert _run(user_quota.check_and_consume(502)) is not None

    def test_database_outage_on_the_whole_gate_still_serves(self, fake_redis, pkg_db):
        pkg_db.fail = True
        assert _run(user_quota.check_and_consume(503)) is None

    def test_package_lookup_error_returns_none_not_raise(self, fake_redis, pkg_db):
        pkg_db.fail = True
        assert _run(user_quota.package_window_limit(504)) is None

    def test_garbage_counter_value_fails_open(self, fake_redis, pkg_db):
        fake_redis.store[user_quota._msg_key(505)] = 'not-a-number'
        assert _run(user_quota.check_and_consume(505)) is None


# ── 5. status ────────────────────────────────────────────────────────────

class TestStatus:
    def test_status_reports_used_and_remaining_without_consuming(self, fake_redis, pkg_db):
        fake_redis.seed(601, 12, ttl=900)
        st = _run(user_quota.get_status(601))
        assert st['limited'] is True
        assert st['limit'] == user_quota.DEFAULT_LIMIT
        assert st['used'] == 12
        assert st['remaining'] == user_quota.DEFAULT_LIMIT - 12
        assert st['reset_in_seconds'] == 900
        assert fake_redis.used(601) == 12

    def test_status_for_an_exempt_user(self, fake_redis, pkg_db, monkeypatch):
        _stub_paid(monkeypatch, paid=True)
        st = _run(user_quota.get_status(602))
        assert st['limited'] is False
        assert st['limit'] is None


# ── 6. SQL contract (see module docstring) ───────────────────────────────

_SQL = str(user_quota._PACKAGE_LIMIT_SQL)


def test_sql_filters_to_the_requesting_user():
    assert "pe.user_id = :uid" in _SQL


def test_sql_requires_an_active_entitlement():
    assert "pe.active = true" in _SQL


def test_sql_excludes_expired_entitlements():
    assert "(pe.expires_at IS NULL OR pe.expires_at > now())" in _SQL


def test_sql_treats_null_request_quota_as_no_quota_not_unlimited():
    assert "cp.request_quota IS NOT NULL" in _SQL


def test_sql_rejects_a_zero_or_negative_quota():
    assert "cp.request_quota > 0" in _SQL


def test_sql_takes_the_highest_quota_the_user_holds():
    assert "MAX(cp.request_quota)" in _SQL


def test_sql_joins_the_package_table_for_the_live_quota():
    """The window cap follows the admin's CURRENT credit_packages setting --
    it is a refreshing rate limit, not the grant-time snapshot rule that
    services/entitlements.py applies to a purchase."""
    assert "JOIN credit_packages cp ON cp.id = pe.package_id" in _SQL


# ── 7. the two gates must not compete ────────────────────────────────────

def test_per_model_ceiling_never_binds_first():
    """services/free_tier.py's per-model cap is subordinate to this
    aggregate one: pinned equal to DEFAULT_LIMIT so it cannot reject a
    default-tier user before the aggregate gate does. Lowering FREE_LIMIT
    below DEFAULT_LIMIT would make the per-model cap the real limit again
    and silently contradict the '50 messages per 5 hours' product rule --
    if that is what you want, change it here on purpose."""
    assert free_tier.FREE_LIMIT >= user_quota.DEFAULT_LIMIT


def test_both_gates_share_the_same_window_length():
    assert free_tier.WINDOW_SECONDS == user_quota.WINDOW_SECONDS


def test_the_two_gates_use_separate_redis_namespaces():
    assert user_quota._msg_key(7) == 'userquota:msg:7'
    assert free_tier._msg_key(7, 'm') == 'freetier:msg:7:m'
    assert not user_quota._msg_key(7).startswith('freetier:')


# ── 8. wiring: one call site, in the shared pre-flight ───────────────────

def test_the_gate_is_wired_into_the_shared_chat_preflight():
    """All four chat HTTP routes reach chat_web._chat_preflight; the gate is
    called there and nowhere else, so there is one counter, not four."""
    import inspect

    import chat_web

    src = inspect.getsource(chat_web._chat_preflight)
    assert '_user_quota_check(uid)' in src
    assert '_user_quota_response(gate)' in src


def test_the_gate_runs_after_the_content_screen():
    """A message blocked for content must not cost the user a message."""
    import inspect

    import chat_web

    src = inspect.getsource(chat_web._chat_preflight)
    assert src.index('moderation_preflight') < src.index('_user_quota_check')


def test_rejection_is_a_429_with_a_distinct_code_and_retry_after():
    import json

    import chat_web

    resp = chat_web._user_quota_response(
        {'limit': 50, 'used': 50, 'source': 'default', 'retry_after_seconds': 3600})
    assert resp.status_code == 429
    body = json.loads(resp.body)['error']
    assert body['code'] == 'message_quota_exceeded'
    assert body['type'] == 'rate_limited'
    assert body['retry_after_seconds'] == 3600
    assert body['limit'] == 50
    # Persian, with Persian-Indic numerals (dependencies._to_fa), not ASCII.
    assert '۵۰' in body['message']
    assert '50' not in body['message']


def test_package_rejection_message_differs_from_the_default_tier_one():
    import json

    import chat_web

    base = {'limit': 200, 'used': 200, 'retry_after_seconds': 60}
    pkg = json.loads(chat_web._user_quota_response({**base, 'source': 'package'}).body)
    dflt = json.loads(chat_web._user_quota_response({**base, 'source': 'default'}).body)
    assert pkg['error']['message'] != dflt['error']['message']
    assert 'بسته' in pkg['error']['message']


# ── 9. end-to-end, through all four chat HTTP routes ─────────────────────
#
# Same shape as tests/test_moderation_wiring.py's parametrised block test,
# and for the same reason: a fifth chat route that forgets
# chat._chat_preflight is exactly the bypass this catches. Drives the REAL
# gate (only its Redis/DB dependencies are faked), so it also proves the
# rejection lands BEFORE BillingService.reserve() and before the upstream
# call -- the position requirement, not just the return value.

import json as _json  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

import chat as chat_mod  # noqa: E402

_AUTH = {'Authorization': 'Bearer test-token'}


class _UpstreamRecorder:
    """Stands in for the upstream HTTP client, returning a well-formed
    completion so the allowed path finishes cleanly (an under-specified mock
    here leaves un-awaited coroutines behind -- see pytest.ini)."""

    def __init__(self):
        self.calls = []
        self.post = AsyncMock(side_effect=self._post)

    async def _post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            'choices': [{'message': {'role': 'assistant', 'content': 'سلام'},
                         'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 5},
        }
        resp.text = ''
        return resp


class _QuotaEnv:
    """The real gate against a full bucket; everything after it stubbed."""

    def __init__(self, used: int = 999, limit_ttl: int = 3600):
        self.redis = FakeRedis()
        self.redis.seed(1, used, ttl=limit_ttl)
        self.db = _FakePackageDB()  # no packages -> DEFAULT_LIMIT applies
        self.billing = MagicMock()
        self.billing.reserve = AsyncMock(return_value={'reservation_id': 'r1'})
        self.billing.release = AsyncMock(return_value=None)
        self.billing.settle = AsyncMock(return_value=None)
        self.http = _UpstreamRecorder()
        import chat_web
        self._patches = (
            patch.object(user_quota, 'rds', self.redis),
            patch.object(user_quota, 'async_session', _session_factory(self.db)),
            patch.object(chat_web, 'moderation_preflight', AsyncMock(return_value=None)),
            patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)),
            patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)),
            patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='kr/m')),
            patch.object(chat_mod, '_safe_default_model', AsyncMock(return_value='kr/m')),
            patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)),
            patch.object(chat_mod, '_apply_persian_style_guard_for_model', AsyncMock(return_value=None)),
            patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)),
            patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)),
            patch.object(chat_mod, 'covering_entitlement', AsyncMock(return_value=None)),
            patch.object(chat_mod, 'get_injection_messages', AsyncMock(return_value=[])),
            patch.object(chat_mod, 'BillingService', MagicMock(return_value=self.billing)),
            patch.object(chat_mod, '_http', self.http),
            patch.object(chat_mod, '_record_usage', AsyncMock(return_value=None)),
            patch.object(chat_mod, '_track_usage', AsyncMock(return_value=None)),
            patch.object(chat_mod, '_fire_memory_extraction', MagicMock(return_value=None)),
        )
        self._entered = []

    def __enter__(self):
        for p in self._patches:
            self._entered.append(p.start())
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False


def _post(client, path):
    msgs = [{'role': 'user', 'content': 'سلام'}]
    if path == '/v1/compare':
        return client.post(path, json={'model_a': 'kr/a', 'model_b': 'kr/b', 'messages': msgs},
                           headers=_AUTH)
    if path == '/v1/chat/with-file':
        return client.post(path, files={'file': ('n.txt', b'hi', 'text/plain')},
                           data={'model': 'kr/m', 'messages': _json.dumps(msgs)}, headers=_AUTH)
    return client.post(path, json={'model': 'kr/m', 'messages': msgs}, headers=_AUTH)


@pytest.mark.parametrize('path', [
    '/v1/chat/completions',
    '/v1/smart-chat',
    '/v1/compare',
    '/v1/chat/with-file',
])
def test_exhausted_quota_blocks_every_chat_entry_point(path, client, mock_async_session):
    with _QuotaEnv() as env:
        resp = _post(client, path)

    assert resp.status_code == 429, f'{path} -> {resp.status_code} {resp.text[:200]}'
    body = resp.json()['error']
    assert body['code'] == 'message_quota_exceeded'
    assert body['retry_after_seconds'] == 3600

    # The position requirement: no money moved and no upstream was called.
    env.billing.reserve.assert_not_awaited()
    assert env.http.post.await_count == 0, f'{path}: upstream called on a blocked request'


@pytest.mark.parametrize('path', [
    '/v1/chat/completions',
    '/v1/smart-chat',
    '/v1/compare',
    '/v1/chat/with-file',
])
def test_a_request_under_the_cap_is_not_blocked_and_consumes_one(path, client, mock_async_session):
    """One message per HTTP request -- /v1/compare included, even though it
    fans out to two models."""
    with _QuotaEnv(used=1) as env:
        resp = _post(client, path)

    assert resp.json().get('error', {}).get('code') != 'message_quota_exceeded'
    assert env.redis.used(1) == 2, f'{path} consumed {env.redis.used(1) - 1} messages, expected 1'
