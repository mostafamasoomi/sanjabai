"""
Public content endpoints: about, features, discounts, catalog, pricing API,
exchange rate, org default model.
"""
from __future__ import annotations

import os
import json
import re
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
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
from database import async_session, rds, _http, LITELLM_HOST, ADMIN_TOKEN
import logging

logger = logging.getLogger(__name__)
from models import AboutContent, Feature, Discount, ProxyConfig, Pricing
from dependencies import admin_required

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


# ── Markup (profit percentage) ─────────────────────────────────
#
# Two levels, resolved the same way everywhere a price is produced: a
# per-model override (model_catalog.markup_pct) wins when it is set (not
# NULL); a model with no override inherits the global percentage stored in
# app_setting under GLOBAL_MARKUP_SETTING_KEY (migrations/0030_markup_pct.sql,
# seeded at 0 so applying that migration is a strict no-op on prices).
#
# Every price consumer -- the catalog/pricing endpoints below AND chat.py's
# billing path (_record_usage) -- MUST resolve the effective percentage via
# get_effective_markup_pct()/resolve_markup_pct() and turn it into a served
# number via apply_markup(), rather than reimplementing the arithmetic, so
# the price a user is shown and the price they are charged are always
# literally the same computation. See NEXT-SESSION.md section 12.

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
    served number. content.py's catalog/pricing endpoints and chat.py's
    billing path (_record_usage) both call this -- never reimplement the
    multiplication -- so the displayed price and the billed price for the
    same model are always the identical integer.
    """
    try:
        base = float(base_per_million or 0)
    except (TypeError, ValueError):
        base = 0.0
    return round(base * (1 + (pct or 0) / 100))


# ── Catalog helpers ─────────────────────────────────────────────

def _catalog_row_to_item(m: dict[str, Any], rate_irt: float = 126488, global_markup_pct: float = 0) -> dict[str, Any]:
    """Map a model_catalog DB row to the camelCase catalog contract.

    When PUBLIC_MODEL_IDS_ENABLED is on, serves `public_id` (never `id`,
    which may still carry the upstream route prefix -- see migrations/
    0028_public_model_ids.sql). `_load_catalog_rows` already filters to
    `public_id IS NOT NULL` in that case, so `m['public_id']` is always
    present here when the flag is on; the `or m['id']` fallback only matters
    for callers that pass a row _load_catalog_rows wouldn't have (defensive,
    not expected to trigger in the flag-on path).

    ``global_markup_pct`` is the caller's already-fetched (cached) global
    markup percentage (see get_global_markup_pct); this function resolves
    the effective per-model percentage (row override wins) and applies it
    to every price field via apply_markup -- the same function chat.py's
    billing path must call, so the displayed and billed price agree.
    """
    served_id = (m.get('public_id') or m['id']) if _public_ids_enabled() else m['id']
    effective_pct = resolve_markup_pct(m.get('markup_pct'), global_markup_pct)
    return {
        'id': served_id,
        # 'providerModelId' / 'provider' (internal routing id, e.g. "bynara")
        # are intentionally NOT exposed here — end users must never see
        # which upstream serves a model, only admins do (see
        # GET /admin/catalog/models).
        'displayName': m['display_name'],
        'description': m.get('description'),
        'modalities': m.get('modalities') or {'input': ['text'], 'output': ['text']},
        'capabilities': m.get('capabilities') or [],
        'recommendedFor': m.get('recommended_for') or [],
        'contextWindow': m['context_window'],
        'maxOutputTokens': m.get('max_output_tokens'),
        'pricing': {
            'currency': m.get('currency') or 'IRT',
            'inputPerMillion': apply_markup(m.get('input_per_million'), effective_pct),
            'outputPerMillion': apply_markup(m.get('output_per_million'), effective_pct),
            'cachedInputPerMillion': apply_markup(m['cached_input_per_million'], effective_pct) if m.get('cached_input_per_million') is not None else None,
            'reasoningPerMillion': apply_markup(m['reasoning_per_million'], effective_pct) if m.get('reasoning_per_million') is not None else None,
            'priceVersion': m.get('price_version') or 'v1',
            'effectiveFrom': m.get('effective_from'),
            'usd': {
                'inputPerMillion': float(m.get('usd_input_per_million') or 0),
                'outputPerMillion': float(m.get('usd_output_per_million') or 0),
            },
        },
        'availability': m.get('availability') or 'available',
        'audience': m.get('audience') or ['consumer', 'developer'],
        'rateLimit': m.get('rate_limit'),
        'deprecatedAt': m.get('deprecated_at'),
        'lastVerifiedAt': m.get('last_verified_at'),
        'provenance': m.get('provenance') or 'admin-approved',
    }


async def _load_catalog_rows() -> list[dict[str, Any]]:
    """Load approved catalog from DB; return [] if unavailable/empty.

    When PUBLIC_MODEL_IDS_ENABLED is on, rows with no public_id (collision
    losers and anything an admin hasn't named yet -- see migrations/
    0028_public_model_ids.sql) are excluded: they must not be publicly
    listable, but they still work as chat ids (chat.py's resolver keeps
    accepting their own `id`/`provider_model_id` indefinitely).
    """
    if async_session is None:
        return []
    try:
        async with async_session() as session:
            public_filter = " AND public_id IS NOT NULL" if _public_ids_enabled() else ""
            res = await session.execute(sqlalchemy.text(
                'SELECT id, provider_model_id, provider, display_name, description, '
                'modalities, capabilities, recommended_for, context_window, max_output_tokens, '
                'currency, input_per_million, output_per_million, cached_input_per_million, '
                'reasoning_per_million, price_version, effective_from, availability, audience, '
                'rate_limit, deprecated_at, last_verified_at, provenance, '
                'usd_input_per_million, usd_output_per_million, public_id, markup_pct '
                "FROM model_catalog WHERE availability = 'available' AND NOT (audience @> '[\"admin\"]')"
                f"{public_filter} ORDER BY provider, id"
            ))
            return [dict(r._mapping) for r in res.fetchall()]
    except Exception:
        return []


async def _litellm_fallback_catalog() -> tuple[list[dict[str, Any]], list[str]]:
    """Build a minimal fallback catalog from litellm when DB has no entries.

    Returns ``(items, health_keys)``. ``items`` is the user-facing list (no
    provider/providerModelId — same rule as `_catalog_row_to_item`).
    ``health_keys[i]`` is the raw upstream id for ``items[i]`` (the ``mid``
    before it gets normalized into the public ``id`` via
    ``mid.replace('/', '-').lower()``); callers need it to join against
    `model_health` state, since the normalized public id won't match there.
    """
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    health_keys: list[str] = []
    try:
        r = await _http.get(f"{LITELLM_HOST}/v1/models", timeout=8)
        if r.status_code == 200:
            for entry in r.json().get('data', []):
                mid = str(entry.get('id') or '').strip()
                if not mid:
                    continue
                items.append({
                    'id': mid.replace('/', '-').lower(),
                    # No 'provider' key — same rule as _catalog_row_to_item:
                    # this fallback list is also user-facing.
                    'displayName': mid,
                    'description': None,
                    'modalities': {'input': ['text'], 'output': ['text']},
                    'capabilities': ['chat'], 'recommendedFor': [],
                    'contextWindow': 8192, 'maxOutputTokens': None,
                    'pricing': {
                        'currency': 'IRT', 'inputPerMillion': 0, 'outputPerMillion': 0,
                        'cachedInputPerMillion': None, 'reasoningPerMillion': None,
                        'priceVersion': 'fallback', 'effectiveFrom': now,
                    },
                    'availability': 'available',
                    'audience': ['consumer', 'developer'],
                    'rateLimit': None, 'deprecatedAt': None,
                    'lastVerifiedAt': now, 'provenance': 'fallback',
                })
                health_keys.append(mid)
    except Exception:
        pass
    return items, health_keys


# ── Routes ──────────────────────────────────────────────────────

@router.get('/v1/models')
async def list_models(request: Request) -> dict[str, Any]:
    """Return only models that are available in the catalog and actually working."""
    models = []
    if async_session is not None:
        try:
            global_markup_pct = await get_global_markup_pct()
            async with async_session() as session:
                public_only = _public_ids_enabled()
                public_filter = " AND public_id IS NOT NULL" if public_only else ""
                res = await session.execute(
                    sqlalchemy.text(
                        "SELECT id, provider_model_id, public_id, display_name, context_window, availability, "
                        "input_per_million, output_per_million, currency, "
                        "usd_input_per_million, usd_output_per_million, markup_pct "
                        "FROM model_catalog WHERE availability = 'available' AND NOT (audience @> '[\"admin\"]')"
                        f"{public_filter} ORDER BY id"
                    )
                )
                for row in res.fetchall():
                    usd_in = float(row.usd_input_per_million or 0)
                    usd_out = float(row.usd_output_per_million or 0)
                    effective_pct = resolve_markup_pct(row.markup_pct, global_markup_pct)
                    # public_id when the flag is on (never provider_model_id,
                    # which leaks the upstream route -- see migrations/
                    # 0028_public_model_ids.sql); provider_model_id unchanged
                    # otherwise, byte-for-byte as before this flag existed.
                    served_id = (row.public_id or row.provider_model_id) if public_only else row.provider_model_id
                    models.append({
                        'id': served_id, 'object': 'model', 'created': 0,
                        'owned_by': 'sanjabai', 'display_name': row.display_name,
                        'context_window': row.context_window,
                        'pricing': {
                            'currency': row.currency or 'IRT',
                            'inputPerMillion': apply_markup(row.input_per_million, effective_pct),
                            'outputPerMillion': apply_markup(row.output_per_million, effective_pct),
                            'usd': {
                                'inputPerMillion': usd_in,
                                'outputPerMillion': usd_out,
                            },
                        },
                    })
        except Exception:
            pass
    # Fallback to LiteLLM if DB has no models
    if not models:
        try:
            r = await _http.get(f"{LITELLM_HOST}/v1/models", timeout=5)
            if r.status_code == 200:
                models = r.json().get('data', [])
        except Exception:
            pass
    return {'object': 'list', 'data': models}


@router.get('/catalog/models')
async def catalog_models(request: Request) -> JSONResponse:
    """Approved model catalog from DB, with litellm fallback when DB is empty."""
    cached = await rds.get('cache:catalog:models')
    if cached:
        return JSONResponse(json.loads(cached))
    rate_irt, _stale_markup_pct = await _get_exchange_rate()
    # Markup is resolved fresh here (5-minute cache), not from the exchange
    # rate's hour-long cache (_stale_markup_pct, discarded) -- otherwise an
    # admin's markup change could take up to an hour to reach this endpoint
    # while chat.py's billing path (which also calls get_global_markup_pct)
    # already sees it, breaking the display/billed-price agreement.
    global_markup_pct = await get_global_markup_pct()
    rows = await _load_catalog_rows()
    if rows:
        data = [_catalog_row_to_item(r, rate_irt, global_markup_pct) for r in rows]
        # Health-lookup keys taken from the source DB rows (server-side only,
        # never serialized to the client) — NOT from the public dicts above,
        # which no longer carry providerModelId.
        health_keys: list[str | None] = [r.get('provider_model_id') for r in rows]
        source = 'approved-catalog'
    else:
        data, health_keys = await _litellm_fallback_catalog()
        source = 'fallback'

    # Attach live health so clients can hide models that are not answering,
    # instead of shipping their own hard-coded list of "working" ids.
    try:
        from model_health import health_map

        states = await health_map()
        for item, health_key in zip(data, health_keys):
            state = states.get(health_key) or states.get(item.get('id'))
            item['health'] = state or {
                'status': 'unknown',
                'successRate': None,
                'latencyP50Ms': None,
                'latencyP95Ms': None,
                'sampleCount': 0,
                'lastOkAt': None,
                'lastError': None,
                'checkedAt': None,
            }
    except Exception:
        for item in data:
            item.setdefault('health', {'status': 'unknown', 'sampleCount': 0})

    result = jsonable_encoder({
        'data': data,
        'generatedAt': datetime.now(timezone.utc),
        'source': source,
    })
    await rds.setex('cache:catalog:models', CATALOG_CACHE_TTL, json.dumps(result))
    return JSONResponse(result)


@router.get('/catalog/pricing')
async def catalog_pricing(request: Request) -> JSONResponse:
    """Versioned pricing for catalog models (falls back to pricing table)."""
    cached = await rds.get('cache:catalog:pricing')
    if cached:
        return JSONResponse(json.loads(cached))
    rows = await _load_catalog_rows()
    global_markup_pct = await get_global_markup_pct()
    pricing = []
    for m in rows:
        # Same public_id substitution as _catalog_row_to_item -- see there.
        served_id = (m.get('public_id') or m['id']) if _public_ids_enabled() else m['id']
        effective_pct = resolve_markup_pct(m.get('markup_pct'), global_markup_pct)
        pricing.append({
            'id': served_id,
            'currency': m.get('currency') or 'IRT',
            'inputPerMillion': apply_markup(m.get('input_per_million'), effective_pct),
            'outputPerMillion': apply_markup(m.get('output_per_million'), effective_pct),
            'cachedInputPerMillion': apply_markup(m['cached_input_per_million'], effective_pct) if m.get('cached_input_per_million') is not None else None,
            'reasoningPerMillion': apply_markup(m['reasoning_per_million'], effective_pct) if m.get('reasoning_per_million') is not None else None,
            'priceVersion': m.get('price_version') or 'v1',
            'effectiveFrom': m.get('effective_from'),
        })
    if not pricing and async_session is not None:
        try:
            async with async_session() as session:
                res = await session.execute(Pricing.__table__.select())
                for r in res.fetchall():
                    d = dict(r._mapping)
                    pricing.append({
                        'id': d['model'],
                        'currency': d.get('currency') or 'IRT',
                        'inputPerMillion': d.get('input_per_million') or 0,
                        'outputPerMillion': d.get('output_per_million') or 0,
                        'cachedInputPerMillion': None, 'reasoningPerMillion': None,
                        'priceVersion': 'legacy',
                        'effectiveFrom': d.get('updated_at'),
                    })
        except Exception:
            pass
    result = jsonable_encoder({
        'data': pricing,
        'generatedAt': datetime.now(timezone.utc),
        'priceVersion': pricing[0]['priceVersion'] if pricing else 'v1',
    })
    await rds.setex('cache:catalog:pricing', CATALOG_CACHE_TTL, json.dumps(result))
    return JSONResponse(result)


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


async def _compute_exchange_rate() -> tuple[float, int]:
    """Return the live USD→IRT (Toman) rate and markup percentage.

    Order of resolution:
      1. A manual DB override (exchange_rate_overrides) if present.
      2. Live tgju.org market rate (authoritative for IRT).
      3. Fallback to open.er-api.com.
      4. Hardcoded fallback constant.
    """
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
                    return float(row.rate), markup_pct
    except Exception:
        pass

    # 2. Live tgju.org
    rate_irr = await _fetch_tgju_rate()

    # 3. Fallback to open.er-api.com
    if rate_irr is None:
        try:
            resp2 = await _http.get('https://open.er-api.com/v6/latest/USD', follow_redirects=True, timeout=10)
            resp2.raise_for_status()
            rate_irr = float(resp2.json()['rates']['IRR'])
        except Exception:
            pass

    # 4. Hardcoded fallback
    if rate_irr is None:
        rate_irr = 1_264_884

    rate_irt = rate_irr / 10  # IRR → IRT (Toman)
    return rate_irt, markup_pct


async def _get_exchange_rate() -> tuple[float, int]:
    """Redis-cached USD→IRT rate.

    The uncached resolver reaches out to tgju.org and open.er-api.com. Without a
    cache every catalog cache miss paid that cost on the request path, which is
    what made the first page load after login take 15 seconds. A negative result
    is cached too (for a shorter window) so an upstream outage cannot turn every
    request into a fresh timeout.
    """
    try:
        cached = await rds.get(EXCHANGE_RATE_CACHE_KEY)
        if cached:
            payload = json.loads(cached)
            base = float(payload["rate_irt"])
            return base + USD_IRT_FLAT_MARKUP, int(payload.get("markup_pct", 0))
    except Exception as e:
        logger.warning("exchange rate cache read failed: %s", e)

    rate_irt, markup_pct = await _compute_exchange_rate()

    try:
        ttl = EXCHANGE_RATE_CACHE_TTL if rate_irt else EXCHANGE_RATE_NEGATIVE_TTL
        await rds.setex(
            EXCHANGE_RATE_CACHE_KEY,
            ttl,
            json.dumps({"rate_irt": rate_irt, "markup_pct": markup_pct}),
        )
    except Exception as e:
        logger.warning("exchange rate cache write failed: %s", e)

    # Redis holds the bare market rate; the margin is added on the way out so a
    # markup change takes effect on the next call instead of waiting out the TTL.
    return rate_irt + USD_IRT_FLAT_MARKUP, markup_pct


async def _fetch_tgju_eur_rate() -> float | None:
    """Fetch the live EUR→IRR market rate from tgju.org.

    Async twin of _fetch_tgju_rate. Returns IRR (Rial), or None on failure.
    """
    try:
        resp = await _http.get(
            "https://www.tgju.org/profile/price_eur",
            follow_redirects=True,
            timeout=TGJU_TIMEOUT_S,
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
    markup_pct = await get_global_markup_pct()
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
            resp2 = await _http.get('https://open.er-api.com/v6/latest/EUR', follow_redirects=True, timeout=10)
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
    await rds.setex('exchange_rate:eur_irt', EXCHANGE_RATE_CACHE_TTL, json.dumps({'eur_to_irt': round(rate_irt, 2)}))
    return rate_irt


@router.get('/pricing-table')
@router.get('/api/pricing')
async def api_pricing(request: Request) -> JSONResponse:
    """Return all active model pricing in Toman.

    Dual paths for Next rewrite compatibility (`/api/pricing` → `/pricing-table`).
    """
    cached = await rds.get('cache:api:pricing')
    if cached:
        return JSONResponse(json.loads(cached))

    rate_irt, markup_pct = await _get_exchange_rate()
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    # NOTE: `models_out` is built but deliberately NOT returned below (this
    # endpoint currently answers with `generatedAt` only). It is kept as a
    # ready-made shape, so it must stay leak-free: `provider` is the internal
    # upstream routing id and this route is UNAUTHENTICATED. Anyone who later
    # wires `models_out` into the response must not reintroduce it — end users
    # never see which upstream serves a model (see GET /admin/catalog/models).
    models_out = []
    async with async_session() as session:
        from sqlalchemy import text as sql_text
        res = await session.execute(sql_text("""
            SELECT DISTINCT ON (model)
                model, input_per_million, output_per_million, currency, source, price_version, effective_from
            FROM pricing
            WHERE effective_to IS NULL
            ORDER BY model, effective_from DESC, price_version DESC
        """))
        rows = [dict(r._mapping) for r in res.fetchall()]

    for r in rows:
        models_out.append({
            'model': r['model'],
            'inputPerMillion': r['input_per_million'],
            'outputPerMillion': r['output_per_million'],
            'currency': r['currency'] or 'IRT', 'source': r['source'],
            'priceVersion': r['price_version'],
            'effectiveFrom': r['effective_from'].isoformat() if r['effective_from'] else None,
        })

    result = jsonable_encoder({
        'generatedAt': datetime.now(timezone.utc).isoformat(),
    })
    await rds.setex('cache:api:pricing', 120, json.dumps(result))
    return JSONResponse(result)


@router.get('/about')
async def get_about() -> JSONResponse:
    cached = await rds.get('cache:about')
    if cached:
        return JSONResponse(json.loads(cached))
    if async_session is None:
        return JSONResponse({'title': 'درباره ما', 'body': ''})
    async with async_session() as session:
        res = await session.execute(AboutContent.__table__.select())
        row = res.fetchone()
        if not row:
            return JSONResponse({'title': 'درباره ما', 'body': ''})
        result = jsonable_encoder(dict(row._mapping))
    await rds.setex('cache:about', 120, json.dumps(result))
    return JSONResponse(result)


@router.get('/org/default-model')
async def get_org_default_model() -> JSONResponse:
    """Public endpoint: get org-wide default model (for chat fallback)."""
    cached = await rds.get('cache:org:default-model')
    if cached:
        return JSONResponse(json.loads(cached))
    if async_session is None:
        return JSONResponse({'default_model': ''})
    async with async_session() as session:
        res = await session.execute(ProxyConfig.__table__.select())
        row = res.fetchone()
        dm = row.default_model if row and hasattr(row, 'default_model') else ''
        result = {'default_model': dm}
    await rds.setex('cache:org:default-model', 120, json.dumps(result))
    return JSONResponse(result)


@router.get('/content/features')
async def public_features() -> JSONResponse:
    cached = await rds.get('cache:content:features')
    if cached:
        return JSONResponse(json.loads(cached))
    if async_session is None:
        return JSONResponse([])
    async with async_session() as session:
        res = await session.execute(Feature.__table__.select().where(Feature.active == True).order_by(Feature.order_idx))
        rows = [dict(r._mapping) for r in res.fetchall()]
    result = jsonable_encoder(rows)
    await rds.setex('cache:content:features', 120, json.dumps(result))
    return JSONResponse(result)


@router.get('/content/discounts')
async def public_discounts() -> JSONResponse:
    cached = await rds.get('cache:content:discounts')
    if cached:
        return JSONResponse(json.loads(cached))
    if async_session is None:
        return JSONResponse([])
    async with async_session() as session:
        res = await session.execute(Discount.__table__.select().where(Discount.active == True))
        rows = [{'code': r.code, 'percent': r.percent} for r in res.fetchall()]
    result = jsonable_encoder(rows)
    await rds.setex('cache:content:discounts', 120, json.dumps(result))
    return JSONResponse(result)


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
    # 1. Fetch fresh exchange rate (now live from tgju)
    await rds.delete('exchange_rate:usd_irt')  # force refresh
    rate_irt, markup_pct = await _get_exchange_rate()
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
        'exchange_source': 'tgju.org',
        'markup_pct': markup_pct,
        'models_matched': len(or_prices) // 3,
        'models_updated': updated,
        'unpriced_demoted': unpriced_demoted,
        'refreshed_at': datetime.now(timezone.utc).isoformat(),
    }


@router.post('/admin/refresh-pricing')
async def admin_refresh_pricing(request: Request) -> JSONResponse:
    """Admin endpoint to trigger a pricing refresh."""
    from dependencies import _get_user_id
    uid = await _get_user_id(request)
    # Allow if admin token in header
    admin_tok = request.headers.get('X-Admin-Token', '')
    if not uid and admin_tok != ADMIN_TOKEN:
        return JSONResponse({'detail': 'admin access required'}, status_code=403)
    result = await refresh_pricing()
    return JSONResponse(jsonable_encoder(result))

# ── Model Test (auto-recommend healthy) ──


# ponytail: test all models + auto-recommend healthy ones (concurrent)
@router.get("/admin/test-models")
async def test_all_models(request: Request):
    """Ping every model concurrently, return status, and mark healthy ones as recommended."""
    import httpx, asyncio
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            "SELECT provider_model_id, display_name FROM model_catalog WHERE availability='available'"
        ))
        rows = res.fetchall()
    
    async def test_one(client, row):
        mid, name = row.provider_model_id, row.display_name
        try:
            r = await client.post(
                f"{LITELLM_HOST}/v1/chat/completions",
                json={"model": mid, "messages": [{"role":"user","content":"hi"}], "max_tokens": 5},
                headers={}
            )
            ok = r.status_code == 200
            return {"id": mid, "name": name, "ok": ok, "status": r.status_code, "ms": r.elapsed.total_seconds() * 1000}
        except Exception as e:
            return {"id": mid, "name": name, "ok": False, "error": str(e)[:100]}
    
    async with httpx.AsyncClient(timeout=10) as client:
        results = await asyncio.gather(*[test_one(client, row) for row in rows])
    
    healthy_ids = [r["id"] for r in results if r["ok"]]
    if healthy_ids:
        async with async_session() as session:
            for mid in healthy_ids:
                await session.execute(
                    sqlalchemy.text("UPDATE model_catalog SET recommended_for = '[\"chat\"]' WHERE provider_model_id = :mid"),
                    {"mid": mid}
                )
            await session.commit()
        await rds.delete('cache:catalog:models')
    
    return JSONResponse({"results": results, "total": len(results), "ok": len(healthy_ids), "recommended": len(healthy_ids)})

# ponytail: image captcha generator
import io, random, base64
from PIL import Image, ImageDraw, ImageFont

@router.get("/captcha")
async def captcha_image(request: Request):
    """Generate a professional alphanumeric captcha image."""
    import string
    
    # 5 random characters (uppercase and digits, excluding ambiguous ones like O, 0, I, 1)
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    answer = "".join(random.choices(chars, k=5))
    
    # Store answer in redis for 5 minutes
    token = base64.urlsafe_b64encode(f"{random.getrandbits(64)}".encode()).decode()[:12]
    await rds.setex(f"captcha:{token}", 300, answer)
    
    W, H = 200, 70
    # Background color (off-white for contrast)
    img = Image.new("RGB", (W, H), (245, 245, 250))
    draw = ImageDraw.Draw(img)
    
    # Load font with fallback chain
    font = None
    for font_path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]:
        try:
            font = ImageFont.truetype(font_path, 42)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
        
    # Draw noise lines and arcs
    for _ in range(5):
        x1, y1 = random.randint(0, W), random.randint(0, H)
        x2, y2 = random.randint(0, W), random.randint(0, H)
        draw.line([(x1, y1), (x2, y2)], fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)), width=random.randint(1, 3))
        
    for _ in range(4):
        x1, y1 = random.randint(-50, W), random.randint(-50, H)
        x2, y2 = random.randint(x1, W+50), random.randint(y1, H+50)
        draw.arc([x1, y1, x2, y2], random.randint(0, 180), random.randint(180, 360), fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)), width=random.randint(1, 3))

    # Draw individual characters with rotation and slight jitter
    x_offset = 15
    for char in answer:
        # Create a blank image for the char
        char_img = Image.new("RGBA", (45, 60), (255, 255, 255, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_color = (random.randint(20, 80), random.randint(20, 80), random.randint(20, 80))
        char_draw.text((0, 0), char, font=font, fill=char_color)
        
        # Rotate
        char_img = char_img.rotate(random.randint(-30, 30), expand=1, resample=Image.BICUBIC)
        
        # Paste into main image
        y_offset = random.randint(0, 10)
        img.paste(char_img, (x_offset, y_offset), char_img)
        x_offset += random.randint(30, 36)

    # Add dot noise
    for _ in range(120):
        x, y = random.randint(0, W-1), random.randint(0, H-1)
        draw.point((x, y), fill=(random.randint(50, 150), random.randint(50, 150), random.randint(50, 150)))
        
    buf = io.BytesIO()
    img.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    
    return JSONResponse({"captcha": f"data:image/png;base64,{b64}", "token": token})

