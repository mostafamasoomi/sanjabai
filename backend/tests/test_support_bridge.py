"""Tests for the Telegram support bridge: services/support_bridge.py (the
send/receive logic) and backend/support.py (the three endpoints).

Style follows tests/test_watchdog_settings.py: a standalone FastAPI app
carrying just this router (no full app wiring needed), plus the conftest
``mock_async_session`` / ``make_result`` / ``make_row`` helpers for the DB
layer. The Telegram HTTP layer is entirely faked -- no test in this file
may reach api.telegram.org, and no real bot token appears anywhere below
(FAKE_BOT_TOKEN is a throwaway string, not a live credential).

The invariants this file exists to hold, in priority order:

 1. A BROKEN BRIDGE MUST NEVER BREAK THE USER-FACING ENDPOINT. An
    unconfigured group, a Telegram timeout, a malformed Telegram response
    -- none of these may raise out of send_to_admins/handle_admin_reply;
    the worst case is a support_message row with status='failed'.
    TestSendToAdmins covers this.
 2. OWNERSHIP. GET /support/messages must never return another user's
    rows -- enforced in the SQL WHERE clause, never filtered in Python.
    TestListMessagesOwnership::test_query_is_scoped_to_the_authenticated_user
    is the mutation-test target (see the handoff report for the paired
    red/green run).
 3. THE GROUP CHECK. POST /support/admin-reply must ignore a reply from
    any chat that is not the admin-configured support_tg_group_id --
    Telegram message_id values are per-chat, not global, so this is a
    real access-control boundary, not decoration.
    TestAdminReplyEndpoint::test_wrong_chat_id_is_ignored is the other
    mutation-test target.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import support
from services import support_bridge as sb
from tests.conftest import make_result, make_row


FAKE_BOT_TOKEN = '1234567890:AAFakeFakeFakeTokenDoNotUseXYZ'
FAKE_GROUP_ID = '-1001112223334'


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def bot_token_set(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', FAKE_BOT_TOKEN)


@pytest.fixture
def bot_token_unset(monkeypatch):
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)


@pytest.fixture
def rate_limit_ok():
    """Every call to the support rate limiter is allowed."""
    with patch.object(sb.support_message_limiter, 'is_allowed',
                       new=AsyncMock(return_value=(True, 9))):
        yield


@pytest.fixture
def rate_limit_blocked():
    with patch.object(sb.support_message_limiter, 'is_allowed',
                       new=AsyncMock(return_value=(False, 0))):
        yield


def _router(handlers: dict[str, object], calls: list):
    """Build an async session.execute() replacement.

    ``handlers`` maps a distinctive SQL substring to a fixed result object
    (built by conftest's ``make_result``). Every call is recorded on
    ``calls`` as ``(sql, params)`` so tests can assert on the exact bound
    parameters -- this is what makes the ownership test below a real
    mutation-test target rather than a shape-only check.

    Deliberately does NOT accept a callable-per-needle shape: a
    ``make_result(...)`` return value is itself a ``MagicMock``, and
    ``MagicMock`` instances are callable by default -- a
    ``callable(result)`` branch would silently call the configured result
    object instead of returning it, which is exactly the wrong answer.
    """
    async def _execute(query, params=None):
        sql = str(query)
        calls.append((sql, params))
        for needle, result in handlers.items():
            if needle in sql:
                return result
        raise AssertionError(f'unexpected SQL in test: {sql}')
    return _execute


class _FakeTelegramResponse:
    def __init__(self, status_code: int, payload: dict, content: bytes = b'{}'):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeTelegramClient:
    """Drop-in for httpx.AsyncClient -- records the single POST it saw."""
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise_exc = raise_exc
        self.posted = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        self.posted = {'url': url, 'json': json}
        if self._raise_exc:
            raise self._raise_exc
        return self._response


# ── 1. send_to_admins: never breaks the caller ────────────────────────

class TestSendToAdmins:
    @pytest.mark.asyncio
    async def test_body_too_long_raises_before_any_db_call(self, mock_async_session):
        async def boom(*a, **k):
            raise AssertionError('must not touch the DB before the length check')
        mock_async_session.execute = boom
        with pytest.raises(sb.SupportMessageTooLong):
            await sb.send_to_admins(1, 'x' * (sb.MAX_BODY_LENGTH + 1))

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_raises_and_touches_no_db(
            self, mock_async_session, rate_limit_blocked):
        async def boom(*a, **k):
            raise AssertionError('must not touch the DB when rate-limited')
        mock_async_session.execute = boom
        with pytest.raises(sb.SupportRateLimitExceeded):
            await sb.send_to_admins(1, 'hello support')

    @pytest.mark.asyncio
    async def test_unconfigured_group_stores_failed_row_without_raising(
            self, mock_async_session, rate_limit_ok, bot_token_set):
        calls = []
        handlers = {
            'INSERT INTO support_message': make_result(scalar_one=42),
            'SELECT value FROM app_setting': make_result(fetchone=None),  # no row -> unset
            "UPDATE support_message SET status = 'failed'": make_result(),
        }
        mock_async_session.execute = _router(handlers, calls)

        result = await sb.send_to_admins(1, 'help me please')

        assert result is None
        failed_calls = [c for c in calls if "status = 'failed'" in c[0]]
        assert len(failed_calls) == 1
        assert failed_calls[0][1] == {'id': 42}

    @pytest.mark.asyncio
    async def test_unconfigured_bot_token_stores_failed_row_without_raising(
            self, mock_async_session, rate_limit_ok, bot_token_unset):
        calls = []
        handlers = {
            'INSERT INTO support_message': make_result(scalar_one=7),
            'SELECT value FROM app_setting': make_result(fetchone=make_row(value=FAKE_GROUP_ID)),
            "UPDATE support_message SET status = 'failed'": make_result(),
        }
        mock_async_session.execute = _router(handlers, calls)

        result = await sb.send_to_admins(1, 'help me please')

        assert result is None

    @pytest.mark.asyncio
    async def test_successful_send_records_tg_message_id(
            self, mock_async_session, rate_limit_ok, bot_token_set):
        calls = []
        handlers = {
            'INSERT INTO support_message': make_result(scalar_one=42),
            'SELECT value FROM app_setting': make_result(fetchone=make_row(value=FAKE_GROUP_ID)),
            'UPDATE support_message SET tg_message_id': make_result(),
        }
        mock_async_session.execute = _router(handlers, calls)

        fake_client = _FakeTelegramClient(
            response=_FakeTelegramResponse(200, {'ok': True, 'result': {'message_id': 555}})
        )
        with patch('services.support_bridge.httpx.AsyncClient', return_value=fake_client):
            result = await sb.send_to_admins(9, 'my wallet is wrong', user_email='u@example.com')

        assert result == 555
        assert fake_client.posted['url'] == f'https://api.telegram.org/bot{FAKE_BOT_TOKEN}/sendMessage'
        assert fake_client.posted['json']['chat_id'] == FAKE_GROUP_ID
        assert '#9' in fake_client.posted['json']['text']
        assert 'u@example.com' in fake_client.posted['json']['text']
        assert 'my wallet is wrong' in fake_client.posted['json']['text']
        assert 'parse_mode' not in fake_client.posted['json']
        mid_calls = [c for c in calls if 'tg_message_id' in c[0] and c[0].strip().startswith('UPDATE')]
        assert mid_calls[0][1] == {'mid': 555, 'id': 42}

    @pytest.mark.asyncio
    async def test_telegram_transport_error_marks_row_failed(
            self, mock_async_session, rate_limit_ok, bot_token_set):
        calls = []
        handlers = {
            'INSERT INTO support_message': make_result(scalar_one=3),
            'SELECT value FROM app_setting': make_result(fetchone=make_row(value=FAKE_GROUP_ID)),
            "UPDATE support_message SET status = 'failed'": make_result(),
        }
        mock_async_session.execute = _router(handlers, calls)
        fake_client = _FakeTelegramClient(raise_exc=RuntimeError('connection reset'))
        with patch('services.support_bridge.httpx.AsyncClient', return_value=fake_client):
            result = await sb.send_to_admins(1, 'hi')
        assert result is None
        assert any("status = 'failed'" in c[0] for c in calls)

    @pytest.mark.asyncio
    async def test_telegram_not_ok_response_marks_row_failed(
            self, mock_async_session, rate_limit_ok, bot_token_set):
        calls = []
        handlers = {
            'INSERT INTO support_message': make_result(scalar_one=3),
            'SELECT value FROM app_setting': make_result(fetchone=make_row(value=FAKE_GROUP_ID)),
            "UPDATE support_message SET status = 'failed'": make_result(),
        }
        mock_async_session.execute = _router(handlers, calls)
        fake_client = _FakeTelegramClient(
            response=_FakeTelegramResponse(400, {'ok': False, 'description': 'chat not found'})
        )
        with patch('services.support_bridge.httpx.AsyncClient', return_value=fake_client):
            result = await sb.send_to_admins(1, 'hi')
        assert result is None
        assert any("status = 'failed'" in c[0] for c in calls)


# ── 2. handle_admin_reply ──────────────────────────────────────────────

class TestHandleAdminReply:
    @pytest.mark.asyncio
    async def test_unknown_tg_message_id_returns_false_without_raising(self, mock_async_session):
        calls = []
        handlers = {
            "SELECT user_id FROM support_message": make_result(fetchone=None),
        }
        mock_async_session.execute = _router(handlers, calls)
        result = await sb.handle_admin_reply(99999, 'this is a reply')
        assert result is False
        # Nothing was ever inserted or added -- an unmatched reply must not
        # write anything.
        assert not any('INSERT INTO support_message' in c[0] for c in calls)
        mock_async_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_known_tg_message_id_creates_row_and_notification(self, mock_async_session):
        calls = []
        handlers = {
            "SELECT user_id FROM support_message": make_result(fetchone=make_row(user_id=7)),
            "INSERT INTO support_message": make_result(),
        }
        mock_async_session.execute = _router(handlers, calls)
        result = await sb.handle_admin_reply(555, 'we fixed your wallet')
        assert result is True
        insert_calls = [c for c in calls if 'INSERT INTO support_message' in c[0]]
        assert insert_calls[0][1] == {
            'uid': 7, 'direction': 'out', 'body': 'we fixed your wallet', 'status': 'delivered',
        }
        mock_async_session.add.assert_called_once()
        notif = mock_async_session.add.call_args.args[0]
        assert notif.user_id == 7
        assert notif.body == 'we fixed your wallet'
        assert notif.type == 'support'

    @pytest.mark.asyncio
    async def test_db_error_returns_false_not_raising(self, mock_async_session):
        async def boom(*a, **k):
            raise RuntimeError('connection reset by peer')
        mock_async_session.execute = boom
        result = await sb.handle_admin_reply(1, 'hello')
        assert result is False


# ── 3. is_configured_group ─────────────────────────────────────────────

class TestIsConfiguredGroup:
    @pytest.mark.asyncio
    async def test_matching_chat_id_is_true(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(value=FAKE_GROUP_ID))
        assert await sb.is_configured_group(int(FAKE_GROUP_ID)) is True

    @pytest.mark.asyncio
    async def test_mismatched_chat_id_is_false(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(value=FAKE_GROUP_ID))
        assert await sb.is_configured_group(-1) is False

    @pytest.mark.asyncio
    async def test_unconfigured_group_is_false(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        assert await sb.is_configured_group(int(FAKE_GROUP_ID)) is False


# ── 4. The endpoints ─────────────────────────────────────────────────────

@pytest.fixture
def app_client():
    app = FastAPI()
    app.include_router(support.router)
    return TestClient(app)


@pytest.fixture
def auth_uid_1():
    with patch.object(support, '_get_user_id', new=AsyncMock(return_value=1)):
        yield


@pytest.fixture
def no_auth():
    with patch.object(support, '_get_user_id', new=AsyncMock(return_value=None)):
        yield


class TestCreateMessageEndpoint:
    def test_requires_auth(self, app_client, no_auth):
        res = app_client.post('/support/messages', json={'body': 'hi'})
        assert res.status_code == 401

    def test_empty_body_rejected(self, app_client, auth_uid_1, mock_async_session):
        res = app_client.post('/support/messages', json={'body': '   '})
        assert res.status_code == 400

    def test_too_long_returns_400(self, app_client, auth_uid_1, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(email='a@b.com'))
        with patch.object(support.support_bridge, 'send_to_admins',
                          new=AsyncMock(side_effect=sb.SupportMessageTooLong('too long'))):
            res = app_client.post('/support/messages', json={'body': 'x' * 5000})
        assert res.status_code == 400

    def test_rate_limited_returns_429(self, app_client, auth_uid_1, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(email='a@b.com'))
        with patch.object(support.support_bridge, 'send_to_admins',
                          new=AsyncMock(side_effect=sb.SupportRateLimitExceeded('too many'))):
            res = app_client.post('/support/messages', json={'body': 'hi'})
        assert res.status_code == 429

    def test_successful_send_returns_sent(self, app_client, auth_uid_1, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(email='a@b.com'))
        with patch.object(support.support_bridge, 'send_to_admins',
                          new=AsyncMock(return_value=555)):
            res = app_client.post('/support/messages', json={'body': 'hi'})
        assert res.status_code == 200
        assert res.json()['status'] == 'sent'

    def test_bridge_failure_still_returns_200_failed(self, app_client, auth_uid_1, mock_async_session):
        """A stored-but-undelivered message is not an HTTP error -- the row
        exists and shows up in GET /support/messages either way."""
        mock_async_session._execute_result = make_result(fetchone=make_row(email='a@b.com'))
        with patch.object(support.support_bridge, 'send_to_admins',
                          new=AsyncMock(return_value=None)):
            res = app_client.post('/support/messages', json={'body': 'hi'})
        assert res.status_code == 200
        assert res.json()['status'] == 'failed'


class TestListMessagesOwnership:
    def test_requires_auth(self, app_client, no_auth):
        res = app_client.get('/support/messages')
        assert res.status_code == 401

    def test_query_is_scoped_to_the_authenticated_user(self, app_client, auth_uid_1, mock_async_session):
        """THE mutation-test target for ownership. The authenticated user
        is uid=1 (auth_uid_1); every query this endpoint issues must filter
        on user_id = 1 -- both the COUNT and the SELECT. A mutation that
        drops the WHERE clause, swaps in the wrong bind value, or fetches
        another user's rows must fail this test.
        """
        calls = []

        async def _execute(query, params=None):
            sql = str(query)
            calls.append((sql, params))
            assert 'user_id = :uid' in sql, f'ownership filter missing from query: {sql}'
            assert params is not None and params.get('uid') == 1, (
                f'query bound to the wrong user: {params!r}'
            )
            if sql.strip().startswith('SELECT COUNT'):
                return make_result(fetchone=make_row(c=0))
            return make_result(fetchall=[])

        mock_async_session.execute = _execute
        res = app_client.get('/support/messages')
        assert res.status_code == 200
        assert len(calls) == 2  # COUNT + SELECT, both scoped

    def test_returns_only_rows_the_mock_scoped_query_produced(
            self, app_client, auth_uid_1, mock_async_session):
        """A second angle on ownership: even if a row for a different user
        somehow reached this process, the endpoint must not editorialize --
        it trusts the SQL scoping entirely and returns exactly what came
        back. Combined with the test above (which asserts the SQL IS
        scoped), this closes the loop: scoped query + faithful passthrough
        = no cross-user leakage."""
        handlers_calls = []

        async def _execute(query, params=None):
            sql = str(query)
            handlers_calls.append(sql)
            if sql.strip().startswith('SELECT COUNT'):
                return make_result(fetchone=make_row(c=1))
            return make_result(fetchall=[make_row(
                id=1, direction='in', body='hi', status='sent', created_at=None,
            )])

        mock_async_session.execute = _execute
        res = app_client.get('/support/messages')
        assert res.status_code == 200
        body = res.json()
        assert body['total'] == 1
        assert len(body['items']) == 1
        assert body['items'][0]['id'] == 1


class TestAdminReplyEndpoint:
    def test_missing_bot_token_header_is_401(self, app_client, bot_token_set):
        res = app_client.post('/support/admin-reply', json={
            'chat_id': -1, 'reply_to_message_id': 1, 'body': 'x',
        })
        assert res.status_code == 401

    def test_wrong_bot_token_header_is_401(self, app_client, bot_token_set):
        res = app_client.post(
            '/support/admin-reply',
            headers={'X-Bot-Token': 'not-the-right-token'},
            json={'chat_id': -1, 'reply_to_message_id': 1, 'body': 'x'},
        )
        assert res.status_code == 401

    def test_unconfigured_server_token_is_401_even_with_a_header(
            self, app_client, bot_token_unset):
        """Both sides empty must fail closed, not open."""
        res = app_client.post(
            '/support/admin-reply',
            headers={'X-Bot-Token': ''},
            json={'chat_id': -1, 'reply_to_message_id': 1, 'body': 'x'},
        )
        assert res.status_code == 401

    def test_wrong_chat_id_is_ignored(self, app_client, bot_token_set, mock_async_session):
        """THE mutation-test target for the chat-id guard. Even with valid
        bot auth, a chat_id that does not match the configured support
        group must never reach handle_admin_reply."""
        with patch.object(support.support_bridge, 'is_configured_group',
                          new=AsyncMock(return_value=False)) as is_cfg, \
             patch.object(support.support_bridge, 'handle_admin_reply',
                          new=AsyncMock()) as handle:
            res = app_client.post(
                '/support/admin-reply',
                headers={'X-Bot-Token': FAKE_BOT_TOKEN},
                json={'chat_id': -999, 'reply_to_message_id': 42, 'body': 'nice try'},
            )
        assert res.status_code == 200
        assert res.json() == {'delivered': False}
        is_cfg.assert_awaited_once_with(-999)
        handle.assert_not_called()

    def test_correct_chat_id_calls_handle_admin_reply(
            self, app_client, bot_token_set, mock_async_session):
        with patch.object(support.support_bridge, 'is_configured_group',
                          new=AsyncMock(return_value=True)), \
             patch.object(support.support_bridge, 'handle_admin_reply',
                          new=AsyncMock(return_value=True)) as handle:
            res = app_client.post(
                '/support/admin-reply',
                headers={'X-Bot-Token': FAKE_BOT_TOKEN},
                json={'chat_id': int(FAKE_GROUP_ID), 'reply_to_message_id': 42, 'body': 'fixed!'},
            )
        assert res.status_code == 200
        assert res.json() == {'delivered': True}
        handle.assert_awaited_once_with(42, 'fixed!')


# ── 5. Wiring: the app.py include line the senior must add ──────────────

class TestWiredIntoApp:
    """The routes above are only reachable because app.py includes this
    router. Without this case the whole file would pass with the bridge
    unreachable in production -- the same blind spot that let the referral
    feature's two call sites be deleted with a fully green suite (see
    tests/test_referral_rewards.py's wiring section)."""

    def test_router_is_registered_on_the_real_app(self):
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
        assert ('POST', '/support/messages') in got
        assert ('GET', '/support/messages') in got
        assert ('POST', '/support/admin-reply') in got
