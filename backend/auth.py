"""
Auth endpoints: signup, login, logout, profile management, password reset,
telegram linking, referral stats, welcome email.

MODULE SPLIT (house 500-line cap; this file used to be 687 lines) -- auth.py
is now the router PLUS a namespace facade, following the same pattern as
chat.py/chat_web.py/chat_search.py: it owns the core session-lifecycle
endpoints directly (admin session, signup, login, /auth/me, referral stats,
logout, logout-all) and re-exports everything the sibling modules need to
keep resolving as `auth.<name>`: auth_profile.py (change-password, profile
get/update, avatar upload) and auth_account.py (password reset, telegram
linking, welcome email).

MONKEYPATCH CONTRACT: tests patch `auth._get_user_id`, `auth.send_email`
and `auth.get_site_flag` directly on THIS module object (see
tests/test_email_honesty.py, tests/test_site_flag_wiring.py), not on
whichever auth_*.py file actually defines a given route today. Both
auth_profile.py and auth_account.py do a plain `import auth` (safe against
the circular import -- nothing touches an `auth` attribute until a function
actually runs, by which point this file has finished executing) and read
`_get_user_id` / `send_email` / `INTERNAL_TOKEN` through `auth.<name>` at
call time wherever they use them, never via `from auth import X` and never
via a bare intra-module reference. Do not "tidy" that into a direct import;
it would silently break the patches above. `get_site_flag` is only ever
used by `signup`, which stays physically in this file, so it keeps its
plain bare-name resolution.
"""
from __future__ import annotations

import os
import secrets
import hmac
from datetime import datetime, timedelta, timezone

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from database import async_session, rds, BASE_URL
from models import User, Quota
from site_settings import get_site_flag
from dependencies import (
    SESSION_COOKIE_NAME, _hash_password, _verify_password,
    _create_session, _get_session_user_id, _set_session_cookie,
    _clear_session_cookie, _get_user_id, admin_required,
    _write_audit_log, _get_admin_session, _create_admin_session,
    ADMIN_COOKIE_NAME, ADMIN_CSRF_COOKIE_NAME, SESSION_COOKIE_SECURE, ADMIN_SESSION_TTL,
    send_email, ADMIN_TOKEN, INTERNAL_TOKEN,
)
from security import (
    record_failed_attempt, clear_lockout, _get_lockout_identifier,
    track_session, get_lockout_info,
)
from i18n import err
from services import referral as referral_service

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


# NOTE: ChangePasswordRequest / UpdateProfileRequest / AvatarUploadRequest now
# live in auth_profile.py; ForgotPasswordRequest / ResetPasswordRequest /
# TelegramLink / TelegramTokenRequest now live in auth_account.py. Both are
# re-exported at the bottom of this file so `auth.<Model>` keeps resolving.


# ── Admin session endpoints ─────────────────────────────────────

@router.post('/admin/login')
async def admin_login(payload: AdminLogin) -> JSONResponse:
    """Validate admin token and establish an isolated server-side session."""
    if not ADMIN_TOKEN or not hmac.compare_digest(payload.token, ADMIN_TOKEN):
        return err('توکن ادمین نامعتبر است', 'Invalid admin token', 401)
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
async def signup(payload: AuthSignup, request: Request) -> JSONResponse:
    # signups_enabled gate (site_settings.py) -- must run before the captcha
    # check so a closed signup window never consumes a captcha token.
    if not await get_site_flag('signups_enabled'):
        return err(
            'ثبت‌نام کاربران جدید موقتاً غیرفعال است. لطفاً بعداً دوباره تلاش کنید.',
            'Sign-ups are temporarily disabled. Please try again later.',
            403,
        )
    from security import validate_email, validate_password
    # Verify captcha
    if not payload.captcha_token or not payload.captcha_answer:
        return err('کپچا الزامی است', 'Captcha is required', 400)
    stored = await rds.get(f"captcha:{payload.captcha_token}")
    if not stored or str(stored) != str(payload.captcha_answer):
        return err('کپچا اشتباه است', 'Incorrect captcha', 400)
    await rds.delete(f"captcha:{payload.captcha_token}")

    # Rate limiting: max 3 signups per minute per email/IP to prevent abuse
    rate_key = f"rate_signup:{payload.email}"
    try:
        count = await rds.incr(rate_key)
        if count == 1:
            await rds.expire(rate_key, 60)
        if count > 3:
            await rds.decr(rate_key)
            return err(
                'ثبت‌نام سریع است. بعداً دوباره تلاش کنید',
                'Too many sign-up attempts. Try again later.',
                429,
            )
    except Exception:
        pass

    valid, verr_fa, verr_en = validate_email(payload.email)
    if not valid:
        return err(verr_fa, verr_en, 400)
    valid, verr_fa, verr_en = validate_password(payload.password)
    if not valid:
        return err(verr_fa, verr_en, 400)

    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        existing = await session.execute(User.__table__.select().where(User.email == payload.email))
        if existing.fetchone():
            return err('ایمیل قبلا ثبت شده است', 'This email is already registered.', 409)
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
                    # Referral attribution + invitee welcome credit. Who
                    # invited whom is recorded (surfaced via /referral/stats);
                    # the invitee is also credited referral_invitee_reward_toman
                    # immediately (owner decision 2026-08-30, superseding the
                    # 2026-08-28 "only on first payment" rule — see
                    # services/referral.py's docstring). The wallet credit is
                    # issued by services/referral.py (an allowlisted crediting
                    # module), NOT here — auth.py itself never calls
                    # credit_wallet; see backend/tests/test_credit_paths.py.
                    await s2.execute(
                        User.__table__.update().where(User.id == user.id),
                        {'referred_by': referrer.id}
                    )
                    await s2.commit()
                    # record the (inviter, invitee) pair as 'pending', then
                    # credit the invitee's welcome reward on the same session.
                    # The inviter's leg still settles later, on this invitee's
                    # first successful payment. Both calls never raise, so a
                    # bookkeeping failure here can never fail this signup.
                    await referral_service.record_attribution(s2, referrer.id, user.id)
                    await referral_service.credit_invitee_signup_reward(s2, user.id)

        # No UNCONDITIONAL signup gift: a user who arrives without a valid
        # invite code starts at a zero wallet balance (the invitee credit
        # above only fires in the referral branch). Their on-ramp is the
        # existing free-tier allowance (services/free_tier.py), not a wallet
        # credit. See backend/tests/test_credit_paths.py.
        quota = Quota(user_id=user.id, daily_limit=200000, used_today=0, reset_at=(datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None))
        session.add(quota)
        await session.commit()
        token = await _create_session(user.id)
        await track_session(token, user.id, request)
        response = JSONResponse({
            'token': token,
            'user': {'id': user.id, 'email': user.email},
        })
        _set_session_cookie(response, token)
        await _write_audit_log('auth.signup', target_type='user', target_id=user.id, details={'email': user.email})
        return response


@router.post('/auth/login')
async def login(payload: AuthLogin, request: Request) -> JSONResponse:
    # Verify captcha
    if not payload.captcha_token or not payload.captcha_answer:
        return err('کپچا الزامی است', 'Captcha is required', 400)
    stored = await rds.get(f"captcha:{payload.captcha_token}")
    if not stored or str(stored) != str(payload.captcha_answer):
        return err('کپچا اشتباه است', 'Incorrect captcha', 400)
    await rds.delete(f"captcha:{payload.captcha_token}")

    # Rate limiting: max 5 attempts per 60 seconds per email
    rate_key = f"rate_login:{payload.email}"
    try:
        count = await rds.incr(rate_key)
        if count == 1:
            await rds.expire(rate_key, 60)
        if count > 5:
            await rds.decr(rate_key)
            return err(
                'تعداد تلاش‌ها زیاد است. بعداً دوباره تلاش کنید',
                'Too many attempts. Try again later.',
                429,
            )
    except Exception:
        pass  # Redis failure -> allow through

    """Authenticate user with email/password. Includes account lockout protection."""
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    # Check lockout before attempting authentication
    lockout_id = f'login_ip:{payload.email}'  # Use email as primary identifier
    lockout_info = await get_lockout_info(lockout_id)
    if lockout_info['locked']:
        remaining = lockout_info['lockout_remaining_seconds']
        # Carries an extra `retry_after` field alongside the bilingual detail,
        # so this is built by hand rather than via err() (which only ever
        # returns {detail, detail_en}) -- see handoff report.
        return JSONResponse(
            {'detail': 'حساب شما به دلیل تلاش‌های ناموفق زیاد موقتاً قفل شده است',
             'detail_en': 'Your account is temporarily locked due to too many failed attempts.',
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
            return err('ایمیل یا رمز عبور اشتباه است', 'Incorrect email or password.', 401)
        if user.banned:
            return err('حساب شما مسدود شده است', 'Your account has been suspended.', 403)

        # Successful login: clear any lockout
        await clear_lockout(lockout_id)

        token = await _create_session(user.id)
        # Record IP/user-agent and enforce MAX_CONCURRENT_SESSIONS. The claim
        # that "middleware handles this on subsequent requests" was never true
        # -- no middleware called track_session, so the concurrent-session
        # limit was dead code from the day it was written. Login is the right
        # place: it is the only moment a new session appears.
        await track_session(token, user.id, request)
        response = JSONResponse({'token': token, 'user': {'id': user.id, 'email': user.email}})
        _set_session_cookie(response, token)
        await _write_audit_log('auth.login', target_type='user', target_id=user.id, details={'email': user.email})
        return response


@router.get('/auth/me')
async def me(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()
        if not user:
            return err('کاربر یافت نشد', 'User not found.', 404)
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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()

        count_res = await session.execute(
            sqlalchemy.text('SELECT COUNT(*) as c FROM users WHERE referred_by = :uid'),
            {'uid': uid}
        )
        count = count_res.fetchone().c

    # total_bonus used to be SUM(ledger.amount) WHERE reason LIKE 'پاداش%',
    # which was always zero -- the signup/referral gifts that reason string
    # matched were removed, and no code path ever wrote a matching ledger
    # row again. services/referral.py::stats() is the real source now: the
    # sum of what has actually been PAID (status='paid' rows only, never
    # pending/capped) to this user as an inviter. Existing response keys
    # are unchanged (no rename); paid_count/pending_count are additive.
    referral_stats_data = await referral_service.stats(uid)

    return JSONResponse({
        'referral_code': user.referral_code if user else None,
        'referral_count': count,
        'total_bonus': referral_stats_data['total_bonus_toman'],
        'referral_url': f'{BASE_URL}/signup?ref={user.referral_code}' if user and user.referral_code else None,
        'referral_paid_count': referral_stats_data['paid_count'],
        'referral_pending_count': referral_stats_data['pending_count'],
    })


@router.post('/auth/logout')
async def logout(request: Request) -> JSONResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME) or \
        request.headers.get('Authorization', '').removeprefix('Bearer ')
    if token:
        uid = await _get_session_user_id(token)
        # session_meta goes with the session: track_session writes it on login
        # and it outlives the session otherwise (7d TTL vs SESSION_TTL).
        await rds.delete(f'session:{token}', f'session_meta:{token}')
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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    raw_members = await rds.smembers(f'sessions:{uid}')
    tokens = list(raw_members or [])
    for tok in tokens:
        await rds.delete(f'session:{tok}', f'session_meta:{tok}')
    await rds.delete(f'sessions:{uid}')
    await _write_audit_log('auth.logout_all', target_type='user', target_id=uid, details={'revoked_sessions': len(tokens)})
    response = JSONResponse({'status': 'ok', 'revoked_sessions': len(tokens)})
    _clear_session_cookie(response)
    return response


# ── Split-out route modules ─────────────────────────────────────
#
# These imports run AFTER `router` is defined above, so importing each
# module registers its `@auth.router.<verb>(...)`-decorated routes onto
# THIS router object as a side effect (same pattern as chat.py importing
# chat_web/chat_compare/chat_smart -- see those modules' docstrings). Every
# name is re-exported here (with `# noqa: F401`) purely so `auth.<name>`
# keeps resolving for any external consumer, exactly as if it were still
# defined directly in this file.
from auth_profile import (  # noqa: E402,F401 -- also registers /auth/change-password, /auth/profile, /auth/avatar
    ChangePasswordRequest, UpdateProfileRequest, AvatarUploadRequest,
    change_password, get_profile, update_profile, upload_avatar,
)
from auth_account import (  # noqa: E402,F401 -- also registers /auth/forgot-password, /auth/reset-password, /auth/telegram-link, /auth/telegram-token, /auth/send-welcome
    ForgotPasswordRequest, ResetPasswordRequest, TelegramLink, TelegramTokenRequest,
    forgot_password, reset_password, telegram_link, get_telegram_token, send_welcome_email,
)
