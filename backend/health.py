"""
Health check and root endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from database import engine, rds, _http, LITELLM_HOST, _start, HealthResponse
from dependencies import admin_required

router = APIRouter()


@router.get('/')
async def root() -> dict[str, str]:
    return {'service': 'Persian AI Gateway', 'docs': '/docs'}


@router.get('/health/live')
async def health_live() -> dict[str, str]:
    return {'status': 'ok'}


@router.get('/health/ready')
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
        await rds.ping()
    except Exception:
        redis_ok = False
    if db_ok and redis_ok:
        return JSONResponse({'status': 'ok'}, status_code=200)
    return JSONResponse({'status': 'unavailable', 'db': 'ok' if db_ok else 'down', 'redis': 'ok' if redis_ok else 'down'}, status_code=503)


@router.get('/health')
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
        await rds.ping()
    except Exception:
        redis_status = 'down'
    return HealthResponse(status='ok', uptime=(datetime.now(timezone.utc) - _start).total_seconds() if _start else 0, db=db_status, redis=redis_status)


@router.get('/health/detailed')
async def health_detailed(request: Request) -> JSONResponse:
    """Detailed health check with metrics"""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    import psutil
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    from middleware.compression import get_compression_stats
    compression = get_compression_stats()

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
        await rds.ping()
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
        'compression': compression,
    })
