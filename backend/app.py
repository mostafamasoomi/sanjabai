from __future__ import annotations
import os, hashlib, secrets, base64, hmac, json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
import csv
import io
import re as _re
from pydantic import BaseModel
import httpx
import redis
import sqlalchemy
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from dotenv import load_dotenv

from services.billing import SqlBillingRepo

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://multiai:multiai@127.0.0.1:5432/multiai')
REDIS_URL = os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0')
LITELLM_HOST = os.getenv('LITELLM_HOST', 'http://127.0.0.1:4000')
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', '')
if not ADMIN_TOKEN:
    raise RuntimeError('ADMIN_TOKEN must be configured; refusing to start')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:3003')

engine: AsyncEngine | None = None
async_session: sessionmaker[AsyncSession] | None = None
rds = redis.Redis.from_url(REDIS_URL, decode_responses=True)
_http: httpx.AsyncClient | None = None  # shared connection pool

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str | None] = mapped_column(unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(index=True)
    phone: Mapped[str | None] = mapped_column(unique=True)
    referral_code: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    referred_by: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Subscription(Base):
    __tablename__ = 'subscriptions'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    plan: Mapped[str] = mapped_column(sqlalchemy.String(32))
    starts_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    ends_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default='active')
    monthly_token_quota: Mapped[int] = mapped_column(default=0)
    tokens_used_this_period: Mapped[int] = mapped_column(default=0)
    auto_renew: Mapped[bool] = mapped_column(default=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    price_paid: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Ledger(Base):
    __tablename__ = 'ledger'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    amount: Mapped[int]
    balance_after: Mapped[int]
    reason: Mapped[str]
    meta: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Quota(Base):
    __tablename__ = 'quota'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    daily_limit: Mapped[int]
    used_today: Mapped[int] = mapped_column(default=0)
    reset_at: Mapped[datetime]
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class ModelAlias(Base):
    __tablename__ = 'model_aliases'
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(unique=True, index=True)
    provider: Mapped[str]
    model_id: Mapped[str]
    priority: Mapped[int] = mapped_column(default=0)
    enabled: Mapped[bool] = mapped_column(default=True)

class Pricing(Base):
    """Versioned model pricing.

    Prices are immutable history: ``set_pricing`` never UPDATEs an existing
    row, it INSERTs a new version (a higher ``price_version``) for the model.
    The active price for a model is the row with the greatest
    ``effective_from`` (see :func:`get_active_price`).
    """
    __tablename__ = 'pricing'
    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(index=True)
    provider: Mapped[str] = mapped_column(default='unknown')
    input_per_million: Mapped[int] = mapped_column(default=0)
    output_per_million: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(default='IRT')
    source: Mapped[str | None] = mapped_column(nullable=True)
    price_version: Mapped[int] = mapped_column(default=1)
    effective_from: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    effective_to: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    __table_args__ = (
        sqlalchemy.UniqueConstraint('model', 'price_version', name='uq_pricing_model_version'),
    )

class Feature(Base):
    __tablename__ = 'features'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(default='')
    icon: Mapped[str] = mapped_column(default='star')
    active: Mapped[bool] = mapped_column(default=True)
    order_idx: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Discount(Base):
    __tablename__ = 'discounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(unique=True)
    percent: Mapped[int] = mapped_column(default=10)
    active: Mapped[bool] = mapped_column(default=True)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class AboutContent(Base):
    __tablename__ = 'about_content'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(default='درباره ما')
    body: Mapped[str] = mapped_column(default='')
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class ProxyConfig(Base):
    __tablename__ = 'proxy_config'
    id: Mapped[int] = mapped_column(primary_key=True)
    proxy_url: Mapped[str] = mapped_column(default='')
    proxy_type: Mapped[str] = mapped_column(default='socks5')
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(default='گفتگوی جدید')
    model: Mapped[str] = mapped_column(default='')
    messages: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    amount: Mapped[int]
    authority: Mapped[str] = mapped_column(unique=True, index=True)
    ref_id: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default='pending')
    payment_type: Mapped[str] = mapped_column(default='wallet_topup')
    reference_id: Mapped[str | None] = mapped_column(nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Wallet(Base):
    """Authoritative per-user balance row. Locked with FOR UPDATE on writes.

    ``balance`` is committed (spendable + held); ``reserved`` is the sum of open
    holds. Available balance = balance - reserved.
    """
    __tablename__ = 'wallet'
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), primary_key=True)
    balance: Mapped[int] = mapped_column(default=0)
    reserved: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class WalletReservation(Base):
    """A hold taken against the wallet before an upstream (paid) call."""
    __tablename__ = 'wallet_reservations'
    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[str] = mapped_column(unique=True, index=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    amount: Mapped[int]
    currency: Mapped[str] = mapped_column(default='IRT')
    status: Mapped[str] = mapped_column(default='reserved')
    model: Mapped[str | None] = mapped_column(nullable=True)
    price_version: Mapped[str | None] = mapped_column(nullable=True)
    request_id: Mapped[str | None] = mapped_column(nullable=True)
    idempotency_key: Mapped[str] = mapped_column(unique=True, index=True)
    reason: Mapped[str | None] = mapped_column(nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    settled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(nullable=True)


class UsageEvent(Base):
    """Immutable record of a single upstream model call / charge."""
    __tablename__ = 'usage_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(unique=True, index=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    model: Mapped[str]
    price_version: Mapped[str | None] = mapped_column(nullable=True)
    provider: Mapped[str | None] = mapped_column(nullable=True)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cached_input_tokens: Mapped[int] = mapped_column(default=0)
    reasoning_tokens: Mapped[int] = mapped_column(default=0)
    reservation_id: Mapped[str | None] = mapped_column(nullable=True)
    charged_amount: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(default='IRT')
    upstream_status: Mapped[str | None] = mapped_column(nullable=True)
    upstream_error: Mapped[str | None] = mapped_column(nullable=True)
    meta: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    billing_source: Mapped[str] = mapped_column(default='wallet')
    subscription_id: Mapped[int | None] = mapped_column(nullable=True)
    credits_charged: Mapped[int] = mapped_column(default=0)
    payg_charged: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    type: Mapped[str] = mapped_column(default='info')
    title: Mapped[str]
    body: Mapped[str] = mapped_column(default='')
    read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class ApiKey(Base):
    __tablename__ = 'api_keys'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(default='Default')
    key_hash: Mapped[str] = mapped_column(unique=True)
    key_prefix: Mapped[str] = mapped_column(default='sk-')
    active: Mapped[bool] = mapped_column(default=True)
    last_used: Mapped[datetime | None] = mapped_column(nullable=True)
    scopes: Mapped[str] = mapped_column(default='read')
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class AuditLog(Base):
    """Immutable record of privileged/admin actions for compliance + forensics."""
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    admin_user_id: Mapped[int | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(nullable=False)
    target_type: Mapped[str | None] = mapped_column(nullable=True)
    target_id: Mapped[str | None] = mapped_column(nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))



class Plan(Base):
    """Subscription plan definitions."""
    __tablename__ = 'plans'
    id: Mapped[str] = mapped_column(primary_key=True)  # 'free', 'basic', 'pro', 'unlimited'
    name_fa: Mapped[str]
    name_en: Mapped[str]
    price_monthly: Mapped[int] = mapped_column(default=0)
    monthly_token_quota: Mapped[int] = mapped_column(default=0)
    daily_token_limit: Mapped[int] = mapped_column(default=0)
    models_allowed: Mapped[list | None] = mapped_column(sqlalchemy.JSON, default=list)
    priority_queue: Mapped[bool] = mapped_column(default=False)
    features: Mapped[list | None] = mapped_column(sqlalchemy.JSON, default=list)
    active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class CreditPackage(Base):
    """Pre-paid credit packages with optional bonus."""
    __tablename__ = 'credit_packages'
    id: Mapped[str] = mapped_column(primary_key=True)  # 'starter', 'popular', 'mega', 'whale'
    name_fa: Mapped[str]
    name_en: Mapped[str]
    base_amount: Mapped[int] = mapped_column(default=0)
    bonus_percent: Mapped[int] = mapped_column(default=0)
    total_credits: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class UserBillingSetting(Base):
    """Per-user billing preferences (PAYG toggle, limits)."""
    __tablename__ = 'user_billing_settings'
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), primary_key=True)
    payg_enabled: Mapped[bool] = mapped_column(default=True)
    payg_hard_limit: Mapped[int | None] = mapped_column(nullable=True)
    notify_on_usage_pct: Mapped[int] = mapped_column(default=80)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class UserMemory(Base):
    """Persistent user memory entries for memory-augmented chat."""
    __tablename__ = 'user_memories'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    content: Mapped[str] = mapped_column()
    category: Mapped[str] = mapped_column(default='general')
    source: Mapped[str] = mapped_column(default='manual')
    tags: Mapped[list | None] = mapped_column(sqlalchemy.ARRAY(sqlalchemy.Text), default=list)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class SkillTemplate(Base):
    """Skill template for the marketplace."""
    __tablename__ = 'skill_templates'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(sqlalchemy.ForeignKey('users.id'), nullable=True)
    title: Mapped[str]
    title_fa: Mapped[str]
    description: Mapped[str] = mapped_column(default='')
    description_fa: Mapped[str] = mapped_column(default='')
    category: Mapped[str] = mapped_column(default='general')
    prompt_template: Mapped[str]
    variables: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, default=list)
    default_model: Mapped[str] = mapped_column(default='')
    is_public: Mapped[bool] = mapped_column(default=False)
    is_featured: Mapped[bool] = mapped_column(default=False)
    usage_count: Mapped[int] = mapped_column(default=0)
    rating_sum: Mapped[int] = mapped_column(default=0)
    rating_count: Mapped[int] = mapped_column(default=0)
    tags: Mapped[list | None] = mapped_column(sqlalchemy.JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class SkillTemplateRating(Base):
    """Rating for a skill template."""
    __tablename__ = 'skill_template_ratings'
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('skill_templates.id'))
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'))
    rating: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class ScheduledTask(Base):
    __tablename__ = 'scheduled_tasks'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(default='')
    prompt: Mapped[str]
    model: Mapped[str] = mapped_column(default='mimo-v2.5')
    cron_expression: Mapped[str] = mapped_column(default='0 9 * * *')
    is_active: Mapped[bool] = mapped_column(default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    run_count: Mapped[int] = mapped_column(default=0)
    last_result: Mapped[str | None] = mapped_column(nullable=True)
    delivery_channel: Mapped[str] = mapped_column(default='dashboard')
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class TaskExecution(Base):
    __tablename__ = 'task_executions'
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('scheduled_tasks.id'))
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(default='pending')
    result: Mapped[str | None] = mapped_column(nullable=True)
    tokens_used: Mapped[int] = mapped_column(default=0)
    cost_toman: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class HealthResponse(BaseModel):
    status: str
    uptime: float | None = None
    db: str
    redis: str

_start: datetime | None = None

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global engine, async_session, _start, _http
    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    _http = httpx.AsyncClient(timeout=httpx.Timeout(90, connect=10), limits=httpx.Limits(max_connections=20, max_keepalive_connections=10))
    from migrate import migrate
    await migrate(engine)
    _start = datetime.now(timezone.utc)
    yield
    await _http.aclose()
    await engine.dispose()

app = FastAPI(title='Persian AI Gateway', version='0.1.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('CORS_ORIGINS', 'https://multiai.ir,http://localhost:3003').split(','),
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Security middleware
from security import RateLimitMiddleware, SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

async def get_db() -> AsyncIterator[AsyncSession]:
    if async_session is None:
        raise RuntimeError('db not initialized')
    async with async_session() as session:
        yield session

def admin_required(request: Request) -> bool:
    # Primary: isolated server-side admin session cookie (CSRF-protected mutations)
    sid = request.cookies.get(ADMIN_COOKIE_NAME)
    if sid:
        sess = _get_admin_session(sid)
        if sess:
            if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
                csrf = request.headers.get('x-csrf-token') or request.headers.get('x-csrf')
                if not csrf or not hmac.compare_digest(csrf, sess.get('csrf', '')):
                    return False
            return True
    # Legacy: constant-time header token (no CSRF needed for header-based auth)
    token = request.headers.get('x-admin-token') or request.headers.get('authorization', '').removeprefix('Bearer ')
    return bool(ADMIN_TOKEN) and bool(token) and hmac.compare_digest(token, ADMIN_TOKEN)


class AdminLogin(BaseModel):
    token: str


@app.post('/admin/login')
async def admin_login(payload: AdminLogin) -> JSONResponse:
    """Validate admin token and establish an isolated server-side session."""
    if not ADMIN_TOKEN or not hmac.compare_digest(payload.token, ADMIN_TOKEN):
        return JSONResponse({'detail': 'invalid admin token'}, status_code=401)
    sid, csrf = _create_admin_session()
    await _write_audit_log('admin.login')
    response = JSONResponse({'status': 'ok', 'csrf': csrf})
    response.set_cookie(
        ADMIN_COOKIE_NAME, sid, httponly=True,
        secure=SESSION_COOKIE_SECURE, samesite='lax',
        max_age=ADMIN_SESSION_TTL, path='/',
    )
    response.set_cookie(
        ADMIN_CSRF_COOKIE_NAME, csrf, httponly=False,
        secure=SESSION_COOKIE_SECURE, samesite='lax',
        max_age=ADMIN_SESSION_TTL, path='/',
    )
    return response


@app.post('/admin/logout')
async def admin_logout(request: Request) -> JSONResponse:
    """Clear the server-side admin session."""
    sid = request.cookies.get(ADMIN_COOKIE_NAME)
    if sid:
        rds.delete(f'admin_session:{sid}')
    await _write_audit_log('admin.logout')
    response = JSONResponse({'status': 'ok'})
    response.delete_cookie(ADMIN_COOKIE_NAME, path='/')
    response.delete_cookie(ADMIN_CSRF_COOKIE_NAME, path='/')
    return response


@app.get('/health/live')
async def health_live() -> dict[str, str]:
    return {'status': 'ok'}


@app.get('/health/ready')
async def health_ready() -> Response:
    db_ok = True
    redis_ok = True
    try:
        if engine is None:
            db_ok = False
        else:
            async with engine.connect() as _:
                pass
    except Exception:
        db_ok = False
    try:
        rds.ping()
    except Exception:
        redis_ok = False
    if db_ok and redis_ok:
        return JSONResponse({'status': 'ok'}, status_code=200)
    return JSONResponse({'status': 'unavailable', 'db': 'ok' if db_ok else 'down', 'redis': 'ok' if redis_ok else 'down'}, status_code=503)


@app.get('/health')
async def health(request: Request) -> HealthResponse:
    db_status = 'ok'
    redis_status = 'ok'
    try:
        if engine is None:
            raise RuntimeError('init')
        async with engine.connect() as _:
            pass
    except Exception:
        db_status = 'down'
    try:
        rds.ping()
    except Exception:
        redis_status = 'down'
    return HealthResponse(status='ok', uptime=(datetime.now(timezone.utc) - _start).total_seconds() if _start else 0, db=db_status, redis=redis_status)

@app.get('/health/detailed')
async def health_detailed(request: Request) -> JSONResponse:
    """Detailed health check with metrics"""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)

    import psutil
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    db_status = 'ok'
    redis_status = 'ok'
    litellm_status = 'ok'

    try:
        if engine:
            async with engine.connect() as _:
                pass
    except Exception:
        db_status = 'down'

    try:
        rds.ping()
    except Exception:
        redis_status = 'down'

    try:
        r = await _http.get(f'{LITELLM_HOST}/health', timeout=5)
        if r.status_code != 200:
            litellm_status = 'degraded'
    except Exception:
        litellm_status = 'down'

    return JSONResponse({
        'status': 'ok' if all(s == 'ok' for s in [db_status, redis_status, litellm_status]) else 'degraded',
        'uptime_seconds': (datetime.now(timezone.utc) - _start).total_seconds() if _start else 0,
        'services': {
            'database': db_status,
            'redis': redis_status,
            'litellm': litellm_status,
        },
        'system': {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': mem.percent,
            'memory_used_gb': round(mem.used / (1024**3), 1),
            'memory_total_gb': round(mem.total / (1024**3), 1),
            'disk_percent': disk.percent,
            'disk_free_gb': round(disk.free / (1024**3), 1),
        },
    })

@app.get('/')
async def root() -> dict[str, str]:
    return {'service': 'Persian AI Gateway', 'docs': '/docs'}

@app.get('/v1/models')
async def list_models(request: Request) -> dict[str, Any]:
    models = []
    try:
        r = await _http.get(f"{LITELLM_HOST}/v1/models", timeout=8)
        if r.status_code == 200:
            models = r.json().get('data', [])
    except Exception:
        pass
    return {'object': 'list', 'data': models}

def _catalog_row_to_item(m: dict[str, Any]) -> dict[str, Any]:
    """Map a model_catalog DB row (dict) to the camelCase catalog contract."""
    return {
        'id': m['id'],
        'providerModelId': m['provider_model_id'],
        'provider': m['provider'],
        'displayName': m['display_name'],
        'description': m.get('description'),
        'modalities': m.get('modalities') or {'input': ['text'], 'output': ['text']},
        'capabilities': m.get('capabilities') or [],
        'recommendedFor': m.get('recommended_for') or [],
        'contextWindow': m['context_window'],
        'maxOutputTokens': m.get('max_output_tokens'),
        'pricing': {
            'currency': m.get('currency') or 'IRT',
            'inputPerMillion': float(m.get('input_per_million') or 0),
            'outputPerMillion': float(m.get('output_per_million') or 0),
            'cachedInputPerMillion': float(m['cached_input_per_million']) if m.get('cached_input_per_million') is not None else None,
            'reasoningPerMillion': float(m['reasoning_per_million']) if m.get('reasoning_per_million') is not None else None,
            'priceVersion': m.get('price_version') or 'v1',
            'effectiveFrom': m.get('effective_from'),
        },
        'availability': m.get('availability') or 'available',
        'audience': m.get('audience') or ['consumer', 'developer'],
        'rateLimit': m.get('rate_limit'),
        'deprecatedAt': m.get('deprecated_at'),
        'lastVerifiedAt': m.get('last_verified_at'),
        'provenance': m.get('provenance') or 'admin-approved',
    }

async def _load_catalog_rows() -> list[dict[str, Any]]:
    """Load approved catalog from DB; return [] if unavailable/empty."""
    if async_session is None:
        return []
    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text('SELECT * FROM model_catalog ORDER BY provider, id'))
            return [dict(r._mapping) for r in res.fetchall()]
    except Exception:
        return []

async def _litellm_fallback_catalog() -> list[dict[str, Any]]:
    """Build a minimal fallback catalog from litellm when DB has no entries."""
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    try:
        r = await _http.get(f"{LITELLM_HOST}/v1/models", timeout=8)
        if r.status_code == 200:
            for entry in r.json().get('data', []):
                    mid = str(entry.get('id') or '').strip()
                    if not mid:
                        continue
                    provider = mid.split('/')[0] if '/' in mid else (entry.get('owned_by') or 'unknown')
                    items.append({
                        'id': mid.replace('/', '-').lower(),
                        'providerModelId': mid,
                        'provider': provider,
                        'displayName': mid,
                        'description': None,
                        'modalities': {'input': ['text'], 'output': ['text']},
                        'capabilities': ['chat'],
                        'recommendedFor': [],
                        'contextWindow': 8192,
                        'maxOutputTokens': None,
                        'pricing': {
                            'currency': 'IRT',
                            'inputPerMillion': 0,
                            'outputPerMillion': 0,
                            'cachedInputPerMillion': None,
                            'reasoningPerMillion': None,
                            'priceVersion': 'fallback',
                            'effectiveFrom': now,
                        },
                        'availability': 'available',
                        'audience': ['consumer', 'developer'],
                        'rateLimit': None,
                        'deprecatedAt': None,
                        'lastVerifiedAt': now,
                        'provenance': 'fallback',
                    })
    except Exception:
        pass
    return items

@app.get('/catalog/models')
async def catalog_models(request: Request) -> JSONResponse:
    """Approved model catalog from DB, with litellm fallback when DB is empty."""
    rows = await _load_catalog_rows()
    if rows:
        data = [_catalog_row_to_item(r) for r in rows]
        source = 'approved-catalog'
    else:
        data = await _litellm_fallback_catalog()
        source = 'fallback'
    return JSONResponse(jsonable_encoder({
        'data': data,
        'generatedAt': datetime.now(timezone.utc),
        'source': source,
    }))

@app.get('/catalog/pricing')
async def catalog_pricing(request: Request) -> JSONResponse:
    """Versioned pricing for catalog models (falls back to pricing table)."""
    rows = await _load_catalog_rows()
    pricing = []
    for m in rows:
        pricing.append({
            'id': m['id'],
            'currency': m.get('currency') or 'IRT',
            'inputPerMillion': float(m.get('input_per_million') or 0),
            'outputPerMillion': float(m.get('output_per_million') or 0),
            'cachedInputPerMillion': float(m['cached_input_per_million']) if m.get('cached_input_per_million') is not None else None,
            'reasoningPerMillion': float(m['reasoning_per_million']) if m.get('reasoning_per_million') is not None else None,
            'priceVersion': m.get('price_version') or 'v1',
            'effectiveFrom': m.get('effective_from'),
        })
    if not pricing and async_session is not None:
        try:
            async with async_session() as session:
                res = await session.execute(Pricing.__table__.select())
                for r in res.fetchall():
                    d = dict(r._mapping)
                    pricing.append({
                        'id': d['model'],
                        'currency': d.get('currency') or 'IRT',
                        'inputPerMillion': d.get('input_per_million') or 0,
                        'outputPerMillion': d.get('output_per_million') or 0,
                        'cachedInputPerMillion': None,
                        'reasoningPerMillion': None,
                        'priceVersion': 'legacy',
                        'effectiveFrom': d.get('updated_at'),
                    })
        except Exception:
            pass
    return JSONResponse(jsonable_encoder({
        'data': pricing,
        'generatedAt': datetime.now(timezone.utc),
        'priceVersion': pricing[0]['priceVersion'] if pricing else 'v1',
    }))


async def _check_quota_pre(uid: int) -> JSONResponse | None:
    """Pre-flight quota and balance check before calling LiteLLM.

    Returns a JSONResponse with status 429 if the user has exceeded their
    daily token quota or has insufficient wallet balance, or *None* if the
    request is allowed to proceed.
    """
    if async_session is None:
        return None  # can't check - allow through (degraded mode)
    try:
        async with async_session() as session:
            # -- daily token quota --
            res = await session.execute(
                Quota.__table__.select().where(Quota.user_id == uid)
            )
            quota = res.fetchone()
            if quota:
                limit = quota.daily_limit
                used = quota.used_today
                reset_at = quota.reset_at
                # Auto-reset if the reset window has passed
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if reset_at and now >= reset_at:
                    await session.execute(
                        Quota.__table__.update().where(Quota.user_id == uid),
                        {'used_today': 0, 'updated_at': now},
                    )
                    await session.commit()
                    used = 0
                if limit > 0 and used >= limit:
                    return JSONResponse(
                        {
                            'error': {
                                'message': 'daily token quota exceeded',
                                'type': 'quota_exceeded',
                                'code': 'daily_limit',
                            }
                        },
                        status_code=429,
                    )

            # -- wallet balance --
            res = await session.execute(
                sqlalchemy.text(
                    'SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'
                ),
                {'uid': uid},
            )
            row = res.fetchone()
            balance = row.balance if row else 0
            if balance <= 0:
                return JSONResponse(
                    {
                        'error': {
                            'message': 'insufficient wallet balance',
                            'type': 'quota_exceeded',
                            'code': 'balance',
                        }
                    },
                    status_code=429,
                )
    except Exception:
        # If the check itself fails, allow the request through (fail-open)
        pass
    return None


@app.post('/v1/chat/completions')
async def chat(request: Request, payload: dict[str, Any]) -> Response:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)

    # P0-2: Quota pre-check — reject before calling LiteLLM if user has
    # exceeded their daily token limit or has zero wallet balance.
    quota_err = await _check_quota_pre(uid)
    if quota_err is not None:
        return quota_err

    # Memory injection: prepend user memories as system context
    memories = await _get_user_memories(uid)
    if memories:
        memory_block = '\n'.join(f'- {m}' for m in memories)
        memory_msg = {'role': 'system', 'content': f'[User Memories]\n{memory_block}'}
        messages = payload.get('messages', [])
        # Insert after any existing system message, otherwise prepend
        insert_idx = 0
        for i, msg in enumerate(messages):
            if isinstance(msg, dict) and msg.get('role') == 'system':
                insert_idx = i + 1
                break
        messages.insert(insert_idx, memory_msg)
        payload['messages'] = messages

    # Web search injection: if client requests web_search, search DuckDuckGo
    # for the last user message and inject results as system context.
    if payload.pop('web_search', False):
        _msgs = payload.get('messages', [])
        _query = ''
        for _m in reversed(_msgs):
            if isinstance(_m, dict) and _m.get('role') == 'user':
                _query = _m.get('content', '')
                break
        if _query:
            _results = await _web_search(_query)
            if _results:
                _search_msg = {'role': 'system', 'content': f'[Web Search Results for: {_query[:100]}]\n{_results}'}
                _idx = 0
                for _i, _m in enumerate(_msgs):
                    if isinstance(_m, dict) and _m.get('role') == 'system':
                        _idx = _i + 1
                _msgs.insert(_idx, _search_msg)
                payload['messages'] = _msgs

    stream = payload.get('stream', False)
    if stream:
        return await _chat_stream(payload, request)
    try:
        r = await _http.post(f"{LITELLM_HOST}/v1/chat/completions", json=payload, headers={'Accept': 'application/json'})
        if r.status_code == 200:
            await _track_usage(request, payload, r.json())
            return Response(content=r.content, status_code=200, media_type='application/json')
        return Response(content=r.content, status_code=r.status_code, media_type='application/json')
    except Exception as e:
        return JSONResponse({'error': {'message': f'upstream unavailable: {e}', 'type': 'gateway_error'}}, status_code=502)


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB hard cap

async def _extract_file_text(upload: UploadFile) -> tuple[str, str]:
    """Return (text, error). Supports txt/md/csv/json/pdf.
    Returns '' on unsupported so callers can 400 with a clear reason."""
    name = (upload.filename or '').lower()
    # Size guard: read in chunks, abort at MAX_FILE_SIZE
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            return '', f'file too large (max {MAX_FILE_SIZE // (1024*1024)} MB)'
        chunks.append(chunk)
    data = b''.join(chunks)
    if name.endswith(('.txt', '.md', '.csv', '.json', '.log', '.text')):
        try:
            return data.decode('utf-8', errors='replace'), ''
        except Exception as e:  # noqa: BLE001
            return '', f'read error: {e}'
    if name.endswith('.pdf'):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if len(reader.pages) > 100:
                return '', 'PDF too many pages (max 100)'
            text = '\n'.join((p.extract_text() or '') for p in reader.pages[:100])
            return text[:200000], ''  # cap at ~200KB of text
        except Exception as e:  # noqa: BLE001
            return '', f'pdf extract error: {e}'
    return '', f'unsupported file type: {name or "unknown"}'


async def _web_search(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo via httpx (respects system proxy). Returns formatted results."""
    try:
        import re as _re
        from urllib.parse import unquote
        r = await _http.post(
            'https://html.duckduckgo.com/html/',
            data={'q': query, 'b': ''},
            headers={'User-Agent': 'Mozilla/5.0 (compatible; Multiai/1.0)'},
            timeout=12, follow_redirects=True,
        )
        if r.status_code != 200:
            return ''
        html = r.text
        links = _re.findall(r'class="result__a"\s+href="([^"]+)"[^>]*>(.+?)</a>', html)
        snippets = _re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, _re.DOTALL)
        if not links:
            return ''
        lines = []
        for i, (href, title) in enumerate(links[:max_results]):
            title = _re.sub(r'<[^>]+>', '', title).strip()
            snippet = _re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ''
            actual_url = href
            if 'uddg=' in href:
                m = _re.search(r'uddg=([^&]+)', href)
                if m:
                    actual_url = unquote(m.group(1))
            lines.append(f'• {title}\n  {snippet}\n  {actual_url}')
        return '\n'.join(lines)
    except Exception:
        return ''


@app.post('/v1/chat/with-file')
async def chat_with_file(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form(''),
    messages: str = Form('[]'),
    stream: bool = Form(False),
):
    """Chat with an attached file (txt/md/csv/json/pdf).

    Extracts text client-side-free on the server, appends it as a user
    message, then forwards to LiteLLM exactly like /v1/chat/completions.
    Mirrors chatone's 'upload & analyze any file' enterprise feature.
    """
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    quota_err = await _check_quota_pre(uid)
    if quota_err is not None:
        return quota_err
    # Parse supplied messages (JSON string from multipart form)
    try:
        msgs = json.loads(messages) if messages else []
    except Exception:  # noqa: BLE001
        msgs = []
    if not isinstance(msgs, list):
        msgs = []
    # Extract attached file text
    text, err = await _extract_file_text(file)
    if err:
        return JSONResponse({'error': {'message': err, 'type': 'file_error'}}, status_code=400)
    if text.strip():
        file_block = f'[Attached file: {file.filename}]\n\n{text[:50000]}'
        msgs.append({'role': 'user', 'content': file_block})
    # Build payload
    selected_model = model or 'mimo-v2.5'
    payload = {'model': selected_model, 'messages': msgs, 'stream': stream}
    # Memory injection (same path as regular chat)
    memories = await _get_user_memories(uid)
    if memories:
        memory_block = '\n'.join(f'- {m}' for m in memories)
        memory_msg = {'role': 'system', 'content': f'[User Memories]\n{memory_block}'}
        insert_idx = 0
        for i, msg in enumerate(msgs):
            if isinstance(msg, dict) and msg.get('role') == 'system':
                insert_idx = i + 1
                break
        msgs.insert(insert_idx, memory_msg)
        payload['messages'] = msgs
    if stream:
        return await _chat_stream(payload, request)
    try:
        r = await _http.post(
            f'{LITELLM_HOST}/v1/chat/completions', json=payload,
            headers={'Accept': 'application/json'},
        )
        if r.status_code == 200:
            await _track_usage(request, payload, r.json())
            return Response(content=r.content, status_code=200, media_type='application/json')
        return Response(content=r.content, status_code=r.status_code, media_type='application/json')
    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            {'error': {'message': f'upstream unavailable: {e}', 'type': 'gateway_error'}},
            status_code=502,
        )

async def _chat_stream(payload: dict[str, Any], request: Request):
    """Stream chat completion via SSE, collecting usage for billing."""
    uid = await _get_user_id(request)

    # Memory injection for streaming path (idempotent: skip if already injected)
    if uid and not any(
        isinstance(m, dict) and m.get('content', '').startswith('[User Memories]')
        for m in payload.get('messages', [])
    ):
        memories = await _get_user_memories(uid)
        if memories:
            memory_block = '\n'.join(f'- {m}' for m in memories)
            memory_msg = {'role': 'system', 'content': f'[User Memories]\n{memory_block}'}
            messages = payload.get('messages', [])
            insert_idx = 0
            for i, msg in enumerate(messages):
                if isinstance(msg, dict) and msg.get('role') == 'system':
                    insert_idx = i + 1
                    break
            messages.insert(insert_idx, memory_msg)
            payload['messages'] = messages

    async def event_stream():
        usage_data = None
        try:
            payload['stream'] = True
            # Ask LiteLLM to include usage in the final SSE chunk
            payload.setdefault('stream_options', {})
            if isinstance(payload['stream_options'], dict):
                payload['stream_options']['include_usage'] = True
            async with _http.stream('POST', f"{LITELLM_HOST}/v1/chat/completions", json=payload, headers={'Accept': 'text/event-stream'}) as r:
                async for line in r.aiter_lines():
                        if line:
                            # Parse SSE data lines to capture usage from the final chunk
                            stripped = line.strip()
                            if stripped.startswith('data:'):
                                data_str = stripped[5:].strip()
                                if data_str == '[DONE]':
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    # The final chunk may carry a "usage" object
                                    if isinstance(chunk.get('usage'), dict) and chunk['usage']:
                                        usage_data = chunk['usage']
                                except (json.JSONDecodeError, ValueError):
                                    pass
                            yield f"{line}\n\n"
        except Exception as e:
            yield f'data: {{"error": "upstream unavailable: {e}"}}\n\n'
        finally:
            # Bill the user after the stream completes
            if uid and usage_data and async_session is not None:
                try:
                    await _bill_stream_usage(uid, payload, usage_data)
                except Exception:
                    pass

    return StreamingResponse(event_stream(), media_type='text/event-stream')

async def _track_usage(request: Request, payload: dict[str, Any], response_data: dict[str, Any]):
    """Record token usage"""
    uid = await _get_user_id(request)
    if not uid or async_session is None:
        return
    usage = response_data.get('usage', {})
    total_tokens = usage.get('total_tokens', 0)
    if total_tokens <= 0:
        return
    try:
        async with async_session() as session:
            # Update quota
            res = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
            quota = res.fetchone()
            if quota:
                await session.execute(
                    Quota.__table__.update().where(Quota.user_id == uid),
                    {'used_today': quota.used_today + total_tokens, 'updated_at': datetime.now(timezone.utc).replace(tzinfo=None)}
                )
            # Deduct from wallet using model_catalog prices
            model = payload.get('model', '')
            input_tokens = int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0)
            output_tokens = int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)

            # Look up price from model_catalog by provider_model_id
            price_row = None
            try:
                price_res = await session.execute(
                    sqlalchemy.text(
                        'SELECT input_per_million, output_per_million FROM model_catalog '
                        'WHERE provider_model_id = :mid AND availability = :avail LIMIT 1'
                    ),
                    {'mid': model, 'avail': 'available'}
                )
                price_row = price_res.fetchone()
            except Exception:
                pass

            if price_row:
                inp_rate = float(price_row.input_per_million or 0)
                out_rate = float(price_row.output_per_million or 0)
                cost = max(1, int((input_tokens * inp_rate + output_tokens * out_rate + 500_000) // 1_000_000))
            else:
                # Fallback: 1 toman per 1000 tokens (old flat rate)
                cost = max(1, total_tokens // 1000)
            res = await session.execute(
                sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
                {'uid': uid}
            )
            row = res.fetchone()
            current = row.balance if row else 0
            if current >= cost:
                entry = Ledger(user_id=uid, amount=-cost, balance_after=current - cost, reason=f'مصرف {model}')
                session.add(entry)

            # Metering: persist immutable usage event in the SAME transaction
            # as the ledger deduction (before commit), so it's not lost.
            try:
                from services.billing import SqlBillingRepo
                from services.metering import record_usage
                from services.money import Money

                _repo = SqlBillingRepo(session)
                await record_usage(
                    _repo,
                    request_id=secrets.token_hex(8),
                    user_id=uid,
                    model=model,
                    charge=Money(cost),
                    upstream_status='success',
                    input_tokens=int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0),
                    output_tokens=int(usage.get('completion_tokens') or usage.get('output_tokens') or 0),
                )
            except Exception:
                pass

            await session.commit()
    except Exception:
        pass

async def _bill_stream_usage(uid: int, payload: dict[str, Any], usage: dict[str, Any]):
    """Bill the user after a streaming chat completes.

    Uses the same pricing logic as ``_track_usage`` but takes the uid and
    usage dict directly (no request/response objects needed).
    """
    total_tokens = usage.get('total_tokens', 0)
    if total_tokens <= 0:
        return
    async with async_session() as session:
        # Update quota
        res = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
        quota = res.fetchone()
        if quota:
            await session.execute(
                Quota.__table__.update().where(Quota.user_id == uid),
                {'used_today': quota.used_today + total_tokens, 'updated_at': datetime.now(timezone.utc).replace(tzinfo=None)},
            )

        model = payload.get('model', '')
        input_tokens = int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0)
        output_tokens = int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)

        # Look up price from model_catalog
        price_row = None
        try:
            price_res = await session.execute(
                sqlalchemy.text(
                    'SELECT input_per_million, output_per_million FROM model_catalog '
                    'WHERE provider_model_id = :mid AND availability = :avail LIMIT 1'
                ),
                {'mid': model, 'avail': 'available'},
            )
            price_row = price_res.fetchone()
        except Exception:
            pass

        if price_row:
            inp_rate = float(price_row.input_per_million or 0)
            out_rate = float(price_row.output_per_million or 0)
            cost = max(1, int((input_tokens * inp_rate + output_tokens * out_rate + 500_000) // 1_000_000))
        else:
            cost = max(1, total_tokens // 1000)

        res = await session.execute(
            sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
            {'uid': uid},
        )
        row = res.fetchone()
        current = row.balance if row else 0
        if current >= cost:
            entry = Ledger(user_id=uid, amount=-cost, balance_after=current - cost, reason=f'مصرف {model}')
            session.add(entry)

        # Metering: persist immutable usage event in the same transaction
        try:
            _repo = SqlBillingRepo(session)
            from services.metering import record_usage
            from services.money import Money
            await record_usage(
                _repo,
                request_id=secrets.token_hex(8),
                user_id=uid,
                model=model,
                charge=Money(cost),
                upstream_status='success',
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except Exception:
            pass

        await session.commit()

@app.get('/me/usage')
async def me_usage(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        q = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
        row = q.fetchone()
        if not row:
            return JSONResponse({'user_id': uid, 'daily_limit': 0, 'used_today': 0, 'reset_at': None})
        return JSONResponse({'user_id': uid, 'daily_limit': row.daily_limit, 'used_today': row.used_today, 'reset_at': row.reset_at.isoformat() if row.reset_at else None})

@app.get('/admin/pricing')
async def list_pricing(request: Request) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            Pricing.__table__.select().order_by(Pricing.model, Pricing.price_version.desc())
        )
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


async def get_active_price(session, model_id: str) -> "Pricing | None":
    """Return the currently-active pricing version for *model_id*.

    Active == the version with the greatest ``effective_from`` whose
    ``effective_to`` IS NULL.  Because prices are immutable (a new version is
    always INSERTed, never UPDATEed), the active price is simply the latest
    version for the model.
    """
    res = await session.execute(
        select(Pricing)
        .where(Pricing.model == model_id, Pricing.effective_to.is_(None))
        .order_by(Pricing.effective_from.desc(), Pricing.price_version.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


@app.post('/admin/pricing')
async def set_pricing(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Insert a NEW versioned price row.  Historical rows are never updated."""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    model = payload.get('model')
    if not model:
        return JSONResponse({'detail': 'model required'}, status_code=400)
    try:
        input_pm = int(payload.get('input_per_million', 0))
        output_pm = int(payload.get('output_per_million', 0))
    except (TypeError, ValueError):
        return JSONResponse({'detail': 'prices must be integers'}, status_code=400)
    currency = payload.get('currency', 'IRT')
    provider = payload.get('provider', 'unknown')
    source = payload.get('source')
    async with async_session() as session:
        # Determine the next version number for this model (no UPDATE of history).
        cur = await session.execute(
            select(func.coalesce(func.max(Pricing.price_version), 0)).where(Pricing.model == model)
        )
        next_version = (cur.scalar_one() or 0) + 1
        row = Pricing(
            model=model,
            provider=provider,
            input_per_million=input_pm,
            output_per_million=output_pm,
            currency=currency,
            source=source,
            price_version=next_version,
            effective_from=datetime.now(timezone.utc).replace(tzinfo=None),
            effective_to=None,
        )
        session.add(row)
        await session.commit()
    await _write_audit_log('admin.pricing.set', target_type='pricing', target_id=model, details={'price_version': next_version})
    return JSONResponse({'status': 'inserted', 'model': model, 'price_version': next_version})

# ===== Features =====
@app.get('/admin/features')
async def list_features(request: Request) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Feature.__table__.select().order_by(Feature.order_idx))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))

@app.post('/admin/features')
async def upsert_feature(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    fid = payload.get('id')
    async with async_session() as session:
        if fid:
            row = await session.get(Feature, fid)
            if not row:
                return JSONResponse({'detail': 'not found'}, status_code=404)
        else:
            row = Feature()
            session.add(row)
        row.title = payload.get('title', row.title)
        row.description = payload.get('description', row.description)
        row.icon = payload.get('icon', row.icon)
        row.active = payload.get('active', row.active)
        row.order_idx = payload.get('order_idx', row.order_idx)
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
    await _write_audit_log('admin.feature.upsert', target_type='feature', target_id=row.id)
    return JSONResponse({'status': 'ok', 'id': row.id})

@app.delete('/admin/features/{fid}')
async def delete_feature(request: Request, fid: int) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    async with async_session() as session:
        row = await session.get(Feature, fid)
        if row:
            await session.delete(row)
            await session.commit()
    await _write_audit_log('admin.feature.delete', target_type='feature', target_id=fid)
    return JSONResponse({'status': 'deleted'})

# ===== Discounts =====
@app.get('/admin/discounts')
async def list_discounts(request: Request) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Discount.__table__.select())
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))

@app.post('/admin/discounts')
async def upsert_discount(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    did = payload.get('id')
    code = payload.get('code')
    if not code:
        return JSONResponse({'detail': 'code required'}, status_code=400)
    async with async_session() as session:
        if did:
            row = await session.get(Discount, did)
            if not row:
                return JSONResponse({'detail': 'not found'}, status_code=404)
        else:
            row = Discount()
            session.add(row)
        row.code = code
        row.percent = payload.get('percent', row.percent)
        row.active = payload.get('active', row.active)
        row.expires_at = payload.get('expires_at')
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
    await _write_audit_log('admin.discount.upsert', target_type='discount', target_id=row.id)
    return JSONResponse({'status': 'ok', 'id': row.id})

@app.delete('/admin/discounts/{did}')
async def delete_discount(request: Request, did: int) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    async with async_session() as session:
        row = await session.get(Discount, did)
        if row:
            await session.delete(row)
            await session.commit()
    await _write_audit_log('admin.discount.delete', target_type='discount', target_id=did)
    return JSONResponse({'status': 'deleted'})

# ===== About =====
@app.get('/about')
async def get_about() -> JSONResponse:
    if async_session is None:
        return JSONResponse({'title': 'درباره ما', 'body': ''})
    async with async_session() as session:
        res = await session.execute(AboutContent.__table__.select())
        row = res.fetchone()
        if not row:
            return JSONResponse({'title': 'درباره ما', 'body': ''})
        return JSONResponse(jsonable_encoder(dict(row._mapping)))

@app.post('/admin/about')
async def set_about(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(AboutContent.__table__.select())
        row = res.fetchone()
        if not row:
            row = AboutContent()
            session.add(row)
        else:
            row = await session.get(AboutContent, row.id)
        row.title = payload.get('title', row.title)
        row.body = payload.get('body', row.body)
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
    await _write_audit_log('admin.about.set')
    return JSONResponse({'status': 'ok'})

# ===== Proxy Config =====
@app.get('/admin/proxy')
async def get_proxy(request: Request) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'proxy_url': '', 'proxy_type': 'socks5', 'active': False})
    async with async_session() as session:
        res = await session.execute(ProxyConfig.__table__.select())
        row = res.fetchone()
        if not row:
            return JSONResponse({'proxy_url': '', 'proxy_type': 'socks5', 'active': False})
        return JSONResponse(jsonable_encoder(dict(row._mapping)))

@app.post('/admin/proxy')
async def set_proxy(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(ProxyConfig.__table__.select())
        row = res.fetchone()
        if not row:
            row = ProxyConfig()
            session.add(row)
        else:
            row = await session.get(ProxyConfig, row.id)
        row.proxy_url = payload.get('proxy_url', row.proxy_url)
        row.proxy_type = payload.get('proxy_type', row.proxy_type)
        row.active = payload.get('active', row.active)
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()
    await _write_audit_log('admin.proxy.set')
    return JSONResponse({'status': 'ok', 'proxy_url': row.proxy_url})

# ===== Public content (frontend) =====
@app.get('/content/features')
async def public_features() -> JSONResponse:
    if async_session is None:
        return JSONResponse([])
    async with async_session() as session:
        res = await session.execute(Feature.__table__.select().where(Feature.active == True).order_by(Feature.order_idx))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))

@app.get('/content/discounts')
async def public_discounts() -> JSONResponse:
    if async_session is None:
        return JSONResponse([])
    async with async_session() as session:
        res = await session.execute(Discount.__table__.select().where(Discount.active == True))
        rows = [{'code': r.code, 'percent': r.percent} for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))

# ═══════════════════════════════════════
# Auth
# ═══════════════════════════════════════

SESSION_TTL = 86400 * 7

# ── Session cookie configuration ──────────────────────────
SESSION_COOKIE_NAME = 'session'
SESSION_COOKIE_SECURE = (
    os.getenv('ENV', 'production').lower() not in ('development', 'dev')
    and not os.getenv('DEBUG')
)
ADMIN_COOKIE_NAME = 'admin_session'
ADMIN_CSRF_COOKIE_NAME = 'admin_csrf'
ADMIN_SESSION_TTL = 3600 * 8
API_KEY_PEPPER=os.getenv('API_KEY_PEPPER', '').encode()
if not API_KEY_PEPPER:
    raise RuntimeError('API_KEY_PEPPER must be set in .env; refusing to start with insecure default')


def _session_payload(user_id: int) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        'user_id': user_id,
        'created_at': now.isoformat(),
        'expires_at': (now + timedelta(seconds=SESSION_TTL)).isoformat(),
    }


def _create_session(user_id: int) -> str:
    """Create a server-side session and return its opaque token."""
    token = _gen_token()
    rds.setex(f'session:{token}', SESSION_TTL, json.dumps(_session_payload(user_id)))
    rds.sadd(f'sessions:{user_id}', token)
    rds.expire(f'sessions:{user_id}', SESSION_TTL)
    return token


def _get_session(token: str | None) -> dict | None:
    if not token:
        return None
    raw = rds.get(f'session:{token}')
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        data = None
    if not isinstance(data, dict):
        # Legacy plain user-id sessions (e.g. telegram bridge)
        try:
            return {'user_id': int(raw), 'created_at': None, 'expires_at': None}
        except (TypeError, ValueError):
            return None
    # Enforce server-side expiry
    exp = data.get('expires_at')
    if exp:
        try:
            if datetime.fromisoformat(exp) < datetime.now(timezone.utc).replace(tzinfo=None):
                rds.delete(f'session:{token}')
                return None
        except ValueError:
            pass
    rds.expire(f'session:{token}', SESSION_TTL)
    return data


def _get_session_user_id(token: str | None) -> int | None:
    data = _get_session(token)
    return int(data['user_id']) if data else None


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME, token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite='lax',
        max_age=SESSION_TTL,
        path='/',
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path='/')


def _rotate_session(request: Request, response: Response, user_id: int) -> str:
    """Invalidate the current session and issue a fresh one (privilege change)."""
    old = request.cookies.get(SESSION_COOKIE_NAME) or \
        request.headers.get('Authorization', '').removeprefix('Bearer ')
    if old:
        rds.delete(f'session:{old}')
        rds.srem(f'sessions:{user_id}', old)
    new_token = _create_session(user_id)
    _set_session_cookie(response, new_token)
    return new_token


def _hash_api_key(raw_key: str) -> str:
    """Hash an API key at rest using sha256 with a server-side pepper (salt)."""
    return hashlib.sha256(API_KEY_PEPPER + raw_key.encode()).hexdigest()


async def _write_audit_log(action: str, target_type: str | None = None,
                            target_id: Any = None, details: dict | None = None) -> None:
    """Best-effort, fire-and-forget audit record of a privileged/admin action.

    Audit logging must never break the primary action, so all failures are
    swallowed. Uses a fresh session so the audit row is committed independently
    of the caller's transaction.
    """
    if async_session is None:
        return
    try:
        async with async_session() as s:
            s.add(AuditLog(
                action=action,
                target_type=target_type,
                target_id=str(target_id) if target_id is not None else None,
                details=details,
            ))
            await s.commit()
    except Exception:
        # Audit failures must not break the action that triggered them.
        pass


# ── Admin session (server-side, isolated from user sessions) ──
def _create_admin_session() -> tuple[str, str]:
    sid = _gen_token()
    csrf = secrets.token_urlsafe(32)
    payload = {
        'created_at': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        'csrf': csrf,
    }
    rds.setex(f'admin_session:{sid}', ADMIN_SESSION_TTL, json.dumps(payload))
    return sid, csrf


def _get_admin_session(sid: str | None) -> dict | None:
    if not sid:
        return None
    raw = rds.get(f'admin_session:{sid}')
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f'{salt}${dk.hex()}'

def _verify_password(password: str, stored: str) -> bool:
    salt, h = stored.split('$')
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return h == dk.hex()

def _gen_token() -> str:
    return secrets.token_urlsafe(32)

async def _get_user_id(request: Request) -> int | None:
    # Primary: server-side session cookie
    token = request.cookies.get(SESSION_COOKIE_NAME)
    # Fallback: Authorization header (legacy / API access / websocket upgrade)
    if not token:
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if not token:
        return None
    uid = _get_session_user_id(token)
    if uid:
        return uid
    # API key authentication
    if token.startswith('sk-'):
        key_hash = _hash_api_key(token)
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(
                    ApiKey.__table__.select().where(
                        ApiKey.key_hash == key_hash,
                        ApiKey.active == True,
                        ApiKey.revoked_at == None,
                        (ApiKey.expires_at == None) | (ApiKey.expires_at > func.now()),
                    )
                )
                key = res.fetchone()
                if key:
                    await session.execute(
                        ApiKey.__table__.update().where(ApiKey.id == key.id),
                        {'last_used': datetime.now(timezone.utc).replace(tzinfo=None)}
                    )
                    await session.commit()
                    return key.user_id
    return None

class AuthSignup(BaseModel):
    email: str
    password: str
    ref: str | None = None

class AuthLogin(BaseModel):
    email: str
    password: str

@app.post('/auth/signup')
async def signup(payload: AuthSignup) -> JSONResponse:
    from security import validate_email, validate_password
    valid, err = validate_email(payload.email)
    if not valid:
        return JSONResponse({'detail': err}, status_code=400)
    valid, err = validate_password(payload.password)
    if not valid:
        return JSONResponse({'detail': err}, status_code=400)

    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        existing = await session.execute(User.__table__.select().where(User.email == payload.email))
        if existing.fetchone():
            return JSONResponse({'detail': 'email already registered'}, status_code=409)
        user = User(email=payload.email, password_hash=_hash_password(payload.password), referral_code=secrets.token_hex(4))
        session.add(user)
        await session.commit()
        await session.refresh(user)
        # Handle referral
        ref_code = payload.ref if hasattr(payload, 'ref') else None
        if ref_code and async_session is not None:
            async with async_session() as s2:
                ref_res = await s2.execute(User.__table__.select().where(User.referral_code == ref_code))
                referrer = ref_res.fetchone()
                if referrer and referrer.id != user.id:
                    await s2.execute(
                        User.__table__.update().where(User.id == user.id),
                        {'referred_by': referrer.id}
                    )
                    # Give referrer bonus
                    bonus = Ledger(user_id=referrer.id, amount=5000, balance_after=0,
                                   reason=f'پاداش دعوت کاربر {user.email}')
                    # Update balance_after
                    bal_res = await s2.execute(
                        sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
                        {'uid': referrer.id}
                    )
                    bal_row = bal_res.fetchone()
                    bonus.balance_after = (bal_row.balance if bal_row else 0) + 5000
                    s2.add(bonus)
                    await s2.commit()
        quota = Quota(user_id=user.id, daily_limit=200000, used_today=0, reset_at=(datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None))
        session.add(quota)
        await session.commit()
        token = _create_session(user.id)
        response = JSONResponse({'token': token, 'user': {'id': user.id, 'email': user.email}})
        _set_session_cookie(response, token)
        return response

@app.post('/auth/login')
async def login(payload: AuthLogin) -> JSONResponse:
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.email == payload.email))
        user = res.fetchone()
        if not user or not user.password_hash or not _verify_password(payload.password, user.password_hash):
            return JSONResponse({'detail': 'invalid email or password'}, status_code=401)
        token = _create_session(user.id)
        response = JSONResponse({'token': token, 'user': {'id': user.id, 'email': user.email}})
        _set_session_cookie(response, token)
        return response

@app.get('/auth/me')
async def me(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()
        if not user:
            return JSONResponse({'detail': 'user not found'}, status_code=404)
        return JSONResponse(jsonable_encoder({
            'id': user.id, 'email': user.email, 'created_at': user.created_at,
            'referral_code': user.referral_code,
        }))

# ── Referral ───────────────────────────────────────────────

@app.get('/referral/stats')
async def referral_stats(request: Request) -> JSONResponse:
    """Get user's referral stats"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        # Get referral code
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()

        # Count referrals
        count_res = await session.execute(
            sqlalchemy.text('SELECT COUNT(*) as c FROM users WHERE referred_by = :uid'),
            {'uid': uid}
        )
        count = count_res.fetchone().c

        # Total bonus earned
        bonus_res = await session.execute(
            sqlalchemy.text("SELECT COALESCE(SUM(amount), 0) as total FROM ledger WHERE user_id = :uid AND reason LIKE 'پاداش%'"),
            {'uid': uid}
        )
        bonus = bonus_res.fetchone().total

    return JSONResponse({
        'referral_code': user.referral_code if user else None,
        'referral_count': count,
        'total_bonus': bonus,
        'referral_url': f'{BASE_URL}/signup?ref={user.referral_code}' if user and user.referral_code else None,
    })

@app.post('/auth/logout')
async def logout(request: Request) -> JSONResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME) or \
        request.headers.get('Authorization', '').removeprefix('Bearer ')
    if token:
        uid = _get_session_user_id(token)
        rds.delete(f'session:{token}')
        if uid:
            rds.srem(f'sessions:{uid}', token)
    response = JSONResponse({'status': 'ok'})
    _clear_session_cookie(response)
    return response


@app.post('/auth/logout-all')
async def logout_all(request: Request) -> JSONResponse:
    """Revoke every active session for the authenticated user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    tokens = list(rds.smembers(f'sessions:{uid}') or [])
    for tok in tokens:
        rds.delete(f'session:{tok}')
    rds.delete(f'sessions:{uid}')
    response = JSONResponse({'status': 'ok', 'revoked_sessions': len(tokens)})
    _clear_session_cookie(response)
    return response

# ── Profile management ─────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

@app.post('/auth/change-password')
async def change_password(request: Request, payload: ChangePasswordRequest) -> JSONResponse:
    """Change user password"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    from security import validate_password
    valid, err = validate_password(payload.new_password)
    if not valid:
        return JSONResponse({'detail': err}, status_code=400)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()
        if not user or not _verify_password(payload.current_password, user.password_hash):
            return JSONResponse({'detail': 'current password is incorrect'}, status_code=401)

        new_hash = _hash_password(payload.new_password)
        await session.execute(
            User.__table__.update().where(User.id == uid),
            {'password_hash': new_hash}
        )
        await session.commit()

    response = JSONResponse({'status': 'ok'})
    _rotate_session(request, response, uid)
    return response


@app.put('/auth/profile')
async def update_profile(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Update user profile fields"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    allowed = {'phone'}
    update_data = {k: v for k, v in payload.items() if k in allowed and v is not None}
    if not update_data:
        return JSONResponse({'detail': 'no valid fields to update'}, status_code=400)

    async with async_session() as session:
        await session.execute(
            User.__table__.update().where(User.id == uid),
            update_data
        )
        await session.commit()

    return JSONResponse({'status': 'ok', 'updated': list(update_data.keys())})

# ── Password reset ─────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@app.post('/auth/forgot-password')
async def forgot_password(payload: ForgotPasswordRequest) -> JSONResponse:
    """Send password reset token (stored in Redis for 15 min)"""
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.email == payload.email))
        user = res.fetchone()
        if not user:
            # Don't reveal if email exists
            return JSONResponse({'status': 'ok', 'message': 'if email exists, reset link sent'})

        reset_token = secrets.token_urlsafe(32)
        rds.setex(f'reset:{reset_token}', 900, str(user.id))  # 15 min TTL

        # In production, send email here
        # Token logged to DB/redis only — never to stdout (security)

        return JSONResponse({
            'status': 'ok',
            'message': 'reset link sent to your email',
            'token': reset_token if os.getenv('DEBUG') else None,  # Only show in debug
        })


@app.post('/auth/reset-password')
async def reset_password(payload: ResetPasswordRequest) -> JSONResponse:
    """Reset password using token"""
    from security import validate_password
    valid, err = validate_password(payload.new_password)
    if not valid:
        return JSONResponse({'detail': err}, status_code=400)

    uid = rds.get(f'reset:{payload.token}')
    if not uid:
        return JSONResponse({'detail': 'invalid or expired reset token'}, status_code=400)

    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    new_hash = _hash_password(payload.new_password)
    async with async_session() as session:
        await session.execute(
            User.__table__.update().where(User.id == int(uid)),
            {'password_hash': new_hash}
        )
        await session.commit()

    rds.delete(f'reset:{payload.token}')
    return JSONResponse({'status': 'ok', 'message': 'password reset successfully'})

# ── Telegram account linking ──────────────────────────────

class TelegramLink(BaseModel):
    telegram_id: int

@app.post('/auth/telegram-link')
async def telegram_link(request: Request, payload: TelegramLink) -> JSONResponse:
    """Link a Telegram account to existing user"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        await session.execute(
            User.__table__.update().where(User.id == uid),
            {'telegram_id': payload.telegram_id}
        )
        await session.commit()
    return JSONResponse({'status': 'ok', 'telegram_id': payload.telegram_id})

@app.get('/auth/telegram-link')
async def get_telegram_token(request: Request) -> JSONResponse:
    """Get auth token for a linked Telegram user (used by bot)"""
    tg_id = request.query_params.get('tg_id')
    if not tg_id:
        return JSONResponse({'detail': 'tg_id required'}, status_code=400)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    try:
        tg_id_int = int(tg_id)
    except ValueError:
        return JSONResponse({'detail': 'invalid tg_id'}, status_code=400)

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.telegram_id == tg_id_int))
        user = res.fetchone()
        if not user:
            return JSONResponse({'detail': 'not linked'}, status_code=404)
        token = _gen_token()
        rds.setex(f'session:{token}', SESSION_TTL, str(user.id))
        return JSONResponse({'token': token, 'user': {'id': user.id, 'email': user.email}})

# ═══════════════════════════════════════
# Conversations
# ═══════════════════════════════════════

class ConvCreate(BaseModel):
    title: str = 'گفتگوی جدید'
    model: str = ''
    messages: list[dict[str, Any]] = []

class ConvUpdate(BaseModel):
    title: str | None = None
    messages: list[dict[str, Any]] | None = None

@app.get('/conversations')
async def list_conversations(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            Conversation.__table__.select()
            .where(Conversation.user_id == uid)
            .order_by(Conversation.updated_at.desc())
        )
        rows = [{'id': r.id, 'title': r.title, 'model': r.model, 'created_at': r.created_at, 'updated_at': r.updated_at} for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))

@app.post('/conversations')
async def create_conversation(request: Request, payload: ConvCreate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        conv = Conversation(user_id=uid, title=payload.title, model=payload.model, messages=payload.messages)
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return JSONResponse(jsonable_encoder({'id': conv.id, 'title': conv.title, 'model': conv.model, 'messages': conv.messages, 'created_at': conv.created_at}))

@app.get('/conversations/search')
async def search_conversations(request: Request, q: str = '') -> JSONResponse:
    """Search conversations by title or message content for the current user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        if q:
            res = await session.execute(
                Conversation.__table__.select()
                .where(
                    Conversation.user_id == uid,
                    Conversation.title.ilike(f'%{q}%')
                )
                .order_by(Conversation.updated_at.desc())
                .limit(50)
            )
            rows = [dict(r._mapping) for r in res.fetchall()]
            # Also search in message content (JSON column)
            res2 = await session.execute(
                Conversation.__table__.select()
                .where(Conversation.user_id == uid)
                .order_by(Conversation.updated_at.desc())
                .limit(200)
            )
            all_rows = res2.fetchall()
            seen_ids = {r.id for r in rows}
            for r in all_rows:
                if r.id in seen_ids:
                    continue
                msgs = r.messages or []
                for msg in msgs:
                    if isinstance(msg, dict) and q.lower() in (msg.get('content', '') or '').lower():
                        rows.append(dict(r._mapping))
                        seen_ids.add(r.id)
                        break
        else:
            res = await session.execute(
                Conversation.__table__.select()
                .where(Conversation.user_id == uid)
                .order_by(Conversation.updated_at.desc())
                .limit(50)
            )
            rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


# ═══════════════════════════════════════════════════════════════════
# Conversation Analytics
# ═══════════════════════════════════════════════════════════════════

@app.get('/conversations/analytics')
async def conversation_analytics(request: Request) -> JSONResponse:
    """Return conversation usage analytics for the current user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    try:
        async with async_session() as session:
            # Total conversations
            conv_count_res = await session.execute(
                sqlalchemy.text(
                    'SELECT COUNT(*) as c FROM conversations WHERE user_id = :uid'
                ),
                {'uid': uid},
            )
            total_conversations = conv_count_res.fetchone().c or 0

            # Total messages across all conversations
            msg_count_res = await session.execute(
                sqlalchemy.text(
                    "SELECT COALESCE(SUM(jsonb_array_length(CASE WHEN messages IS NOT NULL THEN messages ELSE '[]'::jsonb END)), 0) as c "
                    "FROM conversations WHERE user_id = :uid"
                ),
                {'uid': uid},
            )
            total_messages = msg_count_res.fetchone().c or 0

            # Usage stats from usage_events
            usage_res = await session.execute(
                sqlalchemy.text(
                    """SELECT
                        COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                        COALESCE(SUM(charged_amount), 0) as total_cost
                    FROM usage_events WHERE user_id = :uid"""
                ),
                {'uid': uid},
            )
            usage_row = usage_res.fetchone()
            total_tokens_used = usage_row.total_tokens if usage_row else 0
            total_cost = usage_row.total_cost if usage_row else 0

            # Models breakdown
            models_res = await session.execute(
                sqlalchemy.text(
                    """SELECT model, COUNT(*) as calls,
                        SUM(input_tokens + output_tokens) as tokens,
                        SUM(charged_amount) as cost
                    FROM usage_events WHERE user_id = :uid
                    GROUP BY model ORDER BY calls DESC"""
                ),
                {'uid': uid},
            )
            models_used = {}
            for r in models_res.fetchall():
                models_used[r.model] = {
                    'calls': r.calls,
                    'tokens': r.tokens,
                    'cost': r.cost,
                }

            # Daily usage (last 30 days)
            daily_res = await session.execute(
                sqlalchemy.text(
                    """SELECT
                        DATE(created_at) as day,
                        COUNT(*) as calls,
                        SUM(input_tokens + output_tokens) as tokens,
                        SUM(charged_amount) as cost
                    FROM usage_events
                    WHERE user_id = :uid AND created_at >= NOW() - INTERVAL '30 days'
                    GROUP BY DATE(created_at)
                    ORDER BY day DESC"""
                ),
                {'uid': uid},
            )
            daily_usage = {}
            for r in daily_res.fetchall():
                day_str = r.day.isoformat() if hasattr(r.day, 'isoformat') else str(r.day)
                daily_usage[day_str] = {
                    'calls': r.calls,
                    'tokens': r.tokens,
                    'cost': r.cost,
                }

        return JSONResponse({
            'total_conversations': total_conversations,
            'total_messages': total_messages,
            'total_tokens_used': total_tokens_used,
            'total_cost': total_cost,
            'models_used': models_used,
            'daily_usage': daily_usage,
        })
    except Exception as e:
        return JSONResponse(
            {'detail': f'analytics error: {e}'}, status_code=500
        )


@app.get('/conversations/{conv_id}')
async def get_conversation(request: Request, conv_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Conversation.__table__.select().where(Conversation.id == conv_id, Conversation.user_id == uid))
        conv = res.fetchone()
        if not conv:
            return JSONResponse({'detail': 'not found'}, status_code=404)
        return JSONResponse(jsonable_encoder({'id': conv.id, 'title': conv.title, 'model': conv.model, 'messages': conv.messages, 'created_at': conv.created_at}))

@app.put('/conversations/{conv_id}')
async def update_conversation(request: Request, conv_id: int, payload: ConvUpdate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Conversation.__table__.select().where(Conversation.id == conv_id, Conversation.user_id == uid))
        conv = res.fetchone()
        if not conv:
            return JSONResponse({'detail': 'not found'}, status_code=404)
        update_data = {}
        if payload.title is not None:
            update_data['title'] = payload.title
        if payload.messages is not None:
            update_data['messages'] = payload.messages
        if update_data:
            update_data['updated_at'] = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.execute(
                Conversation.__table__.update().where(Conversation.id == conv_id),
                update_data
            )
            await session.commit()
        return JSONResponse({'status': 'ok'})

@app.delete('/conversations/{conv_id}')
async def delete_conversation(request: Request, conv_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Conversation.__table__.select().where(Conversation.id == conv_id, Conversation.user_id == uid))
        conv = res.fetchone()
        if not conv:
            return JSONResponse({'detail': 'not found'}, status_code=404)
        await session.execute(Conversation.__table__.delete().where(Conversation.id == conv_id))
        await session.commit()
    return JSONResponse({'status': 'deleted'})

# ═══════════════════════════════════════
# Memories
# ═══════════════════════════════════════

class MemoryCreate(BaseModel):
    content: str
    category: str = 'general'
    source: str = 'manual'
    tags: list[str] = []

class MemoryUpdate(BaseModel):
    content: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    active: bool | None = None


@app.get('/memories')
async def list_memories(request: Request, category: str | None = None) -> JSONResponse:
    """List active memories for the current user, optionally filtered by category."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        stmt = UserMemory.__table__.select().where(
            UserMemory.user_id == uid,
            UserMemory.active == True,
        )
        if category:
            stmt = stmt.where(UserMemory.category == category)
        stmt = stmt.order_by(UserMemory.created_at.desc())
        res = await session.execute(stmt)
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@app.get('/memories/search')
async def search_memories(request: Request, q: str = '') -> JSONResponse:
    """Full-text search across memory content for the current user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        if q:
            res = await session.execute(
                UserMemory.__table__.select().where(
                    UserMemory.user_id == uid,
                    UserMemory.active == True,
                    UserMemory.content.ilike(f'%{q}%'),
                ).order_by(UserMemory.created_at.desc()).limit(50)
            )
        else:
            res = await session.execute(
                UserMemory.__table__.select().where(
                    UserMemory.user_id == uid,
                    UserMemory.active == True,
                ).order_by(UserMemory.created_at.desc()).limit(50)
            )
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@app.post('/memories')
async def create_memory(request: Request, payload: MemoryCreate) -> JSONResponse:
    """Create a new memory entry for the current user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        mem = UserMemory(
            user_id=uid,
            content=payload.content,
            category=payload.category,
            source=payload.source,
            tags=payload.tags,
        )
        session.add(mem)
        await session.commit()
        await session.refresh(mem)
        return JSONResponse(jsonable_encoder({
            'id': mem.id, 'content': mem.content, 'category': mem.category,
            'source': mem.source, 'tags': mem.tags, 'active': mem.active,
            'created_at': mem.created_at,
        }))


@app.put('/memories/{memory_id}')
async def update_memory(request: Request, memory_id: int, payload: MemoryUpdate) -> JSONResponse:
    """Update an existing memory entry."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            UserMemory.__table__.select().where(
                UserMemory.id == memory_id, UserMemory.user_id == uid
            )
        )
        mem = res.fetchone()
        if not mem:
            return JSONResponse({'detail': 'not found'}, status_code=404)
        update_data = {}
        if payload.content is not None:
            update_data['content'] = payload.content
        if payload.category is not None:
            update_data['category'] = payload.category
        if payload.tags is not None:
            update_data['tags'] = payload.tags
        if payload.active is not None:
            update_data['active'] = payload.active
        if update_data:
            update_data['updated_at'] = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.execute(
                UserMemory.__table__.update().where(UserMemory.id == memory_id),
                update_data,
            )
            await session.commit()
    return JSONResponse({'status': 'ok'})


@app.delete('/memories/{memory_id}')
async def delete_memory(request: Request, memory_id: int) -> JSONResponse:
    """Soft-delete a memory entry (set active=False)."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            UserMemory.__table__.select().where(
                UserMemory.id == memory_id, UserMemory.user_id == uid
            )
        )
        mem = res.fetchone()
        if not mem:
            return JSONResponse({'detail': 'not found'}, status_code=404)
        await session.execute(
            UserMemory.__table__.update().where(UserMemory.id == memory_id),
            {'active': False, 'updated_at': datetime.now(timezone.utc).replace(tzinfo=None)},
        )
        await session.commit()
    return JSONResponse({'status': 'deleted'})


async def _get_user_memories(uid: int) -> list[str]:
    """Fetch active user memory contents for injection into chat."""
    if async_session is None:
        return []
    try:
        async with async_session() as session:
            res = await session.execute(
                UserMemory.__table__.select().where(
                    UserMemory.user_id == uid,
                    UserMemory.active == True,
                ).order_by(UserMemory.created_at.desc()).limit(20)
            )
            return [r.content for r in res.fetchall()]
    except Exception:
        return []



# ═══════════════════════════════════════
# Skills Marketplace
# ═══════════════════════════════════════

class SkillTemplateCreate(BaseModel):
    title: str
    title_fa: str
    description: str = ''
    description_fa: str = ''
    category: str = 'general'
    prompt_template: str
    variables: list[dict[str, Any]] = []
    default_model: str = ''
    is_public: bool = False
    tags: list[str] = []

class SkillTemplateUpdate(BaseModel):
    title: str | None = None
    title_fa: str | None = None
    description: str | None = None
    description_fa: str | None = None
    category: str | None = None
    prompt_template: str | None = None
    variables: list[dict[str, Any]] | None = None
    default_model: str | None = None
    is_public: bool | None = None
    tags: list[str] | None = None

class SkillUseRequest(BaseModel):
    variables: dict[str, str] = {}
    model: str = ''

class SkillRatingRequest(BaseModel):
    rating: int


@app.get('/skills/my')
async def list_my_skill_templates(request: Request) -> JSONResponse:
    """List skill templates owned by the current user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            SkillTemplate.__table__.select().where(
                SkillTemplate.user_id == uid,
            ).order_by(SkillTemplate.created_at.desc())
        )
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@app.get('/skills')
async def list_skill_templates(
    request: Request,
    category: str | None = None,
    featured: bool | None = None,
    sort: str = 'popular',
    q: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> JSONResponse:
    """List public skill templates with optional filtering and sorting."""
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        stmt = SkillTemplate.__table__.select().where(SkillTemplate.is_public == True)
        if category:
            stmt = stmt.where(SkillTemplate.category == category)
        if featured is not None:
            stmt = stmt.where(SkillTemplate.is_featured == featured)
        if q:
            stmt = stmt.where(
                SkillTemplate.title.ilike(f'%{q}%') |
                SkillTemplate.title_fa.ilike(f'%{q}%') |
                SkillTemplate.description.ilike(f'%{q}%') |
                SkillTemplate.description_fa.ilike(f'%{q}%')
            )
        if sort == 'newest':
            stmt = stmt.order_by(SkillTemplate.created_at.desc())
        elif sort == 'top_rated':
            stmt = stmt.order_by(
                SkillTemplate.rating_sum.desc().nullslast(),
                SkillTemplate.rating_count.desc(),
            )
        else:  # popular (default)
            stmt = stmt.order_by(SkillTemplate.usage_count.desc())
        stmt = stmt.offset(skip).limit(min(limit, 100))
        res = await session.execute(stmt)
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@app.get('/skills/{template_id}')
async def get_skill_template(request: Request, template_id: int) -> JSONResponse:
    """Get a single skill template by ID."""
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'not found'}, status_code=404)
        data = dict(row._mapping)
        # Non-public templates only visible to owner or admin
        if not data.get('is_public'):
            uid = await _get_user_id(request)
            if not uid or (data.get('user_id') != uid and not admin_required(request)):
                return JSONResponse({'detail': 'not found'}, status_code=404)
    return JSONResponse(jsonable_encoder(data))


@app.post('/skills')
async def create_skill_template(request: Request, payload: SkillTemplateCreate) -> JSONResponse:
    """Create a new skill template."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        tmpl = SkillTemplate(
            user_id=uid,
            title=payload.title,
            title_fa=payload.title_fa,
            description=payload.description,
            description_fa=payload.description_fa,
            category=payload.category,
            prompt_template=payload.prompt_template,
            variables=payload.variables,
            default_model=payload.default_model,
            is_public=payload.is_public,
            tags=payload.tags,
        )
        session.add(tmpl)
        await session.commit()
        await session.refresh(tmpl)
        return JSONResponse(jsonable_encoder({
            'id': tmpl.id, 'title': tmpl.title, 'title_fa': tmpl.title_fa,
            'description': tmpl.description, 'description_fa': tmpl.description_fa,
            'category': tmpl.category, 'prompt_template': tmpl.prompt_template,
            'variables': tmpl.variables, 'default_model': tmpl.default_model,
            'is_public': tmpl.is_public, 'is_featured': tmpl.is_featured,
            'usage_count': tmpl.usage_count, 'rating_sum': tmpl.rating_sum,
            'rating_count': tmpl.rating_count, 'tags': tmpl.tags,
            'created_at': tmpl.created_at, 'updated_at': tmpl.updated_at,
        }))


@app.put('/skills/{template_id}')
async def update_skill_template(request: Request, template_id: int, payload: SkillTemplateUpdate) -> JSONResponse:
    """Update a skill template (owner only)."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'not found'}, status_code=404)
        if row.user_id != uid:
            return JSONResponse({'detail': 'forbidden'}, status_code=403)
        update_data = {}
        for field in ['title', 'title_fa', 'description', 'description_fa', 'category',
                       'prompt_template', 'variables', 'default_model', 'is_public', 'tags']:
            val = getattr(payload, field, None)
            if val is not None:
                update_data[field] = val
        if update_data:
            update_data['updated_at'] = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.execute(
                SkillTemplate.__table__.update().where(SkillTemplate.id == template_id),
                update_data,
            )
            await session.commit()
    return JSONResponse({'status': 'ok'})


@app.delete('/skills/{template_id}')
async def delete_skill_template(request: Request, template_id: int) -> JSONResponse:
    """Delete a skill template (owner only)."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'not found'}, status_code=404)
        if row.user_id != uid:
            return JSONResponse({'detail': 'forbidden'}, status_code=403)
        await session.execute(
            SkillTemplate.__table__.delete().where(SkillTemplate.id == template_id)
        )
        await session.commit()
    return JSONResponse({'status': 'deleted'})


@app.post('/skills/{template_id}/rate')
async def rate_skill_template(request: Request, template_id: int, payload: SkillRatingRequest) -> JSONResponse:
    """Rate a skill template (1-5)."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if payload.rating < 1 or payload.rating > 5:
        return JSONResponse({'detail': 'rating must be between 1 and 5'}, status_code=400)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        # Check template exists
        res = await session.execute(
            SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
        )
        if not res.fetchone():
            return JSONResponse({'detail': 'not found'}, status_code=404)
        # Upsert rating
        existing = await session.execute(
            SkillTemplateRating.__table__.select().where(
                SkillTemplateRating.template_id == template_id,
                SkillTemplateRating.user_id == uid,
            )
        )
        old_rating = existing.fetchone()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if old_rating:
            old_val = old_rating.rating
            await session.execute(
                SkillTemplateRating.__table__.update().where(
                    SkillTemplateRating.template_id == template_id,
                    SkillTemplateRating.user_id == uid,
                ),
                {'rating': payload.rating, 'created_at': now},
            )
            # Update aggregates: subtract old, add new
            await session.execute(
                SkillTemplate.__table__.update().where(SkillTemplate.id == template_id),
                {
                    'rating_sum': SkillTemplate.rating_sum - old_val + payload.rating,
                    'updated_at': now,
                },
            )
        else:
            session.add(SkillTemplateRating(
                template_id=template_id,
                user_id=uid,
                rating=payload.rating,
            ))
            await session.execute(
                SkillTemplate.__table__.update().where(SkillTemplate.id == template_id),
                {
                    'rating_sum': SkillTemplate.rating_sum + payload.rating,
                    'rating_count': SkillTemplate.rating_count + 1,
                    'updated_at': now,
                },
            )
        await session.commit()
    return JSONResponse({'status': 'ok'})


@app.post('/skills/{template_id}/use')
async def use_skill_template(request: Request, template_id: int, payload: SkillUseRequest) -> JSONResponse:
    """Use a skill template: increment usage count and return rendered prompt."""
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'not found'}, status_code=404)
        # Increment usage count
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.execute(
            SkillTemplate.__table__.update().where(SkillTemplate.id == template_id),
            {'usage_count': SkillTemplate.usage_count + 1, 'updated_at': now},
        )
        await session.commit()
        # Render prompt template by replacing {var_name} placeholders
        rendered = row.prompt_template
        for var_name, var_value in payload.variables.items():
            rendered = rendered.replace('{' + var_name + '}', var_value)
        model = payload.model or row.default_model or ''
    return JSONResponse(jsonable_encoder({
        'rendered_prompt': rendered,
        'model': model,
    }))


# ═══════════════════════════════════════
# Wallet
# ═══════════════════════════════════════

class TopupRequest(BaseModel):
    amount: int

@app.get('/wallet')
async def get_wallet(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
            {'uid': uid}
        )
        row = res.fetchone()
        balance = row.balance if row else 0
    return JSONResponse({'balance': balance})

@app.get('/wallet/ledger')
async def get_ledger(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            Ledger.__table__.select().where(Ledger.user_id == uid).order_by(Ledger.created_at.desc()).limit(50)
        )
        rows = [{'id': r.id, 'amount': r.amount, 'balance_after': r.balance_after, 'reason': r.reason, 'created_at': r.created_at} for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))

@app.post('/wallet/topup')
async def topup(request: Request, payload: TopupRequest) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if payload.amount <= 0:
        return JSONResponse({'detail': 'amount must be positive'}, status_code=400)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        # Get current balance
        res = await session.execute(
            sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
            {'uid': uid}
        )
        row = res.fetchone()
        current = row.balance if row else 0
        new_balance = current + payload.amount
        entry = Ledger(user_id=uid, amount=payload.amount, balance_after=new_balance, reason='شارژ حساب')
        session.add(entry)
        await session.commit()
    return JSONResponse({'status': 'ok', 'balance_after': new_balance})

# ═══════════════════════════════════════
# Admin: User Management
# ═══════════════════════════════════════

@app.get('/admin/users')
async def admin_users(request: Request) -> JSONResponse:
    """List all users (admin only)"""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    page = int(request.query_params.get('page', 1))
    limit = min(int(request.query_params.get('limit', 50)), 200)
    offset = (page - 1) * limit

    async with async_session() as session:
        # Total count
        count_res = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM users'))
        total = count_res.fetchone().c

        # Users with balance
        res = await session.execute(
            sqlalchemy.text('''
                SELECT u.id, u.email, u.phone, u.telegram_id, u.referral_code,
                       u.referred_by, u.created_at,
                       COALESCE((SELECT SUM(amount) FROM ledger WHERE user_id = u.id), 0) as balance,
                       COALESCE((SELECT used_today FROM quota WHERE user_id = u.id), 0) as used_today
                FROM users u
                ORDER BY u.created_at DESC
                LIMIT :limit OFFSET :offset
            '''),
            {'limit': limit, 'offset': offset}
        )
        rows = [dict(r._mapping) for r in res.fetchall()]

    return JSONResponse(jsonable_encoder({
        'users': rows,
        'total': total,
        'page': page,
        'limit': limit,
    }))


@app.post('/admin/users/{uid}/ban')
async def admin_ban_user(request: Request, uid: int) -> JSONResponse:
    """Ban/unban a user"""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        user = await session.get(User, uid)
        if not user:
            return JSONResponse({'detail': 'not found'}, status_code=404)
        # Toggle: set quota to 0 = ban
        await session.execute(
            Quota.__table__.update().where(Quota.user_id == uid),
            {'daily_limit': 0 if user.telegram_id != -1 else 200000}
        )
        await session.execute(
            User.__table__.update().where(User.id == uid),
            {'telegram_id': -1 if user.telegram_id != -1 else None}
        )
        await session.commit()
        await _write_audit_log('admin.user.ban', target_type='user', target_id=uid, details={'banned': user.telegram_id != -1})
        return JSONResponse({'status': 'ok', 'banned': user.telegram_id != -1})


@app.put('/admin/users/{uid}')
async def admin_edit_user(request: Request, uid: int) -> JSONResponse:
    """Edit user details (admin)"""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    payload = await request.json()
    async with async_session() as session:
        if 'daily_limit' in payload:
            await session.execute(
                Quota.__table__.update().where(Quota.user_id == uid),
                {'daily_limit': int(payload['daily_limit'])}
            )
        if 'phone' in payload:
            await session.execute(
                User.__table__.update().where(User.id == uid),
                {'phone': payload['phone']}
            )
        await session.commit()
    await _write_audit_log('admin.user.edit', target_type='user', target_id=uid, details=dict(payload))
    return JSONResponse({'status': 'ok'})

# ═══════════════════════════════════════
# Data Export (CSV)
# ═══════════════════════════════════════

@app.get('/admin/export/ledger')
async def export_ledger(request: Request) -> Response:
    """Export all ledger entries as CSV"""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            Ledger.__table__.select().order_by(Ledger.created_at.desc()).limit(10000)
        )
        rows = res.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'user_id', 'amount', 'balance_after', 'reason', 'created_at'])
    for r in rows:
        writer.writerow([r.id, r.user_id, r.amount, r.balance_after, r.reason, r.created_at])

    await _write_audit_log('admin.export.ledger')
    return Response(
        content=output.getvalue(),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=ledger_export.csv'},
    )


@app.get('/admin/export/users')
async def export_users(request: Request) -> Response:
    """Export all users as CSV"""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('''
                SELECT u.id, u.email, u.phone, u.created_at,
                       COALESCE((SELECT SUM(amount) FROM ledger WHERE user_id = u.id), 0) as balance
                FROM users u ORDER BY u.created_at DESC
            ''')
        )
        rows = res.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'email', 'phone', 'balance', 'created_at'])
    for r in rows:
        writer.writerow([r.id, r.email, r.phone, r.balance, r.created_at])

    await _write_audit_log('admin.export.users')
    return Response(
        content=output.getvalue(),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename=users_export.csv'},
    )

# ═══════════════════════════════════════
# Email (SMTP)
# ═══════════════════════════════════════

SMTP_HOST = os.getenv('SMTP_HOST', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASS = os.getenv('SMTP_PASS', '')
SMTP_FROM = os.getenv('SMTP_FROM', 'noreply@multiai.ir')

async def send_email(to: str, subject: str, body: str) -> bool:
    if not SMTP_HOST:
        print(f'[EMAIL] Would send to {to}: {subject}')
        return False
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(body, 'html', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = SMTP_FROM
    msg['To'] = to
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f'[EMAIL] Failed: {e}')
        return False


@app.post('/auth/send-welcome')
async def send_welcome_email(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()
        if not user or not user.email:
            return JSONResponse({'detail': 'no email'}, status_code=400)
    body = f'<div dir="rtl" style="font-family:Tahoma;max-width:600px;margin:auto;padding:20px;"><h1 style="color:#6c5cf5;">به Multiai خوش آمدید! 🎉</h1><p>سلام {user.email}،</p><p>حساب شما با موفقیت ساخته شد.</p><p><a href="{BASE_URL}/chat" style="background:#6c5cf5;color:white;padding:10px 20px;text-decoration:none;border-radius:8px;">شروع چت</a></p></div>'
    ok = await send_email(user.email, 'به Multiai خوش آمدید!', body)
    return JSONResponse({'status': 'sent' if ok else 'queued'})

@app.get('/admin/analytics')
async def admin_analytics(request: Request) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        # User count
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM users'))
        user_count = r.fetchone().c

        # Total revenue
        r = await session.execute(sqlalchemy.text("SELECT COALESCE(SUM(amount), 0) as total FROM ledger WHERE amount > 0"))
        total_revenue = r.fetchone().total

        # Total tokens used
        r = await session.execute(sqlalchemy.text('SELECT COALESCE(SUM(used_today), 0) as total FROM quota'))
        total_tokens = r.fetchone().total

        # Conversation count
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM conversations'))
        conv_count = r.fetchone().c

        # Active users (used today)
        r = await session.execute(sqlalchemy.text("SELECT COUNT(*) as c FROM quota WHERE used_today > 0"))
        active_users = r.fetchone().c

        # Recent ledger (last 20)
        r = await session.execute(
            Ledger.__table__.select().order_by(Ledger.created_at.desc()).limit(20)
        )
        recent = [{'id': row.id, 'user_id': row.user_id, 'amount': row.amount, 'balance_after': row.balance_after, 'reason': row.reason, 'created_at': row.created_at} for row in r.fetchall()]

    return JSONResponse(jsonable_encoder({
        'user_count': user_count,
        'active_users': active_users,
        'total_revenue': total_revenue,
        'total_tokens': total_tokens,
        'conv_count': conv_count,
        'recent_ledger': recent,
    }))

# ═══════════════════════════════════════
# Zarinpal Payment Gateway
# ═══════════════════════════════════════

from payment import create_payment, verify_payment, PaymentRequest, handle_payment_callback, CallbackResult

@app.post('/payment/request')
async def payment_request(request: Request, payload: PaymentRequest) -> JSONResponse:
    """Create a Zarinpal payment and return redirect URL"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if payload.amount < 1000:
        return JSONResponse({'detail': 'minimum amount is 1000 Tomans'}, status_code=400)

    callback_url = f"{BASE_URL}/api/payment/callback"

    result = await create_payment(
        amount=payload.amount,
        description=payload.description,
        callback_url=callback_url,
    )

    if result.get('status') != 'ok':
        return JSONResponse({'detail': result.get('error', 'payment failed')}, status_code=result.get('status', 500))

    # Store pending payment in DB
    if async_session is not None:
        async with async_session() as session:
            payment = Payment(
                user_id=uid,
                amount=payload.amount,
                authority=result['authority'],
                status='pending',
            )
            session.add(payment)
            await session.commit()

    return JSONResponse({
        'authority': result['authority'],
        'url': result['url'],
        'amount': payload.amount,
    })


@app.get('/payment/callback')
async def payment_callback(request: Request) -> JSONResponse:
    """Zarinpal redirects here after payment.

    Delegates financial-correctness logic to :func:`payment.handle_payment_callback`,
    then dispatches based on ``payment_type`` (wallet_topup, subscription,
    credit_package).
    """
    authority = request.query_params.get('Authority')
    status = request.query_params.get('Status', '')

    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    # First: look up the payment row to determine its type
    payment_type = 'wallet_topup'
    reference_id = None
    pay_row = None
    authority_str = authority or ''
    async with async_session() as session:
        pay_res = await session.execute(
            select(Payment).where(Payment.authority == authority_str)
        )
        pay_row = pay_res.fetchone()
        if pay_row:
            payment_type = getattr(pay_row, 'payment_type', 'wallet_topup') or 'wallet_topup'
            reference_id = getattr(pay_row, 'reference_id', None)

    # Verify + credit wallet (the standard flow)
    async with async_session() as session:
        repo = SqlBillingRepo(session)
        result = await handle_payment_callback(repo, authority=authority or "", status=status)

    if not result.ok:
        # Redirect based on type
        fail_redirect = {
            'subscription': f'{BASE_URL}/plans?payment=failed',
            'credit_package': f'{BASE_URL}/credits?payment=failed',
        }.get(payment_type, f'{BASE_URL}/wallet?payment=failed')
        return JSONResponse({'detail': result.detail, 'redirect': fail_redirect}, status_code=result.code)

    # Post-verification dispatch based on payment_type
    redirect_path = '/wallet?payment=success'
    extra_data = {}

    if payment_type == 'subscription' and reference_id:
        uid = pay_row.user_id if pay_row else 0
        async with async_session() as session:
            # Look up the plan
            plan_res = await session.execute(select(Plan).where(Plan.id == int(reference_id)))
            plan = plan_res.fetchone()
            if plan:
                # Cancel any existing active subscription
                await session.execute(
                    sqlalchemy.text(
                        "UPDATE subscriptions SET status='cancelled', cancelled_at=now(), updated_at=now() "
                        "WHERE user_id=:uid AND status='active'"
                    ),
                    {'uid': uid}
                )
                # Create new subscription
                from datetime import timedelta
                new_sub = Subscription(
                    user_id=uid,
                    plan=plan.name_en.lower() if hasattr(plan, 'name_en') else str(plan.id),
                    plan_id=plan.id,
                    status='active',
                    monthly_token_quota=plan.monthly_token_quota,
                    tokens_used_this_period=0,
                    auto_renew=True,
                    price_paid=result.amount or 0,
                    starts_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    ends_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
                )
                session.add(new_sub)
                await session.commit()
                extra_data['subscription'] = plan.name_en
        redirect_path = '/dashboard?subscription=active'

    elif payment_type == 'credit_package' and reference_id:
        uid = pay_row.user_id if pay_row else 0
        async with async_session() as session:
            pkg_res = await session.execute(select(CreditPackage).where(CreditPackage.id == int(reference_id)))
            pkg = pkg_res.fetchone()
            if pkg:
                # Credit wallet with total_credits (includes bonus)
                credit_amount = pkg.total_credits
                # Get current balance
                bal_res = await session.execute(
                    sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
                    {'uid': uid}
                )
                bal_row = bal_res.fetchone()
                current_balance = bal_row.balance if bal_row else 0
                new_balance = current_balance + credit_amount
                entry = Ledger(
                    user_id=uid,
                    amount=credit_amount,
                    balance_after=new_balance,
                    reason=f"بسته اعتباری: {pkg.name_fa} ({pkg.base_amount:,} + {pkg.bonus_percent}% پاداش)",
                    idempotency_key=f"credit-pkg:{reference_id}:{result.ref_id}",
                )
                session.add(entry)
                await session.commit()
                extra_data['credits_added'] = credit_amount
                extra_data['package'] = pkg.name_fa
        redirect_path = '/wallet?payment=success'

    return JSONResponse({
        'status': 'ok',
        'ref_id': result.ref_id,
        'amount': result.amount,
        'redirect': f'{BASE_URL}{redirect_path}',
        **extra_data,
    })


@app.get('/payment/history')
async def payment_history(request: Request) -> JSONResponse:
    """Get user's payment history"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            Payment.__table__.select()
            .where(Payment.user_id == uid)
            .order_by(Payment.created_at.desc())
            .limit(50)
        )
        rows = [
            {
                'id': r.id,
                'amount': r.amount,
                'authority': r.authority,
                'ref_id': r.ref_id,
                'status': r.status,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'verified_at': r.verified_at.isoformat() if r.verified_at else None,
            }
            for r in res.fetchall()
        ]
    return JSONResponse(jsonable_encoder(rows))

# ═══════════════════════════════════════
# Notifications
# ═══════════════════════════════════════

@app.get('/notifications')
async def list_notifications(request: Request) -> JSONResponse:
    """Get user notifications"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        # Auto-create usage alert if approaching limit
        quota_res = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
        quota = quota_res.fetchone()
        if quota and quota.daily_limit > 0:
            usage_pct = (quota.used_today / quota.daily_limit) * 100
            if usage_pct >= 80:
                # Check if we already sent an alert today
                today = datetime.now(timezone.utc).replace(tzinfo=None).date()
                existing = await session.execute(
                    Notification.__table__.select().where(
                        Notification.user_id == uid,
                        Notification.type == 'alert',
                        Notification.title == 'هشدار مصرف',
                    )
                )
                existing_rows = existing.fetchall()
                today_alerts = [r for r in existing_rows if r.created_at.date() == today]
                if not today_alerts:
                    alert = Notification(
                        user_id=uid,
                        type='alert',
                        title='هشدار مصرف',
                        body=f'شما {usage_pct:.0f}٪ از سقف مصرف روزانه خود را استفاده کرده‌اید. ({quota.used_today:,} از {quota.daily_limit:,} توکن)',
                    )
                    session.add(alert)
                    await session.commit()

        # Get recent notifications
        res = await session.execute(
            Notification.__table__.select()
            .where(Notification.user_id == uid)
            .order_by(Notification.created_at.desc())
            .limit(20)
        )
        rows = [
            {
                'id': r.id,
                'type': r.type,
                'title': r.title,
                'body': r.body,
                'read': r.read,
                'created_at': r.created_at.isoformat() if r.created_at else None,
            }
            for r in res.fetchall()
        ]
    return JSONResponse(jsonable_encoder(rows))


@app.post('/notifications/{nid}/read')
async def mark_notification_read(request: Request, nid: int) -> JSONResponse:
    """Mark notification as read"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        await session.execute(
            Notification.__table__.update()
            .where(Notification.id == nid, Notification.user_id == uid),
            {'read': True}
        )
        await session.commit()
    return JSONResponse({'status': 'ok'})

# ═══════════════════════════════════════
# API Keys
# ═══════════════════════════════════════

class ApiKeyCreate(BaseModel):
    name: str = 'Default'
    scopes: str = 'read'
    expires_at: str | None = None

@app.post('/api-keys')
async def create_api_key(request: Request, payload: ApiKeyCreate) -> JSONResponse:
    """Generate a new API key. The secret is shown only once."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    raw_key = f'sk-{secrets.token_urlsafe(32)}'
    key_hash = _hash_api_key(raw_key)
    key_prefix = raw_key[:12]

    expires_at = None
    if payload.expires_at:
        try:
            expires_at = datetime.fromisoformat(payload.expires_at)
        except ValueError:
            return JSONResponse({'detail': 'invalid expires_at (ISO8601 expected)'}, status_code=400)

    async with async_session() as session:
        key = ApiKey(
            user_id=uid, name=payload.name, key_hash=key_hash,
            key_prefix=key_prefix, scopes=payload.scopes, expires_at=expires_at,
        )
        session.add(key)
        await session.commit()
        await session.refresh(key)

    return JSONResponse({
        'id': key.id,
        'name': key.name,
        'key': raw_key,
        'prefix': key_prefix,
        'masked': f"{key_prefix}••••••••••••",
        'scopes': key.scopes,
        'expires_at': key.expires_at.isoformat() if key.expires_at else None,
        'created_at': key.created_at.isoformat() if key.created_at else None,
    })


@app.get('/api-keys')
async def list_api_keys(request: Request) -> JSONResponse:
    """List user's API keys (never expose raw key)"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            ApiKey.__table__.select()
            .where(ApiKey.user_id == uid)
            .order_by(ApiKey.created_at.desc())
        )
        rows = [
            {
                'id': r.id,
                'name': r.name,
                'prefix': r.key_prefix,
                'masked': f"{r.key_prefix}••••••••••••",
                'scopes': r.scopes,
                'active': r.active,
                'revoked_at': r.revoked_at.isoformat() if r.revoked_at else None,
                'expires_at': r.expires_at.isoformat() if r.expires_at else None,
                'last_used_at': r.last_used.isoformat() if r.last_used else None,
                'created_at': r.created_at.isoformat() if r.created_at else None,
            }
            for r in res.fetchall()
        ]
    return JSONResponse(jsonable_encoder(rows))


@app.delete('/api-keys/{key_id}')
async def revoke_api_key(request: Request, key_id: int) -> JSONResponse:
    """Revoke (deactivate) an API key"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        await session.execute(
            ApiKey.__table__.update()
            .where(ApiKey.id == key_id, ApiKey.user_id == uid),
            {'active': False, 'revoked_at': datetime.now(timezone.utc).replace(tzinfo=None)}
        )
        await session.commit()
    return JSONResponse({'status': 'revoked'})

# ═══════════════════════════════════════
# Pricing & Plans
# ═══════════════════════════════════════

@app.get('/plans')
async def list_plans() -> JSONResponse:
    """List all active subscription plans + credit packages (public)"""
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        plans_result = await session.execute(
            select(Plan).where(Plan.active == True).order_by(Plan.sort_order)
        )
        plans_objs = plans_result.scalars().all()
        plans_rows = [
            {
                'id': p.id, 'name_fa': p.name_fa, 'name_en': p.name_en,
                'price_monthly': p.price_monthly, 'monthly_token_quota': p.monthly_token_quota,
                'daily_token_limit': p.daily_token_limit, 'models_allowed': p.models_allowed,
                'priority_queue': p.priority_queue, 'features': p.features or [],
            }
            for p in plans_objs
        ]
        pkgs_result = await session.execute(
            select(CreditPackage).where(CreditPackage.active == True).order_by(CreditPackage.sort_order)
        )
        pkgs_objs = pkgs_result.scalars().all()
        pkgs_rows = [
            {
                'id': p.id, 'name_fa': p.name_fa, 'name_en': p.name_en,
                'base_amount': p.base_amount, 'bonus_percent': p.bonus_percent,
                'total_credits': p.total_credits,
            }
            for p in pkgs_objs
        ]
    return JSONResponse({'plans': plans_rows, 'credit_packages': pkgs_rows})


@app.get('/plans/{plan_id}')
async def get_plan(plan_id: str) -> JSONResponse:
    """Get a single plan by ID (public)"""
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM plans WHERE id = :pid AND active = true'),
            {'pid': plan_id}
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'plan not found'}, status_code=404)
    return JSONResponse(jsonable_encoder(dict(row._mapping)))


@app.get('/credit-packages')
async def list_credit_packages() -> JSONResponse:
    """List all active credit packages (public)"""
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM credit_packages WHERE active = true ORDER BY sort_order')
        )
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@app.get('/credit-packages/{pkg_id}')
async def get_credit_package(pkg_id: str) -> JSONResponse:
    """Get a single credit package by ID (public)"""
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM credit_packages WHERE id = :pid AND active = true'),
            {'pid': pkg_id}
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'package not found'}, status_code=404)
    return JSONResponse(jsonable_encoder(dict(row._mapping)))


class SubscribeRequest(BaseModel):
    plan_id: str


@app.post('/subscribe')
async def subscribe_to_plan(request: Request, payload: SubscribeRequest) -> JSONResponse:
    """Subscribe the current user to a plan. Cancels any existing active subscription."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        # Validate plan exists
        plan_res = await session.execute(
            sqlalchemy.text('SELECT * FROM plans WHERE id = :pid AND active = true'),
            {'pid': payload.plan_id}
        )
        plan = plan_res.fetchone()
        if not plan:
            return JSONResponse({'detail': 'plan not found'}, status_code=404)

        plan_data = dict(plan._mapping)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Cancel any existing active subscription
        await session.execute(
            sqlalchemy.text(
                "UPDATE subscriptions SET status = 'cancelled', cancelled_at = :now, updated_at = :now "
                "WHERE user_id = :uid AND status = 'active'"
            ),
            {'uid': uid, 'now': now}
        )

        # Create new subscription
        ends_at = now + timedelta(days=30)
        sub = Subscription(
            user_id=uid,
            plan=payload.plan_id,
            starts_at=now,
            ends_at=ends_at,
            status='active',
            monthly_token_quota=plan_data['monthly_token_quota'],
            tokens_used_this_period=0,
            auto_renew=True,
            price_paid=plan_data['price_monthly'],
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)

        # If free plan, no payment needed. Otherwise, create a payment order.
        if plan_data['price_monthly'] > 0:
            await _write_audit_log('subscribe', target_type='subscription', target_id=sub.id,
                                   details={'plan': payload.plan_id, 'price': plan_data['price_monthly']})

    return JSONResponse({
        'status': 'ok',
        'subscription': {
            'id': sub.id,
            'plan': payload.plan_id,
            'price_monthly': plan_data['price_monthly'],
            'monthly_token_quota': plan_data['monthly_token_quota'],
            'daily_token_limit': plan_data['daily_token_limit'],
            'starts_at': sub.starts_at.isoformat() if sub.starts_at else None,
            'ends_at': sub.ends_at.isoformat() if sub.ends_at else None,
            'status': sub.status,
        }
    })


@app.get('/subscription')
async def get_subscription(request: Request) -> JSONResponse:
    """Get the user's current active subscription"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                "SELECT * FROM subscriptions WHERE user_id = :uid AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {'uid': uid}
        )
        sub = res.fetchone()
        if not sub:
            return JSONResponse({'subscription': None, 'plan': None})

        sub_data = dict(sub._mapping)

        # Get plan details
        plan_res = await session.execute(
            sqlalchemy.text('SELECT * FROM plans WHERE id = :pid'),
            {'pid': sub_data['plan']}
        )
        plan_row = plan_res.fetchone()
        plan_data = dict(plan_row._mapping) if plan_row else None

    return JSONResponse(jsonable_encoder({
        'subscription': sub_data,
        'plan': plan_data,
    }))


@app.post('/subscription/cancel')
async def cancel_subscription(request: Request) -> JSONResponse:
    """Cancel the user's active subscription"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                "UPDATE subscriptions SET status = 'cancelled', cancelled_at = :now, auto_renew = false, updated_at = :now "
                "WHERE user_id = :uid AND status = 'active' RETURNING id, plan"
            ),
            {'uid': uid, 'now': now}
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'no active subscription'}, status_code=404)
        await session.commit()

    await _write_audit_log('subscription.cancel', target_type='subscription', target_id=row.id,
                           details={'plan': row.plan})
    return JSONResponse({'status': 'cancelled', 'subscription_id': row.id})


@app.post('/subscription/renew')
async def renew_subscription(request: Request) -> JSONResponse:
    """Renew the user's subscription (extend by 30 days, reset token usage)"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                "SELECT * FROM subscriptions WHERE user_id = :uid AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {'uid': uid}
        )
        sub = res.fetchone()
        if not sub:
            return JSONResponse({'detail': 'no active subscription'}, status_code=404)

        sub_data = dict(sub._mapping)
        new_ends_at = now + timedelta(days=30)

        # Get plan for token reset
        plan_res = await session.execute(
            sqlalchemy.text('SELECT monthly_token_quota FROM plans WHERE id = :pid'),
            {'pid': sub_data['plan']}
        )
        plan = plan_res.fetchone()
        quota = plan.monthly_token_quota if plan else 0

        await session.execute(
            sqlalchemy.text(
                "UPDATE subscriptions SET ends_at = :ends, tokens_used_this_period = 0, "
                "monthly_token_quota = :quota, updated_at = :now WHERE id = :sid"
            ),
            {'ends': new_ends_at, 'quota': quota, 'now': now, 'sid': sub_data['id']}
        )
        await session.commit()

    return JSONResponse({'status': 'renewed', 'ends_at': new_ends_at.isoformat()})


# ═══════════════════════════════════════
# Billing Settings
# ═══════════════════════════════════════

class BillingSettingsUpdate(BaseModel):
    payg_enabled: bool | None = None
    payg_hard_limit: int | None = None
    notify_on_usage_pct: int | None = None


@app.get('/billing/settings')
async def get_billing_settings(request: Request) -> JSONResponse:
    """Get user's billing settings (auto-creates defaults if missing)"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            UserBillingSetting.__table__.select().where(UserBillingSetting.user_id == uid)
        )
        row = res.fetchone()
        if not row:
            # Auto-create default settings
            settings = UserBillingSetting(user_id=uid)
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
            return JSONResponse(jsonable_encoder({
                'user_id': uid,
                'payg_enabled': True,
                'payg_hard_limit': None,
                'notify_on_usage_pct': 80,
            }))
    return JSONResponse(jsonable_encoder({
        'user_id': row.user_id,
        'payg_enabled': row.payg_enabled,
        'payg_hard_limit': row.payg_hard_limit,
        'notify_on_usage_pct': row.notify_on_usage_pct,
    }))


@app.put('/billing/settings')
async def update_billing_settings(request: Request, payload: BillingSettingsUpdate) -> JSONResponse:
    """Update user's billing settings"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    update_data = {'updated_at': now}
    if payload.payg_enabled is not None:
        update_data['payg_enabled'] = payload.payg_enabled
    if payload.payg_hard_limit is not None:
        update_data['payg_hard_limit'] = payload.payg_hard_limit
    if payload.notify_on_usage_pct is not None:
        update_data['notify_on_usage_pct'] = max(1, min(100, payload.notify_on_usage_pct))

    async with async_session() as session:
        # Upsert
        res = await session.execute(
            UserBillingSetting.__table__.select().where(UserBillingSetting.user_id == uid)
        )
        existing = res.fetchone()
        if existing:
            await session.execute(
                UserBillingSetting.__table__.update().where(UserBillingSetting.user_id == uid),
                update_data
            )
        else:
            settings = UserBillingSetting(
                user_id=uid,
                payg_enabled=payload.payg_enabled if payload.payg_enabled is not None else True,
                payg_hard_limit=payload.payg_hard_limit,
                notify_on_usage_pct=payload.notify_on_usage_pct if payload.notify_on_usage_pct is not None else 80,
            )
            session.add(settings)
        await session.commit()

    return JSONResponse({'status': 'ok'})


# ═══════════════════════════════════════
# Admin: Plans & Credit Packages
# ═══════════════════════════════════════

@app.get('/admin/plans')
async def admin_list_plans(request: Request) -> JSONResponse:
    """List all plans (admin, including inactive)"""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text('SELECT * FROM plans ORDER BY sort_order'))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@app.post('/admin/plans')
async def admin_create_plan(request: Request) -> JSONResponse:
    """Create or update a plan (admin)"""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    payload = await request.json()
    plan_id = payload.get('id')
    if not plan_id:
        return JSONResponse({'detail': 'id is required'}, status_code=400)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT id FROM plans WHERE id = :pid'), {'pid': plan_id}
        )
        existing = res.fetchone()

        if existing:
            # Update
            fields = ['name_fa', 'name_en', 'price_monthly', 'monthly_token_quota',
                       'daily_token_limit', 'priority_queue', 'features', 'active', 'sort_order']
            set_parts = []
            params = {'pid': plan_id, 'now': now}
            for f in fields:
                if f in payload:
                    set_parts.append(f'{f} = :{f}')
                    params[f] = payload[f]
            set_parts.append('updated_at = :now')
            set_parts.append('models_allowed = :models_allowed')
            params['models_allowed'] = payload.get('models_allowed')

            await session.execute(
                sqlalchemy.text(f"UPDATE plans SET {', '.join(set_parts)} WHERE id = :pid"),
                params
            )
        else:
            # Insert
            await session.execute(
                sqlalchemy.text(
                    "INSERT INTO plans (id, name_fa, name_en, price_monthly, monthly_token_quota, "
                    "daily_token_limit, models_allowed, priority_queue, features, active, sort_order) "
                    "VALUES (:id, :name_fa, :name_en, :price_monthly, :monthly_token_quota, "
                    ":daily_token_limit, :models_allowed, :priority_queue, :features, :active, :sort_order)"
                ),
                {
                    'id': plan_id,
                    'name_fa': payload.get('name_fa', ''),
                    'name_en': payload.get('name_en', ''),
                    'price_monthly': payload.get('price_monthly', 0),
                    'monthly_token_quota': payload.get('monthly_token_quota', 0),
                    'daily_token_limit': payload.get('daily_token_limit', 0),
                    'models_allowed': payload.get('models_allowed'),
                    'priority_queue': payload.get('priority_queue', False),
                    'features': json.dumps(payload.get('features', [])),
                    'active': payload.get('active', True),
                    'sort_order': payload.get('sort_order', 0),
                }
            )
        await session.commit()

    await _write_audit_log('admin.plan.upsert', target_type='plan', target_id=plan_id, details=payload)
    return JSONResponse({'status': 'ok', 'id': plan_id})


@app.get('/admin/credit-packages')
async def admin_list_credit_packages(request: Request) -> JSONResponse:
    """List all credit packages (admin, including inactive)"""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text('SELECT * FROM credit_packages ORDER BY sort_order'))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@app.post('/admin/credit-packages')
async def admin_create_credit_package(request: Request) -> JSONResponse:
    """Create or update a credit package (admin)"""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    payload = await request.json()
    pkg_id = payload.get('id')
    if not pkg_id:
        return JSONResponse({'detail': 'id is required'}, status_code=400)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT id FROM credit_packages WHERE id = :pid'), {'pid': pkg_id}
        )
        existing = res.fetchone()

        if existing:
            fields = ['name_fa', 'name_en', 'base_amount', 'bonus_percent',
                       'total_credits', 'active', 'sort_order']
            set_parts = []
            params = {'pid': pkg_id, 'now': now}
            for f in fields:
                if f in payload:
                    set_parts.append(f'{f} = :{f}')
                    params[f] = payload[f]
            set_parts.append('updated_at = :now')
            await session.execute(
                sqlalchemy.text(f"UPDATE credit_packages SET {', '.join(set_parts)} WHERE id = :pid"),
                params
            )
        else:
            await session.execute(
                sqlalchemy.text(
                    "INSERT INTO credit_packages (id, name_fa, name_en, base_amount, bonus_percent, "
                    "total_credits, active, sort_order) "
                    "VALUES (:id, :name_fa, :name_en, :base_amount, :bonus_percent, "
                    ":total_credits, :active, :sort_order)"
                ),
                {
                    'id': pkg_id,
                    'name_fa': payload.get('name_fa', ''),
                    'name_en': payload.get('name_en', ''),
                    'base_amount': payload.get('base_amount', 0),
                    'bonus_percent': payload.get('bonus_percent', 0),
                    'total_credits': payload.get('total_credits', 0),
                    'active': payload.get('active', True),
                    'sort_order': payload.get('sort_order', 0),
                }
            )
        await session.commit()

    await _write_audit_log('admin.credit_package.upsert', target_type='credit_package', target_id=pkg_id, details=payload)
    return JSONResponse({'status': 'ok', 'id': pkg_id})


@app.get('/admin/subscriptions')
async def admin_list_subscriptions(request: Request) -> JSONResponse:
    """List all subscriptions (admin)"""
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    page = int(request.query_params.get('page', 1))
    limit = min(int(request.query_params.get('limit', 50)), 200)
    offset = (page - 1) * limit

    async with async_session() as session:
        count_res = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM subscriptions'))
        total = count_res.fetchone().c

        res = await session.execute(
            sqlalchemy.text(
                'SELECT s.*, u.email FROM subscriptions s '
                'LEFT JOIN users u ON s.user_id = u.id '
                'ORDER BY s.created_at DESC LIMIT :limit OFFSET :offset'
            ),
            {'limit': limit, 'offset': offset}
        )
        rows = [dict(r._mapping) for r in res.fetchall()]

    return JSONResponse(jsonable_encoder({
        'subscriptions': rows,
        'total': total,
        'page': page,
        'limit': limit,
    }))


# ═══════════════════════════════════════
# Pricing & Billing Endpoints
# ═══════════════════════════════════════

@app.get('/me/subscription')
async def get_my_subscription(request: Request) -> JSONResponse:
    """Auth required: return current subscription, PAYG status, and usage summary."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        # Active subscription
        sub_res = await session.execute(
            select(Subscription).where(
                Subscription.user_id == uid,
                Subscription.status == 'active',
            ).order_by(Subscription.created_at.desc())
        )
        sub = sub_res.fetchone()

        # Billing settings
        billing_res = await session.execute(
            select(UserBillingSetting).where(UserBillingSetting.user_id == uid)
        )
        billing = billing_res.fetchone()

        # Usage summary (current period)
        usage_tokens = 0
        usage_events_count = 0
        if sub:
            usage_tokens = getattr(sub, 'tokens_used_this_period', 0) or 0
        # Count events this month
        month_start = datetime.now(timezone.utc).replace(tzinfo=None).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count_res = await session.execute(
            sqlalchemy.text(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens "
                "FROM usage_events WHERE user_id=:uid AND created_at >= :month_start"
            ),
            {'uid': uid, 'month_start': month_start}
        )
        count_row = count_res.fetchone()
        if count_row:
            usage_events_count = count_row.cnt
            usage_tokens = count_row.total_tokens

    sub_data = None
    if sub:
        sub_data = {
            'id': sub.id,
            'plan': getattr(sub, 'plan', ''),
            'plan_id': getattr(sub, 'plan_id', None),
            'status': sub.status,
            'monthly_token_quota': getattr(sub, 'monthly_token_quota', 0),
            'tokens_used_this_period': usage_tokens,
            'auto_renew': getattr(sub, 'auto_renew', True),
            'starts_at': sub.starts_at.isoformat() if sub.starts_at else None,
            'ends_at': sub.ends_at.isoformat() if sub.ends_at else None,
            'price_paid': getattr(sub, 'price_paid', 0),
        }

    return JSONResponse({
        'subscription': sub_data,
        'payg_enabled': getattr(billing, 'payg_enabled', False) if billing else False,
        'payg_hard_limit': getattr(billing, 'payg_hard_limit', 0) if billing else 0,
        'usage': {
            'tokens_this_period': usage_tokens,
            'events_this_month': usage_events_count,
        },
    })


class BillingUpdate(BaseModel):
    payg_enabled: bool | None = None
    payg_hard_limit: int | None = None
    notify_on_usage_pct: int | None = None


@app.get('/me/billing')
async def get_my_billing(request: Request) -> JSONResponse:
    """Auth required: return billing settings (PAYG toggle, limits)."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            select(UserBillingSetting).where(UserBillingSetting.user_id == uid)
        )
        billing = res.fetchone()

    if not billing:
        return JSONResponse({
            'user_id': uid,
            'payg_enabled': False,
            'payg_hard_limit': 0,
            'notify_on_usage_pct': 80,
        })

    return JSONResponse({
        'user_id': billing.user_id,
        'payg_enabled': billing.payg_enabled,
        'payg_hard_limit': billing.payg_hard_limit,
        'notify_on_usage_pct': billing.notify_on_usage_pct,
    })


@app.put('/me/billing')
async def update_my_billing(request: Request, payload: BillingUpdate) -> JSONResponse:
    """Auth required: update billing settings (toggle PAYG, set hard limit)."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            select(UserBillingSetting).where(UserBillingSetting.user_id == uid)
        )
        billing = res.fetchone()

        if not billing:
            # Create defaults then update
            billing = UserBillingSetting(user_id=uid)
            session.add(billing)
            await session.flush()

        if payload.payg_enabled is not None:
            billing.payg_enabled = payload.payg_enabled
        if payload.payg_hard_limit is not None:
            billing.payg_hard_limit = payload.payg_hard_limit
        if payload.notify_on_usage_pct is not None:
            billing.notify_on_usage_pct = payload.notify_on_usage_pct
        billing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()

    return JSONResponse({'status': 'ok'})


class SubscriptionCheckout(BaseModel):
    plan_id: str


@app.post('/subscription/checkout')
async def subscription_checkout(request: Request, payload: SubscriptionCheckout) -> JSONResponse:
    """Auth required: create ZarinPal payment for a subscription plan."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        plan_res = await session.execute(select(Plan).where(Plan.id == payload.plan_id, Plan.active == True))
        plan = plan_res.scalar_one_or_none()
        if not plan:
            return JSONResponse({'detail': 'plan not found'}, status_code=404)
        if plan.price_monthly <= 0:
            return JSONResponse({'detail': 'this plan is free, no payment needed'}, status_code=400)

        callback_url = f"{BASE_URL}/api/payment/callback"
        result = await create_payment(
            amount=plan.price_monthly,
            description=f"اشتراک {plan.name_fa} - ماهانه",
            callback_url=callback_url,
        )

        if result.get('status') != 'ok':
            return JSONResponse({'detail': result.get('error', 'payment failed')}, status_code=result.get('status', 500))

        payment = Payment(
            user_id=uid,
            amount=plan.price_monthly,
            authority=result['authority'],
            status='pending',
            payment_type='subscription',
            reference_id=str(plan.id),
        )
        session.add(payment)
        await session.commit()

    return JSONResponse({
        'authority': result['authority'],
        'url': result['url'],
        'amount': plan.price_monthly,
        'plan': plan.name_en,
        'plan_fa': plan.name_fa,
    })


class CreditPackageCheckout(BaseModel):
    package_id: str


@app.post('/credit-package/checkout')
async def credit_package_checkout(request: Request, payload: CreditPackageCheckout) -> JSONResponse:
    """Auth required: create ZarinPal payment for a credit package."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        pkg_res = await session.execute(
            select(CreditPackage).where(CreditPackage.id == payload.package_id, CreditPackage.active == True)
        )
        pkg = pkg_res.scalar_one_or_none()
        if not pkg:
            return JSONResponse({'detail': 'package not found'}, status_code=404)

        price = pkg.total_credits  # total_credits = price in Toman
        if price <= 0:
            return JSONResponse({'detail': 'invalid package price'}, status_code=400)

        callback_url = f"{BASE_URL}/api/payment/callback"
        result = await create_payment(
            amount=price,
            description=f"بسته اعتباری {pkg.name_fa} ({pkg.total_credits:,} توکن)",
            callback_url=callback_url,
        )

        if result.get('status') != 'ok':
            return JSONResponse({'detail': result.get('error', 'payment failed')}, status_code=result.get('status', 500))

        payment = Payment(
            user_id=uid,
            amount=price,
            authority=result['authority'],
            status='pending',
            payment_type='credit_package',
            reference_id=str(pkg.id),
        )
        session.add(payment)
        await session.commit()

    return JSONResponse({
        'authority': result['authority'],
        'url': result['url'],
        'amount': price,
        'package': pkg.name_en,
        'total_credits': pkg.total_credits,
    })


# ═══════════════════════════════════════
# WebSocket for real-time notifications
# ═══════════════════════════════════════

import json
import asyncio as aio

_ws_clients: dict[int, list[WebSocket]] = {}


# ═══════════════════════════════════════
# Scheduled Tasks API
# ═══════════════════════════════════════

class ScheduledTaskCreate(BaseModel):
    title: str
    description: str = ''
    prompt: str
    model: str = 'mimo-v2.5'
    cron_expression: str = '0 9 * * *'
    delivery_channel: str = 'dashboard'


class ScheduledTaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    prompt: str | None = None
    model: str | None = None
    cron_expression: str | None = None
    is_active: bool | None = None
    delivery_channel: str | None = None


@app.get('/tasks')
async def list_tasks(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.user_id == uid).order_by(ScheduledTask.created_at.desc())
        )
        tasks = res.scalars().all()
        return JSONResponse([{
            'id': t.id, 'title': t.title, 'description': t.description,
            'prompt': t.prompt, 'model': t.model, 'cron_expression': t.cron_expression,
            'is_active': t.is_active, 'last_run_at': t.last_run_at.isoformat() if t.last_run_at else None,
            'next_run_at': t.next_run_at.isoformat() if t.next_run_at else None,
            'run_count': t.run_count, 'last_result': t.last_result,
            'delivery_channel': t.delivery_channel,
            'created_at': t.created_at.isoformat() if t.created_at else None,
            'updated_at': t.updated_at.isoformat() if t.updated_at else None,
        } for t in tasks])


@app.post('/tasks')
async def create_task(request: Request, payload: ScheduledTaskCreate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    async with async_session() as session:
        task = ScheduledTask(
            user_id=uid,
            title=payload.title,
            description=payload.description,
            prompt=payload.prompt,
            model=payload.model,
            cron_expression=payload.cron_expression,
            delivery_channel=payload.delivery_channel,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return JSONResponse({
            'id': task.id, 'title': task.title, 'description': task.description,
            'prompt': task.prompt, 'model': task.model, 'cron_expression': task.cron_expression,
            'is_active': task.is_active, 'run_count': task.run_count,
            'delivery_channel': task.delivery_channel,
            'created_at': task.created_at.isoformat() if task.created_at else None,
        })


@app.put('/tasks/{task_id}')
async def update_task(request: Request, task_id: int, payload: ScheduledTaskUpdate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.user_id == uid)
        )
        task = res.scalar_one_or_none()
        if not task:
            return JSONResponse({'detail': 'task not found'}, status_code=404)
        update_data = payload.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            setattr(task, key, val)
        task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
        await session.refresh(task)
        return JSONResponse({
            'id': task.id, 'title': task.title, 'description': task.description,
            'prompt': task.prompt, 'model': task.model, 'cron_expression': task.cron_expression,
            'is_active': task.is_active, 'run_count': task.run_count,
            'delivery_channel': task.delivery_channel,
        })


@app.delete('/tasks/{task_id}')
async def delete_task(request: Request, task_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.user_id == uid)
        )
        task = res.scalar_one_or_none()
        if not task:
            return JSONResponse({'detail': 'task not found'}, status_code=404)
        await session.delete(task)
        await session.commit()
        return JSONResponse({'status': 'deleted'})


@app.post('/tasks/{task_id}/toggle')
async def toggle_task(request: Request, task_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.user_id == uid)
        )
        task = res.scalar_one_or_none()
        if not task:
            return JSONResponse({'detail': 'task not found'}, status_code=404)
        task.is_active = not task.is_active
        task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
        return JSONResponse({'id': task.id, 'is_active': task.is_active})


@app.post('/tasks/{task_id}/run')
async def run_task(request: Request, task_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.user_id == uid)
        )
        task = res.scalar_one_or_none()
        if not task:
            return JSONResponse({'detail': 'task not found'}, status_code=404)

        # Create execution record
        execution = TaskExecution(
            task_id=task.id,
            user_id=uid,
            status='running',
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)

    # Call LiteLLM outside the session to avoid long-held connections
    result_text = None
    error_text = None
    tokens_used = 0
    status = 'completed'
    try:
        chat_payload = {
            'model': task.model,
            'messages': [{'role': 'user', 'content': task.prompt}],
            'stream': False,
        }
        r = await _http.post(f"{LITELLM_HOST}/v1/chat/completions", json=chat_payload, headers={'Accept': 'application/json'})
        if r.status_code == 200:
            data = r.json()
            result_text = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            tokens_used = data.get('usage', {}).get('total_tokens', 0)
        else:
            status = 'failed'
            error_text = f"HTTP {r.status_code}: {r.text[:500]}"
    except Exception as e:
        status = 'failed'
        error_text = str(e)[:500]

    completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    # Update execution record
    async with async_session() as session:
        res = await session.execute(select(TaskExecution).where(TaskExecution.id == execution.id))
        exec_rec = res.scalar_one()
        exec_rec.status = status
        exec_rec.result = result_text
        exec_rec.error = error_text
        exec_rec.tokens_used = tokens_used
        exec_rec.completed_at = completed_at
        await session.commit()

        # Update task stats
        res2 = await session.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
        task_rec = res2.scalar_one()
        task_rec.last_run_at = completed_at
        task_rec.run_count += 1
        task_rec.last_result = result_text
        task_rec.updated_at = completed_at
        await session.commit()

    return JSONResponse({
        'execution_id': execution.id,
        'status': status,
        'result': result_text,
        'error': error_text,
        'tokens_used': tokens_used,
    })


@app.get('/tasks/{task_id}/executions')
async def list_task_executions(request: Request, task_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    async with async_session() as session:
        # Verify task belongs to user
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.user_id == uid)
        )
        task = res.scalar_one_or_none()
        if not task:
            return JSONResponse({'detail': 'task not found'}, status_code=404)
        res2 = await session.execute(
            select(TaskExecution).where(TaskExecution.task_id == task_id).order_by(TaskExecution.created_at.desc())
        )
        execs = res2.scalars().all()
        return JSONResponse([{
            'id': e.id, 'task_id': e.task_id, 'status': e.status,
            'result': e.result, 'tokens_used': e.tokens_used,
            'error': e.error,
            'started_at': e.started_at.isoformat() if e.started_at else None,
            'completed_at': e.completed_at.isoformat() if e.completed_at else None,
            'created_at': e.created_at.isoformat() if e.created_at else None,
        } for e in execs])


# ═══════════════════════════════════════════════════════════════════
# Smart Mode — auto-selects the cheapest capable model
# ═══════════════════════════════════════════════════════════════════

# Regex patterns compiled once

_GREETING_PATTERNS = _re.compile(
    r'^[\s]*(hi|hello|hey|salam|سلام|سلامت|สวัสดี|hallo|ciao|bonjour|hola|'
    r'good\s*(morning|afternoon|evening|night)|สวัสดี|merhaba|selam|hej|'
    r'howdy|yo|how\s*are\s*you|what\'?s\s*up|sup|khubi|chetori|khobi)',
    _re.IGNORECASE,
)

_CODE_KEYWORDS = _re.compile(
    r'(```|def\s|class\s|function\s|import\s|from\s+\w+\s+import|'
    r'async\s+def|const\s|let\s|var\s|=>|return\s|if\s*\(|for\s*\(|'
    r'while\s*\(|try\s*{|except\s|raise\s|throw\s|new\s+\w+|'
    r'print\(|console\.log|SELECT\s|INSERT\s|UPDATE\s|DELETE\s)',
    _re.IGNORECASE,
)

_REASONING_KEYWORDS = _re.compile(
    r'(analyze|analyse|explain|compare|contrast|evaluate|reason|prove|'
    r'derive|derive|optimize|strategy|trade-?off|pros?\s*and\s*cons?|'
    r'logic|argument|hypothesis|theorem|algorithm|proof|'
    r'چرا|چگونه|تحلیل|مقایسه|ارزیابی|استراتژی)',
    _re.IGNORECASE,
)

_Creative_KEYWORDS = _re.compile(
    r'(write\s+a\s+(story|poem|essay|song|novel|article)|'
    r'creative|imagine|fiction|creative\s+writing|'
    r'داستان|شعر|خلاقیت)',
    _re.IGNORECASE,
)

# Model tiers: (provider_model_id, provider)
_FREE_MODELS = [
    ('qwen3-coder-free', 'openrouter'),
    ('hermes-3-405b-free', 'openrouter'),
]

_CODING_MODELS = [
    ('qwen3-coder-free', 'openrouter'),
    ('mimo-v2.5', 'bynara2'),
]

_REASONING_MODELS = [
    ('mimo-v2.5', 'bynara2'),
    ('mimo-v2.5-pro', 'bynara2'),
]

_CREATIVE_MODELS = [
    ('mimo-v2.5', 'bynara2'),
    ('mimo-v2.5-pro', 'bynara2'),
]

_DEFAULT_MODEL = ('mimo-v2.5', 'bynara2')
_ADVANCED_MODEL = ('mimo-v2.5-pro', 'bynara2')
_PREMIUM_MODEL = ('gpt-5.6-luna', 'bynara2')


def _analyze_message(text: str) -> str:
    """Classify a message into: greeting, code, reasoning, creative, simple, complex."""
    if not text or not text.strip():
        return 'simple'
    if _GREETING_PATTERNS.search(text):
        return 'greeting'
    if _CODE_KEYWORDS.search(text):
        return 'code'
    if _REASONING_KEYWORDS.search(text):
        return 'reasoning'
    if _Creative_KEYWORDS.search(text):
        return 'creative'
    # Long messages with multiple sentences are likely complex
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    if len(text) > 500 or len(sentences) > 4:
        return 'complex'
    if len(text) > 200:
        return 'medium'
    return 'simple'


async def _get_user_balance(uid: int) -> int:
    """Return the user's current wallet balance (IRT)."""
    if async_session is None:
        return 0
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text(
                    'SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'
                ),
                {'uid': uid},
            )
            row = res.fetchone()
            return int(row.balance) if row else 0
    except Exception:
        return 0


async def _get_user_plan(uid: int) -> str:
    """Return the user's active subscription plan, or 'free'."""
    if async_session is None:
        return 'free'
    try:
        async with async_session() as session:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            res = await session.execute(
                select(Subscription)
                .where(
                    Subscription.user_id == uid,
                    Subscription.status == 'active',
                    (Subscription.ends_at.is_(None)) | (Subscription.ends_at > now),
                )
                .order_by(Subscription.created_at.desc())
                .limit(1)
            )
            sub = res.scalar_one_or_none()
            return sub.plan if sub else 'free'
    except Exception:
        return 'free'


def _select_smart_model(
    category: str,
    balance: int,
    plan: str,
) -> tuple[str, str]:
    """Pick (provider_model_id, provider) based on message category, balance, and plan."""

    # Low balance: force free model
    if balance < 10000:
        return _FREE_MODELS[0]

    # Greeting / simple messages: free model
    if category in ('greeting', 'simple'):
        return _FREE_MODELS[0]

    # Premium plans get advanced models for complex tasks
    if plan in ('pro', 'enterprise', 'unlimited'):
        if category == 'complex':
            return _ADVANCED_MODEL
        if category == 'reasoning':
            return _REASONING_MODELS[1]  # mimo-v2.5-pro
        if category == 'code':
            return _CODING_MODELS[0]  # free code model
        if category == 'creative':
            return _CREATIVE_MODELS[1]  # mimo-v2.5-pro
        return _DEFAULT_MODEL

    # Free/standard plans
    if category == 'complex':
        return _REASONING_MODELS[0]  # mimo-v2.5
    if category == 'reasoning':
        return _REASONING_MODELS[0]  # mimo-v2.5
    if category == 'code':
        return _CODING_MODELS[0]  # qwen3-coder-free
    if category == 'creative':
        return _CREATIVE_MODELS[0]  # mimo-v2.5
    if category == 'medium':
        return _DEFAULT_MODEL  # mimo-v2.5

    return _DEFAULT_MODEL


@app.post('/v1/smart-chat')
async def smart_chat(request: Request, payload: dict[str, Any]) -> Response:
    """Smart Mode: auto-selects the cheapest model capable of handling the request."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)

    # Quota pre-check
    quota_err = await _check_quota_pre(uid)
    if quota_err is not None:
        return quota_err

    # Extract last user message
    messages = payload.get('messages', [])
    last_user_msg = ''
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get('role') == 'user':
            last_user_msg = msg.get('content', '')
            if isinstance(last_user_msg, list):
                # Handle multimodal content (list of text/image parts)
                parts = []
                for part in last_user_msg:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        parts.append(part.get('text', ''))
                last_user_msg = ' '.join(parts)
            break

    # Analyze and select model
    category = _analyze_message(last_user_msg)
    balance = await _get_user_balance(uid)
    plan = await _get_user_plan(uid)

    # Respect explicit user model choice sent via the X-Smart-Model header.
    # The frontend always forwards the user's selected model there; if present
    # (and not the literal 'auto'), honor it instead of auto-switching on the
    # message category — otherwise the user sees a *different* model answer.
    original_model = payload.get('model', '')
    force_model = request.headers.get('X-Smart-Model', '').strip()
    if force_model and force_model.lower() != 'auto':
        if '/' in force_model:
            selected_provider, selected_model = force_model.split('/', 1)
        else:
            selected_model = force_model
            selected_provider = 'bynara2'
    else:
        selected_model, selected_provider = _select_smart_model(category, balance, plan)

    # Override model in payload
    payload['model'] = selected_model

    # Memory injection (same as regular chat)
    memories = await _get_user_memories(uid)
    if memories:
        memory_block = '\n'.join(f'- {m}' for m in memories)
        memory_msg = {'role': 'system', 'content': f'[User Memories]\n{memory_block}'}
        insert_idx = 0
        for i, msg in enumerate(messages):
            if isinstance(msg, dict) and msg.get('role') == 'system':
                insert_idx = i + 1
                break
        messages.insert(insert_idx, memory_msg)
        payload['messages'] = messages

    stream = payload.get('stream', False)
    if stream:
        return await _smart_chat_stream(payload, request, selected_model, category)

    try:
        r = await _http.post(
                f'{LITELLM_HOST}/v1/chat/completions',
                json=payload,
                headers={'Accept': 'application/json'},
            )
        if r.status_code == 200:
            await _track_usage(request, payload, r.json())
            response_data = r.json()
            resp = Response(
                content=r.content, status_code=200, media_type='application/json'
            )
        else:
            response_data = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
            resp = Response(
                content=r.content, status_code=r.status_code, media_type='application/json'
            )
            # Add smart model info header
            resp.headers['X-Smart-Model'] = selected_model
            resp.headers['X-Smart-Category'] = category
            resp.headers['X-Smart-Provider'] = selected_provider
            if original_model and original_model != selected_model:
                resp.headers['X-Smart-Original-Model'] = original_model
            return resp
    except Exception as e:
        return JSONResponse(
            {'error': {'message': f'upstream unavailable: {e}', 'type': 'gateway_error'}},
            status_code=502,
        )


async def _smart_chat_stream(
    payload: dict[str, Any],
    request: Request,
    selected_model: str,
    category: str,
):
    """Stream smart chat completion via SSE, collecting usage for billing."""
    uid = await _get_user_id(request)

    # Memory injection for streaming (idempotent)
    if uid and not any(
        isinstance(m, dict) and m.get('content', '').startswith('[User Memories]')
        for m in payload.get('messages', [])
    ):
        memories = await _get_user_memories(uid)
        if memories:
            memory_block = '\n'.join(f'- {m}' for m in memories)
            memory_msg = {'role': 'system', 'content': f'[User Memories]\n{memory_block}'}
            messages = payload.get('messages', [])
            insert_idx = 0
            for i, msg in enumerate(messages):
                if isinstance(msg, dict) and msg.get('role') == 'system':
                    insert_idx = i + 1
                    break
            messages.insert(insert_idx, memory_msg)
            payload['messages'] = messages

    async def event_stream():
        usage_data = None
        try:
            payload['stream'] = True
            payload.setdefault('stream_options', {})
            if isinstance(payload['stream_options'], dict):
                payload['stream_options']['include_usage'] = True
            async with _http.stream(
                'POST',
                f'{LITELLM_HOST}/v1/chat/completions',
                json=payload,
                headers={'Accept': 'text/event-stream'},
            ) as r:
                # Send smart model info as first event
                yield f'data: {json.dumps({"type": "smart_info", "model": selected_model, "category": category})}\n\n'
                async for line in r.aiter_lines():
                    if line:
                        stripped = line.strip()
                        if stripped.startswith('data:'):
                            data_str = stripped[5:].strip()
                            if data_str == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data_str)
                                if isinstance(chunk.get('usage'), dict) and chunk['usage']:
                                    usage_data = chunk['usage']
                            except (json.JSONDecodeError, ValueError):
                                pass
                        yield f'{line}\n\n'
        except Exception as e:
            yield f'data: {{"error": "upstream unavailable: {e}"}}\n\n'
        finally:
            if uid and usage_data and async_session is not None:
                try:
                    await _bill_stream_usage(uid, payload, usage_data)
                except Exception:
                    pass

    response = StreamingResponse(event_stream(), media_type='text/event-stream')
    response.headers['X-Smart-Model'] = selected_model
    response.headers['X-Smart-Category'] = category
    return response


# ═══════════════════════════════════════════════════════════════════
# Conversation Export
# ═══════════════════════════════════════════════════════════════════

@app.get('/conversations/{conv_id}/export')
async def export_conversation(
    request: Request, conv_id: int, format: str = 'json'
) -> Response:
    """Export a conversation in JSON, Markdown, or plain text format."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            Conversation.__table__.select().where(
                Conversation.id == conv_id, Conversation.user_id == uid
            )
        )
        conv = res.fetchone()
        if not conv:
            return JSONResponse({'detail': 'not found'}, status_code=404)

    messages = conv.messages or []
    title = conv.title or 'Conversation'
    created = conv.created_at.isoformat() if conv.created_at else ''
    model = conv.model or ''

    if format == 'json':
        data = {
            'id': conv.id,
            'title': title,
            'model': model,
            'created_at': created,
            'messages': messages,
        }
        return JSONResponse(jsonable_encoder(data))

    elif format == 'markdown':
        lines = [f'# {title}', '']
        if model:
            lines.append(f'**Model:** {model}')
        if created:
            lines.append(f'**Created:** {created}')
        lines.append('')
        lines.append('---')
        lines.append('')
        for msg in messages:
            role = msg.get('role', 'unknown') if isinstance(msg, dict) else 'unknown'
            content = msg.get('content', '') if isinstance(msg, dict) else str(msg)
            if isinstance(content, list):
                # Multimodal: extract text parts
                parts = []
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        parts.append(part.get('text', ''))
                content = '\n'.join(parts)
            role_label = {'user': '🧑 User', 'assistant': '🤖 Assistant', 'system': '⚙️ System'}.get(role, role.title())
            lines.append(f'## {role_label}')
            lines.append('')
            # Check if content has code blocks
            if '```' in content:
                lines.append(content)
            else:
                lines.append(content)
            lines.append('')
            lines.append('---')
            lines.append('')
        md_content = '\n'.join(lines)
        return Response(
            content=md_content,
            media_type='text/markdown; charset=utf-8',
            headers={
                'Content-Disposition': f'attachment; filename="conversation-{conv_id}.md"',
            },
        )

    elif format == 'text':
        lines = [f'Title: {title}', '']
        if model:
            lines.append(f'Model: {model}')
        if created:
            lines.append(f'Created: {created}')
        lines.append('')
        for msg in messages:
            role = msg.get('role', 'unknown') if isinstance(msg, dict) else 'unknown'
            content = msg.get('content', '') if isinstance(msg, dict) else str(msg)
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        parts.append(part.get('text', ''))
                content = '\n'.join(parts)
            role_label = {'user': 'User', 'assistant': 'Assistant', 'system': 'System'}.get(role, role.title())
            lines.append(f'[{role_label}]')
            lines.append(content)
            lines.append('')
        text_content = '\n'.join(lines)
        return Response(
            content=text_content,
            media_type='text/plain; charset=utf-8',
            headers={
                'Content-Disposition': f'attachment; filename="conversation-{conv_id}.txt"',
            },
        )

    else:
        return JSONResponse(
            {'detail': f'unsupported format: {format}. Use json, markdown, or text.'},
            status_code=400,
        )



@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    """Real-time connection for notifications and usage updates"""
    await ws.accept()

    # Authenticate via token query param
    token = ws.query_params.get('token', '')
    uid = _get_session_user_id(token) if token else None

    if not uid:
        await ws.send_json({'type': 'error', 'message': 'unauthorized'})
        await ws.close()
        return

    # Register client
    _ws_clients.setdefault(uid, []).append(ws)

    try:
        while True:
            # Keep connection alive, wait for client messages
            try:
                data = await aio.wait_for(ws.receive_text(), timeout=30)
                # Client can send ping
                if data == 'ping':
                    await ws.send_json({'type': 'pong'})
            except aio.TimeoutError:
                # Send heartbeat
                try:
                    await ws.send_json({'type': 'heartbeat'})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        clients = _ws_clients.get(uid, [])
        if ws in clients:
            clients.remove(ws)
        if not clients:
            _ws_clients.pop(uid, None)


async def notify_user(uid: int, message: dict):
    """Send a notification to all WebSocket connections of a user"""
    for ws in _ws_clients.get(uid, []):
        try:
            await ws.send_json(message)
        except Exception:
            pass
