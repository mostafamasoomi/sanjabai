"""Tests for the rewritten free tier (services/free_tier.py): cheap-models-
only + hourly cap + durable lifetime cap, for a user with no pay/package/
balance.

No real Postgres or Redis. Redis is a small in-memory fake; the three
DB-backed helpers (_model_input_price, _lifetime_used, _lifetime_incr) and
the config reader (get_config) are monkeypatched so each test controls
prices, the stored lifetime count, and the three limits directly. This tests
check_and_consume's LOGIC -- ordering, peek-then-consume, boundaries,
fail-open -- which is the part that gates every free chat request; the SQL in
those helpers is exercised separately against the live DB.
"""
from __future__ import annotations

import asyncio

import pytest

from services import free_tier


def _run(coro):
    return asyncio.run(coro)


class FakeRedis:
    """Async Redis stub covering exactly what free_tier issues now: get,
    incr, expire, ttl. TTLs do not count down; expire_now() simulates a
    bucket running out."""

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

    async def incr(self, key):
        self._check()
        cur = int(self.store.get(key, '0')) + 1
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

    def expire_now(self, key):
        self.store.pop(key, None)
        self.ttls.pop(key, None)


@pytest.fixture
def env(monkeypatch):
    """Wire a fake Redis, controllable config, per-model prices, and an
    in-memory lifetime counter into free_tier. Returns a small handle the
    tests drive."""
    fr = FakeRedis()
    monkeypatch.setattr(free_tier, 'rds', fr)

    state = {
        'config': {
            'free_hourly_limit': 3,
            'free_lifetime_limit': 30,
            'free_tier_max_input_per_million': 60000,
        },
        'prices': {},        # model -> input_per_million (None => unknown)
        'lifetime': {},      # uid -> stored lifetime count
        'paid': set(),       # uids treated as paid
        'balance': set(),    # uids treated as holding balance
    }

    async def fake_config():
        return dict(state['config'])

    async def fake_price(model):
        return state['prices'].get(model)

    async def fake_lifetime_used(uid):
        return state['lifetime'].get(uid)

    async def fake_lifetime_incr(uid):
        state['lifetime'][uid] = state['lifetime'].get(uid, 0) + 1

    async def fake_has_paid(uid):
        return uid in state['paid']

    async def fake_has_balance(uid):
        return uid in state['balance']

    monkeypatch.setattr(free_tier, 'get_config', fake_config)
    monkeypatch.setattr(free_tier, '_model_input_price', fake_price)
    monkeypatch.setattr(free_tier, '_lifetime_used', fake_lifetime_used)
    monkeypatch.setattr(free_tier, '_lifetime_incr', fake_lifetime_incr)
    monkeypatch.setattr(free_tier, 'has_paid', fake_has_paid)
    monkeypatch.setattr(free_tier, 'has_balance', fake_has_balance)

    state['redis'] = fr
    return state


CHEAP = 'sanjab/gpt-oss-120b'
PREMIUM = 'sanjab/claude-opus-5'


class TestExemptions:
    def test_paid_user_never_gated(self, env):
        env['paid'].add(1)
        env['prices'][PREMIUM] = 953000  # would be blocked if not exempt
        for _ in range(10):
            assert _run(free_tier.check_and_consume(1, [PREMIUM])) is None

    def test_balance_user_never_gated(self, env):
        env['balance'].add(2)
        env['prices'][PREMIUM] = 953000
        for _ in range(10):
            assert _run(free_tier.check_and_consume(2, [PREMIUM])) is None


class TestCheapModelGate:
    def test_premium_model_blocked(self, env):
        env['prices'][PREMIUM] = 953000  # > 60000 ceiling
        result = _run(free_tier.check_and_consume(3, [PREMIUM]))
        assert result is not None
        assert result['code'] == 'free_model_not_allowed'
        assert result['model'] == PREMIUM

    def test_cheap_model_allowed(self, env):
        env['prices'][CHEAP] = 5718  # <= 60000
        assert _run(free_tier.check_and_consume(4, [CHEAP])) is None

    def test_model_at_exact_ceiling_allowed(self, env):
        env['prices']['edge'] = 60000  # exactly the ceiling, not over
        assert _run(free_tier.check_and_consume(5, ['edge'])) is None

    def test_unknown_price_fails_open(self, env):
        # price None (model not in catalog) => cannot confirm expensive => allow
        assert _run(free_tier.check_and_consume(6, ['mystery-model'])) is None

    def test_compare_blocks_if_any_model_premium(self, env):
        env['prices'][CHEAP] = 5718
        env['prices'][PREMIUM] = 953000
        result = _run(free_tier.check_and_consume(7, [CHEAP, PREMIUM]))
        assert result is not None
        assert result['code'] == 'free_model_not_allowed'
        assert result['model'] == PREMIUM

    def test_blocked_premium_consumes_nothing(self, env):
        env['prices'][PREMIUM] = 953000
        _run(free_tier.check_and_consume(8, [PREMIUM]))
        # Neither the hourly bucket nor the lifetime counter moved.
        assert env['redis'].store.get(free_tier._hourly_key(8)) is None
        assert env['lifetime'].get(8) is None


class TestHourlyCap:
    def test_three_allowed_fourth_blocked(self, env):
        env['prices'][CHEAP] = 5718
        for i in range(3):
            assert _run(free_tier.check_and_consume(10, [CHEAP])) is None, f"msg {i+1}"
        result = _run(free_tier.check_and_consume(10, [CHEAP]))
        assert result is not None
        assert result['code'] == 'free_hourly_throttle'
        assert result['retry_after_seconds'] > 0

    def test_hourly_limit_is_configurable(self, env):
        env['config']['free_hourly_limit'] = 1
        env['prices'][CHEAP] = 5718
        assert _run(free_tier.check_and_consume(11, [CHEAP])) is None
        assert _run(free_tier.check_and_consume(11, [CHEAP])) is not None

    def test_expiry_resets_hourly(self, env):
        env['prices'][CHEAP] = 5718
        for _ in range(3):
            assert _run(free_tier.check_and_consume(12, [CHEAP])) is None
        assert _run(free_tier.check_and_consume(12, [CHEAP])) is not None
        env['redis'].expire_now(free_tier._hourly_key(12))
        assert _run(free_tier.check_and_consume(12, [CHEAP])) is None


class TestLifetimeCap:
    def test_at_lifetime_cap_blocks(self, env):
        env['prices'][CHEAP] = 5718
        env['lifetime'][20] = 30  # already at the cap
        result = _run(free_tier.check_and_consume(20, [CHEAP]))
        assert result is not None
        assert result['code'] == 'free_lifetime_exhausted'

    def test_one_below_cap_allowed_and_increments(self, env):
        env['prices'][CHEAP] = 5718
        env['lifetime'][21] = 29
        assert _run(free_tier.check_and_consume(21, [CHEAP])) is None
        assert env['lifetime'][21] == 30  # incremented on consume

    def test_lifetime_blocked_consumes_no_hourly(self, env):
        env['prices'][CHEAP] = 5718
        env['lifetime'][22] = 30
        _run(free_tier.check_and_consume(22, [CHEAP]))
        assert env['redis'].store.get(free_tier._hourly_key(22)) is None

    def test_lifetime_beats_hourly_when_both_would_block(self, env):
        # Lifetime is checked before hourly, so an exhausted-lifetime user
        # sees the paywall message, not the hourly one.
        env['prices'][CHEAP] = 5718
        env['lifetime'][23] = 100
        result = _run(free_tier.check_and_consume(23, [CHEAP]))
        assert result['code'] == 'free_lifetime_exhausted'


class TestFailOpen:
    def test_redis_outage_fails_open(self, env):
        env['prices'][CHEAP] = 5718
        env['redis'].fail = True
        assert _run(free_tier.check_and_consume(30, [CHEAP])) is None


class TestConsumeOrder:
    def test_allow_increments_both_counters(self, env):
        env['prices'][CHEAP] = 5718
        env['lifetime'][40] = 0
        assert _run(free_tier.check_and_consume(40, [CHEAP])) is None
        assert env['redis'].store.get(free_tier._hourly_key(40)) == '1'
        assert env['lifetime'][40] == 1


class TestStatus:
    def test_status_reports_both_windows(self, env):
        env['prices'][CHEAP] = 5718
        env['lifetime'][50] = 0
        _run(free_tier.check_and_consume(50, [CHEAP]))
        _run(free_tier.check_and_consume(50, [CHEAP]))
        status = _run(free_tier.get_status(50))
        assert status['free_mode'] is True
        assert status['hourly_limit'] == 3
        assert status['hourly_used'] == 2
        assert status['hourly_remaining'] == 1
        assert status['lifetime_limit'] == 30
        assert status['lifetime_used'] == 2
        assert status['lifetime_remaining'] == 28

    def test_status_paid_reports_free_mode_false(self, env):
        env['paid'].add(51)
        status = _run(free_tier.get_status(51))
        assert status['free_mode'] is False
