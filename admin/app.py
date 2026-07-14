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
    'postgresql+asyncpg://multiai:multiai@multiai_pg:5432/multiai'
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

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title='MultiAPI Admin')
app.mount('/static', StaticFiles(directory='/app/static'), name='static')


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


# ===== Health ==============================================================

@app.get('/health')
async def health():
    return {'status': 'ok'}


# ===== Auth ================================================================

@app.get('/admin/login', response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    return templates.TemplateResponse('login.html', {
        'request': request, 'ui': UI, 'error': error,
    })


@app.post('/admin/login')
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


@app.get('/admin/logout')
async def logout(request: Request):
    response = RedirectResponse(url='/admin/login', status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    token = request.cookies.get(SESSION_COOKIE)
    if token and token in sessions:
        sessions.pop(token, None)
    return response


# ===== Server-rendered pages ===============================================

@app.get('/admin', response_class=HTMLResponse)
@app.get('/admin/dashboard', response_class=HTMLResponse)
async def dashboard_page(request: Request):
    stats = {}
    try:
        async with async_session() as session:
            async with session.begin():
                row = await _fetch_one(session, """
                    SELECT
                        (SELECT COUNT(*) FROM users) AS total_users,
                        (SELECT COUNT(*) FROM users) AS active_users,
                        (SELECT COUNT(*) FROM conversations) AS total_conversations,
                        (SELECT COUNT(*) FROM usage_events) AS total_usage_events,
                        (SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM usage_events) AS total_tokens,
                        (SELECT COALESCE(SUM(charged_amount), 0) FROM usage_events) AS total_revenue,
                        (SELECT COALESCE(SUM(balance), 0) FROM wallet) AS total_wallet_balance,
                        (SELECT COUNT(*) FROM payment_orders WHERE status = 'pending') AS total_pending_payments
                """)
                stats = row or {}
    except Exception:
        stats = {
            'total_users': 0, 'active_users': 0, 'total_conversations': 0,
            'total_usage_events': 0, 'total_tokens': 0, 'total_revenue': 0,
            'total_wallet_balance': 0, 'total_pending_payments': 0,
        }
    return _redirect_or_html(request, 'dashboard.html', {'stats': stats})


@app.get('/admin/pricing', response_class=HTMLResponse)
async def pricing_page(request: Request):
    prices = []
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, provider, model, input_per_million, output_per_million, currency, updated_at '
                    'FROM pricing ORDER BY provider, model')
                prices = rows
    except Exception:
        pass
    return _redirect_or_html(request, 'pricing.html', {'prices': prices})


@app.get('/admin/models', response_class=HTMLResponse)
async def models_page(request: Request):
    models = []
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, provider, display_name, provider_model_id, availability, context_window, input_per_million, output_per_million, updated_at '
                    'FROM model_catalog ORDER BY provider, display_name')
                models = rows
    except Exception:
        pass
    return _redirect_or_html(request, 'models.html', {'models': models})


@app.get('/admin/users', response_class=HTMLResponse)
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


@app.get('/admin/usage', response_class=HTMLResponse)
async def usage_page(request: Request):
    return _redirect_or_html(request, 'usage.html', {})


@app.get('/admin/conversations', response_class=HTMLResponse)
async def conversations_page(request: Request):
    return _redirect_or_html(request, 'conversations.html', {})


@app.get('/admin/payments', response_class=HTMLResponse)
async def payments_page(request: Request):
    return _redirect_or_html(request, 'payments.html', {})


@app.get('/admin/api-keys', response_class=HTMLResponse)
async def api_keys_page(request: Request):
    return _redirect_or_html(request, 'api_keys.html', {})


@app.get('/admin/audit', response_class=HTMLResponse)
async def audit_page(request: Request):
    return _redirect_or_html(request, 'audit.html', {})


@app.get('/admin/notifications', response_class=HTMLResponse)
async def notifications_page(request: Request):
    return _redirect_or_html(request, 'notifications.html', {})


@app.get('/admin/discounts', response_class=HTMLResponse)
async def discounts_page(request: Request):
    return _redirect_or_html(request, 'discounts.html', {})


@app.get('/admin/features', response_class=HTMLResponse)
async def features_page(request: Request):
    return _redirect_or_html(request, 'features.html', {})


@app.get('/admin/settings', response_class=HTMLResponse)
async def settings_page(request: Request):
    return _redirect_or_html(request, 'settings.html', {})


# ===== Form-based updates (existing) =======================================

@app.post('/admin/pricing/update')
async def pricing_update(request: Request, item_id: str = Form(...), input: int = Form(...), output: int = Form(...)):
    redirect = _require_session(request)
    if isinstance(redirect, RedirectResponse):
        return redirect
    try:
        async with async_session() as session:
            async with session.begin():
                await _execute(session,
                    'UPDATE pricing SET input_per_million=:i, output_per_million=:o, updated_at=:u WHERE id=:id',
                    {'i': input, 'o': output, 'u': datetime.utcnow(), 'id': item_id})
    except Exception:
        pass
    return RedirectResponse(url='/admin/pricing?updated=1', status_code=302)


@app.post('/admin/models/toggle')
async def model_toggle_form(request: Request, item_id: str = Form(...), enabled: str = Form(...)):
    redirect = _require_session(request)
    if isinstance(redirect, RedirectResponse):
        return redirect
    val = enabled.lower() in ['1', 'true', 'on', 'yes']
    try:
        async with async_session() as session:
            async with session.begin():
                new_avail = 'available' if val else 'disabled'
                await session.execute(text('UPDATE model_catalog SET availability=:e WHERE id=:id'), {'e': new_avail, 'id': item_id})
    except Exception:
        pass
    return RedirectResponse(url='/admin/models?updated=1', status_code=302)


@app.post('/admin/users/update')
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
# All require session auth via _require_api_session

# --- Stats ---

@app.get('/admin/api/stats')
async def api_stats(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                row = await _fetch_one(session, """
                    SELECT
                        (SELECT COUNT(*) FROM users) AS total_users,
                        (SELECT COUNT(*) FROM users) AS active_users,
                        (SELECT COUNT(*) FROM conversations) AS total_conversations,
                        (SELECT COUNT(*) FROM usage_events) AS total_usage_events,
                        (SELECT COALESCE(SUM(input_tokens + output_tokens), 0) FROM usage_events) AS total_tokens,
                        (SELECT COALESCE(SUM(charged_amount), 0) FROM usage_events) AS total_revenue,
                        (SELECT COALESCE(SUM(balance), 0) FROM wallet) AS total_wallet_balance,
                        (SELECT COUNT(*) FROM payment_orders WHERE status = 'pending') AS total_pending_payments
                """)
                return _json_response(row or {})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- Users ---

@app.get('/admin/api/users')
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


@app.get('/admin/api/users/{user_id}')
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


# --- Usage ---

@app.get('/admin/api/users/{user_id}/conversations')
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


@app.get('/admin/api/users/{user_id}/usage')
async def api_user_usage(request: Request, user_id: int):
    """Return per-model token usage breakdown for a user."""
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session, """
                    SELECT model,
                        COALESCE(SUM(input_tokens), 0) AS total_input,
                        COALESCE(SUM(output_tokens), 0) AS total_output,
                        COALESCE(SUM(cached_input_tokens), 0) AS total_cached,
                        COALESCE(SUM(reasoning_tokens), 0) AS total_reasoning,
                        COUNT(*) AS request_count,
                        COALESCE(SUM(charged_amount), 0) AS total_cost_irt
                    FROM usage_events WHERE user_id = :uid
                    GROUP BY model ORDER BY total_cost_irt DESC
                """, {'uid': user_id})

                # Also get pricing from model_catalog
                pricing = await _fetch_all(session, """
                    SELECT id, display_name, input_per_million, output_per_million, currency
                    FROM model_catalog WHERE availability = 'available'
                    ORDER BY display_name
                """)

                # Compute totals
                total_input = sum(r.get('total_input', 0) or 0 for r in rows)
                total_output = sum(r.get('total_output', 0) or 0 for r in rows)
                total_requests = sum(r.get('request_count', 0) or 0 for r in rows)
                total_cost = sum(r.get('total_cost_irt', 0) or 0 for r in rows)

                return _json_response({
                    'usage_by_model': rows,
                    'pricing': pricing,
                    'totals': {
                        'total_input': total_input,
                        'total_output': total_output,
                        'total_requests': total_requests,
                        'total_cost_irt': total_cost,
                    }
                })
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- Usage (global) ---

@app.get('/admin/api/usage')
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


@app.get('/admin/api/usage/summary')
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


# --- Conversations ---

@app.get('/admin/api/conversations')
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


@app.get('/admin/api/conversations/{conv_id}')
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


# --- Payments ---

@app.get('/admin/api/payments')
async def api_payments(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    _require_api_session(request)
    page, limit, offset = _paginate(page, limit)
    try:
        async with async_session() as session:
            async with session.begin():
                count_row = await _fetch_one(session, 'SELECT COUNT(*) AS cnt FROM payment_orders')
                total = count_row['cnt'] if count_row else 0

                rows = await _fetch_all(session,
                    'SELECT p.id, u.email AS user_email, p.amount_irr, p.status, p.authority, p.ref_id, p.created_at '
                    'FROM payment_orders p LEFT JOIN users u ON u.id = p.user_id '
                    'ORDER BY p.created_at DESC LIMIT :limit OFFSET :offset',
                                    {'limit': limit, 'offset': offset})

                return _json_response({'items': rows, 'total': total, 'page': page, 'limit': limit})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- Pricing ---

@app.get('/admin/api/pricing')
async def api_pricing(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, model, provider, input_per_million, output_per_million, currency, updated_at '
                    'FROM pricing ORDER BY provider, model')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@app.post('/admin/api/pricing')
async def api_pricing_create(request: Request):
    _require_api_session(request)
    body = await request.json()
    model = body.get('model')
    provider = body.get('provider', '')
    input_per_million = body.get('input_per_million', 0)
    output_per_million = body.get('output_per_million', 0)
    currency = body.get('currency', 'USD')

    if not model:
        return _json_response({'error': 'model is required'}, 400)

    try:
        async with async_session() as session:
            async with session.begin():
                # Try update first, then insert
                existing = await _fetch_one(session,
                    'SELECT id FROM pricing WHERE model = :model AND provider = :provider',
                    {'model': model, 'provider': provider})
                if existing:
                    await _execute(session,
                        'UPDATE pricing SET input_per_million = :i, output_per_million = :o, '
                        'currency = :c, updated_at = :u WHERE id = :id',
                        {'i': input_per_million, 'o': output_per_million, 'c': currency,
                         'u': datetime.utcnow(), 'id': existing['id']})
                else:
                    await _execute(session,
                        'INSERT INTO pricing (model, provider, input_per_million, output_per_million, currency, updated_at) '
                        'VALUES (:model, :provider, :i, :o, :c, :u)',
                        {'model': model, 'provider': provider, 'i': input_per_million,
                         'o': output_per_million, 'c': currency, 'u': datetime.utcnow()})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- Models ---

@app.get('/admin/api/models')
async def api_models(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, provider, display_name, provider_model_id, availability, context_window, input_per_million, output_per_million, updated_at '
                    'FROM model_catalog ORDER BY provider, display_name')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@app.post('/admin/api/models/{model_id}/toggle')
async def api_model_toggle(request: Request, model_id: str):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                model = await _fetch_one(session,
                    'SELECT id, availability FROM model_catalog WHERE id = :id', {'id': model_id})
                if not model:
                    return _json_response({'error': 'Model not found'}, 404)
                new_val = 'disabled' if model['availability'] == 'available' else 'available'
                await _execute(session,
                    'UPDATE model_catalog SET availability = :e WHERE id = :id',
                    {'e': new_val, 'id': model_id})
                return _json_response({'ok': True, 'availability': new_val})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- API Keys ---

@app.get('/admin/api/api-keys')
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


# --- Audit Logs ---

@app.get('/admin/api/audit')
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


@app.post('/admin/api/audit')
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


# --- Features ---

@app.get('/admin/api/features')
async def api_features(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, title, description, icon, active, order_idx, updated_at FROM features ORDER BY order_idx')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@app.post('/admin/api/features')
async def api_features_create(request: Request):
    _require_api_session(request)
    body = await request.json()
    fid = body.get('id')
    title = body.get('title', '')
    description = body.get('description', '')
    icon = body.get('icon', '')
    active = body.get('active', True)
    order_idx = body.get('order_idx', 0)

    if not title:
        return _json_response({'error': 'title is required'}, 400)

    try:
        async with async_session() as session:
            async with session.begin():
                if fid:
                    await _execute(session,
                        'UPDATE features SET title = :t, description = :d, icon = :i, active = :a, order_idx = :o, updated_at = :c WHERE id = :id',
                        {'t': title, 'd': description, 'i': icon, 'a': active, 'o': order_idx, 'c': datetime.utcnow(), 'id': fid})
                else:
                    await _execute(session,
                        'INSERT INTO features (title, description, icon, active, order_idx, updated_at) VALUES (:t, :d, :i, :a, :o, :c)',
                        {'t': title, 'd': description, 'i': icon, 'a': active, 'o': order_idx, 'c': datetime.utcnow()})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@app.delete('/admin/api/features/{feature_id}')
async def api_features_delete(request: Request, feature_id: int):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                await _execute(session, 'DELETE FROM features WHERE id = :id', {'id': feature_id})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- Discounts ---

@app.get('/admin/api/discounts')
async def api_discounts(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, code, percent, active, expires_at, updated_at '
                    'FROM discounts ORDER BY id')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@app.post('/admin/api/discounts')
async def api_discounts_create(request: Request):
    _require_api_session(request)
    body = await request.json()
    did = body.get('id')
    code = body.get('code', '')
    percent = body.get('percent', 0)
    expires_at = body.get('expires_at')
    active = body.get('active', True)

    if not code:
        return _json_response({'error': 'code is required'}, 400)

    try:
        async with async_session() as session:
            async with session.begin():
                if did:
                    await _execute(session,
                        'UPDATE discounts SET code = :c, percent = :p, expires_at = :e, active = :a, updated_at = :u WHERE id = :id',
                        {'c': code, 'p': percent, 'e': expires_at, 'a': active, 'u': datetime.utcnow(), 'id': did})
                else:
                    await _execute(session,
                        'INSERT INTO discounts (code, percent, active, expires_at, updated_at) '
                        'VALUES (:c, :p, :a, :e, :u)',
                        {'c': code, 'p': percent, 'a': active, 'e': expires_at, 'u': datetime.utcnow()})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@app.delete('/admin/api/discounts/{discount_id}')
async def api_discounts_delete(request: Request, discount_id: int):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                await _execute(session, 'DELETE FROM discounts WHERE id = :id', {'id': discount_id})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- Notifications ---

@app.get('/admin/api/notifications')
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


# --- Notifications mark-read ---

@app.post('/admin/api/notifications/{notif_id}/read')
async def api_notification_read(request: Request, notif_id: int):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                await _execute(session, 'UPDATE notifications SET read=true WHERE id=:id', {'id': notif_id})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- About ---

@app.get('/admin/api/about')
async def api_about(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, section, content, updated_at FROM about_content ORDER BY section')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@app.post('/admin/api/about')
async def api_about_update(request: Request):
    _require_api_session(request)
    body = await request.json()
    section = body.get('section', '')
    content = body.get('content', '')

    if not section:
        return _json_response({'error': 'section is required'}, 400)

    try:
        async with async_session() as session:
            async with session.begin():
                existing = await _fetch_one(session,
                    'SELECT id FROM about_content WHERE section = :s', {'s': section})
                if existing:
                    await _execute(session,
                        'UPDATE about_content SET content = :c, updated_at = :u WHERE id = :id',
                        {'c': content, 'u': datetime.utcnow(), 'id': existing['id']})
                else:
                    await _execute(session,
                        'INSERT INTO about_content (section, content, updated_at) VALUES (:s, :c, :u)',
                        {'s': section, 'c': content, 'u': datetime.utcnow()})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- Proxy Config ---

@app.get('/admin/api/proxy')
async def api_proxy(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, key, value, updated_at FROM proxy_config ORDER BY key')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@app.post('/admin/api/proxy')
async def api_proxy_update(request: Request):
    _require_api_session(request)
    body = await request.json()
    key = body.get('key', '')
    value = body.get('value', '')

    if not key:
        return _json_response({'error': 'key is required'}, 400)

    try:
        async with async_session() as session:
            async with session.begin():
                existing = await _fetch_one(session,
                    'SELECT id FROM proxy_config WHERE key = :k', {'k': key})
                if existing:
                    await _execute(session,
                        'UPDATE proxy_config SET value = :v, updated_at = :u WHERE id = :id',
                        {'v': value, 'u': datetime.utcnow(), 'id': existing['id']})
                else:
                    await _execute(session,
                        'INSERT INTO proxy_config (key, value, updated_at) VALUES (:k, :v, :u)',
                        {'k': key, 'v': value, 'u': datetime.utcnow()})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)
