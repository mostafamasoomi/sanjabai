"""
Admin model catalog: live pricing rows and per-model availability/probe control.

Source of truth for chat billing is the ``model_catalog`` table; the legacy
``Pricing`` version history is read through :func:`get_active_price`.
"""
from __future__ import annotations

from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select

from database import async_session, rds
from models import Pricing
from dependencies import admin_required, _write_audit_log

router = APIRouter()

# ── Pricing admin ───────────────────────────────────────────────

@router.get('/admin/pricing')
async def list_pricing(request: Request) -> JSONResponse:
    """List live model prices. Source of truth = model_catalog (used by chat billing)."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            "SELECT id AS model, display_name, input_per_million, output_per_million, currency, "
            "usd_input_per_million, usd_output_per_million, availability "
            "FROM model_catalog ORDER BY display_name"
        ))
        rows = []
        for r in res.fetchall():
            rows.append({
                'model': r.model,
                'display_name': r.display_name,
                'input_per_million': int(r.input_per_million or 0),
                'output_per_million': int(r.output_per_million or 0),
                'currency': r.currency,
                'usd_input_per_million': r.usd_input_per_million,
                'usd_output_per_million': r.usd_output_per_million,
                'availability': r.availability,
            })
    return JSONResponse(jsonable_encoder(rows))


async def get_active_price(session, model_id: str) -> "Pricing | None":
    """Return the currently-active pricing version for *model_id*."""
    res = await session.execute(
        select(Pricing)
        .where(Pricing.model == model_id, Pricing.effective_to.is_(None))
        .order_by(Pricing.effective_from.desc(), Pricing.price_version.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


@router.post('/admin/pricing')
async def set_pricing(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Update live prices on model_catalog (the table chat billing actually reads)."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    model = payload.get('model')
    if not model:
        return JSONResponse({'detail': 'مدل الزامی است'}, status_code=400)
    try:
        input_pm = int(payload.get('input_per_million', 0))
        output_pm = int(payload.get('output_per_million', 0))
    except (TypeError, ValueError):
        return JSONResponse({'detail': 'قیمتها باید عدد صحیح باشند'}, status_code=400)
    currency = payload.get('currency', 'IRT')
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            "UPDATE model_catalog SET input_per_million=:inp, output_per_million=:out, "
            "currency=:cur, updated_at=now() WHERE id=:m"
        ), {'inp': input_pm, 'out': output_pm, 'cur': currency, 'm': model})
        if res.rowcount == 0:
            return JSONResponse({'detail': 'مدل در کاتالوگ یافت نشد'}, status_code=404)
        await session.commit()
    await _write_audit_log('admin.pricing.set', target_type='model_catalog', target_id=model,
                           details={'input_per_million': input_pm, 'output_per_million': output_pm})
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'updated', 'model': model})


@router.post('/admin/models/{model_id}/toggle')
async def toggle_model(request: Request, model_id: str) -> JSONResponse:
    """Admin: flip a model between 'available' and 'disabled'.

    Same effect as the legacy admin/app.py toggle endpoints, exposed here so
    the React admin panel (the one actually in front of admins day-to-day)
    doesn't need the separate Jinja admin app just to kill a broken model.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            'SELECT availability FROM model_catalog WHERE id = :id'
        ), {'id': model_id})
        row = res.fetchone()
        if row is None:
            return JSONResponse({'detail': 'مدل در کاتالوگ یافت نشد'}, status_code=404)
        new_avail = 'disabled' if row.availability == 'available' else 'available'
        await session.execute(sqlalchemy.text(
            'UPDATE model_catalog SET availability = :a, updated_at = now() WHERE id = :id'
        ), {'a': new_avail, 'id': model_id})
        await session.commit()
    await _write_audit_log('admin.model.toggle', target_type='model_catalog', target_id=model_id,
                           details={'availability': new_avail})
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'ok', 'model': model_id, 'availability': new_avail})


@router.post('/admin/models/{model_id}/test')
async def test_model(request: Request, model_id: str) -> JSONResponse:
    """Admin: send a minimal live probe to a model and report the result.

    Reuses providers.probe_model (the same probe model_health.py runs on a
    schedule) so "test now" in the admin panel and the status page's
    background health checks agree on what "working" means.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    from chat import _resolve_provider
    from providers import probe_model
    provider = await _resolve_provider(model_id)
    result = await probe_model(provider, model_id)
    await _write_audit_log('admin.model.test', target_type='model_catalog', target_id=model_id,
                           details={'ok': result.ok, 'latency_ms': result.latency_ms, 'error': result.error})
    return JSONResponse({
        'model': model_id,
        'upstream': provider.name,
        'ok': result.ok,
        'latency_ms': result.latency_ms,
        'error': result.error,
        'status_code': result.status_code,
    })
