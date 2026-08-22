"""Logical-model routing resolver (Phase 6 / Phase C part 2).

Answers exactly one question: given a *logical* model key (``logical_model.
key``), which *physical* ``model_catalog`` row should a request actually be
sent to right now?

Nothing on the chat path calls this module yet. It is built and tested in
isolation, ready to be wired in behind an off-by-default flag by a later
change. Every guarantee below assumes that isolation: this module never
raises, never blocks chat, and a caller that ignores its return value and
keeps doing what it does today loses nothing.

── Data model (see migrations/0025_logical_models.sql) ─────────────────────
``logical_model`` -- one row per user-visible model key. Carries
``availability`` (available/degraded/maintenance/disabled) and a
``routing_policy`` (cheapest_healthy/priority/pinned).

``logical_model_candidate`` -- N physical ``model_catalog`` rows proposed
as backing a logical key. Carries ``state`` (proposed/approved/rejected)
and ``enabled``. Measured on production today: 449 logical models, 1154
candidates, only 100 ``approved`` -- the other 1054 are ``proposed`` and
were deliberately held back for admin review (many flagged by the
clusterer for a price or context mismatch). A ``proposed`` candidate is
never eligible for routing; approving it is a human decision this module
does not make.

Also measured today: every logical model's ``availability`` is
``maintenance``. Nothing this module resolves is currently user-visible.

── Eligibility (all three routing policies) ─────────────────────────────────
A candidate is only ever considered if, simultaneously:
  1. ``logical_model_candidate.state = 'approved'``
  2. ``logical_model_candidate.enabled = true``
  3. its ``model_catalog`` row has ``availability = 'available'``
The query (``_QUERY``) deliberately fetches every candidate row for the
key, filtered or not, and all three checks are applied afterwards in
:func:`_is_eligible`. That is a deliberate choice, not a shortcut: with the
filters folded into the SQL itself, breaking one of them (a bad JOIN
condition, a flipped boolean) could not be caught without a live database,
and this project runs its test suite against a mocked one. Keeping the
gate as explicit Python means the exact hazards this module exists to
prevent -- a ``proposed`` row leaking through, a ``disabled`` catalog row
being routed to -- are each provably tested (see the mutation-testing
evidence in the accompanying report for tests/test_model_resolver.py).

── Pricing and the "unpriced" hazard ────────────────────────────────────────
``model_catalog.input_per_million`` / ``output_per_million`` are integer
toman (NOT floats -- see the project-wide money rule). A row with either
column at its default of 0 is not a bargain, it is *unpriced*: nobody has
confirmed what it actually costs. Ranking naively by price would sort
every unpriced row to the very top and route every request to the one
model whose cost is unknown -- the opposite of "cheapest". So for
``cheapest_healthy`` an unpriced candidate is scored at
``_UNPRICED_CEILING``, a large plain ``int`` sentinel (not ``float('inf')``
-- money math in this project never touches floats, not even as a
sentinel): it can still be picked if it is the *only* eligible candidate,
but it can never out-rank a genuinely priced one. ``priority`` and
``pinned`` do not consider price at all, so this hazard does not apply to
them.

── HONEST CAVEAT: cheapest_healthy is not a live cost optimisation today ────
Measured against production ``usage_events`` on 2026-08-22: per-route
input-token counts are nearly identical (ag averages 2850 tokens,
gemini-api 2814) -- route-level token overhead does not explain the cost
spread the roadmap attributes to routing. And a full scan of
``model_catalog`` today finds **zero** genuinely priced, cheaper
alternatives for any currently-served model -- the only rows that look
"cheaper" are unpriced ones sitting in ``maintenance``, which the ceiling
rule above excludes from ever winning. So ``cheapest_healthy`` has nothing
to save right now. It exists so that the day a second priced, healthy
candidate shows up for some key, the resolver is already correct -- not as
a claim that it is saving money today.

── routing_policy semantics ─────────────────────────────────────────────────
* ``pinned`` -- use ``logical_model.pinned_candidate_id`` (a
  ``model_catalog.id``) *only if* it is present among the eligible
  candidates computed above. If it is not (unset, rejected, disabled, or
  its catalog row went unhealthy), this returns ``None`` and logs a
  warning -- it never silently substitutes a different model for one an
  admin deliberately pinned.
* ``priority`` -- lowest ``logical_model_candidate.priority`` wins.
* ``cheapest_healthy`` -- lowest effective price (see above) wins.
* Any policy value outside these three (should be impossible; the column
  has a CHECK constraint) resolves to ``None``.

── Tie-break rule (deterministic, documented once, used everywhere) ────────
Ties are broken by ascending ``catalog_id`` (a plain Python string
comparison) as the final tiebreaker. For ``cheapest_healthy``, candidate
``priority`` is the tiebreaker tried *before* ``catalog_id`` (lower
priority number wins), so two equally-priced candidates fall back to
whichever one an admin ranked higher. This makes the resolver a pure
function of its inputs -- same DB state in, same answer out, always.

If ``logical_model.availability`` is not ``'available'``, this resolves to
``None`` regardless of routing_policy -- a degraded/maintenance/disabled
logical model has nothing to route to.

── Fail-safe contract ───────────────────────────────────────────────────────
:func:`resolve_logical_model` never raises. Any Redis error, DB error,
missing row, empty candidate set, or malformed cached value returns
``None``. Every caller is expected to treat ``None`` as "fall back to
today's direct (non-logical) behaviour" -- so ``None`` must always be a
safe answer, and it is by construction here: it is both the default on
every error path and the correct answer for "there is nothing to route
to yet" (every logical model is in maintenance today).

── Caching ───────────────────────────────────────────────────────────────
Follows the idiom in ``backend/site_settings.py``: Redis-cached with a
30-second TTL (this module's brief, distinct from site_settings' own 30s
which is coincidental -- read that module for the fuller rationale of the
pattern). A definitive resolution -- including a definitive ``None``, e.g.
"this logical model is in maintenance" -- is cached, because it is real
DB-derived truth as of the read. A *failure* to reach Redis or Postgres is
never cached: on error this returns ``None`` immediately without writing
anything, so a transient outage cannot freeze a stale wrong answer in
place for the next 30 seconds. A cached value that is not exactly a JSON
``null`` or a non-empty JSON string is treated as corrupt and ignored (a
cache miss, not a trusted answer) -- see :func:`_coerce_cached_resolution`,
the same hazard ``site_settings._coerce_flag`` guards against.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import sqlalchemy

from database import async_session, rds

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 30
_CACHE_PREFIX = 'cache:model_resolver:'

# A plain int sentinel (never a float -- money is never a float in this
# project) larger than any real toman price could plausibly be, used to
# rank unpriced candidates dead last in cheapest_healthy without ever
# excluding them outright (they remain valid if they are the only option).
_UNPRICED_CEILING = 2**62

_QUERY = sqlalchemy.text(
    """
    SELECT
        lm.availability         AS lm_availability,
        lm.routing_policy       AS lm_routing_policy,
        lm.pinned_candidate_id  AS lm_pinned_candidate_id,
        lmc.catalog_id          AS catalog_id,
        lmc.priority            AS priority,
        lmc.state               AS candidate_state,
        lmc.enabled              AS candidate_enabled,
        mc.availability           AS catalog_availability,
        mc.input_per_million      AS input_per_million,
        mc.output_per_million     AS output_per_million
    FROM logical_model lm
    LEFT JOIN logical_model_candidate lmc
           ON lmc.logical_key = lm.key
    LEFT JOIN model_catalog mc
           ON mc.id = lmc.catalog_id
    WHERE lm.key = :key
    """
)


@dataclass(frozen=True)
class _Candidate:
    catalog_id: str
    priority: int
    input_per_million: Any
    output_per_million: Any


def _is_eligible(row: Any) -> bool:
    """The one place all three eligibility rules are enforced. A row with
    no candidate at all (``catalog_id is None`` -- what the LEFT JOIN
    produces when a logical model has zero candidate rows) is never
    eligible either."""
    return (
        row.catalog_id is not None
        and row.candidate_state == 'approved'
        and row.candidate_enabled is True
        and row.catalog_availability == 'available'
    )


def _cache_key(key: str) -> str:
    return f'{_CACHE_PREFIX}{key}'


def _coerce_cached_resolution(raw: str, key: str) -> tuple[bool, str | None]:
    """A cached string becomes a trusted answer only if it is exactly a
    JSON ``null`` (a definitive "no route") or a non-empty JSON string (a
    ``catalog_id``). Every write path below only ever stores one of those
    two shapes, so anything else is corrupt or hand-edited -- and it must
    not be mistaken for a real resolution. Returns ``(is_valid, value)``;
    when ``is_valid`` is False the caller must treat this as a cache miss
    and re-resolve from the database, exactly like ``site_settings.
    _coerce_flag`` falls back to the registered default rather than trust
    a malformed row.
    """
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning(
            'model_resolver: cached value for %r is not valid JSON (%r) -- '
            'treating as a cache miss', key, raw,
        )
        return False, None
    if parsed is None:
        return True, None
    if isinstance(parsed, str) and parsed:
        return True, parsed
    logger.warning(
        'model_resolver: cached value for %r is %r (%s), neither null nor a '
        'catalog id -- treating as a cache miss', key, parsed, type(parsed).__name__,
    )
    return False, None


def _effective_cost(candidate: _Candidate) -> int:
    """Real list price if both sides are priced, else the unpriced ceiling.

    A row with either price at 0 is not "free" -- see the module docstring
    -- it is unknown, and unknown must never look cheap.
    """
    input_price = int(candidate.input_per_million or 0)
    output_price = int(candidate.output_per_million or 0)
    if input_price > 0 and output_price > 0:
        return input_price + output_price
    return _UNPRICED_CEILING


def _pick_pinned(candidates: list[_Candidate], pinned_id: str | None, key: str) -> str | None:
    if not pinned_id:
        logger.warning(
            'model_resolver: logical model %r has routing_policy=pinned but no '
            'pinned_candidate_id set -- resolving to nothing', key,
        )
        return None
    for c in candidates:
        if c.catalog_id == pinned_id:
            return c.catalog_id
    logger.warning(
        'model_resolver: pinned candidate %r for logical model %r is no longer '
        'eligible (not an approved+enabled candidate, or its catalog row is not '
        "available) -- refusing to silently substitute a different model", pinned_id, key,
    )
    return None


def _pick_priority(candidates: list[_Candidate]) -> str | None:
    if not candidates:
        return None
    best = min(candidates, key=lambda c: (c.priority, c.catalog_id))
    return best.catalog_id


def _pick_cheapest(candidates: list[_Candidate]) -> str | None:
    if not candidates:
        return None
    best = min(candidates, key=lambda c: (_effective_cost(c), c.priority, c.catalog_id))
    return best.catalog_id


async def _resolve_from_db(key: str) -> str | None:
    """Runs the single query and applies routing_policy. May raise on a
    real DB error -- the caller (:func:`resolve_logical_model`) is what
    catches that and turns it into a safe ``None``."""
    if async_session is None:
        return None

    async with async_session() as session:
        result = await session.execute(_QUERY, {'key': key})
        rows = result.fetchall()

    if not rows:
        # No such logical_model row at all.
        return None

    first = rows[0]
    if first.lm_availability != 'available':
        return None

    candidates = [
        _Candidate(
            catalog_id=r.catalog_id,
            priority=r.priority,
            input_per_million=r.input_per_million,
            output_per_million=r.output_per_million,
        )
        for r in rows
        if _is_eligible(r)
    ]

    policy = first.lm_routing_policy
    if policy == 'pinned':
        return _pick_pinned(candidates, first.lm_pinned_candidate_id, key)
    if policy == 'priority':
        return _pick_priority(candidates)
    if policy == 'cheapest_healthy':
        return _pick_cheapest(candidates)

    logger.warning('model_resolver: unknown routing_policy %r for %r', policy, key)
    return None


async def resolve_logical_model(key: str) -> str | None:
    """Resolve a logical model key to a physical ``model_catalog.id``.

    Guarantees (see module docstring for the full rationale):
      * Never raises. Any Redis/DB error, missing row, empty eligible
        candidate set, or malformed cache entry returns ``None``.
      * ``None`` always means "caller should fall back to today's direct
        behaviour" -- it is never a rate-limit signal or anything else.
      * A definitive resolution (including a definitive ``None``) is
        cached in Redis for 30 seconds; a *failed* resolution attempt is
        never cached.
      * Deterministic: identical DB state always produces the identical
        answer for the same key (see the tie-break rule in the module
        docstring).
    """
    if not key or not isinstance(key, str):
        return None

    cache_key = _cache_key(key)

    cached: str | None = None
    try:
        cached = await rds.get(cache_key)
    except Exception as e:
        logger.warning('model_resolver: cache read failed for %r: %s', key, e)
        cached = None

    if cached is not None:
        ok, catalog_id = _coerce_cached_resolution(cached, key)
        if ok:
            return catalog_id
        # Malformed cache entry -- fall through and re-resolve from the DB.

    try:
        resolved = await _resolve_from_db(key)
    except Exception as e:
        logger.warning('model_resolver: DB resolution failed for %r: %s', key, e)
        return None

    try:
        await rds.setex(cache_key, _CACHE_TTL_SECONDS, json.dumps(resolved))
    except Exception as e:
        logger.warning('model_resolver: cache write failed for %r: %s', key, e)

    return resolved
