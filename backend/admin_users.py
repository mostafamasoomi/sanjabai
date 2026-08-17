"""
Admin user management: listing, ban/unban, profile edits, and the per-user
detail drill-down (stats, conversations, usage, ledger, payments).
"""
from __future__ import annotations

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import async_session, rds
from models import User, Ledger, Quota, Wallet
from dependencies import admin_required, _write_audit_log

router = APIRouter()


# ── Pydantic models ─────────────────────────────────────────────

class AdminUserEdit(BaseModel):
    daily_limit: int | None = None
    phone: str | None = None
    email: str | None = None
    balance: int | None = None
    status: str | None = None
    reason: str | None = None

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

        balance_delta = 0
        if 'balance' in data:
            target_balance = int(data['balance'])
            from services.billing import SqlBillingRepo, credit_wallet
            from services.money import Money
            import uuid

            repo = SqlBillingRepo(session)
            async with repo.lock_wallet_for_update(uid):
                wallet = await repo.ensure_wallet(uid)
                current_balance = wallet['balance']
                delta = target_balance - current_balance
                balance_delta = delta

                if delta != 0:
                    # Note: credit_wallet expects a positive or negative Money object.
                    # Money doesn't allow negative by default depending on implementation,
                    # but wait, `amount.irt` is used. We can just use raw integer update here
                    # or ensure we do it safely. Since it's admin, we can bypass `credit_wallet`
                    # if it strictly requires positive, but let's use repo methods directly under lock.

                    new_balance = current_balance + delta
                    await repo.set_wallet_balance(uid, new_balance)

                    reason_text = data.get('reason', 'admin.adjustment')
                    await repo.append_ledger({
                        'user_id': uid,
                        'amount': delta,
                        'balance_after': new_balance,
                        'reason': reason_text,
                        'idempotency_key': f"admin_adj_{uuid.uuid4().hex}"
                    })

        await session.commit()

    audit_details = data.copy()
    if 'balance' in data:
        audit_details['balance_delta'] = balance_delta
    await _write_audit_log('admin.user.edit', target_type='user', target_id=uid, details=audit_details)
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
