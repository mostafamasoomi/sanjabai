"""Admin content endpoints: Features, Discounts, About, Proxy Config
(including org-default-model).

Split out of admin.py (house 500-line cap) -- see admin.py's module
docstring for the full split map. Pure move: no behaviour change.

MONKEYPATCH CONTRACT: routes here gate on `admin.admin_required(request)`
(via a plain `import admin`, never `from admin import admin_required`) --
see admin.py's own module docstring for why.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session, rds
from models import Feature, Discount, AboutContent, ProxyConfig
import admin
from dependencies import _write_audit_log
from i18n import bi, err

router = APIRouter()


# ── Features ────────────────────────────────────────────────────

@router.get('/admin/features')
async def list_features(request: Request) -> JSONResponse:
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(Feature.__table__.select().order_by(Feature.order_idx))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/features')
async def upsert_feature(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    fid = payload.get('id')
    async with async_session() as session:
        if fid:
            row = await session.get(Feature, fid)
            if not row:
                return err('یافت نشد', 'Not found.', 404)
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
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
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
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(Discount.__table__.select())
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/discounts')
async def upsert_discount(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    did = payload.get('id')
    code = payload.get('code')
    if not code:
        return err('کد الزامی است', 'Code is required.', 400)
    async with async_session() as session:
        if did:
            row = await session.get(Discount, did)
            if not row:
                return err('یافت نشد', 'Not found.', 404)
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
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    async with async_session() as session:
        row = await session.get(Discount, did)
        if row:
            await session.delete(row)
            await session.commit()
    await _write_audit_log('admin.discount.delete', target_type='discount', target_id=did)
    await rds.delete('cache:content:discounts')
    return JSONResponse({'status': 'deleted'})


# ── About ───────────────────────────────────────────────────────

@router.get('/admin/about')
async def get_about_admin(request: Request) -> JSONResponse:
    """Current about content, for the admin edit form.

    Without this the panel could only POST blind: the form loaded empty and
    a save overwrote the live page with whatever happened to be in the boxes
    -- usually nothing (session 11 found the panel GETting this path and
    silently swallowing the 405). Same shape the form saves: title/body.
    """
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return JSONResponse({'title': '', 'body': ''})
    async with async_session() as session:
        res = await session.execute(AboutContent.__table__.select())
        row = res.fetchone()
        if not row:
            return JSONResponse({'title': '', 'body': ''})
        return JSONResponse({'title': row.title or '', 'body': row.body or ''})


@router.post('/admin/about')
async def set_about(request: Request, payload: dict[str, Any]) -> JSONResponse:
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
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
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
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
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)

    proxy_url = payload.get('proxy_url', '')
    if proxy_url:
        parsed = urlparse(proxy_url)
        _ALLOWED_PROXY_SCHEMES = {'socks5', 'socks5h', 'http', 'https'}
        if parsed.scheme not in _ALLOWED_PROXY_SCHEMES:
            return JSONResponse(
                bi({'code': 'invalid_proxy_scheme'},
                   detail=('نوع پروکسی مجاز نیست', 'Proxy scheme is not allowed.')),
                status_code=400,
            )
        hostname = parsed.hostname or ''
        if hostname in ('localhost', '127.0.0.1', '0.0.0.0', '::1') or \
           hostname.startswith('10.') or hostname.startswith('192.168.') or \
           hostname.startswith('172.'):
            return JSONResponse(
                bi({'code': 'internal_proxy_blocked'},
                   detail=('آدرس پروکسی داخلی مجاز نیست', 'Internal proxy addresses are not allowed.')),
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
    """Admin: set org-wide default model.

    ``default_model`` used to be written verbatim, with no check that the
    id even exists -- one typo here and every new chat silently pointed at
    a dead model. Empty string stays legal on purpose: the frontend offers
    it explicitly to mean "no default, use the first model in the list",
    so it must not be forced through the model_catalog lookup below. Any
    non-empty value must name a row that both exists AND is currently
    `availability = 'available'` -- pointing the org default at a
    maintenance/disabled/degraded row would silently break every new chat
    started against it.
    """
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    model_id = payload.get('default_model', '')
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        if model_id:
            res = await session.execute(sqlalchemy.text(
                'SELECT availability FROM model_catalog WHERE id = :id'
            ), {'id': model_id})
            row = res.fetchone()
            if row is None:
                return err(
                    f'مدل «{model_id}» در کاتالوگ یافت نشد',
                    f'Model "{model_id}" was not found in the catalog.', 400,
                )
            if row.availability != 'available':
                return err(
                    f'مدل «{model_id}» فعال نیست و نمی‌تواند پیش‌فرض سازمان باشد '
                    '(فقط مدلی که وضعیت آن «فعال» است مجاز است).',
                    f'Model "{model_id}" is not active and cannot be the org default '
                    '(only a model with "available" status is allowed).', 400,
                )
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


