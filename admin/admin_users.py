"""


Admin panel users: users page and API endpoints for user management.
from fastapi.responses import HTMLResponse
"""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from admin_config import (
    templates, UI, async_session, _redirect_or_html, _require_session,
    _require_api_session, _json_response, _execute, _fetch_all, _fetch_one,
    _paginate
)

router = APIRouter()


# ===== Server-rendered pages ===============================================

@router.get('/admin/users', response_class=HTMLResponse)
async def users_page(request: Request):
    users = []
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT u.id, u.email, u.created_at, '
                    'COALESCE(w.balance, 0) AS balance '
                    'FROM users u LEFT JOIN wallet w ON w.user_id = u.id '
                    'ORDER BY u.created_at DESC')
                users = rows
    except Exception:
        pass
    return _redirect_or_html(request, 'users.html', {'users': users})


# ===== Form-based updates (existing) =======================================

@router.post('/admin/users/update')
async def user_update_form(request: Request, item_id: str = Form(...), is_active: str = Form(...)):
    redirect = _require_session(request)
    if isinstance(redirect, RedirectResponse):
        return redirect
    val = is_active.lower() in ['1', 'true', 'on', 'yes']
    try:
        async with async_session() as session:
            async with session.begin():
                pass  # users table has no is_active column
    except Exception:
        pass
    return RedirectResponse(url='/admin/users?updated=1', status_code=302)


# ===== API endpoints (JSON) ================================================

@router.get('/admin/api/users')
async def api_users(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session, """
                    SELECT u.id, u.email, u.created_at,
                        COALESCE(w.balance, 0) AS wallet_balance,
                        (SELECT COUNT(*) FROM usage_events WHERE user_id = u.id) AS usage_count,
                        (SELECT COUNT(*) FROM conversations WHERE user_id = u.id) AS conversation_count
                    FROM users u
                    LEFT JOIN wallet w ON w.user_id = u.id
                    ORDER BY u.created_at DESC
                """)
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.get('/admin/api/users/{user_id}')
async def api_user_detail(request: Request, user_id: int):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                user = await _fetch_one(session,
                    'SELECT id, email, created_at FROM users WHERE id = :id',
                    {'id': user_id})
                if not user:
                    return _json_response({'error': 'User not found'}, 404)

                wallet = await _fetch_one(session,
                    'SELECT balance FROM wallet WHERE user_id = :id', {'id': user_id})
                user['wallet_balance'] = wallet['balance'] if wallet else 0

                usage = await _fetch_all(session,
                    'SELECT id, model, input_tokens, output_tokens, charged_amount, created_at '
                    'FROM usage_events WHERE user_id = :id ORDER BY created_at DESC LIMIT 50',
                    {'id': user_id})

                convos = await _fetch_all(session,
                    'SELECT id, title, model, jsonb_array_length(messages) as message_count, created_at '
                    'FROM conversations WHERE user_id = :id ORDER BY created_at DESC LIMIT 50',
                    {'id': user_id})

                payments = await _fetch_all(session,
                    'SELECT id, amount, status, created_at FROM payments WHERE user_id = :id ORDER BY created_at DESC LIMIT 50',
                    {'id': user_id})

                keys = await _fetch_all(session,
                    'SELECT id, name, key_prefix, active, created_at FROM api_keys WHERE user_id = :id ORDER BY created_at DESC',
                    {'id': user_id})

                user['recent_usage'] = usage
                user['conversations'] = convos
                user['payments'] = payments
                user['api_keys'] = keys

                # Usage by model aggregation
                usage_by_model = await _fetch_all(session, """
                    SELECT model,
                        COALESCE(SUM(input_tokens), 0) AS total_input,
                        COALESCE(SUM(output_tokens), 0) AS total_output,
                        COALESCE(SUM(cached_input_tokens), 0) AS total_cached,
                        COALESCE(SUM(reasoning_tokens), 0) AS total_reasoning,
                        COUNT(*) AS request_count,
                        COALESCE(SUM(charged_amount), 0) AS total_cost
                    FROM usage_events WHERE user_id = :id
                    GROUP BY model ORDER BY total_cost DESC
                """, {'id': user_id})

                # Model catalog pricing for reference
                pricing = await _fetch_all(session, """
                    SELECT id, display_name, input_per_million, output_per_million, currency
                    FROM model_catalog WHERE availability = 'available'
                    ORDER BY display_name
                """)

                user['usage_by_model'] = usage_by_model
                user['pricing'] = pricing
                return _json_response(user)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)