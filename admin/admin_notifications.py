"""


Admin panel notifications: notifications page and API endpoints.
from fastapi.responses import HTMLResponse
"""
from __future__ import annotations

from fastapi.responses import HTMLResponse
from fastapi import APIRouter, Request

from admin_config import (
    templates, UI, async_session, _redirect_or_html, _require_api_session,
    _json_response, _fetch_all, _execute
)

router = APIRouter()


# ===== Server-rendered pages ===============================================

@router.get('/admin/notifications', response_class=HTMLResponse)
async def notifications_page(request: Request):
    return _redirect_or_html(request, 'notifications.html', {})


# ===== API endpoints (JSON) ================================================

@router.get('/admin/api/notifications')
async def api_notifications(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, user_id, type, title, body, read, created_at '
                    'FROM notifications ORDER BY created_at DESC')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.post('/admin/api/notifications/{notif_id}/read')
async def api_notification_read(request: Request, notif_id: int):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                await _execute(session, 'UPDATE notifications SET read=true WHERE id=:id', {'id': notif_id})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)