"""Usage metering for Sanjabai.

Records a *usage event* for every upstream model call: which request, which
model and price version were used, the token breakdown (input / output /
cached-input / reasoning), the reservation that funded it, the final charged
amount (a :class:`services.money.Money`), and the upstream outcome.

Charges are computed with exact integer arithmetic — no floating point — by
:func:`compute_charge`, which prices each token category against the
per-million rates of the active price version.
"""
from __future__ import annotations

from typing import Optional

from .money import Money


# Token categories recorded on every usage event.
INPUT = "input"
OUTPUT = "output"
CACHED_INPUT = "cached_input"
REASONING = "reasoning"

# Upstream outcome states.
UPSTREAM_SUCCESS = "success"
UPSTREAM_FAILURE = "failure"
UPSTREAM_CANCELLED = "cancelled"


def _part(tokens: int, per_million: int) -> int:
    """Cost in Tomans for ``tokens`` at ``per_million`` Tomans per 1e6 tokens.

    Uses integer half-up rounding: ``(tokens * per_million + 500000) // 1_000_000``.
    """
    tokens = int(tokens or 0)
    per_million = int(per_million or 0)
    if tokens <= 0 or per_million <= 0:
        return 0
    return (tokens * per_million + 500_000) // 1_000_000


def compute_charge(
    price: dict,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> Money:
    """Compute the total charge (Money, Tomans) for a request.

    ``price`` is a dict-like with ``input_per_million``,
    ``output_per_million``, optional ``cached_input_per_million`` and
    ``reasoning_per_million`` (all integer Tomans per 1e6 tokens).
    """
    total = (
        _part(input_tokens, int(price.get("input_per_million") or 0))
        + _part(output_tokens, int(price.get("output_per_million") or 0))
        + _part(cached_input_tokens, int(price.get("cached_input_per_million") or 0))
        + _part(reasoning_tokens, int(price.get("reasoning_per_million") or 0))
    )
    return Money(total)


async def record_usage(
    repo,
    *,
    request_id: str,
    user_id: int,
    model: str,
    charge: Money,
    upstream_status: str,
    price_version: Optional[str] = None,
    provider: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    reasoning_tokens: int = 0,
    reservation_id: Optional[str] = None,
    upstream_error: Optional[str] = None,
    meta: Optional[dict] = None,
    upstream_cost_toman: Optional[int] = None,
    upstream_cost_basis: Optional[str] = None,
    fx_rate_irt: Optional[float] = None,
    usd_input_per_million: Optional[float] = None,
    usd_output_per_million: Optional[float] = None,
) -> dict:
    """Persist a usage event. ``charge`` must be a :class:`Money`.

    ``charge`` is what the USER paid. The ``upstream_cost_*`` /
    ``fx_rate_irt`` / ``usd_*_per_million`` group is what WE paid, snapshotted
    at write time by :mod:`services.cost_capture` -- see
    ``migrations/0048_usage_event_cost.sql`` for the full column semantics and
    the read-side contract they bind consumers to.

    All five default to None so that a caller which knows nothing about cost
    still works unchanged. **None means unknown, never zero** -- a caller that
    passes nothing produces a row indistinguishable from the pre-0048
    history, which is exactly right: it did not measure anything.
    """
    if not isinstance(charge, Money):
        raise TypeError("charge must be a Money instance")
    if upstream_cost_basis is not None:
        # Coerced, never rejected. This is called from inside the billing
        # transaction; raising on a bad basis string would roll back the
        # wallet charge and the ledger row to protect a bookkeeping field.
        from .cost_capture import normalize_basis
        upstream_cost_basis = normalize_basis(upstream_cost_basis)
    data = {
        "request_id": request_id,
        "user_id": user_id,
        "model": model,
        "price_version": price_version,
        "provider": provider,
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "cached_input_tokens": int(cached_input_tokens or 0),
        "reasoning_tokens": int(reasoning_tokens or 0),
        "reservation_id": reservation_id,
        "charged_amount": charge.amount,
        "currency": "IRT",
        "upstream_status": upstream_status,
        "upstream_error": upstream_error,
        "meta": meta,
        "upstream_cost_toman": upstream_cost_toman,
        "upstream_cost_basis": upstream_cost_basis,
        "fx_rate_irt": fx_rate_irt,
        "usd_input_per_million": usd_input_per_million,
        "usd_output_per_million": usd_output_per_million,
    }
    await repo.append_usage_event(data)
    return data
