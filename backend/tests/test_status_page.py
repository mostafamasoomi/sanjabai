"""Tests for the public status page (`GET /status/summary`) and the admin
incident endpoints in status_page.py.

Kuma is never actually reached here -- `status_page._fetch_kuma` and the
Redis client are mocked, same pattern as the rest of this suite (see
`tests/conftest.py`'s `mock_async_session` fixture and the redis mock it
installs before `app` is imported).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from tests.conftest import make_result, make_row

client = TestClient(app)


@pytest.fixture
def admin_ok():
    with patch('status_page.admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def admin_denied():
    with patch('status_page.admin_required', new=AsyncMock(return_value=False)):
        yield


class TestStatusSummaryNoKuma:
    def test_monitoring_up_false_when_kuma_base_url_unset(self, mock_async_session, monkeypatch):
        monkeypatch.delenv('KUMA_BASE_URL', raising=False)
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch('status_page.rds.get', new=AsyncMock(return_value=None)):
            resp = client.get('/status/summary')
        assert resp.status_code == 200
        body = resp.json()
        assert body['monitoringUp'] is False
        assert body['services'] == []
        assert body['stale'] is False
        assert body['incident'] is None

    def test_never_raises_even_if_db_is_down(self, monkeypatch):
        monkeypatch.delenv('KUMA_BASE_URL', raising=False)
        with patch('status_page.async_session', new=None), \
             patch('status_page.rds.get', new=AsyncMock(return_value=None)):
            resp = client.get('/status/summary')
        assert resp.status_code == 200
        assert resp.json()['incident'] is None

    def test_never_raises_when_incident_query_raises(self, mock_async_session, monkeypatch):
        monkeypatch.delenv('KUMA_BASE_URL', raising=False)

        async def _boom(*args, **kwargs):
            raise RuntimeError('db exploded')

        mock_async_session.execute = _boom
        with patch('status_page.rds.get', new=AsyncMock(return_value=None)):
            resp = client.get('/status/summary')
        assert resp.status_code == 200
        assert resp.json()['incident'] is None


class TestStatusSummaryKuma:
    def test_fresh_cache_hit_is_served_without_fetching(self, mock_async_session, monkeypatch):
        monkeypatch.setenv('KUMA_BASE_URL', 'http://uptime_kuma:3001')
        mock_async_session._execute_result = make_result(fetchone=None)
        cached = json.dumps({
            'services': [{'key': 'web', 'label': 'وب‌سایت', 'status': 'up',
                          'uptime24h': 0.999, 'avgPingMs': 100, 'beats': []}],
            'monitoringUp': True,
        })
        with patch('status_page.rds.get', new=AsyncMock(return_value=cached)), \
             patch('status_page._fetch_kuma', new=AsyncMock()) as fetch_mock:
            resp = client.get('/status/summary')
        fetch_mock.assert_not_called()
        assert resp.status_code == 200
        body = resp.json()
        assert body['monitoringUp'] is True
        assert body['stale'] is False
        assert body['services'][0]['key'] == 'web'

    def test_stale_last_good_served_when_fetch_fails(self, mock_async_session, monkeypatch):
        monkeypatch.setenv('KUMA_BASE_URL', 'http://uptime_kuma:3001')
        mock_async_session._execute_result = make_result(fetchone=None)
        last_good = json.dumps({
            'services': [{'key': 'api', 'label': 'API', 'status': 'up',
                          'uptime24h': 0.987, 'avgPingMs': 250, 'beats': []}],
            'monitoringUp': True,
        })

        async def fake_get(key):
            if key == 'status:kuma:last_good':
                return last_good
            return None  # cache miss, no fail-cooldown yet

        with patch('status_page._fetch_kuma', new=AsyncMock(return_value=None)), \
             patch('status_page.rds.get', new=AsyncMock(side_effect=fake_get)), \
             patch('status_page.rds.setex', new=AsyncMock()), \
             patch('status_page.rds.set', new=AsyncMock()):
            resp = client.get('/status/summary')

        assert resp.status_code == 200
        body = resp.json()
        assert body['stale'] is True
        assert body['monitoringUp'] is True
        assert body['services'][0]['key'] == 'api'

    def test_empty_when_fetch_fails_with_no_last_good(self, mock_async_session, monkeypatch):
        monkeypatch.setenv('KUMA_BASE_URL', 'http://uptime_kuma:3001')
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch('status_page._fetch_kuma', new=AsyncMock(return_value=None)), \
             patch('status_page.rds.get', new=AsyncMock(return_value=None)), \
             patch('status_page.rds.setex', new=AsyncMock()), \
             patch('status_page.rds.set', new=AsyncMock()):
            resp = client.get('/status/summary')
        assert resp.status_code == 200
        body = resp.json()
        assert body['services'] == []
        assert body['monitoringUp'] is False
        assert body['stale'] is False

    def test_kuma_fetch_raising_never_surfaces_as_500(self, mock_async_session, monkeypatch):
        monkeypatch.setenv('KUMA_BASE_URL', 'http://uptime_kuma:3001')
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch('status_page._fetch_kuma', new=AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('status_page.rds.get', new=AsyncMock(return_value=None)), \
             patch('status_page.rds.setex', new=AsyncMock()), \
             patch('status_page.rds.set', new=AsyncMock()):
            resp = client.get('/status/summary')
        assert resp.status_code == 200
        assert resp.json()['monitoringUp'] is False

    def test_support_info_present_and_none_when_empty(self, mock_async_session, monkeypatch):
        monkeypatch.delenv('KUMA_BASE_URL', raising=False)
        monkeypatch.delenv('SUPPORT_EMAIL', raising=False)
        monkeypatch.setenv('SUPPORT_TELEGRAM', '@sanjabai_support')
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch('status_page.rds.get', new=AsyncMock(return_value=None)):
            resp = client.get('/status/summary')
        assert resp.status_code == 200
        support = resp.json()['support']
        assert support['email'] is None
        assert support['telegram'] == '@sanjabai_support'

    def test_dropped_monitor_not_in_label_map(self):
        from status_page import _parse_kuma

        page = {'publicGroupList': [{'monitorList': [
            {'id': 1, 'name': 'web'},
            {'id': 2, 'name': 'internal-hostname-leak'},
        ]}]}
        hb = {'heartbeatList': {
            '1': [{'status': 1, 'time': 't1', 'ping': 100}],
            '2': [{'status': 1, 'time': 't1', 'ping': 50}],
        }, 'uptimeList': {'1_24': 0.999, '2_24': 1.0}}
        result = _parse_kuma(page, hb)
        keys = {s['key'] for s in result['services']}
        assert keys == {'web'}


class TestIncidentAdmin:
    def test_create_incident_requires_admin(self, admin_denied):
        resp = client.post('/admin/status/incident', json={'title': 'قطعی', 'severity': 'warning'})
        assert resp.status_code == 401

    def test_delete_incident_requires_admin(self, admin_denied):
        resp = client.delete('/admin/status/incident')
        assert resp.status_code == 401

    def test_create_incident_rejects_empty_title(self, mock_async_session, admin_ok):
        resp = client.post('/admin/status/incident', json={'title': '  ', 'severity': 'warning'})
        assert resp.status_code == 400

    def test_create_incident_rejects_bad_severity(self, mock_async_session, admin_ok):
        resp = client.post('/admin/status/incident', json={'title': 'قطعی', 'severity': 'nonsense'})
        assert resp.status_code == 400

    def test_create_incident_inserts_when_none_active(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchone=None, scalar_one=42)
        resp = client.post('/admin/status/incident', json={
            'title': 'قطعی سرویس', 'body': 'در حال بررسی', 'severity': 'critical',
        })
        assert resp.status_code == 200
        assert resp.json() == {'status': 'ok', 'id': 42}

    def test_create_incident_updates_when_already_active(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchone=make_row(id=7))
        resp = client.post('/admin/status/incident', json={'title': 'بروزرسانی', 'severity': 'info'})
        assert resp.status_code == 200
        assert resp.json() == {'status': 'ok', 'id': 7}

    def test_resolve_incident(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchone=make_row(id=7))
        resp = client.delete('/admin/status/incident')
        assert resp.status_code == 200
        assert resp.json() == {'status': 'ok'}

    def test_incident_appears_once_created(self, mock_async_session, admin_ok, monkeypatch):
        monkeypatch.delenv('KUMA_BASE_URL', raising=False)

        # Before creation: /status/summary sees no active incident.
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch('status_page.rds.get', new=AsyncMock(return_value=None)):
            before = client.get('/status/summary').json()
        assert before['incident'] is None

        # Create it.
        mock_async_session._execute_result = make_result(fetchone=None, scalar_one=1)
        created = client.post('/admin/status/incident', json={
            'title': 'قطعی موقت', 'body': 'تیم فنی در حال بررسی است', 'severity': 'warning',
        })
        assert created.status_code == 200

        # After creation: /status/summary surfaces the row that would now be
        # active in the database.
        mock_async_session._execute_result = make_result(fetchone=make_row(
            title='قطعی موقت', body='تیم فنی در حال بررسی است',
            severity='warning', started_at='2026-08-21T00:00:00Z',
        ))
        with patch('status_page.rds.get', new=AsyncMock(return_value=None)):
            after = client.get('/status/summary').json()
        assert after['incident'] is not None
        assert after['incident']['title'] == 'قطعی موقت'
        assert after['incident']['severity'] == 'warning'
