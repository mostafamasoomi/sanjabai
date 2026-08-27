"""User billing-settings, /me, and checkout endpoints -- split out of
pricing.py purely to stay under the house 500-line cap.

`GET /me/subscription` and `POST /subscription/checkout` were removed
(session 23, migration 0049_retire_plans_subscriptions.sql) along with the
`Plan`/`Subscription` concept -- `credit_packages` is the only product
concept now. `/billing/settings`, `/me/billing`, and
`/credit-package/checkout` are unchanged.

Mounted onto pricing.py's `router` via `router.include_router(...)` in
pricing.py, so app.py's `from pricing import router as pricing_router`
keeps exposing every route below unchanged (same paths, methods, status
codes, response shapes). No test or script imports this module directly
(see reconnaissance: only `pricing.router` is imported externally), so
there is no separate re-export contract to maintain here.
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from database import async_session, BASE_URL
from models import CreditPackage, Payment, UserBillingSetting
from dependencies import _get_user_id
from i18n import err
from payment import create_payment

router = APIRouter()


# ── Pydantic models ─────────────────────────────────────────────

class BillingSettingsUpdate(BaseModel):
    payg_enabled: bool | None = None
    payg_hard_limit: int | None = None
    notify_on_usage_pct: int | None = None


class BillingUpdate(BaseModel):
    payg_enabled: bool | None = None
    payg_hard_limit: int | None = None
    notify_on_usage_pct: int | None = None


class CreditPackageCheckout(BaseModel):
    package_id: str


# ── Billing Settings ────────────────────────────────────────────

@router.get('/billing/settings')
async def get_billing_settings(request: Request) -> JSONResponse:
    """Get user's billing settings (auto-creates defaults if missing)"""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(
            UserBillingSetting.__table__.select().where(UserBillingSetting.user_id == uid)
        )
        row = res.fetchone()
        if not row:
            settings = UserBillingSetting(user_id=uid)
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
            return JSONResponse(jsonable_encoder({
                'user_id': uid, 'payg_enabled': True,
                'payg_hard_limit': None, 'notify_on_usage_pct': 80,
            }))
    return JSONResponse(jsonable_encoder({
        'user_id': row.user_id, 'payg_enabled': row.payg_enabled,
        'payg_hard_limit': row.payg_hard_limit, 'notify_on_usage_pct': row.notify_on_usage_pct,
    }))


@router.put('/billing/settings')
async def update_billing_settings(request: Request, payload: BillingSettingsUpdate) -> JSONResponse:
    """Update user's billing settings"""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    update_data = {'updated_at': now}
    if payload.payg_enabled is not None:
        update_data['payg_enabled'] = payload.payg_enabled
    if payload.payg_hard_limit is not None:
        update_data['payg_hard_limit'] = payload.payg_hard_limit
    if payload.notify_on_usage_pct is not None:
        update_data['notify_on_usage_pct'] = max(1, min(100, payload.notify_on_usage_pct))

    async with async_session() as session:
        res = await session.execute(
            UserBillingSetting.__table__.select().where(UserBillingSetting.user_id == uid)
        )
        existing = res.fetchone()
        if existing:
            await session.execute(
                UserBillingSetting.__table__.update().where(UserBillingSetting.user_id == uid),
                update_data
            )
        else:
            settings = UserBillingSetting(
                user_id=uid,
                payg_enabled=payload.payg_enabled if payload.payg_enabled is not None else True,
                payg_hard_limit=payload.payg_hard_limit,
                notify_on_usage_pct=payload.notify_on_usage_pct if payload.notify_on_usage_pct is not None else 80,
            )
            session.add(settings)
        await session.commit()

    return JSONResponse({'status': 'ok'})


# ── Me endpoints (billing) ───────────────────────────────────────

@router.get('/me/billing')
async def get_my_billing(request: Request) -> JSONResponse:
    """Auth required: return billing settings."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                'SELECT user_id, payg_enabled, payg_hard_limit, notify_on_usage_pct '
                'FROM user_billing_settings WHERE user_id = :uid'
            ),
            {'uid': uid}
        )
        billing = res.fetchone()

    if not billing:
        return JSONResponse({
            'user_id': uid, 'payg_enabled': False,
            'payg_hard_limit': 0, 'notify_on_usage_pct': 80,
        })

    return JSONResponse({
        'user_id': billing.user_id, 'payg_enabled': billing.payg_enabled,
        'payg_hard_limit': billing.payg_hard_limit, 'notify_on_usage_pct': billing.notify_on_usage_pct,
    })


@router.put('/me/billing')
async def update_my_billing(request: Request, payload: BillingUpdate) -> JSONResponse:
    """Auth required: update billing settings."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(
            select(UserBillingSetting).where(UserBillingSetting.user_id == uid)
        )
        billing = res.fetchone()

        if not billing:
            billing = UserBillingSetting(user_id=uid)
            session.add(billing)
            await session.flush()

        if payload.payg_enabled is not None:
            billing.payg_enabled = payload.payg_enabled
        if payload.payg_hard_limit is not None:
            billing.payg_hard_limit = payload.payg_hard_limit
        if payload.notify_on_usage_pct is not None:
            billing.notify_on_usage_pct = payload.notify_on_usage_pct
        billing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()

    return JSONResponse({'status': 'ok'})


# ── Checkout flows ──────────────────────────────────────────────

@router.post('/credit-package/checkout')
async def credit_package_checkout(request: Request, payload: CreditPackageCheckout) -> JSONResponse:
    """Auth required: create ZarinPal payment for a credit package."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        pkg_res = await session.execute(
            select(CreditPackage).where(CreditPackage.id == payload.package_id, CreditPackage.active == True)
        )
        pkg = pkg_res.scalar_one_or_none()
        if not pkg:
            return err('بسته یافت نشد', 'Package not found.', 404)

        # What the user is actually charged via Zarinpal. total_credits (which
        # may be higher, when bonus_percent > 0) is what the wallet gets
        # credited on success -- see payment_endpoints.py::payment_callback,
        # which passes total_credits as handle_payment_callback's
        # credit_amount. Charging total_credits here would mean users pay for
        # their own bonus, making bonus_percent a no-op.
        price = pkg.base_amount
        if price <= 0:
            return JSONResponse({'detail': 'invalid package price'}, status_code=400)

        callback_url = f"{BASE_URL}/api/payment/callback"
        result = await create_payment(
            amount=price,
            description=f"بسته اعتباری {pkg.name_fa} ({pkg.total_credits:,} توکن)",
            callback_url=callback_url,
        )

        if result.get('status') != 'ok':
            return JSONResponse({'detail': result.get('error', 'payment failed')}, status_code=result.get('status', 500))

        payment = Payment(
            user_id=uid, amount=price, authority=result['authority'],
            status='pending', payment_type='credit_package', reference_id=pkg.id,
        )
        session.add(payment)
        await session.commit()

    return JSONResponse({
        'authority': result['authority'], 'url': result['url'],
        'amount': price, 'package': pkg.name_en, 'total_credits': pkg.total_credits,
    })


# ── Usage endpoint ──────────────────────────────────────────────

