"""
Admin panel conversations: conversations page and API endpoints.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from admin_config import (
    templates, UI, async_session, _redirect_or_html, _require_api_session,
    _json_response, _fetch_all, _fetch_one, _paginate
)

router = APIRouter()


# ===== Server-rendered pages ===============================================

@router.get('/admin/conversations', response_class=HTMLResponse)
async def conversations_page(request: Request):
    return _redirect_or_html(request, 'conversations.html', {})


# ===== API endpoints (JSON) ================================================

@router.get('/admin/api/conversations')
async def api_conversations(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user_id: Optional[int] = None,
):
    _require_api_session(request)
    page, limit, offset = _paginate(page, limit)
    try:
        async with async_session() as session:
            async with session.begin():
                where = []
                params = {'lim': limit, 'off': offset}
                if user_id:
                    where.append('c.user_id = :uid')
                    params['uid'] = user_id
                where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

                count_row = await _fetch_one(session,
                    f'SELECT COUNT(*) AS cnt FROM conversations c {where_sql}', params)
                total = count_row['cnt'] if count_row else 0

                rows = await _fetch_all(session,
                    f'SELECT c.id, c.user_id, u.email AS user_email, c.title, c.model, '
                    f'jsonb_array_length(c.messages) AS message_count, c.created_at '
                    f'FROM conversations c LEFT JOIN users u ON u.id = c.user_id '
                    f'{where_sql} ORDER BY c.created_at DESC LIMIT :lim OFFSET :off', params)

                return _json_response({'items': rows, 'total': total, 'page': page, 'limit': limit})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.get('/admin/api/conversations/{conv_id}')
async def api_conversation_detail(request: Request, conv_id: int):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                convo = await _fetch_one(session,
                    'SELECT id, user_id, title, model, created_at FROM conversations WHERE id = :id',
                    {'id': conv_id})
                if not convo:
                    return _json_response({'error': 'Conversation not found'}, 404)

                # Messages are stored as JSONB in conversations table
                msg_row = await _fetch_one(session,
                    'SELECT messages FROM conversations WHERE id = :id',
                    {'id': conv_id})
                convo['messages'] = msg_row.get('messages', []) if msg_row and msg_row.get('messages') else []

                return _json_response(convo)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.get('/admin/api/users/{user_id}/conversations')
async def api_user_conversations(request: Request, user_id: int):
    """Return all conversations for a user with full messages."""
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                convos = await _fetch_all(session, """
                    SELECT id, title, model, messages,
                        jsonb_array_length(messages) AS message_count, created_at
                    FROM conversations WHERE user_id = :id
                    ORDER BY created_at DESC
                """, {'id': user_id})
                return _json_response(convos)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)