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

SPLIT ACROSS FILES -- this module crossed the house 500-line cap, so it was
split along its documented route groups (following the chat.py /
chat_web.py / chat_search.py precedent):
  hermes.py          (this file) -- catalog + orders, pricing math, and the
                      shared `router` object every other hermes_*.py module
                      registers its routes on.
  hermes_servers.py  -- /hermes/servers/* and /hermes/agent/* (server fleet
                      management + the agent daemon endpoints).
  hermes_admin.py    -- /admin/hermes/* (delivery queue + catalog CRUD).
  hermes_renewal.py  -- run_renewal_cycle (monthly billing cron, invoked by
                      app.py's lifespan background loop).
Nothing changed in the move: every route path, method, status code,
response shape, Persian string and transaction boundary is byte-identical
to before the split.

MONKEYPATCH CONTRACT -- tests/test_hermes.py does
`patch('hermes._get_cached_eur_to_irt', ...)` and calls
`hermes._price_offering(...)` / `hermes._offering_public(...)` /
`hermes._validate_skill_options(...)` / `hermes._round_up_1000(...)`
directly on this module. All four stay defined in *this* file (not moved)
for exactly that reason: Python resolves a bare global name against the
*defining* module's namespace, not the importing one, so if `_price_offering`
moved elsewhere, patching `hermes._get_cached_eur_to_irt` would no longer
reach the call inside it. hermes_servers.py imports `_validate_skill_options`
from here as a plain import (safe -- nothing patches that particular name),
not a case needing the late-binding `hermes.<name>` pattern.

IMPORT CONTRACT for the split files -- hermes_servers.py and hermes_admin.py
do `import hermes` and register their routes with `@hermes.router.get(...)`
etc directly on this module's `router` object (see the imports at the
bottom of this file, which happen after `router = APIRouter()` so the
attribute already exists by the time those modules' decorators run). This
mirrors chat_web.py's `@chat.router.post(...)` pattern against chat.py.
Every name that used to live directly in this file is re-exported at the
bottom so `from hermes import X` / `hermes.X` keeps working unchanged for
any external consumer (app.py, tests, scripts).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from database import async_session, BASE_URL
from models import HermesOffering, HermesSkillCatalog, HermesOrder, Payment
from dependencies import _get_user_id
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
# Split modules -- imported for their route-registration side effect
# (each decorates onto `router` above), and re-exported here so
# `from hermes import X` / `hermes.X` keeps working unchanged for any
# external consumer. Import order matters only in that `router` must
# already be defined, which it is (see top of file).
# ══════════════════════════════════════════════════════════════════

from hermes_servers import (  # noqa: F401,E402
    SkillAttach, SkillUpdate, AgentReportItem, AgentReport,
    _load_owned_server, list_servers, _server_public, get_server,
    attach_skill, update_skill, remove_skill, rotate_agent_token,
    _authenticate_agent, agent_state, agent_report,
)
from hermes_admin import (  # noqa: F401,E402
    ProvisionRequest, OfferingUpsert, SkillCatalogUpsert,
    admin_list_orders, admin_provision_order, admin_suspend_server,
    admin_terminate_server, admin_list_offerings, admin_upsert_offering,
    admin_list_skill_catalog, admin_upsert_skill_catalog,
)
from hermes_renewal import run_renewal_cycle  # noqa: F401,E402
