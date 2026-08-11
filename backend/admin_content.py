"""
Admin site content and runtime configuration: marketing features, discount
codes, the about page, egress proxy settings and the org-wide default model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session, rds
from models import Feature, Discount, AboutContent, ProxyConfig
from dependencies import admin_required, _write_audit_log

router = APIRouter()

# ── Features ────────────────────────────────────────────────────

@router.get('/admin/features')
async def list_features(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Feature.__table__.select().order_by(Feature.order_idx))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/features')
async def upsert_feature(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    fid = payload.get('id')
    async with async_session() as session:
        if fid:
            row = await session.get(Feature, fid)
            if not row:
                return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        else:
            row = Feature()
            session.add(row)
        row.title = payload.get('title', row.title)
        row.description = payload.get('description', row.description)
        row.icon = payload.get('icon', row.icon)
        row.active = payload.get('active', row.active)
        row.order_idx = payload.get('order_idx', row.order_idx)
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    await _write_audit_log('admin.feature.upsert', target_type='feature', target_id=row.id)
    await rds.delete('cache:content:features')
    return JSONResponse({'status': 'ok', 'id': row.id})


@router.delete('/admin/features/{fid}')
async def delete_feature(request: Request, fid: int) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        row = await session.get(Feature, fid)
        if row:
            await session.delete(row)
            await session.commit()
    await _write_audit_log('admin.feature.delete', target_type='feature', target_id=fid)
    await rds.delete('cache:content:features')
    return JSONResponse({'status': 'deleted'})


# ── Discounts ───────────────────────────────────────────────────

@router.get('/admin/discounts')
async def list_discounts(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(Discount.__table__.select())
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/discounts')
async def upsert_discount(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    did = payload.get('id')
    code = payload.get('code')
    if not code:
        return JSONResponse({'detail': 'کد الزامی است'}, status_code=400)
    async with async_session() as session:
        if did:
            row = await session.get(Discount, did)
            if not row:
                return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        else:
            row = Discount()
            session.add(row)
        row.code = code
        row.percent = payload.get('percent', row.percent)
        row.active = payload.get('active', row.active)
        row.expires_at = payload.get('expires_at')
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    await _write_audit_log('admin.discount.upsert', target_type='discount', target_id=row.id)
    await rds.delete('cache:content:discounts')
    return JSONResponse({'status': 'ok', 'id': row.id})


@router.delete('/admin/discounts/{did}')
async def delete_discount(request: Request, did: int) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        row = await session.get(Discount, did)
        if row:
            await session.delete(row)
            await session.commit()
    await _write_audit_log('admin.discount.delete', target_type='discount', target_id=did)
    await rds.delete('cache:content:discounts')
    return JSONResponse({'status': 'deleted'})


# ── About ───────────────────────────────────────────────────────

@router.post('/admin/about')
async def set_about(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(AboutContent.__table__.select())
        row = res.fetchone()
        if not row:
            row = AboutContent()
            session.add(row)
        else:
            row = await session.get(AboutContent, row.id)
        row.title = payload.get('title', row.title)
        row.body = payload.get('body', row.body)
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    await _write_audit_log('admin.about.set')
    await rds.delete('cache:about')
    return JSONResponse({'status': 'ok'})


# ── Proxy Config ────────────────────────────────────────────────

@router.get('/admin/proxy')
async def get_proxy(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'proxy_url': '', 'proxy_type': 'socks5', 'active': False})
    async with async_session() as session:
        res = await session.execute(ProxyConfig.__table__.select())
        row = res.fetchone()
        if not row:
            return JSONResponse({'proxy_url': '', 'proxy_type': 'socks5', 'active': False})
        return JSONResponse(jsonable_encoder(dict(row._mapping)))


@router.post('/admin/proxy')
async def set_proxy(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    proxy_url = payload.get('proxy_url', '')
    if proxy_url:
        parsed = urlparse(proxy_url)
        _ALLOWED_PROXY_SCHEMES = {'socks5', 'socks5h', 'http', 'https'}
        if parsed.scheme not in _ALLOWED_PROXY_SCHEMES:
            return JSONResponse(
                {'detail': 'نوع پروکسی مجاز نیست', 'code': 'invalid_proxy_scheme'},
                status_code=400,
            )
        hostname = parsed.hostname or ''
        if hostname in ('localhost', '127.0.0.1', '0.0.0.0', '::1') or \
           hostname.startswith('10.') or hostname.startswith('192.168.') or \
           hostname.startswith('172.'):
            return JSONResponse(
                {'detail': 'آدرس پروکسی داخلی مجاز نیست', 'code': 'internal_proxy_blocked'},
                status_code=400,
            )

    async with async_session() as session:
        res = await session.execute(ProxyConfig.__table__.select())
        row = res.fetchone()
        if not row:
            row = ProxyConfig()
            session.add(row)
        else:
            row = await session.get(ProxyConfig, row.id)
        row.proxy_url = payload.get('proxy_url', row.proxy_url)
        row.proxy_type = payload.get('proxy_type', row.proxy_type)
        row.active = payload.get('active', row.active)
        row.default_model = payload.get('default_model', row.default_model)
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    await _write_audit_log('admin.proxy.set')
    await rds.delete('cache:org:default-model')
    return JSONResponse({'status': 'ok', 'proxy_url': row.proxy_url})


@router.post('/admin/org-default-model')
async def set_org_default_model(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Admin: set org-wide default model."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    model_id = payload.get('default_model', '')
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(ProxyConfig.__table__.select())
        row = res.fetchone()
        if not row:
            row = ProxyConfig(default_model=model_id)
            session.add(row)
        else:
            row = await session.get(ProxyConfig, row.id)
            row.default_model = model_id
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    await _write_audit_log('admin.org_default_model.set', details={'model': model_id})
    await rds.delete('cache:org:default-model')
    return JSONResponse({'status': 'ok', 'default_model': model_id})
