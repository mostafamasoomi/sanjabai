"""
Shared dependencies: authentication, session management, audit logging,
and utility functions used across all route modules.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from database import async_session, rds, ADMIN_TOKEN, BASE_URL, INTERNAL_TOKEN
from models import ApiKey, AuditLog, User, UserMemory


# ── Session / cookie configuration ──────────────────────────────
SESSION_TTL = 86400 * 7
SESSION_COOKIE_NAME = 'session'
_debug_raw_secure = os.getenv('DEBUG', '').lower()
SESSION_COOKIE_SECURE = (
    os.getenv('ENV', 'production').lower() not in ('development', 'dev')
    and _debug_raw_secure not in ('1', 'true', 'yes')
)
ADMIN_COOKIE_NAME = 'admin_session'
ADMIN_CSRF_COOKIE_NAME = 'admin_csrf'
ADMIN_SESSION_TTL = 3600 * 8
API_KEY_PEPPER = os.getenv('API_KEY_PEPPER', '').encode()
if not API_KEY_PEPPER:
    raise RuntimeError('API_KEY_PEPPER must be set in .env; refusing to start with insecure default')


# ── Token / password helpers ────────────────────────────────────

def _gen_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f'{salt}${dk.hex()}'


def _verify_password(password: str, stored: str) -> bool:
    salt, h = stored.split('$')
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return hmac.compare_digest(h, dk.hex())


def _hash_api_key(raw_key: str) -> str:
    """Hash an API key at rest using sha256 with a server-side pepper (salt)."""
    return hashlib.sha256(API_KEY_PEPPER + raw_key.encode()).hexdigest()


_PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹'


def _to_fa(value: str | int | float) -> str:
    """Convert Western digits (0-9) to Persian digits (۰-۹) in a string."""
    return ''.join(_PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in str(value))


def _escape_like(s: str) -> str:
    """Escape LIKE/ILIKE wildcards in user input to prevent pattern injection."""
    return s.replace('\\\\', '\\\\\\\\').replace('%', '\\\\%').replace('_', '\\\\_')


# ── User session management ─────────────────────────────────────

def _session_payload(user_id: int) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        'user_id': user_id,
        'created_at': now.isoformat(),
        'expires_at': (now + timedelta(seconds=SESSION_TTL)).isoformat(),
    }


async def _create_session(user_id: int) -> str:
    """Create a server-side session and return its opaque token."""
    token = _gen_token()
    await rds.setex(f'session:{token}', SESSION_TTL, json.dumps(_session_payload(user_id)))
    await rds.sadd(f'sessions:{user_id}', token)
    await rds.expire(f'sessions:{user_id}', SESSION_TTL)
    return token


async def _get_session(token: str | None) -> dict | None:
    if not token:
        return None
    raw = await rds.get(f'session:{token}')
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        data = None
    if not isinstance(data, dict):
        try:
            return {'user_id': int(raw), 'created_at': None, 'expires_at': None}
        except (TypeError, ValueError):
            return None
    exp = data.get('expires_at')
    if exp:
        try:
            if datetime.fromisoformat(exp) < datetime.now(timezone.utc).replace(tzinfo=None):
                await rds.delete(f'session:{token}')
                return None
        except ValueError:
            pass
    await rds.expire(f'session:{token}', SESSION_TTL)
    return data


async def _get_session_user_id(token: str | None) -> int | None:
    data = await _get_session(token)
    return int(data['user_id']) if data else None


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME, token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite='lax',
        max_age=SESSION_TTL,
        path='/',
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path='/')


async def _rotate_session(request: Request, response: Response, user_id: int) -> str:
    """Invalidate the current session and issue a fresh one (privilege change)."""
    old = request.cookies.get(SESSION_COOKIE_NAME) or \
        request.headers.get('Authorization', '').removeprefix('Bearer ')
    if old:
        await rds.delete(f'session:{old}')
        await rds.srem(f'sessions:{user_id}', old)
    new_token = await _create_session(user_id)
    _set_session_cookie(response, new_token)
    return new_token


# ── User ID resolution ──────────────────────────────────────────

async def _get_user_id(request: Request) -> int | None:
    from sqlalchemy import func
    # Primary: server-side session cookie
    token = request.cookies.get(SESSION_COOKIE_NAME)
    # Fallback: Authorization header (legacy / API access / websocket upgrade)
    if not token:
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if not token:
        return None
    uid = await _get_session_user_id(token)
    if uid:
        return uid
    # API key authentication
    if token.startswith('sk-'):
        key_hash = _hash_api_key(token)
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(
                    ApiKey.__table__.select().where(
                        ApiKey.key_hash == key_hash,
                        ApiKey.active == True,
                        ApiKey.revoked_at == None,
                        (ApiKey.expires_at == None) | (ApiKey.expires_at > func.now()),
                    )
                )
                key = res.fetchone()
                if key:
                    key_id = key.id
                    user_id = key.user_id
                    asyncio.create_task(_update_api_key_last_used(key_id))
                    user_res = await session.execute(User.__table__.select().where(User.id == user_id))
                    user_row = user_res.fetchone()
                    if user_row and user_row.banned:
                        return None
                    return user_id
    return None


async def _update_api_key_last_used(key_id: int) -> None:
    """Background task: update api_keys.last_used without blocking the response."""
    try:
        if async_session is not None:
            async with async_session() as session:
                await session.execute(
                    ApiKey.__table__.update().where(ApiKey.id == key_id),
                    {'last_used': datetime.now(timezone.utc).replace(tzinfo=None)}
                )
                await session.commit()
    except Exception:
        pass


# ── Admin authentication ────────────────────────────────────────

async def _create_admin_session() -> tuple[str, str]:
    sid = _gen_token()
    csrf = secrets.token_urlsafe(32)
    payload = {
        'created_at': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        'csrf': csrf,
    }
    await rds.setex(f'admin_session:{sid}', ADMIN_SESSION_TTL, json.dumps(payload))
    return sid, csrf


async def _get_admin_session(sid: str | None) -> dict | None:
    if not sid:
        return None
    raw = await rds.get(f'admin_session:{sid}')
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def admin_required(request: Request) -> bool:
    """Verify admin authorization.

    Supports cookie-based admin sessions (CSRF-protected) and legacy
    header-token auth.  When the ``totp_verified`` flag is not present
    in the session and MFA is enabled for the admin, the request is
    rejected with ``totp_required`` so the frontend can prompt for a
    TOTP code.
    """
    # Primary: isolated server-side admin session cookie (CSRF-protected mutations)
    sid = request.cookies.get(ADMIN_COOKIE_NAME)
    if sid:
        sess = await _get_admin_session(sid)
        if sess:
            if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
                csrf = request.headers.get('x-csrf-token') or request.headers.get('x-csrf')
                if not csrf or not hmac.compare_digest(csrf, sess.get('csrf', '')):
                    return False
            # TOTP gate: if MFA is enabled on the admin user, require TOTP verification
            totp_enabled = sess.get('totp_enabled', False)
            totp_verified = sess.get('totp_verified', False)
            if totp_enabled and not totp_verified:
                # Attach a flag so callers can detect TOTP-required state
                request.state.totp_required = True
                return False
            return True
    # Legacy: constant-time header token (no CSRF needed for header-based auth)
    token = request.headers.get('x-admin-token') or request.headers.get('authorization', '').removeprefix('Bearer ')
    return bool(ADMIN_TOKEN) and bool(token) and hmac.compare_digest(token, ADMIN_TOKEN)


# ── Audit logging ───────────────────────────────────────────────

async def _write_audit_log(action: str, target_type: str | None = None,
                            target_id: Any = None, details: dict | None = None,
                            request: Request | None = None) -> None:
    """Best-effort, fire-and-forget audit record of a privileged/admin action.

    When *request* is provided the client IP and User-Agent are captured
    and stored alongside the audit entry for forensic traceability.
    """
    if async_session is None:
        return
    ip_address = None
    user_agent = None
    if request is not None:
        from security import get_real_ip
        ip_address = get_real_ip(request)
        user_agent = (request.headers.get('user-agent') or '')[:200]
    try:
        async with async_session() as s:
            s.add(AuditLog(
                action=action,
                target_type=target_type,
                target_id=str(target_id) if target_id is not None else None,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent,
            ))
            await s.commit()
    except Exception:
        pass


# ── User memories helper ────────────────────────────────────────

async def _get_user_memories(uid: int) -> list[str]:
    """Fetch active user memory contents for injection into chat."""
    if async_session is None:
        return []
    try:
        async with async_session() as session:
            res = await session.execute(
                UserMemory.__table__.select().where(
                    UserMemory.user_id == uid,
                    UserMemory.active == True,
                ).order_by(UserMemory.created_at.desc()).limit(20)
            )
            return [r.content for r in res.fetchall()]
    except Exception:
        return []


async def _get_user_soul(uid: int) -> str:
    """Fetch ai_personality (soul) from user preferences for injection."""
    if async_session is None:
        return ''
    try:
        async with async_session() as session:
            res = await session.execute(
                User.__table__.select().where(User.id == uid)
            )
            row = res.fetchone()
            if row and row.preferences:
                return (row.preferences or {}).get('ai_personality', '')
    except Exception:
        pass
    return ''


# ── Email ───────────────────────────────────────────────────────

SMTP_HOST = os.getenv('SMTP_HOST', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASS = os.getenv('SMTP_PASS', '')
SMTP_FROM = os.getenv('SMTP_FROM', 'noreply@multiai.ir')


async def send_email(to: str, subject: str, body: str) -> bool:
    if not SMTP_HOST:
        print(f'[EMAIL] Would send to {to}: {subject}')
        return False
    from email.mime.text import MIMEText
    msg = MIMEText(body, 'html', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = SMTP_FROM
    msg['To'] = to
    try:
        def _send_sync():
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                if SMTP_USER:
                    server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
        await asyncio.to_thread(_send_sync)
        return True
    except Exception as e:
        print(f'[EMAIL] Failed: {e}')
        return False


# ── WebSocket clients ───────────────────────────────────────────

_ws_clients: dict[int, list] = {}


async def notify_user(uid: int, message: dict):
    """Send a notification to all WebSocket connections of a user"""
    for ws in _ws_clients.get(uid, []):
        try:
            await ws.send_json(message)
        except Exception:
            pass
