"""Tests for the free-tier per-model message throttle (services/free_tier.py).

Uses a small in-memory fake Redis (get/set/incr/expire/ttl/sadd/smembers/
delete) in the same spirit as services.billing.MemoryBillingRepo -- no
external services and no real database. has_paid() falls through to "not
paid" whenever the DB proxy isn't initialized (the default in this test
file, since nothing here sets up database._real_async_session), which is
exactly the behavior these throttle tests want; the one test that needs a
"paid" user seeds the Redis cache key directly instead of standing up a DB.
"""
from __future__ import annotations

import asyncio

import pytest

from services import free_tier


def _run(coro):
    return asyncio.run(coro)


class FakeRedis:
    """Minimal async Redis stub covering exactly the commands
    services.free_tier issues: get, set, incr, expire, ttl, sadd, smembers,
    delete. Not a full Redis reimplementation -- e.g. TTLs don't actually
    count down with wall-clock time; ``expire_now`` simulates a bucket's
    TTL running out for the "expiry resets the allowance" test.
    """

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.sets: dict[str, set] = {}
        self.fail = False

    def _check(self):
        if self.fail:
            raise ConnectionError("simulated redis outage")

    async def get(self, key):
        self._check()
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self._check()
        self.store[key] = str(value)
        if ex is not None:
            self.ttls[key] = int(ex)
        return True

    async def incr(self, key):
        self._check()
        cur = int(self.store.get(key, '0')) + 1
        self.store[key] = str(cur)
        return cur

    async def expire(self, key, seconds):
        self._check()
        if key in self.store or key in self.sets:
            self.ttls[key] = int(seconds)
            return True
        return False

    async def ttl(self, key):
        self._check()
        if key not in self.store and key not in self.sets:
            return -2
        return self.ttls.get(key, -1)

    async def sadd(self, key, *members):
        self._check()
        self.sets.setdefault(key, set()).update(members)
        return len(members)

    async def smembers(self, key):
        self._check()
        return set(self.sets.get(key, set()))

    async def delete(self, key):
        self._check()
        self.store.pop(key, None)
        self.sets.pop(key, None)
        self.ttls.pop(key, None)
        return 1

    # ── test-only helper, not a real Redis command ──
    def expire_now(self, key):
        """Simulate the key's TTL running out (bucket fully expired)."""
        self.store.pop(key, None)
        self.ttls.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr(free_tier, 'rds', fr)
    return fr


def _mark_paid(fr: FakeRedis, uid: int) -> None:
    fr.store[f'freetier:paid:{uid}'] = '1'


class TestThrottle:
    def test_five_allowed_sixth_rejected(self, fake_redis):
        uid = 1
        for i in range(free_tier.FREE_LIMIT):
            result = _run(free_tier.check_and_consume(uid, ['tencent-hy3']))
            assert result is None, f"message {i + 1} should be allowed"
        result = _run(free_tier.check_and_consume(uid, ['tencent-hy3']))
        assert result is not None
        assert result['model'] == 'tencent-hy3'
        assert result['retry_after_seconds'] > 0

    def test_expiry_resets_allowance(self, fake_redis):
        uid = 2
        for _ in range(free_tier.FREE_LIMIT):
            assert _run(free_tier.check_and_consume(uid, ['tencent-hy3'])) is None
        assert _run(free_tier.check_and_consume(uid, ['tencent-hy3'])) is not None

        fake_redis.expire_now(free_tier._msg_key(uid, 'tencent-hy3'))

        result = _run(free_tier.check_and_consume(uid, ['tencent-hy3']))
        assert result is None, "a fresh bucket after expiry should allow again"

    def test_per_model_independence(self, fake_redis):
        uid = 3
        for _ in range(free_tier.FREE_LIMIT):
            assert _run(free_tier.check_and_consume(uid, ['model-a'])) is None
        # model-a is now exhausted; model-b must be completely unaffected.
        assert _run(free_tier.check_and_consume(uid, ['model-a'])) is not None
        assert _run(free_tier.check_and_consume(uid, ['model-b'])) is None

    def test_paid_user_never_throttled(self, fake_redis):
        uid = 4
        _mark_paid(fake_redis, uid)
        for _ in range(free_tier.FREE_LIMIT + 3):
            assert _run(free_tier.check_and_consume(uid, ['tencent-hy3'])) is None

    def test_two_model_check_consumes_nothing_on_reject(self, fake_redis):
        uid = 5
        # Exhaust model-b only.
        for _ in range(free_tier.FREE_LIMIT):
            assert _run(free_tier.check_and_consume(uid, ['model-b'])) is None

        # A combined /v1/compare-style check: model-a still has budget but
        # model-b doesn't. Must reject, and must NOT burn model-a's budget.
        result = _run(free_tier.check_and_consume(uid, ['model-a', 'model-b']))
        assert result is not None
        assert result['model'] == 'model-b'
        assert fake_redis.store.get(free_tier._msg_key(uid, 'model-a')) is None

        # model-a must still have its full allowance.
        for _ in range(free_tier.FREE_LIMIT):
            assert _run(free_tier.check_and_consume(uid, ['model-a'])) is None
        assert _run(free_tier.check_and_consume(uid, ['model-a'])) is not None

    def test_redis_exception_fails_open(self, fake_redis):
        uid = 6
        fake_redis.fail = True
        result = _run(free_tier.check_and_consume(uid, ['tencent-hy3']))
        assert result is None


class TestStatus:
    def test_status_reports_used_and_remaining(self, fake_redis):
        uid = 7
        _run(free_tier.check_and_consume(uid, ['tencent-hy3']))
        _run(free_tier.check_and_consume(uid, ['tencent-hy3']))

        status = _run(free_tier.get_status(uid))
        assert status['free_mode'] is True
        assert status['limit'] == free_tier.FREE_LIMIT
        assert status['window_seconds'] == free_tier.WINDOW_SECONDS
        entry = next(m for m in status['models'] if m['model'] == 'tencent-hy3')
        assert entry['used'] == 2
        assert entry['remaining'] == 3
        assert entry['reset_in_seconds'] > 0

    def test_status_absent_model_not_listed(self, fake_redis):
        uid = 9
        status = _run(free_tier.get_status(uid))
        assert status['models'] == []

    def test_status_paid_user_reports_free_mode_false(self, fake_redis):
        uid = 8
        _mark_paid(fake_redis, uid)
        status = _run(free_tier.get_status(uid))
        assert status['free_mode'] is False
        assert status['models'] == []
