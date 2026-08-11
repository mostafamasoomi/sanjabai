"""
Admin panel dashboard: stats overview page and API endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from admin_config import (
    templates, UI, async_session, _redirect_or_html, _require_api_session,
    _json_response, _fetch_one
)

router = APIRouter()


# ===== Server-rendered pages ===============================================

@router.get('/admin', response_class=HTMLResponse)
@router.get('/admin/dashboard', response_class=HTMLResponse)
async def dashboard_page(request: Request):
    stats = {}
    try:
        async with async_session() as session:
            async with session.begin():
                row = await _fetch_one(session, """
                    SELECT
                        (SELECT COUNT(*) FROM users) AS total_users,
                        (SELECT COUNT(*) FROM users) AS active_users,
                        (SELECT COUNT(*) FROM conversations) AS total_conversations,
                        (SELECT COUNT(*) FROM usage_events) AS total_usage_events,
                        (SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM usage_events) AS total_tokens,
                        (SELECT COALESCE(SUM(charged_amount), 0) FROM usage_events) AS total_revenue,
                        (SELECT COALESCE(SUM(balance), 0) FROM wallet) AS total_wallet_balance,
                        (SELECT COUNT(*) FROM payment_orders WHERE status = 'pending') AS total_pending_payments
                """)
                stats = row or {}
    except Exception:
        stats = {
            'total_users': 0, 'active_users': 0, 'total_conversations': 0,
            'total_usage_events': 0, 'total_tokens': 0, 'total_revenue': 0,
            'total_wallet_balance': 0, 'total_pending_payments': 0,
        }
    return _redirect_or_html(request, 'dashboard.html', {'stats': stats})


# ===== API endpoints (JSON) ================================================

@router.get('/admin/api/stats')
async def api_stats(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                row = await _fetch_one(session, """
                    SELECT
                        (SELECT COUNT(*) FROM users) AS total_users,
                        (SELECT COUNT(*) FROM users) AS active_users,
                        (SELECT COUNT(*) FROM conversations) AS total_conversations,
                        (SELECT COUNT(*) FROM usage_events) AS total_usage_events,
                        (SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM usage_events) AS total_tokens,
                        (SELECT COALESCE(SUM(charged_amount), 0) FROM usage_events) AS total_revenue,
                        (SELECT COALESCE(SUM(balance), 0) FROM wallet) AS total_wallet_balance,
                        (SELECT COUNT(*) FROM payment_orders WHERE status = 'pending') AS total_pending_payments
                """)
                return _json_response(row or {})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)
