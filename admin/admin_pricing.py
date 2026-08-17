"""


Admin panel pricing & models: pricing page, model catalog page, and API endpoints.
from fastapi.responses import HTMLResponse
"""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from admin_config import (
    templates, UI, async_session, _redirect_or_html, _require_session,
    _require_api_session, _json_response, _execute, _fetch_all, _fetch_one
)
from sqlalchemy import text

router = APIRouter()


# ===== Server-rendered pages ===============================================

@router.get('/admin/pricing', response_class=HTMLResponse)
async def pricing_page(request: Request):
    prices = []
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, provider, model, input_per_million, output_per_million, currency, updated_at '
                    'FROM pricing ORDER BY provider, model')
                prices = rows
    except Exception:
        pass
    return _redirect_or_html(request, 'pricing.html', {'prices': prices})


@router.get('/admin/models', response_class=HTMLResponse)
async def models_page(request: Request):
    models = []
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, provider, display_name, provider_model_id, availability, context_window, input_per_million, output_per_million, updated_at '
                    'FROM model_catalog ORDER BY provider, display_name')
                models = rows
    except Exception:
        pass
    return _redirect_or_html(request, 'models.html', {'models': models})


# ===== Form-based updates (existing) =======================================

@router.post('/admin/pricing/update')
async def pricing_update(request: Request, item_id: str = Form(...), input: int = Form(...), output: int = Form(...)):
    redirect = _require_session(request)
    if isinstance(redirect, RedirectResponse):
        return redirect
    try:
        import sys
        from pathlib import Path
        backend_dir = Path(__file__).resolve().parent.parent / "backend"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        from services.pricing import set_model_price, invalidate_pricing_cache

        async with async_session() as session:
            # Look up model id if item_id is pricing.id
            m_row = await _fetch_one(session, 'SELECT model FROM pricing WHERE id = :id', {'id': item_id})
            model_id = m_row['model'] if m_row else item_id

            await set_model_price(
                session,
                model_id=model_id,
                input_per_million=input,
                output_per_million=output,
                currency='IRT',
                source='admin.jinja.pricing_update'
            )
            await session.commit()
            await invalidate_pricing_cache()
    except Exception:
        pass
    return RedirectResponse(url='/admin/pricing?updated=1', status_code=302)


@router.post('/admin/models/toggle')
async def model_toggle_form(request: Request, item_id: str = Form(...), enabled: str = Form(...)):
    redirect = _require_session(request)
    if isinstance(redirect, RedirectResponse):
        return redirect
    val = enabled.lower() in ['1', 'true', 'on', 'yes']
    try:
        async with async_session() as session:
            async with session.begin():
                new_avail = 'available' if val else 'disabled'
                await session.execute(text('UPDATE model_catalog SET availability=:e WHERE id=:id'), {'e': new_avail, 'id': item_id})
    except Exception:
        pass
    return RedirectResponse(url='/admin/models?updated=1', status_code=302)


# ===== API endpoints (JSON) ================================================

@router.get('/admin/api/pricing')
async def api_pricing(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, model, provider, input_per_million, output_per_million, currency, updated_at '
                    'FROM pricing ORDER BY provider, model')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.post('/admin/api/pricing')
async def api_pricing_create(request: Request):
    _require_api_session(request)
    body = await request.json()
    model = body.get('model')
    input_per_million = body.get('input_per_million', 0)
    output_per_million = body.get('output_per_million', 0)
    currency = body.get('currency', 'IRT')

    if not model:
        return _json_response({'error': 'model is required'}, 400)

    try:
        import sys
        from pathlib import Path
        backend_dir = Path(__file__).resolve().parent.parent / "backend"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        from services.pricing import set_model_price, invalidate_pricing_cache

        async with async_session() as session:
            await set_model_price(
                session,
                model_id=model,
                input_per_million=input_per_million,
                output_per_million=output_per_million,
                currency=currency,
                source='admin.jinja.api_pricing_create'
            )
            await session.commit()
            await invalidate_pricing_cache()
            return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.get('/admin/api/models')
async def api_models(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, provider, display_name, provider_model_id, availability, context_window, input_per_million, output_per_million, updated_at '
                    'FROM model_catalog ORDER BY provider, display_name')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.post('/admin/api/models/{model_id}/toggle')
async def api_model_toggle(request: Request, model_id: str):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                model = await _fetch_one(session,
                    'SELECT id, availability FROM model_catalog WHERE id = :id', {'id': model_id})
                if not model:
                    return _json_response({'error': 'Model not found'}, 404)
                new_val = 'disabled' if model['availability'] == 'available' else 'available'
                await _execute(session,
                    'UPDATE model_catalog SET availability = :e WHERE id = :id',
                    {'e': new_val, 'id': model_id})
                return _json_response({'ok': True, 'availability': new_val})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)