"""What a single upstream model call actually cost us, snapshotted at write time.

`usage_events.charged_amount` is what the USER paid. This module produces the
other half of the sentence: what WE paid. Both are integer Toman.

── Why snapshot instead of deriving on read ─────────────────────────────
Before migration 0048 the only way to answer "did that request make money"
was `model_catalog.usd_*_per_million x tokens x TODAY's exchange rate`. The
catalog's USD prices are overwritten by price sync and the rate moves every
few minutes, so the same historical row produced a different cost every time
anyone looked at it. A profit chart drawn that way is a different chart
tomorrow. Capturing at write time makes every event permanently answerable.

── This module owns the formula. It does not own the arithmetic. ────────
`services/margin.py` already holds the project's honest cost primitives --
`is_paid_upstream()`, `FREE_UPSTREAMS`, and `upstream_cost_toman()` with its
category-ceiling fallback and round-UP rule. A second implementation of that
arithmetic living here would drift from the margin guard, and the day those
two disagree is the day a loss-making price passes the guard and gets billed
anyway. So: everything numeric routes through margin.py. What lives here is
only the per-event assembly, the free-upstream short circuit, the lazy
ceiling cache, and the basis bookkeeping.

── The safe direction ───────────────────────────────────────────────────
Every rounding here is UP, and the exchange rate used carries the flat
markup `content._get_exchange_rate()` applies (the same rate the margin guard
uses, deliberately -- cost must not be computed against a cheaper rate than
the guard checks prices against). Both choices OVERSTATE cost, which
UNDERSTATES profit. That is the only safe direction: a cost we quietly
understate is how a loss-making model looks profitable long enough to be
scaled up.

── Never raises ─────────────────────────────────────────────────────────
`capture_upstream_cost` returns a snapshot in every path including its own
internal failure. It is called from inside the billing transaction, next to
the wallet charge and the ledger row; an exception escaping here would roll
those back and serve the request free. Cost accounting is worth exactly zero
requests.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from dataclasses import dataclass
from typing import Any

import sqlalchemy

logger = logging.getLogger(__name__)


#: Every legal value of `usage_events.upstream_cost_basis`.
#:
#: There is no DB CHECK constraint behind this: Postgres has no
#: `ADD CONSTRAINT IF NOT EXISTS`, and migrate.py re-runs every migration
#: file on every startup, so a CHECK would turn a boot into a crash the
#: second time. The set is enforced here instead, by coercion rather than by
#: raising -- see `normalize_basis`.
BASES = frozenset({'listed', 'category_ceiling', 'free_upstream', 'unknown', 'error'})

#: Worst-first. When input and output resolve to different bases the event
#: is recorded at the *least* certain of the two: an event that guessed one
#: of its two sides is a guessed event, and a report that called it 'listed'
#: would overstate how much of the history is really measured.
_BASIS_RANK = {'listed': 0, 'category_ceiling': 1, 'unknown': 2, 'error': 3}


def normalize_basis(value: Any) -> str:
    """Coerce anything into a legal basis. Never raises.

    An unrecognised value means some caller invented a basis this module has
    never heard of, which is a code defect -- and a code defect is exactly
    what 'error' means. Storing the unknown string instead would let it leak
    into the report as if it were a real category.
    """
    text = str(value or '').strip().lower()
    return text if text in BASES else 'error'


@dataclass(frozen=True)
class CostSnapshot:
    """What one usage event cost us, plus everything needed to re-derive it.

    `cost_toman` is None whenever the cost is genuinely unknown. It is NEVER
    0-as-a-stand-in: 0 means "this really was free" (`free_upstream`), and
    conflating the two is the single mistake this whole change exists to
    prevent. Migration 0048's read-side contract binds every consumer to
    honour that distinction.

    `usd_input_per_million` / `usd_output_per_million` are the rates ACTUALLY
    USED for each side, after any category-ceiling fallback -- not the values
    read from the catalog row. Input and output are evaluated independently
    (margin.py does the same), so one event can be listed-priced on input and
    ceiling-priced on output; the single `basis` field cannot express that,
    but the two stored rates make the row fully reconstructable anyway.
    """

    cost_toman: int | None
    basis: str
    fx_rate_irt: float | None
    usd_input_per_million: float | None
    usd_output_per_million: float | None

    def as_kwargs(self) -> dict[str, Any]:
        """The five `usage_events` columns, ready to splat into record_usage."""
        return {
            'upstream_cost_toman': self.cost_toman,
            'upstream_cost_basis': self.basis,
            'fx_rate_irt': self.fx_rate_irt,
            'usd_input_per_million': self.usd_input_per_million,
            'usd_output_per_million': self.usd_output_per_million,
        }


#: The snapshot used whenever capture itself broke. Distinct from an
#: 'unknown' snapshot on purpose: 'unknown' is a DATA gap (nobody has synced
#: this model's price) and is permanent for that row until prices are
#: synced; 'error' is a CODE gap, will cluster immediately after a bad
#: deploy, and is meant to be loud in the report.
_ERROR_SNAPSHOT = CostSnapshot(None, 'error', None, None, None)

#: Served through the owner's own aggregating infrastructure: ~zero marginal
#: cost per token. No exchange rate is read and no USD rate is stored,
#: because none was consulted -- storing today's rate on an event that never
#: used one would be a fabricated audit trail.
#:
#: The fixed monthly cost of the boxes that infrastructure runs on is a
#: PERIOD cost, not a per-request one. Allocating it across events would
#: fabricate precision: the same past request's cost would change every time
#: this month's volume changed. Reports must therefore call
#: `revenue - SUM(upstream_cost_toman)` gross margin on upstream token cost,
#: never net profit.
_FREE_SNAPSHOT = CostSnapshot(0, 'free_upstream', None, None, None)


# ── Category-ceiling cache ───────────────────────────────────────────────
#
# The ceiling is the MAXIMUM USD price among the models on one upstream, and
# it is what an unpriced model is costed at (project law: the ceiling, never
# the average -- assuming the average is how an expensive unpriced model
# gets sold at a loss).
#
# Computing it needs a `GROUP BY upstream` aggregate over all of
# model_catalog (~1900 rows). That must never sit on the unconditional chat
# hot path. It is only ever needed when BOTH (a) the upstream is paid and
# (b) that side's own USD price is missing -- a branch that executes zero
# times in production today, because every enabled upstream is free.
#
# Cached with the same TTL + refresh-lock shape as chat_models._get_model_upstream:
# on a read failure or while a refresh is in flight, the previous values are
# kept rather than cleared. Slightly stale ceilings beat an unpriced event.
_CEILING_CACHE: dict[str, tuple[float | None, float | None]] = {}
_CEILING_CACHE_LOADED_AT: float = 0.0
_CEILING_CACHE_TTL_SECONDS = 300
_CEILING_REFRESH_LOCK = asyncio.Lock()


def _normalize_upstream(upstream: Any) -> str:
    """The canonical upstream name, so a stray alias is not mistaken for paid.

    Thin wrapper over services.margin.normalize_upstream, kept so callers in
    this module read locally. The map deliberately lives in margin.py beside
    FREE_UPSTREAMS: recognising an upstream and classifying it are one
    decision, and an un-normalized alias classifies as PAID and gets costed
    at a category ceiling it never actually paid -- safe direction, still
    wrong, and it shows up in the report as phantom cost on free traffic.

    It used to import the map from `chat_models`, an app module. Live
    verification caught the cost of that: under one import order the
    deferred import raised, and because this function sits inside the
    never-raises guard, EVERY event came back basis='error' with a NULL cost
    and nothing louder than a log line. A silent, total loss of the profit
    number is exactly what this feature exists to prevent, so the dependency
    now points the correct way -- services/ owns the data, app modules
    import it.
    """
    from services.margin import normalize_upstream

    return normalize_upstream(upstream)


async def _category_ceilings(session, upstream: str) -> tuple[float | None, float | None]:
    """(input, output) ceiling USD-per-million for `upstream`. Never raises."""
    global _CEILING_CACHE, _CEILING_CACHE_LOADED_AT

    now = _time.monotonic()
    fresh = (now - _CEILING_CACHE_LOADED_AT) < _CEILING_CACHE_TTL_SECONDS
    if fresh or _CEILING_REFRESH_LOCK.locked():
        return _CEILING_CACHE.get(upstream, (None, None))

    async with _CEILING_REFRESH_LOCK:
        now = _time.monotonic()
        if (now - _CEILING_CACHE_LOADED_AT) < _CEILING_CACHE_TTL_SECONDS:
            return _CEILING_CACHE.get(upstream, (None, None))
        try:
            # Written inline as a literal, not built from a constant:
            # scripts/sql_schema_audit.py only EXPLAINs a text() whose
            # argument is a literal, and the test suite mocks the DB, so
            # nothing else would catch a wrong column name here.
            res = await session.execute(sqlalchemy.text("""
                SELECT upstream,
                       max(usd_input_per_million) AS ceiling_usd_input,
                       max(usd_output_per_million) AS ceiling_usd_output
                FROM model_catalog
                WHERE upstream IS NOT NULL
                GROUP BY upstream
            """))
            cache: dict[str, tuple[float | None, float | None]] = {}
            for row in res.fetchall():
                cache[_normalize_upstream(row.upstream)] = (
                    row.ceiling_usd_input, row.ceiling_usd_output,
                )
            _CEILING_CACHE = cache
            _CEILING_CACHE_LOADED_AT = _time.monotonic()
        except Exception as exc:
            logger.warning(
                f'cost_capture: category-ceiling read failed, keeping previous cache: {exc}'
            )
    return _CEILING_CACHE.get(upstream, (None, None))


def _event_cost_toman(tokens: int, toman_per_million: int) -> int:
    """Cost of `tokens` at `toman_per_million`, rounded UP.

    Deliberately NOT `services.metering._part`, which rounds half-up. That
    function prices what the user is CHARGED, where half-up is fair. This
    prices what we PAY, where rounding down understates cost -- the one
    direction that can make a loss-making request read as profitable.
    """
    tokens = int(tokens or 0)
    rate = int(toman_per_million or 0)
    if tokens <= 0 or rate <= 0:
        return 0
    return -(-tokens * rate // 1_000_000)


async def capture_upstream_cost(
    session,
    *,
    upstream: Any,
    input_tokens: int,
    output_tokens: int,
    usd_input_per_million: float | None,
    usd_output_per_million: float | None,
) -> CostSnapshot:
    """What this event cost us upstream. Never raises, in any path.

    `input_tokens` MUST be the RAW prompt tokens the upstream reported, not
    the overhead-discounted number the user is billed on. When a provider
    injects its own preamble we refuse to bill the user for it
    (services/upstream_overhead.py) -- but the upstream still charges US for
    every token it processed. Revenue on discounted tokens, cost on raw
    tokens. That asymmetry is the honest one, and reversing it would quietly
    shrink recorded cost on exactly the providers that pad hardest.
    """
    try:
        from services.margin import is_paid_upstream, upstream_cost_toman

        name = _normalize_upstream(upstream)

        # Short-circuits BEFORE any exchange-rate lookup: a free upstream
        # consulted no rate, so recording one would invent an audit trail,
        # and a rate-source outage must never be able to affect a path that
        # does not need a rate.
        if not is_paid_upstream(name):
            return _FREE_SNAPSHOT

        from content import _get_exchange_rate
        rate_irt, _markup_pct = await _get_exchange_rate()

        ceiling_in, ceiling_out = (None, None)
        if usd_input_per_million is None or usd_output_per_million is None:
            ceiling_in, ceiling_out = await _category_ceilings(session, name)

        total = 0
        worst = 'listed'
        used: list[float | None] = []
        for tokens, listed_usd, ceiling_usd in (
            (input_tokens, usd_input_per_million, ceiling_in),
            (output_tokens, usd_output_per_million, ceiling_out),
        ):
            per_million = upstream_cost_toman(
                listed_usd, rate_irt, ceiling_usd_per_million=ceiling_usd,
            )
            if per_million is None:
                # No price for this model AND no ceiling for its upstream.
                # Genuinely unknowable, so the whole event is unknowable --
                # a half-costed event reported as a number would understate
                # cost, and understating cost is the forbidden direction.
                return CostSnapshot(None, 'unknown', rate_irt, None, None)
            side_usd = listed_usd if _is_usable(listed_usd) else ceiling_usd
            used.append(float(side_usd) if side_usd is not None else None)
            if not _is_usable(listed_usd):
                worst = _worse(worst, 'category_ceiling')
            total += _event_cost_toman(tokens, per_million)

        return CostSnapshot(total, worst, rate_irt, used[0], used[1])
    except Exception as exc:
        logger.warning(f'cost_capture: capture failed upstream={upstream!r}: {exc}')
        return _ERROR_SNAPSHOT


async def snapshot_for_price_row(
    session,
    price_row: Any,
    *,
    input_tokens: int,
    output_tokens: int,
    model: str = '',
    uid: int | None = None,
) -> CostSnapshot:
    """Cost this request from the catalog row the billing path already read.

    Lives here rather than inline in chat_billing._record_usage for two
    reasons: that function was already at the house line cap, and everything
    this does is cost policy, which belongs beside the rest of it.

    ── Where the caller must invoke this ────────────────────────────────
    ABOVE the entitlement branch, so BOTH billing paths record a cost. A
    package-covered request charges the user nothing but still costs us
    upstream; leaving it uncosted makes every package look infinitely
    profitable, so the more we sell the better the dashboard looks while the
    bill grows.

    ── Which token count ────────────────────────────────────────────────
    `input_tokens` must be the RAW prompt tokens the upstream reported, not
    the overhead-discounted number the user is billed on. Revenue on
    discounted tokens, cost on raw tokens; see capture_upstream_cost.

    ── When price_row is None ───────────────────────────────────────────
    That is the L2 catalog-data-bug path: we served a model with no catalog
    row, so nothing is known about its upstream. The snapshot is honestly
    'error' -- never a zero, which would claim the request was free.

    Belt AND braces on the exception guard: capture_upstream_cost already
    never raises, and this wraps it anyway. It runs inside the billing
    transaction beside the wallet charge and the Ledger row, where an
    escaping exception does not merely lose a bookkeeping field -- it rolls
    the charge back and serves the request free, silently, with nothing worse
    than a warning in the log. That guarantee is too expensive to leave
    resting on one function's internal discipline.
    """
    if price_row is None:
        return _ERROR_SNAPSHOT
    try:
        return await capture_upstream_cost(
            session,
            upstream=getattr(price_row, 'upstream', None),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usd_input_per_million=getattr(price_row, 'usd_input_per_million', None),
            usd_output_per_million=getattr(price_row, 'usd_output_per_million', None),
        )
    except Exception as exc:
        logger.warning(
            f'cost_capture: snapshot raised model={model!r} uid={uid}: {exc}'
        )
        return _ERROR_SNAPSHOT


def _is_usable(value: Any) -> bool:
    """Is this a real positive price? Mirrors margin._positive_float's rule.

    A zero or missing USD price means "never synced", not "free" -- that is
    margin.py's rule and it must not diverge here, or the two would disagree
    about which models are unpriced.
    """
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _worse(left: str, right: str) -> str:
    """The less-certain of two bases (see _BASIS_RANK)."""
    return left if _BASIS_RANK.get(left, 3) >= _BASIS_RANK.get(right, 3) else right
