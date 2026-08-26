"""
Payment gateway endpoints: /payment/request, /payment/callback, /payment/history.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select

from database import async_session, BASE_URL
from models import Payment, Plan, CreditPackage, Subscription, HermesOrder, HermesOffering
from dependencies import _get_user_id, _write_audit_log
from payment import create_payment, verify_payment, PaymentRequest, handle_payment_callback, CallbackResult
from services.billing import SqlBillingRepo
from services.money import Money
from i18n import bi, err

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/payment/request')
async def payment_request(request: Request, payload: PaymentRequest) -> JSONResponse:
    """Create a Zarinpal payment and return redirect URL"""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if payload.amount < 1000:
        return err('حداقل مبلغ ۱۰۰۰ تومان است', 'Minimum amount is 1,000 tomans.', 400)

    callback_url = f"{BASE_URL}/api/payment/callback"

    result = await create_payment(
        amount=payload.amount,
        description=payload.description,
        callback_url=callback_url,
    )

    if result.get('status') != 'ok':
        # NOT CONVERTED -- `detail` here is result.get('error', ...), a
        # variable sourced from the gateway adapter (create_payment) with no
        # Persian sibling visible at this definition site. See handoff report.
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
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

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

    # For a credit package the wallet must be credited total_credits (which
    # may include a bonus above what Zarinpal actually charged/verified,
    # i.e. base_amount) -- resolve that *before* the callback so it can be
    # passed straight into handle_payment_callback's single atomic credit.
    # Previously this was done with a second, separate Ledger insert after
    # the callback, which double-credited the wallet's ledger history
    # without touching Wallet.balance (desyncing the two) and always
    # credited total_credits regardless of what was actually charged,
    # making the bonus_percent field ineffective. reference_id is a
    # CreditPackage.id, which is a string primary key -- not int().
    credit_pkg = None
    if payment_type == 'credit_package' and reference_id:
        async with async_session() as session:
            pkg_res = await session.execute(select(CreditPackage).where(CreditPackage.id == reference_id))
            pkg_row = pkg_res.fetchone()
            credit_pkg = pkg_row[0] if pkg_row else None

    # A Hermes server purchase is not a wallet top-up -- the wallet must not
    # be credited the amount charged (that's handle_payment_callback's
    # default). Only the offering's included_credit, if any, should land as
    # spendable balance, so credit_amount is forced to that (or zero) via
    # the same sanctioned path credit_package uses -- never a second,
    # separate Ledger write (see handle_payment_callback's docstring for why).
    hermes_order = None
    hermes_offering = None
    if payment_type == 'hermes_order' and reference_id:
        async with async_session() as session:
            order_res = await session.execute(select(HermesOrder).where(HermesOrder.id == int(reference_id)))
            hermes_order = order_res.scalar_one_or_none()
            if hermes_order is not None:
                off_res = await session.execute(select(HermesOffering).where(HermesOffering.id == hermes_order.offering_id))
                hermes_offering = off_res.scalar_one_or_none()

    callback_kwargs: dict[str, Any] = {}
    if credit_pkg is not None:
        callback_kwargs['credit_amount'] = Money(credit_pkg.total_credits)
        callback_kwargs['credit_reason'] = (
            f"بسته اعتباری: {credit_pkg.name_fa} "
            f"({credit_pkg.base_amount:,} + {credit_pkg.bonus_percent}% پاداش)"
        )
    elif hermes_order is not None:
        included_credit = hermes_offering.included_credit if hermes_offering else 0
        callback_kwargs['credit_amount'] = Money(included_credit)
        callback_kwargs['credit_reason'] = f'اعتبار همراه سرور هرمس #{hermes_order.id}' if included_credit > 0 else f'خرید سرور هرمس #{hermes_order.id}'

    async with async_session() as session:
        repo = SqlBillingRepo(session)
        result = await handle_payment_callback(repo, authority=authority or "", status=status, **callback_kwargs)

    if not result.ok:
        # Targets must be pages that actually exist in the frontend.
        # frontend/app/plans and frontend/app/credits were never built --
        # `/plans` and `/credits` 404 -- so a failed payment used to strand
        # the user on a dead page with no explanation. Subscription status
        # lives on /dashboard (see the matching success redirect below,
        # `/dashboard?subscription=active`) and credit packages are sold
        # from /wallet (see the matching success redirect,
        # `/wallet?payment=success`) -- point the failure path at the same
        # pages the success path already uses. hermes_order already pointed
        # at the real order form (/hermes/order, 200) and is unchanged.
        fail_redirect = {
            'subscription': f'{BASE_URL}/dashboard?payment=failed',
            'credit_package': f'{BASE_URL}/wallet?payment=failed',
            'hermes_order': f'{BASE_URL}/hermes/order?payment=failed',
        }.get(payment_type, f'{BASE_URL}/wallet?payment=failed')
        # result.detail/result.detail_en (payment.CallbackResult) are already
        # bilingual; bi() is used instead of err() because this response also
        # carries a 'redirect' key that err() doesn't support.
        return JSONResponse(
            bi({'redirect': fail_redirect}, detail=(result.detail, result.detail_en)),
            status_code=result.code,
        )

    redirect_path = '/wallet?payment=success'
    extra_data = {}

    if payment_type == 'subscription' and reference_id:
        uid = p.user_id if pay_row else 0
        async with async_session() as session:
            # Plan.id is a string primary key (admin-chosen, e.g. "pro"),
            # not numeric -- int(reference_id) raised ValueError for any
            # non-numeric plan id, crashing this branch after the user had
            # already been charged. See the identical bug fixed for
            # CreditPackage.id above.
            plan_res = await session.execute(select(Plan).where(Plan.id == reference_id))
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

    elif payment_type == 'credit_package' and credit_pkg is not None:
        # Wallet was already credited total_credits atomically inside
        # handle_payment_callback above (via credit_amount=); nothing left
        # to do here but report what happened.
        extra_data['credits_added'] = credit_pkg.total_credits
        extra_data['package'] = credit_pkg.name_fa
        redirect_path = '/wallet?payment=success'

        # Package quota entitlement (services/entitlements.py), a clean
        # no-op for the vast majority of packages that have none configured.
        # Non-fatal by construction: the user already paid and the wallet
        # was already credited above, so a quota-row failure here must never
        # fail this callback or change the redirect -- grant_for_payment()
        # itself never raises (see services/entitlement_gate.py), and this
        # try/except is defence in depth against that contract. authority_str
        # is this payment's stable identity across a replayed Zarinpal
        # callback (same Authority query param both times); it is what
        # grant_entitlement()'s (package_id, source_payment_id) unique index
        # dedupes on, so a replay grants the quota at most once.
        try:
            from services.entitlement_gate import grant_for_payment
            _grant_uid = p.user_id if pay_row else 0
            entitlement = await grant_for_payment(_grant_uid, credit_pkg.id, authority_str)
            if entitlement is not None:
                extra_data['entitlement'] = {
                    'requests_remaining': entitlement.get('requests_remaining'),
                    'tokens_remaining': entitlement.get('tokens_remaining'),
                    'expires_at': entitlement['expires_at'].isoformat() if entitlement.get('expires_at') else None,
                }
        except Exception as e:
            logger.error(
                f"payment_callback: entitlement grant threw uid={p.user_id if pay_row else 0} "
                f"package={credit_pkg.id} authority={authority_str}: {e}"
            )

    elif payment_type == 'hermes_order' and hermes_order is not None:
        # The wallet effect (crediting only included_credit, never the full
        # amount charged) already happened atomically inside
        # handle_payment_callback above. This just flips the order to 'paid'
        # so it shows up in the admin delivery queue.
        # replay-safe: handle_payment_callback's payment-row lock already
        # rejected a duplicate callback before we get here, but re-check
        # since this branch reads the order row separately.
        if hermes_order.status == 'pending_payment':
            async with async_session() as session:
                order_res = await session.execute(select(HermesOrder).where(HermesOrder.id == hermes_order.id))
                order = order_res.scalar_one_or_none()
                if order and order.status == 'pending_payment':
                    order.status = 'paid'
                    order.paid_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    order.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    await session.commit()
        if hermes_offering and hermes_offering.included_credit > 0:
            extra_data['included_credit'] = hermes_offering.included_credit
        extra_data['order_id'] = hermes_order.id
        # frontend/app/hermes/orders/[id] does not exist -- only the list
        # page frontend/app/hermes/orders/page.tsx does (verified: any
        # per-order URL like /hermes/orders/1 404s on production even
        # though the list page itself is 200). This was silently sending
        # every successful Hermes order purchase to a 404. order_id is
        # still returned in the JSON body above for any caller that wants
        # it; the redirect just has to land on a page that exists.
        redirect_path = '/hermes/orders?payment=success'

    return JSONResponse({
        'status': 'ok', 'ref_id': result.ref_id, 'amount': result.amount,
        'redirect': f'{BASE_URL}{redirect_path}', **extra_data,
    })


@router.get('/payment/history')
async def payment_history(request: Request) -> JSONResponse:
    """Get user's payment history"""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

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
