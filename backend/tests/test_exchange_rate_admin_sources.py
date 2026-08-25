"""Tests for the admin-facing exchange-rate endpoints added 2026-08-25
(backend/exchange_rate_admin.py): the DB-editable flat Toman markup, and
CRUD for admin-configured exchange-rate sources (Bonbast.com plus any
custom_regex source an admin adds). Mounts just this router standalone,
same pattern as tests/test_exchange_rate_source.py's
TestExchangeRateAdminEndpoint -- this agent does not own app.py, so the
router is not wired into the real app yet; that include_router line is the
coordinator's to add.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import exchange_rate_admin
from tests.conftest import make_result, make_row


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(exchange_rate_admin.router)
    return TestClient(app)


def _admin_ok():
    return patch.object(exchange_rate_admin, 'admin_required', new=AsyncMock(return_value=True))


def _admin_denied():
    return patch.object(exchange_rate_admin, 'admin_required', new=AsyncMock(return_value=False))


# ── Flat markup ────────────────────────────────────────────────────────────

class TestFlatMarkupEndpoints:
    def test_get_requires_admin(self, client):
        with _admin_denied():
            resp = client.get('/admin/exchange-rate/flat-markup')
        assert resp.status_code == 401

    def test_get_returns_value_and_default(self, client):
        with _admin_ok(), \
             patch('services.exchange_sources.get_flat_markup_toman', new=AsyncMock(return_value=3500.0)):
            resp = client.get('/admin/exchange-rate/flat-markup')
        assert resp.status_code == 200
        body = resp.json()
        assert body['flat_markup_toman'] == 3500.0
        assert body['default_toman'] == 2000.0

    def test_post_requires_admin(self, client):
        with _admin_denied():
            resp = client.post('/admin/exchange-rate/flat-markup', json={'flat_markup_toman': 3000})
        assert resp.status_code == 401

    def test_post_rejects_negative(self, client, mock_async_session):
        with _admin_ok():
            resp = client.post('/admin/exchange-rate/flat-markup', json={'flat_markup_toman': -1})
        assert resp.status_code == 400

    def test_post_rejects_absurdly_large(self, client, mock_async_session):
        with _admin_ok():
            resp = client.post('/admin/exchange-rate/flat-markup', json={'flat_markup_toman': 10_000_000})
        assert resp.status_code == 400

    def test_post_rejects_non_numeric(self, client, mock_async_session):
        with _admin_ok():
            resp = client.post('/admin/exchange-rate/flat-markup', json={'flat_markup_toman': 'a lot'})
        assert resp.status_code == 400

    def test_post_accepts_zero(self, client, mock_async_session):
        with _admin_ok(), \
             patch.object(exchange_rate_admin, '_write_audit_log', new=AsyncMock()), \
             patch.object(exchange_rate_admin, 'rds', AsyncMock()):
            resp = client.post('/admin/exchange-rate/flat-markup', json={'flat_markup_toman': 0})
        assert resp.status_code == 200
        assert resp.json()['flat_markup_toman'] == 0.0

    def test_post_writes_correct_setting_key_and_invalidates_caches(self, client, mock_async_session):
        captured = {}

        async def capture_execute(stmt, params=None):
            captured['sql'] = str(stmt)
            captured['params'] = params
            return mock_async_session._execute_result

        mock_async_session.execute = capture_execute
        mock_rds = AsyncMock()
        with _admin_ok(), \
             patch.object(exchange_rate_admin, '_write_audit_log', new=AsyncMock()), \
             patch.object(exchange_rate_admin, 'rds', mock_rds):
            resp = client.post('/admin/exchange-rate/flat-markup', json={'flat_markup_toman': 4200})
        assert resp.status_code == 200
        assert captured['params']['key'] == 'usd_irt_flat_markup_toman'
        assert 'app_setting' in captured['sql']
        mock_rds.delete.assert_awaited_once()
        deleted_keys = mock_rds.delete.await_args.args
        assert 'cache:catalog:models' in deleted_keys
        assert 'cache:catalog:pricing' in deleted_keys
        assert 'cache:api:pricing' in deleted_keys
        assert 'exchange_rate:usd_irt:resolved' in deleted_keys or any('exchange_rate' in k for k in deleted_keys)


# ── Sources list ───────────────────────────────────────────────────────────

class TestListSources:
    def test_requires_admin(self, client):
        with _admin_denied():
            resp = client.get('/admin/exchange-rate/sources')
        assert resp.status_code == 401

    def test_returns_builtin_and_configured(self, client, mock_async_session):
        # `.mapping`-style row: the endpoint does dict(r._mapping), so
        # _mapping must be a real dict here, not an auto-generated MagicMock
        # attribute (which does not behave like one).
        row = MagicMock()
        row._mapping = {
            'source_key': 'bonbast', 'display_name': 'Bonbast.com', 'kind': 'bonbast',
            'url': 'https://bonbast.com/', 'unit': 'toman', 'extract_regex': None,
            'enabled': True, 'priority': 20, 'timeout_s': 8, 'is_builtin': True, 'updated_at': None,
        }
        mock_async_session._execute_result = make_result(fetchall=[row])
        with _admin_ok():
            resp = client.get('/admin/exchange-rate/sources')
        assert resp.status_code == 200
        body = resp.json()
        assert any(b['source_key'] == 'tgju' and b['editable'] is False for b in body['builtin'])
        assert len(body['configured']) == 1
        assert body['configured'][0]['source_key'] == 'bonbast'
        assert body['configured'][0]['deletable'] is False  # is_builtin=True


# ── Create source ────────────────────────────────────────────────────────

class TestCreateSource:
    _valid_payload = {
        'source_key': 'mysite', 'display_name': 'My Site',
        'url': 'https://example.com/rate', 'unit': 'toman',
        'extract_regex': r'USD\s*=\s*([\d,]+)', 'priority': 50, 'timeout_s': 5,
    }

    def test_requires_admin(self, client):
        with _admin_denied():
            resp = client.post('/admin/exchange-rate/sources', json=self._valid_payload)
        assert resp.status_code == 401

    def test_rejects_reserved_source_key(self, client, mock_async_session):
        with _admin_ok():
            resp = client.post('/admin/exchange-rate/sources', json={**self._valid_payload, 'source_key': 'tgju'})
        assert resp.status_code == 400

    def test_rejects_bad_source_key_format(self, client, mock_async_session):
        with _admin_ok():
            resp = client.post('/admin/exchange-rate/sources', json={**self._valid_payload, 'source_key': 'My Site!'})
        assert resp.status_code == 400

    def test_rejects_http_url(self, client, mock_async_session):
        with _admin_ok():
            resp = client.post('/admin/exchange-rate/sources', json={**self._valid_payload, 'url': 'http://example.com'})
        assert resp.status_code == 400

    def test_rejects_bad_regex(self, client, mock_async_session):
        with _admin_ok():
            resp = client.post('/admin/exchange-rate/sources', json={**self._valid_payload, 'extract_regex': '(unclosed'})
        assert resp.status_code == 400

    def test_rejects_bad_unit(self, client, mock_async_session):
        with _admin_ok():
            resp = client.post('/admin/exchange-rate/sources', json={**self._valid_payload, 'unit': 'usd'})
        assert resp.status_code == 400

    def test_success_creates_and_invalidates_caches(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(scalar_one=42)
        mock_rds = AsyncMock()
        with _admin_ok(), \
             patch.object(exchange_rate_admin, '_write_audit_log', new=AsyncMock()), \
             patch.object(exchange_rate_admin, 'rds', mock_rds):
            resp = client.post('/admin/exchange-rate/sources', json=self._valid_payload)
        assert resp.status_code == 201
        assert resp.json()['source_key'] == 'mysite'
        mock_rds.delete.assert_awaited_once()


# ── Update / delete source ─────────────────────────────────────────────────

class TestUpdateDeleteSource:
    def test_update_requires_admin(self, client):
        with _admin_denied():
            resp = client.patch('/admin/exchange-rate/sources/mysite', json={'enabled': False})
        assert resp.status_code == 401

    def test_update_not_found(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with _admin_ok():
            resp = client.patch('/admin/exchange-rate/sources/doesnotexist', json={'enabled': False})
        assert resp.status_code == 404

    def test_update_no_fields_is_400(self, client, mock_async_session):
        with _admin_ok():
            resp = client.patch('/admin/exchange-rate/sources/mysite', json={})
        assert resp.status_code == 400

    def test_update_success(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(id=1))
        mock_rds = AsyncMock()
        with _admin_ok(), \
             patch.object(exchange_rate_admin, '_write_audit_log', new=AsyncMock()), \
             patch.object(exchange_rate_admin, 'rds', mock_rds):
            resp = client.patch('/admin/exchange-rate/sources/bonbast', json={'enabled': False, 'priority': 15})
        assert resp.status_code == 200
        mock_rds.delete.assert_awaited_once()

    def test_delete_requires_admin(self, client):
        with _admin_denied():
            resp = client.delete('/admin/exchange-rate/sources/mysite')
        assert resp.status_code == 401

    def test_delete_builtin_rejected(self, client, mock_async_session):
        # The SQL itself filters `is_builtin = FALSE`, so a builtin row
        # never matches and fetchone() comes back empty -- simulated here.
        mock_async_session._execute_result = make_result(fetchone=None)
        with _admin_ok():
            resp = client.delete('/admin/exchange-rate/sources/bonbast')
        assert resp.status_code == 404

    def test_delete_custom_source_success(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(id=1))
        mock_rds = AsyncMock()
        with _admin_ok(), \
             patch.object(exchange_rate_admin, '_write_audit_log', new=AsyncMock()), \
             patch.object(exchange_rate_admin, 'rds', mock_rds):
            resp = client.delete('/admin/exchange-rate/sources/mysite')
        assert resp.status_code == 200
        mock_rds.delete.assert_awaited_once()
