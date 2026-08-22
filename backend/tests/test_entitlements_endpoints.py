"""Tests for GET /entitlements (backend/entitlements_endpoints.py).

This endpoint is NOT wired into app.py yet -- the coordinator owns app.py
and adds the include_router line separately -- so these tests mount
entitlements_endpoints.router on a throwaway FastAPI app, same pattern as
test_images.py.

services/entitlements.py is being written concurrently by another agent and
may not exist on disk at all when this file runs, or may exist without its
backing DB table applied. entitlements_endpoints.py imports it lazily
*inside* the request handler for exactly that reason. To pin down both
failure modes deterministically (regardless of whichever state the other
agent's module happens to be in at the moment these tests run), the "module
missing" test forces the import to fail by setting
`sys.modules['services.entitlements'] = None` -- an import of a name whose
sys.modules entry is exactly `None` always raises ImportError, per the
import system's documented behaviour, independent of whether a real file
exists on disk.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import entitlements_endpoints as entitlements_mod


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(entitlements_mod.router)
    return TestClient(app)


@pytest.fixture
def client():
    return _make_client()


def _fake_service_module(list_entitlements_impl):
    """Build a fake `services.entitlements` module exposing exactly the
    contracted `list_entitlements(uid) -> list[dict]` coroutine function,
    for injection into sys.modules so `from services.entitlements import
    list_entitlements` (executed lazily inside the endpoint) resolves to it
    without needing the real module to exist yet."""
    mod = types.ModuleType('services.entitlements')
    mod.list_entitlements = list_entitlements_impl
    return mod


# ── Auth ─────────────────────────────────────────────────────────────────

class TestAuth:
    def test_unauthenticated_rejected(self, client):
        with patch.object(entitlements_mod, '_get_user_id', AsyncMock(return_value=None)):
            resp = client.get('/entitlements')
        assert resp.status_code == 401
        assert 'وارد' in resp.json()['detail']

    def test_never_accepts_a_user_id_from_the_request(self, client):
        """The endpoint must only ever use the authenticated uid -- a
        query-string user_id must be silently ignored, never used to look
        up someone else's entitlements."""
        seen_uids = []

        async def _fake_list(uid):
            seen_uids.append(uid)
            return []

        fake_mod = _fake_service_module(AsyncMock(side_effect=_fake_list))
        with patch.object(entitlements_mod, '_get_user_id', AsyncMock(return_value=7)), \
             patch.dict(sys.modules, {'services.entitlements': fake_mod}):
            resp = client.get('/entitlements?user_id=999')
        assert resp.status_code == 200
        assert seen_uids == [7]


# ── Own entitlements only, contract fields pass through ────────────────────

class TestReturnsOwnEntitlements:
    def test_user_sees_only_their_own_entitlements(self, client):
        expected = [
            {
                'id': 1, 'package_id': 'pkg-basic',
                'requests_remaining': 40, 'tokens_remaining': 12000,
                'max_cost_per_request_toman': 5000,
                'expires_at': '2026-09-01T00:00:00',
            },
        ]
        fake_list = AsyncMock(return_value=expected)
        fake_mod = _fake_service_module(fake_list)
        with patch.object(entitlements_mod, '_get_user_id', AsyncMock(return_value=42)), \
             patch.dict(sys.modules, {'services.entitlements': fake_mod}):
            resp = client.get('/entitlements')
        assert resp.status_code == 200
        assert resp.json() == expected
        fake_list.assert_awaited_once_with(42)


# ── None (unmetered) survives as JSON null, not 0 ───────────────────────────

class TestNullMeansUnmetered:
    def test_none_remaining_serialises_as_null_not_zero(self, client):
        rows = [
            {
                'id': 2, 'package_id': 'pkg-unlimited-requests',
                'requests_remaining': None,  # not metered on this dimension
                'tokens_remaining': 500,
                'max_cost_per_request_toman': None,
                'expires_at': None,
            },
        ]
        fake_mod = _fake_service_module(AsyncMock(return_value=rows))
        with patch.object(entitlements_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.dict(sys.modules, {'services.entitlements': fake_mod}):
            resp = client.get('/entitlements')
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]['requests_remaining'] is None
        assert body[0]['max_cost_per_request_toman'] is None
        assert body[0]['expires_at'] is None
        # The dimension that IS metered must remain a genuine number, not
        # be swept into the same null bucket.
        assert body[0]['tokens_remaining'] == 500

    def test_genuine_zero_remaining_is_not_confused_with_null(self, client):
        rows = [
            {
                'id': 3, 'package_id': 'pkg-exhausted',
                'requests_remaining': 0, 'tokens_remaining': 0,
                'max_cost_per_request_toman': 1000,
                'expires_at': None,
            },
        ]
        fake_mod = _fake_service_module(AsyncMock(return_value=rows))
        with patch.object(entitlements_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.dict(sys.modules, {'services.entitlements': fake_mod}):
            resp = client.get('/entitlements')
        body = resp.json()
        assert body[0]['requests_remaining'] == 0
        assert body[0]['tokens_remaining'] == 0
        assert body[0]['requests_remaining'] is not None


# ── Graceful degradation ────────────────────────────────────────────────────

class TestDegradesCleanly:
    def test_missing_service_module_returns_empty_list_not_500(self, client):
        # Force the lazy `from services.entitlements import list_entitlements`
        # inside the handler to fail with ImportError, simulating a deploy
        # where the concurrently-written service module hasn't landed yet.
        with patch.object(entitlements_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.dict(sys.modules, {'services.entitlements': None}):
            resp = client.get('/entitlements')
        assert resp.status_code == 200
        assert resp.json() == []

    def test_service_raising_returns_empty_list_not_500(self):
        """Covers the migration-not-applied-yet case: the module exists and
        imports fine, but calling it blows up (e.g. the entitlements table
        doesn't exist in this deployment yet)."""
        client = _make_client()
        fake_mod = _fake_service_module(AsyncMock(side_effect=RuntimeError('relation "entitlements" does not exist')))
        with patch.object(entitlements_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.dict(sys.modules, {'services.entitlements': fake_mod}):
            resp = client.get('/entitlements')
        assert resp.status_code == 200
        assert resp.json() == []
