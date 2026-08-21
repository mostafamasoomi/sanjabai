"""Margin guard for Sanjabai billing (L5).

Answers one question: would selling a model at our listed price lose money
-- or fall below the minimum acceptable margin -- against a given
upstream's per-token cost?

Today every configured upstream (9router/ninerouter, omniroute,
bynara-via-litellm) costs us approximately zero -- they are the owner's own
aggregating infrastructure -- so this check is a no-op in production right
now. The moment a paid upstream (e.g. OpenRouter, registered but disabled
today) is enabled, upstream cost becomes real and this stops being a no-op.

Deliberately NOT wired into the hot chat request path (chat.py) -- it must
not add a new DB round-trip to every chat request, and it answers a pricing
question ("is this listed price safe to sell at"), not a per-request
billing question. It is meant to be called wherever a model's listed price
is set or an upstream is approved for a model -- see the loss-path report
for exactly where to wire it (that code is owned by another agent working
concurrently in this repo, so this module only implements + unit-tests the
helper).

All inputs/outputs here are integer Toman-per-million rates (the same unit
model_catalog.input_per_million / output_per_million already use). The one
float in this module is ``margin_pct``, a diagnostic percentage for
logging/decision-making -- it is never a monetary amount and is never
written to the ledger, so it does not violate the project's
integer-money rule (see services/money.py).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Minimum acceptable margin, as a percentage of upstream cost, before a
# listed price is considered too close to (or below) upstream cost.
# Default 20% -- configurable because the right floor is a business
# decision, not a code constant.
MIN_MARGIN_PCT = float(os.getenv('MIN_MARGIN_PCT', '20'))


@dataclass(frozen=True)
class MarginCheck:
    ok: bool                      # True iff the listed price clears the margin floor
    listed_per_million: int
    upstream_cost_per_million: int
    margin_pct: float | None      # None when upstream cost is 0 (margin is undefined/infinite)
    min_margin_pct: float
    reason: str


def check_margin(
    listed_per_million: int,
    upstream_cost_per_million: int,
    *,
    min_margin_pct: float | None = None,
) -> MarginCheck:
    """Would serving a model at ``listed_per_million`` lose money (or clear
    less than the minimum margin) against ``upstream_cost_per_million``?

    Both are integer Toman per 1,000,000 tokens. This is a per-token-category
    check (call it once for input, once for output) -- it does not attempt
    to blend the two into a single whole-model number, since usage mix
    between input and output tokens varies per request.
    """
    floor_pct = MIN_MARGIN_PCT if min_margin_pct is None else float(min_margin_pct)
    listed = int(listed_per_million)
    upstream = int(upstream_cost_per_million)

    if listed < 0 or upstream < 0:
        return MarginCheck(
            ok=False, listed_per_million=listed, upstream_cost_per_million=upstream,
            margin_pct=None, min_margin_pct=floor_pct,
            reason='negative price or upstream cost is invalid',
        )

    if upstream == 0:
        # Free upstream (today's reality for every enabled upstream): any
        # non-negative listed price is pure margin, clears any floor.
        return MarginCheck(
            ok=True, listed_per_million=listed, upstream_cost_per_million=upstream,
            margin_pct=None, min_margin_pct=floor_pct, reason='upstream cost is zero',
        )

    if listed < upstream:
        margin_pct = (listed - upstream) / upstream * 100.0
        return MarginCheck(
            ok=False, listed_per_million=listed, upstream_cost_per_million=upstream,
            margin_pct=margin_pct, min_margin_pct=floor_pct,
            reason='listed price is below upstream cost -- would lose money on every token',
        )

    # Cross-multiply rather than divide-then-compare for the boolean
    # decision, so the floor comparison is not sensitive to float rounding
    # near the boundary; margin_pct itself (division) is kept only as a
    # human-readable diagnostic on the result, not as the decision input.
    margin_ok = (listed - upstream) * 100.0 >= floor_pct * upstream
    margin_pct = (listed - upstream) / upstream * 100.0

    if not margin_ok:
        return MarginCheck(
            ok=False, listed_per_million=listed, upstream_cost_per_million=upstream,
            margin_pct=margin_pct, min_margin_pct=floor_pct,
            reason=f'margin {margin_pct:.2f}% is below the {floor_pct:.2f}% floor',
        )

    return MarginCheck(
        ok=True, listed_per_million=listed, upstream_cost_per_million=upstream,
        margin_pct=margin_pct, min_margin_pct=floor_pct, reason='ok',
    )
