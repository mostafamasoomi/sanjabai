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
    Notification, Wallet, Payment, UsageEvent, Conversation,
)
from dependencies import (
    admin_required, _get_user_id, _write_audit_log, _to_fa,
    _get_user_memories,
    ADMIN_COOKIE_NAME,
)
from security import get_lockout_info

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


# ── User Detail Endpoints ────────────────────────────────────────

@router.get('/admin/users/{uid}/detail')
async def admin_user_detail(request: Request, uid: int) -> JSONResponse:
    """Full user detail with stats: balance, tokens, conversations count, payments."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        user = await session.get(User, uid)
        if not user:
            return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        # Balance
        bal_res = await session.execute(
            sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
            {'uid': uid},
        )
        balance = bal_res.fetchone().balance
        # Wallet
        wallet = await session.get(Wallet, uid)
        # Quota
        quota = await session.get(Quota, uid)
        # Conversation count
        conv_res = await session.execute(
            sqlalchemy.text('SELECT COUNT(*) as c FROM conversations WHERE user_id = :uid'),
            {'uid': uid},
        )
        conv_count = conv_res.fetchone().c
        # Total tokens used
        token_res = await session.execute(
            sqlalchemy.text('SELECT COALESCE(SUM(used_today), 0) as t FROM quota WHERE user_id = :uid'),
            {'uid': uid},
        )
        # Usage events total
        usage_res = await session.execute(
            sqlalchemy.text('''SELECT COALESCE(SUM(input_tokens + output_tokens), 0) as total,
                               COUNT(*) as events, COALESCE(SUM(charge_amount), 0) as total_cost
                               FROM usage_events WHERE user_id = :uid'''),
            {'uid': uid},
        )
        usage_row = usage_res.fetchone()
        # Payments total
        pay_res = await session.execute(
            sqlalchemy.text('''SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
                               FROM payments WHERE user_id = :uid AND status = :st'''),
            {'uid': uid, 'st': 'verified'},
        )
        pay_row = pay_res.fetchone()

    return JSONResponse(jsonable_encoder({
        'user': {
            'id': user.id, 'email': user.email, 'phone': user.phone,
            'telegram_id': user.telegram_id, 'display_name': user.display_name,
            'bio': user.bio, 'avatar_url': user.avatar_url,
            'timezone': user.timezone, 'language': user.language,
            'banned': user.banned, 'created_at': user.created_at,
            'preferences': user.preferences or {},
        },
        'balance': balance,
        'wallet': {'balance': wallet.balance, 'reserved': wallet.reserved} if wallet else {'balance': 0, 'reserved': 0},
        'quota': {'daily_limit': quota.daily_limit, 'used_today': quota.used_today, 'reset_at': quota.reset_at} if quota else None,
        'stats': {
            'conversation_count': conv_count,
            'total_tokens': usage_row.total if usage_row else 0,
            'usage_events': usage_row.events if usage_row else 0,
            'total_cost': usage_row.total_cost if usage_row else 0,
            'payment_count': pay_row.count if pay_row else 0,
            'total_payments': pay_row.total if pay_row else 0,
        },
    }))


@router.get('/admin/users/{uid}/conversations')
async def admin_user_conversations(request: Request, uid: int) -> JSONResponse:
    """List a user's conversations with message counts."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    page = int(request.query_params.get('page', 1))
    limit = min(int(request.query_params.get('limit', 20)), 100)
    offset = (page - 1) * limit
    async with async_session() as session:
        count_res = await session.execute(
            sqlalchemy.text('SELECT COUNT(*) as c FROM conversations WHERE user_id = :uid'),
            {'uid': uid},
        )
        total = count_res.fetchone().c
        res = await session.execute(
            sqlalchemy.text('''SELECT id, title, model, created_at, updated_at,
                              jsonb_array_length(COALESCE(messages, '[]'::jsonb)) as msg_count
                              FROM conversations WHERE user_id = :uid
                              ORDER BY updated_at DESC LIMIT :limit OFFSET :offset'''),
            {'uid': uid, 'limit': limit, 'offset': offset},
        )
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder({'items': rows, 'total': total, 'page': page, 'limit': limit}))


@router.get('/admin/users/{uid}/usage')
async def admin_user_usage(request: Request, uid: int) -> JSONResponse:
    """Token usage breakdown by model for a user."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('''SELECT model, COUNT(*) as calls,
                              SUM(input_tokens) as input_tokens,
                              SUM(output_tokens) as output_tokens,
                              SUM(charge_amount) as total_cost,
                              MAX(created_at) as last_used
                              FROM usage_events WHERE user_id = :uid
                              GROUP BY model ORDER BY total_cost DESC'''),
            {'uid': uid},
        )
        rows = [dict(r._mapping) for r in res.fetchall()]
        # Daily usage last 30 days
        daily = await session.execute(
            sqlalchemy.text('''SELECT DATE(created_at) as day, SUM(input_tokens + output_tokens) as tokens,
                              SUM(charge_amount) as cost, COUNT(*) as calls
                              FROM usage_events WHERE user_id = :uid
                              AND created_at > NOW() - INTERVAL '30 days'
                              GROUP BY DATE(created_at) ORDER BY day DESC'''),
            {'uid': uid},
        )
        daily_rows = [dict(r._mapping) for r in daily.fetchall()]
    return JSONResponse(jsonable_encoder({'by_model': rows, 'daily': daily_rows}))


@router.get('/admin/users/{uid}/ledger')
async def admin_user_ledger(request: Request, uid: int) -> JSONResponse:
    """Wallet transaction history for a user."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    page = int(request.query_params.get('page', 1))
    limit = min(int(request.query_params.get('limit', 50)), 200)
    offset = (page - 1) * limit
    async with async_session() as session:
        count_res = await session.execute(
            sqlalchemy.text('SELECT COUNT(*) as c FROM ledger WHERE user_id = :uid'),
            {'uid': uid},
        )
        total = count_res.fetchone().c
        res = await session.execute(
            sqlalchemy.text('''SELECT id, amount, balance_after, reason, created_at
                              FROM ledger WHERE user_id = :uid
                              ORDER BY created_at DESC LIMIT :limit OFFSET :offset'''),
            {'uid': uid, 'limit': limit, 'offset': offset},
        )
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder({'items': rows, 'total': total, 'page': page, 'limit': limit}))


@router.get('/admin/users/{uid}/payments')
async def admin_user_payments(request: Request, uid: int) -> JSONResponse:
    """Payment/purchase history for a user."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('''SELECT id, amount, authority, ref_id, status,
                              payment_type, created_at, verified_at
                              FROM payments WHERE user_id = :uid
                              ORDER BY created_at DESC LIMIT 100'''),
            {'uid': uid},
        )
        rows = [dict(r._mapping) for r in res.fetchall()]
        # Subscription info
        sub_res = await session.execute(
            sqlalchemy.text('''SELECT * FROM subscriptions WHERE user_id = :uid
                              ORDER BY created_at DESC LIMIT 5'''),
            {'uid': uid},
        )
        subs = [dict(r._mapping) for r in sub_res.fetchall()]
    return JSONResponse(jsonable_encoder({'payments': rows, 'subscriptions': subs}))


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
        import sqlalchemy
        # Current balance from ledger
        res = await session.execute(sqlalchemy.text(
            "SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid"
        ), {'uid': uid})
        balance = res.fetchone().balance

        # Monthly usage from usage_events
        res2 = await session.execute(sqlalchemy.text(
            "SELECT COALESCE(SUM(input_tokens), 0) as inp, COALESCE(SUM(output_tokens), 0) as out, "
            "COALESCE(SUM(charged_amount), 0) as spent, COUNT(*) as cnt "
            "FROM usage_events WHERE user_id = :uid AND created_at >= date_trunc('month', now())"
        ), {'uid': uid})
        monthly = res2.fetchone()

        # Per-model breakdown
        res3 = await session.execute(sqlalchemy.text(
            "SELECT model, SUM(input_tokens) as inp, SUM(output_tokens) as out, "
            "SUM(charged_amount) as cost, COUNT(*) as calls "
            "FROM usage_events WHERE user_id = :uid AND created_at >= date_trunc('month', now()) "
            "GROUP BY model ORDER BY cost DESC"
        ), {'uid': uid})
        breakdown = [{'model': r.model, 'input_tokens': int(r.inp), 'output_tokens': int(r.out),
                       'cost': float(r.cost), 'calls': int(r.calls)} for r in res3.fetchall()]

        # Recent events
        res4 = await session.execute(sqlalchemy.text(
            "SELECT id, model, input_tokens, output_tokens, charged_amount, created_at "
            "FROM usage_events WHERE user_id = :uid ORDER BY id DESC LIMIT 20"
        ), {'uid': uid})
        events = [{'id': int(r.id), 'model': r.model, 'input_tokens': int(r.input_tokens),
                    'output_tokens': int(r.output_tokens), 'cost': float(r.charged_amount),
                    'created_at': r.created_at.isoformat() if r.created_at else None}
                   for r in res4.fetchall()]

        return JSONResponse({
            'current_balance': float(balance),
            'total_spent_this_month': float(monthly.spent),
            'total_input_tokens_this_month': int(monthly.inp),
            'total_output_tokens_this_month': int(monthly.out),
            'event_count_this_month': int(monthly.cnt),
            'per_model_breakdown': breakdown,
            'recent_events': events,
        })


# ── Enhanced Usage endpoint ──────────────────────────────────────

@router.get('/me/usage/v2')
async def me_usage_v2(
    request: Request,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 20,
) -> JSONResponse:
    """Enhanced usage endpoint with charts, date filtering, efficiency & top call.

    Query params:
      ?from=2026-07-01&to=2026-07-31  -> date range filter (inclusive, by date)
      ?limit=50                       -> number of recent_events to return

    Returns:
      current_balance, monthly totals, per_model_breakdown (with efficiency),
      daily_chart (last 30 days or range), top_message, recent_events.
    """
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    # Validate / build date range for filtering (inclusive on both ends).
    range_sql = ''
    params: dict[str, Any] = {'uid': uid}
    if from_date:
        range_sql += ' AND DATE(created_at) >= :from_date'
        params['from_date'] = from_date
    if to_date:
        range_sql += ' AND DATE(created_at) <= :to_date'
        params['to_date'] = to_date

    # Clamp limit
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500

    async with async_session() as session:
        # Current balance from ledger
        res = await session.execute(sqlalchemy.text(
            "SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid"
        ), {'uid': uid})
        balance = res.fetchone().balance

        # Monthly usage (always current calendar month, unaffected by range filter)
        res2 = await session.execute(sqlalchemy.text(
            "SELECT COALESCE(SUM(input_tokens), 0) as inp, COALESCE(SUM(output_tokens), 0) as out, "
            "COALESCE(SUM(charged_amount), 0) as spent, COUNT(*) as cnt "
            "FROM usage_events WHERE user_id = :uid AND created_at >= date_trunc('month', now())"
        ), {'uid': uid})
        monthly = res2.fetchone()

        # Per-model breakdown WITH token efficiency (avg tokens per call)
        res3 = await session.execute(sqlalchemy.text(
            "SELECT model, SUM(input_tokens) as inp, SUM(output_tokens) as out, "
            "SUM(charged_amount) as cost, COUNT(*) as calls "
            "FROM usage_events WHERE user_id = :uid AND created_at >= date_trunc('month', now()) "
            "GROUP BY model ORDER BY cost DESC"
        ), {'uid': uid})
        breakdown = []
        for r in res3.fetchall():
            calls = int(r.calls)
            breakdown.append({
                'model': r.model,
                'input_tokens': int(r.inp),
                'output_tokens': int(r.out),
                'cost': float(r.cost),
                'calls': calls,
                'avg_input_tokens_per_call': (int(r.inp) / calls) if calls else 0.0,
                'avg_output_tokens_per_call': (int(r.out) / calls) if calls else 0.0,
                'avg_total_tokens_per_call': ((int(r.inp) + int(r.out)) / calls) if calls else 0.0,
            })

        # Daily chart (last 30 days, or filtered range) — zero-filled via generate_series
        from datetime import datetime, timedelta, date as dt_date
        _now = datetime.utcnow()
        _start = dt_date.fromisoformat(from_date) if from_date else (_now - timedelta(days=30)).date()
        _end = dt_date.fromisoformat(to_date) if to_date else _now.date()
        daily_sql = sqlalchemy.text("""
            WITH dates AS (
                SELECT generate_series(CAST(:start_day AS date), CAST(:end_day AS date), '1 day')::date AS day
            )
            SELECT d.day::text AS date,
                   COALESCE(SUM(ue.charged_amount), 0) AS cost,
                   COALESCE(SUM(ue.input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(ue.output_tokens), 0) AS output_tokens,
                   COUNT(ue.id) AS calls
            FROM dates d
            LEFT JOIN usage_events ue
                ON DATE(ue.created_at) = d.day AND ue.user_id = :uid
            GROUP BY d.day
            ORDER BY d.day
        """)
        daily_params: dict[str, Any] = {
            'uid': uid,
            'start_day': _start,
            'end_day': _end,
        }
        res5 = await session.execute(daily_sql, daily_params)
        daily_chart = [{
            'date': str(r._mapping['date']),
            'cost': float(r._mapping['cost']),
            'input_tokens': int(r._mapping['input_tokens']),
            'output_tokens': int(r._mapping['output_tokens']),
            'calls': int(r._mapping['calls']),
        } for r in res5.fetchall()]

        # Top message: most expensive single call this month
        res6 = await session.execute(sqlalchemy.text(
            "SELECT id, model, input_tokens, output_tokens, charged_amount, created_at "
            "FROM usage_events "
            "WHERE user_id = :uid AND created_at >= date_trunc('month', now()) "
            "ORDER BY charged_amount DESC NULLS LAST LIMIT 1"
        ), {'uid': uid})
        top_row = res6.fetchone()
        top_message = None
        if top_row:
            top_message = {
                'id': int(top_row.id),
                'model': top_row.model,
                'input_tokens': int(top_row.input_tokens),
                'output_tokens': int(top_row.output_tokens),
                'cost': float(top_row.charged_amount),
                'created_at': top_row.created_at.isoformat() if top_row.created_at else None,
            }

        # Recent events (default 20, override via ?limit=)
        res4 = await session.execute(sqlalchemy.text(
            "SELECT id, model, input_tokens, output_tokens, charged_amount, created_at "
            "FROM usage_events WHERE user_id = :uid " + range_sql +
            " ORDER BY id DESC LIMIT :limit"
        ), {**params, 'limit': limit})
        events = [{
            'id': int(r.id), 'model': r.model, 'input_tokens': int(r.input_tokens),
            'output_tokens': int(r.output_tokens), 'cost': float(r.charged_amount),
            'created_at': r.created_at.isoformat() if r.created_at else None,
        } for r in res4.fetchall()]

        return JSONResponse({
            'current_balance': float(balance),
            'total_spent_this_month': float(monthly.spent),
            'total_input_tokens_this_month': int(monthly.inp),
            'total_output_tokens_this_month': int(monthly.out),
            'event_count_this_month': int(monthly.cnt),
            'per_model_breakdown': breakdown,
            'daily_chart': daily_chart,
            'top_message': top_message,
            'recent_events': events,
            'filters': {'from': from_date, 'to': to_date, 'limit': limit},
        })


@router.get('/me/usage/export')
async def me_usage_export(
    request: Request,
    format: str = 'csv',
    from_date: str | None = None,
    to_date: str | None = None,
) -> Response:
    """Export usage events as CSV.

    GET /me/usage/export?format=csv
    Optional: ?from=2026-07-01&to=2026-07-31

    CSV columns: date,model,input_tokens,output_tokens,cost
    """
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    if format != 'csv':
        return JSONResponse({'detail': 'Unsupported format. Use format=csv'}, status_code=400)

    range_sql = ''
    params: dict[str, Any] = {'uid': uid}
    if from_date:
        range_sql += ' AND DATE(created_at) >= :from_date'
        params['from_date'] = from_date
    if to_date:
        range_sql += ' AND DATE(created_at) <= :to_date'
        params['to_date'] = to_date

    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            "SELECT DATE(created_at)::text AS date, model, "
            "input_tokens, output_tokens, charged_amount "
            "FROM usage_events WHERE user_id = :uid " + range_sql +
            " ORDER BY created_at DESC"
        ), params)
        rows = res.fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['date', 'model', 'input_tokens', 'output_tokens', 'cost'])
    for r in rows:
        writer.writerow([
            r._mapping['date'],
            r._mapping['model'],
            int(r._mapping['input_tokens']),
            int(r._mapping['output_tokens']),
            float(r._mapping['charged_amount']),
        ])

    csv_bytes = buf.getvalue().encode('utf-8-sig')
    return Response(
        content=csv_bytes,
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="usage_export.csv"'},
    )


# ── Analytics Timeseries ──────────────────────────────────────────

@router.get('/admin/analytics/timeseries')
async def admin_analytics_timeseries(request: Request) -> JSONResponse:
    """30-day timeseries for admin dashboard charts.

    Returns: daily_revenue, daily_users, daily_tokens, top_users, revenue_by_model
    All series include zero-filled days via generate_series.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        # 1) Daily revenue (generate_series fills zero days)
        res_rev = await session.execute(sqlalchemy.text("""
            WITH dates AS (
                SELECT generate_series(
                    (NOW() - INTERVAL '30 days')::date,
                    NOW()::date,
                    '1 day'
                )::date AS day
            )
            SELECT d.day::text AS day,
                   COALESCE(SUM(ue.charged_amount), 0) AS amount
            FROM dates d
            LEFT JOIN usage_events ue ON DATE(ue.created_at) = d.day
            GROUP BY d.day
            ORDER BY d.day
        """))
        daily_revenue = [{'day': str(r._mapping['day']), 'amount': int(r._mapping['amount'])}
                         for r in res_rev.fetchall()]

        # 2) Daily active + new users
        res_users = await session.execute(sqlalchemy.text("""
            WITH dates AS (
                SELECT generate_series(
                    (NOW() - INTERVAL '30 days')::date,
                    NOW()::date,
                    '1 day'
                )::date AS day
            )
            SELECT d.day::text AS day,
                   COUNT(DISTINCT ue.user_id) AS active_users,
                   COUNT(DISTINCT CASE
                       WHEN DATE(u.created_at) = d.day THEN u.id
                   END) AS new_users
            FROM dates d
            LEFT JOIN usage_events ue ON DATE(ue.created_at) = d.day
            LEFT JOIN users u ON DATE(u.created_at) = d.day
            GROUP BY d.day
            ORDER BY d.day
        """))
        daily_users = [{'day': str(r._mapping['day']),
                        'active_users': int(r._mapping['active_users']),
                        'new_users': int(r._mapping['new_users'])}
                       for r in res_users.fetchall()]

        # 3) Daily token volume (input/output stacked)
        res_tok = await session.execute(sqlalchemy.text("""
            WITH dates AS (
                SELECT generate_series(
                    (NOW() - INTERVAL '30 days')::date,
                    NOW()::date,
                    '1 day'
                )::date AS day
            )
            SELECT d.day::text AS day,
                   COALESCE(SUM(ue.input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(ue.output_tokens), 0) AS output_tokens
            FROM dates d
            LEFT JOIN usage_events ue ON DATE(ue.created_at) = d.day
            GROUP BY d.day
            ORDER BY d.day
        """))
        daily_tokens = [{'day': str(r._mapping['day']),
                         'input_tokens': int(r._mapping['input_tokens']),
                         'output_tokens': int(r._mapping['output_tokens'])}
                        for r in res_tok.fetchall()]

        # 4) Revenue by model (current month)
        res_models = await session.execute(sqlalchemy.text("""
            SELECT model,
                   SUM(charged_amount) AS revenue,
                   COUNT(DISTINCT user_id) AS users,
                   COUNT(*) AS calls
            FROM usage_events
            WHERE created_at >= DATE_TRUNC('month', NOW())
            GROUP BY model
            ORDER BY revenue DESC
            LIMIT 10
        """))
        revenue_by_model = [{'model': r._mapping['model'],
                             'revenue': int(r._mapping['revenue']),
                             'users': int(r._mapping['users']),
                             'calls': int(r._mapping['calls'])}
                            for r in res_models.fetchall()]

        # 5) Top users by spend (current month)
        res_top = await session.execute(sqlalchemy.text("""
            SELECT ue.user_id,
                   u.email,
                   SUM(ue.charged_amount) AS total_cost,
                   SUM(ue.input_tokens + ue.output_tokens) AS total_tokens,
                   COUNT(*) AS calls
            FROM usage_events ue
            JOIN users u ON ue.user_id = u.id
            WHERE ue.created_at >= DATE_TRUNC('month', NOW())
            GROUP BY ue.user_id, u.email
            ORDER BY total_cost DESC
            LIMIT 10
        """))
        top_users = [{'user_id': r._mapping['user_id'],
                      'email': r._mapping['email'] or '',
                      'total_cost': int(r._mapping['total_cost']),
                      'total_tokens': int(r._mapping['total_tokens']),
                      'calls': int(r._mapping['calls'])}
                     for r in res_top.fetchall()]

    return JSONResponse(jsonable_encoder({
        'daily_revenue': daily_revenue,
        'daily_users': daily_users,
        'daily_tokens': daily_tokens,
        'revenue_by_model': revenue_by_model,
        'top_users': top_users,
    }))
# ── Enhanced Audit Trail ────────────────────────────────────────

@router.get('/admin/audit-logs')
async def admin_audit_logs(request: Request) -> JSONResponse:
    """Paginated audit log viewer with filtering.

    Query params:
      page      – page number (default 1)
      limit     – results per page (max 200, default 50)
      action    – filter by action prefix (e.g. 'auth.', 'admin.')
      user_id   – filter by admin_user_id
      since     – ISO datetime; only return entries after this time
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    page = max(1, int(request.query_params.get('page', 1)))
    limit = min(max(1, int(request.query_params.get('limit', 50))), 200)
    offset = (page - 1) * limit
    action_filter = request.query_params.get('action')
    user_filter = request.query_params.get('user_id')
    since_filter = request.query_params.get('since')

    conditions = []
    params: dict[str, Any] = {}
    if action_filter:
        conditions.append('action LIKE :action')
        params['action'] = f'{action_filter}%'
    if user_filter:
        conditions.append('admin_user_id = :uid')
        params['uid'] = int(user_filter)
    if since_filter:
        conditions.append('created_at >= :since')
        params['since'] = since_filter

    where_clause = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''

    async with async_session() as session:
        count_res = await session.execute(
            sqlalchemy.text(f'SELECT COUNT(*) as c FROM audit_logs{where_clause}'),
            params,
        )
        total = count_res.fetchone().c
        res = await session.execute(
            sqlalchemy.text(
                f'SELECT id, admin_user_id, action, target_type, target_id, '
                f'details, ip_address, user_agent, created_at '
                f'FROM audit_logs{where_clause} '
                f'ORDER BY created_at DESC LIMIT :limit OFFSET :offset'
            ),
            {**params, 'limit': limit, 'offset': offset},
        )
        rows = [dict(r._mapping) for r in res.fetchall()]

    return JSONResponse(jsonable_encoder({
        'logs': rows, 'total': total, 'page': page, 'limit': limit,
    }))


# ── Admin MFA (TOTP) Skeleton ───────────────────────────────────

class MfaSetupRequest(BaseModel):
    """Empty body – the endpoint generates a new TOTP secret."""
    pass

class MfaVerifyRequest(BaseModel):
    code: str

class MfaEnableRequest(BaseModel):
    code: str
    secret: str


@router.post('/admin/mfa/setup')
async def admin_mfa_setup(request: Request) -> JSONResponse:
    """Generate a new TOTP secret and provisioning URI for the admin.

    Returns the secret and a otpauth:// URI that can be rendered as a QR
    code client-side.  The secret is NOT stored yet – it is stored only
    after the admin verifies a valid TOTP code via /admin/mfa/enable.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    try:
        import pyotp
    except ImportError:
        return JSONResponse({'detail': 'TOTP library not installed'}, status_code=500)

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name='Multiai Admin',
        issuer_name='Multiai',
    )

    # Store the pending secret in Redis so we can verify it later
    try:
        from database import rds
        pending_key = f'mfa_pending:{request.cookies.get(ADMIN_COOKIE_NAME, "unknown")}'
        await rds.setex(pending_key, 300, secret)  # 5 min to complete setup
    except Exception:
        pass

    return JSONResponse({
        'secret': secret,
        'provisioning_uri': provisioning_uri,
        'expires_in': 300,
    })


@router.post('/admin/mfa/enable')
async def admin_mfa_enable(request: Request, payload: MfaEnableRequest) -> JSONResponse:
    """Verify TOTP code and enable MFA for the admin user.

    The admin must have completed /admin/mfa/setup first.
    After verification the secret is stored in the users table.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    try:
        import pyotp
    except ImportError:
        return JSONResponse({'detail': 'TOTP library not installed'}, status_code=500)

    # Retrieve the pending secret
    try:
        from database import rds
        pending_key = f'mfa_pending:{request.cookies.get(ADMIN_COOKIE_NAME, "unknown")}'
        pending_secret = await rds.get(pending_key)
    except Exception:
        pending_secret = None

    secret = payload.secret or pending_secret
    if not secret:
        return JSONResponse({'detail': 'TOTP secret not found. Run setup first.'}, status_code=400)

    # Verify the code
    totp = pyotp.TOTP(secret)
    if not totp.verify(payload.code, valid_window=1):
        return JSONResponse({'detail': 'کد TOTP نامعتبر است'}, status_code=400)

    # Store the secret (would need user_id from admin session; for skeleton, store in Redis)
    try:
        from database import rds
        admin_sid = request.cookies.get(ADMIN_COOKIE_NAME, '')
        mfa_key = f'admin_mfa:{admin_sid}'
        await rds.setex(mfa_key, 86400 * 30, secret)  # 30 day storage
        # Mark session as MFA-enabled
        sess_key = f'admin_session:{admin_sid}'
        sess_raw = await rds.get(sess_key)
        if sess_raw:
            import json
            sess = json.loads(sess_raw)
            sess['totp_enabled'] = True
            from dependencies import ADMIN_SESSION_TTL
            await rds.setex(sess_key, ADMIN_SESSION_TTL, json.dumps(sess))
        # Cleanup pending
        await rds.delete(pending_key)
    except Exception:
        pass

    await _write_audit_log('admin.mfa.enabled', request=request)
    return JSONResponse({'status': 'ok', 'message': 'TOTP MFA فعال شد'})


@router.post('/admin/mfa/verify')
async def admin_mfa_verify(request: Request, payload: MfaVerifyRequest) -> JSONResponse:
    """Verify a TOTP code and mark the current session as verified.

    Called after login when MFA is enabled but the session is not yet verified.
    """
    if not await admin_required(request):
        # Even if admin_required fails due to totp_required, we still need to
        # check for the admin session cookie directly
        sid = request.cookies.get(ADMIN_COOKIE_NAME, '')
        if not sid:
            return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
        try:
            from database import rds as _rds
            mfa_key = f'admin_mfa:{sid}'
            secret = await _rds.get(mfa_key)
            if not secret:
                return JSONResponse({'detail': 'TOTP فعال نیست'}, status_code=400)

            import pyotp
            totp = pyotp.TOTP(secret)
            if not totp.verify(payload.code, valid_window=1):
                return JSONResponse({'detail': 'کد TOTP نامعتبر است'}, status_code=400)

            # Mark session as TOTP verified
            sess_key = f'admin_session:{sid}'
            sess_raw = await _rds.get(sess_key)
            if sess_raw:
                import json
                sess = json.loads(sess_raw)
                sess['totp_verified'] = True
                from dependencies import ADMIN_SESSION_TTL
                await _rds.setex(sess_key, ADMIN_SESSION_TTL, json.dumps(sess))

            await _write_audit_log('admin.mfa.verified', request=request)
            return JSONResponse({'status': 'ok'})
        except Exception:
            return JSONResponse({'detail': 'خطای سرور'}, status_code=500)

    # If admin_required passed (MFA not enabled or already verified)
    return JSONResponse({'status': 'ok', 'message': 'TOTP از قبل تأیید شده'})


@router.post('/admin/mfa/disable')
async def admin_mfa_disable(request: Request) -> JSONResponse:
    """Disable TOTP MFA for the admin session."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    try:
        from database import rds as _rds
        admin_sid = request.cookies.get(ADMIN_COOKIE_NAME, '')
        mfa_key = f'admin_mfa:{admin_sid}'
        await _rds.delete(mfa_key)
        # Update session to disable MFA
        sess_key = f'admin_session:{admin_sid}'
        sess_raw = await _rds.get(sess_key)
        if sess_raw:
            import json
            sess = json.loads(sess_raw)
            sess['totp_enabled'] = False
            sess['totp_verified'] = False
            from dependencies import ADMIN_SESSION_TTL
            await _rds.setex(sess_key, ADMIN_SESSION_TTL, json.dumps(sess))
    except Exception:
        pass

    await _write_audit_log('admin.mfa.disabled', request=request)
    return JSONResponse({'status': 'ok'})


# ── Lockout Management ──────────────────────────────────────────

@router.get('/admin/lockout/status')
async def admin_lockout_status(request: Request) -> JSONResponse:
    """Check lockout status for a given identifier (admin only)."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    identifier = request.query_params.get('identifier', '')
    if not identifier:
        return JSONResponse({'detail': 'identifier parameter required'}, status_code=400)

    info = await get_lockout_info(identifier)
    return JSONResponse(info)
