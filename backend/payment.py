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

    async with httpx.AsyncClient(timeout=15) as client:
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

    async with httpx.AsyncClient(timeout=15) as client:
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