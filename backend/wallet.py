"""
Wallet endpoints: balance, ledger, topup.
"""
from __future__ import annotations

from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import async_session
from models import Ledger
from dependencies import _get_user_id

router = APIRouter()


class TopupRequest(BaseModel):
    amount: int
    payment_order_id: str


@router.get('/wallet')
async def get_wallet(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
            {'uid': uid}
        )
        row = res.fetchone()
        balance = row.balance if row else 0
    return JSONResponse({'balance': balance})


@router.get('/wallet/ledger')
async def get_ledger(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    page = int(request.query_params.get('page', 1))
    limit = min(int(request.query_params.get('limit', 20)), 100)
    offset = (page - 1) * limit
    async with async_session() as session:
        count_res = await session.execute(
            sqlalchemy.text('SELECT COUNT(*) as c FROM ledger WHERE user_id = :uid'),
            {'uid': uid}
        )
        total = count_res.fetchone().c
        res = await session.execute(
            Ledger.__table__.select().where(Ledger.user_id == uid).order_by(Ledger.created_at.desc())
            .offset(offset).limit(limit)
        )
        rows = [{'id': r.id, 'amount': r.amount, 'balance_after': r.balance_after, 'reason': r.reason, 'created_at': r.created_at} for r in res.fetchall()]
    return JSONResponse(jsonable_encoder({'items': rows, 'total': total, 'page': page, 'limit': limit}))


@router.post('/wallet/topup')
async def topup(request: Request, payload: TopupRequest) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if payload.amount <= 0:
        return JSONResponse({'detail': 'مبلغ باید مثبت باشد'}, status_code=400)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        pay_res = await session.execute(
            sqlalchemy.text("SELECT id, status, amount FROM payment_orders WHERE id = :pid AND user_id = :uid"),
            {'pid': payload.payment_order_id, 'uid': uid}
        )
        pay_row = pay_res.fetchone()
        if not pay_row:
            return JSONResponse({'detail': 'سفارش پرداخت یافت نشد'}, status_code=404)
        if pay_row.status != 'completed':
            return JSONResponse({'detail': 'پرداخت تکمیل نشده است'}, status_code=400)
        dup = await session.execute(
            sqlalchemy.text("SELECT id FROM ledger WHERE reason = :reason LIMIT 1"),
            {'reason': f'topup:{payload.payment_order_id}'}
        )
        if dup.fetchone():
            return JSONResponse({'detail': 'پرداخت قبلاً ثبت شده است'}, status_code=409)
        res = await session.execute(
            sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
            {'uid': uid}
        )
        row = res.fetchone()
        current = row.balance if row else 0
        new_balance = current + pay_row.amount
        entry = Ledger(user_id=uid, amount=pay_row.amount, balance_after=new_balance, reason=f'topup:{payload.payment_order_id}')
        session.add(entry)
        await session.commit()
    return JSONResponse({'status': 'ok', 'balance_after': new_balance})
