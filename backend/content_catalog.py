"""Catalog helpers and routes: `/v1/models`, `/catalog/models`,
`/catalog/pricing`, `/pricing-table` (+ `/api/pricing`, `/pricing`).

Split out of content.py purely to stay under the house 500-line cap --
nothing here changed in the move.

IMPORT CONTRACT -- read before moving anything again. content.py re-exports
`_catalog_row_to_item`, `_load_catalog_rows`, `_litellm_fallback_catalog`
from this module near the bottom of content.py (also registering the routes
below onto `content.router`), so `from content import X` and
`content_mod._catalog_row_to_item(...)` (tests/test_markup_billing_wire.py,
tests/test_public_model_ids.py) keep working unchanged.

The routes below call `content.get_global_markup_pct()` and
`content._get_exchange_rate()` -- attribute reads on the `content` module at
CALL time, never `from content import get_global_markup_pct`. Both names are
monkeypatched directly in the test suite
(`patch.object(content_mod, 'get_global_markup_pct', ...)` /
`patch.object(content_mod, '_get_exchange_rate', ...)` in
tests/test_margin_guard.py) as well as reached indirectly through
services/margin.py's own deferred `from content import ...`. A bare
intra-module call from this file would silently miss those patches, since
Python resolves a bare global against the *defining* module's namespace, not
content.py's -- the same hazard chat_web.py / chat_search.py's
IMPORT/MONKEYPATCH CONTRACT docstrings work out for `chat.<name>`.
`_catalog_row_to_item` / `_load_catalog_rows` themselves are never
monkeypatched (only called directly in tests), so their own bare
cross-references to `apply_markup` / `resolve_markup_pct` /
`_public_ids_enabled` also go through `content.<name>` here for uniformity
and future-proofing, but that indirection is not load-bearing for any test
today. `content` is imported plainly at module scope, which is safe against
the content.py <-> content_catalog.py circular import: nothing here touches
a `content` attribute until a function actually runs, by which point
content.py has finished executing (it imports this module only after
`router` is defined).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session, rds, _http, LITELLM_HOST
from models import Pricing
from i18n import err

import content


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
    served_id = (m.get('public_id') or m['id']) if content._public_ids_enabled() else m['id']
    effective_pct = content.resolve_markup_pct(m.get('markup_pct'), global_markup_pct)
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
            'inputPerMillion': content.apply_markup(m.get('input_per_million'), effective_pct),
            'outputPerMillion': content.apply_markup(m.get('output_per_million'), effective_pct),
            'cachedInputPerMillion': content.apply_markup(m['cached_input_per_million'], effective_pct) if m.get('cached_input_per_million') is not None else None,
            'reasoningPerMillion': content.apply_markup(m['reasoning_per_million'], effective_pct) if m.get('reasoning_per_million') is not None else None,
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
            public_filter = " AND public_id IS NOT NULL" if content._public_ids_enabled() else ""
            res = await session.execute(sqlalchemy.text(
                'SELECT id, provider_model_id, provider, display_name, description, '
                'modalities, capabilities, recommended_for, context_window, max_output_tokens, '
                'currency, input_per_million, output_per_million, cached_input_per_million, '
                'reasoning_per_million, price_version, effective_from, availability, audience, '
                'rate_limit, deprecated_at, last_verified_at, provenance, '
                'usd_input_per_million, usd_output_per_million, public_id, markup_pct '
                "FROM model_catalog WHERE availability = 'available' AND NOT (audience @> '[\"admin\"]') "
                # Honest labelling, defense-in-depth: `availability` alone
                # says nothing about whether this row has ever actually
                # answered a live probe. last_ok_at IS NOT NULL (ever-probed-
                # OK, not a freshness window -- a freshness gate here would
                # mass-hide the whole catalog during a prober outage) is the
                # same condition model_health.py's own catalog mirror and
                # services/probe_gate.py already use to decide "servable".
                "AND EXISTS (SELECT 1 FROM model_health_state s "
                "WHERE (s.model_id = model_catalog.id OR s.model_id = model_catalog.provider_model_id) "
                "AND s.last_ok_at IS NOT NULL) "
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

@content.router.get('/v1/models')
async def list_models(request: Request) -> dict[str, Any]:
    """Return only models that are available in the catalog and actually working."""
    models = []
    if async_session is not None:
        try:
            global_markup_pct = await content.get_global_markup_pct()
            async with async_session() as session:
                public_only = content._public_ids_enabled()
                public_filter = " AND public_id IS NOT NULL" if public_only else ""
                res = await session.execute(
                    sqlalchemy.text(
                        "SELECT id, provider_model_id, public_id, display_name, context_window, availability, "
                        "input_per_million, output_per_million, currency, "
                        "usd_input_per_million, usd_output_per_million, markup_pct "
                        "FROM model_catalog WHERE availability = 'available' AND NOT (audience @> '[\"admin\"]') "
                        # Same honest-labelling gate as _load_catalog_rows above.
                        "AND EXISTS (SELECT 1 FROM model_health_state s "
                        "WHERE (s.model_id = model_catalog.id OR s.model_id = model_catalog.provider_model_id) "
                        "AND s.last_ok_at IS NOT NULL) "
                        f"{public_filter} ORDER BY id"
                    )
                )
                for row in res.fetchall():
                    usd_in = float(row.usd_input_per_million or 0)
                    usd_out = float(row.usd_output_per_million or 0)
                    effective_pct = content.resolve_markup_pct(row.markup_pct, global_markup_pct)
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
                            'inputPerMillion': content.apply_markup(row.input_per_million, effective_pct),
                            'outputPerMillion': content.apply_markup(row.output_per_million, effective_pct),
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


@content.router.get('/catalog/models')
async def catalog_models(request: Request) -> JSONResponse:
    """Approved model catalog from DB, with litellm fallback when DB is empty."""
    cached = await rds.get('cache:catalog:models')
    if cached:
        return JSONResponse(json.loads(cached))
    rate_irt, _stale_markup_pct = await content._get_exchange_rate()
    # Markup is resolved fresh here (5-minute cache), not from the exchange
    # rate's hour-long cache (_stale_markup_pct, discarded) -- otherwise an
    # admin's markup change could take up to an hour to reach this endpoint
    # while chat.py's billing path (which also calls get_global_markup_pct)
    # already sees it, breaking the display/billed-price agreement.
    global_markup_pct = await content.get_global_markup_pct()
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
    await rds.setex('cache:catalog:models', content.CATALOG_CACHE_TTL, json.dumps(result))
    return JSONResponse(result)


@content.router.get('/catalog/pricing')
async def catalog_pricing(request: Request) -> JSONResponse:
    """Versioned pricing for catalog models (falls back to pricing table)."""
    cached = await rds.get('cache:catalog:pricing')
    if cached:
        return JSONResponse(json.loads(cached))
    rows = await _load_catalog_rows()
    global_markup_pct = await content.get_global_markup_pct()
    pricing = []
    for m in rows:
        # Same public_id substitution as _catalog_row_to_item -- see there.
        served_id = (m.get('public_id') or m['id']) if content._public_ids_enabled() else m['id']
        effective_pct = content.resolve_markup_pct(m.get('markup_pct'), global_markup_pct)
        pricing.append({
            'id': served_id,
            'currency': m.get('currency') or 'IRT',
            'inputPerMillion': content.apply_markup(m.get('input_per_million'), effective_pct),
            'outputPerMillion': content.apply_markup(m.get('output_per_million'), effective_pct),
            'cachedInputPerMillion': content.apply_markup(m['cached_input_per_million'], effective_pct) if m.get('cached_input_per_million') is not None else None,
            'reasoningPerMillion': content.apply_markup(m['reasoning_per_million'], effective_pct) if m.get('reasoning_per_million') is not None else None,
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
    await rds.setex('cache:catalog:pricing', content.CATALOG_CACHE_TTL, json.dumps(result))
    return JSONResponse(result)


@content.router.get('/pricing-table')
@content.router.get('/api/pricing')
# `/pricing` exists so that `/api/pricing` is reachable from the browser. The
# Next proxy (frontend/app/api/[...path]/route.ts) forwards `/api/X` to the
# backend as `/X` -- it strips the prefix -- so the `/api/pricing` route above
# is only ever hit by a caller talking to the backend directly, and the public
# URL https://sanjabai.com/api/pricing was answering 404. `/api/exchange-rate`
# (content.py) has the same shape and works only because it also registers a
# bare `/exchange-rate`; this mirrors that. Any future `/api/...` route needs
# the bare twin too.
@content.router.get('/pricing')
async def api_pricing(request: Request) -> JSONResponse:
    """Return all active model pricing in Toman.

    Dual paths for Next rewrite compatibility (`/api/pricing` → `/pricing-table`).
    """
    cached = await rds.get('cache:api:pricing')
    if cached:
        return JSONResponse(json.loads(cached))

    rate_irt, markup_pct = await content._get_exchange_rate()
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

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
