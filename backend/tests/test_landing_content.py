"""Tests for the landing page content override store -- B-LAND phase 6.

Covers backend/landing_content.py (public, cached, fail-open GET
/landing/content) and backend/admin_landing.py (the admin write/delete
API), introduced alongside migration 0052_landing_content.sql.

Style follows tests/test_watchdog_settings.py: a standalone FastAPI app
carrying just these two routers (they are not wired into app.py by this
packet -- see the packet's report for the exact include_router lines the
senior still needs to add), plus the conftest ``mock_async_session`` /
``make_result`` helpers for the DB layer and a local ``_MappingRow`` stand-in
for ``_mapping`` (conftest's ``make_row()`` returns a plain MagicMock whose
auto-mocked ``_mapping`` is not itself dict-like -- see
tests/test_catalog_endpoint.py, same fix, same reason).

The invariants this file exists to hold, in priority order:

 1. HONEST LABELLING. A live-counted claim (see landing_content.py's
    FROZEN_PATHS docstring) can never be written through the admin API,
    no matter what key or shape it arrives in.
 2. BOUNDED KEY SPACE. Only the thirteen known frontend module names are
    ever writable -- this table can never become an arbitrary key/value
    dump.
 3. FAIL OPEN, NEVER 500. The public GET must degrade to "no overrides"
    on any DB fault, because the landing page must render even when this
    feature is broken.
 4. SIZE-BOUNDED. No single override may exceed MAX_VALUE_BYTES.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import admin_landing
import landing_content
from tests.conftest import make_result


class _MappingRow:
    """Minimal stand-in for a SQLAlchemy Row exposing `_mapping` as a real
    dict -- see module docstring."""

    def __init__(self, **kwargs):
        self._mapping = dict(kwargs)


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def no_cache():
    """Redis miss on read, no-op on write/delete -- every test in this file
    exercises the DB path unless it explicitly overrides this."""
    with patch('database.rds.get', new=AsyncMock(return_value=None)), \
         patch('database.rds.setex', new=AsyncMock()), \
         patch('database.rds.delete', new=AsyncMock()):
        yield


@pytest.fixture
def admin_ok():
    with patch.object(admin_landing, 'admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def admin_denied():
    with patch.object(admin_landing, 'admin_required', new=AsyncMock(return_value=False)):
        yield


@pytest.fixture
def app_client():
    app = FastAPI()
    app.include_router(landing_content.router)
    app.include_router(admin_landing.router)
    return TestClient(app)


# ── Public GET /landing/content ───────────────────────────────────────────

class TestPublicGet:
    def test_empty_table_returns_empty_data(self, mock_async_session, no_cache, app_client):
        mock_async_session._execute_result = make_result(fetchall=[])
        res = app_client.get('/landing/content')
        assert res.status_code == 200
        assert res.json() == {'data': {}, 'updated_at': None}

    def test_returns_stored_overrides(self, mock_async_session, no_cache, app_client):
        rows = [
            _MappingRow(key='hero', value={'title': 'X'}, updated_at=None),
            _MappingRow(key='footer', value={'text': 'Y'}, updated_at=None),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        res = app_client.get('/landing/content')
        assert res.status_code == 200
        body = res.json()
        assert body['data'] == {'hero': {'title': 'X'}, 'footer': {'text': 'Y'}}

    def test_db_error_fails_open_not_500(self, mock_async_session, no_cache, app_client):
        """Mutation target: flipping this fail-open branch to re-raise (or
        to a bare `return err(...)` 500) must turn this test red."""
        mock_async_session.execute = AsyncMock(side_effect=Exception('db down'))
        res = app_client.get('/landing/content')
        assert res.status_code == 200
        assert res.json() == {'data': {}, 'updated_at': None}

    def test_redis_error_falls_through_to_db(self, mock_async_session, app_client):
        """A Redis-only fault must not blank out working DB overrides."""
        mock_async_session._execute_result = make_result(fetchall=[
            _MappingRow(key='hero', value={'title': 'X'}, updated_at=None),
        ])
        with patch('database.rds.get', new=AsyncMock(side_effect=Exception('redis down'))), \
             patch('database.rds.setex', new=AsyncMock()):
            res = app_client.get('/landing/content')
        assert res.status_code == 200
        assert res.json()['data'] == {'hero': {'title': 'X'}}

    def test_cache_hit_skips_db(self, mock_async_session, app_client):
        # A spy, not a side-effect-raising mock: the fail-open try/except
        # around the DB read would otherwise swallow an exception raised
        # here and silently turn a real bug into a false-green 200.
        cached = json.dumps({'data': {'hero': {'title': 'cached'}}, 'updated_at': None})
        mock_async_session.execute = AsyncMock(return_value=make_result(fetchall=[]))
        with patch('database.rds.get', new=AsyncMock(return_value=cached)):
            res = app_client.get('/landing/content')
        assert res.status_code == 200
        assert res.json()['data'] == {'hero': {'title': 'cached'}}
        mock_async_session.execute.assert_not_awaited()


# ── Admin GET /admin/landing/content ──────────────────────────────────────

class TestAdminGet:
    def test_requires_admin(self, admin_denied, app_client):
        res = app_client.get('/admin/landing/content')
        assert res.status_code == 401

    def test_lists_allowed_keys_and_frozen_paths(self, mock_async_session, admin_ok, app_client):
        mock_async_session._execute_result = make_result(fetchall=[])
        res = app_client.get('/admin/landing/content')
        assert res.status_code == 200
        body = res.json()
        assert set(body['allowedKeys']) == set(landing_content.ALLOWED_KEYS)
        assert body['frozenPaths']['stats'] == ['items.0.value']
        assert body['overrides'] == {}


# ── Admin PUT /admin/landing/content/{key} ────────────────────────────────

class TestAdminPut:
    def test_requires_admin(self, admin_denied, app_client):
        res = app_client.put('/admin/landing/content/hero', json={'value': {'a': 1}})
        assert res.status_code == 401

    def test_unknown_key_rejected(self, admin_ok, app_client):
        res = app_client.put('/admin/landing/content/not_a_real_module', json={'value': {}})
        assert res.status_code == 400
        assert 'detail' in res.json() and 'detail_en' in res.json()

    def test_missing_value_field_rejected(self, admin_ok, app_client):
        res = app_client.put('/admin/landing/content/hero', json={})
        assert res.status_code == 400

    def test_frozen_path_rejected(self, admin_ok, app_client):
        """The single most important guard in this packet: a payload that
        fills in stats.items[0].value (the live model-count claim) must
        never be accepted, no matter that it's a spec-shaped payload."""
        payload = {
            'value': {
                'items': [
                    {'value': '9999', 'label': 'model active'},
                ],
            },
        }
        res = app_client.put('/admin/landing/content/stats', json=payload)
        assert res.status_code == 400
        body = res.json()
        assert 'items.0.value' in body['detail_en']

    def test_frozen_key_non_frozen_path_is_allowed(self, mock_async_session, no_cache, admin_ok, app_client):
        """Editing stats.items[1] (the static "Toman" unit label) must stay
        writable -- freezing is per-path, not per-key."""
        payload = {'value': {'items': [{'other': 'field'}, {'value': 'Toman'}]}}
        res = app_client.put('/admin/landing/content/stats', json=payload)
        assert res.status_code == 200

    def test_frozen_path_rejected_for_comparison_pricing_faq(self, admin_ok, app_client):
        cases = {
            'comparison': {'rows': [{'sanjabai': 'x'}]},
            'pricing': {'columns': [None, {'features': [1, 2, 3, 'x']}]},
            'faq': {'items': [{'a': 'x'}]},
        }
        for key, value in cases.items():
            res = app_client.put(f'/admin/landing/content/{key}', json={'value': value})
            assert res.status_code == 400, f'{key} did not reject its frozen path'

    def test_value_over_size_cap_rejected(self, admin_ok, app_client):
        huge = {'text': 'x' * (landing_content.MAX_VALUE_BYTES + 1)}
        res = app_client.put('/admin/landing/content/hero', json={'value': huge})
        assert res.status_code == 413

    def test_put_upserts_and_invalidates_cache(self, mock_async_session, admin_ok, app_client):
        with patch('database.rds.delete', new=AsyncMock()) as mock_delete:
            res = app_client.put('/admin/landing/content/hero', json={'value': {'title': 'New hero'}})
        assert res.status_code == 200
        assert res.json() == {'status': 'ok', 'key': 'hero', 'value': {'title': 'New hero'}}
        mock_delete.assert_awaited_once_with('cache:landing:content')

    def test_put_then_admin_get_reflects_value(self, mock_async_session, no_cache, admin_ok, app_client):
        res = app_client.put('/admin/landing/content/hero', json={'value': {'title': 'New hero'}})
        assert res.status_code == 200

        mock_async_session._execute_result = make_result(fetchall=[
            _MappingRow(key='hero', value={'title': 'New hero'}, updated_at=None, updated_by=None),
        ])
        res2 = app_client.get('/admin/landing/content')
        assert res2.status_code == 200
        assert res2.json()['overrides']['hero']['value'] == {'title': 'New hero'}


# ── Admin DELETE /admin/landing/content/{key} ─────────────────────────────

class TestAdminDelete:
    def test_requires_admin(self, admin_denied, app_client):
        res = app_client.delete('/admin/landing/content/hero')
        assert res.status_code == 401

    def test_unknown_key_rejected(self, admin_ok, app_client):
        res = app_client.delete('/admin/landing/content/not_a_real_module')
        assert res.status_code == 400

    def test_delete_reverts_to_absent_and_invalidates_cache(self, mock_async_session, admin_ok, app_client):
        with patch('database.rds.delete', new=AsyncMock()) as mock_delete:
            res = app_client.delete('/admin/landing/content/hero')
        assert res.status_code == 200
        assert res.json() == {'status': 'ok', 'key': 'hero', 'deleted': True}
        mock_delete.assert_awaited_once_with('cache:landing:content')

        # After the delete, an admin GET whose row is gone shows no override.
        mock_async_session._execute_result = make_result(fetchall=[])
        res2 = app_client.get('/admin/landing/content')
        assert res2.json()['overrides'] == {}


# ── Path-freeze unit tests (no HTTP) ──────────────────────────────────────

class TestPathValue:
    def test_finds_nested_value(self):
        found, val = landing_content.path_value({'items': [{'value': 1}]}, 'items.0.value')
        assert found is True
        assert val == 1

    def test_missing_path_not_found(self):
        found, _ = landing_content.path_value({'items': []}, 'items.0.value')
        assert found is False

    def test_scalar_midpath_not_found(self):
        found, _ = landing_content.path_value({'items': 'not-a-list'}, 'items.0.value')
        assert found is False

    def test_frozen_conflicts_lists_only_matches(self):
        value = {'items': [{'value': '5'}]}
        assert landing_content.frozen_conflicts('stats', value) == ['items.0.value']
        assert landing_content.frozen_conflicts('hero', value) == []
