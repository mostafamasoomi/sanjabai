"""
Tests for admin endpoints: pricing, features, analytics, discounts, proxy, about
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tests.conftest import make_result, make_row, ADMIN_TOKEN


class TestAdminAuth:
    def test_no_token(self, client):
        response = client.get('/admin/pricing')
        assert response.status_code == 401

    def test_invalid_token(self, client):
        response = client.get('/admin/pricing', headers={'x-admin-token': 'wrong'})
        assert response.status_code == 401


class TestAdminPricing:
    def test_list_pricing(self, client, mock_async_session, admin_headers):
        mock_async_session._execute_result = make_result(fetchall=[
            make_row(_mapping={'model': 'gpt-4o', 'input_per_million': 5000, 'output_per_million': 15000, 'currency': 'IRT'})
        ])
        response = client.get('/admin/pricing', headers=admin_headers)
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_create_pricing(self, client, mock_async_session, admin_headers):
        mock_async_session.get.return_value = None
        response = client.post('/admin/pricing', json={
            'model': 'deepseek-v3', 'input_per_million': 2000, 'output_per_million': 6000,
        }, headers=admin_headers)
        assert response.status_code == 200

    def test_update_pricing(self, client, mock_async_session, admin_headers):
        existing = make_row(input_per_million=5000, output_per_million=15000, currency='IRT')
        mock_async_session.get.return_value = existing
        response = client.post('/admin/pricing', json={
            'model': 'gpt-4o', 'input_per_million': 4000,
        }, headers=admin_headers)
        assert response.status_code == 200

    def test_no_model(self, client, admin_headers):
        response = client.post('/admin/pricing', json={}, headers=admin_headers)
        assert response.status_code == 400


class TestAdminFeatures:
    def test_list_features(self, client, mock_async_session, admin_headers):
        mock_async_session._execute_result = make_result(fetchall=[])
        response = client.get('/admin/features', headers=admin_headers)
        assert response.status_code == 200

    def test_create_feature(self, client, mock_async_session, admin_headers):
        response = client.post('/admin/features', json={
            'title': 'New', 'description': 'Test', 'icon': 'star', 'active': True, 'order_idx': 0,
        }, headers=admin_headers)
        assert response.status_code == 200

    def test_delete_feature(self, client, mock_async_session, admin_headers):
        mock_async_session.get.return_value = make_row(id=1)
        response = client.delete('/admin/features/1', headers=admin_headers)
        assert response.status_code == 200

    def test_delete_nonexistent(self, client, mock_async_session, admin_headers):
        mock_async_session.get.return_value = None
        response = client.delete('/admin/features/999', headers=admin_headers)
        assert response.status_code == 200


class TestAdminDiscounts:
    def test_list_discounts(self, client, mock_async_session, admin_headers):
        mock_async_session._execute_result = make_result(fetchall=[])
        response = client.get('/admin/discounts', headers=admin_headers)
        assert response.status_code == 200

    def test_create_discount(self, client, mock_async_session, admin_headers):
        response = client.post('/admin/discounts', json={
            'code': 'WELCOME10', 'percent': 10, 'active': True,
        }, headers=admin_headers)
        assert response.status_code == 200

    def test_no_code(self, client, admin_headers):
        response = client.post('/admin/discounts', json={'percent': 10}, headers=admin_headers)
        assert response.status_code == 400

    def test_delete_discount(self, client, mock_async_session, admin_headers):
        mock_async_session.get.return_value = make_row(id=1)
        response = client.delete('/admin/discounts/1', headers=admin_headers)
        assert response.status_code == 200


class TestAdminAnalytics:
    def test_analytics(self, client, mock_async_session, admin_headers):
        # Return different results for each execute call
        results = [
            make_result(fetchone=make_row(c=100)),   # user count
            make_result(fetchone=make_row(total=5000000)),  # revenue
            make_result(fetchone=make_row(total=15000000)),  # tokens
            make_result(fetchone=make_row(c=250)),  # conv count
            make_result(fetchone=make_row(c=45)),   # active users
            make_result(fetchall=[]),  # recent ledger
        ]
        mock_async_session._execute_result = results[0]

        # We need to return different values per call. Monkey-patch execute.
        call_count = [0]

        async def multi_execute(*args, **kwargs):
            idx = min(call_count[0], len(results) - 1)
            call_count[0] += 1
            return results[idx]

        mock_async_session.execute = multi_execute

        response = client.get('/admin/analytics', headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data['user_count'] == 100
        assert data['total_revenue'] == 5000000
        assert data['total_tokens'] == 15000000
        assert data['conv_count'] == 250
        assert data['active_users'] == 45

    def test_unauthorized(self, client):
        response = client.get('/admin/analytics')
        assert response.status_code == 401


class TestAdminProxy:
    def test_get_proxy(self, client, mock_async_session, admin_headers):
        mock_async_session._execute_result = make_result(fetchone=None)
        response = client.get('/admin/proxy', headers=admin_headers)
        assert response.status_code == 200
        assert 'proxy_url' in response.json()

    def test_set_proxy(self, client, mock_async_session, admin_headers):
        mock_async_session._execute_result = make_result(fetchone=None)
        response = client.post('/admin/proxy', json={
            'proxy_url': 'socks5://proxy:1080', 'proxy_type': 'socks5', 'active': True,
        }, headers=admin_headers)
        assert response.status_code == 200


class TestAdminAbout:
    def test_set_about(self, client, mock_async_session, admin_headers):
        mock_async_session._execute_result = make_result(fetchone=None)
        response = client.post('/admin/about', json={
            'title': 'درباره ما', 'body': 'Test content.',
        }, headers=admin_headers)
        assert response.status_code == 200