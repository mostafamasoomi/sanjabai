"""Profile management endpoints: change-password, profile get/update, avatar
upload -- split out of auth.py (see auth.py's module docstring for why).

IMPORT CONTRACT -- read before moving anything again. auth.py imports this
module's names AFTER its own `router` is defined, purely so that importing
this module registers `/auth/change-password`, `/auth/profile` (GET+PUT)
and `/auth/avatar` onto `auth.router` as a side effect (same pattern
chat_web.py/chat_compare.py/chat_smart.py use for chat.router -- see
chat.py's MONKEYPATCH CONTRACT docstring). auth.py re-exports every name
defined here so `auth.<name>` keeps resolving for external consumers.

tests/test_email_honesty.py and tests/test_site_flag_wiring.py patch
`auth._get_user_id` directly on the `auth` module object (not on this
file). Every function below therefore reads `_get_user_id` through
`auth._get_user_id(...)` at call time -- a plain `import auth`, never
`from auth import _get_user_id` and never a bare intra-module reference --
so that patch keeps reaching these routes. Do not "tidy" that into a direct
import.
"""
from __future__ import annotations

import base64
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import async_session
from models import User
from dependencies import _hash_password, _verify_password, _rotate_session, _write_audit_log
from i18n import err

import auth

router = auth.router


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


@router.post('/auth/change-password')
async def change_password(request: Request, payload: ChangePasswordRequest) -> JSONResponse:
    """Change user password"""
    uid = await auth._get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    from security import validate_password
    valid, verr_fa, verr_en = validate_password(payload.new_password)
    if not valid:
        return err(verr_fa, verr_en, 400)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()
        if not user or not _verify_password(payload.current_password, user.password_hash):
            return err('رمز عبور فعلی نادرست است', 'The current password is incorrect.', 401)

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
    uid = await auth._get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(User.__table__.select().where(User.id == uid))
        user = res.fetchone()
        if not user:
            return err('کاربر یافت نشد', 'User not found.', 404)

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
                'pinned_context': prefs.get('pinned_context', ''),
                'autonomy_level': prefs.get('autonomy_level', 'medium'),
                'notification_settings': prefs.get('notification_settings', {
                    'email': True,
                    'telegram': False,
                }),
                'smart_router_enabled': prefs.get('smart_router_enabled', True),
                'compression_enabled': prefs.get('compression_enabled', False),
            },
            'created_at': user.created_at,
            'referral_code': user.referral_code,
        }))


@router.put('/auth/profile')
async def update_profile(request: Request, payload: UpdateProfileRequest) -> JSONResponse:
    """Update user profile fields including preferences"""
    uid = await auth._get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    update_data: dict[str, Any] = {}
    if payload.display_name is not None:
        if len(payload.display_name) > 100:
            return err('نام نمایشی نباید بیشتر از ۱۰۰ کاراکتر باشد', 'Display name must not exceed 100 characters.', 400)
        update_data['display_name'] = payload.display_name.strip() or None
    if payload.bio is not None:
        if len(payload.bio) > 500:
            return err('بیوگرافی نباید بیشتر از ۵۰۰ کاراکتر باشد', 'Bio must not exceed 500 characters.', 400)
        update_data['bio'] = payload.bio.strip() or None
    if payload.timezone is not None:
        update_data['timezone'] = payload.timezone
    if payload.language is not None:
        if payload.language not in ('fa', 'en'):
            return err('زبان باید fa یا en باشد', 'Language must be fa or en.', 400)
        update_data['language'] = payload.language

    if payload.preferences is not None:
        async with async_session() as session:
            res = await session.execute(User.__table__.select().where(User.id == uid))
            user = res.fetchone()
            existing_prefs = (user.preferences or {}) if user else {}

        if 'autonomy_level' in payload.preferences:
            level = payload.preferences['autonomy_level']
            if level not in ('low', 'medium', 'high'):
                return err('سطح خودمختاری باید low، medium یا high باشد', 'Autonomy level must be low, medium, or high.', 400)

        if 'pinned_context' in payload.preferences:
            pinned = payload.preferences['pinned_context']
            if not isinstance(pinned, str):
                return err('یادداشت دائمی باید متن باشد', 'Pinned context must be text.', 400)
            if len(pinned) > 20000:
                return err('یادداشت دائمی نباید بیشتر از ۲۰,۰۰۰ کاراکتر باشد', 'Pinned context must not exceed 20,000 characters.', 400)

        if 'smart_router_enabled' in payload.preferences:
            smart_router = payload.preferences['smart_router_enabled']
            if not isinstance(smart_router, bool):
                return err('روتر هوشمند باید true یا false باشد', 'smart_router_enabled must be a boolean (true or false).', 400)

        if 'compression_enabled' in payload.preferences:
            compression = payload.preferences['compression_enabled']
            if not isinstance(compression, bool):
                return err('فشرده‌سازی پیام باید true یا false باشد', 'compression_enabled must be a boolean (true or false).', 400)

        existing_prefs.update(payload.preferences)
        update_data['preferences'] = existing_prefs

    if not update_data:
        return err('فیلد معتبری برای بروزرسانی وجود ندارد', 'No valid field to update.', 400)

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
    uid = await auth._get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    avatar_url = None

    if payload.avatar_url:
        if not payload.avatar_url.startswith(('http://', 'https://')):
            return err('آدرس تصویر نامعتبر است', 'Invalid image URL.', 400)
        if len(payload.avatar_url) > 2000:
            return err('آدرس تصویر بیش از حد طولانی است', 'Image URL is too long.', 400)
        avatar_url = payload.avatar_url
    elif payload.avatar_base64:
        raw = payload.avatar_base64
        if ',' in raw and raw.startswith('data:'):
            raw = raw.split(',', 1)[1]
        try:
            decoded = base64.b64decode(raw)
        except Exception:
            return err('تصویر نامعتبر است (base64 نادرست)', 'Invalid image (bad base64).', 400)
        if len(decoded) > 2 * 1024 * 1024:
            return err('حجم تصویر نباید بیشتر از ۲ مگابایت باشد', 'Image size must not exceed 2 MB.', 400)
        mime = 'image/jpeg'
        if decoded[:8] == b'\x89PNG\r\n\x1a\n':
            mime = 'image/png'
        elif decoded[:4] == b'RIFF' and decoded[8:12] == b'WEBP':
            mime = 'image/webp'
        elif decoded[:4] == b'GIF8':
            mime = 'image/gif'
        avatar_url = f'data:{mime};base64,{raw}'
    else:
        return err('آدرس تصویر یا داده base64 ارسال کنید', 'Provide an image URL or base64 data.', 400)

    async with async_session() as session:
        await session.execute(
            User.__table__.update().where(User.id == uid),
            {'avatar_url': avatar_url}
        )
        await session.commit()

    await _write_audit_log('auth.upload_avatar', target_type='user', target_id=uid)
    return JSONResponse({'status': 'ok', 'avatar_url': avatar_url})


@router.delete('/auth/avatar')
async def delete_avatar(request: Request) -> JSONResponse:
    """Clear the user's avatar. Idempotent -- deleting with no avatar set is
    still a success, not an error (same as the rest of this file's mutation
    endpoints never distinguish "already in the target state" from "changed
    it just now")."""
    uid = await auth._get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        await session.execute(
            User.__table__.update().where(User.id == uid),
            {'avatar_url': None}
        )
        await session.commit()

    await _write_audit_log('auth.delete_avatar', target_type='user', target_id=uid)
    return JSONResponse({'status': 'ok', 'avatar_url': None})
