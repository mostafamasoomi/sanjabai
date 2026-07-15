"""
Admin endpoints: user management, pricing, features, discounts, about,
proxy config, org default model, analytics, stats, plans, credit packages,
subscriptions, data export.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from database import async_session, rds, LITELLM_HOST, _http
from models import (
    User, Pricing, Feature, Discount, AboutContent, ProxyConfig,
    Ledger, Quota, ApiKey, Plan, CreditPackage, Subscription,
    Notification,
)
from dependencies import (
    admin_required, _get_user_id, _write_audit_log, _to_fa,
    _get_user_memories,
)

router = APIRouter()


# ── Pydantic models ─────────────────────────────────────────────

class AdminUserEdit(BaseModel):
    daily_limit: int | None = None
    phone: str | None = None
    email: str | None = None
    balance: int | None = None
    status: str | None = None


# ── Pricing admin ───────────────────────────────────────────────

@router.get('/admin/pricing')
async def list_pricing(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            Pricing.__table__.select().order_by(Pricing.model, Pricing.price_version.desc())
        )
        rows = [dict(r._mapping) for r in res.fetchall()]
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
    """Insert a NEW versioned price row."""
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
    provider = payload.get('provider', 'unknown')
    source = payload.get('source')
    async with async_session() as session:
        cur = await session.execute(
            select(func.coalesce(func.max(Pricing.price_version), 0)).where(Pricing.model == model)
        )
        next_version = (cur.scalar_one() or 0) + 1
        row = Pricing(
            model=model, provider=provider,
            input_per_million=input_pm, output_per_million=output_pm,
            currency=currency, source=source,
            price_version=next_version,
            effective_from=datetime.now(timezone.utc).replace(tzinfo=None),
            effective_to=None,
        )
        session.add(row)
        await session.commit()
    await _write_audit_log('admin.pricing.set', target_type='pricing', target_id=model, details={'price_version': next_version})
    await rds.delete('cache:catalog:models', 'cache:catalog:pricing')
    return JSONResponse({'status': 'inserted', 'model': model, 'price_version': next_version})


# ── Features ────────────────────────────────────────────────────

@router.get('/admin/features')
async def list_features(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Feature.__table__.select().order_by(Feature.order_idx))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/features')
async def upsert_feature(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    fid = payload.get('id')
    async with async_session() as session:
        if fid:
            row = await session.get(Feature, fid)
            if not row:
                return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        else:
            row = Feature()
            session.add(row)
        row.title = payload.get('title', row.title)
        row.description = payload.get('description', row.description)
        row.icon = payload.get('icon', row.icon)
        row.active = payload.get('active', row.active)
        row.order_idx = payload.get('order_idx', row.order_idx)
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    await _write_audit_log('admin.feature.upsert', target_type='feature', target_id=row.id)
    await rds.delete('cache:content:features')
    return JSONResponse({'status': 'ok', 'id': row.id})


@router.delete('/admin/features/{fid}')
async def delete_feature(request: Request, fid: int) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        row = await session.get(Feature, fid)
        if row:
            await session.delete(row)
            await session.commit()
    await _write_audit_log('admin.feature.delete', target_type='feature', target_id=fid)
    await rds.delete('cache:content:features')
    return JSONResponse({'status': 'deleted'})


# ── Discounts ───────────────────────────────────────────────────

@router.get('/admin/discounts')
async def list_discounts(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Discount.__table__.select())
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/discounts')
async def upsert_discount(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    did = payload.get('id')
    code = payload.get('code')
    if not code:
        return JSONResponse({'detail': 'کد الزامی است'}, status_code=400)
    async with async_session() as session:
        if did:
            row = await session.get(Discount, did)
            if not row:
                return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        else:
            row = Discount()
            session.add(row)
        row.code = code
        row.percent = payload.get('percent', row.percent)
        row.active = payload.get('active', row.active)
        row.expires_at = payload.get('expires_at')
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    await _write_audit_log('admin.discount.upsert', target_type='discount', target_id=row.id)
    await rds.delete('cache:content:discounts')
    return JSONResponse({'status': 'ok', 'id': row.id})


@router.delete('/admin/discounts/{did}')
async def delete_discount(request: Request, did: int) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        row = await session.get(Discount, did)
        if row:
            await session.delete(row)
            await session.commit()
    await _write_audit_log('admin.discount.delete', target_type='discount', target_id=did)
    await rds.delete('cache:content:discounts')
    return JSONResponse({'status': 'deleted'})


# ── About ───────────────────────────────────────────────────────

@router.post('/admin/about')
async def set_about(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
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
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    await _write_audit_log('admin.about.set')
    await rds.delete('cache:about')
    return JSONResponse({'status': 'ok'})


# ── Proxy Config ────────────────────────────────────────────────

@router.get('/admin/proxy')
async def get_proxy(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'proxy_url': '', 'proxy_type': 'socks5', 'active': False})
    async with async_session() as session:
        res = await session.execute(ProxyConfig.__table__.select())
        row = res.fetchone()
        if not row:
            return JSONResponse({'proxy_url': '', 'proxy_type': 'socks5', 'active': False})
        return JSONResponse(jsonable_encoder(dict(row._mapping)))


@router.post('/admin/proxy')
async def set_proxy(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    proxy_url = payload.get('proxy_url', '')
    if proxy_url:
        parsed = urlparse(proxy_url)
        _ALLOWED_PROXY_SCHEMES = {'socks5', 'socks5h', 'http', 'https'}
        if parsed.scheme not in _ALLOWED_PROXY_SCHEMES:
            return JSONResponse(
                {'detail': 'نوع پروکسی مجاز نیست', 'code': 'invalid_proxy_scheme'},
                status_code=400,
            )
        hostname = parsed.hostname or ''
        if hostname in ('localhost', '127.0.0.1', '0.0.0.0', '::1') or \
           hostname.startswith('10.') or hostname.startswith('192.168.') or \
           hostname.startswith('172.'):
            return JSONResponse(
                {'detail': 'آدرس پروکسی داخلی مجاز نیست', 'code': 'internal_proxy_blocked'},
                status_code=400,
            )

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
        row.default_model = payload.get('default_model', row.default_model)
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    await _write_audit_log('admin.proxy.set')
    await rds.delete('cache:org:default-model')
    return JSONResponse({'status': 'ok', 'proxy_url': row.proxy_url})


@router.post('/admin/org-default-model')
async def set_org_default_model(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Admin: set org-wide default model."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    model_id = payload.get('default_model', '')
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(ProxyConfig.__table__.select())
        row = res.fetchone()
        if not row:
            row = ProxyConfig(default_model=model_id)
            session.add(row)
        else:
            row = await session.get(ProxyConfig, row.id)
            row.default_model = model_id
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    await _write_audit_log('admin.org_default_model.set', details={'model': model_id})
    await rds.delete('cache:org:default-model')
    return JSONResponse({'status': 'ok', 'default_model': model_id})


# ── User Management ─────────────────────────────────────────────

@router.get('/admin/users')
async def admin_users(request: Request) -> JSONResponse:
    """List all users (admin only)"""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    page = int(request.query_params.get('page', 1))
    limit = min(int(request.query_params.get('limit', 50)), 200)
    offset = (page - 1) * limit

    async with async_session() as session:
        count_res = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM users'))
        total = count_res.fetchone().c
        res = await session.execute(
            sqlalchemy.text('''
                SELECT u.id, u.email, u.phone, u.telegram_id, u.referral_code,
                       u.referred_by, u.created_at,
                       COALESCE(l.balance, 0) as balance,
                       COALESCE(q.used_today, 0) as used_today
                FROM users u
                LEFT JOIN (SELECT user_id, SUM(amount) as balance FROM ledger GROUP BY user_id) l ON l.user_id = u.id
                LEFT JOIN quota q ON q.user_id = u.id
                ORDER BY u.created_at DESC
                LIMIT :limit OFFSET :offset
            '''),
            {'limit': limit, 'offset': offset}
        )
        rows = [dict(r._mapping) for r in res.fetchall()]

    return JSONResponse(jsonable_encoder({
        'users': rows, 'total': total, 'page': page, 'limit': limit,
    }))


@router.post('/admin/users/{uid}/ban')
async def admin_ban_user(request: Request, uid: int) -> JSONResponse:
    """Ban/unban a user"""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        user = await session.get(User, uid)
        if not user:
            return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        new_banned = not user.banned
        await session.execute(User.__table__.update().where(User.id == uid), {'banned': new_banned})
        await session.execute(Quota.__table__.update().where(Quota.user_id == uid), {'daily_limit': 0 if new_banned else 200000})
        await session.commit()
        if new_banned:
            try:
                keys = await rds.keys('session:*')
                for key in keys:
                    val = await rds.get(key)
                    if val and str(uid) in val:
                        await rds.delete(key)
            except Exception:
                pass
        await _write_audit_log('admin.user.ban', target_type='user', target_id=uid, details={'banned': new_banned})
        return JSONResponse({'status': 'ok', 'banned': new_banned})


@router.put('/admin/users/{uid}')
async def admin_edit_user(request: Request, uid: int, payload: AdminUserEdit) -> JSONResponse:
    """Edit user details (admin)"""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    data = payload.model_dump(exclude_none=True)
    async with async_session() as session:
        if 'daily_limit' in data:
            await session.execute(Quota.__table__.update().where(Quota.user_id == uid), {'daily_limit': int(data['daily_limit'])})
        if 'phone' in data:
            await session.execute(User.__table__.update().where(User.id == uid), {'phone': data['phone']})
        if 'email' in data:
            await session.execute(User.__table__.update().where(User.id == uid), {'email': data['email']})
        if 'balance' in data:
            await session.execute(
                Ledger.__table__.insert().values(
                    user_id=uid, amount=int(data['balance']),
                    balance_after=int(data['balance']),
                    reason='admin.adjustment',
                )
            )
        await session.commit()
    await _write_audit_log('admin.user.edit', target_type='user', target_id=uid, details=data)
    return JSONResponse({'status': 'ok'})


# ── Data Export ─────────────────────────────────────────────────

@router.get('/admin/export/ledger')
async def export_ledger(request: Request) -> Response:
    """Export all ledger entries as CSV"""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Ledger.__table__.select().order_by(Ledger.created_at.desc()).limit(10000))
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


@router.get('/admin/export/users')
async def export_users(request: Request) -> Response:
    """Export all users as CSV"""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
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


# ── Analytics & Stats ───────────────────────────────────────────

@router.get('/admin/analytics')
async def admin_analytics(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM users'))
        user_count = r.fetchone().c
        r = await session.execute(sqlalchemy.text("SELECT COALESCE(SUM(amount), 0) as total FROM ledger WHERE amount > 0"))
        total_revenue = r.fetchone().total
        r = await session.execute(sqlalchemy.text('SELECT COALESCE(SUM(used_today), 0) as total FROM quota'))
        total_tokens = r.fetchone().total
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM conversations'))
        conv_count = r.fetchone().c
        r = await session.execute(sqlalchemy.text("SELECT COUNT(*) as c FROM quota WHERE used_today > 0"))
        active_users = r.fetchone().c
        r = await session.execute(Ledger.__table__.select().order_by(Ledger.created_at.desc()).limit(20))
        recent = [{'id': row.id, 'user_id': row.user_id, 'amount': row.amount, 'balance_after': row.balance_after, 'reason': row.reason, 'created_at': row.created_at} for row in r.fetchall()]
    return JSONResponse(jsonable_encoder({
        'user_count': user_count, 'active_users': active_users,
        'total_revenue': total_revenue, 'total_tokens': total_tokens,
        'conv_count': conv_count, 'recent_ledger': recent,
    }))


@router.get('/admin/stats')
async def admin_stats(request: Request) -> JSONResponse:
    """Quick stats summary for admin dashboard."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM users'))
        total_users = r.fetchone().c
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM users WHERE banned = false'))
        active_users = r.fetchone().c
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM conversations'))
        total_conversations = r.fetchone().c
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM api_keys'))
        total_api_keys = r.fetchone().c
        r = await session.execute(sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as t FROM ledger WHERE amount > 0'))
        total_revenue = float(r.scalar() or 0)
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM usage_events'))
        total_usage_events = r.fetchone().c
        r = await session.execute(sqlalchemy.text("SELECT COUNT(*) as c FROM model_catalog WHERE availability = 'available'"))
        total_models = r.fetchone().c
    return JSONResponse({
        'total_users': total_users, 'active_users': active_users,
        'total_conversations': total_conversations, 'total_api_keys': total_api_keys,
        'total_revenue': total_revenue, 'total_usage_events': total_usage_events,
        'total_models': total_models,
    })


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


# ── Usage endpoint ──────────────────────────────────────────────

@router.get('/me/usage')
async def me_usage(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        q = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
        row = q.fetchone()
        if not row:
            return JSONResponse({'user_id': uid, 'daily_limit': 0, 'used_today': 0, 'reset_at': None})
        return JSONResponse({'user_id': uid, 'daily_limit': row.daily_limit, 'used_today': row.used_today, 'reset_at': row.reset_at.isoformat() if row.reset_at else None})
