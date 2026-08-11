"""
Admin billing catalog: subscription plans, credit packages, and the
read-only subscription roster.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session
from dependencies import admin_required, _write_audit_log

router = APIRouter()

# ── Admin: Plans & Credit Packages ──────────────────────────────

@router.get('/admin/plans')
async def admin_list_plans(request: Request) -> JSONResponse:
    """List all plans (admin, including inactive)"""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text('SELECT * FROM plans ORDER BY sort_order'))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/plans')
async def admin_create_plan(request: Request) -> JSONResponse:
    """Create or update a plan (admin)"""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    payload = await request.json()
    plan_id = payload.get('id')
    if not plan_id:
        return JSONResponse({'detail': 'شناسه الزامی است'}, status_code=400)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text('SELECT id FROM plans WHERE id = :pid'), {'pid': plan_id})
        existing = res.fetchone()

        if existing:
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


@router.get('/admin/credit-packages')
async def admin_list_credit_packages(request: Request) -> JSONResponse:
    """List all credit packages (admin, including inactive)"""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text('SELECT * FROM credit_packages ORDER BY sort_order'))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/credit-packages')
async def admin_create_credit_package(request: Request) -> JSONResponse:
    """Create or update a credit package (admin)"""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    payload = await request.json()
    pkg_id = payload.get('id')
    if not pkg_id:
        return JSONResponse({'detail': 'شناسه الزامی است'}, status_code=400)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text('SELECT id FROM credit_packages WHERE id = :pid'), {'pid': pkg_id})
        existing = res.fetchone()

        if existing:
            fields = ['name_fa', 'name_en', 'base_amount', 'bonus_percent',
                       'total_credits', 'model_id', 'active', 'sort_order']
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
                    "total_credits, model_id, active, sort_order) "
                    "VALUES (:id, :name_fa, :name_en, :base_amount, :bonus_percent, "
                    ":total_credits, :model_id, :active, :sort_order)"
                ),
                {
                    'id': pkg_id,
                    'name_fa': payload.get('name_fa', ''),
                    'name_en': payload.get('name_en', ''),
                    'base_amount': payload.get('base_amount', 0),
                    'bonus_percent': payload.get('bonus_percent', 0),
                    'total_credits': payload.get('total_credits', 0),
                    'model_id': payload.get('model_id'),
                    'active': payload.get('active', True),
                    'sort_order': payload.get('sort_order', 0),
                }
            )
        await session.commit()

    await _write_audit_log('admin.credit_package.upsert', target_type='credit_package', target_id=pkg_id, details=payload)
    return JSONResponse({'status': 'ok', 'id': pkg_id})


@router.get('/admin/subscriptions')
async def admin_list_subscriptions(request: Request) -> JSONResponse:
    """List all subscriptions (admin)"""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

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
        'subscriptions': rows, 'total': total, 'page': page, 'limit': limit,
    }))
