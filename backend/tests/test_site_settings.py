"""Tests for backend/site_settings.py -- the admin-editable runtime
site-control switches (migrations/0036_site_settings.sql extends the
existing `app_setting` key/value store, no new table).

Style mirrors tests/test_admin_packages.py (standalone FastAPI app carrying
just this router, since site_settings is not wired into app.py yet -- that
include_router line is the coordinator's to add) and
tests/test_markup.py's TestGetGlobalMarkupPct class (the fail-open /
cache-then-DB pattern for the read helper).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import site_settings
from tests.conftest import make_result, make_row


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def admin_ok():
    with patch.object(site_settings, 'admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def admin_denied():
    with patch.object(site_settings, 'admin_required', new=AsyncMock(return_value=False)):
        yield


@pytest.fixture
def app_client():
    app = FastAPI()
    app.include_router(site_settings.router)
    return TestClient(app)


# ── get_site_flag: the fail-open read helper other modules will call ──────

class TestGetSiteFlag:
    @pytest.mark.asyncio
    async def test_unknown_key_fails_open_to_false(self):
        assert await site_settings.get_site_flag('not_a_real_flag') is False

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value_without_touching_db(self):
        with patch.object(site_settings.rds, 'get', new=AsyncMock(return_value='true')):
            value = await site_settings.get_site_flag('chat_enabled')
        assert value is True

    @pytest.mark.asyncio
    async def test_cache_miss_reads_db_and_populates_cache(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(value=False))
        with patch.object(site_settings.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(site_settings.rds, 'setex', new=AsyncMock()) as mock_setex:
            value = await site_settings.get_site_flag('maintenance_mode')
        assert value is False
        mock_setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_row_in_db_falls_back_to_registered_default(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(site_settings.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(site_settings.rds, 'setex', new=AsyncMock()):
            value = await site_settings.get_site_flag('signups_enabled')
        assert value is site_settings.FLAGS['signups_enabled'].default is True

    @pytest.mark.asyncio
    async def test_db_error_fails_open_to_default_not_restrictive(self, mock_async_session):
        """🔴 THE core guard this file exists to prove: a settings-store
        outage must never take the site down. signups_enabled defaults to
        True (today's real behaviour); a DB error here must still return
        True, not silently start rejecting every signup."""
        async def _boom(*a, **k):
            raise RuntimeError('db down')
        mock_async_session.execute = _boom
        with patch.object(site_settings.rds, 'get', new=AsyncMock(return_value=None)):
            value = await site_settings.get_site_flag('signups_enabled')
        assert value is True

    @pytest.mark.asyncio
    async def test_redis_read_error_falls_through_to_db_not_straight_to_default(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(value=False))
        with patch.object(site_settings.rds, 'get', new=AsyncMock(side_effect=Exception('redis down'))), \
             patch.object(site_settings.rds, 'setex', new=AsyncMock()):
            value = await site_settings.get_site_flag('chat_enabled')
        # chat_enabled defaults True, but the DB row here explicitly says
        # False -- a cache-read error alone must not discard that real value.
        assert value is False

    @pytest.mark.asyncio
    async def test_no_db_configured_falls_back_to_default(self):
        with patch.object(site_settings, 'async_session', None), \
             patch.object(site_settings.rds, 'get', new=AsyncMock(return_value=None)):
            value = await site_settings.get_site_flag('image_generation_enabled')
        assert value is True


# ── GET /admin/site-settings ──────────────────────────────────────────────

class TestGetSiteSettings:
    def test_requires_admin(self, app_client, admin_denied):
        resp = app_client.get('/admin/site-settings')
        assert resp.status_code == 401

    def test_returns_every_known_flag(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[])
        resp = app_client.get('/admin/site-settings')
        assert resp.status_code == 200
        body = resp.json()
        keys = {f['key'] for f in body['flags']}
        assert keys == set(site_settings.FLAGS)

    def test_missing_row_reports_default_and_row_missing_true(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[])
        resp = app_client.get('/admin/site-settings')
        flags = {f['key']: f for f in resp.json()['flags']}
        assert flags['signups_enabled']['value'] is True
        assert flags['signups_enabled']['row_missing'] is True

    def test_db_value_overrides_default(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchall=[make_row(flag_key='signups_enabled', value=False)]
        )
        resp = app_client.get('/admin/site-settings')
        flags = {f['key']: f for f in resp.json()['flags']}
        assert flags['signups_enabled']['value'] is False
        assert flags['signups_enabled']['row_missing'] is False

    def test_unwired_flags_are_labelled_as_such(self, app_client, admin_ok, mock_async_session):
        """The scope rule this project cares about: a switch that controls
        nothing yet must never be presented as if it does."""
        mock_async_session._execute_result = make_result(fetchall=[])
        resp = app_client.get('/admin/site-settings')
        flags = {f['key']: f for f in resp.json()['flags']}
        for key in site_settings.FLAGS:
            assert flags[key]['wired'] is False
            assert flags[key]['wire_note']

    def test_db_error_returns_500_never_a_fabricated_all_off_payload(self, app_client, admin_ok, mock_async_session):
        """A failed fetch must surface as an error -- showing every switch
        as off when the truth is unknown is a lie the owner could act on."""
        async def _boom(*a, **k):
            raise RuntimeError('db down')
        mock_async_session.execute = _boom
        resp = app_client.get('/admin/site-settings')
        assert resp.status_code == 500
        assert 'flags' not in resp.json()


# ── POST /admin/site-settings ──────────────────────────────────────────────

class TestUpdateSiteSettings:
    def test_requires_admin(self, app_client, admin_denied):
        resp = app_client.post('/admin/site-settings', json={'chat_enabled': False})
        assert resp.status_code == 401

    def test_empty_payload_rejected(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/site-settings', json={})
        assert resp.status_code == 400

    def test_unknown_key_rejected(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/site-settings', json={'not_a_real_flag': True})
        assert resp.status_code == 400

    def test_non_bool_value_rejected(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/site-settings', json={'chat_enabled': 'yes'})
        assert resp.status_code == 400

    def test_int_value_rejected_not_coerced(self, app_client, admin_ok, mock_async_session):
        """1/0 must not be silently accepted as True/False -- an admin
        control switch should reject anything that isn't a real boolean."""
        resp = app_client.post('/admin/site-settings', json={'chat_enabled': 1})
        assert resp.status_code == 400

    def test_valid_single_flag_update_succeeds(self, app_client, admin_ok, mock_async_session):
        with patch.object(site_settings, '_write_audit_log', new=AsyncMock()):
            resp = app_client.post('/admin/site-settings', json={'maintenance_mode': True})
        assert resp.status_code == 200
        assert resp.json()['updated'] == {'maintenance_mode': True}

    def test_valid_multi_flag_update_succeeds(self, app_client, admin_ok, mock_async_session):
        with patch.object(site_settings, '_write_audit_log', new=AsyncMock()):
            resp = app_client.post(
                '/admin/site-settings',
                json={'chat_enabled': False, 'signups_enabled': False},
            )
        assert resp.status_code == 200
        assert resp.json()['updated'] == {'chat_enabled': False, 'signups_enabled': False}

    def test_cache_invalidated_on_write(self, app_client, admin_ok, mock_async_session):
        with patch.object(site_settings, '_write_audit_log', new=AsyncMock()), \
             patch.object(site_settings.rds, 'delete', new=AsyncMock()) as mock_delete:
            resp = app_client.post('/admin/site-settings', json={'chat_enabled': False})
        assert resp.status_code == 200
        mock_delete.assert_awaited_once_with(site_settings._cache_key('chat_enabled'))

    def test_audit_entry_written_with_every_changed_key(self, app_client, admin_ok, mock_async_session):
        with patch.object(site_settings, '_write_audit_log', new=AsyncMock()) as mock_audit:
            resp = app_client.post(
                '/admin/site-settings',
                json={'chat_enabled': False, 'openrouter_enabled': True},
            )
        assert resp.status_code == 200
        mock_audit.assert_awaited_once()
        args, kwargs = mock_audit.call_args
        assert args[0] == 'admin.site_settings.update'
        assert kwargs['target_type'] == 'site_setting'
        assert kwargs['details'] == {'chat_enabled': False, 'openrouter_enabled': True}
