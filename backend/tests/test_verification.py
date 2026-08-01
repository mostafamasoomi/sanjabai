"""
Verification tests for Sanjhubai backend - simplified version.
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
            User, Subscription, Ledger, Quota, ModelAlias, Pricing, Feature, Discount,
            AboutContent, ProxyConfig, Assistant, Conversation, Payment, Wallet,
            WalletReservation, UsageEvent, Notification, ApiKey, AuditLog, Plan,
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
    
    def test_working_models_set(self):
        from chat import _HARDCODED_WORKING, get_working_models
        assert 'tencent-hy3' in _HARDCODED_WORKING
        assert 'deepseek-v4-pro' in _HARDCODED_WORKING
    
    def test_model_catalog_table_exists(self):
        from models import ModelAlias
        assert ModelAlias is not None


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
    
    def test_plan_model_exists(self):
        from models import Plan
        assert Plan is not None
    
    def test_credit_package_model_exists(self):
        from models import CreditPackage
        assert CreditPackage is not None