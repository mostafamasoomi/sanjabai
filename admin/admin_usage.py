"""
Admin panel usage: usage page and API endpoints for global usage analytics.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from admin_config import (
    async_session, _require_api_session, _json_response, _fetch_all, _fetch_one,
    _paginate
)

router = APIRouter()


# ===== Server-rendered pages ===============================================

@router.get('/admin/usage', response_class=HTMLResponse)
async def usage_page(request: Request):
    from admin_config import _redirect_or_html
    return _redirect_or_html(request, 'usage.html', {})


# ===== API endpoints (JSON) ================================================

@router.get('/admin/api/usage')
async def api_usage(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user_id: Optional[int] = None,
    model: Optional[str] = None,
):
    _require_api_session(request)
    page, limit, offset = _paginate(page, limit)
    try:
        async with async_session() as session:
            async with session.begin():
                where: list[str] = []
                params: dict = {'lim': limit, 'off': offset}
                if user_id:
                    where.append('user_id = :uid')
                    params['uid'] = user_id
                if model:
                    where.append('model = :model')
                    params['model'] = model
                where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

                count_row = await _fetch_one(session, f'SELECT COUNT(*) AS cnt FROM usage_events {where_sql}', params)
                total = count_row['cnt'] if count_row else 0

                rows = await _fetch_all(session,
                    f'SELECT id, user_id, model, input_tokens, output_tokens, charged_amount, created_at '
                    f'FROM usage_events {where_sql} ORDER BY created_at DESC LIMIT :lim OFFSET :off', params)

                return _json_response({'items': rows, 'total': total, 'page': page, 'limit': limit})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.get('/admin/api/usage/summary')
async def api_usage_summary(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session, """
                    SELECT model,
                        COUNT(*) AS event_count,
                        COALESCE(SUM(input_tokens), 0) AS total_input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS total_output_tokens,
                        COALESCE(SUM(input_tokens + output_tokens), 0) AS total_tokens,
                        COALESCE(SUM(charged_amount), 0) AS total_cost
                    FROM usage_events
                    GROUP BY model
                    ORDER BY total_cost DESC
                """)
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)