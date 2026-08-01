"""Tests for the optional model_id label on credit packages (used to sell a
package as "N million tokens of <model>" -- see
migrations/0018_credit_package_model_label.sql). Deliberately does not touch
the checkout/charge math, only that the label round-trips through the admin
create/update endpoint."""
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


@pytest.fixture
def admin_ok():
    with patch('admin.admin_required', new=AsyncMock(return_value=True)):
        yield


class TestCreditPackageModelLabel:
    def test_create_new_package_stores_model_id(self, mock_async_session, admin_ok):
        captured = {}

        async def mock_execute(stmt, params=None, *a, **k):
            sql = str(stmt)
            if 'SELECT id FROM credit_packages' in sql:
                return MagicMock(fetchone=MagicMock(return_value=None))
            if 'INSERT INTO credit_packages' in sql:
                captured['params'] = params
            return MagicMock(fetchone=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

        mock_async_session.execute = mock_execute

        resp = client.post('/admin/credit-packages', json={
            'id': 'pkg_mimo_20m',
            'name_fa': '۲۰ میلیون توکن mimo',
            'name_en': '20M mimo tokens',
            'base_amount': 20000,
            'total_credits': 20000,
            'model_id': 'mimo-v2.5-pro',
            'active': True,
        })
        assert resp.status_code == 200
        assert captured['params']['model_id'] == 'mimo-v2.5-pro'

    def test_update_existing_package_can_set_model_id(self, mock_async_session, admin_ok):
        captured = {}

        async def mock_execute(stmt, params=None, *a, **k):
            sql = str(stmt)
            if 'SELECT id FROM credit_packages' in sql:
                return MagicMock(fetchone=MagicMock(return_value=(1,)))
            if sql.startswith('UPDATE credit_packages'):
                captured['sql'] = sql
                captured['params'] = params
            return MagicMock(fetchone=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

        mock_async_session.execute = mock_execute

        resp = client.post('/admin/credit-packages', json={
            'id': 'pkg_mimo_20m',
            'model_id': 'gpt-4o-mini',
        })
        assert resp.status_code == 200
        assert 'model_id = :model_id' in captured['sql']
        assert captured['params']['model_id'] == 'gpt-4o-mini'

    def test_create_without_model_id_defaults_to_none(self, mock_async_session, admin_ok):
        captured = {}

        async def mock_execute(stmt, params=None, *a, **k):
            sql = str(stmt)
            if 'SELECT id FROM credit_packages' in sql:
                return MagicMock(fetchone=MagicMock(return_value=None))
            if 'INSERT INTO credit_packages' in sql:
                captured['params'] = params
            return MagicMock(fetchone=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

        mock_async_session.execute = mock_execute

        resp = client.post('/admin/credit-packages', json={
            'id': 'pkg_generic_100k',
            'name_fa': 'شارژ عمومی', 'base_amount': 100000, 'total_credits': 100000,
        })
        assert resp.status_code == 200
        assert captured['params']['model_id'] is None
