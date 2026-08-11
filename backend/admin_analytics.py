"""
Admin reporting: CSV data exports, dashboard aggregates, and the 30-day
timeseries powering the admin charts.
"""
from __future__ import annotations

import csv
import io

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from database import async_session
from models import Ledger
from dependencies import admin_required, _write_audit_log

router = APIRouter()

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
