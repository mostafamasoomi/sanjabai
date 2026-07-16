"""
Payment gateway endpoints: /payment/request, /payment/callback, /payment/history.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select

from database import async_session, BASE_URL
from models import Payment, Ledger, Plan, CreditPackage, Subscription
from dependencies import _get_user_id, _write_audit_log
from payment import create_payment, verify_payment, PaymentRequest, handle_payment_callback, CallbackResult
from services.billing import SqlBillingRepo

router = APIRouter()


@router.post('/payment/request')
async def payment_request(request: Request, payload: PaymentRequest) -> JSONResponse:
    """Create a Zarinpal payment and return redirect URL"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if payload.amount < 1000:
        return JSONResponse({'detail': 'حداقل مبلغ ۱۰۰۰ تومان است'}, status_code=400)

    callback_url = f"{BASE_URL}/api/payment/callback"

    result = await create_payment(
        amount=payload.amount,
        description=payload.description,
        callback_url=callback_url,
    )

    if result.get('status') != 'ok':
        return JSONResponse({'detail': result.get('error', 'payment failed')}, status_code=result.get('status', 500))

    if async_session is not None:
        async with async_session() as session:
            payment = Payment(
                user_id=uid, amount=payload.amount,
                authority=result['authority'], status='pending',
            )
            session.add(payment)
            await session.commit()

    return JSONResponse({
        'authority': result['authority'], 'url': result['url'], 'amount': payload.amount,
    })


@router.get('/payment/callback')
async def payment_callback(request: Request) -> JSONResponse:
    """Zarinpal redirects here after payment."""
    authority = request.query_params.get('Authority')
    status = request.query_params.get('Status', '')

    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    payment_type = 'wallet_topup'
    reference_id = None
    pay_row = None
    authority_str = authority or ''
    async with async_session() as session:
        pay_res = await session.execute(
            select(Payment).where(Payment.authority == authority_str)
        )
        pay_row = pay_res.fetchone()
        p = pay_row[0] if pay_row else None
        if p:
            payment_type = getattr(p, 'payment_type', 'wallet_topup') or 'wallet_topup'
            reference_id = getattr(p, 'reference_id', None)

    async with async_session() as session:
        repo = SqlBillingRepo(session)
        result = await handle_payment_callback(repo, authority=authority or "", status=status)

    if not result.ok:
        fail_redirect = {
            'subscription': f'{BASE_URL}/plans?payment=failed',
            'credit_package': f'{BASE_URL}/credits?payment=failed',
        }.get(payment_type, f'{BASE_URL}/wallet?payment=failed')
        return JSONResponse({'detail': result.detail, 'redirect': fail_redirect}, status_code=result.code)

    redirect_path = '/wallet?payment=success'
    extra_data = {}

    if payment_type == 'subscription' and reference_id:
        uid = p.user_id if pay_row else 0
        async with async_session() as session:
            plan_res = await session.execute(select(Plan).where(Plan.id == int(reference_id)))
            plan_row = plan_res.fetchone()
            plan = plan_row[0] if plan_row else None
            if plan:
                await session.execute(
                    sqlalchemy.text(
                        "UPDATE subscriptions SET status='cancelled', cancelled_at=now(), updated_at=now() "
                        "WHERE user_id=:uid AND status='active'"
                    ),
                    {'uid': uid}
                )
                new_sub = Subscription(
                    user_id=uid,
                    plan=plan.name_en.lower() if hasattr(plan, 'name_en') else str(plan.id),
                    plan_id=plan.id,
                    status='active',
                    monthly_token_quota=plan.monthly_token_quota,
                    tokens_used_this_period=0,
                    auto_renew=True,
                    price_paid=result.amount or 0,
                    starts_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    ends_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
                )
                session.add(new_sub)
                await session.commit()
                extra_data['subscription'] = plan.name_en
        redirect_path = '/dashboard?subscription=active'

    elif payment_type == 'credit_package' and reference_id:
        uid = p.user_id if pay_row else 0
        async with async_session() as session:
            pkg_res = await session.execute(select(CreditPackage).where(CreditPackage.id == int(reference_id)))
            pkg = pkg_res.fetchone()
            if pkg:
                credit_amount = pkg.total_credits
                bal_res = await session.execute(
                    sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
                    {'uid': uid}
                )
                bal_row = bal_res.fetchone()
                current_balance = bal_row.balance if bal_row else 0
                new_balance = current_balance + credit_amount
                entry = Ledger(
                    user_id=uid, amount=credit_amount, balance_after=new_balance,
                    reason=f"بسته اعتباری: {pkg.name_fa} ({pkg.base_amount:,} + {pkg.bonus_percent}% پاداش)",
                    idempotency_key=f"credit-pkg:{reference_id}:{result.ref_id}",
                )
                session.add(entry)
                await session.commit()
                extra_data['credits_added'] = credit_amount
                extra_data['package'] = pkg.name_fa
        redirect_path = '/wallet?payment=success'

    return JSONResponse({
        'status': 'ok', 'ref_id': result.ref_id, 'amount': result.amount,
        'redirect': f'{BASE_URL}{redirect_path}', **extra_data,
    })


@router.get('/payment/history')
async def payment_history(request: Request) -> JSONResponse:
    """Get user's payment history"""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            Payment.__table__.select()
            .where(Payment.user_id == uid)
            .order_by(Payment.created_at.desc())
            .limit(50)
        )
        rows = [
            {
                'id': r.id, 'amount': r.amount, 'authority': r.authority,
                'ref_id': r.ref_id, 'status': r.status,
                'created_at': r.created_at.isoformat() if r.created_at else None,
                'verified_at': r.verified_at.isoformat() if r.verified_at else None,
            }
            for r in res.fetchall()
        ]
    return JSONResponse(jsonable_encoder(rows))
