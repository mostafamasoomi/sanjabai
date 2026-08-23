"""GET /admin/security/stats -- the endpoint the panel's «امنیت» page needs.

The page shipped against this route before it existed; the 404 was swallowed
by Promise.allSettled and the page showed a loading skeleton forever (session
11 audit A3). These tests pin the contract the frontend already declares
(SecurityStats in AdminPanel.tsx) so the two cannot drift apart again, and
guard the auth gate.

Mocked DB/Redis per tests/conftest.py -- no live services. The SQL these
queries run is separately validated against the real schema by
scripts/sql_schema_audit.py, since a mocked session cannot catch a bad column.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import admin_security
from tests.conftest import make_result


@pytest.fixture
def admin_ok():
    with patch.object(admin_security.admin, 'admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def admin_denied():
    with patch.object(admin_security.admin, 'admin_required', new=AsyncMock(return_value=False)):
        yield


@pytest.fixture
def app_client():
    app = FastAPI()
    app.include_router(admin_security.router)
    return TestClient(app)


class TestAuthGate:
    def test_denied_without_admin(self, app_client, admin_denied, mock_async_session):
        resp = app_client.get('/admin/security/stats')
        assert resp.status_code == 401


class TestContract:
    """Every field SecurityStats (frontend) reads must be present and correctly
    typed, so the panel never renders `undefined`."""

    def _run(self, app_client, mock_async_session, *, failed, chart, banned, sessions, lockouts):
        # execute() is called three times in order: failed count, chart, banned.
        results = iter([
            make_result(fetchone=type('R', (), {'c': failed})()),
            make_result(fetchall=chart),
            make_result(fetchall=banned),
        ])

        async def exec_side_effect(*a, **k):
            return next(results)

        mock_async_session.execute = exec_side_effect

        async def fake_scan(match=None, count=500):
            keys = {"session:*": sessions, "lockout:*": lockouts}.get(match, 0)
            for i in range(keys):
                yield f"{match}:{i}"

        with patch.object(admin_security.rds, 'scan_iter', fake_scan):
            return app_client.get('/admin/security/stats')

    def test_full_shape_and_threat_levels(self, app_client, admin_ok, mock_async_session):
        resp = self._run(app_client, mock_async_session,
                          failed=0, chart=[], banned=[], sessions=3, lockouts=0)
        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {'threat_level', 'failed_logins_24h', 'active_sessions',
                             'failed_login_chart', 'banned_users'}
        assert body['threat_level'] == 'low'
        assert body['failed_logins_24h'] == 0
        assert body['active_sessions'] == 3
        assert body['failed_login_chart'] == []
        assert body['banned_users'] == []

    def test_threat_high_on_active_lockout(self, app_client, admin_ok, mock_async_session):
        resp = self._run(app_client, mock_async_session,
                         failed=2, chart=[], banned=[], sessions=1, lockouts=1)
        assert resp.json()['threat_level'] == 'high'

    def test_threat_critical_on_failure_burst(self, app_client, admin_ok, mock_async_session):
        resp = self._run(app_client, mock_async_session,
                         failed=120, chart=[], banned=[], sessions=1, lockouts=0)
        assert resp.json()['threat_level'] == 'critical'

    def test_threat_medium_band(self, app_client, admin_ok, mock_async_session):
        resp = self._run(app_client, mock_async_session,
                         failed=15, chart=[], banned=[], sessions=1, lockouts=0)
        assert resp.json()['threat_level'] == 'medium'
