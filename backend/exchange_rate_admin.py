"""
Admin visibility into the USD->IRT exchange rate that every displayed price
depends on: current rate, which resolver tier produced it (source), and when
it was last refreshed.

Mirrors admin_catalog.py's pattern exactly (same `admin_required` dependency,
same JSONResponse-with-401 style) -- see that file for the house style this
follows.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import rds
from dependencies import admin_required, _write_audit_log

router = APIRouter()


@router.get('/admin/exchange-rate')
async def get_exchange_rate_admin(request: Request) -> JSONResponse:
    """Current USD->IRT rate, its source, and when it was last fetched."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    from content import get_exchange_rate_meta
    meta = await get_exchange_rate_meta()
    return JSONResponse(jsonable_encoder(meta))


@router.post('/admin/exchange-rate/refresh')
async def refresh_exchange_rate_admin(request: Request) -> JSONResponse:
    """Bust the cached rate and re-resolve it immediately.

    Deletes the same Redis key `_get_exchange_rate()` reads/writes
    (`content.EXCHANGE_RATE_CACHE_KEY`), so the very next read (this
    request's own call to `get_exchange_rate_meta()`) is a forced cache
    miss and re-runs the full 4-tier resolver.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    import content
    if rds:
        try:
            await rds.delete(content.EXCHANGE_RATE_CACHE_KEY)
        except Exception:
            pass

    meta = await content.get_exchange_rate_meta()
    await _write_audit_log('admin.exchange_rate.refresh', target_type='exchange_rate', target_id=None,
                            details={'source': meta.get('source')}, request=request)
    return JSONResponse(jsonable_encoder(meta))
