"""
Persian AI Gateway — Main application.

This is the thin orchestrator that:
1. Configures the FastAPI app and middleware
2. Manages the lifespan (engine, session, HTTP client, migrations)
3. Includes all route modules
4. Re-exports symbols for backward compatibility with tests/init_db/services
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

load_dotenv()

# ── Import shared infrastructure ────────────────────────────────
# These are imported first so they're available when route modules load
import database as _db
from database import (
    engine, async_session, rds, _http, _start, Base, get_db, HealthResponse,
    DATABASE_URL, REDIS_URL, LITELLM_HOST, ADMIN_TOKEN, BASE_URL, INTERNAL_TOKEN,
)

# ── Import all ORM models (for backward compat: from app import User, etc.) ──
from models import (
    User, Subscription, Ledger, Quota, ModelAlias, Pricing, Feature, Discount,
    AboutContent, ProxyConfig, Assistant, Conversation, Payment, Wallet,
    WalletReservation, UsageEvent, Notification, ApiKey, AuditLog, Plan,
    CreditPackage, UserBillingSetting, UserMemory, SkillTemplate,
    SkillTemplateRating, ScheduledTask, TaskExecution,
    RagDocument, RagChunk, RagEmbeddingUsage,
    HermesOffering, HermesSkillCatalog, HermesOrder, HermesServer,
    HermesServerSkill, HermesAgentEvent,
)

# ── Import shared helpers (for backward compat: from app import _gen_token, etc.) ──
from dependencies import (
    _gen_token, _hash_password, _verify_password, _hash_api_key,
    _to_fa, _escape_like, _get_user_id, _get_session_user_id,
    admin_required, _write_audit_log, notify_user,
    SESSION_TTL, SESSION_COOKIE_NAME, SESSION_COOKIE_SECURE,
    ADMIN_COOKIE_NAME, ADMIN_CSRF_COOKIE_NAME, ADMIN_SESSION_TTL,
    API_KEY_PEPPER,
)

# ── Security middleware ─────────────────────────────────────────
from security import RateLimitMiddleware, SecurityHeadersMiddleware, CsrfMiddleware


# ── Inline security-headers middleware (defense-in-depth) ─────────
from starlette.middleware.base import BaseHTTPMiddleware


class ContentSecurityPolicyMiddleware(BaseHTTPMiddleware):
    """Explicitly set CSP and core security headers on every response.

    This complements security.SecurityHeadersMiddleware and guarantees the
    headers exist even if that middleware is removed/renamed. Headers already
    present on the response (e.g. set by the security middleware) are preserved.
    """

    _SECURITY_HEADERS = {
        'Content-Security-Policy': (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none';"
        ),
        'X-Frame-Options': 'DENY',
        'X-Content-Type-Options': 'nosniff',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
    }

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for key, value in self._SECURITY_HEADERS.items():
            if key not in response.headers:
                response.headers[key] = value
        return response


# ═══════════════════════════════════════════════════════════════════
# Lifespan
# ═══════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global engine, async_session, _start, _http
    # Update database module globals via proxy-aware setters
    _eng = create_async_engine(
        DATABASE_URL, echo=False, pool_pre_ping=True,
        pool_size=10, max_overflow=20, pool_recycle=300, pool_timeout=30,
    )
    _db.set_engine(_eng)
    _db.set_async_session(sessionmaker(_eng, class_=AsyncSession, expire_on_commit=False))
    _db.set_http(httpx.AsyncClient(
        timeout=httpx.Timeout(90, connect=10),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        trust_env=False,
    ))
    _db._start = datetime.now(timezone.utc)

    from migrate import migrate
    # Migration with retry guard — reduces startup fragility
    import asyncio as _aio
    _max_retries, _attempt = 1, 0
    while True:
        try:
            await migrate(_eng)
            break
        except Exception:
            _attempt += 1
            if _attempt > _max_retries:
                raise
            await _aio.sleep(5)

    # Start background pricing refresh task (every 15 minutes)
    import asyncio
    async def _pricing_refresh_loop():
        await asyncio.sleep(30)  # initial delay for startup
        while True:
            try:
                from content import refresh_pricing
                result = await refresh_pricing()
                print(f"[pricing-refresh] {result}")
            except Exception as e:
                print(f"[pricing-refresh] error: {e}")
            await asyncio.sleep(900)  # 15 minutes

    _pricing_task = asyncio.create_task(_pricing_refresh_loop())

    # Hermes server product: charge active servers past their paid_through_at
    # for another month, once a day. Idempotent per calendar month (see
    # hermes.run_renewal_cycle), so a missed/late tick just catches up.
    async def _hermes_renewal_loop():
        await asyncio.sleep(60)  # initial delay for startup
        while True:
            try:
                from hermes import run_renewal_cycle
                result = await run_renewal_cycle()
                print(f"[hermes-renewal] {result}")
            except Exception as e:
                print(f"[hermes-renewal] error: {e}")
            await asyncio.sleep(86400)  # 24 hours

    _hermes_renewal_task = asyncio.create_task(_hermes_renewal_loop())

    # Model discovery + health.
    #
    # Discovery keeps model_catalog in step with what the upstreams expose;
    # the health loop probes each catalog model on a slow cycle and rolls the
    # results up with the passive samples chat.py records from real traffic.
    # Both are best-effort: neither may take the API down if an upstream is
    # unreachable at boot.
    async def _discovery_loop():
        await asyncio.sleep(20)
        while True:
            try:
                from model_discovery import sync_all
                print(f"[model-discovery] {await sync_all()}")
            except Exception as e:
                print(f"[model-discovery] error: {e}")
            await asyncio.sleep(int(os.getenv('MODEL_DISCOVERY_INTERVAL', '3600')))

    async def _health_loop():
        try:
            from model_health import health_loop
            await health_loop()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[model-health] loop stopped: {e}")

    _discovery_task = asyncio.create_task(_discovery_loop())
    _health_task = asyncio.create_task(_health_loop())

    yield

    _health_task.cancel()
    _discovery_task.cancel()
    _pricing_task.cancel()
    _hermes_renewal_task.cancel()
    if _db._real_http:
        await _db._real_http.aclose()
    await _eng.dispose()


# ═══════════════════════════════════════════════════════════════════
# App creation
# ═══════════════════════════════════════════════════════════════════

_debug_raw = os.getenv('DEBUG', '').lower()
_is_production = os.getenv('ENV', 'production').lower() not in ('development', 'dev') and _debug_raw not in ('1', 'true', 'yes')
app = FastAPI(
    title='Persian AI Gateway',
    version='0.1.0',
    lifespan=lifespan,
    docs_url=None if _is_production else '/docs',
    redoc_url=None if _is_production else '/redoc',
    openapi_url=None if _is_production else '/openapi.json',
)

# ── Middleware ───────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('CORS_ORIGINS', 'https://sanjabai.ir,http://localhost:3003').split(','),
    allow_credentials=False,
    allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allow_headers=['Authorization', 'Content-Type', 'X-Requested-With'],
)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ContentSecurityPolicyMiddleware)
app.add_middleware(CsrfMiddleware)
app.add_middleware(RateLimitMiddleware)


# ═══════════════════════════════════════════════════════════════════
# Register all routers
# ═══════════════════════════════════════════════════════════════════

# API ROUTE CONVENTION:
#   /v1/ prefix   – public-facing OpenAI-compatible API (models, chat)
#   /admin/*       – internal/admin management endpoints (no /v1/)
#   /auth/*        – authentication & user profile endpoints
#   /health/*      – service health probes
#   All other paths – app-level endpoints (conversations, wallet, etc.)

from health import router as health_router
from auth import router as auth_router
from content import router as content_router
from chat import router as chat_router
from conversations import router as conversations_router
from memory import router as memory_router
from skills import router as skills_router
from assistants import router as assistants_router
from wallet import router as wallet_router
from admin import router as admin_router
from api_keys import router as api_keys_router
from pricing import router as pricing_router
from payment_endpoints import router as payment_router
from notifications import router as notifications_router
from tasks import router as tasks_router
from websocket import router as websocket_router
from rag_endpoints import router as rag_router
from document_generator import router as doc_gen_router
from model_health import router as model_health_router
from hermes import router as hermes_router

app.include_router(model_health_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(content_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(memory_router)
app.include_router(skills_router)
app.include_router(assistants_router)
app.include_router(wallet_router)
app.include_router(admin_router)
app.include_router(api_keys_router)
app.include_router(pricing_router)
app.include_router(payment_router)
app.include_router(notifications_router)
app.include_router(tasks_router)
app.include_router(websocket_router)
app.include_router(rag_router)
app.include_router(doc_gen_router)
app.include_router(hermes_router)
