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
            """
            SELECT mc.id AS model, mc.display_name, mc.input_per_million, mc.output_per_million, mc.currency,
                   mc.usd_input_per_million, mc.usd_output_per_million, mc.availability, mc.provider_model_id,
                   mc.context_window, mc.max_output_tokens, mc.upstream, mc.provenance,
                   mc.last_verified_at,
                   mhs.status AS health_status, mhs.latency_p50_ms, mhs.success_rate, mhs.last_error
            FROM model_catalog mc
            LEFT JOIN model_health_state mhs ON mc.id = mhs.model_id
            ORDER BY mc.display_name
            """
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
                'provider_model_id': r.provider_model_id,
                'context_window': r.context_window,
                'max_output_tokens': r.max_output_tokens,
                'upstream': r.upstream,
                'provenance': r.provenance,
                'last_verified_at': r.last_verified_at.isoformat() if r.last_verified_at else None,
                'health': {
                    'status': r.health_status,
                    'latency_p50_ms': r.latency_p50_ms,
                    'success_rate': r.success_rate,
                    'last_error': r.last_error,
                }
            })
    return JSONResponse(jsonable_encoder(rows))

@router.put('/admin/models/{model_id}/metadata')
async def edit_model_metadata(request: Request, model_id: str, payload: dict[str, Any]) -> JSONResponse:
    """Admin: Edit model display name, description, capabilities, etc."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    updatable_fields = ['display_name', 'description', 'capabilities', 'recommended_for', 'audience', 'upstream', 'context_window', 'max_output_tokens']
    update_data = {k: v for k, v in payload.items() if k in updatable_fields}

    if not update_data:
        return JSONResponse({'detail': 'داده‌ای برای به‌روزرسانی یافت نشد'}, status_code=400)

    async with async_session() as session:
        set_clause = ', '.join(f"{k}=:{k}" for k in update_data.keys())
        res = await session.execute(
            sqlalchemy.text(
                f"UPDATE model_catalog SET {set_clause}, updated_at = now() WHERE id = :model_id"
            ),
            {**update_data, 'model_id': model_id}
        )
        if res.rowcount == 0:
             return JSONResponse({'detail': 'مدل در کاتالوگ یافت نشد'}, status_code=404)
        await session.commit()
    await _write_audit_log('admin.model.metadata_edit', target_type='model_catalog', target_id=model_id, details=update_data)
    from database import rds
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'ok', 'model': model_id, **update_data})

@router.post('/admin/models/{model_id}/approve')
async def approve_model(request: Request, model_id: str, payload: dict[str, Any]) -> JSONResponse:
    """Admin: Approve a provider-sourced model, setting its provenance and initial pricing."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    input_pm = int(payload.get('input_per_million', 0))
    output_pm = int(payload.get('output_per_million', 0))
    currency = payload.get('currency', 'IRT')

    async with async_session() as session:
        # Check if model exists and is in 'maintenance' or 'disabled' state
        res = await session.execute(sqlalchemy.text(
            "SELECT id, provenance FROM model_catalog WHERE id = :id AND (provenance = 'provider' OR availability IN ('maintenance', 'disabled'))"
        ), {'id': model_id})
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'مدل یافت نشد یا در وضعیت قابل تأیید نیست'}, status_code=404)

        # Use unified pricing service
        from services.pricing import set_model_price, invalidate_pricing_cache
        price_result = await set_model_price(
            session,
            model_id=model_id,
            input_per_million=input_pm,
            output_per_million=output_pm,
            currency=currency,
            source='admin.model.approve'
        )

        # Update model_catalog provenance and availability
        await session.execute(sqlalchemy.text(
            "UPDATE model_catalog SET provenance = 'admin-approved', availability = 'available', updated_at = now() WHERE id = :id"
        ), {'id': model_id})
        await session.commit()

        await _write_audit_log('admin.model.approved', target_type='model_catalog', target_id=model_id, details={'new_pricing': price_result})
        await invalidate_pricing_cache()
        return JSONResponse({'status': 'ok', 'model': model_id, 'new_pricing': price_result})

@router.post('/admin/models/{model_id}/set-upstream')
async def set_model_upstream(request: Request, model_id: str, payload: dict[str, Any]) -> JSONResponse:
    """Admin: Manually assign an upstream provider to a model."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    upstream_name = payload.get('upstream')
    if not upstream_name:
        return JSONResponse({'detail': 'نام upstream الزامی است'}, status_code=400)

    # Basic validation: check if upstream exists
    from providers import configured_providers
    valid_upstreams = [p.name for p in configured_providers()]
    if upstream_name not in valid_upstreams:
        return JSONResponse({'detail': f'Upstream {upstream_name} نامعتبر است'}, status_code=400)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                "UPDATE model_catalog SET upstream = :upstream, updated_at = now() WHERE id = :model_id"
            ),
            {'upstream': upstream_name, 'model_id': model_id}
        )
        if res.rowcount == 0:
             return JSONResponse({'detail': 'مدل در کاتالوگ یافت نشد'}, status_code=404)
        await session.commit()
    await _write_audit_log('admin.model.set_upstream', target_type='model_catalog', target_id=model_id, details={'upstream': upstream_name})
    from database import rds
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'ok', 'model': model_id, 'upstream': upstream_name})


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
    """Update live prices on model_catalog (via unified services/pricing.py)."""
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
    source = payload.get('source', 'admin.pricing.set')

    from services.pricing import set_model_price, invalidate_pricing_cache
    async with async_session() as session:
        try:
            result = await set_model_price(
                session,
                model_id=model,
                input_per_million=input_pm,
                output_per_million=output_pm,
                currency=currency,
                source=source,
            )
            await session.commit()
        except Exception as e:
            return JSONResponse({'detail': f'خطا در ثبت قیمت: {e}'}, status_code=500)

    await _write_audit_log('admin.pricing.set', target_type='model_catalog', target_id=model,
                           details={'input_per_million': input_pm, 'output_per_million': output_pm, 'price_version': result['price_version']})
    await invalidate_pricing_cache()
    return JSONResponse({'status': 'updated', 'model': model, 'price_version': result['price_version']})


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
