"""
Conversation CRUD, search, analytics, and export endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from database import async_session
from models import Conversation, UsageEvent
from dependencies import _get_user_id

router = APIRouter()


class ConvCreate(BaseModel):
    title: str = 'گفتگوی جدید'
    model: str = ''
    messages: list[dict[str, Any]] = []


class ConvUpdate(BaseModel):
    title: str | None = None
    messages: list[dict[str, Any]] | None = None


@router.get('/conversations')
async def list_conversations(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    page = int(request.query_params.get('page', 1))
    limit = min(int(request.query_params.get('limit', 20)), 100)
    offset = (page - 1) * limit
    async with async_session() as session:
        count_res = await session.execute(
            sqlalchemy.text('SELECT COUNT(*) as c FROM conversations WHERE user_id = :uid'),
            {'uid': uid}
        )
        total = count_res.fetchone().c
        res = await session.execute(
            sqlalchemy.text(
                'SELECT id, title, model, created_at, updated_at FROM conversations '
                'WHERE user_id = :uid ORDER BY updated_at DESC OFFSET :off LIMIT :lim'
            ),
            {'uid': uid, 'off': offset, 'lim': limit},
        )
        rows = [{'id': r.id, 'title': r.title, 'model': r.model, 'created_at': r.created_at, 'updated_at': r.updated_at} for r in res.fetchall()]
    return JSONResponse(jsonable_encoder({'items': rows, 'total': total, 'page': page, 'limit': limit}))


@router.post('/conversations')
async def create_conversation(request: Request, payload: ConvCreate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        conv = Conversation(user_id=uid, title=payload.title, model=payload.model, messages=payload.messages)
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return JSONResponse(jsonable_encoder({'id': conv.id, 'title': conv.title, 'model': conv.model, 'messages': conv.messages, 'created_at': conv.created_at}))


@router.get('/conversations/search')
async def search_conversations(request: Request, q: str = '') -> JSONResponse:
    """Search conversations by title or message content for the current user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        if q:
            search_sql = sqlalchemy.text(
                """
                SELECT DISTINCT c.id, c.user_id, c.title, c.model, c.created_at, c.updated_at
                FROM conversations c
                WHERE c.user_id = :uid
                  AND (
                    c.title ILIKE :pat
                    OR EXISTS (
                      SELECT 1 FROM jsonb_array_elements(c.messages) AS msg
                      WHERE msg->>'content' ILIKE :pat
                    )
                  )
                ORDER BY c.updated_at DESC
                LIMIT 50
                """
            )
            res = await session.execute(search_sql, {'uid': uid, 'pat': f'%{q}%'})
            rows = [dict(r._mapping) for r in res.fetchall()]
        else:
            res = await session.execute(
                sqlalchemy.text(
                    'SELECT id, title, model, created_at, updated_at FROM conversations '
                    'WHERE user_id = :uid ORDER BY updated_at DESC LIMIT 50'
                ),
                {'uid': uid},
            )
            rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.get('/conversations/analytics')
async def conversation_analytics(request: Request) -> JSONResponse:
    """Return conversation usage analytics for the current user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    try:
        async with async_session() as session:
            conv_count_res = await session.execute(
                sqlalchemy.text('SELECT COUNT(*) as c FROM conversations WHERE user_id = :uid'),
                {'uid': uid},
            )
            total_conversations = conv_count_res.fetchone().c or 0

            msg_count_res = await session.execute(
                sqlalchemy.text(
                    "SELECT COALESCE(SUM(jsonb_array_length(CASE WHEN messages IS NOT NULL THEN messages ELSE '[]'::jsonb END)), 0) as c "
                    "FROM conversations WHERE user_id = :uid"
                ),
                {'uid': uid},
            )
            total_messages = msg_count_res.fetchone().c or 0

            usage_res = await session.execute(
                sqlalchemy.text(
                    """SELECT
                        COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                        COALESCE(SUM(charged_amount), 0) as total_cost
                    FROM usage_events WHERE user_id = :uid"""
                ),
                {'uid': uid},
            )
            usage_row = usage_res.fetchone()
            total_tokens_used = usage_row.total_tokens if usage_row else 0
            total_cost = usage_row.total_cost if usage_row else 0

            models_res = await session.execute(
                sqlalchemy.text(
                    """SELECT model, COUNT(*) as calls,
                        SUM(input_tokens + output_tokens) as tokens,
                        SUM(charged_amount) as cost
                    FROM usage_events WHERE user_id = :uid
                    GROUP BY model ORDER BY calls DESC"""
                ),
                {'uid': uid},
            )
            models_used = {}
            for r in models_res.fetchall():
                models_used[r.model] = {'calls': r.calls, 'tokens': r.tokens, 'cost': r.cost}

            daily_res = await session.execute(
                sqlalchemy.text(
                    """SELECT
                        DATE(created_at) as day,
                        COUNT(*) as calls,
                        SUM(input_tokens + output_tokens) as tokens,
                        SUM(charged_amount) as cost
                    FROM usage_events
                    WHERE user_id = :uid AND created_at >= NOW() - INTERVAL '30 days'
                    GROUP BY DATE(created_at)
                    ORDER BY day DESC"""
                ),
                {'uid': uid},
            )
            daily_usage = {}
            for r in daily_res.fetchall():
                day_str = r.day.isoformat() if hasattr(r.day, 'isoformat') else str(r.day)
                daily_usage[day_str] = {'calls': r.calls, 'tokens': r.tokens, 'cost': r.cost}

        return JSONResponse({
            'total_conversations': int(total_conversations),
            'total_messages': int(total_messages),
            'total_tokens_used': int(total_tokens_used),
            'total_cost': float(total_cost),
            'models_used': {m: {'calls': int(v['calls']), 'tokens': int(v['tokens']), 'cost': float(v['cost'])} for m, v in models_used.items()},
            'daily_usage': {d: {'calls': int(v['calls']), 'tokens': int(v['tokens']), 'cost': float(v['cost'])} for d, v in daily_usage.items()},
        })
    except Exception as e:
        return JSONResponse({'detail': f'analytics error: {e}'}, status_code=500)


@router.get('/conversations/{conv_id}')
async def get_conversation(request: Request, conv_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Conversation.__table__.select().where(Conversation.id == conv_id, Conversation.user_id == uid))
        conv = res.fetchone()
        if not conv:
            return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        return JSONResponse(jsonable_encoder({'id': conv.id, 'title': conv.title, 'model': conv.model, 'messages': conv.messages, 'created_at': conv.created_at}))


@router.put('/conversations/{conv_id}')
async def update_conversation(request: Request, conv_id: int, payload: ConvUpdate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Conversation.__table__.select().where(Conversation.id == conv_id, Conversation.user_id == uid))
        conv = res.fetchone()
        if not conv:
            return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        update_data = {}
        if payload.title is not None:
            update_data['title'] = payload.title
        if payload.messages is not None:
            update_data['messages'] = payload.messages
        if update_data:
            update_data['updated_at'] = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.execute(
                Conversation.__table__.update().where(Conversation.id == conv_id),
                update_data
            )
            await session.commit()
        return JSONResponse({'status': 'ok'})


@router.delete('/conversations/{conv_id}')
async def delete_conversation(request: Request, conv_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Conversation.__table__.select().where(Conversation.id == conv_id, Conversation.user_id == uid))
        conv = res.fetchone()
        if not conv:
            return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        await session.execute(Conversation.__table__.delete().where(Conversation.id == conv_id))
        await session.commit()
    return JSONResponse({'status': 'deleted'})


@router.get('/conversations/{conv_id}/export')
async def export_conversation(
    request: Request, conv_id: int, format: str = 'json'
) -> Response:
    """Export a conversation in JSON, Markdown, or plain text format."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            Conversation.__table__.select().where(
                Conversation.id == conv_id, Conversation.user_id == uid
            )
        )
        conv = res.fetchone()
        if not conv:
            return JSONResponse({'detail': 'یافت نشد'}, status_code=404)

    messages = conv.messages or []
    title = conv.title or 'Conversation'
    created = conv.created_at.isoformat() if conv.created_at else ''
    model = conv.model or ''

    if format == 'json':
        data = {'id': conv.id, 'title': title, 'model': model, 'created_at': created, 'messages': messages}
        return JSONResponse(jsonable_encoder(data))

    elif format == 'markdown':
        lines = [f'# {title}', '']
        if model:
            lines.append(f'**Model:** {model}')
        if created:
            lines.append(f'**Created:** {created}')
        lines.extend(['', '---', ''])
        for msg in messages:
            role = msg.get('role', 'unknown') if isinstance(msg, dict) else 'unknown'
            content = msg.get('content', '') if isinstance(msg, dict) else str(msg)
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        parts.append(part.get('text', ''))
                content = '\n'.join(parts)
            role_label = {'user': '🧑 User', 'assistant': '🤖 Assistant', 'system': '⚙️ System'}.get(role, role.title())
            lines.append(f'## {role_label}')
            lines.append('')
            lines.append(content)
            lines.extend(['', '---', ''])
        md_content = '\n'.join(lines)
        return Response(
            content=md_content,
            media_type='text/markdown; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="conversation-{conv_id}.md"'},
        )

    elif format == 'text':
        lines = [f'Title: {title}', '']
        if model:
            lines.append(f'Model: {model}')
        if created:
            lines.append(f'Created: {created}')
        lines.append('')
        for msg in messages:
            role = msg.get('role', 'unknown') if isinstance(msg, dict) else 'unknown'
            content = msg.get('content', '') if isinstance(msg, dict) else str(msg)
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        parts.append(part.get('text', ''))
                content = '\n'.join(parts)
            role_label = {'user': 'User', 'assistant': 'Assistant', 'system': 'System'}.get(role, role.title())
            lines.append(f'[{role_label}]')
            lines.append(content)
            lines.append('')
        text_content = '\n'.join(lines)
        return Response(
            content=text_content,
            media_type='text/plain; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="conversation-{conv_id}.txt"'},
        )

    else:
        return JSONResponse(
            {'detail': f'unsupported format: {format}. Use json, markdown, or text.'},
            status_code=400,
        )
