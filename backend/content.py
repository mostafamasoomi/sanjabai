"""
Public content endpoints: about, features, discounts, catalog, pricing API,
exchange rate, org default model.
"""
from __future__ import annotations

import os
import json
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
from models import AboutContent, Feature, Discount, ProxyConfig, Pricing
from dependencies import admin_required

router = APIRouter()

EXCHANGE_RATE_CACHE_TTL = 3600  # 1 hour


# ── Catalog helpers ─────────────────────────────────────────────

def _catalog_row_to_item(m: dict[str, Any], rate_irt: float = 126488, markup_pct: int = 0) -> dict[str, Any]:
    """Map a model_catalog DB row to the camelCase catalog contract."""
    return {
        'id': m['id'],
        'providerModelId': m['provider_model_id'],
        'provider': m['provider'],
        'displayName': m['display_name'],
        'description': m.get('description'),
        'modalities': m.get('modalities') or {'input': ['text'], 'output': ['text']},
        'capabilities': m.get('capabilities') or [],
        'recommendedFor': m.get('recommended_for') or [],
        'contextWindow': m['context_window'],
        'maxOutputTokens': m.get('max_output_tokens'),
        'pricing': {
            'currency': m.get('currency') or 'IRT',
            'inputPerMillion': float(m.get('input_per_million') or 0),
            'outputPerMillion': float(m.get('output_per_million') or 0),
            'cachedInputPerMillion': float(m['cached_input_per_million']) if m.get('cached_input_per_million') is not None else None,
            'reasoningPerMillion': float(m['reasoning_per_million']) if m.get('reasoning_per_million') is not None else None,
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
    """Load approved catalog from DB; return [] if unavailable/empty."""
    if async_session is None:
        return []
    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                'SELECT id, provider_model_id, provider, display_name, description, '
                'modalities, capabilities, recommended_for, context_window, max_output_tokens, '
                'currency, input_per_million, output_per_million, cached_input_per_million, '
                'reasoning_per_million, price_version, effective_from, availability, audience, '
                'rate_limit, deprecated_at, last_verified_at, provenance, '
                'usd_input_per_million, usd_output_per_million '
                "FROM model_catalog WHERE availability = 'available' ORDER BY provider, id"
            ))
            return [dict(r._mapping) for r in res.fetchall()]
    except Exception:
        return []


async def _litellm_fallback_catalog() -> list[dict[str, Any]]:
    """Build a minimal fallback catalog from litellm when DB has no entries."""
    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    try:
        r = await _http.get(f"{LITELLM_HOST}/v1/models", timeout=8)
        if r.status_code == 200:
            for entry in r.json().get('data', []):
                mid = str(entry.get('id') or '').strip()
                if not mid:
                    continue
                provider = mid.split('/')[0] if '/' in mid else (entry.get('owned_by') or 'unknown')
                items.append({
                    'id': mid.replace('/', '-').lower(),
                    'providerModelId': mid, 'provider': provider, 'displayName': mid,
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
    except Exception:
        pass
    return items


# ── Routes ──────────────────────────────────────────────────────

@router.get('/v1/models')
async def list_models(request: Request) -> dict[str, Any]:
    """Return only models that are available in the catalog and actually working."""
    models = []
    if async_session is not None:
        try:
            rate_irt, markup_pct = await _get_exchange_rate()
            async with async_session() as session:
                res = await session.execute(
                    sqlalchemy.text(
                        "SELECT id, provider_model_id, display_name, context_window, availability, "
                        "input_per_million, output_per_million, currency, "
                        "usd_input_per_million, usd_output_per_million "
                        "FROM model_catalog WHERE availability = 'available' ORDER BY id"
                    )
                )
                for row in res.fetchall():
                    usd_in = float(row.usd_input_per_million or 0)
                    usd_out = float(row.usd_output_per_million or 0)
                    models.append({
                        'id': row.provider_model_id, 'object': 'model', 'created': 0,
                        'owned_by': 'multiai', 'display_name': row.display_name,
                        'context_window': row.context_window,
                        'pricing': {
                            'currency': row.currency or 'IRT',
                            'inputPerMillion': float(row.input_per_million or 0),
                            'outputPerMillion': float(row.output_per_million or 0),
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
    rate_irt, markup_pct = await _get_exchange_rate()
    rows = await _load_catalog_rows()
    if rows:
        data = [_catalog_row_to_item(r, rate_irt, markup_pct) for r in rows]
        source = 'approved-catalog'
    else:
        data = await _litellm_fallback_catalog()
        source = 'fallback'

    # Attach live health so clients can hide models that are not answering,
    # instead of shipping their own hard-coded list of "working" ids.
    try:
        from model_health import health_map

        states = await health_map()
        for item in data:
            state = states.get(item.get('providerModelId')) or states.get(item.get('id'))
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
    await rds.setex('cache:catalog:models', 120, json.dumps(result))
    return JSONResponse(result)


@router.get('/catalog/pricing')
async def catalog_pricing(request: Request) -> JSONResponse:
    """Versioned pricing for catalog models (falls back to pricing table)."""
    cached = await rds.get('cache:catalog:pricing')
    if cached:
        return JSONResponse(json.loads(cached))
    rows = await _load_catalog_rows()
    pricing = []
    for m in rows:
        pricing.append({
            'id': m['id'],
            'currency': m.get('currency') or 'IRT',
            'inputPerMillion': float(m.get('input_per_million') or 0),
            'outputPerMillion': float(m.get('output_per_million') or 0),
            'cachedInputPerMillion': float(m['cached_input_per_million']) if m.get('cached_input_per_million') is not None else None,
            'reasoningPerMillion': float(m['reasoning_per_million']) if m.get('reasoning_per_million') is not None else None,
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
    await rds.setex('cache:catalog:pricing', 120, json.dumps(result))
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
    markup_pct = 0
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
            proxy_url = os.getenv("HTTP_PROXY", "http://10.10.11.2:8888")
            _proxy = _ur.ProxyHandler({"http": proxy_url, "https": proxy_url})
            _opener = _ur.build_opener(_proxy)
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
    """Fetch live USD→IRR market rate from tgju.org via the HTTP proxy.

    Returns the rate in IRR (Rial); callers convert to IRT (Toman) by /10.
    Returns None on any failure so callers can fall back.
    """
    try:
        import re
        import urllib.request as _ur
        proxy_url = os.getenv("HTTP_PROXY", os.getenv("HTTPS_PROXY", "http://10.10.11.2:8888"))
        _proxy = _ur.ProxyHandler({"http": proxy_url, "https": proxy_url})
        _opener = _ur.build_opener(_proxy)
        _resp = _opener.open("https://www.tgju.org/profile/price_dollar_rl", timeout=15)
        _text = _resp.read().decode()
        _m = re.search(r'class="price"[^>]*>([\d,]+)<', _text)
        if _m:
            return float(_m.group(1).replace(",", ""))
    except Exception as e:
        print(f"[warn] _fetch_tgju_rate failed: {e}")
    return None


async def _get_exchange_rate() -> tuple[float, int]:
    """Return the live USD→IRT (Toman) rate and markup percentage.

    Order of resolution:
      1. A manual DB override (exchange_rate_overrides) if present.
      2. Live tgju.org market rate (authoritative for IRT).
      3. Fallback to open.er-api.com.
      4. Hardcoded fallback constant.
    """
    markup_pct = 0
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


async def _fetch_tgju_eur_rate() -> float | None:
    """Fetch live EUR→IRR market rate from tgju.org via the HTTP proxy.

    Returns the rate in IRR (Rial); callers convert to IRT (Toman) by /10.
    Returns None on any failure so callers can fall back.
    """
    try:
        import re
        import urllib.request as _ur
        proxy_url = os.getenv("HTTP_PROXY", os.getenv("HTTPS_PROXY", "http://10.10.11.2:8888"))
        _proxy = _ur.ProxyHandler({"http": proxy_url, "https": proxy_url})
        _opener = _ur.build_opener(_proxy)
        _resp = _opener.open("https://www.tgju.org/profile/price_eur", timeout=15)
        _text = _resp.read().decode()
        _m = re.search(r'class="price"[^>]*>([\d,]+)<', _text)
        if _m:
            return float(_m.group(1).replace(",", ""))
    except Exception as e:
        print(f"[warn] _fetch_tgju_eur_rate failed: {e}")
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
    markup_pct = 0
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

    models_out = []
    async with async_session() as session:
        from sqlalchemy import text as sql_text
        res = await session.execute(sql_text("""
            SELECT DISTINCT ON (model)
                model, provider, input_per_million, output_per_million, currency, source, price_version, effective_from
            FROM pricing
            WHERE effective_to IS NULL
            ORDER BY model, effective_from DESC, price_version DESC
        """))
        rows = [dict(r._mapping) for r in res.fetchall()]

    for r in rows:
        models_out.append({
            'model': r['model'], 'provider': r['provider'],
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
    multiplier = rate_irt * (1 + markup_pct / 100)

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
    """Generate a simple math captcha image."""
    a = random.randint(1, 15)
    b = random.randint(1, 15)
    answer = a + b
    text = f"{a} + {b} = ?"
    
    # Store answer in redis for 5 minutes
    token = base64.urlsafe_b64encode(f"{random.getrandbits(64)}".encode()).decode()[:12]
    await rds.setex(f"captcha:{token}", 300, str(answer))
    
    # Generate image — larger, more readable
    W, H = 280, 80
    img = Image.new("RGB", (W, H), (24, 24, 36))
    draw = ImageDraw.Draw(img)
    
    # Background noise lines (subtle)
    for _ in range(8):
        x1, y1 = random.randint(0, W), random.randint(0, H)
        x2, y2 = random.randint(0, W), random.randint(0, H)
        draw.line([(x1, y1), (x2, y2)], fill=(random.randint(40, 80), random.randint(40, 80), random.randint(60, 100)), width=1)
    
    # Noise dots
    for _ in range(80):
        x, y = random.randint(0, W-1), random.randint(0, H-1)
        draw.point((x, y), fill=(random.randint(80, 160), random.randint(80, 160), random.randint(100, 180)))
    
    # Load font with fallback chain
    font = None
    for font_path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]:
        try:
            font = ImageFont.truetype(font_path, 36)
            break
        except Exception:
            continue
    if font is None:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        except Exception:
            font = ImageFont.load_default()
    
    # Center text
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W - tw) // 2
    y = (H - th) // 2 - bbox[1]
    
    # Draw text with slight shadow for depth
    draw.text((x+1, y+1), text, fill=(60, 60, 80), font=font)
    draw.text((x, y), text, fill=(220, 220, 255), font=font)
    
    buf = io.BytesIO()
    img.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    
    return JSONResponse({"captcha": f"data:image/png;base64,{b64}", "token": token})
