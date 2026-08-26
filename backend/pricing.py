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

from database import async_session
from models import (
    Plan, CreditPackage, Subscription, Ledger,
)
from dependencies import _get_user_id, _write_audit_log
from i18n import err

router = APIRouter()

# Billing-settings / /me / checkout endpoints were split out to
# pricing_billing.py purely to stay under the house 500-line cap (pure
# move, no behaviour change -- see that module's docstring). Mounted here
# so `router` (the object app.py's `from pricing import router as
# pricing_router` imports) keeps exposing every route unchanged.
from pricing_billing import router as _billing_router  # noqa: E402
router.include_router(_billing_router)


# ── Pydantic models ─────────────────────────────────────────────

class SubscribeRequest(BaseModel):
    plan_id: str


# ── Public endpoints ────────────────────────────────────────────

@router.get('/plans')
async def list_plans() -> JSONResponse:
    """List all active subscription plans + credit packages (public)"""
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
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
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM plans WHERE id = :pid AND active = true'),
            {'pid': plan_id}
        )
        row = res.fetchone()
        if not row:
            return err('طرح یافت نشد', 'Plan not found.', 404)
    return JSONResponse(jsonable_encoder(dict(row._mapping)))


@router.get('/credit-packages')
async def list_credit_packages() -> JSONResponse:
    """List all active credit packages (public)"""
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
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
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM credit_packages WHERE id = :pid AND active = true'),
            {'pid': pkg_id}
        )
        row = res.fetchone()
        if not row:
            return err('بسته یافت نشد', 'Package not found.', 404)
    return JSONResponse(jsonable_encoder(dict(row._mapping)))


# ── Subscription management ─────────────────────────────────────

@router.post('/subscribe')
async def subscribe_to_plan(request: Request, payload: SubscribeRequest) -> JSONResponse:
    """Subscribe the current user to a plan."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    async with async_session() as session:
        plan_res = await session.execute(
            sqlalchemy.text('SELECT * FROM plans WHERE id = :pid AND active = true'),
            {'pid': payload.plan_id}
        )
        plan = plan_res.fetchone()
        if not plan:
            return err('طرح یافت نشد', 'Plan not found.', 404)

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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

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


# ── Usage endpoint ──────────────────────────────────────────────

