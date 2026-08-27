"""Admin analytics endpoints: data export (CSV), dashboard analytics/stats,
30-day timeseries, and the audit-log viewer.

Split out of admin.py (house 500-line cap) -- see admin.py's module
docstring for the full split map. Pure move: no behaviour change.

MONKEYPATCH CONTRACT: routes here gate on `admin.admin_required(request)`
(via a plain `import admin`, never `from admin import admin_required`) --
see admin.py's own module docstring for why.
"""
from __future__ import annotations

import csv
import io
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from database import async_session
from models import Ledger
import admin
from dependencies import _write_audit_log
from i18n import err

router = APIRouter()


# ── Data Export ─────────────────────────────────────────────────

@router.get('/admin/export/ledger')
async def export_ledger(request: Request) -> Response:
    """Export all ledger entries as CSV"""
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
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
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
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
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM users'))
        user_count = r.fetchone().c
        # ── Revenue must mean money that actually arrived through the ──
        # ── payment gateway, never "any positive ledger row".          ──
        #
        # The old query here was `SELECT COALESCE(SUM(amount), 0) FROM ledger
        # WHERE amount > 0`. That is not revenue -- it is "every ledger row
        # with a plus sign", and the ledger's sign alone cannot tell a
        # gateway payment apart from an admin-seeded credit, a refund, or a
        # released reservation. Measured on production on 2026-08-22:
        #   payments completed = 0, payment_orders completed = 0
        #   ledger: one 'topup' row = +10,000,000 (admin-seeded by hand,
        #     reason='initial_credit'), 52 'usage' rows summing to -53,514
        #   old query -> total_revenue = 10,000,000 for a business that has
        #   taken ZERO gateway payments.
        #
        # Fix: resolve revenue directly from the payment tables, never from
        # the ledger. This follows the exact precedent already established
        # by services/free_tier.py::_HAS_PAID_SQL, whose docstring explains
        # why: "the ledger writes txn_type='credit' for gateway payments,
        # referral bonuses AND the signup gift alike, so it cannot tell a
        # real payment apart from free money" -- that module resolves
        # "has ever paid" from `payments`/`payment_orders` for the same
        # reason we resolve revenue from them here.
        #
        # Units: `payments.amount` is integer TOMAN -- proven from code, not
        # from live data, because both `payments` and `payment_orders` are
        # currently EMPTY in production (0 rows each), so there is nothing
        # to sample. The proof: payment.py's create_payment() takes
        # `amount: int  # in Tomans`, and handle_payment_callback() wraps
        # `payment["amount"]` in `Money(...)` (services/money.py -- an
        # integer-toman value object) before crediting the wallet. The
        # legacy `payment_orders.amount_irr` column is integer RIAL (the
        # name says so; it predates the Money/toman refactor and has no
        # active writer left in this codebase -- grepped), so it is
        # converted to toman (/10) before being added. If this assumption
        # is ever wrong, it would show up as revenue being off by exactly
        # 10x -- see test_admin_revenue_truth.py's assertion against that.
        #
        # `total_admin_credit` is reported separately so the owner can see
        # real money vs. seeded money side by side. It sums positive ledger
        # rows whose txn_type is NOT 'credit' -- 'credit' is the txn_type
        # `services/billing.py::credit_wallet` defaults to, and the ONLY
        # caller that relies on that default is payment.py's real gateway
        # credit path (payment.py L199-205, no txn_type passed). Every
        # non-gateway credit path in the current codebase passes an explicit
        # non-'credit' txn_type (admin_user_ops.py uses 'admin_credit'; the
        # one production 'topup'/'initial_credit' row was seeded directly).
        # Do NOT "simplify" this back to SUM(amount) WHERE amount > 0.
        r = await session.execute(sqlalchemy.text(
            "SELECT COALESCE((SELECT SUM(amount) FROM payments WHERE status = 'completed'), 0) "
            "+ COALESCE((SELECT SUM(amount_irr) FROM payment_orders WHERE status = 'completed'), 0) / 10 "
            "AS total"
        ))
        total_revenue = r.fetchone().total
        r = await session.execute(sqlalchemy.text(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM ledger WHERE amount > 0 AND txn_type <> 'credit'"
        ))
        total_admin_credit = r.fetchone().total
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
        'total_revenue': total_revenue, 'total_admin_credit': total_admin_credit,
        'total_tokens': total_tokens,
        'conv_count': conv_count, 'recent_ledger': recent,
    }))


@router.get('/admin/stats')
async def admin_stats(request: Request) -> JSONResponse:
    """Quick stats summary for admin dashboard."""
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM users'))
        total_users = r.fetchone().c
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM users WHERE banned = false'))
        active_users = r.fetchone().c
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM conversations'))
        total_conversations = r.fetchone().c
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM api_keys'))
        total_api_keys = r.fetchone().c
        # Revenue = completed gateway payments only, never a raw ledger sum.
        # See the long comment in admin_analytics() above for the full
        # rationale, the production evidence (10,000,000 toman of fake
        # "revenue" from a single admin-seeded ledger row), the toman-unit
        # proof, and why total_admin_credit is reported separately. Also
        # switched float(...) -> int(...): money in this codebase is always
        # integer toman, never a float (services/money.py).
        r = await session.execute(sqlalchemy.text(
            "SELECT COALESCE((SELECT SUM(amount) FROM payments WHERE status = 'completed'), 0) "
            "+ COALESCE((SELECT SUM(amount_irr) FROM payment_orders WHERE status = 'completed'), 0) / 10 "
            "AS total"
        ))
        total_revenue = int(r.scalar() or 0)
        r = await session.execute(sqlalchemy.text(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM ledger WHERE amount > 0 AND txn_type <> 'credit'"
        ))
        total_admin_credit = int(r.scalar() or 0)
        r = await session.execute(sqlalchemy.text('SELECT COUNT(*) as c FROM usage_events'))
        total_usage_events = r.fetchone().c
        r = await session.execute(sqlalchemy.text("SELECT COUNT(*) as c FROM model_catalog WHERE availability = 'available'"))
        total_models = r.fetchone().c
    return JSONResponse({
        'total_users': total_users, 'active_users': active_users,
        'total_conversations': total_conversations, 'total_api_keys': total_api_keys,
        'total_revenue': total_revenue, 'total_admin_credit': total_admin_credit,
        'total_usage_events': total_usage_events,
        'total_models': total_models,
    })


# ── Analytics Timeseries ──────────────────────────────────────────
#
# Moved to admin_analytics_timeseries.py. It was the largest endpoint in
# this file and it roughly doubled when the migration-0048 cost and
# margin series landed, which would have pushed this module well past the
# house 500-line cap. Its router is included alongside this one in
# admin.py, so the route path is unchanged.


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
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

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


