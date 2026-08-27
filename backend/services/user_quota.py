"""Aggregate per-user message quota, scaled by the user's paid package.

THE ONE GATE. This is the single per-user message cap for every chat entry
point. It is wired in exactly one place -- ``chat_web.py::_chat_preflight``,
which all four chat HTTP routes (/v1/chat/completions, /v1/chat/with-file,
/v1/smart-chat, /v1/compare) already funnel through as their first act after
resolving the user -- so there is one counter, one limit resolution and one
rejection message rather than four drifting copies.

Also home to :func:`premium_package_window_limit`, the identical
best-active-package lookup for services/premium_quota.py's
``premium_rate_limit_per_window`` column (migration 0046). It shares this
module's tiering logic (package holder -> capped, everyone else -> exempt
from THAT gate) and its query helper (:func:`_best_package_value`) rather
than duplicating the JOIN/WHERE in a second module -- see
services/premium_quota.py's module docstring for what the premium gate does
with the number this returns.

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
   ``credit_packages.rate_limit_per_window`` is set  ->  that value is the
   window limit (highest one wins if several packages are held). Checked
   FIRST, before the paid/balance exemption below: a package buyer has
   almost certainly paid, so testing has_paid() first would make every
   package's quota dead code.

   NOTE (migration 0046): this used to read ``request_quota``, which is a
   DIFFERENT column that services/entitlements.py separately snapshots into
   a finite bundle of free requests at purchase time. Reading it here too
   meant setting a rate limit silently handed the buyer that many free
   requests as well -- the owner never intended that giveaway. This module
   now reads its own dedicated ``rate_limit_per_window`` column, completely
   independent of entitlements/request_quota.
2. Otherwise the user has paid through the gateway or holds wallet credit
   (services/free_tier.py::has_paid / has_balance)  ->  EXEMPT, no cap.
   This preserves today's behaviour exactly: a wallet customer pays per
   request and is self-limiting, and the account holding 9,954,787 toman
   that was once told "your credit has run out" must never be capped again.
3. Otherwise (never paid, no balance, no package = the FREE TIER)  ->  also
   EXEMPT here. The free tier is handled entirely by services/free_tier.py,
   which runs post-model (after model resolution) so it can additionally
   enforce the cheap-models-only rule alongside its hourly and lifetime
   caps -- something this pre-model, per-user gate cannot do. Gating free
   users here as well would double-count and could burn a free user's
   lifetime allowance on a premium request this gate cannot even see. So in
   practice this module is now the PACKAGE-holder gate; :data:`DEFAULT_LIMIT`
   is retained only as documentation of the former default and is no longer
   returned.

Note the deliberate divergence from services/entitlements.py's rule that
quota values are snapshotted at grant time and never re-read live from
``credit_packages``. That rule protects a *purchase* (what a user already
bought must not shrink because an admin edited a package). This is a
refreshing rate limit, not a purchase: it must follow the admin's current
setting, so it reads ``credit_packages.rate_limit_per_window`` live. The
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

logger = logging.getLogger(__name__)

# LEGACY. Was the free-tier aggregate cap; the free tier moved wholesale to
# services/free_tier.py (hourly + lifetime + cheap-models). Retained as a
# named constant only so tests and readers can refer to the former value; it
# is no longer returned by resolve_limit().
DEFAULT_LIMIT = 50

# 5 hours, the same bucket length services/free_tier.py uses.
WINDOW_SECONDS = 18000

# Limit sources, reported in the gate dict and in get_status() so the
# rejection message and any admin debugging can say WHY this cap applied.
SOURCE_PACKAGE = 'package'
SOURCE_DEFAULT = 'default'  # legacy, no longer returned (see DEFAULT_LIMIT)
SOURCE_EXEMPT = 'exempt'


def _msg_key(uid: int) -> str:
    return f'userquota:msg:{uid}'


# Highest rate_limit_per_window among the packages this user currently holds.
#
# Every clause here is load-bearing and asserted literally in
# tests/test_user_quota.py (SQL-contract style, following
# tests/test_entitlements_sql_contract.py -- there is no live Postgres in
# the test environment, so a fake session that re-implements the predicate
# in Python cannot prove a weakened WHERE clause was not shipped):
#   * active = true and not expired -- a lapsed package must not keep
#     granting its higher cap
#   * rate_limit_per_window IS NOT NULL AND > 0 -- NULL means "this package
#     grants no rate-limit tier", which must fall through to exempt, never
#     be read as "unlimited"
#   * MAX(...) -- a user holding several packages gets the best one
# Deliberately does NOT filter on requests_remaining/request_quota (a
# different, entitlements-owned column as of migration 0046 -- see the
# module docstring): the rate limit and the finite request bundle are now
# fully independent, and this predicate does not look at the bundle at all.
_PACKAGE_LIMIT_SQL = sqlalchemy.text(
    "SELECT MAX(cp.rate_limit_per_window) AS limit_value "
    "FROM package_entitlement pe "
    "JOIN credit_packages cp ON cp.id = pe.package_id "
    "WHERE pe.user_id = :uid "
    "AND pe.active = true "
    "AND (pe.expires_at IS NULL OR pe.expires_at > now()) "
    "AND cp.rate_limit_per_window IS NOT NULL "
    "AND cp.rate_limit_per_window > 0"
)

# Same shape, for services/premium_quota.py's premium_rate_limit_per_window
# column (migration 0046): of the messages the rate limit above allows, how
# many may land on an "expensive" model. Same NULL-means-no-tier and
# MAX-across-packages rules as _PACKAGE_LIMIT_SQL, on the sibling column.
_PREMIUM_LIMIT_SQL = sqlalchemy.text(
    "SELECT MAX(cp.premium_rate_limit_per_window) AS limit_value "
    "FROM package_entitlement pe "
    "JOIN credit_packages cp ON cp.id = pe.package_id "
    "WHERE pe.user_id = :uid "
    "AND pe.active = true "
    "AND (pe.expires_at IS NULL OR pe.expires_at > now()) "
    "AND cp.premium_rate_limit_per_window IS NOT NULL "
    "AND cp.premium_rate_limit_per_window > 0"
)


async def _best_package_value(uid: int, sql) -> Optional[int]:
    """Shared body for :func:`package_window_limit` and
    :func:`premium_package_window_limit`: run ``sql`` (a MAX(...) query over
    this user's active, unexpired packages) and return the positive int it
    found, or None on no row / a NULL/non-positive value / any error.

    Returns None both when the user holds no quota-granting package AND
    when the lookup itself failed -- the caller cannot tell the difference
    and must not: both mean "no package-scaled cap applies here". Never
    raises.

    Not cached. A purchase must lift the cap immediately -- the same reason
    services/free_tier.py::has_balance is not cached -- and this is one
    indexed lookup on (user_id, active) joined to a three-row table.
    """
    try:
        if async_session is None:
            return None
        async with async_session() as session:
            res = await session.execute(sql, {'uid': int(uid)})
            row = res.fetchone()
            if row is None:
                return None
            value = row._mapping['limit_value']
            if value is None:
                return None
            value = int(value)
            return value if value > 0 else None
    except Exception as e:
        logger.warning(f"user_quota._best_package_value failed uid={uid}: {e}")
        return None


# Existence-only sibling of _PACKAGE_LIMIT_SQL / _PREMIUM_LIMIT_SQL: same
# active/unexpired predicate, but does not care which tiering columns (if
# any) the held package sets -- used where the caller only needs "does this
# user hold ANY live package" (security.py's chat limiter tier,
# chat_smart.py's model eligibility), not a specific numeric cap.
_ACTIVE_PACKAGE_SQL = sqlalchemy.text(
    "SELECT 1 "
    "FROM package_entitlement pe "
    "JOIN credit_packages cp ON cp.id = pe.package_id "
    "WHERE pe.user_id = :uid "
    "AND pe.active = true "
    "AND (pe.expires_at IS NULL OR pe.expires_at > now()) "
    "LIMIT 1"
)


async def has_active_package(uid: int) -> bool:
    """True iff the user holds any active, unexpired package entitlement.

    Used by security.py to pick the chat rate-limiter tier (package holder
    -> pro limiter, everyone else -> free limiter). That is its ONLY
    consumer, deliberately: chat_smart.py was going to read it for model
    eligibility and that was reversed before it shipped, because switching
    on a never-executed tier branch would have changed which model paying
    customers are served as a side effect of a refactor. See
    chat_smart.py::_select_smart_model's docstring. Deliberately
    existence-only: unlike
    :func:`package_window_limit` it does not require any particular
    tiering column to be set on the held package.

    Fails OPEN like the rest of this module (see the module docstring) --
    but "open" here means the SAME thing it means everywhere else in this
    file: never let an infrastructure hiccup make a request MORE
    restricted than it would otherwise be. Concretely that means returning
    True on error, handing the caller the more permissive (pro) limiter
    tier rather than silently downgrading a possible package holder to the
    free tier's tighter cap. This is a UX nudge, not a money gate --
    BillingService.reserve() still guards spend on every path regardless
    of what this returns.
    """
    try:
        if async_session is None:
            return True
        async with async_session() as session:
            res = await session.execute(_ACTIVE_PACKAGE_SQL, {'uid': int(uid)})
            return res.fetchone() is not None
    except Exception as e:
        logger.warning(f"user_quota.has_active_package failed uid={uid}: {e}")
        return True


async def package_window_limit(uid: int) -> Optional[int]:
    """The rate-limit window granted by the user's best active package, or
    None -- see :func:`_best_package_value`."""
    return await _best_package_value(uid, _PACKAGE_LIMIT_SQL)


async def premium_package_window_limit(uid: int) -> Optional[int]:
    """The premium (expensive-model) sub-allowance granted by the user's
    best active package, or None -- see :func:`_best_package_value`. Used by
    services/premium_quota.py; kept here rather than duplicated so both
    gates share one JOIN/WHERE shape and one set of tests."""
    return await _best_package_value(uid, _PREMIUM_LIMIT_SQL)


async def resolve_limit(uid: int) -> tuple[Optional[int], str]:
    """``(limit, source)`` for this user. ``limit is None`` means exempt.

    See the module docstring for the three tiers and why the package tier
    is evaluated before the paid/balance exemption.
    """
    pkg_limit = await package_window_limit(uid)
    if pkg_limit is not None:
        return pkg_limit, SOURCE_PACKAGE

    # Everyone without a quota-granting package is exempt from THIS gate:
    # paid/balance users pay per request, and the free tier is enforced by
    # services/free_tier.py (post-model, so it can also gate on model price).
    # See the module docstring, tier 3.
    return None, SOURCE_EXEMPT


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
