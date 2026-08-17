"""
Usage tracking and wallet/quota charging for chat.

Pulled out of chat.py (which was well past the project's 500-line ceiling).
Holds the shared billing helpers used by the /v1/chat/completions, /v1/chat/
with-file, /v1/compare and /v1/smart-chat endpoints and their streaming
paths:

  _record_usage        – append ledger + charge Wallet.balance after a call
  _track_usage         – non-streaming variant (wraps _record_usage)
  _bill_stream_usage   – streaming variant (wraps _record_usage)
  _release_reservation – release a BillingService reservation, fire-and-forget
  _check_quota_pre     – legacy quota/balance pre-flight fallback

``chat._record_usage`` is re-exported from the chat aggregator: the wallet
regression tests (tests/test_wallet_balance_charge.py) call it directly with
a fake session.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models import Quota, Ledger
from dependencies import _get_user_id
from services.billing import SqlBillingRepo, BillingService

logger = logging.getLogger(__name__)


async def _release_reservation(reservation: dict | None, uid: int, label: str = '') -> None:
    """Release a billing reservation; fire-and-forget, logs on failure."""
    if not reservation or async_session is None:
        return
    try:
        async with async_session() as s:
            _rel_repo = SqlBillingRepo(s)
            _rel_svc = BillingService(_rel_repo)
            await _rel_svc.release(reservation['reservation_id'])
            await s.commit()
    except Exception as e:
        logger.warning(f"release_reservation failed uid={uid} {label}: {e}")


async def _check_quota_pre(uid: int) -> JSONResponse | None:
    """Pre-flight quota and balance check before calling LiteLLM."""
    if async_session is None:
        return None
    try:
        async with async_session() as session:
            res = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
            quota = res.fetchone()
            if quota:
                limit = quota.daily_limit
                used = quota.used_today
                reset_at = quota.reset_at
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if reset_at and now >= reset_at:
                    await session.execute(
                        Quota.__table__.update().where(Quota.user_id == uid),
                        {'used_today': 0, 'updated_at': now},
                    )
                    await session.commit()
                    used = 0
                if limit > 0 and used >= limit:
                    return JSONResponse(
                        {'error': {'message': 'daily token quota exceeded', 'type': 'quota_exceeded', 'code': 'daily_limit'}},
                        status_code=429,
                    )
            res = await session.execute(
                sqlalchemy.text('SELECT balance FROM wallet WHERE user_id = :uid'),
                {'uid': uid},
            )
            row = res.fetchone()
            balance = row.balance if row else 0
            if balance <= 0:
                return JSONResponse(
                    {'error': {'message': 'insufficient wallet balance | موجودی کیف پول کافی نیست', 'type': 'quota_exceeded', 'code': 'balance'}},
                    status_code=429,
                )
    except Exception as e:
        logger.warning(f"_check_quota_pre failed uid={uid}: {e}")
    return None


async def _record_usage(session: AsyncSession, uid: int, payload: dict[str, Any], usage: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]:
    """Shared billing logic for tracking and billing usage. Returns cost info dict."""
    result = {'input_tokens': 0, 'output_tokens': 0, 'cost': 0, 'balance_after': 0}
    total_tokens = usage.get('total_tokens', 0)
    if total_tokens <= 0:
        return result
    model = payload.get('model', '')
    input_tokens = int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0)
    output_tokens = int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)

    result['input_tokens'] = input_tokens
    result['output_tokens'] = output_tokens

    res = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
    quota = res.fetchone()
    if quota:
        await session.execute(
            Quota.__table__.update().where(Quota.user_id == uid),
            {'used_today': quota.used_today + total_tokens, 'updated_at': datetime.now(timezone.utc).replace(tzinfo=None)},
        )

    price_row = None
    try:
        price_res = await session.execute(
            sqlalchemy.text(
                'SELECT input_per_million, output_per_million FROM model_catalog '
                'WHERE provider_model_id = :mid AND availability = :avail LIMIT 1'
            ),
            {'mid': model, 'avail': 'available'},
        )
        price_row = price_res.fetchone()
    except Exception as e:
        logger.warning(f"_record_usage price lookup failed model={model} uid={uid}: {e}")

    if price_row:
        inp_rate = int(price_row.input_per_million or 0)
        out_rate = int(price_row.output_per_million or 0)
        cost = max(1, int((input_tokens * inp_rate + output_tokens * out_rate + 500_000) // 1_000_000))
    else:
        # Fallback to pricing table or any availability model_catalog entry if exact available entry missed
        try:
            fallback_res = await session.execute(
                sqlalchemy.text('SELECT input_per_million, output_per_million FROM model_catalog WHERE provider_model_id = :mid LIMIT 1'),
                {'mid': model},
            )
            fb_row = fallback_res.fetchone()
            if fb_row and (fb_row.input_per_million or fb_row.output_per_million):
                inp_rate = int(fb_row.input_per_million or 0)
                out_rate = int(fb_row.output_per_million or 0)
                cost = max(1, int((input_tokens * inp_rate + output_tokens * out_rate + 500_000) // 1_000_000))
            else:
                # Default baseline price per million if completely unpriced
                cost = max(1, int((input_tokens * 1000 + output_tokens * 2000 + 500_000) // 1_000_000))
        except Exception:
            cost = max(1, total_tokens)

    result['cost'] = cost

    # Always charge against Wallet.balance and append a Ledger row, even if current < cost.
    # No more free usage when current < cost.
    from services.billing import SqlBillingRepo
    _repo = SqlBillingRepo(session)
    async with _repo.lock_wallet_for_update(uid):
        wallet = await _repo.ensure_wallet(uid)
        current = wallet['balance']
        new_balance = current - cost
        await _repo.set_wallet_balance(uid, new_balance)
        entry = Ledger(user_id=uid, amount=-cost, balance_after=new_balance, reason=f'مصرف {model}', idempotency_key=idempotency_key)
        session.add(entry)
    result['balance_after'] = new_balance

    try:
        from services.metering import record_usage
        from services.money import Money
        await record_usage(
            _repo,
            request_id=secrets.token_hex(8),
            user_id=uid,
            model=model,
            charge=Money(cost),
            upstream_status='success',
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except Exception as e:
        logger.warning(f"_record_usage metering failed model={model} uid={uid}: {e}")

    return result


async def _track_usage(request: Request, payload: dict[str, Any], response_data: dict[str, Any]) -> dict[str, Any]:
    """Record token usage for non-streaming requests. Returns cost info."""
    uid = await _get_user_id(request)
    if not uid or async_session is None:
        return {}
    usage = response_data.get('usage', {})
    if usage.get('total_tokens', 0) <= 0:
        return {}
    resp_id = response_data.get('id')
    idempotency_key = f"usage:{resp_id}" if resp_id else None
    try:
        async with async_session() as session:
            cost_info = await _record_usage(session, uid, payload, usage, idempotency_key=idempotency_key)
            await session.commit()
            return cost_info
    except Exception as e:
        logger.warning(f"_track_usage failed uid={uid} model={payload.get('model')}: {e}")
        return {}


async def _bill_stream_usage(uid: int, payload: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    """Bill the user after a streaming chat completes. Returns cost info."""
    if usage.get('total_tokens', 0) <= 0:
        return {}
    try:
        async with async_session() as session:
            cost_info = await _record_usage(session, uid, payload, usage)
            await session.commit()
            return cost_info
    except Exception as e:
        logger.warning(f"_bill_stream_usage failed uid={uid} model={payload.get('model')}: {e}")
        return {}
