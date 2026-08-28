"""Tests for gate 4 -- the per-user opt-out -- added to `llm_route` on top
of `tests/test_smart_router_llm.py`'s existing three-gate coverage, plus a
few tests of `services/smart_router_prefs.user_allows_router` in isolation.

The point of this file is GATE ORDER: gate 4 (`smart_router_prefs.py`, a
Postgres read) must never run while gate 2 (the site flag, cheap) has
already closed the door. `llm_route`'s full pipeline (router model
configured + eligible, provider resolvable, upstream call succeeds) is
stood up locally with fakes so "router runs" here means the call actually
went all the way through, not that `llm_route` returned non-None by luck.

Do not edit tests/test_smart_router_llm.py -- it is an existing guard for
the other three gates and is untouched by this change.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import chat as chat_mod
import services.router_probe as router_probe
import services.smart_router_llm as llm
import services.smart_router_prefs as prefs
from services.smart_router import Candidate

_POOL = [Candidate(
    provider_model_id='up/cheap',
    public_id='sanjab/cheap',
    input_per_million=10_000,
    output_per_million=30_000,
    context_window=100_000,
    upstream='ninerouter',  # in services.margin.FREE_UPSTREAMS -- no live cost lookup needed
    blended=40_000,
)]

_ABOVE_FLOOR = 50_000
_DEFAULT_ROUTER_MODEL = 'sanjab/cheap'


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


class _FakeHttp:
    """A router call that always answers '1' (menu position one)."""

    async def post(self, url, json=None, headers=None, timeout=None):
        return _FakeResponse({
            'choices': [{'message': {'role': 'assistant', 'content': '1'}}],
            'usage': {'prompt_tokens': 120, 'completion_tokens': 2},
        })


class _RouterSession:
    """Answers `_router_model`'s two app_setting reads (patched onto
    `llm.async_session`) -- always names `_DEFAULT_ROUTER_MODEL`, freshly
    probed ok=true, so a passing pipeline reaches the upstream call."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        key = (params or {}).get('key')
        if key == router_probe.SETTING_KEY:
            value = {'version': 1, 'measured_at': _now_iso(),
                     'results': {_DEFAULT_ROUTER_MODEL: {'ok': True}}}
            row = SimpleNamespace(value=value)
        else:
            row = SimpleNamespace(value=_DEFAULT_ROUTER_MODEL)
        return SimpleNamespace(fetchone=lambda: row, fetchall=lambda: [row])


class _PrefsSession:
    """Answers `user_allows_router`'s single `users` row read (patched onto
    `prefs.async_session`)."""

    def __init__(self, preferences=None, no_row=False, boom=False):
        self.preferences = preferences
        self.no_row = no_row
        self.boom = boom

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        if self.boom:
            raise RuntimeError('db down')
        row = None if self.no_row else SimpleNamespace(preferences=self.preferences)
        return SimpleNamespace(fetchone=lambda: row)


class _Factory:
    """`async_session`-shaped callable that counts how many times it was
    invoked -- the gate-order guard is "this must be zero"."""

    def __init__(self, session):
        self.session = session
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.session


@pytest.fixture
def env(monkeypatch):
    """Site flag on, router model configured and eligible, provider and
    upstream call both succeed -- the full non-preference pipeline that
    "router runs" needs to actually mean something. No preference read is
    wired up here; each test patches `prefs.async_session` itself."""
    async def _flag(key):
        assert key == 'smart_llm_router_enabled', f'unexpected flag read: {key}'
        return True

    async def _provider(model_id):
        return SimpleNamespace(v1='http://upstream/v1', headers=lambda: {'Authorization': 'Bearer k'})

    monkeypatch.setattr(llm, 'get_site_flag', _flag)
    monkeypatch.setattr(llm, 'async_session', _Factory(_RouterSession()))
    monkeypatch.setattr(chat_mod, '_resolve_provider', _provider)
    monkeypatch.setattr(chat_mod, '_http', _FakeHttp())
    return monkeypatch


# ── the kill switch always wins, whatever the user picked ────────────────

@pytest.mark.asyncio
async def test_site_flag_off_blocks_even_if_user_preference_is_on(env, monkeypatch):
    async def _off(key):
        return False
    monkeypatch.setattr(llm, 'get_site_flag', _off)
    monkeypatch.setattr(prefs, 'async_session',
                         _Factory(_PrefsSession(preferences={'smart_router_enabled': True})))
    assert await llm.llm_route('hello', _POOL, _ABOVE_FLOOR, uid=1) is None


@pytest.mark.asyncio
async def test_site_flag_off_never_reads_the_user_preference(env, monkeypatch):
    """Gate-order guard: gate 4 (a Postgres read) must not run while gate 2
    (the site flag) already returned None."""
    async def _off(key):
        return False
    monkeypatch.setattr(llm, 'get_site_flag', _off)
    prefs_factory = _Factory(_PrefsSession(preferences={'smart_router_enabled': True}))
    monkeypatch.setattr(prefs, 'async_session', prefs_factory)
    await llm.llm_route('hello', _POOL, _ABOVE_FLOOR, uid=1)
    assert prefs_factory.calls == 0, 'gate 4 ran while the site flag was already off'


# ── the opt-out within the flag ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_flag_on_and_preference_explicitly_false_blocks(env, monkeypatch):
    monkeypatch.setattr(prefs, 'async_session',
                         _Factory(_PrefsSession(preferences={'smart_router_enabled': False})))
    assert await llm.llm_route('hello', _POOL, _ABOVE_FLOOR, uid=1) is None


@pytest.mark.asyncio
async def test_flag_on_and_preference_absent_defaults_true(env, monkeypatch):
    monkeypatch.setattr(prefs, 'async_session', _Factory(_PrefsSession(preferences={})))
    assert await llm.llm_route('hello', _POOL, _ABOVE_FLOOR, uid=1) is not None


@pytest.mark.asyncio
async def test_flag_on_and_no_row_defaults_true(env, monkeypatch):
    monkeypatch.setattr(prefs, 'async_session', _Factory(_PrefsSession(no_row=True)))
    assert await llm.llm_route('hello', _POOL, _ABOVE_FLOOR, uid=1) is not None


@pytest.mark.asyncio
async def test_flag_on_and_uid_none_runs_without_touching_the_db(env, monkeypatch):
    """uid=None means there is nothing to read -- treated as opted-in, and
    `user_allows_router` must not even try `async_session()`."""
    prefs_factory = _Factory(_PrefsSession(preferences={'smart_router_enabled': False}))
    monkeypatch.setattr(prefs, 'async_session', prefs_factory)
    assert await llm.llm_route('hello', _POOL, _ABOVE_FLOOR) is not None
    assert prefs_factory.calls == 0


@pytest.mark.asyncio
async def test_db_error_reading_preference_fails_open(env, monkeypatch):
    monkeypatch.setattr(prefs, 'async_session', _Factory(_PrefsSession(boom=True)))
    assert await llm.llm_route('hello', _POOL, _ABOVE_FLOOR, uid=1) is not None


# ── user_allows_router in isolation ───────────────────────────────────────

@pytest.mark.asyncio
async def test_user_allows_router_uid_none_short_circuits(monkeypatch):
    def _boom():
        raise AssertionError('async_session() must not be called for uid=None')
    monkeypatch.setattr(prefs, 'async_session', _boom)
    assert await prefs.user_allows_router(None) is True


@pytest.mark.asyncio
async def test_user_allows_router_reads_the_literal_key():
    assert prefs._PREF_KEY == 'smart_router_enabled'
