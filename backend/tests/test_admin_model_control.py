"""Tests for the admin panel model control endpoints (enable/disable,
live test) added so the React admin panel doesn't need the separate
legacy admin/app.py just to kill a broken model or probe it on demand."""
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import database as _db
from app import app
from tests.conftest import make_result, make_row

client = TestClient(app)


@pytest.fixture
def admin_ok():
    with patch('admin.admin_required', new=AsyncMock(return_value=True)):
        yield


class TestToggleModel:
    def test_toggle_flips_available_to_disabled(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='available'))
        resp = client.post('/admin/models/tencent-hy3/toggle')
        assert resp.status_code == 200
        assert resp.json() == {'status': 'ok', 'model': 'tencent-hy3', 'availability': 'disabled'}

    def test_toggle_flips_disabled_to_available(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='disabled'))
        resp = client.post('/admin/models/tencent-hy3/toggle')
        assert resp.status_code == 200
        assert resp.json()['availability'] == 'available'

    def test_toggle_unknown_model_404s(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchone=None)
        resp = client.post('/admin/models/does-not-exist/toggle')
        assert resp.status_code == 404

    def test_toggle_requires_admin(self, mock_async_session):
        with patch('admin.admin_required', new=AsyncMock(return_value=False)):
            resp = client.post('/admin/models/tencent-hy3/toggle')
        assert resp.status_code == 401


class TestTestModel:
    def test_test_model_reports_probe_result(self, mock_async_session, admin_ok):
        fake_http = MagicMock()
        fake_http.post = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=lambda: {'choices': [{'message': {'content': 'pong'}}]},
        ))
        with patch.object(_db, '_real_http', fake_http):
            resp = client.post('/admin/models/tencent-hy3/test')
        assert resp.status_code == 200
        body = resp.json()
        assert body['model'] == 'tencent-hy3'
        assert body['upstream'] == 'litellm'
        assert body['ok'] is True

    def test_test_model_reports_failure(self, mock_async_session, admin_ok):
        fake_http = MagicMock()
        fake_http.post = AsyncMock(return_value=MagicMock(status_code=500, json=lambda: {}))
        with patch.object(_db, '_real_http', fake_http):
            resp = client.post('/admin/models/broken-model/test')
        assert resp.status_code == 200
        body = resp.json()
        assert body['ok'] is False
        assert body['error'] == 'http_500'

    def test_test_model_requires_admin(self, mock_async_session):
        with patch('admin.admin_required', new=AsyncMock(return_value=False)):
            resp = client.post('/admin/models/tencent-hy3/test')
        assert resp.status_code == 401
