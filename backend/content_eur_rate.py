"""EUR->IRT exchange rate mirror of content.py's USD resolver.

Split out of content.py purely to stay under the house 500-line cap --
nothing here changed in the move. Used only by hermes.py to price Hetzner's
EUR-denominated hosting cost in Toman (never exposed as a currency choice to
end users).

IMPORT CONTRACT -- read before moving anything again. content.py re-exports
`_fetch_tgju_eur_rate`, `_get_eur_exchange_rate`, `_get_cached_eur_to_irt`
from this module (`from content_eur_rate import ...` near the bottom of
content.py), so `from content import _get_cached_eur_to_irt` (hermes.py) and
any bare reference to these names inside content.py itself keep working
unchanged.

`_get_eur_exchange_rate` below calls `content.get_global_markup_pct()` and
`_fetch_tgju_eur_rate` reads `content.TGJU_TIMEOUT_S` / `content._http` --
attribute reads on the `content` module at CALL time, never
`from content import get_global_markup_pct`. This is the same late-binding
pattern chat_web.py / chat_search.py use for `chat.<name>`: content.py is
the hub the test suite monkeypatches (`patch.object(content_mod,
'get_global_markup_pct', ...)` in tests/test_margin_guard.py), and a bare
intra-module call from a *different* file would silently miss that patch,
since Python resolves a bare global against the *defining* module's
namespace. Nothing in this file is itself monkeypatched today, but calling
back into content.py this way keeps that guarantee true if it ever is.
`content` is imported plainly at module scope, which is safe against the
content.py <-> content_eur_rate.py circular import: nothing here touches a
`content` attribute until a function actually runs, by which point
content.py has finished executing.
"""
from __future__ import annotations

import json
import logging
import re

import sqlalchemy

from database import async_session, rds

import content

logger = logging.getLogger('content')  # keep all content_*.py logs under the pre-split 'content' logger name


async def _fetch_tgju_eur_rate() -> float | None:
    """Fetch the live EUR→IRR market rate from tgju.org.

    Async twin of _fetch_tgju_rate. Returns IRR (Rial), or None on failure.
    """
    try:
        resp = await content._http.get(
            "https://www.tgju.org/profile/price_eur",
            follow_redirects=True,
            timeout=content.TGJU_TIMEOUT_S,
        )
        resp.raise_for_status()
        m = re.search(r'class="price"[^>]*>([\d,]+)<', resp.text)
        if m:
            return float(m.group(1).replace(",", ""))
    except Exception as e:
        logger.warning("tgju EUR rate fetch failed: %s", e)
    return None


async def _get_eur_exchange_rate() -> tuple[float, int]:
    """Return the live EUR→IRT (Toman) rate and markup percentage.

    Mirrors ``_get_exchange_rate`` (USD) exactly, used by the Hermes server
    product to price Hetzner's EUR-denominated hosting cost in Toman. Order
    of resolution:
      1. A manual DB override (exchange_rate_overrides, EUR->IRT) if present.
      2. Live tgju.org market rate.
      3. Fallback to open.er-api.com.
      4. Hardcoded fallback constant.
    """
    markup_pct = await content.get_global_markup_pct()
    rate_irr = None

    # 1. Manual DB override (highest priority)
    try:
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(sqlalchemy.text(
                    "SELECT rate FROM exchange_rate_overrides "
                    "WHERE from_currency='EUR' AND to_currency='IRT' AND active=TRUE "
                    "ORDER BY id DESC LIMIT 1"
                ))
                row = res.fetchone()
                if row:
                    # stored value is already IRT (Toman)
                    return float(row.rate), markup_pct
    except Exception:
        pass

    # 2. Live tgju.org
    rate_irr = await _fetch_tgju_eur_rate()

    # 3. Fallback to open.er-api.com
    if rate_irr is None:
        try:
            resp2 = await content._http.get('https://open.er-api.com/v6/latest/EUR', follow_redirects=True, timeout=10)
            resp2.raise_for_status()
            rate_irr = float(resp2.json()['rates']['IRR'])
        except Exception:
            pass

    # 4. Hardcoded fallback (approximate, reviewed periodically)
    if rate_irr is None:
        rate_irr = 1_370_000

    rate_irt = rate_irr / 10  # IRR → IRT (Toman)
    return rate_irt, markup_pct


async def _get_cached_eur_to_irt() -> float:
    """Return the EUR→IRT rate, cached in Redis for EXCHANGE_RATE_CACHE_TTL.

    Separate cache key from the USD rate (``exchange_rate:eur_irt``) so the
    two currencies refresh independently. Used by hermes.py to price
    offerings without ever exposing the EUR figure to end users.
    """
    cached = await rds.get('exchange_rate:eur_irt')
    if cached:
        return float(json.loads(cached)['eur_to_irt'])
    rate_irt, _markup = await _get_eur_exchange_rate()
    await rds.setex('exchange_rate:eur_irt', content.EXCHANGE_RATE_CACHE_TTL, json.dumps({'eur_to_irt': round(rate_irt, 2)}))
    return rate_irt
