"""
Pricing and billing endpoints: plans, credit packages, subscriptions,
billing settings, checkout flows.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from database import async_session, BASE_URL
from models import (
    Plan, CreditPackage, Subscription, Payment, Ledger,
    UserBillingSetting,
)
from dependencies import _get_user_id, _write_audit_log

router = APIRouter()

# Re-export for payment.py compatibility
from payment import create_payment  # noqa: E402


# ── Pydantic models ─────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    plan_id: str


class BillingSettingsUpdate(BaseModel):
    payg_enabled: bool | None = None
    payg_hard_limit: int | None = None
    notify_on_usage_pct: int | None = None


class BillingUpdate(BaseModel):
    payg_enabled: bool | None = None
    payg_hard_limit: int | None = None
    notify_on_usage_pct: int | None = None


class SubscriptionCheckout(BaseModel):
    plan_id: str


class CreditPackageCheckout(BaseModel):
    package_id: str


# ── Public endpoints ────────────────────────────────────────────

@router.get('/plans')
async def list_plans() -> JSONResponse:
    """List all active subscription plans + credit packages (public)"""
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        plans_result = await session.execute(
            select(Plan).where(Plan.active == True).order_by(Plan.sort_order)
        )
        plans_objs = plans_result.scalars().all()
        plans_rows = [
            {
                'id': p.id, 'name_fa': p.name_fa, 'name_en': p.name_en,
                'price_monthly': p.price_monthly, 'monthly_token_quota': p.monthly_token_quota,
                'daily_token_limit': p.daily_token_limit, 'models_allowed': p.models_allowed,
                'priority_queue': p.priority_queue, 'features': p.features or [],
            }
            for p in plans_objs
        ]
        pkgs_result = await session.execute(
            select(CreditPackage).where(CreditPackage.active == True).order_by(CreditPackage.sort_order)
        )
        pkgs_objs = pkgs_result.scalars().all()
        pkgs_rows = [
            {
                'id': p.id, 'name_fa': p.name_fa, 'name_en': p.name_en,
                'base_amount': p.base_amount, 'bonus_percent': p.bonus_percent,
                'total_credits': p.total_credits,
            }
            for p in pkgs_objs
        ]
    return JSONResponse({'plans': plans_rows, 'credit_packages': pkgs_rows})


@router.get('/plans/{plan_id}')
async def get_plan(plan_id: str) -> JSONResponse:
    """Get a single plan by ID (public)"""
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM plans WHERE id = :pid AND active = true'),
            {'pid': plan_id}
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'طرح یافت نشد'}, status_code=404)
    return JSONResponse(jsonable_encoder(dict(row._mapping)))


@router.get('/credit-packages')
async def list_credit_packages() -> JSONResponse:
    """List all active credit packages (public)"""
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM credit_packages WHERE active = true ORDER BY sort_order')
        )
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.get('/credit-packages/{pkg_id}')
async def get_credit_package(pkg_id: str) -> JSONResponse:
    """Get a single credit package by ID (public)"""
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM credit_packages WHERE id = :pid AND active = true'),
            {'pid': pkg_id}
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'بسته یافت نشد'}, status_code=404)
    return JSONResponse(jsonable_encoder(dict(row._mapping)))


# ── Subscription management ─────────────────────────────────────

@router.post('/subscribe')
async def subscribe_to_plan(request: Request, payload: SubscribeRequest) -> JSONResponse:
    """Subscribe the current user to a plan."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        plan_res = await session.execute(
            sqlalchemy.text('SELECT * FROM plans WHERE id = :pid AND active = true'),
            {'pid': payload.plan_id}
        )
        plan = plan_res.fetchone()
        if not plan:
            return JSONResponse({'detail': 'طرح یافت نشد'}, status_code=404)

        plan_data = dict(plan._mapping)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        await session.execute(
            sqlalchemy.text(
                "UPDATE subscriptions SET status = 'cancelled', cancelled_at = :now, updated_at = :now "
                "WHERE user_id = :uid AND status = 'active'"
            ),
            {'uid': uid, 'now': now}
        )

        ends_at = now + timedelta(days=30)
        sub = Subscription(
            user_id=uid, plan=payload.plan_id, starts_at=now, ends_at=ends_at,
            status='active', monthly_token_quota=plan_data['monthly_token_quota'],
            tokens_used_this_period=0, auto_renew=True,
            price_paid=plan_data['price_monthly'],
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)

        if plan_data['price_monthly'] > 0:
            await _write_audit_log('subscribe', target_type='subscription', target_id=sub.id,
                                   details={'plan': payload.plan_id, 'price': plan_data['price_monthly']})

    return JSONResponse({
        'status': 'ok',
        'subscription': {
            'id': sub.id, 'plan': payload.plan_id,
            'price_monthly': plan_data['price_monthly'],
            'monthly_token_quota': plan_data['monthly_token_quota'],
            'daily_token_limit': plan_data['daily_token_limit'],
            'starts_at': sub.starts_at.isoformat() if sub.starts_at else None,
            'ends_at': sub.ends_at.isoformat() if sub.ends_at else None,
            'status': sub.status,
        }
    })


@router.get('/subscription')
async def get_subscription(request: Request) -> JSONResponse:
    """Get the user's current active subscription"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                "SELECT * FROM subscriptions WHERE user_id = :uid AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {'uid': uid}
        )
        sub = res.fetchone()
        if not sub:
            return JSONResponse({'subscription': None, 'plan': None})
        sub_data = dict(sub._mapping)
        plan_res = await session.execute(
            sqlalchemy.text('SELECT * FROM plans WHERE id = :pid'),
            {'pid': sub_data['plan']}
        )
        plan_row = plan_res.fetchone()
        plan_data = dict(plan_row._mapping) if plan_row else None

    return JSONResponse(jsonable_encoder({'subscription': sub_data, 'plan': plan_data}))


@router.post('/subscription/cancel')
async def cancel_subscription(request: Request) -> JSONResponse:
    """Cancel the user's active subscription"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                "UPDATE subscriptions SET status = 'cancelled', cancelled_at = :now, auto_renew = false, updated_at = :now "
                "WHERE user_id = :uid AND status = 'active' RETURNING id, plan"
            ),
            {'uid': uid, 'now': now}
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'no active subscription'}, status_code=404)
        await session.commit()

    await _write_audit_log('subscription.cancel', target_type='subscription', target_id=row.id,
                           details={'plan': row.plan})
    return JSONResponse({'status': 'cancelled', 'subscription_id': row.id})


@router.post('/subscription/renew')
async def renew_subscription(request: Request) -> JSONResponse:
    """Renew the user's subscription (extend by 30 days, reset token usage)"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                "SELECT * FROM subscriptions WHERE user_id = :uid AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {'uid': uid}
        )
        sub = res.fetchone()
        if not sub:
            return JSONResponse({'detail': 'no active subscription'}, status_code=404)

        sub_data = dict(sub._mapping)
        new_ends_at = now + timedelta(days=30)

        plan_res = await session.execute(
            sqlalchemy.text('SELECT monthly_token_quota FROM plans WHERE id = :pid'),
            {'pid': sub_data['plan']}
        )
        plan = plan_res.fetchone()
        quota = plan.monthly_token_quota if plan else 0

        await session.execute(
            sqlalchemy.text(
                "UPDATE subscriptions SET ends_at = :ends, tokens_used_this_period = 0, "
                "monthly_token_quota = :quota, updated_at = :now WHERE id = :sid"
            ),
            {'ends': new_ends_at, 'quota': quota, 'now': now, 'sid': sub_data['id']}
        )
        await session.commit()

    return JSONResponse({'status': 'renewed', 'ends_at': new_ends_at.isoformat()})


# ── Billing Settings ────────────────────────────────────────────

@router.get('/billing/settings')
async def get_billing_settings(request: Request) -> JSONResponse:
    """Get user's billing settings (auto-creates defaults if missing)"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

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


# ── Me endpoints (subscription/billing) ─────────────────────────

@router.get('/me/subscription')
async def get_my_subscription(request: Request) -> JSONResponse:
    """Auth required: return current subscription, PAYG status, and usage summary."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        sub_res = await session.execute(
            select(Subscription).where(
                Subscription.user_id == uid, Subscription.status == 'active',
            ).order_by(Subscription.created_at.desc())
        )
        sub = sub_res.fetchone()

        billing_res = await session.execute(
            select(UserBillingSetting).where(UserBillingSetting.user_id == uid)
        )
        billing = billing_res.fetchone()

        usage_tokens = 0
        usage_events_count = 0
        if sub:
            usage_tokens = getattr(sub, 'tokens_used_this_period', 0) or 0
        month_start = datetime.now(timezone.utc).replace(tzinfo=None).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count_res = await session.execute(
            sqlalchemy.text(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens "
                "FROM usage_events WHERE user_id=:uid AND created_at >= :month_start"
            ),
            {'uid': uid, 'month_start': month_start}
        )
        count_row = count_res.fetchone()
        if count_row:
            usage_events_count = count_row.cnt
            usage_tokens = count_row.total_tokens

    sub_data = None
    if sub:
        sub_data = {
            'id': sub.id, 'plan': getattr(sub, 'plan', ''),
            'plan_id': getattr(sub, 'plan_id', None), 'status': sub.status,
            'monthly_token_quota': getattr(sub, 'monthly_token_quota', 0),
            'tokens_used_this_period': usage_tokens,
            'auto_renew': getattr(sub, 'auto_renew', True),
            'starts_at': sub.starts_at.isoformat() if sub.starts_at else None,
            'ends_at': sub.ends_at.isoformat() if sub.ends_at else None,
            'price_paid': getattr(sub, 'price_paid', 0),
        }

    return JSONResponse({
        'subscription': sub_data,
        'payg_enabled': getattr(billing, 'payg_enabled', False) if billing else False,
        'payg_hard_limit': getattr(billing, 'payg_hard_limit', 0) if billing else 0,
        'usage': {'tokens_this_period': usage_tokens, 'events_this_month': usage_events_count},
    })


@router.get('/me/billing')
async def get_my_billing(request: Request) -> JSONResponse:
    """Auth required: return billing settings."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

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

@router.post('/subscription/checkout')
async def subscription_checkout(request: Request, payload: SubscriptionCheckout) -> JSONResponse:
    """Auth required: create ZarinPal payment for a subscription plan."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        plan_res = await session.execute(select(Plan).where(Plan.id == payload.plan_id, Plan.active == True))
        plan = plan_res.scalar_one_or_none()
        if not plan:
            return JSONResponse({'detail': 'طرح یافت نشد'}, status_code=404)
        if plan.price_monthly <= 0:
            return JSONResponse({'detail': 'این طرح رایگان است، نیازی به پرداخت نیست'}, status_code=400)

        callback_url = f"{BASE_URL}/api/payment/callback"
        result = await create_payment(
            amount=plan.price_monthly,
            description=f"اشتراک {plan.name_fa} - ماهانه",
            callback_url=callback_url,
        )

        if result.get('status') != 'ok':
            return JSONResponse({'detail': result.get('error', 'payment failed')}, status_code=result.get('status', 500))

        payment = Payment(
            user_id=uid, amount=plan.price_monthly, authority=result['authority'],
            status='pending', payment_type='subscription', reference_id=str(plan.id),
        )
        session.add(payment)
        await session.commit()

    return JSONResponse({
        'authority': result['authority'], 'url': result['url'],
        'amount': plan.price_monthly, 'plan': plan.name_en, 'plan_fa': plan.name_fa,
    })


@router.post('/credit-package/checkout')
async def credit_package_checkout(request: Request, payload: CreditPackageCheckout) -> JSONResponse:
    """Auth required: create ZarinPal payment for a credit package."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        pkg_res = await session.execute(
            select(CreditPackage).where(CreditPackage.id == payload.package_id, CreditPackage.active == True)
        )
        pkg = pkg_res.scalar_one_or_none()
        if not pkg:
            return JSONResponse({'detail': 'بسته یافت نشد'}, status_code=404)

        price = pkg.total_credits
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
            status='pending', payment_type='credit_package', reference_id=str(pkg.id),
        )
        session.add(payment)
        await session.commit()

    return JSONResponse({
        'authority': result['authority'], 'url': result['url'],
        'amount': price, 'package': pkg.name_en, 'total_credits': pkg.total_credits,
    })
