"""
Caller-facing usage endpoints (``/me/usage``): monthly totals, per-model
breakdown, daily charts and CSV export for the authenticated user.

These are user-scoped, not admin-scoped — they authorise via ``_get_user_id``
rather than ``admin_required``.
"""
from __future__ import annotations

import csv
import io
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from database import async_session
from dependencies import _get_user_id

router = APIRouter()

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
            # Convenience wrapper matching the frontend's legacy `usage.monthly` shape.
            'monthly': {
                'inp': int(monthly.inp),
                'out': int(monthly.out),
                'spent': float(monthly.spent),
                'count': int(monthly.cnt),
            },
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
