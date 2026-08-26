"""
Public content endpoints: about, features, discounts, catalog, pricing API,
exchange rate, org default model.

This is the hub of a module split across `content.py` (this file),
`content_catalog.py`, `content_eur_rate.py`, `content_refresh.py`, and
`content_misc.py` -- done purely to stay under the house 500-line cap, with
zero behaviour change. The module path `content` keeps exposing the same
`router` object under the same name (`app.py` does
`from content import router as content_router`), and every name any other
module or test previously imported from `content` is still importable from
`content` after the split -- either defined here directly, or re-exported
from a satellite near the bottom of this file.

IMPORT/MONKEYPATCH CONTRACT -- read before moving anything again. The test
suite patches several names directly on this module
(`content_mod.get_global_markup_pct = ...` via `unittest.mock.patch.object`,
see tests/test_margin_guard_wiring.py and tests/test_exchange_rate_source.py for
`get_global_markup_pct`, `_get_exchange_rate`, `_fetch_tgju_rate`, `_http`,
and `content.get_exchange_rate_meta`), and several external modules
(admin_catalog.py, exchange_rate_admin.py, hermes.py, images.py,
chat_billing.py, conversations.py, services/margin.py) reach these same
names via a deferred `from content import X` / `import content` inside a
function body, which re-reads the *current* attribute off this module at
call time -- so those keep working unchanged no matter which file now
defines the callee, as long as it is reachable as `content.<name>`.

The satellites (content_catalog.py, content_eur_rate.py, content_refresh.py)
call back into the monkeypatch-sensitive functions defined below
(`get_global_markup_pct`, `_get_exchange_rate`, `_public_ids_enabled`,
`apply_markup`, `resolve_markup_pct`) via `content.<name>(...)` -- an
attribute read on this module at CALL time, never a bare name and never
`from content import X` at their own module scope -- because Python
resolves a bare global against the *defining* module's namespace, not this
one. This is the same late-binding pattern chat_web.py / chat_search.py use
for `chat.<name>`; see their IMPORT CONTRACT docstrings for the hazard this
avoids. content_misc.py has no such calls and needs no such contract (see
its own docstring).
"""
from __future__ import annotations

import os
import json
import re
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


# Provider display names (moved to catalog response)
_PROVIDER_DISPLAY = {
    "bynara": "byNara",
    "google": "Google",
    "freellmapi": "FreeLLMAPI",
    "openrouter": "OpenRouter",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
}
from database import async_session, rds, _http
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

EXCHANGE_RATE_CACHE_TTL = 3600  # 1 hour
EXCHANGE_RATE_CACHE_KEY = "exchange_rate:usd_irt:resolved"
EXCHANGE_RATE_NEGATIVE_TTL = 300  # cache upstream failures briefly too
TGJU_TIMEOUT_S = 4.0  # was an effectively unbounded 15s through a dead proxy
CATALOG_CACHE_TTL = 600

# Kill switch for migrations/0028_public_model_ids.sql's model_catalog.public_id
# column: default OFF so behavior is byte-for-byte identical to before the
# migration until this is flipped on deliberately. When OFF, every public
# response below keeps serving `id`/`provider_model_id` exactly as it does
# today. When ON, `/v1/models`, `/catalog/models`, and `/catalog/pricing`
# serve `public_id` instead (never `id`/`provider_model_id`, which leak the
# upstream route), and rows with no public_id (collision losers, and any row
# an admin hasn't named yet) are simply absent from these listings.
#
# Read fresh on every call (not cached at import time) so a test/deploy can
# flip it without a process restart. chat.py's model-string RESOLVER
# (_resolve_public_model) is intentionally NOT gated by this flag -- it is a
# pure superset (an old id always still resolves) and must keep working even
# with this flag off, so flipping it back off never breaks a client that
# already adopted a `sanjab/*` id.
def _public_ids_enabled() -> bool:
    return os.getenv('PUBLIC_MODEL_IDS_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes')


# Flat margin added to the USD->IRT rate, in Toman. Applied centrally in
# _get_exchange_rate so every price consumer derives the same effective
# rate.
#
# 2026-08-22: this comment used to say a per-model markup was rejected
# because it "would make margin wildly uneven across tiers." The owner has
# now explicitly asked for exactly that -- a profit percentage settable
# per model or globally (see get_global_markup_pct / resolve_markup_pct /
# apply_markup below, and migrations/0030_markup_pct.sql) -- so that
# decision is reversed here; the owner's decision wins over the old
# rationale. USD_IRT_FLAT_MARKUP and the percentage markup are two
# SEPARATE things that COMPOSE, not alternatives to each other: the
# exchange rate is `market_rate + USD_IRT_FLAT_MARKUP` (a flat Toman
# amount, applied once to the USD->IRT rate), and each model's served
# price is `base_price * (1 + effective_markup_pct / 100)` (a
# proportional amount, applied per model on top of that rate). Do not fold
# one into the other.
USD_IRT_FLAT_MARKUP = float(os.getenv('USD_IRT_FLAT_MARKUP', '2000'))

# 2026-08-25: now admin-editable (was env-var-only). The getter,
# get_flat_markup_toman(), lives in services/exchange_sources.py (this file
# is at the 500-line cap) -- see its docstring for the cache/DB shape and
# why its fail-open value is this constant, never 0.


# ── Markup (profit percentage) ─────────────────────────────────
#
# Two levels, resolved the same way everywhere a price is produced: a
# per-model override (model_catalog.markup_pct) wins when it is set (not
# NULL); a model with no override inherits the global percentage stored in
# app_setting under GLOBAL_MARKUP_SETTING_KEY (migrations/0030_markup_pct.sql,
# seeded at 0 so applying that migration is a strict no-op on prices).
#
# Every price consumer -- the catalog/pricing endpoints (content_catalog.py)
# AND chat.py's billing path (_record_usage) -- MUST resolve the effective
# percentage via get_effective_markup_pct()/resolve_markup_pct() and turn it
# into a served number via apply_markup(), rather than reimplementing the
# arithmetic, so the price a user is shown and the price they are charged
# are always literally the same computation. See NEXT-SESSION.md section 12.

GLOBAL_MARKUP_SETTING_KEY = 'global_markup_pct'
MARKUP_CACHE_KEY = 'cache:markup:global_pct'
MARKUP_CACHE_TTL = 300  # admin writes also delete this key immediately (admin_catalog.py)


async def get_global_markup_pct() -> float:
    """Redis-cached global markup percentage from app_setting.

    Degrades to 0 -- never to some other default -- on any cache-read
    failure, missing row, or DB error: failing open to a nonzero markup
    would silently overcharge every model that has no per-model override.
    """
    try:
        cached = await rds.get(MARKUP_CACHE_KEY)
        if cached is not None:
            return float(json.loads(cached))
    except Exception as e:
        # Mirrors _get_exchange_rate's idiom: log and fall through to the DB
        # rather than assume any particular value -- a cache outage alone is
        # not a reason to serve 0% when the DB still has the real setting.
        logger.warning("global markup cache read failed: %s", e)

    pct = 0.0
    try:
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(sqlalchemy.text(
                    'SELECT value FROM app_setting WHERE key = :k'
                ), {'k': GLOBAL_MARKUP_SETTING_KEY})
                row = res.fetchone()
                if row is not None and row.value is not None:
                    val = row.value
                    pct = float(val.get('pct', 0) or 0) if isinstance(val, dict) else float(val)
    except Exception as e:
        logger.warning("global markup DB read failed: %s", e)
        return 0.0

    try:
        await rds.setex(MARKUP_CACHE_KEY, MARKUP_CACHE_TTL, json.dumps(pct))
    except Exception as e:
        logger.warning("global markup cache write failed: %s", e)

    return pct


def resolve_markup_pct(model_markup_pct: Any, global_pct: float) -> float:
    """Per-model override wins; NULL/None means "inherit the global"."""
    if model_markup_pct is None:
        return global_pct
    try:
        return float(model_markup_pct)
    except (TypeError, ValueError):
        return global_pct


async def get_effective_markup_pct(model_markup_pct: Any = None) -> float:
    """Effective percentage for one model: its own override if set, else the
    (cached) global. The single entry point a caller with only one model to
    price should use (e.g. chat.py's billing path); catalog listings that
    render many rows should fetch the global once via get_global_markup_pct()
    and call resolve_markup_pct() per row instead, to avoid a Redis round
    trip per row."""
    return resolve_markup_pct(model_markup_pct, await get_global_markup_pct())


def apply_markup(base_per_million: Any, pct: float) -> int:
    """Apply a profit percentage to a per-million rate, rounded to the
    nearest whole Toman.

    This is the ONE function that turns (base price, effective pct) into a
    served number. content_catalog.py's catalog/pricing endpoints and
    chat.py's billing path (_record_usage) both call this -- never
    reimplement the multiplication -- so the displayed price and the billed
    price for the same model are always the identical integer.
    """
    try:
        base = float(base_per_million or 0)
    except (TypeError, ValueError):
        base = 0.0
    return round(base * (1 + (pct or 0) / 100))


# ── Exchange rate (USD->IRT) ────────────────────────────────────

async def _fetch_tgju_rate() -> float | None:
    """Fetch the live USD→IRR market rate from tgju.org.

    Uses the shared async httpx client so the event loop stays free. Returns the
    rate in IRR (Rial); callers convert to IRT (Toman) by /10. Returns None on any
    failure so callers can fall back.
    """
    try:
        resp = await _http.get(
            "https://www.tgju.org/profile/price_dollar_rl",
            follow_redirects=True,
            timeout=TGJU_TIMEOUT_S,
        )
        resp.raise_for_status()
        m = re.search(r'class="price"[^>]*>([\d,]+)<', resp.text)
        if m:
            return float(m.group(1).replace(",", ""))
    except Exception as e:
        logger.warning("tgju USD rate fetch failed: %s", e)
    return None


async def _compute_exchange_rate() -> tuple[float, int, str]:
    """Return the live USD→IRT (Toman) rate, markup percentage, and provenance.

    Order of resolution (the returned `source` records which tier won):
      1. A manual DB override (exchange_rate_overrides) if present -> 'db_override'.
      2. Live tgju.org market rate (authoritative for IRT) -> 'tgju'.
      2b. Admin-configured sources (Bonbast.com + any admin-added custom
          source, migrations/0047_exchange_sources.sql) -> the source's own
          `source_key`, e.g. 'bonbast'. See services/exchange_sources.py.
      3. Fallback to open.er-api.com -> 'er_api'.
      4. Hardcoded fallback constant -> 'hardcoded_fallback'.

    Tiers 2, 2b, and 3 are each passed through
    services.exchange_sources.is_plausible_usd_irt_toman() before being
    trusted -- an order-of-magnitude sanity band that rejects a scrape gone
    wrong (garbage number, or a Rial/Toman mixup) rather than ever letting
    it reach the catalogue. Tier 1 (an explicit admin override) and tier 4
    (a fixed code constant) are not run through the band: an override is
    already a deliberate human decision, and the hardcoded constant cannot
    itself be "a bad scrape".
    """
    from services.exchange_sources import is_plausible_usd_irt_toman, resolve_configured_sources

    markup_pct = await get_global_markup_pct()
    rate_irr = None

    # 1. Manual DB override (highest priority)
    try:
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(sqlalchemy.text(
                    "SELECT rate FROM exchange_rate_overrides "
                    "WHERE from_currency='USD' AND to_currency='IRT' AND active=TRUE "
                    "ORDER BY id DESC LIMIT 1"
                ))
                row = res.fetchone()
                if row:
                    # stored value is already IRT (Toman)
                    return float(row.rate), markup_pct, 'db_override'
    except Exception:
        pass

    # 2. Live tgju.org
    rate_irr = await _fetch_tgju_rate()
    source = 'tgju'
    if rate_irr is not None and not is_plausible_usd_irt_toman(rate_irr / 10):
        logger.warning("tgju USD rate %s Toman failed the sanity band, ignoring", rate_irr / 10)
        rate_irr = None

    # 2b. Admin-configured sources (Bonbast.com + any custom source)
    if rate_irr is None:
        configured_rate, configured_source = await resolve_configured_sources()
        if configured_rate is not None:
            return configured_rate, markup_pct, configured_source

    # 3. Fallback to open.er-api.com
    if rate_irr is None:
        source = 'er_api'
        try:
            resp2 = await _http.get('https://open.er-api.com/v6/latest/USD', follow_redirects=True, timeout=10)
            resp2.raise_for_status()
            candidate_irr = float(resp2.json()['rates']['IRR'])
            if is_plausible_usd_irt_toman(candidate_irr / 10):
                rate_irr = candidate_irr
            else:
                logger.warning("er_api USD rate %s Toman failed the sanity band, ignoring", candidate_irr / 10)
        except Exception:
            pass

    # 4. Hardcoded fallback
    if rate_irr is None:
        source = 'hardcoded_fallback'
        rate_irr = 1_264_884

    rate_irt = rate_irr / 10  # IRR → IRT (Toman)
    return rate_irt, markup_pct, source


async def _get_exchange_rate() -> tuple[float, int]:
    """Redis-cached USD→IRT rate.

    The uncached resolver reaches out to tgju.org and open.er-api.com. Without a
    cache every catalog cache miss paid that cost on the request path, which is
    what made the first page load after login take 15 seconds. A negative result
    is cached too (for a shorter window) so an upstream outage cannot turn every
    request into a fresh timeout.

    The flat Toman markup is resolved via get_flat_markup_toman() (own Redis
    cache key, DB-backed, admin-editable) FIRST -- before this function's own
    EXCHANGE_RATE_CACHE_KEY read/write -- purely so its own cache traffic
    never sits between this function's cache read and its cache write; the
    public 2-tuple contract and the EXCHANGE_RATE_CACHE_KEY payload shape
    are both unchanged.
    """
    from services.exchange_sources import get_flat_markup_toman
    flat_markup = await get_flat_markup_toman()

    try:
        cached = await rds.get(EXCHANGE_RATE_CACHE_KEY)
        if cached:
            payload = json.loads(cached)
            base = float(payload["rate_irt"])
            return base + flat_markup, int(payload.get("markup_pct", 0))
    except Exception as e:
        logger.warning("exchange rate cache read failed: %s", e)

    rate_irt, markup_pct, source = await _compute_exchange_rate()

    try:
        ttl = EXCHANGE_RATE_CACHE_TTL if rate_irt else EXCHANGE_RATE_NEGATIVE_TTL
        await rds.setex(
            EXCHANGE_RATE_CACHE_KEY,
            ttl,
            json.dumps({
                "rate_irt": rate_irt,
                "markup_pct": markup_pct,
                "source": source,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }),
        )
    except Exception as e:
        logger.warning("exchange rate cache write failed: %s", e)

    # Redis holds the bare market rate; the margin is added on the way out so a
    # markup change takes effect on the next call instead of waiting out the TTL.
    return rate_irt + flat_markup, markup_pct


async def get_exchange_rate_meta() -> dict:
    """Rate + provenance for the admin panel. Reuses `_get_exchange_rate()`'s
    resolution/cache-fill (no extra network call), then re-reads the raw cache
    entry for `source`/`fetched_at` -- missing on an old pre-deploy cache
    entry, reported as 'unknown'/None rather than raised."""
    from services.exchange_sources import get_flat_markup_toman
    rate_irt_effective, markup_pct = await _get_exchange_rate()
    flat_markup = await get_flat_markup_toman()  # own 300s cache, cheap on a repeat call
    bare = rate_irt_effective - flat_markup
    source, fetched_at, ttl_remaining = 'unknown', None, None
    try:
        cached = await rds.get(EXCHANGE_RATE_CACHE_KEY)
        if cached:
            payload = json.loads(cached)
            bare = float(payload.get("rate_irt", bare))
            source = payload.get("source") or 'unknown'
            fetched_at = payload.get("fetched_at")
        ttl_remaining = await rds.ttl(EXCHANGE_RATE_CACHE_KEY)
        if not isinstance(ttl_remaining, int) or ttl_remaining < 0:
            ttl_remaining = None
    except Exception as e:
        logger.warning("exchange rate meta cache read failed: %s", e)

    return {
        "rate_irt_bare": bare,
        "flat_markup_irt": flat_markup,
        "rate_irt_effective": bare + flat_markup,
        "markup_pct": markup_pct,
        "source": source,
        "fetched_at": fetched_at,
        "cache_ttl_remaining_s": ttl_remaining,
    }


@router.get('/exchange-rate')
@router.get('/api/exchange-rate')
async def api_exchange_rate() -> JSONResponse:
    """Return the current USD→IRT exchange rate with markup.

    Dual paths:
    - `/exchange-rate` — used by Next.js rewrite (`/api/exchange-rate` → backend `/exchange-rate`)
    - `/api/exchange-rate` — direct backend / external clients
    """
    cached = await rds.get('exchange_rate:usd_irt')
    if cached:
        return JSONResponse(json.loads(cached))

    # 1. Check DB override first (market rate)
    rate_irt = None
    source = 'fallback'
    markup_pct = await get_global_markup_pct()
    try:
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(sqlalchemy.text(
                    "SELECT rate FROM exchange_rate_overrides "
                    "WHERE from_currency='USD' AND to_currency='IRT' AND active=TRUE "
                    "ORDER BY id DESC LIMIT 1"
                ))
                row = res.fetchone()
                if row:
                    rate_irt = float(row.rate)
                    source = 'manual-override'
    except Exception:
        pass

    # 2. Primary: tgju.org (Iran market, live)
    if rate_irt is None:
        rate_irr = None
        try:
            import re, urllib.request as _ur
            # No hard-coded backhaul-proxy IP here — this repo is public.
            # HTTP(S)_PROXY is the same env var the Bynara traffic path uses
            # (see chat.py); when unset we just go direct.
            proxy_url = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
            if proxy_url:
                _opener = _ur.build_opener(_ur.ProxyHandler({"http": proxy_url, "https": proxy_url}))
            else:
                _opener = _ur.build_opener()
            _resp = _opener.open("https://www.tgju.org/profile/price_dollar_rl", timeout=15)
            _text = _resp.read().decode()
            _m = re.search(r'class="price"[^>]*>([\d,]+)<', _text)
            if _m:
                rate_irr = float(_m.group(1).replace(",", ""))
                source = "tgju.org"
        except Exception:
            pass

# 3. Fallback to open.er-api.com
        if rate_irr is None:
            try:
                resp2 = await _http.get('https://open.er-api.com/v6/latest/USD', follow_redirects=True, timeout=10)
                resp2.raise_for_status()
                rate_irr = float(resp2.json()['rates']['IRR'])
                source = 'open.er-api.com'
            except Exception:
                pass

        if rate_irr is None:
            rate_irr = 1_264_884  # hardcoded fallback

        rate_irt = rate_irr / 10  # IRR → IRT (Toman)

    eur_to_irt = await _get_cached_eur_to_irt()

    result = jsonable_encoder({
        'usd_to_irt': round(rate_irt),
        'usd_to_irr': round(rate_irt * 10),
        # EUR rate is used internally to price the Hermes server product
        # (Hetzner bills in EUR); exposed here for admin/ops visibility only
        # -- never surfaced as a currency choice to end users.
        'eur_to_irt': round(eur_to_irt),
        'markup_pct': markup_pct,
        'source': source,
        'cached_at': datetime.now(timezone.utc).isoformat(),
    })
    await rds.setex('exchange_rate:usd_irt', EXCHANGE_RATE_CACHE_TTL, json.dumps(result))
    return JSONResponse(result)


# ── Satellite modules ───────────────────────────────────────────
#
# Imported after `router` (and every name a satellite calls back into via
# `content.<name>`) is defined above. Each import both registers that
# satellite's routes onto `router` and re-exports the names external callers
# import from `content` -- see this file's module docstring for the
# monkeypatch contract this relies on.
from content_eur_rate import _fetch_tgju_eur_rate, _get_eur_exchange_rate, _get_cached_eur_to_irt  # noqa: F401,E402
from content_catalog import _catalog_row_to_item, _load_catalog_rows, _litellm_fallback_catalog  # noqa: F401,E402 -- also registers /v1/models, /catalog/models, /catalog/pricing, /pricing-table, /api/pricing, /pricing
from content_refresh import OPENROUTER_API, _fetch_openrouter_prices, refresh_pricing  # noqa: F401,E402 -- also registers /admin/refresh-pricing
import content_misc  # noqa: F401,E402 -- registers /about, /org/default-model, /content/features, /content/discounts, /admin/test-models, /captcha
