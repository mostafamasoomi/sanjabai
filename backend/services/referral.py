"""Referral rewards: pay an inviter (and, optionally, the invitee) a bonus
the moment the INVITEE's first payment succeeds -- never at signup.

See migrations/0051_referral_rewards.sql for the schema (`referral_reward`,
one row per (inviter, invitee) pair) and the three `app_setting` numbers
this module reads.

── Owner decision, 2026-08-28, not up for re-litigation here ─────────────
Paying a referral reward at signup was refused because this server has no
way to tell a real signup from a scripted one at that point in time:
`models/_users.py` has no email-verification column, the signup rate
limiter's key is `sha256(ip + user-agent)` (security.py:106-126, beaten by
rotating the User-Agent header), and the disposable-email blocklist
(security.py:306) covers four domains. Under those three facts, crediting a
wallet at signup is free money for a loop. The invitee's first successful
payment is an external, costly event a script cannot fabricate, so that is
the only trigger this module honours. **The signup path
(auth.py::signup) must stay wallet-credit-free -- record_attribution()
below only ever writes a 'pending' row, never touches a wallet.**

── Two functions, two very different failure contracts ───────────────────
record_attribution() runs on the signup hot path (auth.py) and therefore
must NEVER raise -- a referral bookkeeping failure must not turn into a
failed signup. settle_on_first_payment() runs from the payment callback
(payment_endpoints.py) AFTER the user has already been told their payment
succeeded, so it must also never raise -- see that call site's own
try/except for why (defence in depth, matching the existing
grant_for_payment() pattern in services/entitlement_gate.py).

── Config caching (copied from services/free_tier_config.py) ─────────────
Same idiom, same TTL, same fail-safe-to-defaults contract, because this is
also read on a request path (the payment callback) and must degrade to
"feature off" rather than raise if app_setting is briefly unreadable.

── The only sanctioned credit path ────────────────────────────────────────
settle_on_first_payment() is the ONLY place in this module (and, by
tests/test_credit_paths.py's allowlist, the only place outside
payment.py/admin_user_ops.py/services/billing.py anywhere in the backend)
that calls services.billing.credit_wallet(). Two independent calls, one per
leg (inviter, invitee), each with its own stable idempotency_key, so a
retry/replay of the settle path can never double-pay either side even if
the row-status guard below were somehow raced.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import sqlalchemy

from database import async_session
from services.billing import SqlBillingRepo, credit_wallet
from services.money import Money

logger = logging.getLogger(__name__)

# Fail-safe defaults. MUST equal the seeds in migration 0051 so behaviour
# before and after that migration is identical until an admin changes a
# value. All-zero amounts mean "feature off" -- see settle_on_first_payment.
DEFAULT_INVITER_REWARD_TOMAN = 0
DEFAULT_INVITEE_REWARD_TOMAN = 0
DEFAULT_REWARD_CAP = 10

_KEYS = ('referral_reward_toman', 'referral_invitee_reward_toman', 'referral_reward_cap')
_DEFAULTS = {
    'referral_reward_toman': DEFAULT_INVITER_REWARD_TOMAN,
    'referral_invitee_reward_toman': DEFAULT_INVITEE_REWARD_TOMAN,
    'referral_reward_cap': DEFAULT_REWARD_CAP,
}

_CACHE_TTL = 60  # seconds
_cache: Optional[dict[str, int]] = None
_cache_at: float = 0.0

_SELECT_SETTINGS_SQL = sqlalchemy.text(
    'SELECT key AS setting_key, value FROM app_setting WHERE key = ANY(:keys)'
)


def invalidate() -> None:
    """Drop the config cache so the next read reflects a just-written admin
    change (admin_referral.py calls this after a successful write)."""
    global _cache, _cache_at
    _cache = None
    _cache_at = 0.0


def _coerce_int(value, fallback: int) -> int:
    """app_setting.value is JSONB. A number comes back as int/float; a
    string (some rows historically store JSON strings) is parsed. Anything
    that will not become a non-negative int falls back to the seeded
    default rather than poisoning payout math with a bad number."""
    try:
        if isinstance(value, str):
            value = json.loads(value)
        n = int(value)
        return n if n >= 0 else fallback
    except Exception:
        return fallback


async def _load() -> dict[str, int]:
    """Read all three values from app_setting, each falling back to its
    default if its row is missing or malformed. Never raises."""
    result = dict(_DEFAULTS)
    try:
        if async_session is None:
            return result
        async with async_session() as session:
            res = await session.execute(_SELECT_SETTINGS_SQL, {'keys': list(_KEYS)})
            for row in res.fetchall():
                m = row._mapping
                key = m['setting_key']
                if key in _DEFAULTS:
                    result[key] = _coerce_int(m['value'], _DEFAULTS[key])
    except Exception as e:
        logger.warning(f"referral config load failed, using defaults: {e}")
        return dict(_DEFAULTS)
    return result


async def config() -> dict[str, int]:
    """The three referral numbers, cached for 60s. Always returns a
    complete dict with every key present (defaults fill any gap). Never
    raises."""
    global _cache, _cache_at
    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < _CACHE_TTL:
        return _cache
    loaded = await _load()
    _cache = loaded
    _cache_at = now
    return loaded


# ── attribution (signup path) ──────────────────────────────────────────────

_INSERT_ATTRIBUTION_SQL = sqlalchemy.text(
    "INSERT INTO referral_reward (inviter_id, invitee_id, status) "
    "VALUES (:inviter_id, :invitee_id, 'pending') "
    "ON CONFLICT (invitee_id) DO NOTHING"
)


async def record_attribution(session, inviter_id: int, invitee_id: int) -> None:
    """Record that ``inviter_id`` referred ``invitee_id``, as a 'pending'
    row -- no wallet is touched here, ever (see module docstring).

    Self-referral (inviter_id == invitee_id) writes nothing. A user who was
    already attributed to someone (an earlier signup, or a second referral
    link click before that account existed some other way) is left alone:
    ON CONFLICT (invitee_id) DO NOTHING makes a duplicate attempt a no-op,
    matching invitee_id's UNIQUE constraint in migration 0051 -- a user is
    invited at most once, ever.

    Never raises: a referral bookkeeping failure must not fail a signup.
    Commits on the session it was given so the caller does not have to
    remember to.
    """
    try:
        if inviter_id == invitee_id:
            return
        await session.execute(
            _INSERT_ATTRIBUTION_SQL,
            {'inviter_id': int(inviter_id), 'invitee_id': int(invitee_id)},
        )
        await session.commit()
    except Exception as e:
        logger.error(
            f"referral.record_attribution failed inviter={inviter_id} "
            f"invitee={invitee_id}: {e}"
        )


# ── settlement (first-payment path) ────────────────────────────────────────

_SELECT_PENDING_SQL = sqlalchemy.text(
    "SELECT id, inviter_id, invitee_id FROM referral_reward "
    "WHERE invitee_id = :invitee_id AND status = 'pending'"
)

_COUNT_PAID_SQL = sqlalchemy.text(
    "SELECT count(*) AS c FROM referral_reward "
    "WHERE inviter_id = :inviter_id AND status = 'paid'"
)

_MARK_CAPPED_SQL = sqlalchemy.text(
    "UPDATE referral_reward SET status = 'capped' "
    "WHERE id = :id AND status = 'pending'"
)

_MARK_PAID_SQL = sqlalchemy.text(
    "UPDATE referral_reward SET status = 'paid', paid_at = now(), "
    "inviter_amount_toman = :inviter_amount, invitee_amount_toman = :invitee_amount "
    "WHERE id = :id AND status = 'pending'"
)


async def settle_on_first_payment(user_id: int) -> Optional[dict]:
    """Pay out the referral reward for ``user_id``'s (the invitee's) FIRST
    successful payment. Idempotent, fail-safe, and never raises -- this is
    called from payment_endpoints.py AFTER the user has already been told
    their payment succeeded, so a bug here must never surface as an error
    to anyone.

    Returns None when there is nothing to do: no pending attribution for
    this invitee (never referred, or already settled by an earlier call),
    or the feature is off (both configured amounts are zero -- the row is
    left 'pending' untouched so a later admin turning the feature on can
    still pay it, since 'pending' is not 'expired').

    Returns a dict on every outcome that DID touch the row:
      {'capped': True, 'inviter_id': ..., 'invitee_id': ...}
        -- the invitee paid, but the inviter already has
        referral_reward_cap paid referrals; row -> 'capped', nothing
        credited.
      {'capped': False, 'inviter_id': ..., 'invitee_id': ...,
       'inviter_amount_toman': ..., 'invitee_amount_toman': ...}
        -- one or both legs were credited; row -> 'paid'.
    """
    try:
        if async_session is None:
            return None
        async with async_session() as session:
            res = await session.execute(_SELECT_PENDING_SQL, {'invitee_id': int(user_id)})
            row = res.fetchone()
            if row is None:
                return None
            reward_id = row.id
            inviter_id = row.inviter_id
            invitee_id = row.invitee_id

            cfg = await config()
            inviter_amount = int(cfg['referral_reward_toman'])
            invitee_amount = int(cfg['referral_invitee_reward_toman'])
            cap = int(cfg['referral_reward_cap'])

            if inviter_amount <= 0 and invitee_amount <= 0:
                # Feature off. Row stays 'pending' -- an admin turning the
                # reward on later can still pay this exact attribution.
                return None

            count_res = await session.execute(_COUNT_PAID_SQL, {'inviter_id': inviter_id})
            paid_count = count_res.fetchone().c
            if paid_count >= cap:
                await session.execute(_MARK_CAPPED_SQL, {'id': reward_id})
                await session.commit()
                return {'capped': True, 'inviter_id': inviter_id, 'invitee_id': invitee_id}

            repo = SqlBillingRepo(session)
            if inviter_amount > 0:
                await credit_wallet(
                    repo, inviter_id, Money(inviter_amount),
                    reason=f'پاداش دعوت — کاربر #{invitee_id} اولین پرداخت را انجام داد',
                    idempotency_key=f'referral:inviter:{inviter_id}:{invitee_id}',
                    txn_type='referral_bonus',
                )
            if invitee_amount > 0:
                await credit_wallet(
                    repo, invitee_id, Money(invitee_amount),
                    reason='پاداش خوش‌آمدگویی دعوت — اولین پرداخت شما',
                    idempotency_key=f'referral:invitee:{invitee_id}',
                    txn_type='referral_bonus',
                )

            await session.execute(_MARK_PAID_SQL, {
                'id': reward_id,
                'inviter_amount': inviter_amount,
                'invitee_amount': invitee_amount,
            })
            await session.commit()
            return {
                'capped': False,
                'inviter_id': inviter_id,
                'invitee_id': invitee_id,
                'inviter_amount_toman': inviter_amount,
                'invitee_amount_toman': invitee_amount,
            }
    except Exception as e:
        logger.error(f"referral.settle_on_first_payment failed user_id={user_id}: {e}")
        return None


# ── stats (surfaced by GET /referral/stats) ─────────────────────────────────

_STATS_SQL = sqlalchemy.text(
    "SELECT "
    "count(*) AS referral_count, "
    "count(*) FILTER (WHERE status = 'paid') AS paid_count, "
    "count(*) FILTER (WHERE status = 'pending') AS pending_count, "
    "COALESCE(SUM(inviter_amount_toman) FILTER (WHERE status = 'paid'), 0) AS total_bonus_toman "
    "FROM referral_reward WHERE inviter_id = :inviter_id"
)

_STATS_FALLBACK = {
    'referral_count': 0, 'paid_count': 0, 'pending_count': 0, 'total_bonus_toman': 0,
}


async def stats(user_id: int) -> dict:
    """This user's referral counts and the total inviter-side bonus they
    have actually been paid. Fails safe to all-zero (never raises) so a
    stats read can never take down the profile/referral endpoint."""
    try:
        if async_session is None:
            return dict(_STATS_FALLBACK)
        async with async_session() as session:
            res = await session.execute(_STATS_SQL, {'inviter_id': int(user_id)})
            row = res.fetchone()
            if row is None:
                return dict(_STATS_FALLBACK)
            m = row._mapping
            return {
                'referral_count': int(m['referral_count'] or 0),
                'paid_count': int(m['paid_count'] or 0),
                'pending_count': int(m['pending_count'] or 0),
                'total_bonus_toman': int(m['total_bonus_toman'] or 0),
            }
    except Exception as e:
        logger.warning(f"referral.stats failed user_id={user_id}: {e}")
        return dict(_STATS_FALLBACK)
