"""Tests for USD->IRT exchange rate provenance tracking.

Covers two things added to backend/content.py for admin visibility
(backend/exchange_rate_admin.py): each resolver tier now reports which one
won (`source`), and `get_exchange_rate_meta()` exposes that plus the
market/markup/effective split without disturbing the existing cache shape or
`_get_exchange_rate()`'s public 2-tuple contract.

Style mirrors tests/test_markup.py: calls content.py's functions directly
(patching content.rds / content._http / the mock_async_session fixture)
rather than only going through HTTP, since the interesting logic lives
entirely in content.py. A small standalone FastAPI app carries just the new
router so these tests don't depend on app.py having wired it in yet (that
`include_router` line is added by the coordinator separately, outside this
agent's file ownership).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import content as content_mod
import exchange_rate_admin
from tests.conftest import make_result, make_row


@pytest.fixture(autouse=True)
def _no_global_markup_cache():
    """get_global_markup_pct() has its own Redis cache key; stub it out so
    every test here exercises only the exchange-rate cache key."""
    with patch.object(content_mod, 'get_global_markup_pct', new=AsyncMock(return_value=0)):
        yield


def _mock_http_json(irr_value: float):
    """A MagicMock standing in for content._http whose .get() is awaitable
    and returns a sync httpx.Response-shaped object (raise_for_status/json
    are sync on a real httpx.Response, so these must NOT be AsyncMock)."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={'rates': {'IRR': irr_value}})
    http = MagicMock()
    http.get = AsyncMock(return_value=resp)
    return http


class TestComputeExchangeRateSource:
    """_compute_exchange_rate() reports which of the 4 tiers won."""

    @pytest.mark.asyncio
    async def test_tier1_db_override_reports_source(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(rate=900_000.0))
        rate, pct, source = await content_mod._compute_exchange_rate()
        assert source == 'db_override'
        assert rate == 900_000.0

    @pytest.mark.asyncio
    async def test_tier2_tgju_reports_source_when_no_override(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(content_mod, '_fetch_tgju_rate', new=AsyncMock(return_value=1_000_000.0)):
            rate, pct, source = await content_mod._compute_exchange_rate()
        assert source == 'tgju'
        assert rate == 100_000.0  # IRR -> IRT is /10

    @pytest.mark.asyncio
    async def test_tier3_er_api_reports_source_when_db_and_tgju_fail(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(content_mod, '_fetch_tgju_rate', new=AsyncMock(return_value=None)), \
             patch.object(content_mod, '_http', _mock_http_json(2_000_000.0)):
            rate, pct, source = await content_mod._compute_exchange_rate()
        assert source == 'er_api'
        assert rate == 200_000.0

    @pytest.mark.asyncio
    async def test_tier4_hardcoded_fallback_reports_source_when_everything_fails(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        broken_http = MagicMock()
        broken_http.get = AsyncMock(side_effect=Exception('er-api down'))
        with patch.object(content_mod, '_fetch_tgju_rate', new=AsyncMock(return_value=None)), \
             patch.object(content_mod, '_http', broken_http):
            rate, pct, source = await content_mod._compute_exchange_rate()
        assert source == 'hardcoded_fallback'
        assert rate == pytest.approx(1_264_884 / 10)


class TestGetExchangeRateBackwardCompat:
    """_get_exchange_rate() must keep its original (rate_with_markup, pct)
    2-tuple shape -- every existing price-computing caller depends on it."""

    @pytest.mark.asyncio
    async def test_cache_miss_still_returns_2_tuple_and_stores_bare_rate(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(content_mod.rds, 'setex', new=AsyncMock()) as mock_setex, \
             patch.object(content_mod, '_fetch_tgju_rate', new=AsyncMock(return_value=1_000_000.0)):
            result = await content_mod._get_exchange_rate()

        assert result == pytest.approx((100_000.0 + content_mod.USD_IRT_FLAT_MARKUP, 0))
        # Redis holds the BARE market rate, not the marked-up one.
        stored = json.loads(mock_setex.await_args.args[2])
        assert stored['rate_irt'] == pytest.approx(100_000.0)
        assert stored['source'] == 'tgju'
        assert 'fetched_at' in stored and stored['fetched_at']

    @pytest.mark.asyncio
    async def test_cache_hit_still_returns_2_tuple(self):
        payload = json.dumps({'rate_irt': 500_000.0, 'markup_pct': 12, 'source': 'tgju', 'fetched_at': 'x'})
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=payload)):
            result = await content_mod._get_exchange_rate()
        assert result == (500_000.0 + content_mod.USD_IRT_FLAT_MARKUP, 12)

    @pytest.mark.asyncio
    async def test_old_cache_entry_with_no_source_key_does_not_crash(self):
        """The most important test in this file: an entry written by the
        currently-running (pre-this-change) production code has neither
        `source` nor `fetched_at`. _get_exchange_rate() must not care --
        it never read those keys even before this change."""
        payload = json.dumps({'rate_irt': 300_000.0, 'markup_pct': 5})
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=payload)):
            result = await content_mod._get_exchange_rate()
        assert result == (300_000.0 + content_mod.USD_IRT_FLAT_MARKUP, 5)


class TestGetExchangeRateMeta:
    """get_exchange_rate_meta() -- the admin-panel read helper."""

    @pytest.mark.asyncio
    async def test_old_cache_entry_with_no_source_reports_unknown_not_a_crash(self):
        """Deploy-ordering case: this code ships before the old cache entry
        (written by the currently-running process) expires. Must degrade to
        'unknown' provenance, never raise."""
        payload = json.dumps({'rate_irt': 300_000.0, 'markup_pct': 5})
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=payload)), \
             patch.object(content_mod.rds, 'ttl', new=AsyncMock(return_value=120)):
            meta = await content_mod.get_exchange_rate_meta()

        assert meta['source'] == 'unknown'
        assert meta['fetched_at'] is None
        assert meta['rate_irt_bare'] == pytest.approx(300_000.0)
        assert meta['markup_pct'] == 5

    @pytest.mark.asyncio
    async def test_effective_rate_is_bare_plus_flat_markup(self):
        payload = json.dumps({
            'rate_irt': 400_000.0, 'markup_pct': 0,
            'source': 'er_api', 'fetched_at': '2026-08-22T00:00:00+00:00',
        })
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=payload)), \
             patch.object(content_mod.rds, 'ttl', new=AsyncMock(return_value=1800)):
            meta = await content_mod.get_exchange_rate_meta()

        assert meta['rate_irt_bare'] == pytest.approx(400_000.0)
        assert meta['flat_markup_irt'] == content_mod.USD_IRT_FLAT_MARKUP
        assert meta['rate_irt_effective'] == pytest.approx(400_000.0 + content_mod.USD_IRT_FLAT_MARKUP)
        assert meta['source'] == 'er_api'
        assert meta['fetched_at'] == '2026-08-22T00:00:00+00:00'
        assert meta['cache_ttl_remaining_s'] == 1800

    @pytest.mark.asyncio
    async def test_ttl_read_failure_degrades_to_none_not_a_crash(self):
        payload = json.dumps({'rate_irt': 400_000.0, 'markup_pct': 0, 'source': 'tgju', 'fetched_at': 'x'})
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=payload)), \
             patch.object(content_mod.rds, 'ttl', new=AsyncMock(side_effect=Exception('redis down'))):
            meta = await content_mod.get_exchange_rate_meta()
        assert meta['cache_ttl_remaining_s'] is None
        # The rate/source it already read before the ttl() call still comes through.
        assert meta['source'] == 'tgju'


class TestExchangeRateAdminEndpoint:
    """HTTP layer (backend/exchange_rate_admin.py) mounted standalone -- this
    agent does not own app.py, so the router is not wired into the real app
    yet; that include_router line is the coordinator's to add."""

    def setup_method(self):
        app = FastAPI()
        app.include_router(exchange_rate_admin.router)
        self.client = TestClient(app)

    def test_requires_admin(self):
        with patch.object(exchange_rate_admin, 'admin_required', new=AsyncMock(return_value=False)):
            resp = self.client.get('/admin/exchange-rate')
        assert resp.status_code == 401

    def test_returns_meta_shape_for_admin(self):
        meta = {
            'rate_irt_bare': 1000.0, 'flat_markup_irt': 2000.0, 'rate_irt_effective': 3000.0,
            'markup_pct': 0, 'source': 'tgju', 'fetched_at': 'x', 'cache_ttl_remaining_s': 100,
        }
        with patch.object(exchange_rate_admin, 'admin_required', new=AsyncMock(return_value=True)), \
             patch('content.get_exchange_rate_meta', new=AsyncMock(return_value=meta)):
            resp = self.client.get('/admin/exchange-rate')
        assert resp.status_code == 200
        assert resp.json() == meta

    def test_refresh_requires_admin(self):
        with patch.object(exchange_rate_admin, 'admin_required', new=AsyncMock(return_value=False)):
            resp = self.client.post('/admin/exchange-rate/refresh')
        assert resp.status_code == 401

    def test_refresh_busts_cache_key_then_returns_meta(self):
        with patch.object(exchange_rate_admin, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(exchange_rate_admin, 'rds', new=AsyncMock()) as mock_rds, \
             patch.object(exchange_rate_admin, '_write_audit_log', new=AsyncMock()), \
             patch('content.get_exchange_rate_meta', new=AsyncMock(return_value={'source': 'tgju'})):
            resp = self.client.post('/admin/exchange-rate/refresh')
        assert resp.status_code == 200
        assert resp.json() == {'source': 'tgju'}
        mock_rds.delete.assert_awaited_once_with(content_mod.EXCHANGE_RATE_CACHE_KEY)
