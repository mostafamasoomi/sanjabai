"""
Model health: the read side.

`health_map`, `healthy_model_ids`, and the public `/models/health` endpoint
that backs the /status page. Split out of model_health.py — which owns
recording samples, the rollup, and the probe loop, all DB-touching — because
the two together no longer fit under the project's 500-line cap. Read here,
written there; model_health_policy.py holds the pure decision functions both
depend on indirectly (this file only needs WINDOW and the shared cache key).

model_health.py re-exports `router` and `health_map` from this module so
app.py's `from model_health import router as model_health_router` and
admin_monitoring.py's / content.py's `from model_health import health_map`
keep working unchanged — this module must not import from model_health.py,
or that re-export becomes a circular import.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from database import async_session, rds
from model_health_policy import WINDOW, _SUMMARY_CACHE_KEY
from providers import configured_providers, upstream_alive

logger = logging.getLogger('model_health_api')

router = APIRouter()

_SUMMARY_CACHE_TTL = 20


async def health_map() -> dict[str, dict[str, Any]]:
    """Current state keyed by model id, for joining onto the catalog."""
    if async_session is None:
        return {}
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text(
                    'SELECT model_id, provider, status, success_rate, latency_p50_ms, '
                    'latency_p95_ms, sample_count, last_ok_at, last_error, checked_at '
                    'FROM model_health_state'
                )
            )
            out: dict[str, dict[str, Any]] = {}
            for r in res.fetchall():
                d = dict(r._mapping)
                out[str(d['model_id'])] = {
                    'status': d['status'],
                    'successRate': float(d['success_rate']) if d['success_rate'] is not None else None,
                    'latencyP50Ms': d['latency_p50_ms'],
                    'latencyP95Ms': d['latency_p95_ms'],
                    'sampleCount': d['sample_count'],
                    'lastOkAt': d['last_ok_at'],
                    'lastError': d['last_error'],
                    'checkedAt': d['checked_at'],
                }
            return out
    except Exception as e:
        logger.warning('health_map failed: %s', e)
        return {}


async def healthy_model_ids() -> set[str]:
    """Ids considered usable right now.

    `unknown` counts as usable: a model nobody has exercised yet must not be
    hidden, or a fresh deployment would show an empty model picker.
    """
    if async_session is None:
        return set()
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text(
                    'SELECT model_id FROM model_health_state '
                    "WHERE status IN ('healthy', 'degraded', 'unknown')"
                )
            )
            return {str(r.model_id) for r in res.fetchall()}
    except Exception:
        return set()


async def _served_models() -> dict[str, dict[str, str]] | None:
    """Route id -> public identity, for the models we actually sell.

    `availability = 'available' AND public_id IS NOT NULL` is the same
    definition of "served" that tasks.py and the public catalog endpoint use;
    it must not drift from them, or /status starts describing a different
    product than /catalog/models does.

    Returns None — not {} — when the catalog cannot be read, so the caller can
    tell "we serve nothing" apart from "we do not know what we serve".
    """
    if async_session is None:
        return None
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text(
                    'SELECT provider_model_id, public_id, display_name '
                    'FROM model_catalog '
                    "WHERE availability = 'available' AND public_id IS NOT NULL"
                )
            )
            out: dict[str, dict[str, str]] = {}
            for r in res.fetchall():
                d = dict(r._mapping)
                out[str(d['provider_model_id'])] = {
                    'publicId': str(d['public_id']),
                    'displayName': str(d['display_name']),
                }
            return out
    except Exception as e:
        logger.warning('_served_models failed: %s', e)
        return None


@router.get('/models/health')
async def models_health(request: Request) -> JSONResponse:
    """Public health summary. Backs the /status page.

    Reports only models we actually serve, under their public `sanjab/*` ids.
    This endpoint is anonymous, so every row it emits is public: listing the
    raw health table here published upstream route prefixes (kr/, cc/, cx/,
    openrouter/, gemini-api/, ...) to any visitor, which the product forbids,
    and counted models we do not sell — 45 of 69 rows — into an `overall` of
    'degraded' while every model a user could actually pick was healthy.
    Admins still get the unfiltered table via /admin/monitoring, which reads
    health_map() directly.
    """
    cached = await rds.get(_SUMMARY_CACHE_KEY)
    if cached:
        return JSONResponse(json.loads(cached))

    states = await health_map()
    served = await _served_models()

    if served is None:
        # The catalog is unreadable, so we cannot tell which rows are ours to
        # talk about. Publishing `states` raw here is what leaked route ids in
        # the first place, and publishing nothing while claiming 'operational'
        # would be a lie. Report that we do not know and let the upstream
        # section below carry the real signal.
        models: list[dict[str, Any]] = []
        counts = {'healthy': 0, 'degraded': 0, 'down': 0, 'unknown': 0}
        unknown_catalog = True
    else:
        unknown_catalog = False
        # One row per model we actually sell, keyed by its public id. A served
        # model with no health row yet is 'unknown', not missing: the page
        # promises that anything in the catalog appears here.
        models = []
        for route_id, meta in served.items():
            state = states.get(route_id) or {
                'status': 'unknown', 'successRate': None,
                'latencyP50Ms': None, 'latencyP95Ms': None,
                'sampleCount': 0, 'lastOkAt': None,
                'lastError': None, 'checkedAt': None,
            }
            models.append({
                'id': meta['publicId'],
                'displayName': meta['displayName'],
                **state,
            })
        models.sort(key=lambda m: m['id'])

        counts = {'healthy': 0, 'degraded': 0, 'down': 0, 'unknown': 0}
        for m in models:
            counts[m['status']] = counts.get(m['status'], 0) + 1

    # Run concurrently, not sequentially: 9Router legitimately takes up to
    # ~11s to answer, and upstream_alive's default timeout is only 5s. A
    # sequential loop over N providers at up to 15s each turned one slow-but-
    # alive upstream into a multi-provider pileup and got the tunnel wrongly
    # declared dead. timeout=15.0 gives 9Router room; gather runs every
    # provider's check in parallel so total latency is bounded by the
    # slowest single provider, not the sum of all of them.
    providers_list = configured_providers()
    alive_results = await asyncio.gather(
        *(upstream_alive(p, timeout=15.0) for p in providers_list),
        return_exceptions=True,
    )
    # AGGREGATE ONLY -- never the gateway names.
    #
    # This endpoint is anonymous, and it used to emit one entry per upstream
    # carrying `name` verbatim: `litellm`, `omniroute`, `ninerouter`, each
    # with its own latency. That is the supply chain, published to any
    # visitor of /status. The same rule that renames model ids to `sanjab/*`
    # above applies here and was simply missed on this one field: a normal
    # user never learns which upstream serves anything, only an admin does
    # (admin_monitoring._upstreams_section keeps the full named breakdown,
    # behind admin auth).
    #
    # A per-gateway count is not published either -- how many routers we run
    # is the same fact told more quietly. The page keeps the one thing a
    # visitor can act on: whether model supply as a whole is healthy.
    gateway_ok = sum(
        1 for r in alive_results if not isinstance(r, BaseException) and r.ok
    )
    if not providers_list:
        gateways_status = 'unknown'
    elif gateway_ok == len(providers_list):
        gateways_status = 'operational'
    elif gateway_ok:
        gateways_status = 'degraded'
    else:
        gateways_status = 'down'

    # Overall reads as the worst thing a user would actually notice — so it is
    # computed over served models only. A model parked in maintenance/disabled
    # is not something a user can notice; saying it is "down" advertises an
    # outage we do not have.
    if unknown_catalog:
        overall = 'degraded'
    elif counts['healthy'] == 0 and (counts['down'] or counts['degraded']):
        overall = 'down'
    elif counts['down'] or counts['degraded']:
        overall = 'degraded'
    else:
        overall = 'operational'

    from fastapi.encoders import jsonable_encoder

    payload = jsonable_encoder({
        'overall': overall,
        'counts': counts,
        # `upstreams` (a named, per-gateway list) was REMOVED, not renamed --
        # see above. Anything that still reads it gets undefined, which is
        # the correct outcome for a field that must not be public.
        'gateways': {'status': gateways_status},
        'models': models,
        'windowMinutes': int(WINDOW.total_seconds() // 60),
        'generatedAt': datetime.now(timezone.utc),
    })
    try:
        await rds.setex(_SUMMARY_CACHE_KEY, _SUMMARY_CACHE_TTL, json.dumps(payload))
    except Exception:
        pass
    return JSONResponse(payload)
