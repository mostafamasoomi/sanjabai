"""Pricing refresh: live OpenRouter USD prices -> IRT catalog prices.

Split out of content.py purely to stay under the house 500-line cap --
nothing here changed in the move.

IMPORT CONTRACT -- read before moving anything again. content.py re-exports
`_fetch_openrouter_prices`, `refresh_pricing`, `OPENROUTER_API` from this
module (also registering `/admin/refresh-pricing` onto `content.router`), so
`from content import refresh_pricing` (app.py's lifespan background loop,
and `app.py:160`'s deferred import) keeps working unchanged.

`refresh_pricing` below calls `content._get_exchange_rate()` -- an attribute
read on the `content` module at CALL time, never `from content import
_get_exchange_rate`. That name is monkeypatched directly in the test suite
(`patch.object(content_mod, '_get_exchange_rate', ...)` in
tests/test_margin_guard.py) and reached indirectly through services/
margin.py's own deferred `from content import ...`; a bare intra-module call
from this file would silently miss that patch, since Python resolves a bare
global against the *defining* module's namespace, not content.py's -- the
same hazard chat_web.py / chat_search.py's IMPORT/MONKEYPATCH CONTRACT
docstrings work out for `chat.<name>`. `content` is imported plainly at
module scope, which is safe against the content.py <-> content_refresh.py
circular import: nothing here touches a `content` attribute until a
function actually runs, by which point content.py has finished executing
(it imports this module only after `router` is defined).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session, rds, _http, ADMIN_TOKEN
from dependencies import admin_required

import content

logger = logging.getLogger('content')  # keep all content_*.py logs under the pre-split 'content' logger name

# ── Pricing refresh (admin or cron) ────────────────────────────

OPENROUTER_API = "https://openrouter.ai/api/v1/models"


async def _fetch_openrouter_prices() -> dict[str, dict[str, float]]:
    """Fetch live USD pricing per 1M tokens from the OpenRouter API.

    Returns a map keyed by the bare model id published by OpenRouter, e.g.
    ``tencent/hy3`` -> {'input': <usd/1M>, 'output': <usd/1M>}.
    Falls back to {} on any network/parse failure.
    """
    try:
        # _http is the shared httpx client (already proxy-aware).
        resp = await _http.get(OPENROUTER_API, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as e:
        print(f"[warn] _fetch_openrouter_prices failed: {e}")
        return {}

    prices: dict[str, dict[str, float]] = {}
    for m in data:
        mid = (m.get("id") or "").strip()
        if not mid:
            continue
        p = m.get("pricing") or {}
        try:
            # OpenRouter exposes per-token USD; convert to per-million.
            pin = float(p.get("prompt") or 0.0) * 1_000_000
            pout = float(p.get("completion") or 0.0) * 1_000_000
        except (TypeError, ValueError):
            continue
        # Normalise to a bare key for matching against model_catalog ids.
        bare = mid.split("/")[-1] if "/" in mid else mid
        prices[mid] = {"input": round(pin, 6), "output": round(pout, 6)}
        prices[bare] = prices[mid]
        prices[mid.replace("/", "-")] = prices[mid]
    return prices


async def refresh_pricing() -> dict[str, Any]:
    """Refresh exchange rate and recalculate IRT prices for all catalog models.

    Live OpenRouter USD prices are fetched and stored per-model into
    model_catalog; Toman (IRT) prices are derived from the live USD→IRT rate.
    Models with no OpenRouter price are left untouched (existing values kept).
    """
    # 1. Fetch fresh exchange rate (loss-safe max of tgju/configured sources,
    # see content._compute_exchange_rate())
    await rds.delete('exchange_rate:usd_irt')  # force refresh
    rate_irt, markup_pct = await content._get_exchange_rate()
    # Truthful provenance: `_get_exchange_rate()` only returns the 2-tuple
    # (rate, markup_pct) contract every price-computing caller depends on
    # (see content.py's TestGetExchangeRateBackwardCompat), so the winning
    # source is read back off the cache payload it just wrote/refreshed,
    # rather than hardcoding a source name here that may not be the one
    # that actually won.
    exchange_source = 'unknown'
    try:
        cached = await rds.get(content.EXCHANGE_RATE_CACHE_KEY)
        if cached:
            exchange_source = json.loads(cached).get('source') or 'unknown'
    except Exception as e:
        logger.warning('failed to read back exchange rate source for refresh_pricing log: %s', e)
    # NOTE: the percentage markup is deliberately NOT folded into this
    # multiplier. model_catalog.input_per_million/output_per_million store
    # the BASE Toman price (USD * rate_irt only); the effective markup
    # (global or per-model override) is applied on top, at read time, by
    # apply_markup() in every price-serving endpoint below and in chat.py's
    # billing path -- see the "Markup (profit percentage)" section above.
    # Baking it in here too would double-apply it for every model this loop
    # touches, and would also skip models without a live OpenRouter price
    # (left untouched below), so the two paths could disagree.
    multiplier = rate_irt

    # 2. Live USD prices from OpenRouter
    or_prices = await _fetch_openrouter_prices()

    # 3. Update model_catalog with new USD + IRT prices
    updated = 0
    if async_session is not None:
        try:
            async with async_session() as session:
                res = await session.execute(sqlalchemy.text(
                    "SELECT id, provider_model_id FROM model_catalog "
                    "WHERE availability = 'available'"
                ))
                rows = res.fetchall()
                for row in rows:
                    mid = row.provider_model_id
                    # Try the catalog id, then the provider_model_id (may contain '/')
                    for key in (row.id, mid, mid.replace('/', '-')):
                        price = or_prices.get(key)
                        if price:
                            break
                    else:
                        # No live OpenRouter price for this model — keep existing.
                        continue
                    irt_input = round(price['input'] * multiplier)
                    irt_output = round(price['output'] * multiplier)
                    await session.execute(
                        sqlalchemy.text(
                            'UPDATE model_catalog SET '
                            'input_per_million = :inp, output_per_million = :out, '
                            'usd_input_per_million = :usd_in, usd_output_per_million = :usd_out, '
                            'price_version = :pv, last_verified_at = now() '
                            'WHERE id = :mid'
                        ),
                        {
                            'inp': irt_input, 'out': irt_output,
                            'usd_in': price['input'], 'usd_out': price['output'],
                            'pv': 'v1', 'mid': row.id,
                        },
                    )
                    updated += 1
                await session.commit()
        except Exception as e:
            return {'status': 'error', 'detail': str(e)}

    # 3b. A model that is offered to users but has no price bills nothing.
    # The health checker promotes models back to `available` on its own and has
    # no notion of pricing, so this has to be re-checked every cycle rather than
    # fixed once.
    unpriced_demoted = 0
    if async_session is not None:
        try:
            async with async_session() as session:
                res = await session.execute(sqlalchemy.text(
                    "UPDATE model_catalog SET availability = 'maintenance', "
                    "updated_at = now() "
                    "WHERE availability = 'available' "
                    "AND (input_per_million IS NULL OR input_per_million <= 0) "
                    "RETURNING id"
                ))
                demoted = [r[0] for r in res.fetchall()]
                await session.commit()
                unpriced_demoted = len(demoted)
                if demoted:
                    logger.warning(
                        'demoted %d unpriced model(s) out of `available`: %s',
                        len(demoted), ', '.join(demoted),
                    )
        except Exception as e:
            logger.warning('unpriced-model guard failed: %s', e)

    # 4. Invalidate caches
    for key in ['cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing']:
        await rds.delete(key)

    return {
        'status': 'ok',
        'exchange_rate': rate_irt,
        'exchange_source': exchange_source,
        'markup_pct': markup_pct,
        'models_matched': len(or_prices) // 3,
        'models_updated': updated,
        'unpriced_demoted': unpriced_demoted,
        'refreshed_at': datetime.now(timezone.utc).isoformat(),
    }


@content.router.post('/admin/refresh-pricing')
async def admin_refresh_pricing(request: Request) -> JSONResponse:
    """Admin endpoint to trigger a pricing refresh."""
    # The old test here was `if not uid and admin_tok != ADMIN_TOKEN`, which let
    # through ANY logged-in user- merely being authenticated was enough, because
    # `uid` is truthy for every ordinary account. That is a privilege check on
    # the wrong predicate. refresh_pricing() calls upstream pricing sources and
    # rewrites our pricing table, so a normal user could trigger repeated
    # upstream work and catalog churn through an /admin/ route. Now it needs a
    # real admin session, or the X-Admin-Token shared secret that the
    # non-interactive callers have always used.
    admin_tok = request.headers.get('X-Admin-Token', '')
    if admin_tok != ADMIN_TOKEN and not await admin_required(request):
        return JSONResponse({'detail': 'admin access required'}, status_code=403)
    result = await refresh_pricing()
    return JSONResponse(jsonable_encoder(result))
