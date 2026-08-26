"""
API key management endpoints.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import async_session
from models import ApiKey
from dependencies import _get_user_id, _hash_api_key, _write_audit_log
from i18n import err

router = APIRouter()


class ApiKeyCreate(BaseModel):
    name: str = 'Default'
    scopes: str = 'read'
    expires_at: str | None = None


@router.post('/api-keys')
async def create_api_key(request: Request, payload: ApiKeyCreate) -> JSONResponse:
    """Generate a new API key. The secret is shown only once."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    raw_key = f'sk-{secrets.token_urlsafe(32)}'
    key_hash = _hash_api_key(raw_key)
    key_prefix = raw_key[:12]

    expires_at = None
    if payload.expires_at:
        try:
            expires_at = datetime.fromisoformat(payload.expires_at)
        except ValueError:
            return err('تاریخ انقضا نامعتبر است (فرمت ISO8601 مورد انتظار)', 'Invalid expiration date (ISO8601 format expected).', 400)

    async with async_session() as session:
        key = ApiKey(
            user_id=uid, name=payload.name, key_hash=key_hash,
            key_prefix=key_prefix, scopes=payload.scopes, expires_at=expires_at,
        )
        session.add(key)
        await session.commit()
        await session.refresh(key)

    await _write_audit_log('api_key.create', target_type='api_key', target_id=key.id, details={'name': payload.name, 'prefix': key_prefix})
    return JSONResponse({
        'id': key.id, 'name': key.name, 'key': raw_key, 'prefix': key_prefix,
        'masked': f"{key_prefix}••••••••••••", 'scopes': key.scopes,
        'expires_at': key.expires_at.isoformat() if key.expires_at else None,
        'created_at': key.created_at.isoformat() if key.created_at else None,
    })


@router.get('/api-keys')
async def list_api_keys(request: Request) -> JSONResponse:
    """List user's API keys (never expose raw key)"""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(
            ApiKey.__table__.select()
            .where(ApiKey.user_id == uid)
            .order_by(ApiKey.created_at.desc())
        )
        rows = [
            {
                'id': r.id, 'name': r.name, 'prefix': r.key_prefix,
                'masked': f"{r.key_prefix}••••••••••••", 'scopes': r.scopes,
                'active': r.active,
                'revoked_at': r.revoked_at.isoformat() if r.revoked_at else None,
                'expires_at': r.expires_at.isoformat() if r.expires_at else None,
                'last_used_at': r.last_used.isoformat() if r.last_used else None,
                'created_at': r.created_at.isoformat() if r.created_at else None,
            }
            for r in res.fetchall()
        ]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/api-keys/{key_id}/rotate')
async def rotate_api_key(request: Request, key_id: int) -> JSONResponse:
    """Issue a fresh secret for an existing API key; the old secret stops
    authenticating the moment this commits. The raw key is returned exactly
    once, just like creation — reuses the same generation/hashing code path
    (`secrets.token_urlsafe` + `_hash_api_key`), never a second implementation.

    Rotation semantics: the existing row is updated in place (same id, name,
    scopes, created_at, usage history) — only key_hash/key_prefix change.
    This avoids orphaning a row and keeps a single source of truth per named
    key, at the cost of losing the previous secret's audit trail as a
    separate row (the audit log entry below preserves that history instead).
    """
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(
            ApiKey.__table__.select().where(ApiKey.id == key_id, ApiKey.user_id == uid)
        )
        row = res.fetchone()
        if row is None:
            return err('کلید یافت نشد', 'Key not found.', 404)
        if not row.active:
            return err('کلید غیرفعال است و قابل چرخش نیست', 'Key is inactive and cannot be rotated.', 400)

        raw_key = f'sk-{secrets.token_urlsafe(32)}'
        key_hash = _hash_api_key(raw_key)
        key_prefix = raw_key[:12]

        await session.execute(
            ApiKey.__table__.update()
            .where(ApiKey.id == key_id, ApiKey.user_id == uid),
            {'key_hash': key_hash, 'key_prefix': key_prefix}
        )
        await session.commit()

    await _write_audit_log('api_key.rotate', target_type='api_key', target_id=key_id, details={'user_id': uid, 'prefix': key_prefix})
    return JSONResponse({
        'id': key_id, 'name': row.name, 'key': raw_key, 'prefix': key_prefix,
        'masked': f"{key_prefix}••••••••••••", 'scopes': row.scopes,
        'expires_at': row.expires_at.isoformat() if row.expires_at else None,
        'created_at': row.created_at.isoformat() if row.created_at else None,
    })


@router.delete('/api-keys/{key_id}')
async def revoke_api_key(request: Request, key_id: int) -> JSONResponse:
    """Revoke (deactivate) an API key"""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        await session.execute(
            ApiKey.__table__.update()
            .where(ApiKey.id == key_id, ApiKey.user_id == uid),
            {'active': False, 'revoked_at': datetime.now(timezone.utc).replace(tzinfo=None)}
        )
        await session.commit()
    await _write_audit_log('api_key.revoke', target_type='api_key', target_id=key_id, details={'user_id': uid})
    return JSONResponse({'status': 'revoked'})
