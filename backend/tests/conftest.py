"""
Test fixtures and configuration for Multiai backend.
Uses TestClient with dependency overrides for async DB and Redis.
"""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import AsyncMock, MagicMock, patch

# ── Mock Redis BEFORE app import ──────────────────────────
_mock_redis_instance = MagicMock()
_mock_redis_instance.incr.return_value = 1
_mock_redis_instance.expire.return_value = True
_mock_redis_instance.get.return_value = None
_mock_redis_instance.set.return_value = True
_mock_redis_instance.delete.return_value = True

_mock_redis_module = MagicMock()
_mock_redis_module.Redis = MagicMock()
_mock_redis_module.Redis.from_url = MagicMock(return_value=_mock_redis_instance)
sys.modules['redis'] = _mock_redis_module

# ── Mock asyncpg ──────────────────────────────────────────
sys.modules['asyncpg'] = MagicMock()

# ── Mock migrate module BEFORE app import ─────────────────
# This prevents the lifespan from running real migrations
_mock_migrate_module = MagicMock()
_mock_migrate_module.migrate = AsyncMock()
sys.modules['migrate'] = _mock_migrate_module

# ── Set test ADMIN_TOKEN ──────────────────────────────────
import os
os.environ['ADMIN_TOKEN'] = 'test-admin-token'

# ── Now import app ────────────────────────────────────────
from app import app, _gen_token, _hash_password

ADMIN_TOKEN = 'test-admin-token'


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")


@pytest.fixture
def client():
    """FastAPI TestClient with mocked DB engine"""
    with patch('app.create_async_engine') as mock_engine_fn:
        mock_eng = MagicMock()
        mock_eng.dispose = AsyncMock()
        mock_engine_fn.return_value = mock_eng
        from fastapi.testclient import TestClient
        with TestClient(app) as c:
            yield c


@pytest.fixture
def auth_headers():
    """Create a valid auth token and return headers"""
    token = _gen_token()
    with patch('app.rds.get', return_value='1'), patch('app.rds.expire'):
        yield {'Authorization': f'Bearer {token}'}


@pytest.fixture
def admin_headers():
    """Create admin headers"""
    return {'x-admin-token': ADMIN_TOKEN}


@pytest.fixture
def mock_async_session():
    """Mock async_session maker returning a proper async session"""
    session = AsyncMock()

    async def mock_execute(*args, **kwargs):
        return session._execute_result

    session.execute = mock_execute
    session.commit = AsyncMock()

    async def mock_refresh(obj, *args, **kwargs):
        if not hasattr(obj, 'id') or obj.id is None:
            obj.id = 1
        if not hasattr(obj, 'email'):
            obj.email = 'test@example.com'
        if not hasattr(obj, 'created_at'):
            obj.created_at = '2024-01-01'

    session.refresh = mock_refresh
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.get = AsyncMock()

    class _Ctx:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *args):
            pass

    maker = MagicMock(return_value=_Ctx())
    with patch('app.async_session', maker):
        yield session


def make_row(**kwargs):
    """Create a mock row with attribute access"""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row

def make_fetchone(**kwargs):
    """Create a mock for execute().fetchone() returning a row"""
    row = make_row(**kwargs) if kwargs else None
    return row

def make_result(fetchone=None, fetchall=None):
    """Create a mock SQLAlchemy result"""
    result = MagicMock()
    result.fetchone.return_value = fetchone
    result.fetchall.return_value = fetchall if fetchall is not None else []
    return result
