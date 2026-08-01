"""
Tests for auth endpoints: signup, login, me, logout
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app import _hash_password, _verify_password
from tests.conftest import make_result, make_row


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
        with patch('app.rds.ping', new_callable=AsyncMock, return_value=True), \
             patch('app.engine') as mock_engine:
            mock_engine.connect.return_value.__aenter__ = AsyncMock()
            response = client.get('/health')
            assert response.status_code == 200
            assert response.json()['status'] == 'ok'

    def test_root_endpoint(self, client):
        response = client.get('/')
        assert response.status_code == 200
        assert response.json()['service'] == 'Persian AI Gateway'


CAPTCHA = {'captcha_token': 'test-token', 'captcha_answer': '1234'}


class TestSignup:
    def test_signup_new_user(self, client, mock_async_session):
        # No existing user
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch('app.rds.setex', new_callable=AsyncMock), \
             patch('app.rds.get', new_callable=AsyncMock, return_value='1234'):
            response = client.post('/auth/signup', json={
                'email': 'test@example.com', 'password': 'securepass123', **CAPTCHA,
            })
            assert response.status_code == 200
            assert 'token' in response.json()

    def test_signup_existing_user(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=make_row(email='test@example.com')
        )
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1234'):
            response = client.post('/auth/signup', json={
                'email': 'test@example.com', 'password': 'securepass123', **CAPTCHA,
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
            # make_row is a bare MagicMock with only the passed kwargs set —
            # `user.banned` on an unset attribute auto-vivifies as a (truthy)
            # child MagicMock, tripping the `if user.banned: return 403`
            # check below. Must be set explicitly to False.
            fetchone=make_row(password_hash=hashed, email='test@example.com', id=1, banned=False)
        )
        with patch('app.rds.setex', new_callable=AsyncMock), \
             patch('app.rds.get', new_callable=AsyncMock, return_value='1234'):
            response = client.post('/auth/login', json={
                'email': 'test@example.com', 'password': pw, **CAPTCHA,
            })
            assert response.status_code == 200
            assert 'token' in response.json()

    def test_login_wrong_password(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=make_row(password_hash=_hash_password("correct"), email='test@example.com')
        )
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1234'):
            response = client.post('/auth/login', json={
                'email': 'test@example.com', 'password': 'wrongpass', **CAPTCHA,
            })
            assert response.status_code == 401

    def test_login_nonexistent_user(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1234'):
            response = client.post('/auth/login', json={
                'email': 'nobody@example.com', 'password': 'x', **CAPTCHA,
            })
            assert response.status_code == 401


class TestMe:
    def test_me_authenticated(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=make_row(id=1, email='test@example.com', created_at='2024-01-01')
        )
        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.get('/auth/me', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200
            assert response.json()['email'] == 'test@example.com'

    def test_me_unauthenticated(self, client):
        with patch('app.rds.get', new_callable=AsyncMock, return_value=None):
            response = client.get('/auth/me')
            assert response.status_code == 401

    def test_me_no_token(self, client):
        with patch('app.rds.get', new_callable=AsyncMock, return_value=None):
            response = client.get('/auth/me')
            assert response.status_code == 401


class TestLogout:
    def test_logout(self, client):
        with patch('app.rds.delete', new_callable=AsyncMock):
            response = client.post('/auth/logout', headers={'Authorization': 'Bearer x'})
            assert response.status_code == 200

    def test_logout_no_token(self, client):
        response = client.post('/auth/logout')
        assert response.status_code == 200


class TestModelsEndpoint:
    def test_models_list(self, client, mock_async_session):
        # /v1/models (content.py) reads model_catalog first and only falls
        # back to an HTTP call to LiteLLM if that query comes back empty —
        # patching `app.httpx.AsyncClient` never exercised that fallback
        # anyway, since the DB path is tried first and (like the wallet/
        # ownership endpoints) `async_session` here is database.py's shared
        # proxy, not a name `app.httpx.AsyncClient` patching could reach.
        # Satisfying the real (preferred) DB path is simpler than mocking
        # the HTTP fallback.
        mock_async_session._execute_result = make_result(fetchall=[
            make_row(
                id=1, provider_model_id='gpt-4o', display_name='GPT-4o',
                context_window=128000, availability='available',
                input_per_million=0, output_per_million=0, currency='IRT',
                usd_input_per_million=0, usd_output_per_million=0,
            )
        ])
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
        # /me/usage (admin.py) is a wallet-usage summary, not the old
        # quota shape this test used to assert on — it issues four
        # sequential session.execute() calls (balance sum, this month's
        # aggregate, per-model breakdown rows, recent events rows), each
        # needing its own result shape.
        results = [
            make_result(fetchone=make_row(balance=45000)),
            make_result(fetchone=make_row(inp=1000, out=500, spent=5000, cnt=3)),
            make_result(fetchall=[]),
            make_result(fetchall=[]),
        ]

        async def sequenced_execute(*args, **kwargs):
            return results[sequenced_execute.calls.pop(0)]
        sequenced_execute.calls = [0, 1, 2, 3]
        mock_async_session.execute = sequenced_execute

        with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), patch('app.rds.expire', new_callable=AsyncMock):
            response = client.get('/me/usage', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 200
            body = response.json()
            assert body['current_balance'] == 45000
            assert body['total_spent_this_month'] == 5000
            assert body['monthly']['count'] == 3

    def test_usage_unauthenticated(self, client):
        with patch('app.rds.get', new_callable=AsyncMock, return_value=None):
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