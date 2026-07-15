"""
Database and shared infrastructure configuration.

Holds the global engine, session factory, Redis client, and HTTP client
that all route modules import from.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import httpx
import redis.asyncio as aioredis
from dotenv import load_dotenv
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

load_dotenv()

# ── Configuration ────────────────────────────────────────────────
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://multiai:multiai@127.0.0.1:5432/multiai')
REDIS_URL = os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0')
LITELLM_HOST = os.getenv('LITELLM_HOST', 'http://127.0.0.1:4000')
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', '')
if not ADMIN_TOKEN:
    raise RuntimeError('ADMIN_TOKEN must be configured; refusing to start')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:3003')
INTERNAL_TOKEN = os.getenv('INTERNAL_TOKEN', '')

# ── Runtime state ────────────────────────────────────────────────
_real_engine: AsyncEngine | None = None
_real_async_session: sessionmaker[AsyncSession] | None = None


class _EngineProxy:
    """Lazy proxy for the SQLAlchemy async engine."""
    def __getattr__(self, name):
        if _real_engine is None:
            raise RuntimeError('Engine not initialized')
        return getattr(_real_engine, name)

    def __bool__(self):
        return _real_engine is not None

    def __repr__(self):
        return f'<EngineProxy bound={_real_engine is not None}>'


class _SessionProxy:
    """Lazy proxy that defers to _real_async_session at call time."""
    def __call__(self):
        if _real_async_session is None:
            raise RuntimeError('Database not initialized')
        return _real_async_session()

    def __bool__(self):
        return _real_async_session is not None

    def __repr__(self):
        return f'<SessionProxy bound={_real_async_session is not None}>'


engine = _EngineProxy()
async_session = _SessionProxy()


class _HttpProxy:
    """Lazy proxy for the httpx.AsyncClient."""
    def __getattr__(self, name):
        if _real_http is None:
            raise RuntimeError('HTTP client not initialized')
        return getattr(_real_http, name)

    def __bool__(self):
        return _real_http is not None


_real_http: httpx.AsyncClient | None = None
_http = _HttpProxy()


def set_http(client: httpx.AsyncClient | None) -> None:
    global _real_http
    _real_http = client


def set_engine(eng: AsyncEngine | None) -> None:
    global _real_engine
    _real_engine = eng


def set_async_session(sm: sessionmaker[AsyncSession] | None) -> None:
    global _real_async_session
    _real_async_session = sm

rds = aioredis.from_url(REDIS_URL, decode_responses=True)
_start: datetime | None = None


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    if async_session is None:
        raise RuntimeError('db not initialized')
    async with async_session() as session:
        yield session


class HealthResponse(BaseModel):
    status: str
    uptime: float | None = None
    db: str
    redis: str
