"""Live candidate pool + rule-based model selection for Smart Mode.

This module is the replacement for the hardcoded model tuples in
chat_smart.py (`_FREE_MODELS`, `_CODING_MODELS`, `_REASONING_MODELS`,
`_CREATIVE_MODELS`, `_DEFAULT_MODEL`). All six ids those tuples name are
unservable today -- every category x balance combination landed on a model
that 404s upstream, which is how they took Smart Mode down in production
(fixed by the rescue path in chat_smart._select_smart_model_safe). The fix
is not a better hardcoded list: it is to stop hardcoding and ask the
catalog which models are actually available, actually priced, and actually
answered a probe.

Scope: pool + price bands + rule selection + cost estimate, plus combo
selection (`select_for_combo`, added later against the migration-0050
tables). The LLM-driven router is deliberately NOT here -- it is optional,
costs money per message, and lives in services/smart_router_llm.py so that
nothing on this rule-based path can be broken by it.

MONEY: every amount in this module is an integer number of Toman. There is
no float arithmetic anywhere and there must never be one -- see
services/money.py for why (a single /10 once showed a 9,995,511 Toman
balance as 995,551).

`chat` is imported plainly at module scope and every attribute is resolved
through `chat.<name>` at call time, exactly as chat_smart.py does it -- see
that module's docstring for why this is safe against the chat.py import
cycle and why late binding is required for the test monkeypatch contract.
`security` is imported the same way and reached as `security._get_redis()`
at call time, for the same monkeypatch reason -- see security_lockout.py.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import sqlalchemy

import chat
import security

logger = logging.getLogger('chat')  # same logger name as the rest of the chat path


@dataclass(frozen=True)
class Candidate:
    """One servable model: priced, public, and live-probed.

    `blended` is `3 * input + output` -- the same weighting
    chat_smart._cheapest_live_model already orders by, on the assumption
    that a chat request reads roughly three times more than it writes. It is
    a ranking key only, never a charge; real billing goes through
    services/billing.py on measured tokens.
    """
    provider_model_id: str
    public_id: str
    input_per_million: int
    output_per_million: int
    context_window: int
    upstream: str | None
    blended: int


# ── Candidate pool ───────────────────────────────────────────────────────

_POOL_CACHE_TTL_SECONDS = 60
_pool_cache: list[Candidate] = []
_pool_cache_at: float = 0.0

# Plain string literal, NOT an f-string and NOT assembled from parts --
# scripts/sql_schema_audit.py only EXPLAINs literals, and the pytest suite
# mocks the DB, so an f-string here would drop this query out of the audit
# and let a wrong column name survive all the way to production.
#
# Each of the five filters is load-bearing:
#   availability = 'available'    -- withdrawn models are not offered.
#   public_id IS NOT NULL         -- never hand a raw provider route to a
#                                    user; Smart Mode labels with public_id.
#   *_per_million > 0             -- NOT `IS NOT NULL`. Both columns are
#                                    NUMERIC NOT NULL DEFAULT 0, so an
#                                    unpriced row reads as 0 and would sort
#                                    as the cheapest thing in the catalog.
#                                    "No request may be loss-making" would
#                                    then break from behind: the router
#                                    would preferentially pick exactly the
#                                    models nobody has priced yet.
#   health_quarantined_at IS NULL -- a quarantined model is out, whatever
#                                    its last probe said (0029).
#   s.last_ok_at IS NOT NULL      -- NEVER `status = 'healthy'`:
#                                    _derive_status returned 'healthy' for
#                                    models whose every probe had failed
#                                    until it was fixed, and
#                                    last_verified_at is separately known to
#                                    lie. last_ok_at is the only column that
#                                    means "this model actually answered".
_POOL_SQL = sqlalchemy.text(
    "SELECT c.provider_model_id, c.public_id, c.input_per_million, "
    "c.output_per_million, c.context_window, c.upstream "
    "FROM model_catalog c "
    "JOIN model_health_state s "
    "ON s.model_id = c.id OR s.model_id = c.provider_model_id "
    "WHERE c.availability = 'available' AND c.public_id IS NOT NULL "
    "AND c.input_per_million > 0 AND c.output_per_million > 0 "
    "AND c.health_quarantined_at IS NULL "
    "AND s.last_ok_at IS NOT NULL "
    "ORDER BY (3 * c.input_per_million + c.output_per_million) ASC, "
    "c.context_window DESC, c.public_id ASC"
)


async def candidate_pool() -> list[Candidate]:
    """Every model Smart Mode is allowed to route to right now, cheapest
    blended price first. Cached `_POOL_CACHE_TTL_SECONDS`.

    NEVER raises. On any DB error the last good cache is returned (or `[]`
    if the cache is still cold) -- Smart Mode degrades to whatever it last
    knew rather than 500ing, and `select_by_rules` returns None on an empty
    pool so the caller can run its own fallback.

    The health join can in principle match twice for one catalog row (once
    on `c.id`, once on `c.provider_model_id`) if both keys have a health
    row. That is zero rows in production today, but a duplicate would skew
    the band percentiles, so rows are de-duplicated by `public_id` here --
    public_id is unique in model_catalog and the SQL already excludes NULLs.
    """
    global _pool_cache, _pool_cache_at
    if chat.async_session is None:
        return []
    now = time.monotonic()
    if _pool_cache_at and now - _pool_cache_at < _POOL_CACHE_TTL_SECONDS:
        return _pool_cache
    try:
        async with chat.async_session() as session:
            res = await session.execute(_POOL_SQL)
            rows = res.fetchall()
        pool: list[Candidate] = []
        seen: set[str] = set()
        for row in rows:
            public_id = str(row.public_id)
            if public_id in seen:
                continue
            seen.add(public_id)
            input_per_million = int(row.input_per_million)
            output_per_million = int(row.output_per_million)
            pool.append(Candidate(
                provider_model_id=str(row.provider_model_id),
                public_id=public_id,
                input_per_million=input_per_million,
                output_per_million=output_per_million,
                context_window=int(row.context_window or 0),
                upstream=row.upstream,
                blended=3 * input_per_million + output_per_million,
            ))
        _pool_cache = pool
        _pool_cache_at = now
    except Exception as e:
        logger.warning(f"candidate_pool DB read failed, keeping previous cache: {e}")
    return _pool_cache


# ── Price bands ──────────────────────────────────────────────────────────

# Percentile cut points, in percent. Integer arithmetic only: the index is
# computed as (n - 1) * pct // 100, so there is no float anywhere near a
# price.
_BAND_P33 = 33
_BAND_P67 = 67


def band_thresholds(pool: list[Candidate]) -> tuple[int, int]:
    """The 33rd and 67th percentile blended VALUES of the pool.

    Bands are by price value, never by row count. `ntile(3)` over the live
    pool split two models with the IDENTICAL blended price of 2,573,100
    into different bands purely by row order -- a tie is broken by whatever
    order the planner happened to emit, so the same model can change band
    when an unrelated row is added to the catalog. Returning threshold
    VALUES and comparing against them (see `band_of`) makes equal prices
    land in the same band, always.

    Returns `(0, 0)` for an empty pool, which puts nothing anywhere; callers
    check for an empty pool before they get here.
    """
    if not pool:
        return (0, 0)
    values = sorted(c.blended for c in pool)
    last = len(values) - 1
    return (values[(last * _BAND_P33) // 100], values[(last * _BAND_P67) // 100])


def band_of(c: Candidate, thresholds: tuple[int, int]) -> int:
    """1 = cheap, 2 = mid, 3 = high. Compares blended price against the
    threshold VALUES, so two candidates with equal blended price always get
    the same band."""
    p33, p67 = thresholds
    if c.blended <= p33:
        return 1
    if c.blended <= p67:
        return 2
    return 3


# ── Rule-based selection ─────────────────────────────────────────────────

# Below this balance the user gets the cheap band whatever they asked for.
# This is exactly today's behaviour in chat_smart._select_smart_model and
# the owner has confirmed it stays.
_LOW_BALANCE_TOMAN = 10_000

# Categories come from chat_smart._analyze_message; this mapping preserves
# what the hardcoded tuples meant (free -> cheap, coding/creative -> mid,
# reasoning/complex -> high). No new categories are invented here.
#
# NOTE, and do not re-open it: holding an active credit package does NOT
# earn a better band. Balance alone gates. services.user_quota.
# has_active_package is deliberately not imported -- switching on a tier
# branch for paying users is a product decision, not a refactor (see
# chat_smart._select_smart_model's docstring for the full history).
_BAND_BY_CATEGORY = {
    'greeting': 1,
    'simple': 1,
    'medium': 1,
    'code': 2,
    'creative': 2,
    'reasoning': 3,
    'complex': 3,
}


def _best_in(members: list[Candidate]) -> Candidate:
    """Largest context window, ties broken by public_id ascending. Fully
    deterministic: the same pool always yields the same pick."""
    return sorted(members, key=lambda c: (-c.context_window, c.public_id))[0]


def select_by_rules(category: str, balance: int, pool: list[Candidate]) -> Candidate | None:
    """Pick one candidate for a classified message. Never raises; returns
    None only when there is nothing to pick from, in which case the caller
    runs its own fallback.

    An empty target band falls back to the next CHEAPER band and then to
    band 1 -- never upward. Routing a user to a costlier model than the rule
    asked for, because the band they were entitled to happened to be empty,
    is the wrong direction to fail in.
    """
    try:
        if not pool:
            return None
        broke = balance < _LOW_BALANCE_TOMAN
        want = 1 if broke else _BAND_BY_CATEGORY.get(category, 1)
        thresholds = band_thresholds(pool)
        banded: dict[int, list[Candidate]] = {}
        for c in pool:
            banded.setdefault(band_of(c, thresholds), []).append(c)
        for band in range(want, 0, -1):
            members = banded.get(band)
            if members:
                # A user under the floor gets the CHEAPEST member, not the
                # roomiest one. Band 1 spans a real spread -- measured live
                # it runs 49,556 to 428,850 blended, so `_best_in`'s
                # largest-context rule hands the near-empty wallet the
                # priciest model in the band, 8.6x the cheapest. Today's
                # production behaviour for balance < 10,000 is the cheapest
                # model outright, so picking on context here would be a
                # silent regression aimed squarely at the users who can
                # least absorb it. Above the floor, roomiest-in-band stands:
                # the band already bounds the cost.
                if broke:
                    return sorted(members, key=lambda c: (c.blended, c.public_id))[0]
                return _best_in(members)
        # Unreachable while band_of is total over 1..3 (the cheapest member
        # of a non-empty pool is always <= p33, so band 1 is never empty),
        # but a pick from the whole pool beats returning None to a caller
        # that has candidates in hand.
        return _best_in(pool)
    except Exception as e:
        logger.warning(f"select_by_rules failed category={category}: {e}")
        return None


# ── Cost estimate ────────────────────────────────────────────────────────

# A representative Smart Mode turn, used only to show/compare an expected
# price. Real charges are metered per response by services/billing.py.
_ESTIMATE_INPUT_TOKENS = 2000
_ESTIMATE_OUTPUT_TOKENS = 800
_ESTIMATE_FLOOR_TOMAN = 1000


def estimate_cost_toman(c: Candidate) -> int:
    """Expected cost of one representative request, in integer Toman.

    Integer floor division only -- never float, never a /10 rial detour.
    Floored at `_ESTIMATE_FLOOR_TOMAN` so a very cheap model never estimates
    at 0, which would read as "free" and there are no free models.
    """
    return max(
        _ESTIMATE_FLOOR_TOMAN,
        (_ESTIMATE_INPUT_TOKENS * c.input_per_million
         + _ESTIMATE_OUTPUT_TOKENS * c.output_per_million) // 1_000_000,
    )


# ── Combo selection ──────────────────────────────────────────────────────

# Plain string literal for the same reason as _POOL_SQL above -- an f-string
# would drop this statement out of scripts/sql_schema_audit.py, and both
# tables exist in production (migration 0050) so the auditor really does
# EXPLAIN it.
#
# Every clause of the WHERE is load-bearing:
#   c.id = :combo_id AND c.user_id = :uid -- ownership is enforced IN THE
#       QUERY, exactly as combos._fetch_combo does it: a combo belonging to
#       another user comes back as zero rows, indistinguishable from an id
#       that does not exist. Selecting first and comparing user_id in Python
#       would be one forgotten branch away from routing on someone else's
#       combo.
#   c.enabled = true              -- a disabled combo is not a combo; the
#                                    caller must fall back to select_by_rules.
# LEFT JOIN, not JOIN: a combo with no items still returns one row, so the
# policy is readable and "combo exists but is empty" stays distinguishable
# from "no such combo" in the log. Both end up returning None.
_COMBO_SQL = sqlalchemy.text(
    "SELECT c.policy, i.position, i.model_public_id "
    "FROM user_model_combo c "
    "LEFT JOIN user_model_combo_item i ON i.combo_id = c.id "
    "WHERE c.id = :combo_id AND c.user_id = :uid AND c.enabled = true "
    "ORDER BY i.position"
)

# Rotation counter for the round_robin policy. Per combo, not per user: the
# combo is what is being rotated through.
_COMBO_RR_KEY = 'smart:combo_rr:{}'


async def _combo_rr_index(combo_id: int, count: int) -> int:
    """Next index for a round_robin combo, or 0 when Redis cannot answer.

    Reached through `security._get_redis()` AT CALL TIME, never via `from
    security import _get_redis` -- tests monkeypatch `security._get_redis`
    directly and a module-level binding here would freeze the pre-patch
    function object (see security_lockout.py's IMPORT/MONKEYPATCH CONTRACT).

    DEGRADES TO SEQUENTIAL (index 0) on any Redis trouble instead of
    propagating. A rotation counter is a nicety; failing a chat request
    because a counter was unreachable would trade the whole feature for it.
    """
    try:
        counter = int(await security._get_redis().incr(_COMBO_RR_KEY.format(combo_id)))
        return counter % count
    except Exception as e:
        logger.warning(
            f"combo round-robin counter unavailable combo_id={combo_id}, "
            f"falling back to sequential: {e}"
        )
        return 0


async def select_for_combo(uid: int, combo_id: int, pool: list[Candidate]) -> Candidate | None:
    """Pick one candidate from a user's saved combo, or None.

    None means "this combo cannot serve the request" -- unknown id, someone
    else's combo, disabled, empty, or every item dead -- and the caller
    falls back to `select_by_rules`. Never raises.

    DEAD ENTRIES ARE SKIPPED, NEVER FATAL. Items store the PUBLIC id the
    user picked (`sanjab/...`, see combos.py); models get withdrawn,
    quarantined or unpriced afterwards, at which point the saved id either
    stops resolving or resolves to something no longer in the pool. A saved
    combo has to degrade to its surviving members, not break, or one
    withdrawn model would silently disable every combo that named it.
    """
    try:
        if not pool or chat.async_session is None:
            return None
        async with chat.async_session() as session:
            res = await session.execute(_COMBO_SQL, {'combo_id': combo_id, 'uid': uid})
            rows = res.fetchall()
        if not rows:
            return None

        policy = rows[0].policy
        # provider_model_id is what _resolve_public_model canonicalizes to
        # and what the pool is keyed on for routing/health/billing.
        by_route = {c.provider_model_id: c for c in pool}
        healthy: list[Candidate] = []
        for row in rows:
            public_id = row.model_public_id
            if not public_id:
                continue  # LEFT JOIN filler row: the combo has no items
            resolved = await chat._resolve_public_model(public_id)
            candidate = by_route.get(resolved) if resolved else None
            if candidate is None:
                logger.info(
                    f"select_for_combo skipping dead item combo_id={combo_id} "
                    f"model={public_id!r}: not in the servable pool"
                )
                continue
            healthy.append(candidate)

        if not healthy:
            logger.info(
                f"select_for_combo found no live member combo_id={combo_id} uid={uid}"
            )
            return None
        if policy == 'round_robin':
            return healthy[await _combo_rr_index(combo_id, len(healthy))]
        return healthy[0]
    except Exception as e:
        logger.warning(f"select_for_combo failed uid={uid} combo_id={combo_id}: {e}")
        return None
