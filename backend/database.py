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
engine: AsyncEngine | None = None
async_session: sessionmaker[AsyncSession] | None = None
rds = aioredis.from_url(REDIS_URL, decode_responses=True)
_http: httpx.AsyncClient | None = None
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
