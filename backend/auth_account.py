"""Password reset, Telegram account linking, and the welcome email --
split out of auth.py (see auth.py's module docstring for why).

IMPORT CONTRACT -- read before moving anything again. auth.py imports this
module's names AFTER its own `router` is defined, purely so that importing
this module registers `/auth/forgot-password`, `/auth/reset-password`,
`/auth/telegram-link`, `/auth/telegram-token` and `/auth/send-welcome` onto
`auth.router` as a side effect (same pattern chat_web.py/chat_compare.py/
chat_smart.py use for chat.router -- see chat.py's MONKEYPATCH CONTRACT
docstring). auth.py re-exports every name defined here so `auth.<name>`
keeps resolving for external consumers.

tests/test_email_honesty.py patches `auth._get_user_id` and
`auth.send_email` directly on the `auth` module object (not on this file).
`send_welcome_email` and `telegram_link` therefore read those names through
`auth._get_user_id(...)` / `auth.send_email(...)` at call time -- a plain
`import auth`, never `from auth import _get_user_id, send_email` and never
a bare intra-module reference -- so those patches keep reaching these
routes. `get_telegram_token` reads `auth.INTERNAL_TOKEN` the same way,
since auth.py deliberately rebinds `INTERNAL_TOKEN = INTERNAL_TOKEN` in its
own namespace to make it independently overridable there. Do not "tidy"
any of this into a direct import.
"""
from __future__ import annotations

import logging as _logging
import secrets
import hmac

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import async_session, rds, BASE_URL
from models import User
from dependencies import SESSION_TTL, _hash_password, _gen_token, _write_audit_log

import auth

router = auth.router


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class TelegramLink(BaseModel):
    telegram_id: int


class TelegramTokenRequest(BaseModel):
    telegram_id: int


# ── Password reset ──────────────────────────────────────────────

@router.post('/auth/forgot-password')
async def forgot_password(payload: ForgotPasswordRequest) -> JSONResponse:
    """Send password reset token (stored in Redis for 15 min)"""
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.email == payload.email))
        user = res.fetchone()
        if not user:
            return JSONResponse({'status': 'ok', 'message': 'در صورت وجود ایمیل، لینک بازیابی ارسال شد'})

        reset_token = secrets.token_urlsafe(32)
        await rds.setex(f'reset:{reset_token}', 900, str(user.id))

        _logging.getLogger(__name__).warning('Password reset token generated for user %s (email delivery not configured)', user.id)
        return JSONResponse({
            'status': 'ok',
            'message': 'لینک بازیابی به ایمیل شما ارسال شد',
        })


@router.post('/auth/reset-password')
async def reset_password(payload: ResetPasswordRequest) -> JSONResponse:
    """Reset password using token"""
    from security import validate_password
    valid, err = validate_password(payload.new_password)
    if not valid:
        return JSONResponse({'detail': err}, status_code=400)

    uid = await rds.get(f'reset:{payload.token}')
    if not uid:
        return JSONResponse({'detail': 'توکن بازیابی نامعتبر یا منقضی شده است'}, status_code=400)

    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    new_hash = _hash_password(payload.new_password)
    async with async_session() as session:
        await session.execute(
            User.__table__.update().where(User.id == int(uid)),
            {'password_hash': new_hash}
        )
        await session.commit()

    await rds.delete(f'reset:{payload.token}')
    return JSONResponse({'status': 'ok', 'message': 'رمز عبور با موفقیت تغییر کرد'})


# ── Telegram account linking ────────────────────────────────────

@router.post('/auth/telegram-link')
async def telegram_link(request: Request, payload: TelegramLink) -> JSONResponse:
    """Link a Telegram account to existing user"""
    uid = await auth._get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        await session.execute(
            User.__table__.update().where(User.id == uid),
            {'telegram_id': payload.telegram_id}
        )
        await session.commit()
    return JSONResponse({'status': 'ok', 'telegram_id': payload.telegram_id})


@router.post('/auth/telegram-token')
async def get_telegram_token(request: Request, payload: TelegramTokenRequest) -> JSONResponse:
    """Exchange a Telegram ID for a session token. Requires internal service auth."""
    internal_token = request.headers.get('x-internal-token', '')
    if not auth.INTERNAL_TOKEN or not internal_token or not hmac.compare_digest(internal_token, auth.INTERNAL_TOKEN):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.telegram_id == payload.telegram_id))
        user = res.fetchone()
        if not user:
            return JSONResponse({'detail': 'متصل نشده'}, status_code=404)
        if user.telegram_id != payload.telegram_id:
            return JSONResponse({'detail': 'عدم تطابق شناسه تلگرام'}, status_code=403)
        token = _gen_token()
        rds.setex(f'session:{token}', SESSION_TTL, str(user.id))
        await _write_audit_log('auth.telegram_token', target_type='user', target_id=user.id)
        return JSONResponse({'token': token, 'user': {'id': user.id, 'email': user.email}})


# ── Welcome email ───────────────────────────────────────────────

@router.post('/auth/send-welcome')
async def send_welcome_email(request: Request) -> JSONResponse:
    uid = await auth._get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()
        if not user or not user.email:
            return JSONResponse({'detail': 'ایمیلی ثبت نشده است'}, status_code=400)
    body = f'<div dir="rtl" style="font-family:Tahoma;max-width:600px;margin:auto;padding:20px;"><h1 style="color:#6c5cf5;">به Sanjabai خوش آمدید! 🎉</h1><p>سلام {user.email}،</p><p>حساب شما با موفقیت ساخته شد.</p><p><a href="{BASE_URL}/chat" style="background:#6c5cf5;color:white;padding:10px 20px;text-decoration:none;border-radius:8px;">شروع چت</a></p></div>'
    ok = await auth.send_email(user.email, 'به Sanjabai خوش آمدید!', body)
    # 'queued' used to be returned on failure too, implying a background
    # queue would retry and deliver it later. There is no such queue --
    # send_email either sent synchronously or did nothing at all (and, on
    # this host, outbound SMTP is blocked entirely -- see dependencies.py's
    # send_email for the measured port results -- so `ok` is always False
    # here in production today). Report honestly instead: a caller must be
    # able to tell "sent" from "not sent" from `status` alone, and the
    # user-facing `message` must never claim an email is on its way when
    # none was sent and none can be.
    if ok:
        return JSONResponse({'status': 'sent', 'message': 'ایمیل خوش‌آمدگویی ارسال شد.'})
    return JSONResponse({
        'status': 'not_sent',
        'message': 'در حال حاضر امکان ارسال ایمیل وجود ندارد؛ حساب شما همچنان فعال و قابل استفاده است.',
    })
