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


@router.get('/models/health')
async def models_health(request: Request) -> JSONResponse:
    """Public health summary. Backs the /status page."""
    cached = await rds.get(_SUMMARY_CACHE_KEY)
    if cached:
        return JSONResponse(json.loads(cached))

    states = await health_map()

    # Join display names on so the status page does not need the catalog too.
    names: dict[str, str] = {}
    if async_session is not None:
        try:
            async with async_session() as session:
                res = await session.execute(
                    sqlalchemy.text(
                        'SELECT id, provider_model_id, display_name, provider '
                        'FROM model_catalog'
                    )
                )
                for r in res.fetchall():
                    d = dict(r._mapping)
                    names[str(d['provider_model_id'])] = d['display_name']
                    names[str(d['id'])] = d['display_name']
        except Exception:
            pass

    models = []
    for model_id, state in sorted(states.items()):
        models.append({
            'id': model_id,
            'displayName': names.get(model_id, model_id),
            **state,
        })

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
    upstreams = []
    for p, r in zip(providers_list, alive_results):
        if isinstance(r, BaseException):
            upstreams.append({
                'name': p.name, 'ok': False, 'latencyMs': None,
                'error': type(r).__name__,
            })
            continue
        upstreams.append({
            'name': p.name,
            'ok': r.ok,
            'latencyMs': r.latency_ms,
            'error': r.error,
        })

    # Overall reads as the worst thing a user would actually notice.
    if counts['healthy'] == 0 and (counts['down'] or counts['degraded']):
        overall = 'down'
    elif counts['down'] or counts['degraded']:
        overall = 'degraded'
    else:
        overall = 'operational'

    from fastapi.encoders import jsonable_encoder

    payload = jsonable_encoder({
        'overall': overall,
        'counts': counts,
        'upstreams': upstreams,
        'models': models,
        'windowMinutes': int(WINDOW.total_seconds() // 60),
        'generatedAt': datetime.now(timezone.utc),
    })
    try:
        await rds.setex(_SUMMARY_CACHE_KEY, _SUMMARY_CACHE_TTL, json.dumps(payload))
    except Exception:
        pass
    return JSONResponse(payload)
