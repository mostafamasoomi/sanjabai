"""Tests for backend/middleware/maintenance.py -- the maintenance_mode
site-control switch (migrations/0036_site_settings.sql seeds the flag;
site_settings.py stores/reads it; this middleware is what actually turns it
into behaviour: a 503 for ordinary traffic).

Style mirrors tests/test_site_settings.py: a standalone FastAPI app (the
middleware is not registered in app.py yet -- that's the coordinator's
change) carrying a handful of routes representative of the real router
layout, so exempt-prefix behaviour is exercised against paths that
actually mirror production ones.

Exempt prefixes were verified against the real routers before being
hardcoded in middleware/maintenance.py:
    /health           -> health.py           (router = APIRouter(), no prefix)
    /admin            -> admin.py, admin_catalog.py, admin_packages.py,
                          site_settings.py, exchange_rate_admin.py, and
                          auth.py's POST /admin/login + POST /admin/logout
    /auth/login        -> auth.py: POST /auth/login
    /auth/logout       -> auth.py: POST /auth/logout, POST /auth/logout-all
    /status            -> status_page.py: GET /status/summary,
                          POST /admin/status/incident (already under /admin)

`/auth/admin-login` does NOT exist anywhere in this codebase -- admin login
is `POST /admin/login`, already covered by the `/admin` prefix -- so it is
deliberately not in the exempt list and not tested here.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import dependencies
import site_settings
from middleware.maintenance import MaintenanceModeMiddleware


# ── Test app: a handful of routes standing in for the real routers ────────

def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(MaintenanceModeMiddleware)

    @app.get('/v1/chat/completions')
    async def ordinary_chat():
        return {'ok': True}

    @app.get('/wallet')
    async def ordinary_wallet():
        return {'ok': True}

    @app.get('/health')
    async def health():
        return {'ok': True}

    @app.get('/health/detailed')
    async def health_detailed():
        return {'ok': True}

    @app.get('/admin/site-settings')
    async def admin_site_settings():
        return {'ok': True}

    @app.post('/auth/login')
    async def auth_login():
        return {'ok': True}

    @app.post('/auth/logout')
    async def auth_logout():
        return {'ok': True}

    @app.get('/status/summary')
    async def status_summary():
        return {'ok': True}

    return app


@pytest.fixture
def app_client():
    return TestClient(_build_app())


@pytest.fixture
def maintenance_off():
    with patch.object(site_settings, 'get_site_flag', new=AsyncMock(return_value=False)):
        yield


@pytest.fixture
def maintenance_on():
    with patch.object(site_settings, 'get_site_flag', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def maintenance_flag_raises():
    with patch.object(site_settings, 'get_site_flag', new=AsyncMock(side_effect=RuntimeError('redis+db both down'))):
        yield


@pytest.fixture
def admin_ok():
    with patch.object(dependencies, 'admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def admin_denied():
    with patch.object(dependencies, 'admin_required', new=AsyncMock(return_value=False)):
        yield


# ── Behaviour ───────────────────────────────────────────────────────────

class TestMaintenanceModeOff:
    def test_ordinary_route_returns_200_when_flag_off(self, app_client, maintenance_off, admin_denied):
        resp = app_client.get('/v1/chat/completions')
        assert resp.status_code == 200


class TestMaintenanceModeOn:
    def test_ordinary_route_returns_503_for_ordinary_user(self, app_client, maintenance_on, admin_denied):
        resp = app_client.get('/v1/chat/completions')
        assert resp.status_code == 503
        body = resp.json()
        assert 'تعمیر' in body['detail']

    def test_second_ordinary_route_also_blocked(self, app_client, maintenance_on, admin_denied):
        resp = app_client.get('/wallet')
        assert resp.status_code == 503

    def test_admin_still_gets_through(self, app_client, maintenance_on, admin_ok):
        resp = app_client.get('/v1/chat/completions')
        assert resp.status_code == 200

    @pytest.mark.parametrize('method,path', [
        ('GET', '/health'),
        ('GET', '/health/detailed'),
        ('GET', '/admin/site-settings'),
        ('POST', '/auth/login'),
        ('POST', '/auth/logout'),
        ('GET', '/status/summary'),
    ])
    def test_exempt_prefix_reachable_even_for_non_admin(self, app_client, maintenance_on, admin_denied, method, path):
        resp = app_client.request(method, path)
        assert resp.status_code != 503

    def test_options_preflight_not_blocked(self, app_client, maintenance_on, admin_denied):
        resp = app_client.options('/v1/chat/completions')
        assert resp.status_code != 503


class TestMaintenanceModeFailsOpen:
    def test_flag_read_error_lets_traffic_through(self, app_client, maintenance_flag_raises, admin_denied):
        """The core guard this file exists to prove: a settings-store
        outage must never take the whole site down. If get_site_flag()
        raises for any reason, ordinary traffic must still reach the
        route -- not get a fabricated 503."""
        resp = app_client.get('/v1/chat/completions')
        assert resp.status_code == 200
