"""
Test fixtures and configuration for Sanjabai backend.
Uses TestClient with dependency overrides for async DB and Redis.
"""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import AsyncMock, MagicMock, patch

# ── Mock Redis BEFORE app import ──────────────────────────
# The real client is redis.asyncio, so every method the app calls is awaited
# (`await rds.incr(...)`, `await rds.setex(...)`, etc). A plain MagicMock's
# methods return their return_value directly, not a coroutine — `await <int>`
# raises TypeError, which RateLimiter.is_allowed() (security.py) catches and
# "fails closed" on, turning every request in the suite into a 429 regardless
# of what the test is actually exercising; the same failure mode shows up as
# a swallowed-and-logged "Lockout check Redis error" from check_lockout(),
# silently changing login/signup behavior instead of raising loudly.
#
# The base object is AsyncMock, not MagicMock: AsyncMock auto-generates any
# *unconfigured* attribute access as another AsyncMock too, so a Redis method
# nobody explicitly listed here (setex, sadd, srem, zadd, ...) is still
# awaitable by default instead of silently reintroducing this exact bug the
# next time the app starts calling one. The explicit method assignments below
# exist only to pin a specific return_value for the handful the tests
# actually assert against.
_mock_redis_instance = AsyncMock()
_mock_redis_instance.incr = AsyncMock(return_value=1)
_mock_redis_instance.expire = AsyncMock(return_value=True)
_mock_redis_instance.get = AsyncMock(return_value=None)
_mock_redis_instance.set = AsyncMock(return_value=True)
_mock_redis_instance.delete = AsyncMock(return_value=True)

_mock_redis_module = MagicMock()
_mock_redis_module.Redis = MagicMock()
_mock_redis_module.Redis.from_url = MagicMock(return_value=_mock_redis_instance)

# database.py does `import redis.asyncio as aioredis`, which needs the parent
# to behave like a package: Python resolves the submodule through
# sys.modules['redis.asyncio'], and a bare MagicMock in sys.modules['redis']
# raises "'redis' is not a package". Registering the submodule explicitly is
# what makes the whole suite importable — without it conftest fails to load
# and every backend test errors during collection.
_mock_aioredis = MagicMock()
_mock_aioredis.from_url = MagicMock(return_value=_mock_redis_instance)
_mock_redis_module.asyncio = _mock_aioredis

sys.modules['redis'] = _mock_redis_module
sys.modules['redis.asyncio'] = _mock_aioredis

# ── Mock asyncpg ──────────────────────────────────────────
sys.modules['asyncpg'] = MagicMock()

# ── Mock migrate module BEFORE app import ─────────────────
# This prevents the lifespan from running real migrations
_mock_migrate_module = MagicMock()
_mock_migrate_module.migrate = AsyncMock()
sys.modules['migrate'] = _mock_migrate_module

# ── Import-time required secrets ──────────────────────────
# Both database.py and dependencies.py refuse to import without these, so they
# have to be set before `from app import ...` below. Values are throwaway.
import os
os.environ['ADMIN_TOKEN'] = 'test-admin-token'
os.environ.setdefault('API_KEY_PEPPER', 'test-api-key-pepper')

# ── Now import app ────────────────────────────────────────
import database as _database
from app import app, _gen_token, _hash_password

ADMIN_TOKEN = 'test-admin-token'

# ── TestClient without the deprecated httpx `app=` shortcut ──────────────────
# The suite previously subclassed starlette's TestClient to build the ASGI
# transport by hand, working around an httpx DeprecationWarning about the
# `app=` shortcut. Starlette no longer uses that shortcut, so the workaround is
# obsolete — and it reached into private internals (`_TestClientTransport`,
# `_AsyncBackend`, `_WrapASGI2`) whose signatures have since changed, which
# made every client-based test error with:
#
#     TypeError: _TestClientTransport.__init__() missing 1 required
#                keyword-only argument: 'client'
#
# starlette is not pinned in requirements.txt, so this broke on any fresh
# install. Using the public TestClient directly is both correct and stable.
from starlette.testclient import TestClient


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line(
        "markers", "live: requires a live server on localhost — only runs with --live"
    )


def pytest_addoption(parser):
    # test_document_generator.py's TestDocumentGeneratorLive documents
    # itself as "run against the live API: pytest ... --live", but no
    # --live option was ever actually registered, and nothing skipped that
    # class without it — so it unconditionally tried a real HTTP connection
    # to localhost:8081 on every plain `pytest tests/` run (this suite's
    # standard invocation, including CI), and unconditionally failed with
    # ConnectError wherever no such server happens to be running.
    parser.addoption(
        "--live", action="store_true", default=False,
        help="Run tests marked @pytest.mark.live against a real local server.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="requires a live server; pass --live to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def client():
    """FastAPI TestClient with mocked DB engine"""
    with patch('app.create_async_engine') as mock_engine_fn:
        mock_eng = MagicMock()
        mock_eng.dispose = AsyncMock()
        mock_engine_fn.return_value = mock_eng
        with TestClient(app) as c:
            yield c


@pytest.fixture
def auth_headers():
    """Create a valid auth token and return headers"""
    token = _gen_token()
    with patch('app.rds.get', new_callable=AsyncMock, return_value='1'), \
         patch('app.rds.expire', new_callable=AsyncMock):
        yield {'Authorization': f'Bearer {token}'}


@pytest.fixture
def admin_headers():
    """Create admin headers"""
    return {'x-admin-token': ADMIN_TOKEN}


@pytest.fixture
def mock_async_session():
    """Mock async_session maker returning a proper async session.

    ``session.execute`` is an *awaitable* coroutine function that returns the
    value stored on ``session._execute_result`` (defaulting to a result whose
    ``scalar_one()`` is ``0``).  Individual tests may overwrite
    ``session._execute_result`` or ``session.execute`` (e.g. the analytics
    test that needs different rows per call).

    Patches ``database._real_async_session`` — the state backing
    ``database.async_session``'s ``_SessionProxy`` — rather than
    ``app.async_session``. Every route module (wallet.py, chat.py, admin.py,
    ...) does its own ``from database import async_session``, which binds
    the *same shared proxy object* into each module's namespace; patching
    the name ``app.async_session`` only ever affected code living directly
    in app.py, which is essentially none of the actual endpoints per this
    project's router-per-domain architecture. Every other endpoint fell
    through to the proxy's real (unmocked) path — which, once the ratelimit
    bug above stopped masking it, surfaced as SQLAlchemy trying to run real
    async engine internals against the `client` fixture's MagicMock engine.
    """
    session = AsyncMock()
    # Default result so any endpoint that executes a query without an explicit
    # fixture setup still awaits a real (non-coroutine) result object.
    session._execute_result = make_result(scalar_one=0, scalar_one_or_none=0)

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
    with patch('app.async_session', maker), patch.object(_database, '_real_async_session', maker):
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

def make_result(fetchone=None, fetchall=None, scalar_one=None, scalar_one_or_none=None):
    """Create a mock SQLAlchemy result.

    If a test does not set ``session._execute_result`` before calling an
    endpoint that executes a query, the ``mock_async_session`` fixture uses a
    default built by this helper so that ``await session.execute(...)`` always
    returns a *real* (non-coroutine) result object.  This is what previously
    caused ``coroutine 'AsyncMockMixin._execute_mock_call' was never awaited``:
    accessing the unset ``_execute_result`` attribute on an ``AsyncMock``
    auto-created a child ``AsyncMock`` whose ``scalar_one()`` returned a
    coroutine instead of a value.
    """
    result = MagicMock()
    result.fetchone.return_value = fetchone
    result.fetchall.return_value = fetchall if fetchall is not None else []
    result.scalar_one.return_value = scalar_one
    result.scalar_one_or_none.return_value = scalar_one_or_none
    return result
