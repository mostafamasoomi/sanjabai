"""
Persian AI Gateway — Main application.

This is the thin orchestrator that:
1. Configures the FastAPI app and middleware
2. Manages the lifespan (engine, session, HTTP client, migrations)
3. Includes all route modules
4. Re-exports symbols for backward compatibility with tests/init_db/services
"""
from __future__ import annotations

import logging
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
logger = logging.getLogger(__name__)

import database as _db
from database import (
    engine, async_session, rds, _http, _start, Base, get_db, HealthResponse,
    DATABASE_URL, REDIS_URL, LITELLM_HOST, ADMIN_TOKEN, BASE_URL, INTERNAL_TOKEN,
)

# ── Import all ORM models (for backward compat: from app import User, etc.) ──
from models import (
    User, Ledger, Quota, ModelAlias, Pricing, Feature, Discount,
    AboutContent, ProxyConfig, Assistant, Conversation, Payment, Wallet,
    WalletReservation, UsageEvent, Notification, ApiKey, AuditLog,
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
from middleware.maintenance import MaintenanceModeMiddleware


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
    # Startup does NOT apply migrations by default.
    #
    # `docker compose build` copies untracked files into the image, so an
    # auto-applying startup let an unreviewed migration reach the production
    # schema simply because it happened to be sitting in the working tree when
    # somebody rebuilt for an unrelated reason. Schema changes are now a
    # deliberate act: `docker exec <api> python migrate.py`.
    #
    # Set AUTO_MIGRATE=true to restore the old apply-on-boot behaviour.
    import asyncio as _aio
    _auto_migrate = os.getenv('AUTO_MIGRATE', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
    _max_retries, _attempt = 1, 0
    while True:
        try:
            _pending = await migrate(_eng, apply=_auto_migrate)
            if _pending and not _auto_migrate:
                logger.warning(
                    'startup: %d migration(s) PENDING and not applied (AUTO_MIGRATE is off): %s '
                    '— apply deliberately with: docker exec <api> python migrate.py',
                    len(_pending), ', '.join(_pending),
                )
            elif _pending:
                logger.warning('startup: applied %d pending migration(s): %s',
                               len(_pending), ', '.join(_pending))
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

    # Provider model-list cache: refreshes each configured provider's
    # `GET /v1/models` into Redis on an interval (default 15 min, see
    # PROVIDER_CATALOG_REFRESH_INTERVAL). Discovery/health read this cache
    # instead of ever calling a slow upstream synchronously.
    async def _provider_catalog_loop():
        try:
            from provider_catalog import refresh_loop
            await refresh_loop()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[provider-catalog] loop stopped: {e}")

    _discovery_task = asyncio.create_task(_discovery_loop())
    _health_task = asyncio.create_task(_health_loop())
    _provider_catalog_task = asyncio.create_task(_provider_catalog_loop())

    # Scheduled-task runner. Gated by TASK_SCHEDULER_ENABLED and OFF by
    # default: this is the first path in the product that spends a user's
    # money with no human on the trigger, so it stays dark until a manual
    # task run has been seen to produce a correct ledger row on live.
    from services.task_scheduler import scheduler_loop
    _task_scheduler_task = asyncio.create_task(scheduler_loop())

    # Releases reservations stranded in status='reserved'. Not gated: it only
    # ever moves money back TO a user, and there was no sweeper at all until
    # now -- a 1000-toman hold from 2026-08-23 sat untouched for five days
    # because watchdog_rules.py:203 only *alerts*, above a threshold
    # (>5 rows OR >100000 toman) that a single small leak never reaches.
    # Verified against the live database on 2026-08-28: a synthetic 2h-old
    # reservation was swept, and both writes landed -- the row went
    # 'released' AND wallet.reserved dropped. Releasing the row alone is the
    # half-fix that leaves the money held; see services/reservation_sweeper.py.
    from services.reservation_sweeper import reservation_sweeper_loop
    _reservation_sweeper_task = asyncio.create_task(reservation_sweeper_loop())

    yield

    _health_task.cancel()
    _discovery_task.cancel()
    _provider_catalog_task.cancel()
    _task_scheduler_task.cancel()
    _reservation_sweeper_task.cancel()
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
#
# ORDER MATTERS AND IS COUNTER-INTUITIVE: Starlette applies add_middleware in
# REVERSE order, so the LAST one added is the OUTERMOST layer (first to see a
# request, last to see a response). Today that means a request travels
# RateLimit -> Csrf -> CSP -> SecurityHeaders -> GZip -> CORS -> route.
#
# MaintenanceModeMiddleware is added FIRST on purpose, which makes it the
# INNERMOST layer, sitting immediately in front of the routes. That is the
# position that matters: its 503 still travels back out through CORS,
# SecurityHeaders and CSP, so a maintenance response carries the same CORS and
# security headers as any other. Registered outermost instead, the 503 would
# be produced before CORSMiddleware ran and a cross-origin caller
# (api.sanjabai.com) would see an opaque CORS failure rather than the Persian
# "site is in maintenance" body it is supposed to read.
app.add_middleware(MaintenanceModeMiddleware)
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
from entitlements_endpoints import router as entitlements_router
from admin import router as admin_router
from admin_catalog import router as admin_catalog_router
from admin_packages import router as admin_packages_router
from admin_logical import router as admin_logical_router
from site_settings import router as site_settings_router
from admin_watchdog import router as admin_watchdog_router
from admin_free_tier import router as admin_free_tier_router
from admin_referral import router as admin_referral_router
from landing_content import router as landing_content_router
from admin_landing import router as admin_landing_router
from exchange_rate_admin import router as exchange_rate_admin_router
from admin_overhead import router as admin_overhead_router
# Beside admin_overhead deliberately: same problem, same idiom -- an expensive
# live measurement whose result is persisted in app_setting and read back
# lazily, triggered by an admin rather than by a loop on the hot path.
from admin_smart_router import router as admin_smart_router_router
from images import router as images_router
from admin_user_ops import router as admin_user_ops_router
from api_keys import router as api_keys_router
from combos import router as combos_router
from pricing import router as pricing_router
from payment_endpoints import router as payment_router
from notifications import router as notifications_router
from support import router as support_router
from tasks import router as tasks_router
from websocket import router as websocket_router
from rag_endpoints import router as rag_router
from document_generator import router as doc_gen_router
from model_health import router as model_health_router
from hermes import router as hermes_router
from status_page import router as status_page_router
from admin_monitoring import router as admin_monitoring_router

app.include_router(model_health_router)
app.include_router(status_page_router)
app.include_router(admin_monitoring_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(content_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(memory_router)
app.include_router(skills_router)
app.include_router(assistants_router)
app.include_router(wallet_router)
app.include_router(entitlements_router)
app.include_router(admin_router)
app.include_router(admin_catalog_router)
app.include_router(admin_packages_router)
# Phase C admin surface: approve/reject/pin the 1054 candidate rows the
# clusterer left in `proposed`. Read-only for users -- every logical model
# is still availability='maintenance' and nothing routes through them yet.
app.include_router(admin_logical_router)
app.include_router(site_settings_router)
app.include_router(admin_watchdog_router)
app.include_router(admin_free_tier_router)
app.include_router(admin_referral_router)
# Landing copy overrides: the public read is unauthenticated and fails open
# to {} (landing_content.py); the admin write is admin_required
# (admin_landing.py). Safe to register before migration 0052 is applied --
# measured with the table absent, /landing/content answers
# {"data":{},"updated_at":null} rather than 500ing, and both admin routes
# answer 401 without a token.
app.include_router(landing_content_router)
app.include_router(admin_landing_router)
app.include_router(exchange_rate_admin_router)
app.include_router(admin_overhead_router)
app.include_router(admin_smart_router_router)
app.include_router(images_router)
app.include_router(admin_user_ops_router)
app.include_router(api_keys_router)
app.include_router(combos_router)
app.include_router(pricing_router)
app.include_router(payment_router)
app.include_router(notifications_router)
# Telegram support bridge. Inert until BOTH TELEGRAM_BOT_TOKEN is set (unset
# today -- the bot container has been stopped for six days) and an admin puts
# a group id in app_setting.support_tg_group_id. /support/admin-reply refuses
# every call while the token is unset rather than treating "no secret" as
# "no check needed".
app.include_router(support_router)
app.include_router(tasks_router)
app.include_router(websocket_router)
app.include_router(rag_router)
app.include_router(doc_gen_router)
app.include_router(hermes_router)
