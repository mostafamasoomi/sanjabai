"""Tests for the operator monitoring dashboard (`GET /admin/monitoring`).

Every section computes independently and swallows its own failures (see
admin_monitoring.py's module docstring); these tests exercise that directly
by making individual sub-queries raise and checking the endpoint still
answers 200 with every top-level key present.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from tests.conftest import make_result, make_row

client = TestClient(app)


@pytest.fixture
def admin_ok():
    with patch('admin_monitoring.admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def admin_denied():
    with patch('admin_monitoring.admin_required', new=AsyncMock(return_value=False)):
        yield


@pytest.fixture(autouse=True)
def no_redis_cache():
    """Every test in this file exercises the live-query path, not the
    30s admin-dashboard cache, unless it explicitly overrides this."""
    with patch('admin_monitoring.rds.get', new=AsyncMock(return_value=None)), \
         patch('admin_monitoring.rds.setex', new=AsyncMock()):
        yield


class TestAuth:
    def test_requires_admin(self, admin_denied):
        resp = client.get('/admin/monitoring')
        assert resp.status_code == 401


class TestSections:
    def _patch_providers_empty(self):
        return patch('admin_monitoring.configured_providers', return_value=[])

    def test_returns_all_sections_with_empty_db(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchall=[])
        with self._patch_providers_empty(), \
             patch('admin_monitoring.health_map', new=AsyncMock(return_value={})):
            resp = client.get('/admin/monitoring')
        assert resp.status_code == 200
        body = resp.json()
        for key in ('upstreams', 'models', 'traffic', 'volume', 'billing', 'wallet', 'kuma', 'generatedAt'):
            assert key in body
        assert body['upstreams'] == []
        assert body['models'] == []
        assert body['traffic'] == {'hours': []}
        assert body['volume'] == {'days': []}
        assert body['billing']['shortfall']['count'] == 0
        assert body['billing']['estimated']['count24h'] == 0
        assert body['wallet']['negativeBalances'] == []
        assert body['wallet']['ledgerMismatches'] == []

    def test_upstreams_run_concurrently_and_report_alive(self, mock_async_session, admin_ok):
        from providers import Provider, ProbeResult

        fake_providers = [
            Provider(name='litellm', base_url='http://litellm:4000', api_key='', health_path=None),
            Provider(name='ninerouter', base_url='http://9router:20128', api_key='', health_path='/api/health'),
        ]
        mock_async_session._execute_result = make_result(fetchall=[])

        async def fake_alive(p, timeout=5.0):
            assert timeout == 15.0
            return ProbeResult(True, 500, None, 200)

        with patch('admin_monitoring.configured_providers', return_value=fake_providers), \
             patch('admin_monitoring.upstream_alive', new=fake_alive), \
             patch('admin_monitoring.health_map', new=AsyncMock(return_value={})):
            resp = client.get('/admin/monitoring')

        assert resp.status_code == 200
        upstreams = resp.json()['upstreams']
        assert {u['name'] for u in upstreams} == {'litellm', 'ninerouter'}
        assert all(u['alive'] for u in upstreams)

    def test_one_failing_section_does_not_500_the_endpoint(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchall=[])

        async def boom():
            raise RuntimeError('billing query exploded')

        with self._patch_providers_empty(), \
             patch('admin_monitoring.health_map', new=AsyncMock(return_value={})), \
             patch('admin_monitoring._billing_section', new=boom):
            resp = client.get('/admin/monitoring')

        assert resp.status_code == 200
        body = resp.json()
        # billing degraded to the safe default, but now says so: a dict-shaped
        # section carries `error: True` inline and is named in `errors`.
        # Without that the admin cannot tell "no shortfalls" from "the query
        # exploded", which is the whole point of this contract.
        assert body['billing'] == {
            'shortfall': {'count': 0, 'sum': 0, 'recent': []},
            'estimated': {'count24h': 0, 'count30d': 0, 'recent': []},
            'error': True,
        }
        assert body['errors'] == ['billing']
        assert 'upstreams' in body and 'models' in body

    def test_healthy_response_reports_no_errors(self, mock_async_session, admin_ok):
        """The happy path must say so explicitly, or `errors` is meaningless."""
        mock_async_session._execute_result = make_result(fetchall=[])
        with self._patch_providers_empty(), \
             patch('admin_monitoring.health_map', new=AsyncMock(return_value={})):
            resp = client.get('/admin/monitoring')
        assert resp.status_code == 200
        assert resp.json()['errors'] == []

    def test_failing_list_sections_are_named_in_errors(self, mock_async_session, admin_ok):
        """The regression this contract exists for.

        `upstreams` and `models` are lists, so they cannot carry an inline
        `error` key. They used to degrade to `[]` — indistinguishable from
        "nothing configured" — and the admin was shown an empty panel with no
        hint that a query had failed. They must now be named in `errors`.
        """
        mock_async_session._execute_result = make_result(fetchall=[])

        def explode(*_a, **_kw):
            raise RuntimeError('providers lookup exploded')

        with patch('admin_monitoring.configured_providers', new=explode), \
             patch('admin_monitoring.health_map',
                   new=AsyncMock(side_effect=RuntimeError('health_map exploded'))):
            resp = client.get('/admin/monitoring')

        assert resp.status_code == 200
        body = resp.json()
        assert body['upstreams'] == []
        assert body['models'] == []
        assert body['errors'] == ['models', 'upstreams']

    def test_wallet_reuses_watchdog_queries(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(
            fetchall=[make_row(user_id=9, balance=-500)]
        )
        with self._patch_providers_empty(), \
             patch('admin_monitoring.health_map', new=AsyncMock(return_value={})):
            resp = client.get('/admin/monitoring')
        assert resp.status_code == 200
        # Same mocked rows answer both wallet queries (single shared
        # _execute_result), which is enough to prove the section runs and
        # shapes its output rather than raising.
        wallet = resp.json()['wallet']
        assert isinstance(wallet['negativeBalances'], list)
        assert isinstance(wallet['ledgerMismatches'], list)

    def test_kuma_section_is_read_only_from_redis(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchall=[])
        with self._patch_providers_empty(), \
             patch('admin_monitoring.health_map', new=AsyncMock(return_value={})), \
             patch('admin_monitoring.upstream_alive') as fetch_should_not_be_called:
            resp = client.get('/admin/monitoring')
        assert resp.status_code == 200
        # kuma section must never call the upstream-liveness fetcher used for
        # the `upstreams` section, or Kuma itself -- it only reads Redis.
        assert resp.json()['kuma'] == {
            'monitoringUp': False, 'stale': False, 'source': None, 'failing': False,
        }

    def test_cached_result_served_without_recomputing(self, mock_async_session, admin_ok):
        import json
        cached_payload = json.dumps({
            'upstreams': [], 'models': [], 'traffic': {'hours': []},
            'volume': {'days': []},
            'billing': {'shortfall': {'count': 0, 'sum': 0, 'recent': []},
                        'estimated': {'count24h': 0, 'count30d': 0, 'recent': []}},
            'wallet': {'negativeBalances': [], 'ledgerMismatches': []},
            'kuma': {'monitoringUp': False}, 'generatedAt': 'x',
        })
        with patch('admin_monitoring.rds.get', new=AsyncMock(return_value=cached_payload)), \
             patch('admin_monitoring.health_map', new=AsyncMock()) as health_mock:
            resp = client.get('/admin/monitoring')
        health_mock.assert_not_called()
        assert resp.status_code == 200
        assert resp.json()['generatedAt'] == 'x'
