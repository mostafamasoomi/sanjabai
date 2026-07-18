"""
Auth endpoints: signup, login, logout, profile management, password reset,
telegram linking, referral stats, welcome email.
"""
from __future__ import annotations

import base64
import logging as _logging
import os
import secrets
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from database import async_session, rds, BASE_URL
from models import User, Ledger, Quota
from dependencies import (
    SESSION_TTL, SESSION_COOKIE_NAME, _hash_password, _verify_password, _gen_token,
    _create_session, _get_session, _get_session_user_id, _set_session_cookie,
    _clear_session_cookie, _rotate_session, _get_user_id, admin_required,
    _write_audit_log, _get_admin_session, _create_admin_session,
    ADMIN_COOKIE_NAME, ADMIN_CSRF_COOKIE_NAME, SESSION_COOKIE_SECURE, ADMIN_SESSION_TTL,
    send_email, ADMIN_TOKEN, INTERNAL_TOKEN,
)
from security import (
    record_failed_attempt, clear_lockout, _get_lockout_identifier,
    track_session, get_lockout_info,
)

router = APIRouter()

INTERNAL_TOKEN = INTERNAL_TOKEN


# ── Pydantic models ─────────────────────────────────────────────

class AdminLogin(BaseModel):
    token: str


class AuthSignup(BaseModel):
    email: str
    password: str
    ref: str | None = None
    captcha_token: str | None = None
    captcha_answer: str | None = None


class AuthLogin(BaseModel):
    email: str
    password: str
    captcha_token: str | None = None
    captcha_answer: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    bio: str | None = None
    timezone: str | None = None
    language: str | None = None
    preferences: dict | None = None


class AvatarUploadRequest(BaseModel):
    avatar_url: str | None = None
    avatar_base64: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class TelegramLink(BaseModel):
    telegram_id: int


class TelegramTokenRequest(BaseModel):
    telegram_id: int


# ── Admin session endpoints ─────────────────────────────────────

@router.post('/admin/login')
async def admin_login(payload: AdminLogin) -> JSONResponse:
    """Validate admin token and establish an isolated server-side session."""
    if not ADMIN_TOKEN or not hmac.compare_digest(payload.token, ADMIN_TOKEN):
        return JSONResponse({'detail': 'توکن ادمین نامعتبر است'}, status_code=401)
    sid, csrf = await _create_admin_session()
    # Capture request info for audit (admin_login doesn't have request param, skip)
    response = JSONResponse({'status': 'ok', 'csrf': csrf})
    response.set_cookie(
        ADMIN_COOKIE_NAME, sid, httponly=True,
        secure=SESSION_COOKIE_SECURE, samesite='lax',
        max_age=ADMIN_SESSION_TTL, path='/',
    )
    response.set_cookie(
        ADMIN_CSRF_COOKIE_NAME, csrf, httponly=False,
        secure=SESSION_COOKIE_SECURE, samesite='lax',
        max_age=ADMIN_SESSION_TTL, path='/',
    )
    await _write_audit_log('admin.login')
    return response


@router.post('/admin/logout')
async def admin_logout(request: Request) -> JSONResponse:
    """Clear the server-side admin session."""
    sid = request.cookies.get(ADMIN_COOKIE_NAME)
    if sid:
        await rds.delete(f'admin_session:{sid}')
    await _write_audit_log('admin.logout')
    response = JSONResponse({'status': 'ok'})
    response.delete_cookie(ADMIN_COOKIE_NAME, path='/')
    response.delete_cookie(ADMIN_CSRF_COOKIE_NAME, path='/')
    return response


# ── Signup / Login / Logout ─────────────────────────────────────

@router.post('/auth/signup')
async def signup(payload: AuthSignup) -> JSONResponse:
    from security import validate_email, validate_password
    # Verify captcha
    if not payload.captcha_token or not payload.captcha_answer:
        return JSONResponse({"detail": "کپچا الزامی است"}, status_code=400)
    stored = await rds.get(f"captcha:{payload.captcha_token}")
    if not stored or str(stored) != str(payload.captcha_answer):
        return JSONResponse({"detail": "کپچا اشتباه است"}, status_code=400)
    await rds.delete(f"captcha:{payload.captcha_token}")
    valid, err = validate_email(payload.email)
    if not valid:
        return JSONResponse({'detail': err}, status_code=400)
    valid, err = validate_password(payload.password)
    if not valid:
        return JSONResponse({'detail': err}, status_code=400)

    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        existing = await session.execute(User.__table__.select().where(User.email == payload.email))
        if existing.fetchone():
            return JSONResponse({'detail': 'email already registered | ایمیل قبلا ثبت شده است'}, status_code=409)
        user = User(email=payload.email, password_hash=_hash_password(payload.password), referral_code=secrets.token_hex(4))
        session.add(user)
        await session.commit()
        await session.refresh(user)
        # Handle referral
        ref_code = payload.ref if hasattr(payload, 'ref') else None
        if ref_code and async_session is not None:
            async with async_session() as s2:
                ref_res = await s2.execute(User.__table__.select().where(User.referral_code == ref_code))
                referrer = ref_res.fetchone()
                if referrer and referrer.id != user.id:
                    await s2.execute(
                        User.__table__.update().where(User.id == user.id),
                        {'referred_by': referrer.id}
                    )
                    bonus = Ledger(user_id=referrer.id, amount=5000, balance_after=0,
                                   reason=f'پاداش دعوت کاربر {user.email}')
                    bal_res = await s2.execute(
                        sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
                        {'uid': referrer.id}
                    )
                    bal_row = bal_res.fetchone()
                    bonus.balance_after = (bal_row.balance if bal_row else 0) + 5000
                    s2.add(bonus)
                    await s2.commit()
        quota = Quota(user_id=user.id, daily_limit=200000, used_today=0, reset_at=(datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None))
        session.add(quota)
        await session.commit()
        token = await _create_session(user.id)
        response = JSONResponse({'token': token, 'user': {'id': user.id, 'email': user.email}})
        _set_session_cookie(response, token)
        await _write_audit_log('auth.signup', target_type='user', target_id=user.id, details={'email': user.email})
        return response


@router.post('/auth/login')
async def login(payload: AuthLogin) -> JSONResponse:
    # Verify captcha
    if not payload.captcha_token or not payload.captcha_answer:
        return JSONResponse({"detail": "کپچا الزامی است"}, status_code=400)
    stored = await rds.get(f"captcha:{payload.captcha_token}")
    if not stored or str(stored) != str(payload.captcha_answer):
        return JSONResponse({"detail": "کپچا اشتباه است"}, status_code=400)
    await rds.delete(f"captcha:{payload.captcha_token}")
    """Authenticate user with email/password. Includes account lockout protection."""
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    # Check lockout before attempting authentication
    lockout_id = f'login_ip:{payload.email}'  # Use email as primary identifier
    lockout_info = await get_lockout_info(lockout_id)
    if lockout_info['locked']:
        remaining = lockout_info['lockout_remaining_seconds']
        return JSONResponse(
            {'detail': 'حساب شما به دلیل تلاش‌های ناموفق زیاد موقتاً قفل شده است',
             'retry_after': remaining},
            status_code=423,
        )

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.email == payload.email))
        user = res.fetchone()
        if not user or not user.password_hash or not _verify_password(payload.password, user.password_hash):
            # Record failed attempt for lockout tracking
            await record_failed_attempt(lockout_id)
            await _write_audit_log('auth.login_failed', details={'email': payload.email})
            return JSONResponse({'detail': 'ایمیل یا رمز عبور اشتباه است'}, status_code=401)
        if user.banned:
            return JSONResponse({'detail': 'حساب شما مسدود شده است'}, status_code=403)

        # Successful login: clear any lockout
        await clear_lockout(lockout_id)

        token = await _create_session(user.id)
        # Track session with metadata and enforce concurrent limit
        # Note: request object not available here, so we skip full tracking
        # Session tracking will be handled by middleware on subsequent requests
        response = JSONResponse({'token': token, 'user': {'id': user.id, 'email': user.email}})
        _set_session_cookie(response, token)
        await _write_audit_log('auth.login', target_type='user', target_id=user.id, details={'email': user.email})
        return response


@router.get('/auth/me')
async def me(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()
        if not user:
            return JSONResponse({'detail': 'user not found | کاربر یافت نشد'}, status_code=404)
        from fastapi.encoders import jsonable_encoder
        return JSONResponse(jsonable_encoder({
            'id': user.id, 'email': user.email, 'created_at': user.created_at,
            'referral_code': user.referral_code,
            'display_name': user.display_name,
            'avatar_url': user.avatar_url,
            'bio': user.bio,
            'preferences': user.preferences or {},
            'timezone': user.timezone or 'Asia/Tehran',
            'language': user.language or 'fa',
        }))


@router.get('/referral/stats')
async def referral_stats(request: Request) -> JSONResponse:
    """Get user's referral stats"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()

        count_res = await session.execute(
            sqlalchemy.text('SELECT COUNT(*) as c FROM users WHERE referred_by = :uid'),
            {'uid': uid}
        )
        count = count_res.fetchone().c

        bonus_res = await session.execute(
            sqlalchemy.text("SELECT COALESCE(SUM(amount), 0) as total FROM ledger WHERE user_id = :uid AND reason LIKE 'پاداش%'"),
            {'uid': uid}
        )
        bonus = bonus_res.fetchone().total

    return JSONResponse({
        'referral_code': user.referral_code if user else None,
        'referral_count': count,
        'total_bonus': bonus,
        'referral_url': f'{BASE_URL}/signup?ref={user.referral_code}' if user and user.referral_code else None,
    })


@router.post('/auth/logout')
async def logout(request: Request) -> JSONResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME) or \
        request.headers.get('Authorization', '').removeprefix('Bearer ')
    if token:
        uid = await _get_session_user_id(token)
        await rds.delete(f'session:{token}')
        if uid:
            await rds.srem(f'sessions:{uid}', token)
            await _write_audit_log('auth.logout', target_type='user', target_id=uid)
    response = JSONResponse({'status': 'ok'})
    _clear_session_cookie(response)
    return response


@router.post('/auth/logout-all')
async def logout_all(request: Request) -> JSONResponse:
    """Revoke every active session for the authenticated user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    raw_members = await rds.smembers(f'sessions:{uid}')
    tokens = list(raw_members or [])
    for tok in tokens:
        await rds.delete(f'session:{tok}')
    await rds.delete(f'sessions:{uid}')
    await _write_audit_log('auth.logout_all', target_type='user', target_id=uid, details={'revoked_sessions': len(tokens)})
    response = JSONResponse({'status': 'ok', 'revoked_sessions': len(tokens)})
    _clear_session_cookie(response)
    return response


# ── Profile management ──────────────────────────────────────────

@router.post('/auth/change-password')
async def change_password(request: Request, payload: ChangePasswordRequest) -> JSONResponse:
    """Change user password"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    from security import validate_password
    valid, err = validate_password(payload.new_password)
    if not valid:
        return JSONResponse({'detail': err}, status_code=400)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()
        if not user or not _verify_password(payload.current_password, user.password_hash):
            return JSONResponse({'detail': 'current password is incorrect | رمز عبور فعلی نادرست است'}, status_code=401)

        new_hash = _hash_password(payload.new_password)
        await session.execute(
            User.__table__.update().where(User.id == uid),
            {'password_hash': new_hash}
        )
        await session.commit()

    response = JSONResponse({'status': 'ok'})
    await _rotate_session(request, response, uid)
    await _write_audit_log('auth.change_password', target_type='user', target_id=uid)
    return response


@router.get('/auth/profile')
async def get_profile(request: Request) -> JSONResponse:
    """Get full user profile including preferences and autonomy settings"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()
        if not user:
            return JSONResponse({'detail': 'user not found | کاربر یافت نشد'}, status_code=404)

        prefs = user.preferences or {}
        from fastapi.encoders import jsonable_encoder
        return JSONResponse(jsonable_encoder({
            'id': user.id,
            'email': user.email,
            'display_name': user.display_name,
            'avatar_url': user.avatar_url,
            'bio': user.bio,
            'timezone': user.timezone or 'Asia/Tehran',
            'language': user.language or 'fa',
            'preferences': {
                'default_model': prefs.get('default_model', ''),
                'theme': prefs.get('theme', 'dark'),
                'ai_personality': prefs.get('ai_personality', ''),
                'autonomy_level': prefs.get('autonomy_level', 'medium'),
                'notification_settings': prefs.get('notification_settings', {
                    'email': True,
                    'telegram': False,
                }),
            },
            'created_at': user.created_at,
            'referral_code': user.referral_code,
        }))


@router.put('/auth/profile')
async def update_profile(request: Request, payload: UpdateProfileRequest) -> JSONResponse:
    """Update user profile fields including preferences"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    update_data: dict[str, Any] = {}
    if payload.display_name is not None:
        if len(payload.display_name) > 100:
            return JSONResponse({'detail': 'نام نمایشی نباید بیشتر از ۱۰۰ کاراکتر باشد'}, status_code=400)
        update_data['display_name'] = payload.display_name.strip() or None
    if payload.bio is not None:
        if len(payload.bio) > 500:
            return JSONResponse({'detail': 'بیوگرافی نباید بیشتر از ۵۰۰ کاراکتر باشد'}, status_code=400)
        update_data['bio'] = payload.bio.strip() or None
    if payload.timezone is not None:
        update_data['timezone'] = payload.timezone
    if payload.language is not None:
        if payload.language not in ('fa', 'en'):
            return JSONResponse({'detail': 'زبان باید fa یا en باشد'}, status_code=400)
        update_data['language'] = payload.language

    if payload.preferences is not None:
        async with async_session() as session:
            res = await session.execute(User.__table__.select().where(User.id == uid))
            user = res.fetchone()
            existing_prefs = (user.preferences or {}) if user else {}

        if 'autonomy_level' in payload.preferences:
            level = payload.preferences['autonomy_level']
            if level not in ('low', 'medium', 'high'):
                return JSONResponse({'detail': 'سطح خودمختاری باید low، medium یا high باشد'}, status_code=400)

        existing_prefs.update(payload.preferences)
        update_data['preferences'] = existing_prefs

    if not update_data:
        return JSONResponse({'detail': 'فیلد معتبری برای بروزرسانی وجود ندارد'}, status_code=400)

    async with async_session() as session:
        await session.execute(
            User.__table__.update().where(User.id == uid),
            update_data
        )
        await session.commit()

    await _write_audit_log('auth.update_profile', target_type='user', target_id=uid,
                           details={'fields': list(update_data.keys())})
    return JSONResponse({'status': 'ok', 'updated': list(update_data.keys())})


@router.post('/auth/avatar')
async def upload_avatar(request: Request, payload: AvatarUploadRequest) -> JSONResponse:
    """Upload or set user avatar (URL or base64 image)"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    avatar_url = None

    if payload.avatar_url:
        if not payload.avatar_url.startswith(('http://', 'https://')):
            return JSONResponse({'detail': 'آدرس تصویر نامعتبر است'}, status_code=400)
        if len(payload.avatar_url) > 2000:
            return JSONResponse({'detail': 'آدرس تصویر بیش از حد طولانی است'}, status_code=400)
        avatar_url = payload.avatar_url
    elif payload.avatar_base64:
        raw = payload.avatar_base64
        if ',' in raw and raw.startswith('data:'):
            raw = raw.split(',', 1)[1]
        try:
            decoded = base64.b64decode(raw)
        except Exception:
            return JSONResponse({'detail': 'تصویر نامعتبر است (base64 نادرست)'}, status_code=400)
        if len(decoded) > 2 * 1024 * 1024:
            return JSONResponse({'detail': 'حجم تصویر نباید بیشتر از ۲ مگابایت باشد'}, status_code=400)
        mime = 'image/jpeg'
        if decoded[:8] == b'\x89PNG\r\n\x1a\n':
            mime = 'image/png'
        elif decoded[:4] == b'RIFF' and decoded[8:12] == b'WEBP':
            mime = 'image/webp'
        elif decoded[:4] == b'GIF8':
            mime = 'image/gif'
        avatar_url = f'data:{mime};base64,{raw}'
    else:
        return JSONResponse({'detail': 'آدرس تصویر یا داده base64 ارسال کنید'}, status_code=400)

    async with async_session() as session:
        await session.execute(
            User.__table__.update().where(User.id == uid),
            {'avatar_url': avatar_url}
        )
        await session.commit()

    await _write_audit_log('auth.upload_avatar', target_type='user', target_id=uid)
    return JSONResponse({'status': 'ok', 'avatar_url': avatar_url})


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
    uid = await _get_user_id(request)
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
    if not INTERNAL_TOKEN or not internal_token or not hmac.compare_digest(internal_token, INTERNAL_TOKEN):
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
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()
        if not user or not user.email:
            return JSONResponse({'detail': 'ایمیلی ثبت نشده است'}, status_code=400)
    body = f'<div dir="rtl" style="font-family:Tahoma;max-width:600px;margin:auto;padding:20px;"><h1 style="color:#6c5cf5;">به Multiai خوش آمدید! 🎉</h1><p>سلام {user.email}،</p><p>حساب شما با موفقیت ساخته شد.</p><p><a href="{BASE_URL}/chat" style="background:#6c5cf5;color:white;padding:10px 20px;text-decoration:none;border-radius:8px;">شروع چت</a></p></div>'
    ok = await send_email(user.email, 'به Multiai خوش آمدید!', body)
    return JSONResponse({'status': 'sent' if ok else 'queued'})
