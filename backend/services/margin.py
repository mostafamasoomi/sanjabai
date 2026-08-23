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
billing question.

WIRED (Phase F1) into the six admin decision points that can price a model
or put it on sale, all of them through ``refuse_if_loss_making`` below:

    admin_pricing.set_pricing              base price
    admin_pricing.toggle_model             flip to 'available'
    admin_catalog.bulk_set_availability    bulk flip to 'available'
    admin_catalog.set_model_upstream       free upstream -> paid upstream
    admin_catalog.set_model_markup         the other half of the price
    admin_catalog.bulk_set_model_markup    ditto, in bulk

STILL UNGUARDED, and the reason OpenRouter must not be enabled yet: the
background health mirror (model_health.py + model_health_policy.
_target_catalog_state) promotes a row to 'available' on a healthy probe
plus ``input_per_million > 0`` alone -- a price test, not a MARGIN test --
and model_discovery.py's ON CONFLICT re-binds an existing row's
``upstream`` without asking. Together those can put a paid-upstream model
on sale without this module ever being consulted.

All inputs/outputs here are integer Toman-per-million rates (the same unit
model_catalog.input_per_million / output_per_million already use). The one
float in this module is ``margin_pct``, a diagnostic percentage for
logging/decision-making -- it is never a monetary amount and is never
written to the ledger, so it does not violate the project's
integer-money rule (see services/money.py).
"""
from __future__ import annotations

import logging
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy

logger = logging.getLogger(__name__)

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


# ── Which upstreams actually cost us money ──────────────────────────────
#
# Every upstream enabled today is the owner's own aggregating
# infrastructure and costs ~zero per token, which is why check_margin()
# above is a no-op in production right now. OpenRouter is the first real
# paid one. An upstream nobody has classified is assumed PAID: assuming
# "free" is precisely the mistake that sells at a loss, so the unknown
# case must fail towards refusing, never towards approving.
FREE_UPSTREAMS = frozenset({'litellm', 'ninerouter', 'omniroute'})


def is_paid_upstream(upstream: str | None) -> bool:
    """Does serving a model through ``upstream`` cost us money per token?"""
    return str(upstream or '').strip().lower() not in FREE_UPSTREAMS


def upstream_cost_toman(
    usd_per_million: float | None,
    rate_irt: float,
    *,
    ceiling_usd_per_million: float | None,
) -> int | None:
    """Integer Toman-per-million we pay upstream, or None when unknowable.

    ``usd_per_million`` is model_catalog.usd_input_per_million /
    usd_output_per_million -- the upstream's own list price in USD.
    A missing or zero value means "never synced", not "free", so it falls
    back to ``ceiling_usd_per_million``: the MAXIMUM in that model's
    category, never the average (project law: an unpriced model is costed
    at the category ceiling). None when the ceiling is unknown too -- the
    caller must refuse rather than assume zero.

    Rounded UP: understating upstream cost is the single rounding
    direction that can let a loss-making price through. The result is
    Toman; no Rial conversion happens anywhere outside the payment
    gateway adapter.
    """
    usd = _positive_float(usd_per_million)
    if usd is None:
        usd = _positive_float(ceiling_usd_per_million)
    if usd is None:
        return None
    return int(math.ceil(usd * float(rate_irt)))


def _positive_float(value: Any) -> float | None:
    """``value`` as a float when it is a usable positive price, else None."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


@dataclass(frozen=True)
class PriceRefusal:
    """Why a listed price may not be sold. Persian text for the admin,
    raw numbers for audit_log."""

    model_id: str
    detail: str
    audit: dict[str, Any]


_TOKEN_KIND_FA = {'input': 'ورودی', 'output': 'خروجی'}


def evaluate_price(
    model_id: str,
    *,
    upstream: str | None,
    listed_input_per_million: int,
    listed_output_per_million: int,
    usd_input_per_million: float | None,
    usd_output_per_million: float | None,
    rate_irt: float,
    ceiling_usd_input_per_million: float | None,
    ceiling_usd_output_per_million: float | None,
) -> PriceRefusal | None:
    """None when ``model_id`` is safe to sell at these prices, else the refusal.

    ``listed_*_per_million`` are the EFFECTIVE Toman rates the user is
    billed (base price with markup already applied by the caller), so the
    comparison is against what a request actually earns, not against an
    intermediate number nobody is charged.

    Input and output are checked separately: a fat input margin must not
    paper over a loss-making output rate, and the two token categories are
    priced independently anyway (see check_margin's docstring).
    """
    if not is_paid_upstream(upstream):
        return None

    for kind, listed, usd, ceiling in (
        ('input', listed_input_per_million, usd_input_per_million, ceiling_usd_input_per_million),
        ('output', listed_output_per_million, usd_output_per_million, ceiling_usd_output_per_million),
    ):
        cost = upstream_cost_toman(usd, rate_irt, ceiling_usd_per_million=ceiling)
        kind_fa = _TOKEN_KIND_FA[kind]
        if cost is None:
            return PriceRefusal(
                model_id=model_id,
                detail=(
                    f'هزینه بالادست «{model_id}» روی «{upstream}» برای توکن {kind_fa} '
                    f'نامعلوم است و سقف دسته هم در دسترس نیست. تا مشخص‌شدن هزینه، '
                    f'قیمت‌گذاری و عرضهٔ این مدل رد می‌شود (هیچ درخواستی نباید ضررده باشد).'
                ),
                audit={
                    'model': model_id, 'upstream': upstream, 'token_kind': kind,
                    'listed_per_million': int(listed), 'upstream_cost_per_million': None,
                    'margin_pct': None, 'min_margin_pct': MIN_MARGIN_PCT,
                    'currency': 'IRT', 'reason': 'upstream cost unknown, no category ceiling',
                },
            )
        result = check_margin(int(listed), cost)
        if not result.ok:
            margin_txt = 'نامعلوم' if result.margin_pct is None else f'{result.margin_pct:.1f}٪'
            return PriceRefusal(
                model_id=model_id,
                detail=(
                    f'فروش «{model_id}» ضررده است: قیمت توکن {kind_fa} '
                    f'{int(listed):,} تومان بر هر میلیون توکن در برابر هزینه بالادست '
                    f'{cost:,} تومان — حاشیه {margin_txt}، حداقل مجاز '
                    f'{MIN_MARGIN_PCT:g}٪. هیچ درخواستی نباید ضررده باشد.'
                ),
                audit={
                    'model': model_id, 'upstream': upstream, 'token_kind': kind,
                    'listed_per_million': int(listed), 'upstream_cost_per_million': cost,
                    'margin_pct': result.margin_pct, 'min_margin_pct': result.min_margin_pct,
                    'currency': 'IRT', 'reason': result.reason,
                },
            )
    return None


async def refuse_if_loss_making(
    session,
    model_ids: Sequence[str],
    *,
    input_per_million: int | None = None,
    output_per_million: int | None = None,
    markup_pct: float | None = None,
    markup_pct_provided: bool = False,
    upstream: str | None = None,
) -> PriceRefusal | None:
    """Guard for every admin decision that prices or offers a model.

    Returns None when every id may be sold at the resulting price, else the
    first :class:`PriceRefusal`. Never raises -- a guard that throws on the
    caller is a guard that gets wrapped in a bare `except` and neutered.

    ``input_per_million``/``output_per_million`` are the BASE Toman prices
    the caller is about to write (None = keep what is stored);
    ``markup_pct`` is the override the caller is about to write, which
    needs ``markup_pct_provided`` to tell "set it to null (inherit the
    global)" apart from "not changing it". ``upstream`` is the router the
    caller is about to move these models onto (None = keep the stored
    one): moving a row from free infrastructure to a paid upstream turns a
    zero cost into a real one without the price changing at all. The
    comparison is made against the price after markup, i.e. what a request
    actually earns.

    Fails CLOSED: if the guard cannot prove the price is safe -- a failed
    query, an unknown upstream cost with no category ceiling -- it refuses.
    """
    ids = [str(i) for i in model_ids]
    if not ids:
        return None

    try:
        # Written inline, not as a module constant: scripts/sql_schema_audit.py
        # only EXPLAINs a `text()` whose argument is a literal, and the test
        # suite mocks the DB so nothing else can catch a wrong column name.
        #
        # One query answers both halves of the guard -- the rows being
        # changed, and the per-upstream price CEILING used to cost a row
        # whose own usd price is missing (project law: unpriced => ceiling of
        # the category, never the average). `IS NOT DISTINCT FROM` rather
        # than `=` so rows with a NULL upstream still join to their own group
        # instead of dropping out.
        res = await session.execute(sqlalchemy.text("""
            SELECT m.id, m.upstream, m.markup_pct,
                   m.input_per_million, m.output_per_million,
                   m.usd_input_per_million, m.usd_output_per_million,
                   c.ceiling_usd_input, c.ceiling_usd_output
            FROM model_catalog m
            LEFT JOIN (
                SELECT upstream,
                       max(usd_input_per_million) AS ceiling_usd_input,
                       max(usd_output_per_million) AS ceiling_usd_output
                FROM model_catalog GROUP BY upstream
            ) c ON c.upstream IS NOT DISTINCT FROM m.upstream
            WHERE m.id = ANY(:ids)
        """), {'ids': ids})
        rows = res.fetchall()
    except Exception as e:
        logger.error(f'margin guard: catalog read failed for {len(ids)} model(s): {e}')
        return PriceRefusal(
            model_id=ids[0],
            detail=(
                'بررسی حاشیهٔ سود ممکن نشد و تغییر قیمت/عرضه انجام نشد. '
                'هیچ درخواستی نباید ضررده باشد، پس تا زمانی که این بررسی '
                'قابل انجام نباشد تغییر پذیرفته نمی‌شود.'
            ),
            audit={'model': ids[0], 'model_count': len(ids), 'currency': 'IRT',
                   'reason': f'margin guard could not read model_catalog: {type(e).__name__}'},
        )

    paid = [r for r in rows if is_paid_upstream(upstream if upstream is not None else r.upstream)]
    if not paid:
        # Today's production reality: every enabled upstream is the owner's
        # own infrastructure. No USD conversion is needed, so a rate-source
        # outage can never block ordinary catalog admin.
        return None

    from content import apply_markup, get_global_markup_pct, resolve_markup_pct, _get_exchange_rate

    try:
        rate_irt, _ = await _get_exchange_rate()
        global_pct = await get_global_markup_pct()
    except Exception as e:
        logger.error(f'margin guard: rate/markup lookup failed: {e}')
        return PriceRefusal(
            model_id=paid[0].id,
            detail=(
                'نرخ ارز یا درصد سود در دسترس نیست، پس ضررده‌نبودن این قیمت '
                'قابل اثبات نیست و تغییر پذیرفته نشد.'
            ),
            audit={'model': paid[0].id, 'currency': 'IRT',
                   'reason': f'margin guard could not resolve rate/markup: {type(e).__name__}'},
        )

    for row in paid:
        row_markup = markup_pct if markup_pct_provided else row.markup_pct
        effective_pct = resolve_markup_pct(row_markup, global_pct)
        base_in = row.input_per_million if input_per_million is None else input_per_million
        base_out = row.output_per_million if output_per_million is None else output_per_million
        refusal = evaluate_price(
            row.id,
            upstream=upstream if upstream is not None else row.upstream,
            listed_input_per_million=apply_markup(base_in, effective_pct),
            listed_output_per_million=apply_markup(base_out, effective_pct),
            usd_input_per_million=row.usd_input_per_million,
            usd_output_per_million=row.usd_output_per_million,
            rate_irt=rate_irt,
            ceiling_usd_input_per_million=row.ceiling_usd_input,
            ceiling_usd_output_per_million=row.ceiling_usd_output,
        )
        if refusal is not None:
            return refusal
    return None
