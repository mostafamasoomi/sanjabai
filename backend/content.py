"""
Public content endpoints: about, features, discounts, catalog, pricing API,
exchange rate, org default model.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session, rds, _http, LITELLM_HOST
from models import AboutContent, Feature, Discount, ProxyConfig, Pricing
from dependencies import admin_required

router = APIRouter()

EXCHANGE_RATE_CACHE_TTL = 3600  # 1 hour


# ── Catalog helpers ─────────────────────────────────────────────

def _catalog_row_to_item(m: dict[str, Any]) -> dict[str, Any]:
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
                'rate_limit, deprecated_at, last_verified_at, provenance '
                'FROM model_catalog ORDER BY provider, id'
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
    models = []
    try:
        r = await _http.get(f"{LITELLM_HOST}/v1/models", timeout=5)
        if r.status_code == 200:
            models = r.json().get('data', [])
    except Exception:
        pass
    if not models and async_session is not None:
        try:
            async with async_session() as session:
                res = await session.execute(
                    sqlalchemy.text("SELECT id, provider_model_id, display_name, context_window, availability FROM model_catalog WHERE availability = 'available' ORDER BY id")
                )
                for row in res.fetchall():
                    models.append({
                        'id': row.provider_model_id, 'object': 'model', 'created': 0,
                        'owned_by': 'multiai', 'display_name': row.display_name,
                        'context_window': row.context_window,
                    })
        except Exception:
            pass
    return {'object': 'list', 'data': models}


@router.get('/catalog/models')
async def catalog_models(request: Request) -> JSONResponse:
    """Approved model catalog from DB, with litellm fallback when DB is empty."""
    cached = await rds.get('cache:catalog:models')
    if cached:
        return JSONResponse(json.loads(cached))
    rows = await _load_catalog_rows()
    if rows:
        data = [_catalog_row_to_item(r) for r in rows]
        source = 'approved-catalog'
    else:
        data = await _litellm_fallback_catalog()
        source = 'fallback'
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


@router.get('/api/exchange-rate')
async def api_exchange_rate() -> JSONResponse:
    """Return the current USD→IRR exchange rate."""
    cached = await rds.get('cache:exchange_rate')
    if cached:
        return JSONResponse(json.loads(cached))

    rate = None
    try:
        resp = await _http.get('https://api.exchangerate-api.com/v4/latest/USD', follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        rate = float(data['rates']['IRR'])
    except Exception:
        pass

    if rate is None:
        rate = 850_000 * 10

    result = jsonable_encoder({
        'USD_IRR': rate,
        'USD_TOMAN': rate / 10,
        'source': 'exchangerate-api.com' if rate != 8_500_000 else 'fallback',
        'fetchedAt': datetime.now(timezone.utc).isoformat(),
    })
    await rds.setex('cache:exchange_rate', EXCHANGE_RATE_CACHE_TTL, json.dumps(result))
    return JSONResponse(result)


@router.get('/api/pricing')
async def api_pricing(request: Request) -> JSONResponse:
    """Return all active model pricing in Toman."""
    cached = await rds.get('cache:api:pricing')
    if cached:
        return JSONResponse(json.loads(cached))

    rate_resp = await api_exchange_rate()
    rate_data = json.loads(rate_resp.body) if hasattr(rate_resp, 'body') else {}
    toman_rate = rate_data.get('USD_TOMAN', 85_000)

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
        'data': models_out, 'exchangeRate': toman_rate, 'margin': 0.20,
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
