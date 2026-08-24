"""Hermes server product -- monthly renewal cron (`run_renewal_cycle`).

Invoked on a daily schedule from app.py's lifespan background loop
(mirrors `_pricing_refresh_loop`; see app.py's `_hermes_renewal_loop`,
which does `from hermes import run_renewal_cycle` on every tick).

Split out of hermes.py purely to stay under the house 500-line cap -- see
hermes.py's module docstring for the full product overview. Nothing here
changed in the move.

SAFETY NOTE: the function body below is one `async with async_session() as
session:` transaction spanning the whole per-server loop, with a single
`await session.commit()` at the very end (after the loop, not per-server).
It writes two `Notification` rows inside that transaction (one for
"suspended", one for "insufficient balance, not yet suspended") plus the
`Ledger` row for a successful charge. The function was moved as a single,
unmodified unit -- nothing was added, removed, or reindented inside or
outside the `async with` block, so the transaction's extent (and thus what
would roll back together on failure) is unchanged from before the split.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from database import async_session
from services.billing import SqlBillingRepo
from models import HermesServer, Ledger, Notification
from hermes import _utcnow


async def run_renewal_cycle() -> dict:
    """Charge active servers past `paid_through_at` for another month.

    Idempotent per calendar month via `idempotency_key`; grace period of 7
    days on insufficient balance before suspension. Called on a daily
    schedule from app.py's lifespan (mirrors `_pricing_refresh_loop`).
    """
    if async_session is None:
        return {'charged': 0, 'suspended': 0}

    charged = 0
    suspended = 0
    now = _utcnow()
    async with async_session() as session:
        res = await session.execute(
            select(HermesServer).where(
                HermesServer.status == 'active', HermesServer.paid_through_at <= now,
            )
        )
        servers = [row[0] for row in res.fetchall()]
        repo = SqlBillingRepo(session)

        for server in servers:
            month_key = now.strftime('%Y-%m')
            idem_key = f"hermes-renew:{server.id}:{month_key}"

            existing = await session.execute(
                select(Ledger).where(Ledger.idempotency_key == idem_key)
            )
            if existing.scalar_one_or_none():
                # Already charged this month; just roll the due date forward.
                server.paid_through_at = server.paid_through_at + timedelta(days=30)
                continue

            async with repo.lock_wallet_for_update(server.user_id):
                wallet = await repo.ensure_wallet(server.user_id)
                current_balance = wallet['balance']

                if current_balance < server.monthly_price_irt:
                    grace_deadline = server.paid_through_at + timedelta(days=7)
                    if now >= grace_deadline:
                        server.status = 'suspended'
                        server.updated_at = now
                        session.add(Notification(
                            user_id=server.user_id, type='hermes',
                            title='سرور هرمس شما به دلیل کسری موجودی متوقف شد',
                            body='برای فعال‌سازی مجدد، کیف پول خود را شارژ کنید.',
                        ))
                        suspended += 1
                    else:
                        session.add(Notification(
                            user_id=server.user_id, type='hermes',
                            title='موجودی کیف پول برای تمدید سرور هرمس کافی نیست',
                            body=f'لطفاً تا {grace_deadline.date().isoformat()} کیف پول را شارژ کنید تا سرور متوقف نشود.',
                        ))
                    continue

                new_balance = current_balance - server.monthly_price_irt
                await repo.set_wallet_balance(server.user_id, new_balance)
                session.add(Ledger(
                    user_id=server.user_id, amount=-server.monthly_price_irt, balance_after=new_balance,
                    reason=f'تمدید ماهانه سرور هرمس #{server.id}', idempotency_key=idem_key,
                ))
                server.paid_through_at = server.paid_through_at + timedelta(days=30)
                server.updated_at = now
                charged += 1

        await session.commit()

    return {'charged': charged, 'suspended': suspended}
