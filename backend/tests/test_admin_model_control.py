"""Tests for the admin panel model control endpoints (enable/disable,
live test) added so the React admin panel doesn't need the separate
legacy admin/app.py just to kill a broken model or probe it on demand."""
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import database as _db
from app import app
from i18n import err
from tests.conftest import make_result, make_row

client = TestClient(app)


@pytest.fixture
def admin_ok():
    with patch('admin.admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def gates_pass():
    """Satisfy both promotion gates (probe + margin) so a flip to
    'available' proceeds -- see admin_pricing.toggle_model's own comment on
    why enabling a model is gated while disabling one is not.

    Patches the module-level names `admin_pricing._refuse_unprobed` /
    `admin_pricing._refuse_loss_making` rather than the `services.probe_gate`
    / `services.margin` functions they wrap, because toggle_model reaches
    them as bare module globals (`await _refuse_unprobed(...)`) -- same
    monkeypatch shape as admin_pricing.py's own module docstring documents
    for `admin.admin_required`.
    """
    with patch('admin_pricing._refuse_unprobed', new=AsyncMock(return_value=None)), \
         patch('admin_pricing._refuse_loss_making', new=AsyncMock(return_value=None)):
        yield


def _spy_on_execute(session):
    """Wrap ``session.execute`` to record every SQL text passed to it,
    without changing what it returns (still ``session._execute_result``).

    Used to prove a refused promotion never reaches the UPDATE -- asserting
    only the response status code would still pass if the gate were checked
    after the write, so the tests that use this look at what was actually
    executed.
    """
    calls: list[str] = []
    orig_execute = session.execute

    async def spy_execute(*args, **kwargs):
        if args:
            calls.append(str(args[0]))
        return await orig_execute(*args, **kwargs)

    session.execute = spy_execute
    return calls


class TestToggleModel:
    def test_toggle_flips_available_to_disabled(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='available'))
        resp = client.post('/admin/models/tencent-hy3/toggle')
        assert resp.status_code == 200
        assert resp.json() == {'status': 'ok', 'model': 'tencent-hy3', 'availability': 'disabled'}

    def test_toggle_flips_disabled_to_available(self, mock_async_session, admin_ok, gates_pass):
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


class TestTogglePromotionGates:
    """«مدل فقط بعد از پروب زنده موفق ارائه می‌شود» و «هیچ درخواستی نباید
    ضررده باشد» -- toggle_model must not just *report* a refusal when either
    gate fires on a disabled -> available flip, it must not have written the
    row at all. A status-code-only assertion would still pass if the UPDATE
    ran before the gate check, so these look at what was actually executed.
    """

    def test_toggle_refuses_unprobed_model_and_does_not_write(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='disabled'))
        calls = _spy_on_execute(mock_async_session)
        refusal = err('پروب زنده این مدل را تأیید نکرده', 'Live probe has not confirmed this model.', 400)
        with patch('admin_pricing._refuse_unprobed', new=AsyncMock(return_value=refusal)):
            resp = client.post('/admin/models/tencent-hy3/toggle')
        assert resp.status_code == 400
        assert resp.json()['detail'] == 'پروب زنده این مدل را تأیید نکرده'
        assert not any('UPDATE' in c for c in calls), (
            f'toggle_model wrote to model_catalog despite the probe gate refusing: {calls}'
        )

    def test_toggle_refuses_loss_making_model_and_does_not_write(self, mock_async_session, admin_ok):
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='disabled'))
        calls = _spy_on_execute(mock_async_session)
        refusal = err('این قیمت ضررده است', 'This price is loss-making.', 400)
        with patch('admin_pricing._refuse_unprobed', new=AsyncMock(return_value=None)), \
             patch('admin_pricing._refuse_loss_making', new=AsyncMock(return_value=refusal)):
            resp = client.post('/admin/models/tencent-hy3/toggle')
        assert resp.status_code == 400
        assert resp.json()['detail'] == 'این قیمت ضررده است'
        assert not any('UPDATE' in c for c in calls), (
            f'toggle_model wrote to model_catalog despite the margin gate refusing: {calls}'
        )


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
