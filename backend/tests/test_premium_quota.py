"""Tests for the premium (expensive-model) sub-allowance gate
(services/premium_quota.py, migration 0046).

Two kinds, as in tests/test_user_quota.py: (1) BEHAVIOUR against an
in-memory fake Redis with premium_quota's DB helpers monkeypatched directly
(same spirit as tests/test_free_tier.py); (2) WIRING, proving the real gate
is reached from chat_web.py's ``chat_with_file`` -- the one entry point this
session owns -- after the free-tier gate and before reserve().

``premium_package_window_limit`` is patched on the ``premium_quota`` module,
not ``services.user_quota`` -- premium_quota.py imports it by name, a
module-level binding a patch on the source module would not reach (same
footgun test_user_quota.py documents for has_paid/has_balance).

An autouse fixture invalidates premium_quota's 60s setting cache before
every test -- a plain module-level global that would otherwise leak a value
cached by an earlier test into a later one.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import premium_quota
from services import user_quota as _uq


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_setting_cache():
    premium_quota.invalidate_setting_cache()
    yield
    premium_quota.invalidate_setting_cache()


# ── fakes ────────────────────────────────────────────────────────────────

class FakeRedis:
    """Exactly the commands services.premium_quota issues: get, ttl, incrby,
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
        self.store[premium_quota._msg_key(uid)] = str(used)
        self.ttls[premium_quota._msg_key(uid)] = ttl

    def used(self, uid: int) -> int:
        return int(self.store.get(premium_quota._msg_key(uid), '0'))

    def expire_now(self, uid: int):
        self.store.pop(premium_quota._msg_key(uid), None)
        self.ttls.pop(premium_quota._msg_key(uid), None)


@pytest.fixture
def fake_redis(monkeypatch):
    fr = FakeRedis()
    monkeypatch.setattr(premium_quota, 'rds', fr)
    return fr


def _stub_limit(monkeypatch, limit):
    """The user's premium sub-allowance, as if resolved from their best
    active package. ``None`` = no quota-granting package = exempt."""
    monkeypatch.setattr(
        premium_quota, 'premium_package_window_limit', AsyncMock(return_value=limit)
    )


def _stub_price(monkeypatch, price_by_model: dict[str, int | None]):
    async def fake(model):
        return price_by_model.get(model)
    monkeypatch.setattr(premium_quota, '_model_input_price', fake)


CHEAP = 'kr/cheap'
PRICEY = 'kr/pricey'


# ── 1. exemption (no rate-limiting package) ─────────────────────────────

class TestExemption:
    def test_no_package_is_always_exempt(self, fake_redis, monkeypatch):
        _stub_limit(monkeypatch, None)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        for _ in range(10):
            assert _run(premium_quota.check_and_consume(1, [PRICEY])) is None
        assert fake_redis.used(1) == 0


# ── 2. expensive-model detection ─────────────────────────────────────────

class TestExpensiveDetection:
    def test_price_at_threshold_is_not_expensive(self, fake_redis, monkeypatch):
        """Strictly greater than, per the module docstring -- equal is not
        expensive."""
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {CHEAP: 150_000})
        monkeypatch.setattr(premium_quota, '_min_input_per_million', AsyncMock(return_value=150_000))
        assert _run(premium_quota.check_and_consume(3, [CHEAP])) is None
        assert fake_redis.used(3) == 0

    def test_price_above_threshold_is_expensive(self, fake_redis, monkeypatch):
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 150_001})
        monkeypatch.setattr(premium_quota, '_min_input_per_million', AsyncMock(return_value=150_000))
        assert _run(premium_quota.check_and_consume(4, [PRICEY])) is None
        assert fake_redis.used(4) == 1

    def test_unknown_price_is_not_treated_as_expensive(self, fake_redis, monkeypatch):
        """Fails open: 'cannot confirm expensive' is not 'expensive'."""
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {})  # no entry -> None
        assert _run(premium_quota.check_and_consume(5, ['kr/unknown'])) is None
        assert fake_redis.used(5) == 0

    def test_a_cheap_model_request_consumes_nothing(self, fake_redis, monkeypatch):
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {CHEAP: 1000})
        for _ in range(20):
            assert _run(premium_quota.check_and_consume(6, [CHEAP])) is None
        assert fake_redis.used(6) == 0

    def test_either_model_in_a_multi_model_request_being_expensive_counts(self, fake_redis, monkeypatch):
        """/v1/compare's two models -- EITHER expensive makes it premium."""
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {CHEAP: 1000, PRICEY: 999_999})
        assert _run(premium_quota.check_and_consume(7, [CHEAP, PRICEY])) is None
        assert fake_redis.used(7) == 1, "one request -> one consumed unit, not per-model"


# ── 3. boundaries ─────────────────────────────────────────────────────────

class TestBoundary:
    def test_allowed_just_below_limit(self, fake_redis, monkeypatch):
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        fake_redis.seed(201, 4)
        assert _run(premium_quota.check_and_consume(201, [PRICEY])) is None
        assert fake_redis.used(201) == 5

    def test_blocked_at_limit(self, fake_redis, monkeypatch):
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        fake_redis.seed(202, 5, ttl=777)
        gate = _run(premium_quota.check_and_consume(202, [PRICEY]))
        assert gate is not None
        assert gate['code'] == 'premium_quota_exceeded'
        assert gate['retry_after_seconds'] == 777
        assert gate['model'] == PRICEY

    def test_rejection_consumes_nothing(self, fake_redis, monkeypatch):
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        fake_redis.seed(203, 5)
        _run(premium_quota.check_and_consume(203, [PRICEY]))
        assert fake_redis.used(203) == 5, "a blocked request must not INCR"

    def test_n_premium_messages_then_the_next_is_blocked(self, fake_redis, monkeypatch):
        uid = 204
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        for i in range(5):
            assert _run(premium_quota.check_and_consume(uid, [PRICEY])) is None, f"message {i + 1}"
        assert _run(premium_quota.check_and_consume(uid, [PRICEY])) is not None

    def test_cheap_messages_do_not_count_toward_the_premium_cap(self, fake_redis, monkeypatch):
        """However much cheap traffic there is, it never eats the sub-allowance."""
        uid = 205
        _stub_limit(monkeypatch, 1)
        _stub_price(monkeypatch, {CHEAP: 1000, PRICEY: 999_999})
        for _ in range(50):
            assert _run(premium_quota.check_and_consume(uid, [CHEAP])) is None
        assert fake_redis.used(uid) == 0
        # the lone premium slot is still available
        assert _run(premium_quota.check_and_consume(uid, [PRICEY])) is None
        assert _run(premium_quota.check_and_consume(uid, [PRICEY])) is not None


# ── 4. windowing ─────────────────────────────────────────────────────────

class TestWindow:
    def test_first_premium_message_anchors_the_five_hour_window(self, fake_redis, monkeypatch):
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        assert _run(premium_quota.check_and_consume(401, [PRICEY])) is None
        assert fake_redis.ttls[premium_quota._msg_key(401)] == premium_quota.WINDOW_SECONDS
        assert premium_quota.WINDOW_SECONDS == 18000

    def test_expiry_resets_the_allowance(self, fake_redis, monkeypatch):
        uid = 402
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        fake_redis.seed(uid, 5)
        assert _run(premium_quota.check_and_consume(uid, [PRICEY])) is not None
        fake_redis.expire_now(uid)
        assert _run(premium_quota.check_and_consume(uid, [PRICEY])) is None

    def test_at_cap_with_no_ttl_fails_open_rather_than_trapping(self, fake_redis, monkeypatch):
        uid = 403
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        fake_redis.store[premium_quota._msg_key(uid)] = '5'
        assert _run(premium_quota.check_and_consume(uid, [PRICEY])) is None

    def test_a_key_that_lost_its_ttl_gets_one_back(self, fake_redis, monkeypatch):
        uid = 404
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        fake_redis.store[premium_quota._msg_key(uid)] = '1'
        assert _run(premium_quota.check_and_consume(uid, [PRICEY])) is None
        assert fake_redis.ttls[premium_quota._msg_key(uid)] == premium_quota.WINDOW_SECONDS


# ── 5. fail-open ─────────────────────────────────────────────────────────

class TestFailOpen:
    def test_redis_outage_allows_the_request(self, fake_redis, monkeypatch):
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        fake_redis.seed(501, 999)
        fake_redis.fail = True
        assert _run(premium_quota.check_and_consume(501, [PRICEY])) is None

    def test_package_lookup_error_fails_open(self, fake_redis, monkeypatch):
        monkeypatch.setattr(
            premium_quota, 'premium_package_window_limit',
            AsyncMock(side_effect=RuntimeError("simulated db outage")),
        )
        _stub_price(monkeypatch, {PRICEY: 999_999})
        assert _run(premium_quota.check_and_consume(502, [PRICEY])) is None

    def test_price_lookup_error_fails_open(self, fake_redis, monkeypatch):
        _stub_limit(monkeypatch, 5)

        async def boom(model):
            raise RuntimeError("simulated db outage")
        monkeypatch.setattr(premium_quota, '_model_input_price', boom)
        assert _run(premium_quota.check_and_consume(503, [PRICEY])) is None

    def test_garbage_counter_value_fails_open(self, fake_redis, monkeypatch):
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        fake_redis.store[premium_quota._msg_key(504)] = 'not-a-number'
        assert _run(premium_quota.check_and_consume(504, [PRICEY])) is None


# ── 6. the rejection message ───────────────────────────────────────────

class TestMessage:
    def test_message_content(self, fake_redis, monkeypatch):
        """Persian countdown, says other models work, names no rule/model/provider."""
        _stub_limit(monkeypatch, 5)
        _stub_price(monkeypatch, {PRICEY: 999_999})
        fake_redis.seed(601, 5, ttl=3600)
        gate = _run(premium_quota.check_and_consume(601, [PRICEY]))
        msg = gate['message']
        assert '۱' in msg or 'ساعت' in msg
        assert 'retry' not in msg
        assert 'مدل‌های دیگر' in msg
        for forbidden in (PRICEY, 'kr/', 'provider', 'upstream', 'litellm', 'openrouter'):
            assert forbidden not in msg


# ── 7. the setting cache ─────────────────────────────────────────────────

class TestSettingCache:
    def test_no_db_falls_back_to_the_migration_default(self, monkeypatch):
        monkeypatch.setattr(premium_quota, 'async_session', None)
        assert _run(premium_quota._min_input_per_million()) == premium_quota.DEFAULT_MIN_INPUT_PER_MILLION
        assert premium_quota.DEFAULT_MIN_INPUT_PER_MILLION == 150_000

    def test_value_is_cached_across_calls_within_the_ttl(self, monkeypatch):
        calls = {'n': 0}

        class _Result:
            def fetchone(self_inner):
                calls['n'] += 1
                return MagicMock(_mapping={'value': 200_000})

        class _Session:
            async def execute(self_inner, *a, **k):
                return _Result()

            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False

        monkeypatch.setattr(premium_quota, 'async_session', lambda: _Session())
        first = _run(premium_quota._min_input_per_million())
        second = _run(premium_quota._min_input_per_million())
        assert first == second == 200_000
        assert calls['n'] == 1, "second call within the TTL must not hit the DB again"


# ── 8. SQL contract for user_quota.py's _PREMIUM_LIMIT_SQL (this gate's dependency) ──
# premium_quota.py resolves its limit via user_quota.py's
# premium_package_window_limit rather than reimplementing the JOIN/WHERE;
# asserted here (the actual consumer), not in tests/test_user_quota.py.

_PREMIUM_SQL = str(_uq._PREMIUM_LIMIT_SQL)


def test_premium_limit_sql_contract():
    assert "pe.user_id = :uid" in _PREMIUM_SQL
    assert "pe.active = true" in _PREMIUM_SQL
    assert "(pe.expires_at IS NULL OR pe.expires_at > now())" in _PREMIUM_SQL
    assert "cp.premium_rate_limit_per_window IS NOT NULL" in _PREMIUM_SQL
    assert "cp.premium_rate_limit_per_window > 0" in _PREMIUM_SQL
    assert "MAX(cp.premium_rate_limit_per_window)" in _PREMIUM_SQL
    assert "JOIN credit_packages cp ON cp.id = pe.package_id" in _PREMIUM_SQL


# ── 9. wiring: chat_web.py's chat_with_file, the entry point this session owns ─

def test_the_gate_is_called_after_free_tier_and_before_reserve():
    import inspect

    import chat_web

    src = inspect.getsource(chat_web.chat_with_file)
    assert '_premium_quota_check(uid' in src
    assert '_premium_quota_response(_premium_gate)' in src
    i_free_tier, i_premium, i_reserve = (
        src.index('_ft_gate'), src.index('_premium_quota_check(uid'), src.index('_bill_svc.reserve('))
    assert i_free_tier < i_premium < i_reserve


def test_rejection_is_a_429_with_the_gates_own_message():
    import json

    import chat_web

    resp = chat_web._premium_quota_response(
        {'code': 'premium_quota_exceeded', 'model': PRICEY,
         'retry_after_seconds': 120, 'message': 'پیام آزمایشی'})
    assert resp.status_code == 429
    body = json.loads(resp.body)['error']
    assert body['code'] == 'premium_quota_exceeded'
    assert body['type'] == 'rate_limited'
    assert body['retry_after_seconds'] == 120
    assert body['message'] == 'پیام آزمایشی'


# ── 10. end-to-end through /v1/chat/with-file ─────────────────────────────
# Drives the REAL gate (only Redis/DB deps faked): proves the rejection
# lands before reserve() and before the upstream call, not just the return
# value. Same shape as tests/test_user_quota.py's own end-to-end block.

import chat as chat_mod  # noqa: E402
import chat_web  # noqa: E402

_AUTH = {'Authorization': 'Bearer test-token'}


class _UpstreamRecorder:
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


class _PremiumEnv:
    def __init__(self, *, limit=5, used=0, ttl=3600, price=999_999):
        self.redis = FakeRedis()
        if used:
            self.redis.seed(1, used, ttl=ttl)
        self.billing = MagicMock()
        self.billing.reserve = AsyncMock(return_value={'reservation_id': 'r1'})
        self.billing.release = AsyncMock(return_value=None)
        self.billing.settle = AsyncMock(return_value=None)
        self.http = _UpstreamRecorder()
        self._patches = (
            patch.object(chat_web, '_user_quota_check', AsyncMock(return_value=None)),
            patch.object(chat_web, 'moderation_preflight', AsyncMock(return_value=None)),
            patch.object(chat_web, 'covering_entitlement', AsyncMock(return_value=None)),
            patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)),
            patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)),
            patch.object(chat_mod, '_resolve_public_model', AsyncMock(side_effect=lambda m: m)),
            patch.object(chat_mod, '_safe_default_model', AsyncMock(return_value=PRICEY)),
            patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)),
            patch.object(chat_mod, '_apply_persian_style_guard_for_model', AsyncMock(return_value=None)),
            patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)),  # free-tier: allow
            patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)),
            patch.object(chat_mod, 'covering_entitlement', AsyncMock(return_value=None)),
            patch.object(chat_mod, 'get_injection_messages', AsyncMock(return_value=[])),
            patch.object(chat_mod, 'BillingService', MagicMock(return_value=self.billing)),
            patch.object(chat_mod, '_http', self.http),
            patch.object(chat_mod, '_record_usage', AsyncMock(return_value=None)),
            patch.object(chat_mod, '_track_usage', AsyncMock(return_value=None)),
            patch.object(chat_mod, '_fire_memory_extraction', MagicMock(return_value=None)),
            patch.object(premium_quota, 'rds', self.redis),
            patch.object(premium_quota, 'premium_package_window_limit', AsyncMock(return_value=limit)),
            patch.object(premium_quota, '_model_input_price', AsyncMock(return_value=price)),
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


def _post_with_file(client, model=PRICEY):
    return client.post(
        '/v1/chat/with-file',
        files={'file': ('n.txt', b'hi', 'text/plain')},
        data={'model': model, 'messages': '[{"role": "user", "content": "سلام"}]'},
        headers=_AUTH,
    )


def test_exhausted_premium_quota_blocks_with_file_before_reserve_and_upstream(client, mock_async_session):
    with _PremiumEnv(limit=5, used=5, ttl=1800) as env:
        resp = _post_with_file(client)

    assert resp.status_code == 429, f'{resp.status_code} {resp.text[:200]}'
    body = resp.json()['error']
    assert body['code'] == 'premium_quota_exceeded'
    assert body['retry_after_seconds'] == 1800

    env.billing.reserve.assert_not_awaited()
    assert env.http.post.await_count == 0, 'upstream called on a blocked premium request'


def test_a_premium_request_under_the_cap_is_allowed_and_consumes_one(client, mock_async_session):
    with _PremiumEnv(limit=5, used=1) as env:
        resp = _post_with_file(client)

    assert resp.json().get('error', {}).get('code') != 'premium_quota_exceeded', resp.text[:200]
    assert env.redis.used(1) == 2


def test_an_exempt_user_is_never_blocked_regardless_of_usage(client, mock_async_session):
    with _PremiumEnv(limit=None, used=0) as env:
        resp = _post_with_file(client)

    assert resp.json().get('error', {}).get('code') != 'premium_quota_exceeded', resp.text[:200]
    assert env.redis.used(1) == 0, "exempt user must never be counted"
