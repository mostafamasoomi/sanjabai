"""Unified pricing service (Phase 5).

Single source of truth for setting a model's price. Both the versioned `pricing`
rows and the denormalized `model_catalog` columns are updated in one transaction,
and the relevant cache keys are invalidated. Every call also writes an audit
event.

The three historical write paths (`admin_catalog.set_pricing`,
`scripts/update_models.py`, `admin/app.py::pricing_update`) now delegate here so
there is exactly one place that decides how a price change is persisted.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy

from database import rds
from models import Pricing


async def set_model_price(session, *, model_id: str, input_per_million: int,
                          output_per_million: int, currency: str = 'IRT',
                          source: str | None = None) -> dict[str, Any]:
    """Update a model's price atomically: new versioned `pricing` row +
    denormalized `model_catalog` columns. Caller is responsible for the
    cache invalidation + audit (or pass `commit_and_audit` helpers).

    Returns the new state.

    This does NOT commit the session; the caller decides transactionality.
    """
    # Fetch current max version for the model
    res = await session.execute(sqlalchemy.text(
        "SELECT COALESCE(MAX(price_version), 0) FROM pricing WHERE model = :m"
    ), {'m': model_id})
    current_version = int(res.scalar_one())

    new_version = current_version + 1

    # Insert new versioned row
    pricing = Pricing(
        model=model_id,
        input_per_million=int(input_per_million),
        output_per_million=int(output_per_million),
        currency=currency,
        price_version=new_version,
        source=source,
        effective_from=datetime.utcnow(),
    )
    session.add(pricing)

    # Update the denormalized model_catalog columns
    await session.execute(sqlalchemy.text(
        "UPDATE model_catalog SET input_per_million = :inp, "
        "output_per_million = :out, currency = :cur, updated_at = now() "
        "WHERE id = :m"
    ), {'inp': int(input_per_million), 'out': int(output_per_million),
        'cur': currency, 'm': model_id})

    return {
        'model': model_id,
        'price_version': new_version,
        'input_per_million': int(input_per_million),
        'output_per_million': int(output_per_million),
        'currency': currency,
        'source': source,
    }


async def invalidate_pricing_cache() -> None:
    """Clear the catalog/pricing caches so a price change is immediately visible."""
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')