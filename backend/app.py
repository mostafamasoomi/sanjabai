from __future__ import annotations
import os, hashlib, secrets, base64, hmac
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
import csv
import io
from pydantic import BaseModel
import httpx
import redis
import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from dotenv import load_dotenv

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

class Ledger(Base):
    __tablename__ = 'ledger'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    amount: Mapped[int]
    balance_after: Mapped[int]
    reason: Mapped[str]
    meta: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, nullable=True)
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
    __tablename__ = 'pricing'
    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(unique=True)
    input_per_million: Mapped[int]
    output_per_million: Mapped[int]
    currency: Mapped[str] = mapped_column(default='IRT')
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

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
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)

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
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class HealthResponse(BaseModel):
    status: str
    uptime: float | None = None
    db: str
    redis: str

_start: datetime | None = None

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global engine, async_session, _start
    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    from migrate import migrate
    await migrate(engine)
    _start = datetime.now(timezone.utc)
    yield
    await engine.dispose()

app = FastAPI(title='Persian AI Gateway', version='0.1.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
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
    token = request.headers.get('x-admin-token') or request.headers.get('authorization', '').removeprefix('Bearer ')
    return bool(ADMIN_TOKEN) and bool(token) and hmac.compare_digest(token, ADMIN_TOKEN)

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
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f'{LITELLM_HOST}/health')
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
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"{LITELLM_HOST}/v1/models")
            if r.status_code == 200:
                models = r.json().get('data', [])
    except Exception:
        pass
    return {'object': 'list', 'data': models}

@app.post('/v1/chat/completions')
async def chat(request: Request, payload: dict[str, Any]) -> Response:
    stream = payload.get('stream', False)
    if stream:
        return await _chat_stream(payload, request)
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(f"{LITELLM_HOST}/v1/chat/completions", json=payload, headers={'Accept': 'application/json'})
            if r.status_code == 200:
                # Track usage
                await _track_usage(request, payload, r.json())
                return Response(content=r.content, status_code=200, media_type='application/json')
            return Response(content=r.content, status_code=r.status_code, media_type='application/json')
    except Exception as e:
        return JSONResponse({'error': {'message': f'upstream unavailable: {e}', 'type': 'gateway_error'}}, status_code=502)

async def _chat_stream(payload: dict[str, Any], request: Request):
    """Stream chat completion via SSE"""
    async def event_stream():
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                payload['stream'] = True
                async with client.stream('POST', f"{LITELLM_HOST}/v1/chat/completions", json=payload, headers={'Accept': 'text/event-stream'}) as r:
                    async for line in r.aiter_lines():
                        if line:
                            yield f"{line}\n\n"
        except Exception as e:
            yield f'data: {{"error": "upstream unavailable: {e}"}}\n\n'
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
            # Deduct from wallet (1 token = 0.001 toman rough estimate)
            model = payload.get('model', '')
            cost = max(1, total_tokens // 1000)  # 1 toman per 1000 tokens
            res = await session.execute(
                sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
                {'uid': uid}
            )
            row = res.fetchone()
            current = row.balance if row else 0
            if current >= cost:
                entry = Ledger(user_id=uid, amount=-cost, balance_after=current - cost, reason=f'مصرف {model}')
                session.add(entry)
            await session.commit()
    except Exception:
        pass

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
        res = await session.execute(Pricing.__table__.select())
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))

@app.post('/admin/pricing')
async def set_pricing(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not admin_required(request):
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    model = payload.get('model')
    if not model:
        return JSONResponse({'detail': 'model required'}, status_code=400)
    async with async_session() as session:
        row = await session.get(Pricing, model)
        if row:
            row.input_per_million = payload.get('input_per_million', row.input_per_million)
            row.output_per_million = payload.get('output_per_million', row.output_per_million)
            row.currency = payload.get('currency', row.currency)
            row.updated_at = datetime.now(timezone.utc)
        else:
            row = Pricing(model=model, input_per_million=payload.get('input_per_million', 0), output_per_million=payload.get('output_per_million', 0), currency=payload.get('currency', 'IRT'))
            session.add(row)
        await session.commit()
    return JSONResponse({'status': 'updated', 'model': model})

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
    token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if not token:
        return None
    # Check session token first
    uid = rds.get(f'session:{token}')
    if uid:
        rds.expire(f'session:{token}', SESSION_TTL)
        return int(uid)
    # Check API key
    if token.startswith('sk-'):
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(
                    ApiKey.__table__.select().where(ApiKey.key_hash == key_hash, ApiKey.active == True)
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
        token = _gen_token()
        rds.setex(f'session:{token}', SESSION_TTL, str(user.id))
        return JSONResponse({'token': token, 'user': {'id': user.id, 'email': user.email}})

@app.post('/auth/login')
async def login(payload: AuthLogin) -> JSONResponse:
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.email == payload.email))
        user = res.fetchone()
        if not user or not user.password_hash or not _verify_password(payload.password, user.password_hash):
            return JSONResponse({'detail': 'invalid email or password'}, status_code=401)
        token = _gen_token()
        rds.setex(f'session:{token}', SESSION_TTL, str(user.id))
        return JSONResponse({'token': token, 'user': {'id': user.id, 'email': user.email}})

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
    token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if token:
        rds.delete(f'session:{token}')
    return JSONResponse({'status': 'ok'})

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

    return JSONResponse({'status': 'ok'})


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
        print(f'[RESET] Password reset for {payload.email}: token={reset_token}')

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

from payment import create_payment, verify_payment, PaymentRequest

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
    """Zarinpal redirects here after payment"""
    authority = request.query_params.get('Authority')
    status = request.query_params.get('Status', '')

    if status != 'OK' or not authority:
        return JSONResponse({'detail': 'payment cancelled or failed'}, status_code=400)

    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    async with async_session() as session:
        # ATOMIC: lock the payment row to prevent double-credit race
        res = await session.execute(
            sqlalchemy.text(
                'SELECT * FROM payments WHERE authority = :auth AND status = :st FOR UPDATE'
            ),
            {'auth': authority, 'st': 'pending'}
        )
        payment = res.fetchone()
        if not payment:
            return JSONResponse({'detail': 'payment not found or already processed'}, status_code=404)

        # Verify with Zarinpal
        result = await verify_payment(payment.amount, authority)

        if result.get('status') != 'verified':
            await session.execute(
                sqlalchemy.text('UPDATE payments SET status = :st, verified_at = :now WHERE id = :id'),
                {'st': 'failed', 'now': datetime.now(timezone.utc).replace(tzinfo=None), 'id': payment.id}
            )
            await session.commit()
            return JSONResponse({'detail': result.get('error', 'verification failed')}, status_code=400)

        # Mark as verified (within same transaction)
        await session.execute(
            sqlalchemy.text(
                'UPDATE payments SET status = :st, ref_id = :ref, verified_at = :now WHERE id = :id'
            ),
            {'st': 'verified', 'ref': result['ref_id'], 'now': datetime.now(timezone.utc).replace(tzinfo=None), 'id': payment.id}
        )

        # Credit wallet — SAME transaction, atomic
        balance_res = await session.execute(
            sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
            {'uid': payment.user_id}
        )
        row = balance_res.fetchone()
        current = row.balance if row else 0
        new_balance = current + payment.amount

        entry = Ledger(
            user_id=payment.user_id,
            amount=payment.amount,
            balance_after=new_balance,
            reason=f'شارژ حساب — Zarinpal ref: {result["ref_id"]}',
        )
        session.add(entry)
        await session.commit()

    # Redirect to frontend wallet page
    return JSONResponse({
        'status': 'ok',
        'ref_id': result['ref_id'],
        'amount': payment.amount,
        'redirect': f'{BASE_URL}/wallet?payment=success',
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

@app.post('/api-keys')
async def create_api_key(request: Request, payload: ApiKeyCreate) -> JSONResponse:
    """Generate a new API key"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'unauthorized'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'db not initialized'}, status_code=500)

    raw_key = f'sk-{secrets.token_urlsafe(32)}'
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    async with async_session() as session:
        key = ApiKey(user_id=uid, name=payload.name, key_hash=key_hash, key_prefix='sk-')
        session.add(key)
        await session.commit()
        await session.refresh(key)

    return JSONResponse({
        'id': key.id,
        'name': key.name,
        'key': raw_key,
        'prefix': 'sk-',
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
                'active': r.active,
                'last_used': r.last_used.isoformat() if r.last_used else None,
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
            {'active': False}
        )
        await session.commit()
    return JSONResponse({'status': 'revoked'})

# ═══════════════════════════════════════
# WebSocket for real-time notifications
# ═══════════════════════════════════════

import json
import asyncio as aio

_ws_clients: dict[int, list[WebSocket]] = {}


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    """Real-time connection for notifications and usage updates"""
    await ws.accept()

    # Authenticate via token query param
    token = ws.query_params.get('token', '')
    uid = None
    if token:
        uid = rds.get(f'session:{token}')
        if uid:
            uid = int(uid)

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
        _ws_clients.get(uid, []).remove(ws)


async def notify_user(uid: int, message: dict):
    """Send a notification to all WebSocket connections of a user"""
    for ws in _ws_clients.get(uid, []):
        try:
            await ws.send_json(message)
        except Exception:
            pass
