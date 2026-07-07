from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
import os
import secrets
from datetime import datetime, timedelta

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql+asyncpg://persian:persian@localhost:5432/persian_gateway'
)
SECRET_KEY = os.getenv('ADMIN_SECRET_KEY', 'admin-placeholder-change-me')
SESSION_COOKIE = 'admin_session'

templates = Jinja2Templates(directory='/app/templates')
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession)

PERSIAN = {
    'login_title': 'ورود مدیر',
    'login_heading': 'ورود به پنل مدیریت',
    'username_label': 'نام کاربری',
    'password_label': 'رمز عبور',
    'login_button': 'ورود',
    'dashboard': 'داشبورد',
    'pricing': 'قیمت‌گذاری',
    'models': 'مدل‌ها',
    'users': 'کاربران',
    'logout': 'خروج',
    'welcome': 'خوش آمدید',
    'admin_panel': 'پنل مدیریت دروازه هوش مصنوعی فارسی',
}

UI = {
    'brand': 'دروازه هوش مصنوعی فارسی',
    'login_title': PERSIAN['login_title'],
    'login_heading': PERSIAN['login_heading'],
    'username_label': PERSIAN['username_label'],
    'password_label': PERSIAN['password_label'],
    'login_button': PERSIAN['login_button'],
    'nav_dashboard': PERSIAN['dashboard'],
    'nav_pricing': PERSIAN['pricing'],
    'nav_models': PERSIAN['models'],
    'nav_users': PERSIAN['users'],
    'logout': PERSIAN['logout'],
    'welcome': PERSIAN['welcome'],
}

FAKE_USERS = {
    'admin': {'password': 'admin', 'display': 'مدیر'},
}

sessions = {}
SESSION_EXPIRY = timedelta(hours=8)

app = FastAPI(title='Persian AI Gateway Admin')


def _session_token() -> str:
    return secrets.token_urlsafe(32)


def _require_session(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token or token not in sessions:
        return RedirectResponse(url='/admin/login', status_code=302)
    if sessions[token]['expires_at'] < datetime.utcnow():
        sessions.pop(token, None)
        return RedirectResponse(url='/admin/login', status_code=302)
    return sessions[token]['username']


@app.get('/admin/login', response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    return templates.TemplateResponse('login.html', {
        'request': request,
        'ui': UI,
        'error': error,
    })


@app.post('/admin/login')
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = FAKE_USERS.get(username)
    if not user or user['password'] != password:
        return templates.TemplateResponse('login.html', {
            'request': request,
            'ui': UI,
            'error': 'نام کاربری یا رمز عبور اشتباه است',
        })
    token = _session_token()
    sessions[token] = {
        'username': username,
        'display': user['display'],
        'expires_at': datetime.utcnow() + SESSION_EXPIRY,
    }
    response = RedirectResponse(url='/admin/pricing', status_code=302)
    response.set_cookie(SESSION_COOKIE, token, httponly=True)
    return response


@app.get('/admin/logout')
async def logout():
    response = RedirectResponse(url='/admin/login', status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    sessions.clear()
    return response


def _redirect_or_html(request: Request, template: str, context: dict):
    redirect = _require_session(request)
    if isinstance(redirect, RedirectResponse):
        return redirect
    ctx = {
        'request': request,
        'ui': UI,
        'username': redirect,
        **context,
    }
    return templates.TemplateResponse(template, ctx)


@app.get('/admin/pricing', response_class=HTMLResponse)
async def pricing_page(request: Request):
    async with async_session() as session:
        async with session.begin():
            rows = (await session.execute(text('SELECT id, provider, model, input_price, output_price, currency, updated_at FROM pricing ORDER BY provider, model'))).mappings().all()
    prices = [dict(r) for r in rows]
    return _redirect_or_html(request, 'pricing.html', {'prices': prices})


@app.get('/admin/models', response_class=HTMLResponse)
async def models_page(request: Request):
    async with async_session() as session:
        async with session.begin():
            rows = (await session.execute(text('SELECT id, provider, model, enabled, priority, created_at FROM models ORDER BY provider, model'))).mappings().all()
    models = [dict(r) for r in rows]
    return _redirect_or_html(request, 'models.html', {'models': models})


@app.get('/admin/users', response_class=HTMLResponse)
async def users_page(request: Request):
    async with async_session() as session:
        async with session.begin():
            rows = (await session.execute(text('SELECT id, username, role, credits, is_active, created_at FROM users ORDER BY username'))).mappings().all()
    users = [dict(r) for r in rows]
    return _redirect_or_html(request, 'users.html', {'users': users})


@app.post('/admin/pricing/update')
async def pricing_update(request: Request, item_id: str = Form(...), input: int = Form(...), output: int = Form(...)):
    redirect = _require_session(request)
    if isinstance(redirect, RedirectResponse):
        return redirect
    async with async_session() as session:
        async with session.begin():
            await session.execute(text('UPDATE pricing SET input_price=:i, output_price=:o, updated_at=:u WHERE id=:id'), {'i': input, 'o': output, 'u': datetime.utcnow(), 'id': item_id})
    return RedirectResponse(url='/admin/pricing?updated=1', status_code=302)


@app.post('/admin/models/toggle')
async def model_toggle(request: Request, item_id: str = Form(...), enabled: str = Form(...)):
    redirect = _require_session(request)
    if isinstance(redirect, RedirectResponse):
        return redirect
    val = enabled.lower() in ['1', 'true', 'on', 'yes']
    async with async_session() as session:
        async with session.begin():
            await session.execute(text('UPDATE models SET enabled=:e WHERE id=:id'), {'e': val, 'id': item_id})
    return RedirectResponse(url='/admin/models?updated=1', status_code=302)


@app.post('/admin/users/update')
async def user_update(request: Request, item_id: str = Form(...), credits: int = Form(...), is_active: str = Form(...)):
    redirect = _require_session(request)
    if isinstance(redirect, RedirectResponse):
        return redirect
    val = is_active.lower() in ['1', 'true', 'on', 'yes']
    async with async_session() as session:
        async with session.begin():
            await session.execute(text('UPDATE users SET credits=:c, is_active=:a WHERE id=:id'), {'c': credits, 'a': val, 'id': item_id})
    return RedirectResponse(url='/admin/users?updated=1', status_code=302)
