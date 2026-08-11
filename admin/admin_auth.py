"""
Admin panel authentication: login, logout, session management.
"""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from admin_config import (
    templates, UI, FAKE_USERS, ADMIN_PASS,
    sessions, SESSION_EXPIRY, SESSION_COOKIE,
    _session_token, _require_session, _redirect_or_html
)

router = APIRouter()


# ===== Auth ================================================================

@router.get('/admin/login', response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    return templates.TemplateResponse('login.html', {
        'request': request, 'ui': UI, 'error': error,
    })


@router.post('/admin/login')
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not ADMIN_PASS:
        return templates.TemplateResponse('login.html', {
            'request': request, 'ui': UI, 'error': 'ورود غیرفعال است',
        })
    user = FAKE_USERS.get(username)
    if not user or user['password'] != password:
        return templates.TemplateResponse('login.html', {
            'request': request, 'ui': UI, 'error': 'نام کاربری یا رمز عبور اشتباه است',
        })
    token = _session_token()
    sessions[token] = {
        'username': username,
        'display': user['display'],
        'expires_at': datetime.utcnow() + SESSION_EXPIRY,
    }
    response = RedirectResponse(url='/admin/dashboard', status_code=302)
    response.set_cookie(SESSION_COOKIE, token, httponly=True)
    return response


@router.get('/admin/logout')
async def logout(request: Request):
    response = RedirectResponse(url='/admin/login', status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    token = request.cookies.get(SESSION_COOKIE)
    if token and token in sessions:
        sessions.pop(token, None)
    return response
