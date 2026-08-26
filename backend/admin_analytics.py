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

@router.get('/admin/analytics/timeseries')
async def admin_analytics_timeseries(request: Request) -> JSONResponse:
    """30-day timeseries for admin dashboard charts.

    Returns: daily_consumption, daily_gateway_revenue, daily_users,
    daily_tokens, top_users, consumption_by_model.
    All series include zero-filled days via generate_series.

    ── Naming, and why there are now two separate daily money series ──
    This endpoint used to return a single `daily_revenue` computed as
    `SUM(usage_events.charged_amount)` per day. That is *consumption* --
    what users were charged for model usage -- not revenue: it has nothing
    to do with money actually arriving through the payment gateway. The
    identical mistake in `/admin/stats` and `/admin/analytics` (a ledger
    variant of it) was fixed in commit 81d8240 ("the dashboard reported ten
    million toman of revenue from zero sales"), which established the
    precedent this endpoint now follows: `total_revenue` means completed
    gateway payments only, everything else gets an honest, different name.

    `daily_consumption` (was `daily_revenue`) and `consumption_by_model`
    (was `revenue_by_model`) are renamed to say what they actually are.
    `daily_gateway_revenue` is new: real completed payments per day, mirrored
    from `payments`/`payment_orders` exactly like 81d8240's `total_revenue`
    query -- summing `payments.amount` (integer toman, proven from
    payment.py's `amount: int  # in Tomans` + its Money() wrapping) plus the
    legacy `payment_orders.amount_irr` (integer RIAL, converted /10). Both
    tables are empty in production today (verified via `\\d`/`SELECT
    status, count(*)` against the live DB on 2026-08-22), so this series is
    all zeros right now -- that zero is the truth, not a bug: consumption
    was never zero, gateway revenue always has been.

    The old `daily_revenue`/`revenue_by_model` keys are deliberately NOT
    kept as aliases -- that would perpetuate exactly the naming lie this
    fix exists to remove. The only consumer of this endpoint is
    frontend/app/admin/sections/AnalyticsSection.tsx, updated in the same
    change.
    """
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        # 1) Daily consumption -- what users were charged for usage. This is
        # NOT revenue (see docstring above). generate_series fills zero days.
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
        daily_consumption = [{'day': str(r._mapping['day']), 'amount': int(r._mapping['amount'])}
                             for r in res_rev.fetchall()]

        # 1b) Daily GATEWAY revenue -- actual completed payments per day,
        # never derived from usage_events. Same payments/payment_orders
        # union and toman conversion as 81d8240's total_revenue query.
        res_gw = await session.execute(sqlalchemy.text("""
            WITH dates AS (
                SELECT generate_series(
                    (NOW() - INTERVAL '30 days')::date,
                    NOW()::date,
                    '1 day'
                )::date AS day
            ),
            gateway AS (
                SELECT DATE(verified_at) AS day, amount AS amount_toman
                FROM payments
                WHERE status = 'completed' AND verified_at IS NOT NULL
                UNION ALL
                SELECT DATE(completed_at) AS day, amount_irr / 10 AS amount_toman
                FROM payment_orders
                WHERE status = 'completed' AND completed_at IS NOT NULL
            )
            SELECT d.day::text AS day,
                   COALESCE(SUM(g.amount_toman), 0) AS amount
            FROM dates d
            LEFT JOIN gateway g ON g.day = d.day
            GROUP BY d.day
            ORDER BY d.day
        """))
        daily_gateway_revenue = [{'day': str(r._mapping['day']), 'amount': int(r._mapping['amount'])}
                                 for r in res_gw.fetchall()]

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

        # 4) Consumption by model (current month) -- was "revenue_by_model";
        # this is spend on usage_events, not gateway revenue (see docstring).
        res_models = await session.execute(sqlalchemy.text("""
            SELECT model,
                   SUM(charged_amount) AS consumption,
                   COUNT(DISTINCT user_id) AS users,
                   COUNT(*) AS calls
            FROM usage_events
            WHERE created_at >= DATE_TRUNC('month', NOW())
            GROUP BY model
            ORDER BY consumption DESC
            LIMIT 10
        """))
        consumption_by_model = [{'model': r._mapping['model'],
                                 'consumption': int(r._mapping['consumption']),
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
        'daily_consumption': daily_consumption,
        'daily_gateway_revenue': daily_gateway_revenue,
        'daily_users': daily_users,
        'daily_tokens': daily_tokens,
        'consumption_by_model': consumption_by_model,
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


