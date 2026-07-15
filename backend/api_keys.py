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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    raw_key = f'sk-{secrets.token_urlsafe(32)}'
    key_hash = _hash_api_key(raw_key)
    key_prefix = raw_key[:12]

    expires_at = None
    if payload.expires_at:
        try:
            expires_at = datetime.fromisoformat(payload.expires_at)
        except ValueError:
            return JSONResponse({'detail': 'تاریخ انقضا نامعتبر است (فرمت ISO8601 مورد انتظار)'}, status_code=400)

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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

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


@router.delete('/api-keys/{key_id}')
async def revoke_api_key(request: Request, key_id: int) -> JSONResponse:
    """Revoke (deactivate) an API key"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        await session.execute(
            ApiKey.__table__.update()
            .where(ApiKey.id == key_id, ApiKey.user_id == uid),
            {'active': False, 'revoked_at': datetime.now(timezone.utc).replace(tzinfo=None)}
        )
        await session.commit()
    await _write_audit_log('api_key.revoke', target_type='api_key', target_id=key_id, details={'user_id': uid})
    return JSONResponse({'status': 'revoked'})
