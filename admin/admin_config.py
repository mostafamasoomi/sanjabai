"""
Admin panel config: DB engine, templates, UI strings, session helpers, shared utilities.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
import os
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql+asyncpg://sanjabai:sanjabai@sanjabai_pg:5432/sanjabai'
)
SECRET_KEY = os.getenv('ADMIN_SECRET_KEY', '')
if not SECRET_KEY:
    raise RuntimeError('ADMIN_SECRET_KEY must be set in environment; refusing to start with insecure default')
SESSION_COOKIE = 'admin_session'
ADMIN_USER = os.getenv('ADMIN_USER', '')
ADMIN_PASS = os.getenv('ADMIN_PASS', '')
if not ADMIN_USER or not ADMIN_PASS:
    raise RuntimeError('ADMIN_USER and ADMIN_PASS must be set in environment; refusing to start with defaults')

FAKE_USERS = {}
if ADMIN_PASS:
    FAKE_USERS[ADMIN_USER] = {'password': ADMIN_PASS, 'display': 'مدیر'}

# ---------------------------------------------------------------------------
# DB engine
# ---------------------------------------------------------------------------
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession)

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
templates = Jinja2Templates(directory='/app/templates')

# ---------------------------------------------------------------------------
# Persian UI strings
# ---------------------------------------------------------------------------
UI = {
    'brand': 'دروازه هوش مصنوعی فارسی',
    'login_title': 'ورود مدیر',
    'login_heading': 'ورود به پنل مدیریت',
    'username_label': 'نام کاربری',
    'password_label': 'رمز عبور',
    'login_button': 'ورود',
    'nav_dashboard': 'داشبورد',
    'nav_pricing': 'قیمتگذاری',
    'nav_models': 'مدلها',
    'nav_users': 'کاربران',
    'nav_usage': 'مصرف',
    'nav_conversations': 'مکالمات',
    'nav_payments': 'پرداخت‌ها',
    'nav_api_keys': 'کلیدهای API',
    'nav_audit': 'لاگ‌ها',
    'nav_notifications': 'اعلان‌ها',
    'logout': 'خروج',
    'welcome': 'خوش آمدید',
    'admin_panel': 'پنل مدیریت',
}

# ---------------------------------------------------------------------------
# Sessions (in-memory)
# ---------------------------------------------------------------------------
sessions: dict = {}
SESSION_EXPIRY = timedelta(hours=8)


# ===== Helpers =============================================================

def _session_token() -> str:
    return secrets.token_urlsafe(32)


def _require_session(request: Request):
    """Returns username if valid, RedirectResponse if not."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token or token not in sessions:
        return RedirectResponse(url='/admin/login', status_code=302)
    if sessions[token]['expires_at'] < datetime.utcnow():
        sessions.pop(token, None)
        return RedirectResponse(url='/admin/login', status_code=302)
    return sessions[token]['username']


def _redirect_or_html(request: Request, template: str, context: dict):
    redirect = _require_session(request)
    if isinstance(redirect, RedirectResponse):
        return redirect
    ctx = {'request': request, 'ui': UI, 'username': redirect, **context}
    return templates.TemplateResponse(template, ctx)


def _require_api_session(request: Request) -> str:
    """Returns username or raises 401."""
    result = _require_session(request)
    if isinstance(result, RedirectResponse):
        raise HTTPException(status_code=401, detail='Unauthorized')
    return result


def _paginate(page: int, limit: int):
    limit = max(1, min(limit, 200))
    page = max(1, page)
    offset = (page - 1) * limit
    return page, limit, offset


def _json_serial(obj):
    from decimal import Decimal as _Decimal
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _Decimal):
        return float(obj)
    if isinstance(obj, (bytes, memoryview)):
        return obj.hex() if isinstance(obj, bytes) else bytes(obj).hex()
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f'Type {type(obj)} not serializable')


async def _fetch_all(session, query, params=None):
    try:
        result = await session.execute(text(query), params or {})
        return [dict(r) for r in result.mappings().all()]
    except Exception as e:
        return []


async def _fetch_one(session, query, params=None):
    try:
        result = await session.execute(text(query), params or {})
        row = result.mappings().first()
        return dict(row) if row else None
    except Exception as e:
        return None


async def _execute(session, query, params=None):
    try:
        await session.execute(text(query), params or {})
        return True
    except Exception as e:
        return False


def _json_response(data, status=200):
    body = json.dumps(data, default=_json_serial)
    return Response(content=body, status_code=status, media_type='application/json')