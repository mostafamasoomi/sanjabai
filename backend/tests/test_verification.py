"""
Verification tests for Sanjabai backend - simplified version.
Tests core functionality without full app initialization.
"""
import pytest


class TestModels:
    """Test ORM models exist and have correct structure"""
    
    def test_user_model_exists(self):
        """User model should exist"""
        from models import User
        assert User is not None
        assert hasattr(User, '__tablename__')
    
    def test_wallet_model_exists(self):
        """Wallet model should exist"""
        from models import Wallet
        assert Wallet is not None
    
    def test_ledger_model_exists(self):
        """Ledger model should exist"""
        from models import Ledger
        assert Ledger is not None
    
    def test_all_core_models_exist(self):
        """All core models should be importable"""
        from models import (
            User, Ledger, Quota, ModelAlias, Pricing, Feature, Discount,
            AboutContent, ProxyConfig, Assistant, Conversation, Payment, Wallet,
            WalletReservation, UsageEvent, Notification, ApiKey, AuditLog,
            CreditPackage, UserBillingSetting, UserMemory, SkillTemplate,
            SkillTemplateRating, ScheduledTask, TaskExecution,
            RagDocument, RagChunk, RagEmbeddingUsage
        )
        assert True  # All imports successful


class TestRouters:
    """Test all routers are configured"""
    
    def test_chat_router(self):
        from chat import router
        assert router is not None
        assert len(router.routes) > 0
    
    def test_wallet_router(self):
        from wallet import router
        assert router is not None
    
    def test_pricing_router(self):
        from pricing import router
        assert router is not None
    
    def test_memory_router(self):
        from memory import router
        assert router is not None
    
    def test_admin_router(self):
        from admin import router
        assert router is not None


class TestSecurity:
    """Test security components"""
    
    def test_rate_limit_middleware(self):
        from security import RateLimitMiddleware
        assert RateLimitMiddleware is not None
    
    def test_security_headers_middleware(self):
        from security import SecurityHeadersMiddleware
        assert SecurityHeadersMiddleware is not None
    
    def test_csrf_middleware(self):
        from security import CsrfMiddleware
        assert CsrfMiddleware is not None


class TestServices:
    """Test service modules"""
    
    def test_billing_service(self):
        from services.billing import BillingService
        assert BillingService is not None
    
    def test_money_service(self):
        from services.money import Money
        assert Money is not None
    
    def test_memory_extractor(self):
        from services.memory_extractor import extract_memories
        assert extract_memories is not None


class TestModelsConfig:
    """Test model configuration"""

    # test_working_models_set was deleted (packet W): it only asserted that
    # specific model ids sat in the now-deleted `_HARDCODED_WORKING` fallback
    # set -- a list that had gone stale (every member unservable) months
    # before anyone noticed, precisely because this test kept reporting
    # green against the pinned literal instead of live behaviour. See
    # chat_models.py's get_working_models() for the fail-closed replacement.

    def test_model_catalog_table_exists(self):
        from models import ModelAlias
        assert ModelAlias is not None

    @pytest.mark.asyncio
    async def test_get_working_models_fails_closed_on_cold_cache(self):
        """No hardcoded fallback survives: a cold cache (nothing ever read
        successfully) plus an unreachable DB must return an EMPTY working
        set, not some baked-in list -- see chat_models.py's get_working_models()
        for why a non-empty fallback here is exactly the bug this deleted."""
        from unittest.mock import patch
        import chat as chat_mod
        with patch.object(chat_mod, 'async_session', None), \
             patch.object(chat_mod, '_WORKING_SET_CACHE', None):
            working = await chat_mod.get_working_models()
            assert working == frozenset()
            assert await chat_mod.is_working_model('tencent-hy3') is False
            assert await chat_mod.is_working_model('anything') is False

    @pytest.mark.asyncio
    async def test_get_working_models_serves_warm_cache_on_db_failure(self):
        """A DB blip with a previously-populated cache must keep serving the
        last-known-good set unchanged -- the normal transient-failure case
        must not regress into the same empty-set behaviour as a cold cache."""
        from unittest.mock import patch
        import chat as chat_mod
        with patch.object(chat_mod, 'async_session', None), \
             patch.object(chat_mod, '_WORKING_SET_CACHE', {'tencent-hy3', 'mistral-large'}):
            working = await chat_mod.get_working_models()
            assert working == frozenset({'tencent-hy3', 'mistral-large'})
            assert await chat_mod.is_working_model('tencent-hy3') is True


class TestDependencies:
    """Test dependency functions"""
    
    def test_get_user_id(self):
        from dependencies import _get_user_id
        assert _get_user_id is not None
    
    def test_admin_required(self):
        from dependencies import admin_required
        assert admin_required is not None


class TestDatabaseConfig:
    """Test database configuration"""
    
    def test_database_url_variable(self):
        from database import DATABASE_URL
        assert DATABASE_URL is not None
        assert 'postgresql' in DATABASE_URL
    
    def test_redis_url_variable(self):
        from database import REDIS_URL
        assert REDIS_URL is not None
    
    def test_base_url_variable(self):
        from database import BASE_URL
        assert BASE_URL is not None


class TestPricingConfig:
    """Test pricing configuration"""
    
    def test_pricing_model_exists(self):
        from models import Pricing
        assert Pricing is not None
    
    def test_plan_model_is_gone(self):
        """Migration 0049 retired the plan/subscription concept outright.

        Inverted rather than deleted on purpose: a re-added `Plan` would be
        someone reviving a product the owner decided against, and that
        should trip a test rather than pass silently.
        """
        import models
        assert not hasattr(models, 'Plan')
        assert not hasattr(models, 'Subscription')

    def test_credit_package_model_exists(self):
        from models import CreditPackage
        assert CreditPackage is not None