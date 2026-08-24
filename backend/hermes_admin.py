"""Hermes server product -- admin routes: `/admin/hermes/*` (delivery queue
+ catalog CRUD for the admin panel).

Split out of hermes.py purely to stay under the house 500-line cap -- see
hermes.py's module docstring for the full product overview and the
IMPORT/MONKEYPATCH CONTRACT this file follows. Nothing here changed in the
move.

`import hermes` is done plainly at module scope, which is safe against the
hermes.py <-> hermes_admin.py circular import: nothing here touches a
`hermes` attribute until a function/decorator actually runs (the
`@hermes.router...` decorators below execute when *this* module is
imported, which hermes.py only does after `router = APIRouter()` has
already run -- see the bottom of hermes.py).

SAFETY NOTE: `admin_provision_order` below writes a `Notification` row
(delivery confirmation) inside the same `async with async_session() as
session:` transaction that creates the `ApiKey` and `HermesServer` rows and
flips the order to `active` -- one `session.commit()` covers all of it.
That transaction was moved as a single, unmodified unit; its extent
(everything from `async with async_session()` down to `await
session.commit()`) is unchanged from before the split.
"""
from __future__ import annotations

import secrets
from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

import hermes
from database import async_session
from models import ApiKey, HermesOffering, HermesSkillCatalog, HermesOrder, HermesServer, HermesServerSkill, Notification
from dependencies import admin_required, _write_audit_log, _hash_api_key
from hermes import _utcnow


# ── Pydantic models ─────────────────────────────────────────────

class ProvisionRequest(BaseModel):
    hostname: str | None = None
    ip_address: str
    ssh_port: int = 22
    region: str | None = None


class OfferingUpsert(BaseModel):
    id: str
    name_fa: str
    name_en: str
    description_fa: str = ''
    description_en: str = ''
    hetzner_type: str
    arch: str = 'amd64'
    vcpu: int
    ram_mb: int
    disk_gb: int
    traffic_tb: int = 20
    provider_cost_eur: float
    margin_pct: int = 50
    setup_fee_irt: int = 0
    max_skills: int = 5
    included_credit: int = 0
    active: bool = True
    sort_order: int = 0


class SkillCatalogUpsert(BaseModel):
    id: str
    name_fa: str
    name_en: str
    description_fa: str = ''
    description_en: str = ''
    category: str = 'general'
    manifest: dict[str, Any] = {}
    options_schema: dict[str, Any] = {}
    requires_cron: bool = False
    active: bool = True
    sort_order: int = 0


# ══════════════════════════════════════════════════════════════════
# Admin
# ══════════════════════════════════════════════════════════════════

@hermes.router.get('/admin/hermes/orders')
async def admin_list_orders(request: Request, status: str | None = None) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        query = select(HermesOrder).order_by(HermesOrder.created_at.desc())
        if status:
            query = query.where(HermesOrder.status == status)
        res = await session.execute(query)
        orders = [row[0] for row in res.fetchall()]
    return JSONResponse(jsonable_encoder(orders))


@hermes.router.post('/admin/hermes/orders/{order_id}/provision')
async def admin_provision_order(request: Request, order_id: int, payload: ProvisionRequest) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    raw_agent_token = f'hsa-{secrets.token_urlsafe(32)}'
    raw_api_key = f'sk-{secrets.token_urlsafe(32)}'

    async with async_session() as session:
        order_res = await session.execute(select(HermesOrder).where(HermesOrder.id == order_id))
        order = order_res.scalar_one_or_none()
        if not order:
            return JSONResponse({'detail': 'سفارش یافت نشد'}, status_code=404)
        if order.status != 'paid':
            return JSONResponse({'detail': 'سفارش در وضعیت قابل تحویل نیست'}, status_code=400)

        api_key = ApiKey(
            user_id=order.user_id, name=f'hermes-server-order-{order.id}',
            key_hash=_hash_api_key(raw_api_key), key_prefix=raw_api_key[:12], scopes='chat',
        )
        session.add(api_key)
        await session.flush()

        server = HermesServer(
            order_id=order.id, user_id=order.user_id, offering_id=order.offering_id,
            hostname=payload.hostname, ip_address=payload.ip_address, ssh_port=payload.ssh_port,
            region=payload.region, status='active', monthly_price_irt=order.monthly_price_irt,
            paid_through_at=_utcnow() + timedelta(days=30),
            agent_token_hash=_hash_api_key(raw_agent_token), agent_token_prefix=raw_agent_token[:12],
            api_key_id=api_key.id, desired_state_version=1,
        )
        session.add(server)
        await session.flush()

        for sel in (order.requested_config or {}).get('skills', []):
            session.add(HermesServerSkill(
                server_id=server.id, skill_id=sel['skill_id'], options=sel.get('options', {}),
                enabled=True, state='pending',
            ))

        order.status = 'active'
        order.delivered_at = _utcnow()
        order.updated_at = _utcnow()

        session.add(Notification(
            user_id=order.user_id, type='hermes',
            title='سرور هرمس شما آماده شد', body=f'سرور شما با آی‌پی {payload.ip_address} فعال شد.',
        ))
        await session.commit()

    await _write_audit_log('admin.hermes.provision', target_type='hermes_order', target_id=order_id, request=request)
    return JSONResponse({
        'status': 'ok', 'server_id': server.id, 'agent_token': raw_agent_token, 'api_key': raw_api_key,
    })


@hermes.router.post('/admin/hermes/servers/{server_id}/suspend')
async def admin_suspend_server(request: Request, server_id: int) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        server = await session.get(HermesServer, server_id)
        if not server:
            return JSONResponse({'detail': 'سرور یافت نشد'}, status_code=404)
        server.status = 'suspended'
        server.updated_at = _utcnow()
        await session.commit()
    await _write_audit_log('admin.hermes.suspend', target_type='hermes_server', target_id=server_id, request=request)
    return JSONResponse({'status': 'ok'})


@hermes.router.post('/admin/hermes/servers/{server_id}/terminate')
async def admin_terminate_server(request: Request, server_id: int) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        server = await session.get(HermesServer, server_id)
        if not server:
            return JSONResponse({'detail': 'سرور یافت نشد'}, status_code=404)
        server.status = 'terminated'
        server.updated_at = _utcnow()
        await session.commit()
    await _write_audit_log('admin.hermes.terminate', target_type='hermes_server', target_id=server_id, request=request)
    return JSONResponse({'status': 'ok'})


@hermes.router.get('/admin/hermes/offerings')
async def admin_list_offerings(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(select(HermesOffering).order_by(HermesOffering.sort_order))
        rows = [row[0] for row in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@hermes.router.post('/admin/hermes/offerings')
async def admin_upsert_offering(request: Request, payload: OfferingUpsert) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        existing = await session.get(HermesOffering, payload.id)
        data = payload.model_dump()
        data['provider_cost_eur'] = Decimal(str(data['provider_cost_eur']))
        if existing:
            for k, v in data.items():
                if k != 'id':
                    setattr(existing, k, v)
            existing.updated_at = _utcnow()
        else:
            session.add(HermesOffering(**data))
        await session.commit()
    await _write_audit_log('admin.hermes.offering.upsert', target_type='hermes_offering', target_id=payload.id, request=request)
    return JSONResponse({'status': 'ok', 'id': payload.id})


@hermes.router.get('/admin/hermes/skill-catalog')
async def admin_list_skill_catalog(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(select(HermesSkillCatalog).order_by(HermesSkillCatalog.sort_order))
        rows = [row[0] for row in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@hermes.router.post('/admin/hermes/skill-catalog')
async def admin_upsert_skill_catalog(request: Request, payload: SkillCatalogUpsert) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        existing = await session.get(HermesSkillCatalog, payload.id)
        data = payload.model_dump()
        if existing:
            for k, v in data.items():
                if k != 'id':
                    setattr(existing, k, v)
            existing.updated_at = _utcnow()
        else:
            session.add(HermesSkillCatalog(**data))
        await session.commit()
    await _write_audit_log('admin.hermes.skill_catalog.upsert', target_type='hermes_skill_catalog', target_id=payload.id, request=request)
    return JSONResponse({'status': 'ok', 'id': payload.id})
