"""
Tests for auth endpoints: signup, login, me, logout
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app import _hash_password, _verify_password
from conftest import make_result, make_row


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "testpassword123"
        hashed = _hash_password(pw)
        assert '$' in hashed
        assert _verify_password(pw, hashed) is True
        assert _verify_password("wrong", hashed) is False

    def test_hash_is_unique(self):
        pw = "samepassword"
        h1 = _hash_password(pw)
        h2 = _hash_password(pw)
        assert h1 != h2

    def test_empty_password(self):
        hashed = _hash_password("")
        assert _verify_password("", hashed) is True


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        with patch('app.rds.ping', return_value=True), \
             patch('app.engine') as mock_engine:
            mock_engine.connect.return_value.__aenter__ = AsyncMock()
            response = client.get('/health')
            assert response.status_code == 200
            assert response.json()['status'] == 'ok'

    def test_root_endpoint(self, client):
        response = client.get('/')
        assert response.status_code == 200
        assert response.json()['service'] == 'Persian AI Gateway'


class TestSignup:
    def test_signup_new_user(self, client, mock_async_session):
        # No existing user
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch('app.rds.setex'):
            response = client.post('/auth/signup', json={
                'email': 'test@example.com', 'password': 'securepass123',
            })
            assert response.status_code == 200
            assert 'token' in response.json()

    def test_signup_existing_user(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=make_row(email='test@example.com')
        )
        response = client.post('/auth/signup', json={
            'email': 'test@example.com', 'password': 'securepass123',
        })
        assert response.status_code == 409

    def test_signup_missing_fields(self, client):
        response = client.post('/auth/signup', json={})
        assert response.status_code == 422


class TestLogin:
    def test_login_success(self, client, mock_async_session):
        pw = "securepass123"
        hashed = _hash_password(pw)
        mock_async_session._execute_result = make_result(
            fetchone=make_row(password_hash=hashed, email='test@example.com', id=1)
        )
        with patch('app.rds.setex'):
            response = client.post('/auth/login', json={
                'email': 'test@example.com', 'password': pw,
            })
            assert response.status_code == 200
            assert 'token' in response.json()

    def test_login_wrong_password(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=make_row(password_hash=_hash_password("correct"), email='test@example.com')
        )
        response = client.post('/auth/login', json={
            'email': 'test@example.com', 'password': 'wrongpass',
        })
        assert response.status_code == 401

    def test_login_nonexistent_user(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        response = client.post('/auth/login', json={
            'email': 'nobody@example.com', 'password': 'x',
        })
        assert response.status_code == 401


class TestMe:
    def test_me_authenticated(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=make_row(id=1, email='test@example.com', created_at='2024-01-01')
        )
        with patch('app.rds.get', return_value='1'), patch('app.rds.expire'):
            response = client.get('/auth/me', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200
            assert response.json()['email'] == 'test@example.com'

    def test_me_unauthenticated(self, client):
        with patch('app.rds.get', return_value=None):
            response = client.get('/auth/me')
            assert response.status_code == 401

    def test_me_no_token(self, client):
        with patch('app.rds.get', return_value=None):
            response = client.get('/auth/me')
            assert response.status_code == 401


class TestLogout:
    def test_logout(self, client):
        with patch('app.rds.delete'):
            response = client.post('/auth/logout', headers={'Authorization': 'Bearer x'})
            assert response.status_code == 200

    def test_logout_no_token(self, client):
        response = client.post('/auth/logout')
        assert response.status_code == 200


class TestModelsEndpoint:
    def test_models_list(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={'data': [{'id': 'gpt-4o'}]})

        class MockClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def get(self, url):
                return mock_resp

        with patch('app.httpx.AsyncClient', return_value=MockClient()):
            response = client.get('/v1/models')
            assert response.status_code == 200
            assert len(response.json()['data']) == 1

    def test_models_upstream_failure(self, client):
        with patch('httpx.AsyncClient.get', side_effect=Exception('timeout')):
            response = client.get('/v1/models')
            assert response.status_code == 200
            assert response.json()['data'] == []


class TestUsageEndpoint:
    def test_usage_authenticated(self, client, mock_async_session):
        reset_mock = MagicMock()
        reset_mock.isoformat.return_value = '2024-12-31T00:00:00'
        mock_async_session._execute_result = make_result(
            fetchone=make_row(daily_limit=200000, used_today=5000, reset_at=reset_mock)
        )
        with patch('app.rds.get', return_value='1'), patch('app.rds.expire'):
            response = client.get('/me/usage', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200
            assert response.json()['daily_limit'] == 200000

    def test_usage_unauthenticated(self, client):
        with patch('app.rds.get', return_value=None):
            response = client.get('/me/usage')
            assert response.status_code == 401


class TestContentEndpoints:
    def test_public_features(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[])
        response = client.get('/content/features')
        assert response.status_code == 200

    def test_public_discounts(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[])
        response = client.get('/content/discounts')
        assert response.status_code == 200

    def test_about_endpoint(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        response = client.get('/about')
        assert response.status_code == 200
        assert 'title' in response.json()