"""SQL contract, call-site wiring, and end-to-end HTTP tests for the
aggregate per-user message quota (services/user_quota.py).

Split out of the original tests/test_user_quota.py (which grew past the
500-line cap) -- the limit-resolution/boundary/window/fail-open/status
behaviour tests now live in tests/test_user_quota_gate.py, and the fakes
both files share live in tests/_user_quota_fakes.py.

Two kinds of check here, deliberately:

1. SQL CONTRACT, asserting the literal clause text of _PACKAGE_LIMIT_SQL --
   following tests/test_entitlements_sql_contract.py and for exactly the
   reason its docstring gives: there is no live Postgres here (conftest.py
   mocks asyncpg at import time), so a fake that re-implements the WHERE
   clause in Python would keep enforcing the OLD rule even if someone
   silently deleted that clause from the real SQL. The Python fake in
   tests/_user_quota_fakes.py proves the semantics are right; the text
   assertions below prove the shipped SQL still says so. (Migration 0046:
   this gate used to read ``request_quota``, now reads its own
   ``rate_limit_per_window`` column, independent of services/entitlements.py
   -- see user_quota.py.)

2. WIRING, both as source introspection (the gate is called from exactly one
   place, after the content screen) and end-to-end through all four chat
   HTTP routes with only Redis/DB faked -- same shape as
   tests/test_moderation_wiring.py's parametrised block test, and for the
   same reason: a fifth chat route that forgets chat._chat_preflight is
   exactly the bypass this catches.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
from services import user_quota
from tests._user_quota_fakes import FakeRedis, _FakePackageDB, _session_factory

# ── 6. SQL contract ──────────────────────────────────────────────────────

_SQL = str(user_quota._PACKAGE_LIMIT_SQL)


def test_sql_filters_to_the_requesting_user():
    assert "pe.user_id = :uid" in _SQL


def test_sql_requires_an_active_entitlement():
    assert "pe.active = true" in _SQL


def test_sql_excludes_expired_entitlements():
    assert "(pe.expires_at IS NULL OR pe.expires_at > now())" in _SQL


def test_sql_treats_null_rate_limit_as_no_tier_not_unlimited():
    assert "cp.rate_limit_per_window IS NOT NULL" in _SQL


def test_sql_rejects_a_zero_or_negative_rate_limit():
    assert "cp.rate_limit_per_window > 0" in _SQL


def test_sql_takes_the_highest_rate_limit_the_user_holds():
    assert "MAX(cp.rate_limit_per_window)" in _SQL


def test_sql_does_not_read_the_entitlements_request_quota_column():
    """migration 0046's whole point: the rate limit must never read
    request_quota again, or setting it would silently re-hand out free
    requests through services/entitlements.py's snapshot."""
    assert "request_quota" not in _SQL


# _PREMIUM_LIMIT_SQL's own SQL-contract tests live in
# tests/test_premium_quota.py (its actual consumer), not here.


def test_sql_joins_the_package_table_for_the_live_quota():
    """The window cap follows the admin's CURRENT credit_packages setting --
    it is a refreshing rate limit, not the grant-time snapshot rule that
    services/entitlements.py applies to a purchase."""
    assert "JOIN credit_packages cp ON cp.id = pe.package_id" in _SQL


def test_the_two_gates_use_separate_redis_namespaces():
    from services import free_tier
    assert user_quota._msg_key(7) == 'userquota:msg:7'
    assert free_tier._hourly_key(7) == 'freetier:hourly:7'
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
        # A package holder is the only user THIS gate now caps (the free tier
        # moved to services/free_tier.py). Give uid 1 a package so the
        # aggregate quota actually binds in these end-to-end tests.
        self.db = _FakePackageDB()
        self.db.add_package('pro', rate_limit_per_window=50)
        self.db.add_entitlement(1, 'pro')
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
                           data={'model': 'kr/m', 'messages': json.dumps(msgs)}, headers=_AUTH)
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
