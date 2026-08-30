"""Referral rewards: pay the invitee a welcome bonus at signup, and pay the
inviter (and, historically, the invitee too) when the INVITEE's first
payment succeeds.

See migrations/0051_referral_rewards.sql for the schema (`referral_reward`,
one row per (inviter, invitee) pair) and the three `app_setting` numbers
this module reads.

── Owner decision, 2026-08-30, supersedes the 2026-08-28 decision below ──
The invitee-side bonus is now paid IMMEDIATELY at signup, not deferred to
first payment. The free-money-farm risk documented below (no email
verification, a beatable rate-limiter key, a four-domain disposable-email
blocklist) is explicitly OWNER-ACCEPTED for this leg -- do not reintroduce
a verification gate here without a new owner decision. `auth.py::signup`
now calls `credit_invitee_signup_reward()` (below) right after
`record_attribution()`, in the same referrer-exists branch. The INVITER
leg is unaffected by this change and still only pays out on the invitee's
first successful payment (`settle_on_first_payment()`), because paying an
inviter at signup time -- before the referral has cost the platform
anything real -- was never the question the owner revisited.

Both the signup credit and the settle credit target the invitee with the
exact same idempotency_key (`referral:invitee:{invitee_id}`), so
`services.billing.credit_wallet()`'s own idempotency guard makes a
double-pay of the invitee structurally impossible even if some future call
site forgot the row-status bookkeeping entirely. `settle_on_first_payment()`
additionally treats a non-zero `invitee_amount_toman` already on the row as
"this leg was paid at signup" and skips crediting it again, preserving the
signup-time amount in that column instead of recomputing it from
(possibly since-changed) config -- see that function's docstring.

── Original 2026-08-28 decision (invitee leg only, now superseded above) ──
Paying a referral reward at signup was refused because this server has no
way to tell a real signup from a scripted one at that point in time:
`models/_users.py` has no email-verification column, the signup rate
limiter's key is `sha256(ip + user-agent)` (security.py:106-126, beaten by
rotating the User-Agent header), and the disposable-email blocklist
(security.py:306) covers four domains. Under those three facts, crediting a
wallet at signup is free money for a loop. That risk analysis still stands
as a fact about this server; the owner reviewed it on 2026-08-30 and
decided to accept it for the invitee leg specifically, in exchange for the
growth benefit of an immediate reward. The INVITER leg's trigger (the
invitee's first successful payment, an external event a script cannot
fabricate) is untouched.

── Three functions, three very different failure contracts ───────────────
record_attribution() and credit_invitee_signup_reward() both run on the
signup hot path (auth.py) and therefore must NEVER raise -- a referral
bookkeeping or crediting failure must not turn into a failed signup.
settle_on_first_payment() runs from the payment callback
(payment_endpoints.py) AFTER the user has already been told their payment
succeeded, so it must also never raise -- see that call site's own
try/except for why (defence in depth, matching the existing
grant_for_payment() pattern in services/entitlement_gate.py).

── Config caching (copied from services/free_tier_config.py) ─────────────
Same idiom, same TTL, same fail-safe-to-defaults contract, because this is
also read on a request path (the payment callback, and now the signup
path too) and must degrade to "feature off" rather than raise if
app_setting is briefly unreadable.

── The only sanctioned credit path ────────────────────────────────────────
credit_invitee_signup_reward() and settle_on_first_payment() are the ONLY
places in this module (and, by tests/test_credit_paths.py's allowlist, the
only places outside payment.py/admin_user_ops.py/services/billing.py
anywhere in the backend) that call services.billing.credit_wallet(). Every
call carries its own stable idempotency_key -- the invitee's key is shared
between the two functions on purpose (see above) -- so a retry/replay of
either path can never double-pay any leg even if the row-status guard
below were somehow raced.
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
    row -- no wallet is touched HERE, ever. (The caller, auth.py, calls
    ``credit_invitee_signup_reward()`` below separately, right after this,
    for the invitee's signup bonus -- see module docstring.)

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


# ── signup-time invitee bonus (owner decision 2026-08-30) ──────────────────

_MARK_SIGNUP_INVITEE_PAID_SQL = sqlalchemy.text(
    "UPDATE referral_reward SET invitee_amount_toman = :amount "
    "WHERE invitee_id = :invitee_id AND status = 'pending' AND invitee_amount_toman = 0"
)


async def credit_invitee_signup_reward(session, invitee_id: int) -> Optional[dict]:
    """Credit the invitee's welcome bonus immediately at signup.

    Called from auth.py's signup handler right after ``record_attribution``,
    on the same session, only in the branch where a referrer was actually
    resolved -- see module docstring for the 2026-08-30 owner decision that
    moved this leg off the "only on first payment" trigger.

    Reads ``referral_invitee_reward_toman`` fresh (through the shared 60s
    cache); a value of 0 or less (the feature-off / unconfigured state) is a
    silent no-op -- no wallet touch, no row write.

    Otherwise credits ``invitee_id`` via the SAME idempotency key
    ``settle_on_first_payment`` uses for the invitee leg
    (``referral:invitee:{invitee_id}``), so ``credit_wallet``'s own
    idempotency guard makes it structurally impossible for this call and a
    later ``settle_on_first_payment`` call to both pay the invitee -- see
    that function's own skip-if-already-signup-paid logic for the second,
    row-level layer of the same guarantee.

    Also stamps ``invitee_amount_toman`` on the pending ``referral_reward``
    row (guarded so it only ever fires once, on a still-'pending', still-
    zero row) so ``settle_on_first_payment`` can see this leg was already
    paid and skip it, and so the amount that actually landed is preserved
    even if an admin edits the setting before the inviter's leg settles --
    row ``status`` itself is deliberately left 'pending': the INVITER leg is
    unresolved and marking the whole row 'paid' here would let
    settle_on_first_payment's `SELECT ... WHERE status = 'pending'` miss it
    forever, permanently stranding the inviter's reward.

    Never raises: this runs on the signup hot path, same contract as
    ``record_attribution``. Commits on the session it was given.
    """
    try:
        cfg = await config()
        amount = int(cfg.get('referral_invitee_reward_toman', 0))
        if amount <= 0:
            return None
        repo = SqlBillingRepo(session)
        await credit_wallet(
            repo, invitee_id, Money(amount),
            reason='پاداش خوش‌آمدگویی دعوت',
            idempotency_key=f'referral:invitee:{invitee_id}',
            txn_type='referral_bonus',
        )
        await session.execute(
            _MARK_SIGNUP_INVITEE_PAID_SQL,
            {'invitee_id': int(invitee_id), 'amount': amount},
        )
        await session.commit()
        return {'invitee_id': invitee_id, 'invitee_amount_toman': amount}
    except Exception as e:
        logger.error(
            f"referral.credit_invitee_signup_reward failed invitee_id={invitee_id}: {e}"
        )
        return None


# ── settlement (first-payment path) ────────────────────────────────────────

_SELECT_PENDING_SQL = sqlalchemy.text(
    "SELECT id, inviter_id, invitee_id, invitee_amount_toman FROM referral_reward "
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
        -- one or both legs were credited (or the invitee leg was already
        credited at signup -- see below); row -> 'paid'.

    ── SINGLE-PAY (owner decision 2026-08-30) ──────────────────────────────
    The invitee leg may already have been paid at signup by
    ``credit_invitee_signup_reward()``. This function detects that by
    reading the row's own ``invitee_amount_toman``: a non-zero value means
    that leg already landed, so it is NOT recredited here (``credit_wallet``
    would no-op it anyway via the shared idempotency key -- this is the
    row-level half of that same guarantee, not a substitute for it) and the
    row is closed out with the AMOUNT THAT ACTUALLY LANDED AT SIGNUP, not
    whatever ``referral_invitee_reward_toman`` reads as right now (an admin
    may have changed it in between). The inviter leg is completely
    unaffected by any of this -- it still only ever pays here.
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
            # Non-zero here means credit_invitee_signup_reward() already paid
            # this leg at signup -- preserve that landed amount, don't
            # recredit and don't recompute it from (possibly changed) config.
            signup_invitee_amount = int(getattr(row, 'invitee_amount_toman', 0) or 0)
            invitee_already_paid = signup_invitee_amount > 0

            cfg = await config()
            inviter_amount = int(cfg['referral_reward_toman'])
            invitee_amount = (
                signup_invitee_amount if invitee_already_paid
                else int(cfg['referral_invitee_reward_toman'])
            )
            cap = int(cfg['referral_reward_cap'])

            if inviter_amount <= 0 and invitee_amount <= 0:
                # Feature off, and this leg was never paid at signup either.
                # Row stays 'pending' -- an admin turning the reward on
                # later can still pay this exact attribution.
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
            if invitee_amount > 0 and not invitee_already_paid:
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
