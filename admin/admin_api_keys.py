"""


Admin panel API keys: api_keys page and API endpoints.
from fastapi.responses import HTMLResponse
"""
from __future__ import annotations

from fastapi.responses import HTMLResponse
from fastapi import APIRouter, Request

from admin_config import (
    templates, UI, async_session, _redirect_or_html, _require_api_session,
    _json_response, _fetch_all
)

router = APIRouter()


# ===== Server-rendered pages ===============================================

@router.get('/admin/api-keys', response_class=HTMLResponse)
async def api_keys_page(request: Request):
    return _redirect_or_html(request, 'api_keys.html', {})


# ===== API endpoints (JSON) ================================================

@router.get('/admin/api/api-keys')
async def api_api_keys(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session, """
                    SELECT k.id, k.user_id, k.name, k.key_prefix, k.active, k.created_at,
                        u.email AS user_email
                    FROM api_keys k
                    LEFT JOIN users u ON u.id = k.user_id
                    ORDER BY k.created_at DESC
                """)
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)