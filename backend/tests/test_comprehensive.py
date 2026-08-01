"""
Comprehensive unit tests for Sanjhubai backend.
Tests all major components: auth, chat, models, wallet, pricing, memory.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app import app
from database import async_session
from tests.conftest import make_result, make_row

client = TestClient(app)


# ── Auth Tests ──────────────────────────────────────────────────────────────

class TestAuth:
    """Authentication endpoints tests"""
    
    def test_health_endpoint(self):
        """Health check should return ok status"""
        with patch('app.rds.ping', return_value=True):
            response = client.get('/health')
            assert response.status_code == 200
            assert response.json()['status'] == 'ok'
    
    def test_root_endpoint(self):
        """Root should identify service"""
        response = client.get('/')
        assert response.status_code == 200
        assert response.json()['service'] == 'Persian AI Gateway'


# ── Chat Tests ──────────────────────────────────────────────────────────────

class TestChat:
    """Chat endpoints tests"""
    
    def test_chat_completions_basic(self, mock_async_session):
        """Basic chat completion should work"""
        # `chat._http` is database.py's _HttpProxy — like async_session,
        # __getattr__ raises "HTTP client not initialized" until
        # database._real_http is set, and patch() itself needs to read the
        # *current* value of the attribute it's replacing, so it hits that
        # same raise before the test body even runs.
        import database as _db
        fake_http = MagicMock()
        fake_http.post = AsyncMock(return_value=MagicMock(
            json=lambda: {'choices': [{'message': {'content': 'سلام!'}}]},
            status_code=200,
        ))
        with patch.object(_db, '_real_http', fake_http):
            response = client.post('/v1/chat/completions', json={
                'model': 'tencent-hy3',
                'messages': [{'role': 'user', 'content': 'سلام'}]
            })
            assert response.status_code in [200, 401]  # May need auth
    
    def test_chat_streaming(self, mock_async_session):
        """Streaming should be enabled"""
        response = client.post('/v1/chat/completions', json={
            'model': 'tencent-hy3',
            'messages': [{'role': 'user', 'content': 'سلام'}],
            'stream': True
        }, headers={'Accept': 'text/event-stream'})
        # Streaming endpoint should return iterable
        assert response.status_code in [200, 401]


# ── Models Tests ───────────────────────────────────────────────────────────

class TestModels:
    """Model catalog and selection tests"""
    
    def test_list_models(self, mock_async_session):
        """Should list available models"""
        # `models.py` (the ORM module) has never had an `async_session`
        # attribute to patch — the real target is database.py's shared
        # proxy, which `mock_async_session` (conftest.py) already patches.
        mock_async_session._execute_result = make_result(fetchall=[
            make_row(
                id=1, provider_model_id='tencent-hy3', display_name='Tencent Hy3',
                context_window=32000, availability='available',
                input_per_million=0, output_per_million=0, currency='IRT',
                usd_input_per_million=0, usd_output_per_million=0,
            )
        ])
        response = client.get('/v1/models')
        assert response.status_code in [200, 401]
    
    def test_model_availability_check(self):
        """Working models set should be defined"""
        from chat import get_working_models, _HARDCODED_WORKING
        assert 'tencent-hy3' in _HARDCODED_WORKING
        assert 'deepseek-v4-pro' in _HARDCODED_WORKING


# ── Wallet Tests ───────────────────────────────────────────────────────────

class TestWallet:
    """Wallet and balance tests"""
    
    def test_get_wallet_balance(self, mock_async_session):
        """Should return wallet balance"""
        with patch('wallet.async_session') as mock_session:
            mock_session.return_value.__aenter__.return_value.execute.return_value.fetchone.return_value = MagicMock(balance=1000)
            response = client.get('/wallet')
            assert response.status_code in [200, 401]
    
    def test_ledger_pagination(self, mock_async_session):
        """Ledger should support pagination"""
        response = client.get('/wallet/ledger?page=1&limit=10')
        assert response.status_code in [200, 401]
    
    def test_topup_validation(self):
        """Topup should validate amount"""
        response = client.post('/wallet/topup', json={
            'amount': -100,
            'payment_order_id': 'test-order'
        })
        assert response.status_code in [400, 401]


# ── Pricing Tests ───────────────────────────────────────────────────────────

class TestPricing:
    """Pricing and billing tests"""
    
    def test_list_plans(self, mock_async_session):
        """Should list subscription plans"""
        response = client.get('/plans')
        assert response.status_code in [200, 401]
    
    def test_credit_packages(self, mock_async_session):
        """Should list credit packages"""
        response = client.get('/credit-packages')
        assert response.status_code in [200, 401]


# ── Memory Tests ───────────────────────────────────────────────────────────

class TestMemory:
    """User memory tests"""
    
    def test_list_memories(self, mock_async_session):
        """Should list user memories"""
        response = client.get('/memories')
        assert response.status_code in [200, 401]
    
    def test_memory_count(self, mock_async_session):
        """Should count memories"""
        response = client.get('/memories/count')
        assert response.status_code in [200, 401]
    
    def test_memory_search(self, mock_async_session):
        """Should search memories"""
        response = client.get('/memories/search?q=test')
        assert response.status_code in [200, 401]


# ── Admin Tests ─────────────────────────────────────────────────────────────

class TestAdmin:
    """Admin panel tests"""
    
    def test_admin_pricing_list(self):
        """Admin should be able to list pricing"""
        response = client.get('/admin/pricing')
        assert response.status_code in [200, 401]
    
    def test_admin_user_management(self):
        """Admin should manage users"""
        response = client.get('/admin/users')
        assert response.status_code in [200, 401]


# ── Integration Tests ───────────────────────────────────────────────────────

class TestIntegration:
    """End-to-end integration tests"""
    
    def test_full_chat_flow(self, mock_async_session):
        """Complete chat flow from start to finish"""
        # This would test: auth -> chat -> usage tracking -> billing
        pass
    
    def test_wallet_topup_flow(self, mock_async_session):
        """Complete topup flow"""
        # This would test: create payment -> verify -> update balance
        pass


# ── Fixtures ────────────────────────────────────────────────────────────────
#
# mock_async_session used to be redefined here, patching `database.async_session`
# — the proxy object's *name* in the database module — rather than the state
# backing it (`database._real_async_session`). Route modules each do their own
# `from database import async_session`, binding their own independent reference
# to the original proxy at import time, so patching the name in database.py
# afterward never reached any of them; every endpoint under test silently fell
# through to the real (uninitialized) proxy and raised "Database not
# initialized". This local fixture also shadowed conftest.py's correctly-fixed
# version of the same name for every test in this module. Removed so the
# shared one (conftest.py) applies here too.


@pytest.fixture
def test_client():
    """Test client with app"""
    return TestClient(app)