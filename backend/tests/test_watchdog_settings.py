"""Tests for the admin-editable Telegram alerting credentials.

Covers backend/services/watchdog_settings.py (the resolver every alert call
site now goes through) and backend/admin_watchdog.py (the panel API),
introduced alongside migration 0044_watchdog_settings.sql.

Style follows tests/test_site_settings.py: a standalone FastAPI app carrying
just this router so the endpoint tests do not depend on full app wiring,
plus the conftest ``mock_async_session`` / ``make_result`` / ``make_row``
helpers for the DB layer.

The invariants this file exists to hold, in priority order:

 1. PRECEDENCE. A non-empty DB row beats the environment variable. Get this
    backwards and the admin panel becomes a button that confirms success
    and changes nothing -- the exact failure mode this codebase refuses.
    Guarded by ``TestPrecedence`` and specifically by
    ``test_db_value_wins_over_env``, which is the mutation-test target.
 2. FAIL OPEN, NEVER RAISE. ``_send_alert`` is reached from
    ``services.moderation.screen_request`` on the chat hot path. A DB or
    Redis fault in the *alerting configuration* must cost an alert, never a
    user's message.
 3. THE TOKEN NEVER COMES BACK OUT. The masked GET may return "set or not"
    and the last 4 characters and nothing else.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import admin_watchdog
from services import watchdog_settings as ws
from tests.conftest import make_result, make_row


# A realistically-shaped Telegram bot token, so the hint/masking assertions
# are about a real value and not a 3-character stand-in.
FAKE_TOKEN = '7654321098-AAHfakefaketokentokendonotuseXYZW'
FAKE_CHAT = '-1001234567890'


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def no_env(monkeypatch):
    """Neither environment variable set -- which is the LIVE state on this
    host: neither name appears in .env at all."""
    monkeypatch.delenv(ws.ENV_BOT_TOKEN, raising=False)
    monkeypatch.delenv(ws.ENV_CHAT_ID, raising=False)


@pytest.fixture
def env_set(monkeypatch):
    monkeypatch.setenv(ws.ENV_BOT_TOKEN, 'env-token-9999')
    monkeypatch.setenv(ws.ENV_CHAT_ID, 'env-chat-8888')


@pytest.fixture
def no_cache():
    """Redis miss on read, no-op on write -- so every test in this file
    exercises the DB path rather than a leftover cached blob."""
    with patch('database.rds.get', new=AsyncMock(return_value=None)), \
         patch('database.rds.setex', new=AsyncMock()), \
         patch('database.rds.delete', new=AsyncMock()):
        yield


@pytest.fixture
def admin_ok():
    with patch.object(admin_watchdog, 'admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def admin_denied():
    with patch.object(admin_watchdog, 'admin_required', new=AsyncMock(return_value=False)):
        yield


@pytest.fixture
def app_client():
    app = FastAPI()
    app.include_router(admin_watchdog.router)
    return TestClient(app)


def _db_rows(token=None, chat=None):
    """A fetchall() payload shaped like the SELECT in both modules."""
    rows = []
    if token is not None:
        rows.append(make_row(setting_key=ws.KEY_BOT_TOKEN, value=token))
    if chat is not None:
        rows.append(make_row(setting_key=ws.KEY_CHAT_ID, value=chat))
    return make_result(fetchall=rows)


# ── 1. Precedence: DB > env > empty ──────────────────────────────────────

class TestPrecedence:
    @pytest.mark.asyncio
    async def test_db_value_wins_over_env(self, mock_async_session, no_cache, env_set):
        """THE load-bearing test. Both sources populated -- the DB row must
        win, or the admin panel silently does nothing on a host that has
        the env vars set (which is how alerting is configured today)."""
        mock_async_session._execute_result = _db_rows(FAKE_TOKEN, FAKE_CHAT)
        creds = await ws.get_watchdog_credentials()
        assert creds.bot_token == FAKE_TOKEN
        assert creds.chat_id == FAKE_CHAT
        assert creds.bot_token_source == 'db'
        assert creds.chat_id_source == 'db'
        assert creds.active is True

    @pytest.mark.asyncio
    async def test_db_empty_falls_back_to_env(self, mock_async_session, no_cache, env_set):
        """Empty string is 'unset, defer', not a value -- this is what
        migration 0044 seeds, so a fresh deploy must keep using the env."""
        mock_async_session._execute_result = _db_rows('', '')
        creds = await ws.get_watchdog_credentials()
        assert creds.as_tuple() == ('env-token-9999', 'env-chat-8888')
        assert creds.bot_token_source == 'env'
        assert creds.chat_id_source == 'env'

    @pytest.mark.asyncio
    async def test_rows_missing_falls_back_to_env(self, mock_async_session, no_cache, env_set):
        """Before 0044 runs there are no rows at all -- same answer."""
        mock_async_session._execute_result = _db_rows()
        creds = await ws.get_watchdog_credentials()
        assert creds.as_tuple() == ('env-token-9999', 'env-chat-8888')

    @pytest.mark.asyncio
    async def test_both_empty_is_inert(self, mock_async_session, no_cache, no_env):
        mock_async_session._execute_result = _db_rows('', '')
        creds = await ws.get_watchdog_credentials()
        assert creds.as_tuple() == ('', '')
        assert creds.bot_token_source == 'none'
        assert creds.chat_id_source == 'none'
        assert creds.active is False

    @pytest.mark.asyncio
    async def test_halves_resolve_independently(self, mock_async_session, no_cache, env_set):
        """A DB token can pair with an env chat id. Anything else would make
        setting one field in the panel silently drop the other."""
        mock_async_session._execute_result = _db_rows(FAKE_TOKEN, '')
        creds = await ws.get_watchdog_credentials()
        assert creds.bot_token == FAKE_TOKEN and creds.bot_token_source == 'db'
        assert creds.chat_id == 'env-chat-8888' and creds.chat_id_source == 'env'

    @pytest.mark.asyncio
    async def test_one_half_missing_is_not_active(self, mock_async_session, no_cache, no_env):
        mock_async_session._execute_result = _db_rows(FAKE_TOKEN, '')
        creds = await ws.get_watchdog_credentials()
        assert creds.bot_token == FAKE_TOKEN
        assert creds.active is False


# ── 2. Fail open: a config fault costs an alert, never a request ─────────

class TestFailOpen:
    @pytest.mark.asyncio
    async def test_db_error_falls_back_to_env(self, mock_async_session, no_cache, env_set):
        async def boom(*a, **k):
            raise RuntimeError('connection reset by peer')
        mock_async_session.execute = boom
        creds = await ws.get_watchdog_credentials()
        assert creds.as_tuple() == ('env-token-9999', 'env-chat-8888')
        assert creds.bot_token_source == 'env'

    @pytest.mark.asyncio
    async def test_db_error_with_no_env_is_inert_not_raising(
            self, mock_async_session, no_cache, no_env):
        async def boom(*a, **k):
            raise RuntimeError('connection reset by peer')
        mock_async_session.execute = boom
        creds = await ws.get_watchdog_credentials()
        assert creds.as_tuple() == ('', '')

    @pytest.mark.asyncio
    async def test_cache_error_still_reads_db(self, mock_async_session, env_set):
        mock_async_session._execute_result = _db_rows(FAKE_TOKEN, FAKE_CHAT)
        with patch('database.rds.get', new=AsyncMock(side_effect=RuntimeError('redis down'))), \
             patch('database.rds.setex', new=AsyncMock(side_effect=RuntimeError('redis down'))):
            creds = await ws.get_watchdog_credentials()
        assert creds.as_tuple() == (FAKE_TOKEN, FAKE_CHAT)

    @pytest.mark.asyncio
    async def test_cache_hit_short_circuits_the_db(self, env_set):
        blob = json.dumps({ws.KEY_BOT_TOKEN: FAKE_TOKEN, ws.KEY_CHAT_ID: FAKE_CHAT})
        with patch('database.rds.get', new=AsyncMock(return_value=blob)), \
             patch.object(ws, '_read_via_session',
                          new=AsyncMock(side_effect=AssertionError('DB must not be touched'))):
            creds = await ws.get_watchdog_credentials()
        assert creds.as_tuple() == (FAKE_TOKEN, FAKE_CHAT)

    @pytest.mark.asyncio
    async def test_non_string_row_is_treated_as_unset(self, mock_async_session, no_cache, env_set):
        """A hand-edited `true` must not become the literal token 'True'."""
        mock_async_session._execute_result = _db_rows(True, 42)
        creds = await ws.get_watchdog_credentials()
        assert creds.as_tuple() == ('env-token-9999', 'env-chat-8888')

    @pytest.mark.asyncio
    async def test_custom_reader_failure_falls_back_to_env(self, env_set):
        """watchdog.py's asyncpg reader path -- same contract."""
        async def boom(keys):
            raise RuntimeError('pool is closed')
        creds = await ws.get_watchdog_credentials(reader=boom)
        assert creds.as_tuple() == ('env-token-9999', 'env-chat-8888')

    @pytest.mark.asyncio
    async def test_custom_reader_result_wins_over_env(self, env_set):
        async def reader(keys):
            assert keys == ws.SETTING_KEYS
            return {ws.KEY_BOT_TOKEN: FAKE_TOKEN, ws.KEY_CHAT_ID: FAKE_CHAT}
        creds = await ws.get_watchdog_credentials(reader=reader)
        assert creds.as_tuple() == (FAKE_TOKEN, FAKE_CHAT)
        assert creds.bot_token_source == 'db'

    @pytest.mark.asyncio
    async def test_env_only_credentials_matches_pre_0044_behaviour(self, env_set):
        creds = ws.env_only_credentials()
        assert creds.as_tuple() == ('env-token-9999', 'env-chat-8888')


# ── 3. The masked admin GET ──────────────────────────────────────────────

class TestAdminGet:
    def test_requires_admin(self, app_client, admin_denied):
        res = app_client.get('/admin/watchdog-settings')
        assert res.status_code == 401

    def test_never_returns_the_full_token(self, app_client, admin_ok,
                                          mock_async_session, env_set):
        mock_async_session._execute_result = _db_rows(FAKE_TOKEN, FAKE_CHAT)
        res = app_client.get('/admin/watchdog-settings')
        assert res.status_code == 200
        body = res.json()
        assert FAKE_TOKEN not in res.text
        assert body['bot_token_set'] is True
        assert body['bot_token_hint'] == FAKE_TOKEN[-4:]
        assert body['bot_token_source'] == 'db'
        assert body['active'] is True

    def test_chat_id_is_returned_in_full(self, app_client, admin_ok,
                                         mock_async_session, env_set):
        mock_async_session._execute_result = _db_rows(FAKE_TOKEN, FAKE_CHAT)
        body = app_client.get('/admin/watchdog-settings').json()
        assert body['chat_id'] == FAKE_CHAT

    def test_env_fallback_is_reported_as_env_and_still_active(
            self, app_client, admin_ok, mock_async_session, env_set):
        mock_async_session._execute_result = _db_rows('', '')
        body = app_client.get('/admin/watchdog-settings').json()
        assert body['active'] is True
        assert body['bot_token_source'] == 'env'
        assert body['chat_id_source'] == 'env'
        assert body['env_available'] == {'bot_token': True, 'chat_id': True}
        assert 'env-token-9999' not in app_client.get('/admin/watchdog-settings').text

    def test_nothing_set_anywhere_reports_inert(self, app_client, admin_ok,
                                                mock_async_session, no_env):
        mock_async_session._execute_result = _db_rows('', '')
        body = app_client.get('/admin/watchdog-settings').json()
        assert body['active'] is False
        assert body['bot_token_set'] is False
        assert body['bot_token_hint'] == ''
        assert body['bot_token_source'] == 'none'

    def test_short_token_gets_no_hint(self, app_client, admin_ok,
                                      mock_async_session, no_env):
        """Revealing the last 4 of a 6-character value is revealing it."""
        mock_async_session._execute_result = _db_rows('abc123', FAKE_CHAT)
        body = app_client.get('/admin/watchdog-settings').json()
        assert body['bot_token_set'] is True
        assert body['bot_token_hint'] == ''

    def test_db_error_is_500_not_a_fabricated_not_configured(
            self, app_client, admin_ok, mock_async_session, env_set):
        async def boom(*a, **k):
            raise RuntimeError('db down')
        mock_async_session.execute = boom
        res = app_client.get('/admin/watchdog-settings')
        assert res.status_code == 500
        assert 'active' not in res.json()


# ── 4. The write endpoint ────────────────────────────────────────────────

class TestAdminPost:
    def test_requires_admin(self, app_client, admin_denied):
        res = app_client.post('/admin/watchdog-settings', json={'bot_token': FAKE_TOKEN})
        assert res.status_code == 401

    def test_writes_both_fields_and_invalidates_cache(self, app_client, admin_ok,
                                                      mock_async_session):
        with patch.object(admin_watchdog, 'invalidate_cache', new=AsyncMock()) as inval, \
             patch.object(admin_watchdog, '_write_audit_log', new=AsyncMock()):
            res = app_client.post('/admin/watchdog-settings',
                                  json={'bot_token': FAKE_TOKEN, 'chat_id': FAKE_CHAT})
        assert res.status_code == 200
        assert res.json()['updated'] == {
            ws.KEY_BOT_TOKEN: 'set', ws.KEY_CHAT_ID: 'set'}
        inval.assert_awaited_once()

    def test_empty_string_clears_back_to_env_fallback(self, app_client, admin_ok,
                                                      mock_async_session):
        with patch.object(admin_watchdog, 'invalidate_cache', new=AsyncMock()), \
             patch.object(admin_watchdog, '_write_audit_log', new=AsyncMock()):
            res = app_client.post('/admin/watchdog-settings', json={'bot_token': ''})
        assert res.status_code == 200
        assert res.json()['updated'] == {ws.KEY_BOT_TOKEN: 'cleared'}

    def test_audit_log_never_records_the_token(self, app_client, admin_ok,
                                               mock_async_session):
        with patch.object(admin_watchdog, 'invalidate_cache', new=AsyncMock()), \
             patch.object(admin_watchdog, '_write_audit_log', new=AsyncMock()) as audit:
            app_client.post('/admin/watchdog-settings', json={'bot_token': FAKE_TOKEN})
        audit.assert_awaited_once()
        assert FAKE_TOKEN not in json.dumps(audit.await_args.kwargs, default=str)
        assert audit.await_args.kwargs['details'] == {ws.KEY_BOT_TOKEN: 'set'}

    def test_unknown_field_rejected(self, app_client, admin_ok, mock_async_session):
        res = app_client.post('/admin/watchdog-settings', json={'admin_token': 'x'})
        assert res.status_code == 400

    def test_empty_payload_rejected(self, app_client, admin_ok, mock_async_session):
        assert app_client.post('/admin/watchdog-settings', json={}).status_code == 400

    def test_non_string_rejected(self, app_client, admin_ok, mock_async_session):
        res = app_client.post('/admin/watchdog-settings', json={'bot_token': 123})
        assert res.status_code == 400

    def test_overlong_value_rejected(self, app_client, admin_ok, mock_async_session):
        res = app_client.post('/admin/watchdog-settings', json={'bot_token': 'x' * 600})
        assert res.status_code == 400

    def test_newline_rejected(self, app_client, admin_ok, mock_async_session):
        res = app_client.post('/admin/watchdog-settings',
                              json={'bot_token': 'abc\nDATABASE_URL=x'})
        assert res.status_code == 400

    def test_db_write_error_is_500(self, app_client, admin_ok, mock_async_session):
        async def boom(*a, **k):
            raise RuntimeError('db down')
        mock_async_session.execute = boom
        with patch.object(admin_watchdog, 'invalidate_cache', new=AsyncMock()):
            res = app_client.post('/admin/watchdog-settings', json={'bot_token': FAKE_TOKEN})
        assert res.status_code == 500


# ── 5. The three call sites really go through the resolver ───────────────

class TestCallSitesAreWired:
    """A helper nothing calls is the same failure as a switch nothing reads.
    These assert the wiring by source, because the alternative -- actually
    posting to api.telegram.org -- is not something a test may do."""

    def test_router_is_registered_on_the_real_app(self):
        """A router that exists but is never included is a page the panel
        can only ever 404 against."""
        import app as app_module

        def paths(router):
            out = set()
            for r in router.routes:
                if type(r).__name__ == '_IncludedRouter':
                    out |= paths(r.original_router)
                else:
                    p = getattr(r, 'path', None)
                    if p:
                        for m in getattr(r, 'methods', ()) or ():
                            out.add((m, p))
            return out

        got = paths(app_module.app)
        assert ('GET', '/admin/watchdog-settings') in got
        assert ('POST', '/admin/watchdog-settings') in got

    def test_no_call_site_still_reads_the_env_var_directly(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent
        for rel in ('security.py', 'watchdog.py', 'services/moderation_store.py'):
            src = (root / rel).read_text(encoding='utf-8')
            assert "os.getenv('WATCHDOG_BOT_TOKEN'" not in src, rel
            assert "os.getenv('WATCHDOG_CHAT_ID'" not in src, rel
            assert 'get_watchdog_credentials' in src, rel

    def test_watchdog_reads_credentials_per_send_not_at_import(self):
        """The module-level constants are gone -- a process that runs for
        weeks must not freeze the credentials at import."""
        import watchdog
        assert not hasattr(watchdog, 'WATCHDOG_BOT_TOKEN')
        assert not hasattr(watchdog, 'WATCHDOG_CHAT_ID')

    @pytest.mark.asyncio
    async def test_lockout_alert_uses_the_resolver_and_sends(self, monkeypatch):
        import security
        posted = {}

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None):
                posted['url'] = url
                posted['json'] = json

        creds = ws.WatchdogCredentials(FAKE_TOKEN, FAKE_CHAT, 'db', 'db')
        import httpx
        monkeypatch.setattr(httpx, 'AsyncClient', lambda *a, **k: _Client())
        with patch.object(ws, 'get_watchdog_credentials', new=AsyncMock(return_value=creds)):
            await security._send_lockout_alert('user@example.com', 5, 900)
        assert posted['url'].endswith(f'/bot{FAKE_TOKEN}/sendMessage')
        assert posted['json']['chat_id'] == FAKE_CHAT

    @pytest.mark.asyncio
    async def test_lockout_alert_is_silent_when_resolver_raises(self, monkeypatch):
        import security
        with patch.object(ws, 'get_watchdog_credentials',
                          new=AsyncMock(side_effect=RuntimeError('boom'))):
            await security._send_lockout_alert('user@example.com', 5, 900)  # must not raise

    @pytest.mark.asyncio
    async def test_moderation_alert_is_silent_when_resolver_raises(self):
        from services.moderation_store import _send_alert
        from services.moderation_rules import Verdict
        with patch.object(ws, 'get_watchdog_credentials',
                          new=AsyncMock(side_effect=RuntimeError('boom'))):
            await _send_alert(1, Verdict(decision='block'))  # must not raise
