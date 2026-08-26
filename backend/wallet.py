"""
Wallet endpoints: balance, ledger, free-tier throttle status.
"""
from __future__ import annotations

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session
from models import Ledger
from dependencies import _get_user_id
from services.free_tier import get_status as _free_tier_status
from i18n import err

router = APIRouter()


@router.get('/wallet')
async def get_wallet(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
            {'uid': uid}
        )
        row = res.fetchone()
        balance = int(row.balance) if row and row.balance is not None else 0
    return JSONResponse({'balance': balance})


@router.get('/wallet/ledger')
async def get_ledger(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
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


@router.get('/free-tier/status')
async def free_tier_status(request: Request) -> JSONResponse:
    """Per-model free-tier throttle snapshot (reached by the browser as
    /api/free-tier/status). See services/free_tier.py for the throttle
    rules; this endpoint is read-only and never consumes budget."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    status = await _free_tier_status(uid)
    return JSONResponse(status)
