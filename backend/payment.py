"""
Zarinpal payment gateway integration.
Flow: create → redirect user → callback → verify → credit wallet
"""
import os
import httpx
from datetime import datetime, timezone
from pydantic import BaseModel
from fastapi import Request
from fastapi.responses import JSONResponse

from services.billing import credit_wallet
from services.money import Money

ZARINPAL_MERCHANT = os.getenv('ZARINPAL_MERCHANT_ID', '')
ZARINPAL_SANDBOX = os.getenv('ZARINPAL_SANDBOX', 'true').lower() == 'true'
ZARINPAL_API = 'https://sandbox.zarinpal.com/pg/v4/payment' if ZARINPAL_SANDBOX else 'https://api.zarinpal.com/pg/v4/payment'
ZARINPAL_START = 'https://sandbox.zarinpal.com/pg/StartPay' if ZARINPAL_SANDBOX else 'https://www.zarinpal.com/pg/StartPay'


class PaymentRequest(BaseModel):
    amount: int  # in Tomans
    description: str = 'شارژ حساب Multiai'


async def create_payment(amount: int, description: str, callback_url: str, email: str = '', mobile: str = '') -> dict:
    """
    Create a Zarinpal payment request.
    Returns: {authority, url, status} or {error}
    """
    if not ZARINPAL_MERCHANT:
        return {'error': 'payment gateway not configured', 'status': 503}

    payload = {
        'merchant_id': ZARINPAL_MERCHANT,
        'amount': amount,
        'description': description,
        'callback_url': callback_url,
        'metadata': {'email': email, 'mobile': mobile},
    }

    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        try:
            r = await client.post(f'{ZARINPAL_API}/request.json', json=payload)
            data = r.json()
            if data.get('data', {}).get('code') == 100:
                authority = data['data']['authority']
                return {
                    'authority': authority,
                    'url': f'{ZARINPAL_START}/{authority}',
                    'status': 'ok',
                }
            return {'error': f'Zarinpal error: {data.get("errors", "unknown")}', 'status': 400}
        except Exception as e:
            return {'error': f'payment gateway unreachable: {e}', 'status': 502}


async def verify_payment(amount: int, authority: str) -> dict:
    """
    Verify a Zarinpal payment.
    Returns: {ref_id, status} or {error}
    """
    if not ZARINPAL_MERCHANT:
        return {'error': 'payment gateway not configured', 'status': 503}

    payload = {
        'merchant_id': ZARINPAL_MERCHANT,
        'amount': amount,
        'authority': authority,
    }

    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        try:
            r = await client.post(f'{ZARINPAL_API}/verify.json', json=payload)
            data = r.json()
            if data.get('data', {}).get('code') == 100:
                return {
                    'ref_id': data['data']['ref_id'],
                    'status': 'verified',
                }
            return {'error': f'Verification failed: {data.get("errors", "unknown")}', 'status': 400}
        except Exception as e:
            return {'error': f'payment gateway unreachable: {e}', 'status': 502}


class CallbackResult:
    """Structured outcome of :func:`handle_payment_callback`."""

    def __init__(self, *, ok: bool, code: int = 200, detail: str = "",
                 ref_id=None, amount=None):
        self.ok = ok
        self.code = code
        self.detail = detail
        self.ref_id = ref_id
        self.amount = amount

    def to_dict(self) -> dict:
        return {
            "status": "ok" if self.ok else "error",
            "ref_id": self.ref_id,
            "amount": self.amount,
            "detail": self.detail,
        }


async def handle_payment_callback(
    repo,
    *,
    authority: str,
    status: str,
    verify_fn=None,
    expected_amount=None,
) -> CallbackResult:
    """Hardened Zarinpal payment callback.

    Financial-correctness guarantees:

    1. **Order integrity** — the payment row is locked with ``FOR UPDATE`` and
       must currently be ``pending``. If it does not exist or is already
       ``completed``/``failed`` the call is rejected (replay protection).
    2. **Amount / authority verification** — the gateway is asked to verify the
       *exact* ``authority`` and the order's recorded ``amount``. An optional
       ``expected_amount`` lets the caller assert the amount was not tampered
       with between creation and callback.
    3. **Atomic credit** — on success the wallet is credited **and** a ledger
       entry is written in the same transaction, then the order is marked
       ``completed``. A failure marks the order ``failed`` and credits nothing.

    ``repo`` is a :class:`services.billing.BillingRepo` (typically
    :class:`SqlBillingRepo(session)`).
    """
    if status != "OK" or not authority:
        return CallbackResult(ok=False, code=400, detail="payment cancelled or invalid")

    if verify_fn is None:
        verify_fn = verify_payment

    # 1. Lock the order row. Rejects replays (already completed) atomically.
    payment = await repo.lock_pending_payment(authority)
    try:
        if payment is None:
            return CallbackResult(
                ok=False, code=409,
                detail="order not found or already processed (replay rejected)",
            )

        # 2. Amount integrity check (optional but recommended).
        if expected_amount is not None:
            expected = expected_amount.amount if isinstance(expected_amount, Money) else int(expected_amount)
            if payment["amount"] != expected:
                return CallbackResult(
                    ok=False, code=400,
                    detail=f"amount mismatch: order={payment['amount']} expected={expected}",
                )

        # 2b. Authority verification with the gateway.
        verify = await verify_fn(payment["amount"], authority)
        if not verify or verify.get("status") != "verified":
            await repo.mark_payment_failed(payment["id"])
            await repo.commit()
            return CallbackResult(
                ok=False, code=400,
                detail=verify.get("error", "verification failed") if verify else "verification failed",
            )

        # 3. Atomically credit wallet + ledger, then mark completed.
        amount = Money(payment["amount"])
        await credit_wallet(
            repo,
            payment["user_id"],
            amount,
            reason=f"شارژ حساب — Zarinpal ref: {verify['ref_id']}",
            idempotency_key=f"payment-credit:{payment['id']}",
        )
        await repo.mark_payment_completed(payment["id"], ref_id=verify["ref_id"])
        await repo.commit()
        return CallbackResult(ok=True, code=200, ref_id=verify["ref_id"], amount=payment["amount"])
    except Exception as exc:  # pragma: no cover - defensive
        await repo.rollback()
        return CallbackResult(ok=False, code=500, detail=f"internal error: {exc}")
    finally:
        await repo.release_pending_lock(authority)