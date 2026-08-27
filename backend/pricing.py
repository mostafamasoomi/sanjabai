"""
Pricing endpoints: credit packages. Plans/subscriptions were retired
(session 23, migration 0049_retire_plans_subscriptions.sql) -- credit_packages
is now the only product concept. Billing settings, /me, and checkout flows
live in pricing_billing.py.
"""
from __future__ import annotations

from typing import Any

import sqlalchemy
from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session
from i18n import err

router = APIRouter()

# Billing-settings / /me / checkout endpoints were split out to
# pricing_billing.py purely to stay under the house 500-line cap (pure
# move, no behaviour change -- see that module's docstring). Mounted here
# so `router` (the object app.py's `from pricing import router as
# pricing_router` imports) keeps exposing every route unchanged.
from pricing_billing import router as _billing_router  # noqa: E402
router.include_router(_billing_router)


# ── Public endpoints ────────────────────────────────────────────

@router.get('/credit-packages')
async def list_credit_packages() -> JSONResponse:
    """List all active credit packages (public)"""
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM credit_packages WHERE active = true ORDER BY sort_order')
        )
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.get('/credit-packages/{pkg_id}')
async def get_credit_package(pkg_id: str) -> JSONResponse:
    """Get a single credit package by ID (public)"""
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM credit_packages WHERE id = :pid AND active = true'),
            {'pid': pkg_id}
        )
        row = res.fetchone()
        if not row:
            return err('بسته یافت نشد', 'Package not found.', 404)
    return JSONResponse(jsonable_encoder(dict(row._mapping)))

