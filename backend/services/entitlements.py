"""Package entitlements: request/token quotas granted by a credit package,
counted separately from the Toman wallet.

See migrations/0034_package_entitlements.sql for the schema this module
reads and writes (``credit_packages``'s four new nullable quota columns,
and the new ``package_entitlement`` table).

── The loss-protection rule this module exists to enforce ─────────────────
The product rule is that no request may ever be loss-making. A package
granting "500 requests" with no per-request cost ceiling is a loss path: a
user could spend the whole quota on the single most expensive model
available and lose money on every one of those requests. So every
entitlement carries a ``max_cost_per_request_toman`` ceiling, copied from
the package at *grant* time (never read live from ``credit_packages`` on
the request path, so editing a package later can never retroactively
change what a user already bought). A request whose estimated cost is
above an entitlement's ceiling is simply not covered by it and falls
through to the normal wallet path -- see :func:`find_covering_entitlement`.

An entitlement with a NULL ceiling covers nothing. NULL is not "no limit",
it is "no ceiling was ever set for this grant" -- and this module fails
closed on that: it is treated exactly like an entitlement whose quota is
already exhausted, never as an unlimited allowance.

── What NULL means on ``requests_remaining`` / ``tokens_remaining`` ────────
NULL on either of these means "this entitlement does not meter this
dimension" -- e.g. a requests-only package leaves ``tokens_remaining`` NULL
forever, and :func:`consume_entitlement` never touches it. It is NOT
shorthand for "unlimited by omission": :func:`grant_entitlement` refuses to
create a row at all when a package's ``request_quota`` and ``token_quota``
are both NULL (i.e. the package grants no quota whatsoever), precisely to
avoid ever materializing an entitlement whose only two counters are both
NULL and would therefore look bottomless to :func:`consume_entitlement`'s
WHERE clause.

Money is an integer number of Toman throughout. No floats, ever, and never
a multiply/divide by 10 (that conversion belongs only inside a
payment-gateway adapter, nowhere near this module).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import sqlalchemy

from database import async_session

logger = logging.getLogger(__name__)


def _utcnow_naive() -> datetime:
    # The rest of the schema (created_at defaults, etc.) stores naive UTC
    # timestamps via Postgres `now()`; computing expires_at in Python needs
    # the same convention so comparisons against `now()` in SQL line up.
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── selection ────────────────────────────────────────────────────────────

# Selection rules, in the WHERE clause below:
#   * active must be true
#   * not expired (NULL expires_at = never expires)
#   * not exhausted on either metered dimension (NULL remaining = that
#     dimension isn't metered by this entitlement, so it can't be exhausted)
#   * max_cost_per_request_toman must be set AND cover the estimated cost --
#     a NULL ceiling is fail-closed, never treated as "no ceiling, allow it"
# Among the survivors, the one expiring soonest is preferred (NULLS LAST:
# an entitlement that never expires is the least urgent to spend first).
_FIND_COVERING_SQL = sqlalchemy.text(
    "SELECT id, user_id, package_id, requests_remaining, tokens_remaining, "
    "max_cost_per_request_toman, expires_at, active, source_payment_id, created_at "
    "FROM package_entitlement "
    "WHERE user_id = :uid "
    "AND active = true "
    "AND (expires_at IS NULL OR expires_at > now()) "
    "AND (requests_remaining IS NULL OR requests_remaining > 0) "
    "AND (tokens_remaining IS NULL OR tokens_remaining > 0) "
    "AND max_cost_per_request_toman IS NOT NULL "
    "AND max_cost_per_request_toman >= :est_cost_toman "
    "ORDER BY expires_at ASC NULLS LAST, id ASC "
    "LIMIT 1"
)


async def find_covering_entitlement(uid: int, est_cost_toman: int) -> Optional[dict]:
    """The best active entitlement that can cover a request of this
    estimated cost, or None.

    Returns at least {'id', 'requests_remaining', 'tokens_remaining',
    'max_cost_per_request_toman', 'expires_at'} when one is found.
    """
    est_cost_toman = int(est_cost_toman)
    if async_session is None:
        return None
    async with async_session() as session:
        res = await session.execute(_FIND_COVERING_SQL, {'uid': int(uid), 'est_cost_toman': est_cost_toman})
        row = res.fetchone()
        if row is None:
            return None
        return dict(row._mapping)


# ── consumption ──────────────────────────────────────────────────────────

# Atomic, race-safe decrement: a single conditional UPDATE that re-checks
# every guard (active, not expired, enough of each metered dimension left)
# against the row's CURRENT values at the moment Postgres takes the row
# lock for this statement -- not against a value read by this process
# earlier. Two concurrent callers racing to spend the last unit both issue
# this same UPDATE; Postgres serializes them via the row lock, so the
# second one to actually execute sees the FIRST one's already-decremented
# values in its own WHERE evaluation, not a stale snapshot. If that leaves
# too little remaining, the WHERE clause fails to match and RETURNING
# yields no row -- this is a plain read-then-write done entirely inside a
# single statement, so there is no window between "check" and "write" for
# a second transaction to land in.
#
# requests_remaining/tokens_remaining are only decremented when they are
# not NULL (a NULL dimension is not metered by this entitlement and must
# stay NULL forever, never drift to a negative number).
_CONSUME_SQL = sqlalchemy.text(
    "UPDATE package_entitlement SET "
    "requests_remaining = CASE WHEN requests_remaining IS NULL THEN NULL "
    "ELSE requests_remaining - :requests END, "
    "tokens_remaining = CASE WHEN tokens_remaining IS NULL THEN NULL "
    "ELSE tokens_remaining - :tokens END "
    "WHERE id = :id "
    "AND active = true "
    "AND (expires_at IS NULL OR expires_at > now()) "
    "AND (requests_remaining IS NULL OR requests_remaining >= :requests) "
    "AND (tokens_remaining IS NULL OR tokens_remaining >= :tokens) "
    "RETURNING id"
)


async def consume_entitlement(entitlement_id: int, *, requests: int = 1, tokens: int = 0) -> bool:
    """Atomically decrement an entitlement's remaining requests/tokens.

    Returns False if it could not be consumed (raced to zero, expired,
    deactivated) -- the caller must then fall back to the wallet. Never
    reads the row first: the guard and the write are the same statement.
    """
    requests = int(requests)
    tokens = int(tokens)
    if requests < 0 or tokens < 0:
        raise ValueError("requests/tokens must be non-negative")
    if async_session is None:
        return False
    async with async_session() as session:
        res = await session.execute(
            _CONSUME_SQL,
            {'id': int(entitlement_id), 'requests': requests, 'tokens': tokens},
        )
        row = res.fetchone()
        if row is None:
            await session.commit()
            return False
        await session.commit()
        return True


# ── granting ─────────────────────────────────────────────────────────────

_PACKAGE_QUOTA_SQL = sqlalchemy.text(
    "SELECT request_quota, token_quota, validity_days, max_cost_per_request_toman "
    "FROM credit_packages WHERE id = :package_id"
)

_INSERT_ENTITLEMENT_SQL = sqlalchemy.text(
    "INSERT INTO package_entitlement "
    "(user_id, package_id, requests_remaining, tokens_remaining, "
    "max_cost_per_request_toman, expires_at, active, source_payment_id) "
    "VALUES (:user_id, :package_id, :requests_remaining, :tokens_remaining, "
    ":max_cost_per_request_toman, :expires_at, true, :source_payment_id) "
    "RETURNING id, user_id, package_id, requests_remaining, tokens_remaining, "
    "max_cost_per_request_toman, expires_at, active, source_payment_id, created_at"
)


async def grant_entitlement(uid: int, package_id: str, *, source_payment_id: Optional[str] = None) -> Optional[dict]:
    """Create an entitlement from a package's quota columns.

    Returns None if the package grants no quota (``request_quota`` AND
    ``token_quota`` both NULL) -- that is the current state of every
    package, and it must be a clean no-op, not an error. Also returns None
    if the package_id does not exist at all (defensive; the caller is
    expected to have already validated the purchase against a real
    package).

    Quota values (and the ceiling) are copied onto the new row at grant
    time, so a later edit to the package's columns never changes what an
    already-granted entitlement allows.
    """
    if async_session is None:
        return None
    async with async_session() as session:
        res = await session.execute(_PACKAGE_QUOTA_SQL, {'package_id': package_id})
        pkg_row = res.fetchone()
        if pkg_row is None:
            return None
        pkg = dict(pkg_row._mapping)

        request_quota = pkg.get('request_quota')
        token_quota = pkg.get('token_quota')
        if request_quota is None and token_quota is None:
            # No quota configured on this package at all -- granting an
            # entitlement here would leave both remaining counters NULL,
            # which consume_entitlement() would treat as "not metered,
            # therefore unlimited" on both dimensions. That must never
            # happen implicitly, so this is a clean no-op instead.
            return None

        validity_days = pkg.get('validity_days')
        expires_at = None
        if validity_days is not None:
            expires_at = _utcnow_naive() + timedelta(days=int(validity_days))

        params = {
            'user_id': int(uid),
            'package_id': package_id,
            'requests_remaining': request_quota,
            'tokens_remaining': token_quota,
            'max_cost_per_request_toman': pkg.get('max_cost_per_request_toman'),
            'expires_at': expires_at,
            'source_payment_id': source_payment_id,
        }
        res = await session.execute(_INSERT_ENTITLEMENT_SQL, params)
        row = res.fetchone()
        await session.commit()
        if row is None:
            return None
        return dict(row._mapping)


# ── listing ──────────────────────────────────────────────────────────────

_LIST_SQL = sqlalchemy.text(
    "SELECT id, user_id, package_id, requests_remaining, tokens_remaining, "
    "max_cost_per_request_toman, expires_at, active, source_payment_id, created_at "
    "FROM package_entitlement "
    "WHERE user_id = :uid "
    "AND active = true "
    "AND (expires_at IS NULL OR expires_at > now()) "
    "ORDER BY created_at DESC"
)


async def list_entitlements(uid: int) -> list[dict]:
    """Active, non-expired entitlements for the user, for display.

    Deliberately does not filter out an exhausted-but-still-active
    entitlement (0 remaining) -- a user should still be able to see a
    package they bought and fully used; the request path's own
    find_covering_entitlement is what actually excludes it from routing.
    """
    if async_session is None:
        return []
    async with async_session() as session:
        res = await session.execute(_LIST_SQL, {'uid': int(uid)})
        return [dict(r._mapping) for r in res.fetchall()]
