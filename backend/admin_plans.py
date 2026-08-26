"""Admin plans, credit packages and subscriptions endpoints.

Split out of admin.py (house 500-line cap) -- see admin.py's module
docstring for the full split map. Pure move: no behaviour change.

MONKEYPATCH CONTRACT: routes here gate on `admin.admin_required(request)`
(via a plain `import admin`, never `from admin import admin_required`) so
that `patch('admin.admin_required', ...)` in
tests/test_credit_package_model_label.py still works -- see admin.py's own
module docstring for why.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session
import admin
from dependencies import _write_audit_log
from i18n import err

router = APIRouter()


# ── Admin: Plans & Credit Packages ──────────────────────────────

@router.get('/admin/plans')
async def admin_list_plans(request: Request) -> JSONResponse:
    """List all plans (admin, including inactive)"""
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text('SELECT * FROM plans ORDER BY sort_order'))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


def _plan_jsonb(value: Any) -> str | None:
    """Encode a Python value for a raw ``text()`` bind against a jsonb column.

    ``sqlalchemy.text()`` does no type coercion — the value goes to asyncpg
    exactly as given. asyncpg's jsonb codec requires already-serialized JSON
    text, not a Python list/dict; binding a raw list (as this handler's
    UPDATE branch used to do for ``features``, and both branches used to do
    for ``models_allowed``) fails against a real jsonb column. ``None`` is
    passed through unchanged so it still binds as SQL NULL (the column is
    nullable) instead of becoming the string ``"null"``.
    """
    return None if value is None else json.dumps(value)


@router.post('/admin/plans')
async def admin_create_plan(request: Request) -> JSONResponse:
    """Create or update a plan (admin).

    ── NOT NULL columns the old INSERT branch silently skipped ──
    `plans` has three NOT NULL columns with no default that the INSERT
    branch never set: `name`, `price_yearly`, `token_quota_monthly`. Every
    "create new plan" call from the admin panel raised an IntegrityError and
    500'd — proven on a throwaway DB via migrate.py before this fix (see
    tests/test_admin_plans.py). All three are now populated: `name` falls
    back to name_fa/name_en/the plan id, `price_yearly` defaults to
    `price_monthly * 12` when not supplied (no yearly-price field exists in
    the admin UI yet), `token_quota_monthly` is written together with
    `monthly_token_quota` (see below).

    ── The two duplicate quota columns must never diverge ──
    `plans` carries BOTH `token_quota_monthly` (NOT NULL, from an earlier
    migration) and `monthly_token_quota` (nullable, what this handler
    actually reads/writes) holding the same number. The old handler only
    ever wrote the second, so the first edit from the UI made them diverge.
    Both are now always written together from the single `monthly_token_quota`
    (or legacy `token_quota_monthly`) value the API accepts.

    ── features / models_allowed jsonb binding ──
    The UPDATE branch used to bind `features` and `models_allowed` as raw
    Python values into a `text()` statement against jsonb columns (fails
    against a real jsonb column — see `_plan_jsonb`'s docstring), while the
    INSERT branch only `json.dumps`'d `features` and still bound
    `models_allowed` raw. Both columns in both branches now go through
    `_plan_jsonb`.
    """
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    payload = await request.json()
    plan_id = payload.get('id')
    if not plan_id:
        return err('شناسه الزامی است', 'ID is required.', 400)

    # Single source of truth for the monthly quota, written to BOTH
    # `monthly_token_quota` and the legacy `token_quota_monthly` so they can
    # never diverge again. Accepts either key on input (the legacy one is
    # accepted for backward compatibility, never written to alone).
    quota_present = 'monthly_token_quota' in payload or 'token_quota_monthly' in payload
    try:
        quota = int(payload.get('monthly_token_quota', payload.get('token_quota_monthly', 0)) or 0)
    except (TypeError, ValueError):
        quota = 0

    models_allowed_json = _plan_jsonb(payload.get('models_allowed'))

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text('SELECT id FROM plans WHERE id = :pid'), {'pid': plan_id})
        existing = res.fetchone()

        if existing:
            fields = ['name_fa', 'name_en', 'price_monthly',
                       'daily_token_limit', 'priority_queue', 'active', 'sort_order']
            set_parts = []
            params: dict[str, Any] = {'pid': plan_id, 'now': now}
            for f in fields:
                if f in payload:
                    set_parts.append(f'{f} = :{f}')
                    params[f] = payload[f]
            if quota_present:
                set_parts.append('monthly_token_quota = :quota')
                set_parts.append('token_quota_monthly = :quota')
                params['quota'] = quota
            if 'features' in payload:
                set_parts.append('features = :features')
                params['features'] = _plan_jsonb(payload['features'])
            set_parts.append('updated_at = :now')
            set_parts.append('models_allowed = :models_allowed')
            params['models_allowed'] = models_allowed_json
            await session.execute(
                sqlalchemy.text(f"UPDATE plans SET {', '.join(set_parts)} WHERE id = :pid"),
                params
            )
        else:
            name = payload.get('name') or payload.get('name_fa') or payload.get('name_en') or plan_id
            price_monthly = int(payload.get('price_monthly', 0) or 0)
            price_yearly = int(payload.get('price_yearly', price_monthly * 12) or 0)
            await session.execute(
                sqlalchemy.text(
                    "INSERT INTO plans (id, name, name_fa, name_en, price_monthly, price_yearly, "
                    "token_quota_monthly, monthly_token_quota, daily_token_limit, models_allowed, "
                    "priority_queue, features, active, sort_order) "
                    "VALUES (:id, :name, :name_fa, :name_en, :price_monthly, :price_yearly, "
                    ":quota, :quota, :daily_token_limit, :models_allowed, :priority_queue, :features, "
                    ":active, :sort_order)"
                ),
                {
                    'id': plan_id,
                    'name': name,
                    'name_fa': payload.get('name_fa', ''),
                    'name_en': payload.get('name_en', ''),
                    'price_monthly': price_monthly,
                    'price_yearly': price_yearly,
                    'quota': quota,
                    'daily_token_limit': payload.get('daily_token_limit', 0),
                    'models_allowed': models_allowed_json,
                    'priority_queue': payload.get('priority_queue', False),
                    'features': _plan_jsonb(payload.get('features', [])),
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
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text('SELECT * FROM credit_packages ORDER BY sort_order'))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/credit-packages')
async def admin_create_credit_package(request: Request) -> JSONResponse:
    """Create or update a credit package (admin)"""
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    payload = await request.json()
    pkg_id = payload.get('id')
    if not pkg_id:
        return err('شناسه الزامی است', 'ID is required.', 400)

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
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

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


