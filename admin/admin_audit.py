"""


Admin panel audit logs: audit page and API endpoints.
from fastapi.responses import HTMLResponse
"""
from __future__ import annotations

from fastapi.responses import HTMLResponse
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Request, Query

from admin_config import (
    templates, UI, async_session, _redirect_or_html, _require_api_session,
    _json_response, _fetch_all, _fetch_one, _execute, _paginate
)

router = APIRouter()


# ===== Server-rendered pages ===============================================

@router.get('/admin/audit', response_class=HTMLResponse)
async def audit_page(request: Request):
    return _redirect_or_html(request, 'audit.html', {})


# ===== API endpoints (JSON) ================================================

@router.get('/admin/api/audit')
async def api_audit(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    _require_api_session(request)
    page, limit, offset = _paginate(page, limit)
    try:
        async with async_session() as session:
            async with session.begin():
                count_row = await _fetch_one(session, 'SELECT COUNT(*) AS cnt FROM audit_logs')
                total = count_row['cnt'] if count_row else 0

                rows = await _fetch_all(session, """
                                    SELECT id, admin_user_id, action, target_type, target_id, details, created_at
                                    FROM audit_logs
                                """)

                return _json_response({'items': rows, 'total': total, 'page': page, 'limit': limit})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.post('/admin/api/audit')
async def api_audit_create(request: Request):
    _require_api_session(request)
    body = await request.json()
    action = body.get('action', '')
    details = body.get('details', '')
    user_id = body.get('user_id')
    target_type = body.get('target_type')
    target_id = body.get('target_id')

    try:
        async with async_session() as session:
            async with session.begin():
                await _execute(session,
                    'INSERT INTO audit_logs (admin_user_id, action, target_type, target_id, details, created_at) '
                    'VALUES (:uid, :action, :tt, :ti, :details, :u)',
                    {'uid': user_id, 'action': action, 'tt': target_type, 'ti': target_id, 'details': details,
                     'u': datetime.utcnow()})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)