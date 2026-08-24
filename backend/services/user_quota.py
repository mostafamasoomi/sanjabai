"""Aggregate per-user message quota, scaled by the user's paid package.

THE ONE GATE. This is the single per-user message cap for every chat entry
point. It is wired in exactly one place -- ``chat_web.py::_chat_preflight``,
which all four chat HTTP routes (/v1/chat/completions, /v1/chat/with-file,
/v1/smart-chat, /v1/compare) already funnel through as their first act after
resolving the user -- so there is one counter, one limit resolution and one
rejection message rather than four drifting copies.

── What it counts ─────────────────────────────────────────────────────────
One *request* = one message, aggregated across ALL models. This is the
deliberate difference from services/free_tier.py, which counts per model:
a user's 50 messages are 50 messages whether they spend them on one model
or on twenty. /v1/compare therefore costs ONE message even though it fans
out to two models -- the wallet still charges both model calls, this gate is
a message-count nudge, not a cost gate. ``cost`` exists so that decision can
be revisited at a call site without touching this module.

── How the limit is resolved (three tiers, in this order) ─────────────────
1. The user holds an active, unexpired ``package_entitlement`` whose
   ``credit_packages.request_quota`` is set  ->  that quota is the window
   limit (highest one wins if several packages are held). Checked FIRST,
   before the paid/balance exemption below: a package buyer has almost
   certainly paid, so testing has_paid() first would make every package's
   quota dead code.
2. Otherwise the user has paid through the gateway or holds wallet credit
   (services/free_tier.py::has_paid / has_balance)  ->  EXEMPT, no cap.
   This preserves today's behaviour exactly: a wallet customer pays per
   request and is self-limiting, and the account holding 9,954,787 toman
   that was once told "your credit has run out" must never be capped again.
3. Otherwise (never paid, no balance, no package)  ->  :data:`DEFAULT_LIMIT`.

Note the deliberate divergence from services/entitlements.py's rule that
quota values are snapshotted at grant time and never re-read live from
``credit_packages``. That rule protects a *purchase* (what a user already
bought must not shrink because an admin edited a package). This is a
refreshing rate limit, not a purchase: it must follow the admin's current
setting, so it reads ``credit_packages.request_quota`` live. The
entitlement row is used only to answer "does this user hold this package".

── Windowing ──────────────────────────────────────────────────────────────
Same fixed-5-hour bucket as services/free_tier.py, for consistency: key
``userquota:msg:{uid}`` is INCRBY'd, and the FIRST message of a bucket sets
EXPIRE 18000. It is anchored at that first message, not rolling -- an
attempt made while the count already sits at the limit is rejected without
touching the counter, and the key's remaining TTL is what is handed back as
the retry countdown.

── Fail-open ──────────────────────────────────────────────────────────────
Any Redis or DB error anywhere in :func:`check_and_consume` is logged as a
warning and the request is ALLOWED. A Redis hiccup must never lock out a
paying user. Money is still protected by BillingService.reserve() on every
path regardless of what this gate decides -- availability wins here, the
message cap does not.
"""
from __future__ import annotations

import logging
from typing import Optional

import sqlalchemy

from database import async_session, rds
from services.free_tier import has_balance, has_paid

logger = logging.getLogger(__name__)

# Messages per window for a user with no paid package. Product baseline,
# owner-set. Mainstream AI chat products cap free chat with a modest
# time-windowed message allowance and a substantially larger one on paid
# tiers; this is that shape, with the paid tier read off the package.
DEFAULT_LIMIT = 50

# 5 hours, the same bucket length services/free_tier.py uses.
WINDOW_SECONDS = 18000

# Limit sources, reported in the gate dict and in get_status() so the
# rejection message and any admin debugging can say WHY this cap applied.
SOURCE_PACKAGE = 'package'
SOURCE_DEFAULT = 'default'
SOURCE_EXEMPT = 'exempt'


def _msg_key(uid: int) -> str:
    return f'userquota:msg:{uid}'


# Highest request_quota among the packages this user currently holds.
#
# Every clause here is load-bearing and asserted literally in
# tests/test_user_quota.py (SQL-contract style, following
# tests/test_entitlements_sql_contract.py -- there is no live Postgres in
# the test environment, so a fake session that re-implements the predicate
# in Python cannot prove a weakened WHERE clause was not shipped):
#   * active = true and not expired -- a lapsed package must not keep
#     granting its higher cap
#   * request_quota IS NOT NULL AND > 0 -- NULL means "this package grants
#     no request quota", which must fall through to DEFAULT_LIMIT, never be
#     read as "unlimited"
#   * MAX(...) -- a user holding several packages gets the best one
# Deliberately does NOT filter on requests_remaining: an entitlement whose
# purchased requests are spent still means the user *holds* that package
# until it expires, and the rate limit is not the thing that should punish
# them for it (they have no quota left to spend anyway).
_PACKAGE_LIMIT_SQL = sqlalchemy.text(
    "SELECT MAX(cp.request_quota) AS limit_value "
    "FROM package_entitlement pe "
    "JOIN credit_packages cp ON cp.id = pe.package_id "
    "WHERE pe.user_id = :uid "
    "AND pe.active = true "
    "AND (pe.expires_at IS NULL OR pe.expires_at > now()) "
    "AND cp.request_quota IS NOT NULL "
    "AND cp.request_quota > 0"
)


async def package_window_limit(uid: int) -> Optional[int]:
    """The window limit granted by the user's best active package, or None.

    Returns None both when the user holds no quota-granting package AND
    when the lookup itself failed -- the caller cannot tell the difference
    and must not: both mean "no package-scaled cap applies here", and the
    tiers below (paid exemption, then the default) are the safe answer in
    either case. Never raises.

    Not cached. A purchase must lift the cap immediately -- the same reason
    services/free_tier.py::has_balance is not cached -- and this is one
    indexed lookup on (user_id, active) joined to a three-row table.
    """
    try:
        if async_session is None:
            return None
        async with async_session() as session:
            res = await session.execute(_PACKAGE_LIMIT_SQL, {'uid': int(uid)})
            row = res.fetchone()
            if row is None:
                return None
            value = row._mapping['limit_value']
            if value is None:
                return None
            value = int(value)
            return value if value > 0 else None
    except Exception as e:
        logger.warning(f"user_quota.package_window_limit failed uid={uid}: {e}")
        return None


async def resolve_limit(uid: int) -> tuple[Optional[int], str]:
    """``(limit, source)`` for this user. ``limit is None`` means exempt.

    See the module docstring for the three tiers and why the package tier
    is evaluated before the paid/balance exemption.
    """
    pkg_limit = await package_window_limit(uid)
    if pkg_limit is not None:
        return pkg_limit, SOURCE_PACKAGE

    if await has_paid(uid):
        return None, SOURCE_EXEMPT
    if await has_balance(uid):
        return None, SOURCE_EXEMPT

    return DEFAULT_LIMIT, SOURCE_DEFAULT


async def check_and_consume(uid: int, cost: int = 1) -> Optional[dict]:
    """Charge ``cost`` messages against the user's window, or reject.

    Returns ``None`` when the request is allowed (and the counter has been
    advanced by ``cost``). Otherwise returns the rejection detail --
    ``{'limit', 'used', 'source', 'retry_after_seconds'}`` -- and the
    counter is left completely untouched, never partially consumed and
    never pushed past the limit.

    Peek-then-consume, in that order, exactly like
    services/free_tier.py::check_and_consume: the read decides, the write
    only happens once the decision is "allow". That two-phase shape is what
    keeps a rejection from burning budget.

    NOT ATOMIC ACROSS THE TWO PHASES, deliberately and identically to
    free_tier: two requests arriving at the same instant can both peek at
    limit-1 and both be allowed, so a user firing concurrent requests can
    overshoot the cap by roughly their concurrency. That is acceptable here
    -- this is a UX nudge, not the money guard (BillingService.reserve is,
    and it DOES lock) -- and the alternative, an INCRBY-first-then-refund
    shape, would burn budget on every rejection, which is worse. Do not
    "fix" this by moving the INCRBY before the check.

    Fails OPEN: any Redis/DB error is logged and treated as an allow.
    """
    try:
        cost = max(1, int(cost))
        limit, source = await resolve_limit(uid)
        if limit is None:
            return None

        key = _msg_key(uid)

        # Phase 1 -- peek. Nothing is mutated on the rejection path.
        raw = await rds.get(key)
        used = int(raw) if raw is not None else 0
        if used + cost > limit:
            ttl = await rds.ttl(key)
            if ttl is None or ttl < 0:
                # At the cap with no expiry set: the bucket would never
                # reset and there is no honest countdown to report, so fail
                # open rather than trap the user behind a dead key. Same
                # reasoning as free_tier's identical branch.
                logger.warning(
                    f"user_quota: uid={uid} at cap ({used}/{limit}) with no TTL, failing open"
                )
                return None
            return {
                'limit': limit,
                'used': used,
                'source': source,
                'retry_after_seconds': int(ttl),
            }

        # Phase 2 -- consume. The first message of a bucket anchors the
        # 5-hour window; a key that somehow lost its TTL gets one back
        # rather than living forever.
        new_count = await rds.incrby(key, cost)
        if new_count <= cost:
            await rds.expire(key, WINDOW_SECONDS)
        else:
            ttl = await rds.ttl(key)
            if ttl is None or ttl < 0:
                await rds.expire(key, WINDOW_SECONDS)

        return None
    except Exception as e:
        logger.warning(f"user_quota.check_and_consume failed uid={uid} cost={cost}: {e}")
        return None


async def get_status(uid: int) -> dict:
    """Read-only snapshot of the user's aggregate window. Consumes nothing.

    Not currently exposed by any HTTP route -- wallet.py (which owns
    /free-tier/status) is outside this change's file ownership. Written now
    so the endpoint is a one-line addition when the owner wants it.

    Fails open to an "unlimited/unknown" shape rather than raising.
    """
    try:
        limit, source = await resolve_limit(uid)
        if limit is None:
            return {'limited': False, 'limit': None, 'used': 0,
                    'remaining': None, 'source': source,
                    'window_seconds': WINDOW_SECONDS, 'reset_in_seconds': 0}

        raw = await rds.get(_msg_key(uid))
        used = int(raw) if raw is not None else 0
        ttl = await rds.ttl(_msg_key(uid))
        reset_in = int(ttl) if (ttl is not None and ttl > 0) else 0
        return {
            'limited': True,
            'limit': limit,
            'used': used,
            'remaining': max(limit - used, 0),
            'source': source,
            'window_seconds': WINDOW_SECONDS,
            'reset_in_seconds': reset_in,
        }
    except Exception as e:
        logger.warning(f"user_quota.get_status failed uid={uid}: {e}")
        return {'limited': False, 'limit': None, 'used': 0, 'remaining': None,
                'source': SOURCE_EXEMPT, 'window_seconds': WINDOW_SECONDS,
                'reset_in_seconds': 0}
