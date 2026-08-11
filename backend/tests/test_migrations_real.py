"""Real (non-mocked) migration tests against a disposable PostgreSQL.

Runs the actual ``backend/migrate.py`` runner against a *real* PostgreSQL so we
exercise the real migration path -- no mocks, no fakes.  The target database is
resolved in this order:

  1. ``$TEST_DATABASE_URL``  (its name must contain "test"), else
  2. ``$DATABASE_URL``       (its name must contain "test"), else
  3. a freshly ``CREATE DATABASE``'d temporary database
     (``sanjabai_test_<pid>_<rand>``), which is dropped after the session.

The tests SKIP (rather than fail) when:
  * the real ``asyncpg`` driver is unavailable, or
  * no disposable PostgreSQL can be reached / provisioned,

so the suite stays green in environments without a test DB while still running
the real migrations in CI.

Contract under test -- every one of these tables must exist after a full,
fresh migration:

    users, sessions, api_keys, wallets, ledger, payment_orders, quotas,
    model_aliases, pricing, audit_logs, model_catalog, usage_events,
    wallet_reservations
"""
from __future__ import annotations

import asyncio
import os
import random
import string
import sys
import urllib.parse

import pytest

# ── Undo conftest's global mocks so we talk to a REAL database ────────────
# conftest installs MagicMocks for both ``asyncpg`` and ``migrate`` *before*
# importing app.  We must evict those stubs or ``from migrate import migrate``
# would bind to the mock and never touch a real database.
sys.modules.pop("asyncpg", None)
sys.modules.pop("migrate", None)
try:  # pragma: no cover - env dependent
    import asyncpg  # noqa: F401  real driver
    _HAS_ASYNCPG = True
except Exception:  # pragma: no cover
    _HAS_ASYNCPG = False

from sqlalchemy import text  # noqa: E402
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from migrate import migrate  # the REAL runner  # noqa: E402

DEFAULT_URL = "postgresql+asyncpg://sanjabai:sanjabai@127.0.0.1:5432/sanjabai_test"

# The authoritative post-migration table contract (from the task spec).
EXPECTED_TABLES = {
    "users",
    "sessions",
    "api_keys",
    "wallet",
    "ledger",
    "payments",
    "quota",
    "model_aliases",
    "pricing",
    "audit_logs",
    "model_catalog",
    "usage_events",
    "wallet_reservations",
}


# ── helpers ────────────────────────────────────────────────────────────────
def _parse(url: str) -> dict:
    p = urllib.parse.urlparse(url)
    return {
        "scheme": p.scheme,
        "host": p.hostname or "127.0.0.1",
        "port": p.port or 5432,
        "user": p.username or "sanjabai",
        "password": p.password or "sanjabai",
        "database": (p.path or "").lstrip("/") or "sanjabai",
    }


def _with_db(url: str, dbname: str) -> str:
    p = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(p._replace(path=f"/{dbname}"))


def _db_name(url: str) -> str:
    return _parse(url)["database"]


def _random_suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


async def _create_temp_database(base_url: str) -> str:
    """Create a fresh ``sanjabai_test_<rand>`` database and return its URL.

    Raises if a maintenance database (postgres/template1) cannot be reached or
    the role lacks CREATEDB privilege -- the caller turns that into a skip.
    """
    info = _parse(base_url)
    name = f"sanjabai_test_{os.getpid()}_{_random_suffix()}"
    last_err: Exception | None = None
    for maint in ("postgres", "template1"):
        try:
            conn = await asyncpg.connect(
                host=info["host"],
                port=info["port"],
                user=info["user"],
                password=info["password"],
                database=maint,
            )
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", name
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{name}"')
            await conn.close()
            return _with_db(base_url, name)
        except Exception as exc:  # try the other maintenance db
            last_err = exc
            continue
    raise RuntimeError(f"cannot provision temp database: {last_err}")


async def _ping(engine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _reset_schema(engine) -> None:
    """Drop and recreate the public schema for a clean, disposable state."""
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))


async def _table_names(engine) -> set[str]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        ).all()
        return {r[0] for r in rows}


async def _applied_versions(engine) -> set[str]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(text("SELECT version FROM schema_migrations"))
        ).all()
        return {r[0] for r in rows}


# ── session-scoped database resolution ─────────────────────────────────────
@pytest.fixture(scope="session")
def test_db():
    """Resolve a disposable test database URL, or skip the whole session.

    Yields a dict: {url, owned} where ``owned`` is True when we created a
    temporary database (and therefore own its lifecycle / may reset it).
    """
    if not _HAS_ASYNCPG:
        pytest.skip("real asyncpg driver not available")

    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    owned = False
    temp_name: str | None = None

    if not url:
        url = DEFAULT_URL
        try:
            url = asyncio.run(_create_temp_database(url))
        except Exception as exc:  # pragma: no cover - env dependent
            pytest.skip(f"no disposable PostgreSQL available: {exc}")
        owned = True
        temp_name = _db_name(url)
    else:
        name = _db_name(url)
        if "test" not in name.lower():
            pytest.skip(f"refusing to run against non-test database '{name}'")
        # Confirm reachable with a read-only probe (no destructive ops).
        try:
            eng = create_async_engine(url, poolclass=NullPool)
            asyncio.run(_ping(eng))
            asyncio.run(eng.dispose())
        except Exception as exc:
            pytest.skip(f"cannot reach test database {url}: {exc}")

    yield {"url": url, "owned": owned}

    # Best-effort cleanup of a session-created temporary database.
    if temp_name:  # pragma: no cover - env dependent
        try:
            info = _parse(url)

            async def _drop_temp() -> None:
                conn = await asyncpg.connect(
                    host=info["host"],
                    port=info["port"],
                    user=info["user"],
                    password=info["password"],
                    database="postgres",
                )
                await conn.execute(f'DROP DATABASE IF EXISTS "{temp_name}"')
                await conn.close()

            asyncio.run(_drop_temp())
        except Exception:
            pass


@pytest.fixture
def engine(test_db):
    """A real engine.  For an owned temp DB we start from a clean schema."""
    url = test_db["url"]
    eng = create_async_engine(url, echo=False, poolclass=NullPool)
    if test_db["owned"]:
        asyncio.run(_reset_schema(eng))
    yield eng
    asyncio.run(eng.dispose())


# ── tests ──────────────────────────────────────────────────────────────────
def test_fresh_migration_runs(engine):
    """A brand-new database can be fully migrated without raising."""
    # must not raise
    asyncio.run(migrate(engine))


def test_rerun_is_idempotent(engine):
    """Re-running migrate on an already-migrated DB is a no-op.

    No error, and the recorded schema-version count is unchanged.
    """
    asyncio.run(migrate(engine))
    versions_first = asyncio.run(_applied_versions(engine))

    asyncio.run(migrate(engine))  # re-run
    versions_second = asyncio.run(_applied_versions(engine))

    assert versions_first, "no migration versions recorded after fresh migrate"
    assert versions_first == versions_second, (
        f"rerun changed recorded versions: {versions_first} -> {versions_second}"
    )


def test_existing_schema_migration_is_noop(engine):
    """When the schema already exists, migrate() is a true no-op.

    It must not raise, must not add new version rows, and must not alter the
    set of tables.
    """
    asyncio.run(migrate(engine))
    tables_before = asyncio.run(_table_names(engine))
    versions_before = asyncio.run(_applied_versions(engine))

    asyncio.run(migrate(engine))  # existing schema -> no-op

    tables_after = asyncio.run(_table_names(engine))
    versions_after = asyncio.run(_applied_versions(engine))

    assert tables_before == tables_after, "existing-schema migrate changed table set"
    assert (
        versions_before == versions_after
    ), "existing-schema migrate added version rows"


def test_all_expected_tables_exist(engine):
    """Every contract table is present after a fresh migration."""
    asyncio.run(migrate(engine))
    present = asyncio.run(_table_names(engine))
    missing = EXPECTED_TABLES - present
    assert not missing, f"missing expected tables after migration: {sorted(missing)}"
