"""
Admin panel payments: payments page and API endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from admin_config import (
    templates, UI, async_session, _redirect_or_html, _require_api_session,
    _json_response, _fetch_all, _fetch_one, _paginate
)

router = APIRouter()


# ===== Server-rendered pages ===============================================

@router.get('/admin/payments', response_class=HTMLResponse)
async def payments_page(request: Request):
    return _redirect_or_html(request, 'payments.html', {})


# ===== API endpoints (JSON) ================================================

@router.get('/admin/api/payments')
async def api_payments(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    _require_api_session(request)
    page, limit, offset = _paginate(page, limit)
    try:
        async with async_session() as session:
            async with session.begin():
                count_row = await _fetch_one(session, 'SELECT COUNT(*) AS cnt FROM payment_orders')
                total = count_row['cnt'] if count_row else 0

                rows = await _fetch_all(session,
                    'SELECT p.id, u.email AS user_email, p.amount_irr, p.status, p.authority, p.ref_id, p.created_at '
                    'FROM payment_orders p LEFT JOIN users u ON u.id = p.user_id '
                    'ORDER BY p.created_at DESC LIMIT :limit OFFSET :offset',
                                    {'limit': limit, 'offset': offset})

                return _json_response({'items': rows, 'total': total, 'page': page, 'limit': limit})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)
