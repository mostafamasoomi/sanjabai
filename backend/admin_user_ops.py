"""Admin user-ops endpoints: wallet credit/debit and consumer/developer panel.

Split out of `admin.py` (already ~1,600 lines, over this repo's 500-line cap)
rather than added there. `admin.py`'s `PUT /admin/users/{uid}` used to let an
admin "edit balance" by inserting a single ledger row shaped like
`amount = balance_after = <new balance>`, with no `txn_type`, no idempotency
key, and without ever touching the `wallet` table -- silently desynchronising
the ledger from the wallet and violating the
`balance_after == previous_balance + amount` invariant enforced everywhere
else in this codebase. That branch now refuses the request outright (see the
admin.py diff) and points callers here instead.

Credit reuses `services.billing.credit_wallet` unchanged (it is already
correct: idempotent, wallet+ledger updated atomically under a row lock).
Debit has no existing call site to reuse -- `_debit_wallet` below is a
mirror-image of `credit_wallet`, built from the exact same
`SqlBillingRepo`/`MemoryBillingRepo` primitives (`lock_wallet_for_update`,
`ensure_wallet`, `set_wallet_balance`, `append_ledger`, `ledger_has_key`), so
it works against either repo and keeps the same idempotency and invariant
guarantees. It intentionally lives here, not in `services/billing.py`
(read-only for this change) -- if a second debit call-site ever appears,
promote it there.
"""
from __future__ import annotations

import secrets
from typing import Any, Optional

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from database import async_session
from models import User
from dependencies import admin_required, _write_audit_log
from services.billing import SqlBillingRepo, credit_wallet, InsufficientBalanceError
from services.money import Money

router = APIRouter()

_VALID_DIRECTIONS = {"credit", "debit"}
_VALID_PANELS = {"consumer", "developer"}


async def _debit_wallet(
    repo: Any,
    user_id: int,
    amount: Money,
    reason: str,
    idempotency_key: Optional[str] = None,
    txn_type: str = "admin_debit",
) -> int:
    """Atomically debit a wallet and append a ledger effect.

    Mirrors :func:`services.billing.credit_wallet` in reverse: same
    idempotency guard (checked before taking the lock), same
    lock-then-read-then-write shape, same append-only ledger effect with
    `balance_after == previous_balance + amount` (amount is negative here).
    Refuses -- raises :class:`InsufficientBalanceError` -- rather than ever
    taking `wallet.balance` negative. Returns the resulting balance (the
    pre-existing balance, unchanged, on a replayed idempotency key).
    """
    if not isinstance(amount, Money):
        raise TypeError("amount must be a Money instance")

    if idempotency_key is not None and await repo.ledger_has_key(idempotency_key):
        wallet = await repo.get_wallet(user_id) or {"balance": 0, "reserved": 0}
        return wallet["balance"]

    async with repo.lock_wallet_for_update(user_id):
        wallet = await repo.ensure_wallet(user_id)
        if amount.toman > wallet["balance"]:
            raise InsufficientBalanceError(
                f"insufficient balance: balance {wallet['balance']}, "
                f"requested debit {amount.toman}"
            )
        new_balance = wallet["balance"] - amount.toman
        await repo.set_wallet_balance(user_id, new_balance)
        await repo.append_ledger({
            "user_id": user_id,
            "txn_type": txn_type,
            "amount": -amount.toman,
            "balance_after": new_balance,
            "reason": reason,
            "idempotency_key": idempotency_key,
        })
    return new_balance


@router.post('/admin/users/{uid}/wallet-adjust')
async def wallet_adjust(request: Request, uid: int, payload: dict[str, Any]) -> JSONResponse:
    """Manually credit or debit a user's wallet, with an audited, mandatory reason.

    Body: {amount_toman: int (>0), direction: 'credit'|'debit', reason: str,
    idempotency_key?: str}. `idempotency_key` is optional and client-supplied
    (e.g. generated once per submit by the admin UI) so a retried/duplicated
    request never double-applies -- this repo's existing idempotency keys
    (payment.py, auth.py referral/signup bonuses, hermes.py renewals) are all
    derived from a natural external event id; a manual admin action has none,
    so the caller supplies one instead. Money is a plain integer number of
    Toman -- floats (even integral ones like 100.0) are rejected explicitly
    here rather than silently coerced, since a coerced float is exactly the
    kind of quietly-wrong money handling this codebase has been burned by
    before.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    amount = payload.get('amount_toman')
    direction = payload.get('direction')
    reason = payload.get('reason')
    idempotency_key = payload.get('idempotency_key')

    if isinstance(amount, bool) or not isinstance(amount, int):
        return JSONResponse(
            {'detail': 'مبلغ باید عدد صحیح تومان باشد؛ اعشار مجاز نیست'},
            status_code=400,
        )
    if amount <= 0:
        return JSONResponse({'detail': 'مبلغ باید بزرگ‌تر از صفر باشد'}, status_code=400)
    if direction not in _VALID_DIRECTIONS:
        return JSONResponse(
            {'detail': "جهت تراکنش باید 'credit' یا 'debit' باشد"}, status_code=400,
        )
    if not isinstance(reason, str) or not reason.strip():
        return JSONResponse({'detail': 'ذکر دلیل تراکنش الزامی است'}, status_code=400)
    reason = reason.strip()
    if idempotency_key is not None and not isinstance(idempotency_key, str):
        return JSONResponse({'detail': 'کلید یکتایی نامعتبر است'}, status_code=400)
    if not idempotency_key:
        idempotency_key = f"admin_{direction}:{uid}:{secrets.token_hex(16)}"

    money = Money(amount)

    async with async_session() as session:
        user = await session.get(User, uid)
        if not user:
            return JSONResponse({'detail': 'کاربر یافت نشد'}, status_code=404)

        repo = SqlBillingRepo(session)
        try:
            if direction == 'credit':
                await credit_wallet(
                    repo, uid, money, reason=reason,
                    idempotency_key=idempotency_key, txn_type='admin_credit',
                )
            else:
                await _debit_wallet(
                    repo, uid, money, reason=reason,
                    idempotency_key=idempotency_key, txn_type='admin_debit',
                )
        except InsufficientBalanceError:
            await session.rollback()
            return JSONResponse(
                {'detail': 'موجودی کیف پول کافی نیست؛ این کسر موجودی را منفی می‌کند'},
                status_code=400,
            )
        await session.commit()
        wallet_row = await repo.get_wallet(uid) or {'balance': 0, 'reserved': 0}

    await _write_audit_log(
        f'admin.user.wallet_{direction}',
        target_type='user', target_id=uid,
        details={
            'amount_toman': amount, 'direction': direction,
            'reason': reason, 'idempotency_key': idempotency_key,
        },
        request=request,
    )
    return JSONResponse({
        'status': 'ok', 'uid': uid, 'direction': direction,
        'amount_toman': amount, 'balance': wallet_row['balance'],
    })


@router.post('/admin/users/{uid}/panel')
async def set_user_panel(request: Request, uid: int, payload: dict[str, Any]) -> JSONResponse:
    """Move a user between the consumer and developer panels.

    Investigation finding (see report): there is no `role` column on `users`
    and no backend-enforced consumer/developer distinction anywhere today --
    `/developer` is an unconditionally visible nav item and a public route in
    the frontend (frontend/components/AppShell.tsx), reachable by any
    authenticated user regardless of anything stored server-side. ROADMAP's
    "migration 0026 for the role column" was never created (migration
    numbering jumps 0025 -> 0027). Rather than adding a new column for a
    distinction nothing reads yet, this writes the label into the existing
    `users.preferences` JSONB column (migrations/0010_user_profile.sql),
    the same column that already carries `ai_personality` and
    `pinned_context` (dependencies.py). The `||` jsonb-concat update merges
    in just the `panel` key without clobbering the rest of preferences and
    without a read-modify-write race.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    panel = payload.get('panel')
    if panel not in _VALID_PANELS:
        return JSONResponse(
            {'detail': "مقدار پنل باید 'consumer' یا 'developer' باشد"}, status_code=400,
        )

    async with async_session() as session:
        user = await session.get(User, uid)
        if not user:
            return JSONResponse({'detail': 'کاربر یافت نشد'}, status_code=404)
        await session.execute(
            sqlalchemy.text(
                "UPDATE users SET preferences = COALESCE(preferences, '{}'::jsonb) "
                "|| jsonb_build_object('panel', :panel) WHERE id = :uid"
            ),
            {'panel': panel, 'uid': uid},
        )
        await session.commit()

    await _write_audit_log(
        'admin.user.panel', target_type='user', target_id=uid,
        details={'panel': panel}, request=request,
    )
    return JSONResponse({'status': 'ok', 'uid': uid, 'panel': panel})
