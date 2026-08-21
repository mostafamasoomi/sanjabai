"""Free-tier per-model message throttle.

Applies ONLY to users who have never made a real gateway payment (see
:func:`has_paid`). Free-mode messages are still charged against the wallet
as normal by BillingService.reserve() — this is an *additional* UX gate
whose purpose is to stop a signup gift being burned on a single model, and
to nudge new users into trying several models.

Storage: Redis only, no DB migration involved. Key
``freetier:msg:{uid}:{model}`` is a fixed 5-hour bucket anchored at the
first message of the bucket (NOT a rolling window): the first message
INCRs the key to 1 then sets EXPIRE 18000; messages 2-5 INCR the same key;
an attempt while the count already sits at FREE_LIMIT is rejected and the
counter is left untouched (never decremented, never incremented past the
limit) — the key's remaining TTL is what gets handed back as the retry
countdown. A companion set key, ``freetier:models:{uid}``, tracks which
models have an open bucket so the status endpoint can build its response
without a Redis SCAN.

"Has never paid" is resolved from the payment tables (``payments`` and the
legacy ``payment_orders``), never the ``ledger`` — the ledger writes
``txn_type='credit'`` for gateway payments, referral bonuses AND the
signup gift alike, so it cannot tell a real payment apart from free money.
The answer is cached in Redis (``freetier:paid:{uid}``) since has_paid() is
on the hot path of every chat request.

Fail-open: any Redis or DB error while evaluating the gate is logged as a
warning and the request is allowed through unthrottled. Money is still
protected by BillingService.reserve regardless of the outcome of this
gate — availability wins here, not the free-tier nudge.
"""
from __future__ import annotations

import logging
from typing import Optional

import sqlalchemy

from database import async_session, rds

logger = logging.getLogger(__name__)

FREE_LIMIT = 5
WINDOW_SECONDS = 18000  # 5 hours

_PAID_TTL = 30 * 24 * 3600  # 30 days — paying never un-pays
_UNPAID_TTL = 300  # 5 minutes — re-check soon in case a payment just landed

_HAS_PAID_SQL = sqlalchemy.text(
    "SELECT 1 FROM payments WHERE user_id = :uid AND status = 'completed' "
    "UNION ALL "
    "SELECT 1 FROM payment_orders WHERE user_id = :uid AND status = 'completed' "
    "LIMIT 1"
)


def _paid_key(uid: int) -> str:
    return f'freetier:paid:{uid}'


def _msg_key(uid: int, model: str) -> str:
    return f'freetier:msg:{uid}:{model}'


def _models_key(uid: int) -> str:
    return f'freetier:models:{uid}'


async def has_paid(uid: int) -> bool:
    """Return True iff the user has ever completed a real gateway payment.

    Cached in Redis so this doesn't cost a DB round-trip on every chat
    request. On any Redis/DB error this logs a warning and returns False
    (i.e. "can't confirm paid, apply the free-tier gate") rather than
    raising — callers (:func:`check_and_consume`) have their own top-level
    fail-open handling for the case where the gate itself can't run at all.
    """
    key = _paid_key(uid)
    try:
        cached = await rds.get(key)
        if cached == '1':
            return True
        if cached == '0':
            return False
    except Exception as e:
        logger.warning(f"free_tier.has_paid cache read failed uid={uid}: {e}")

    paid = False
    try:
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(_HAS_PAID_SQL, {'uid': uid})
                paid = res.fetchone() is not None
    except Exception as e:
        logger.warning(f"free_tier.has_paid db check failed uid={uid}: {e}")
        return False

    try:
        if paid:
            await rds.set(key, '1', ex=_PAID_TTL)
        else:
            await rds.set(key, '0', ex=_UNPAID_TTL)
    except Exception as e:
        logger.warning(f"free_tier.has_paid cache write failed uid={uid}: {e}")

    return paid


async def check_and_consume(uid: int, models: list[str]) -> Optional[dict]:
    """Check the free-tier throttle for every model in ``models`` and, only
    if all of them pass, consume one message from each of their buckets.

    Returns ``None`` when the request is allowed (the user has paid, or
    every model in ``models`` still has budget left in its current
    window). Otherwise returns ``{'model': m, 'retry_after_seconds': ttl}``
    for the first model that is out of budget — nothing is consumed in
    that case, including for models earlier in the list that would
    otherwise have passed (this matters for /v1/compare's two-model call).

    Fails open: any Redis/DB error anywhere in this function is logged as
    a warning and treated as an allow (returns None).
    """
    try:
        if await has_paid(uid):
            return None

        # Phase 1 — peek every model's counter without mutating anything.
        for model in models:
            key = _msg_key(uid, model)
            raw = await rds.get(key)
            count = int(raw) if raw is not None else 0
            if count >= FREE_LIMIT:
                ttl = await rds.ttl(key)
                if ttl is None or ttl < 0:
                    # Expiry was somehow lost on a key that's at the cap —
                    # can't report a meaningful countdown, so fail open
                    # rather than trap the user behind a bucket that will
                    # never reset.
                    logger.warning(
                        f"free_tier: uid={uid} model={model} at cap with no TTL, failing open"
                    )
                    return None
                return {'model': model, 'retry_after_seconds': int(ttl)}

        # Phase 2 — every model passed, now actually consume one message
        # from each bucket.
        models_key = _models_key(uid)
        for model in models:
            key = _msg_key(uid, model)
            new_count = await rds.incr(key)
            if new_count == 1:
                await rds.expire(key, WINDOW_SECONDS)
            else:
                ttl = await rds.ttl(key)
                if ttl is None or ttl < 0:
                    await rds.expire(key, WINDOW_SECONDS)
            await rds.sadd(models_key, model)
            await rds.expire(models_key, WINDOW_SECONDS)

        return None
    except Exception as e:
        logger.warning(f"free_tier.check_and_consume failed uid={uid} models={models}: {e}")
        return None


async def get_status(uid: int) -> dict:
    """Per-model free-tier usage snapshot for GET /free-tier/status.

    Fails open (reports ``free_mode: True`` with no per-model detail)
    rather than raising, so a Redis/DB hiccup never breaks the wallet page.
    """
    try:
        if await has_paid(uid):
            return {
                'free_mode': False,
                'limit': FREE_LIMIT,
                'window_seconds': WINDOW_SECONDS,
                'models': [],
            }

        members = await rds.smembers(_models_key(uid)) or set()
        models: list[dict] = []
        for model in members:
            key = _msg_key(uid, model)
            raw = await rds.get(key)
            if raw is None:
                # Bucket already expired (or never existed) — the frontend
                # treats an absent model as 5/5 remaining.
                continue
            ttl = await rds.ttl(key)
            if ttl is None or ttl < 0:
                continue
            used = int(raw)
            models.append({
                'model': model,
                'used': used,
                'remaining': max(FREE_LIMIT - used, 0),
                'reset_in_seconds': int(ttl),
            })

        return {
            'free_mode': True,
            'limit': FREE_LIMIT,
            'window_seconds': WINDOW_SECONDS,
            'models': models,
        }
    except Exception as e:
        logger.warning(f"free_tier.get_status failed uid={uid}: {e}")
        return {
            'free_mode': True,
            'limit': FREE_LIMIT,
            'window_seconds': WINDOW_SECONDS,
            'models': [],
        }
