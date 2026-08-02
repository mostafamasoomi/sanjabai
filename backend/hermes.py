"""Hermes server product: sell a ready-to-use VPS with the Hermes agent
pre-installed, plus a catalog of installable "skills" the user picks at
checkout or later from the dashboard.

Route groups:
  /hermes/*        user-facing catalog, orders, and server/skill management
  /hermes/agent/*  the agent daemon running on the delivered VPS (token auth,
                    not the session cookie)
  /admin/hermes/*  delivery queue and catalog CRUD for the admin panel

Pricing: offerings carry a EUR cost basis (Hetzner) + margin; GET
/hermes/offerings converts to Toman live using the current eur_to_irt rate
(see content._get_cached_eur_to_irt). Orders and servers snapshot the
computed Toman price at purchase time, so an exchange-rate move never
changes what an existing customer owes -- only the live catalog price
before checkout.
"""
from __future__ import annotations

import math
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from database import async_session, BASE_URL
from services.billing import SqlBillingRepo
from models import (
    HermesOffering, HermesSkillCatalog, HermesOrder, HermesServer,
    HermesServerSkill, HermesAgentEvent, ApiKey, Payment, Ledger,
    Notification,
)
from dependencies import _get_user_id, admin_required, _write_audit_log, _hash_api_key
from content import _get_cached_eur_to_irt
from payment import create_payment

router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _round_up_1000(value: float) -> int:
    """Round a Toman amount up to the nearest 1,000 so prices stay clean."""
    return int(math.ceil(value / 1000.0)) * 1000


# ── Pydantic models ─────────────────────────────────────────────

class SkillSelection(BaseModel):
    skill_id: str
    options: dict[str, Any] = {}


class OrderConfig(BaseModel):
    skills: list[SkillSelection] = []


class OrderCreate(BaseModel):
    offering_id: str
    config: OrderConfig = OrderConfig()


class SkillAttach(BaseModel):
    skill_id: str
    options: dict[str, Any] = {}


class SkillUpdate(BaseModel):
    options: dict[str, Any] | None = None
    enabled: bool | None = None


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


class AgentReportItem(BaseModel):
    skill_id: str
    state: str  # 'installed' | 'failed' | 'removed'
    error: str | None = None


class AgentReport(BaseModel):
    version: int
    results: list[AgentReportItem] = []


# ── Pricing ──────────────────────────────────────────────────────

async def _price_offering(offering: HermesOffering) -> tuple[int, int, float]:
    """Convert an offering's EUR cost basis to locked Toman prices.

    Returns (setup_price_irt, monthly_price_irt, eur_to_irt_rate). Never
    returns EUR figures to callers that might expose them publicly -- only
    the resulting Toman amounts and the rate used (for audit/lock purposes).
    """
    eur_rate = await _get_cached_eur_to_irt()
    raw_monthly = float(offering.provider_cost_eur) * eur_rate * (1 + offering.margin_pct / 100)
    monthly_price_irt = _round_up_1000(raw_monthly)
    setup_price_irt = offering.setup_fee_irt
    return setup_price_irt, monthly_price_irt, eur_rate


def _offering_public(offering: HermesOffering, setup_price_irt: int, monthly_price_irt: int) -> dict:
    """Public-facing offering shape -- no EUR fields, ever."""
    return {
        'id': offering.id,
        'name_fa': offering.name_fa,
        'name_en': offering.name_en,
        'description_fa': offering.description_fa,
        'description_en': offering.description_en,
        'arch': offering.arch,
        'vcpu': offering.vcpu,
        'ram_mb': offering.ram_mb,
        'disk_gb': offering.disk_gb,
        'traffic_tb': offering.traffic_tb,
        'max_skills': offering.max_skills,
        'included_credit': offering.included_credit,
        'setup_price_irt': setup_price_irt,
        'monthly_price_irt': monthly_price_irt,
        'currency': 'IRT',
    }


# ── Config / options-schema validation ───────────────────────────

def _validate_skill_options(schema: dict, options: dict) -> str | None:
    """Validate `options` against a skill's `options_schema`.

    Returns a Persian error message on failure, or None if valid. Schema
    shape example:
      {"languages": {"type": "multiselect", "values": [...], "max": 5}}
      {"topics": {"type": "tags", "max": 10}}
      {"schedule": {"type": "cron", "default": "0 9 * * *"}}
    Unknown option keys are ignored (forward-compatible); missing optional
    keys are fine. This is intentionally permissive -- it catches obviously
    bad input, not every edge case.
    """
    if not isinstance(options, dict):
        return 'گزینه‌های اسکیل نامعتبر است'
    for key, spec in (schema or {}).items():
        if key not in options:
            continue
        value = options[key]
        field_type = spec.get('type')
        if field_type == 'multiselect':
            if not isinstance(value, list):
                return f'{key} باید فهرستی از مقادیر باشد'
            allowed = spec.get('values')
            if allowed and any(v not in allowed for v in value):
                return f'مقدار نامعتبر در {key}'
            max_items = spec.get('max')
            if max_items and len(value) > max_items:
                return f'حداکثر {max_items} مورد برای {key} مجاز است'
        elif field_type == 'tags':
            if not isinstance(value, list):
                return f'{key} باید فهرستی از مقادیر باشد'
            max_items = spec.get('max')
            if max_items and len(value) > max_items:
                return f'حداکثر {max_items} مورد برای {key} مجاز است'
        elif field_type == 'cron':
            if not isinstance(value, str) or not value.strip():
                return f'{key} باید یک عبارت cron معتبر باشد'
    return None


# ══════════════════════════════════════════════════════════════════
# User-facing catalog
# ══════════════════════════════════════════════════════════════════

@router.get('/hermes/offerings')
async def list_offerings() -> JSONResponse:
    """Public server catalog, live-priced in Toman. No EUR fields ever."""
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            select(HermesOffering).where(HermesOffering.active == True).order_by(HermesOffering.sort_order)
        )
        offerings = [row[0] for row in res.fetchall()]

    items = []
    for offering in offerings:
        setup_price_irt, monthly_price_irt, _rate = await _price_offering(offering)
        items.append(_offering_public(offering, setup_price_irt, monthly_price_irt))
    return JSONResponse(jsonable_encoder(items))


@router.get('/hermes/skill-catalog')
async def list_skill_catalog() -> JSONResponse:
    """Public catalog of skills installable on a Hermes server."""
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            select(HermesSkillCatalog).where(HermesSkillCatalog.active == True).order_by(HermesSkillCatalog.sort_order)
        )
        rows = [row[0] for row in res.fetchall()]

    items = [{
        'id': s.id, 'name_fa': s.name_fa, 'name_en': s.name_en,
        'description_fa': s.description_fa, 'description_en': s.description_en,
        'category': s.category, 'options_schema': s.options_schema,
        'requires_cron': s.requires_cron,
    } for s in rows]
    return JSONResponse(jsonable_encoder(items))


# ══════════════════════════════════════════════════════════════════
# Orders
# ══════════════════════════════════════════════════════════════════

@router.post('/hermes/orders')
async def create_order(request: Request, payload: OrderCreate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    if len(payload.config.skills) > 20:
        return JSONResponse({'detail': 'تعداد اسکیل‌های درخواستی بیش از حد مجاز است'}, status_code=400)

    async with async_session() as session:
        offering_res = await session.execute(
            select(HermesOffering).where(HermesOffering.id == payload.offering_id, HermesOffering.active == True)
        )
        offering = offering_res.scalar_one_or_none()
        if not offering:
            return JSONResponse({'detail': 'سرویس یافت نشد'}, status_code=404)

        if len(payload.config.skills) > offering.max_skills:
            return JSONResponse(
                {'detail': f'این پلن حداکثر {offering.max_skills} اسکیل پشتیبانی می‌کند'}, status_code=400
            )

        seen_skill_ids: set[str] = set()
        for sel in payload.config.skills:
            if sel.skill_id in seen_skill_ids:
                return JSONResponse({'detail': 'اسکیل تکراری در سفارش'}, status_code=400)
            seen_skill_ids.add(sel.skill_id)
            skill_res = await session.execute(
                select(HermesSkillCatalog).where(HermesSkillCatalog.id == sel.skill_id, HermesSkillCatalog.active == True)
            )
            skill = skill_res.scalar_one_or_none()
            if not skill:
                return JSONResponse({'detail': f'اسکیل «{sel.skill_id}» یافت نشد'}, status_code=404)
            error = _validate_skill_options(skill.options_schema, sel.options)
            if error:
                return JSONResponse({'detail': error}, status_code=400)

        setup_price_irt, monthly_price_irt, eur_rate = await _price_offering(offering)
        total = setup_price_irt + monthly_price_irt

        order = HermesOrder(
            user_id=uid, offering_id=offering.id, status='pending_payment',
            setup_price_irt=setup_price_irt, monthly_price_irt=monthly_price_irt,
            eur_rate_at_order=Decimal(str(round(eur_rate, 2))), priced_at=_utcnow(),
            requested_config=payload.config.model_dump(),
        )
        session.add(order)
        await session.flush()

        if total <= 0:
            await session.rollback()
            return JSONResponse({'detail': 'قیمت سرویس نامعتبر است'}, status_code=400)

        result = await create_payment(
            amount=total,
            description=f"سرور هرمس: {offering.name_fa}",
            callback_url=f"{BASE_URL}/api/payment/callback",
        )
        if result.get('status') != 'ok':
            await session.rollback()
            return JSONResponse({'detail': result.get('error', 'payment failed')}, status_code=result.get('status', 500) if isinstance(result.get('status'), int) else 500)

        payment = Payment(
            user_id=uid, amount=total, authority=result['authority'],
            status='pending', payment_type='hermes_order', reference_id=str(order.id),
        )
        session.add(payment)
        await session.flush()
        order.payment_id = payment.id
        await session.commit()

    return JSONResponse({
        'order_id': order.id, 'authority': result['authority'], 'url': result['url'],
        'amount': total, 'setup_price_irt': setup_price_irt, 'monthly_price_irt': monthly_price_irt,
    })


@router.get('/hermes/orders')
async def list_orders(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            select(HermesOrder).where(HermesOrder.user_id == uid).order_by(HermesOrder.created_at.desc())
        )
        orders = [row[0] for row in res.fetchall()]
    return JSONResponse(jsonable_encoder(orders))


@router.get('/hermes/orders/{order_id}')
async def get_order(request: Request, order_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(select(HermesOrder).where(HermesOrder.id == order_id))
        order = res.scalar_one_or_none()
        if not order or order.user_id != uid:
            return JSONResponse({'detail': 'سفارش یافت نشد'}, status_code=404)
    return JSONResponse(jsonable_encoder(order))


# ══════════════════════════════════════════════════════════════════
# Servers
# ══════════════════════════════════════════════════════════════════

async def _load_owned_server(session, server_id: int, uid: int) -> HermesServer | None:
    res = await session.execute(select(HermesServer).where(HermesServer.id == server_id))
    server = res.scalar_one_or_none()
    if not server or server.user_id != uid:
        return None
    return server


@router.get('/hermes/servers')
async def list_servers(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            select(HermesServer).where(HermesServer.user_id == uid).order_by(HermesServer.created_at.desc())
        )
        servers = [row[0] for row in res.fetchall()]
    return JSONResponse(jsonable_encoder([_server_public(s) for s in servers]))


def _server_public(server: HermesServer) -> dict:
    """Server shape safe to return to the owning user -- no token hash."""
    return {
        'id': server.id, 'order_id': server.order_id, 'offering_id': server.offering_id,
        'hostname': server.hostname, 'ip_address': server.ip_address, 'ssh_port': server.ssh_port,
        'region': server.region, 'status': server.status,
        'monthly_price_irt': server.monthly_price_irt, 'paid_through_at': server.paid_through_at,
        'agent_token_prefix': server.agent_token_prefix,
        'desired_state_version': server.desired_state_version,
        'applied_state_version': server.applied_state_version,
        'in_sync': server.desired_state_version == server.applied_state_version,
        'last_heartbeat_at': server.last_heartbeat_at, 'agent_version': server.agent_version,
        'created_at': server.created_at,
    }


@router.get('/hermes/servers/{server_id}')
async def get_server(request: Request, server_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        server = await _load_owned_server(session, server_id, uid)
        if not server:
            return JSONResponse({'detail': 'سرور یافت نشد'}, status_code=404)
        skills_res = await session.execute(
            select(HermesServerSkill).where(HermesServerSkill.server_id == server.id)
        )
        skills = [row[0] for row in skills_res.fetchall()]

    data = _server_public(server)
    data['skills'] = jsonable_encoder(skills)
    return JSONResponse(jsonable_encoder(data))


@router.post('/hermes/servers/{server_id}/skills')
async def attach_skill(request: Request, server_id: int, payload: SkillAttach) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        server = await _load_owned_server(session, server_id, uid)
        if not server:
            return JSONResponse({'detail': 'سرور یافت نشد'}, status_code=404)

        skill_res = await session.execute(
            select(HermesSkillCatalog).where(HermesSkillCatalog.id == payload.skill_id, HermesSkillCatalog.active == True)
        )
        skill = skill_res.scalar_one_or_none()
        if not skill:
            return JSONResponse({'detail': 'اسکیل یافت نشد'}, status_code=404)

        error = _validate_skill_options(skill.options_schema, payload.options)
        if error:
            return JSONResponse({'detail': error}, status_code=400)

        offering_res = await session.execute(select(HermesOffering).where(HermesOffering.id == server.offering_id))
        offering = offering_res.scalar_one_or_none()

        existing_res = await session.execute(
            select(HermesServerSkill).where(
                HermesServerSkill.server_id == server.id, HermesServerSkill.enabled == True
            )
        )
        existing_count = len(existing_res.fetchall())
        if offering and existing_count >= offering.max_skills:
            return JSONResponse({'detail': f'این سرور حداکثر {offering.max_skills} اسکیل پشتیبانی می‌کند'}, status_code=400)

        dup_res = await session.execute(
            select(HermesServerSkill).where(
                HermesServerSkill.server_id == server.id, HermesServerSkill.skill_id == payload.skill_id
            )
        )
        if dup_res.scalar_one_or_none():
            return JSONResponse({'detail': 'این اسکیل قبلاً روی سرور نصب شده است'}, status_code=400)

        row = HermesServerSkill(
            server_id=server.id, skill_id=payload.skill_id, options=payload.options,
            enabled=True, state='pending',
        )
        session.add(row)
        server.desired_state_version += 1
        server.updated_at = _utcnow()
        await session.commit()

    return JSONResponse({'status': 'ok', 'desired_state_version': server.desired_state_version})


@router.put('/hermes/servers/{server_id}/skills/{skill_id}')
async def update_skill(request: Request, server_id: int, skill_id: str, payload: SkillUpdate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        server = await _load_owned_server(session, server_id, uid)
        if not server:
            return JSONResponse({'detail': 'سرور یافت نشد'}, status_code=404)

        row_res = await session.execute(
            select(HermesServerSkill).where(
                HermesServerSkill.server_id == server.id, HermesServerSkill.skill_id == skill_id
            )
        )
        row = row_res.scalar_one_or_none()
        if not row:
            return JSONResponse({'detail': 'اسکیل روی این سرور نصب نیست'}, status_code=404)

        if payload.options is not None:
            catalog_res = await session.execute(select(HermesSkillCatalog).where(HermesSkillCatalog.id == skill_id))
            catalog = catalog_res.scalar_one_or_none()
            error = _validate_skill_options(catalog.options_schema if catalog else {}, payload.options)
            if error:
                return JSONResponse({'detail': error}, status_code=400)
            row.options = payload.options
        if payload.enabled is not None:
            row.enabled = payload.enabled

        row.state = 'pending'
        row.updated_at = _utcnow()
        server.desired_state_version += 1
        server.updated_at = _utcnow()
        await session.commit()

    return JSONResponse({'status': 'ok', 'desired_state_version': server.desired_state_version})


@router.delete('/hermes/servers/{server_id}/skills/{skill_id}')
async def remove_skill(request: Request, server_id: int, skill_id: str) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        server = await _load_owned_server(session, server_id, uid)
        if not server:
            return JSONResponse({'detail': 'سرور یافت نشد'}, status_code=404)

        row_res = await session.execute(
            select(HermesServerSkill).where(
                HermesServerSkill.server_id == server.id, HermesServerSkill.skill_id == skill_id
            )
        )
        row = row_res.scalar_one_or_none()
        if not row:
            return JSONResponse({'detail': 'اسکیل روی این سرور نصب نیست'}, status_code=404)

        # Not deleted immediately -- the agent must confirm removal via
        # POST /hermes/agent/report before the row disappears.
        row.state = 'removing'
        row.enabled = False
        row.updated_at = _utcnow()
        server.desired_state_version += 1
        server.updated_at = _utcnow()
        await session.commit()

    return JSONResponse({'status': 'ok', 'desired_state_version': server.desired_state_version})


@router.post('/hermes/servers/{server_id}/rotate-agent-token')
async def rotate_agent_token(request: Request, server_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    raw_token = f'hsa-{secrets.token_urlsafe(32)}'
    async with async_session() as session:
        server = await _load_owned_server(session, server_id, uid)
        if not server:
            return JSONResponse({'detail': 'سرور یافت نشد'}, status_code=404)
        server.agent_token_hash = _hash_api_key(raw_token)
        server.agent_token_prefix = raw_token[:12]
        server.updated_at = _utcnow()
        await session.commit()

    await _write_audit_log('hermes.server.rotate_agent_token', target_type='hermes_server', target_id=server_id, request=request)
    return JSONResponse({'status': 'ok', 'agent_token': raw_token})


# ══════════════════════════════════════════════════════════════════
# Agent daemon endpoints (token auth, not session cookie)
# ══════════════════════════════════════════════════════════════════

async def _authenticate_agent(request: Request) -> HermesServer | JSONResponse:
    """Resolve the calling server from its `Authorization: Bearer hsa-...`
    token. Returns the HermesServer row, or a ready-to-return 401
    JSONResponse on failure -- callers check the type."""
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    if not token or not token.startswith('hsa-'):
        return JSONResponse({'detail': 'توکن نامعتبر است'}, status_code=401)
    token_hash = _hash_api_key(token)
    async with async_session() as session:
        res = await session.execute(select(HermesServer).where(HermesServer.agent_token_hash == token_hash))
        server = res.scalar_one_or_none()
        if not server or server.status == 'terminated':
            return JSONResponse({'detail': 'توکن نامعتبر است'}, status_code=401)
        return server


@router.get('/hermes/agent/state')
async def agent_state(request: Request) -> JSONResponse:
    server = await _authenticate_agent(request)
    if isinstance(server, JSONResponse):
        return server

    async with async_session() as session:
        skills_res = await session.execute(
            select(HermesServerSkill, HermesSkillCatalog).join(
                HermesSkillCatalog, HermesServerSkill.skill_id == HermesSkillCatalog.id
            ).where(HermesServerSkill.server_id == server.id)
        )
        rows = skills_res.fetchall()

        db_server = await session.get(HermesServer, server.id)
        db_server.last_heartbeat_at = _utcnow()
        agent_version = request.headers.get('X-Agent-Version')
        if agent_version:
            db_server.agent_version = agent_version
        await session.commit()

    skills = [{
        'id': skill_row.skill_id, 'manifest': catalog_row.manifest,
        'options': skill_row.options, 'enabled': skill_row.enabled,
    } for skill_row, catalog_row in rows]

    return JSONResponse(jsonable_encoder({'version': server.desired_state_version, 'skills': skills}))


@router.post('/hermes/agent/report')
async def agent_report(request: Request, payload: AgentReport) -> JSONResponse:
    server = await _authenticate_agent(request)
    if isinstance(server, JSONResponse):
        return server

    async with async_session() as session:
        db_server = await session.get(HermesServer, server.id)
        for item in payload.results:
            row_res = await session.execute(
                select(HermesServerSkill).where(
                    HermesServerSkill.server_id == server.id, HermesServerSkill.skill_id == item.skill_id
                )
            )
            row = row_res.scalar_one_or_none()
            if not row:
                continue
            if item.state == 'removed':
                await session.delete(row)
            else:
                row.state = item.state
                row.error = item.error
                row.updated_at = _utcnow()

        db_server.applied_state_version = payload.version
        db_server.last_heartbeat_at = _utcnow()
        session.add(HermesAgentEvent(
            server_id=server.id, event='report',
            detail={'version': payload.version, 'results': [r.model_dump() for r in payload.results]},
        ))
        await session.commit()

    return JSONResponse({'status': 'ok'})


# ══════════════════════════════════════════════════════════════════
# Admin
# ══════════════════════════════════════════════════════════════════

@router.get('/admin/hermes/orders')
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


@router.post('/admin/hermes/orders/{order_id}/provision')
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


@router.post('/admin/hermes/servers/{server_id}/suspend')
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


@router.post('/admin/hermes/servers/{server_id}/terminate')
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


@router.get('/admin/hermes/offerings')
async def admin_list_offerings(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(select(HermesOffering).order_by(HermesOffering.sort_order))
        rows = [row[0] for row in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/hermes/offerings')
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


@router.get('/admin/hermes/skill-catalog')
async def admin_list_skill_catalog(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(select(HermesSkillCatalog).order_by(HermesSkillCatalog.sort_order))
        rows = [row[0] for row in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/hermes/skill-catalog')
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


# ══════════════════════════════════════════════════════════════════
# Monthly renewal (invoked by app.py's lifespan background loop)
# ══════════════════════════════════════════════════════════════════

async def run_renewal_cycle() -> dict:
    """Charge active servers past `paid_through_at` for another month.

    Idempotent per calendar month via `idempotency_key`; grace period of 7
    days on insufficient balance before suspension. Called on a daily
    schedule from app.py's lifespan (mirrors `_pricing_refresh_loop`).
    """
    if async_session is None:
        return {'charged': 0, 'suspended': 0}

    charged = 0
    suspended = 0
    now = _utcnow()
    async with async_session() as session:
        res = await session.execute(
            select(HermesServer).where(
                HermesServer.status == 'active', HermesServer.paid_through_at <= now,
            )
        )
        servers = [row[0] for row in res.fetchall()]
        repo = SqlBillingRepo(session)

        for server in servers:
            month_key = now.strftime('%Y-%m')
            idem_key = f"hermes-renew:{server.id}:{month_key}"

            existing = await session.execute(
                select(Ledger).where(Ledger.idempotency_key == idem_key)
            )
            if existing.scalar_one_or_none():
                # Already charged this month; just roll the due date forward.
                server.paid_through_at = server.paid_through_at + timedelta(days=30)
                continue

            async with repo.lock_wallet_for_update(server.user_id):
                wallet = await repo.ensure_wallet(server.user_id)
                current_balance = wallet['balance']

                if current_balance < server.monthly_price_irt:
                    grace_deadline = server.paid_through_at + timedelta(days=7)
                    if now >= grace_deadline:
                        server.status = 'suspended'
                        server.updated_at = now
                        session.add(Notification(
                            user_id=server.user_id, type='hermes',
                            title='سرور هرمس شما به دلیل کسری موجودی متوقف شد',
                            body='برای فعال‌سازی مجدد، کیف پول خود را شارژ کنید.',
                        ))
                        suspended += 1
                    else:
                        session.add(Notification(
                            user_id=server.user_id, type='hermes',
                            title='موجودی کیف پول برای تمدید سرور هرمس کافی نیست',
                            body=f'لطفاً تا {grace_deadline.date().isoformat()} کیف پول را شارژ کنید تا سرور متوقف نشود.',
                        ))
                    continue

                new_balance = current_balance - server.monthly_price_irt
                await repo.set_wallet_balance(server.user_id, new_balance)
                session.add(Ledger(
                    user_id=server.user_id, amount=-server.monthly_price_irt, balance_after=new_balance,
                    reason=f'تمدید ماهانه سرور هرمس #{server.id}', idempotency_key=idem_key,
                ))
                server.paid_through_at = server.paid_through_at + timedelta(days=30)
                server.updated_at = now
                charged += 1

        await session.commit()

    return {'charged': charged, 'suspended': suspended}
