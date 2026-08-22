"""Tests for backend/site_settings.py -- the admin-editable runtime
site-control switches (migrations/0036_site_settings.sql extends the
existing `app_setting` key/value store, no new table).

Style mirrors tests/test_admin_packages.py (a standalone FastAPI app
carrying just this router, so the endpoint tests stay independent of the
full app wiring) and tests/test_markup.py's TestGetGlobalMarkupPct class
(the fail-open / cache-then-DB pattern for the read helper).

The router IS registered in app.py. The flags' actual call sites are
covered by tests/test_site_flag_wiring.py (signup/chat/images),
tests/test_maintenance_mode.py and tests/test_env_flag_db_override.py
(scheduler/OpenRouter); what this file guards is the store itself, plus
the invariant that a flag advertised to the admin as wired really does
have a reader.
"""
from __future__ import annotations

from pathlib import Path
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

    # ── Only a real boolean is a flag ────────────────────────────────────
    #
    # The store always writes json.dumps(bool), and the live database was
    # checked directly: every row comes back from asyncpg as a Python bool.
    # Anything else is a corrupt or hand-edited row, and it must fall back
    # to the registered default rather than be coerced.
    #
    # This replaced a plain `bool(raw)`, which was wrong in the one
    # direction that matters: bool('false') is True and bool(1) is True, so
    # a single mistyped row would have read as "maintenance mode ON" and
    # taken the entire site down -- with the admin panel showing the same
    # wrong answer back, so the owner could not even see why.

    @pytest.mark.asyncio
    @pytest.mark.parametrize('junk', ['false', 'true', 1, 0, '', 'yes', [], {}, 3.5])
    async def test_non_boolean_db_value_falls_back_to_default(self, junk, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(value=junk))
        with patch.object(site_settings.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(site_settings.rds, 'setex', new=AsyncMock()):
            value = await site_settings.get_site_flag('maintenance_mode')
        # maintenance_mode defaults to False. The string 'false' and the
        # integer 1 are the two that a naive bool() would have turned into
        # a site-wide outage.
        assert value is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize('junk', ['"false"', '1', '0', '"yes"', '[]', '3.5'])
    async def test_non_boolean_cached_value_falls_back_to_default(self, junk):
        with patch.object(site_settings.rds, 'get', new=AsyncMock(return_value=junk)):
            value = await site_settings.get_site_flag('maintenance_mode')
        assert value is False

    @pytest.mark.asyncio
    async def test_real_booleans_are_still_honoured_in_both_directions(self, mock_async_session):
        """The strictness must not swallow legitimate values."""
        for stored, expected in ((True, True), (False, False)):
            mock_async_session._execute_result = make_result(fetchone=make_row(value=stored))
            with patch.object(site_settings.rds, 'get', new=AsyncMock(return_value=None)), \
                 patch.object(site_settings.rds, 'setex', new=AsyncMock()):
                assert await site_settings.get_site_flag('maintenance_mode') is expected
        for cached, expected in (('true', True), ('false', False)):
            with patch.object(site_settings.rds, 'get', new=AsyncMock(return_value=cached)):
                assert await site_settings.get_site_flag('chat_enabled') is expected


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

    def test_every_flag_carries_a_wire_note(self, app_client, admin_ok, mock_async_session):
        """Every switch must explain, in the panel, what it actually does."""
        mock_async_session._execute_result = make_result(fetchall=[])
        resp = app_client.get('/admin/site-settings')
        flags = {f['key']: f for f in resp.json()['flags']}
        for key in site_settings.FLAGS:
            assert flags[key]['wire_note'], f'{key} has no wire_note'

    def test_wired_bit_is_not_a_claim_nobody_checks(self):
        """A flag marked ``wired=True`` must have a real reader in the source.

        This is the guard that matters. The original version of this test
        asserted every flag was ``wired=False``, which was true when the
        store shipped ahead of its call sites -- but it only pinned a
        snapshot, so the moment the flags were wired the test had to be
        rewritten anyway, and nothing then stopped someone flipping
        ``wired=True`` on a flag they never actually wired.

        That specific failure -- a control that reports success and changes
        nothing -- is the exact bug class this whole section exists to
        remove (see the admin user-edit modal and the developer-panel
        button, both of which confirmed writes that no code ever read). So
        this scans the real backend sources for a literal
        ``get_site_flag('<key>')`` call, the same static-source-scan idiom
        tests/test_credit_paths.py uses to keep the wallet honest. A flag
        can only be labelled wired in the panel if the code truly reads it.
        """
        backend_dir = Path(__file__).resolve().parent.parent
        sources = []
        for path in backend_dir.rglob('*.py'):
            parts = set(path.parts)
            if 'tests' in parts or '__pycache__' in parts:
                continue
            if path.name == 'site_settings.py':
                continue  # the store itself, not a consumer
            sources.append(path.read_text(encoding='utf-8'))
        haystack = '\n'.join(sources)

        for key, meta in site_settings.FLAGS.items():
            called = (
                f"get_site_flag('{key}')" in haystack
                or f'get_site_flag("{key}")' in haystack
            )
            if meta.wired:
                assert called, (
                    f'{key} is labelled wired=True in the admin panel but no '
                    f"backend module calls get_site_flag('{key}') -- the panel "
                    f'would be promising a control that does nothing'
                )
            else:
                assert not called, (
                    f'{key} IS read by the backend but is still labelled '
                    f'wired=False -- update its FlagMeta and wire_note'
                )

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
