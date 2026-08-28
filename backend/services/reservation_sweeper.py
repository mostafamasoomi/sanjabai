"""Sweeper for stale ``wallet_reservations`` rows stuck in ``status='reserved'``.

Root cause this repairs: nothing in the codebase ever releases a reservation
that never got a matching settle/release call (e.g. the request crashed
between reserve() and settle()/release()). The only existing observer,
``watchdog_rules.py``'s ``stale_reservations`` check (interval 15 minutes),
is an *alert*, not a repair, and its ``HAVING COUNT(*) > 5 OR SUM(amount) >
100000`` threshold means a single small leak never fires it -- the user's
``available = balance - reserved`` (see services/billing.py's
``BillingService`` docstring) stays permanently understated.

Correctness requirement (do not regress this): releasing a reservation MUST
decrement the denormalized ``wallet.reserved`` column in the same
transaction as marking the row released, under the wallet's row lock.
``services.billing.SqlBillingRepo.mark_reservation_released`` alone does
NOT do this -- it only flips the ``wallet_reservations`` row, which would
leave the money held while the row no longer looks stuck (the original bug,
now invisible). The only correct path is
``services.billing.BillingService.release()`` (see billing.py:415-437),
which does both writes inside ``repo.lock_wallet_for_update(user_id)``.
This module goes through that method exclusively -- never
``mark_reservation_released`` directly.

Age threshold -- why 1 hour is safe:
A live request can only hold a reservation for, at most, the sum of its own
processing time. The two governing timeouts are both far below one hour:

  * ``COMPLETION_TIMEOUT_SECONDS`` (non-streaming ceiling) defaults to 180s
    -- see backend/providers.py:54-55.
  * The shared HTTP client's streaming/default read timeout is 90s -- see
    backend/app.py:116 (``httpx.Timeout(90, connect=10)``), also referenced
    in backend/providers.py:41-52.

So no in-flight request can still legitimately own a reservation older than
one hour; anything that old is a leak, not a slow request.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import async_session
from services.billing import BillingService, SqlBillingRepo

logger = logging.getLogger(__name__)

# Age threshold, in seconds, above which a 'reserved' row is considered
# leaked rather than in flight. See module docstring for the justification
# against COMPLETION_TIMEOUT_SECONDS / the shared client's read timeout.
STALE_RESERVATION_AGE_SECONDS = 3600  # 1 hour

# How often the background loop ticks.
SWEEP_INTERVAL_SECONDS = 300  # 5 minutes

# Written to wallet_reservations.reason so a later audit can tell a swept
# leak apart from a normal application-triggered release at a glance.
SWEEP_REASON = "swept: stale reservation older than 1h"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_stale(created_at: Optional[datetime], now: datetime, threshold_seconds: int) -> bool:
    if created_at is None:
        return False
    return (now - created_at).total_seconds() >= threshold_seconds


async def _find_stale_reservation_ids(repo: Any, now: datetime, threshold_seconds: int) -> list[str]:
    """Repo-agnostic on purpose: ``created_at`` is not part of the
    ``get_reservation()``/``release()`` repo contract (services/billing.py),
    so this looks past the contract at the underlying storage directly --
    the SQL table for :class:`SqlBillingRepo`, or the in-memory dict for
    :class:`services.billing_memory.MemoryBillingRepo` (test double), which
    lets the whole find+release pipeline be exercised in tests with no
    database (see tests/test_reservation_sweeper.py).
    """
    reservations = getattr(repo, "reservations", None)
    if reservations is not None:
        return [
            rid
            for rid, r in list(reservations.items())
            if r.get("status") == "reserved"
            and _is_stale(r.get("created_at"), now, threshold_seconds)
        ]
    from sqlalchemy import select
    from models import WalletReservation
    cutoff = now - timedelta(seconds=threshold_seconds)
    res = await repo.session.execute(
        select(WalletReservation.reservation_id)
        .where(WalletReservation.status == "reserved")
        .where(WalletReservation.created_at < cutoff)
    )
    return [row[0] for row in res.fetchall()]


@dataclass
class SweepResult:
    examined: int
    swept: int
    failed: int


async def sweep_stale_reservations(
    repo: Any,
    *,
    now: Optional[datetime] = None,
    threshold_seconds: int = STALE_RESERVATION_AGE_SECONDS,
) -> SweepResult:
    """Find every stale ``reserved`` row and release it through
    :meth:`BillingService.release` (the only path that also decrements
    ``wallet.reserved`` -- see module docstring). One reservation failing to
    release must not stop the rest from being swept: each release is wrapped
    individually and a failure is logged and counted, not raised. Idempotent:
    a row already moved out of ``status='reserved'`` (by a previous sweep, or
    by the app settling/releasing it normally in the meantime) is simply not
    selected on the next run.
    """
    now = now or _utcnow()
    try:
        stale_ids = await _find_stale_reservation_ids(repo, now, threshold_seconds)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("reservation_sweeper: failed to query stale reservations")
        return SweepResult(examined=0, swept=0, failed=0)

    service = BillingService(repo)
    swept = 0
    failed = 0
    for reservation_id in stale_ids:
        try:
            await service.release(reservation_id, reason=SWEEP_REASON)
            swept += 1
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "reservation_sweeper: failed to release reservation %s", reservation_id
            )
            failed += 1

    commit = getattr(repo, "commit", None)
    if commit is not None:
        try:
            await commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("reservation_sweeper: commit failed after sweep")

    return SweepResult(examined=len(stale_ids), swept=swept, failed=failed)


async def sweep_tick() -> SweepResult:
    """One tick against a fresh DB session. Mirrors
    ``services/task_scheduler.py``'s ``scheduler_tick()``. Never raises
    (except ``asyncio.CancelledError``, which must propagate for clean
    shutdown) -- a sweeper that kills startup/shutdown is worse than the
    leak it fixes.
    """
    if async_session is None:
        return SweepResult(examined=0, swept=0, failed=0)
    try:
        async with async_session() as session:
            repo = SqlBillingRepo(session)
            return await sweep_stale_reservations(repo)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("reservation_sweeper: tick failed")
        return SweepResult(examined=0, swept=0, failed=0)


async def reservation_sweeper_loop() -> None:
    """Background loop entry point -- for the coordinator to wire into
    app.py's lifespan via ``asyncio.create_task(reservation_sweeper_loop())``
    (and cancel it there on shutdown; ``asyncio.CancelledError`` is never
    swallowed here, so cancellation propagates and the task ends promptly).
    """
    logger.info(
        "reservation_sweeper: loop starting, interval=%ds, threshold=%ds",
        SWEEP_INTERVAL_SECONDS, STALE_RESERVATION_AGE_SECONDS,
    )
    while True:
        try:
            result = await sweep_tick()
            if result.examined:
                logger.info(
                    "reservation_sweeper: examined=%d swept=%d failed=%d",
                    result.examined, result.swept, result.failed,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("reservation_sweeper: iteration crashed")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
