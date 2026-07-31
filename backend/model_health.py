"""
Model health: which models are actually answering right now.

Before this module, "is this model working?" was answered by two hand-written
lists — `_HARDCODED_WORKING` in chat.py and `WORKING_MODEL_IDS` in the
frontend, the latter carrying a comment saying it was synced from a live test
on a specific date. Both went stale the moment an upstream changed, and nothing
noticed.

Health is now measured from two sources and combined:

  probe     a synthetic `max_tokens=1` completion sent on a slow loop. Covers
            models nobody happens to be using. Costs one output token per model
            per cycle, which is why the interval is minutes, not seconds.

  traffic   the outcome of real user requests, recorded by chat.py. Free, and
            far more representative than a probe, but only covers models people
            actually use.

Neither alone is sufficient: probes alone are expensive and unrepresentative,
traffic alone leaves rarely-used models permanently unknown. Together the
common case costs nothing and the long tail still gets covered.

Status is derived over a rolling window rather than from the last sample, so a
single blip does not take a model out of the picker and a model that fails
every other call does not look healthy.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from database import async_session, rds
from providers import (
    Provider,
    configured_providers,
    list_models,
    probe_model,
    upstream_alive,
)

logger = logging.getLogger('model_health')

router = APIRouter()

Status = Literal['healthy', 'degraded', 'down', 'unknown']

# ── Tuning ──────────────────────────────────────────────────────────────────

#: How far back a sample still counts toward the current rollup.
WINDOW = timedelta(minutes=int(os.getenv('MODEL_HEALTH_WINDOW_MIN', '30')))

#: Gap between probe sweeps. Deliberately long: a sweep costs one token per
#: model, and real traffic covers the models that matter in between.
PROBE_INTERVAL_S = int(os.getenv('MODEL_HEALTH_PROBE_INTERVAL', '600'))

#: Probes run a few at a time so a sweep does not open 23 upstream sockets at
#: once and look like an attack.
PROBE_CONCURRENCY = int(os.getenv('MODEL_HEALTH_PROBE_CONCURRENCY', '4'))

#: Below this success rate in the window a model is degraded; below the second
#: it is down.
DEGRADED_BELOW = float(os.getenv('MODEL_HEALTH_DEGRADED_BELOW', '0.85'))
DOWN_BELOW = float(os.getenv('MODEL_HEALTH_DOWN_BELOW', '0.4'))

#: Consecutive failures that mark a model down regardless of rate — catches a
#: model that just broke without waiting for the window average to sag.
DOWN_AFTER_CONSECUTIVE = int(os.getenv('MODEL_HEALTH_DOWN_AFTER', '3'))

#: A model answering this slowly is usable but not healthy.
DEGRADED_LATENCY_MS = int(os.getenv('MODEL_HEALTH_SLOW_MS', '15000'))

#: Samples older than this are deleted; the status page only shows the window.
RETENTION = timedelta(days=int(os.getenv('MODEL_HEALTH_RETENTION_DAYS', '7')))

_SUMMARY_CACHE_KEY = 'cache:model_health:summary'
_SUMMARY_CACHE_TTL = 20


# ── Recording ───────────────────────────────────────────────────────────────


async def record(
    model_id: str,
    *,
    ok: bool,
    source: Literal['probe', 'traffic'],
    latency_ms: int | None = None,
    error: str | None = None,
    provider: str = 'unknown',
) -> None:
    """Append one health sample.

    Never raises. This is called from the chat request path, where a failure to
    record health must not turn a working completion into a 500.
    """
    if not model_id or async_session is None:
        return
    try:
        async with async_session() as session:
            await session.execute(
                sqlalchemy.text(
                    'INSERT INTO model_health_event '
                    '(model_id, provider, source, ok, latency_ms, error) '
                    'VALUES (:m, :p, :s, :ok, :lat, :err)'
                ),
                {
                    'm': model_id,
                    'p': provider,
                    's': source,
                    'ok': ok,
                    'lat': latency_ms,
                    # Reason codes only — these are served to an unauthenticated
                    # status page, so never let a raw upstream body through.
                    'err': (error or None) if not ok else None,
                },
            )
            await session.commit()
    except Exception as e:
        logger.warning('record health failed for %s: %s', model_id, e)


async def record_traffic(
    model_id: str, ok: bool, latency_ms: int | None = None, error: str | None = None
) -> None:
    """Convenience wrapper for the chat path."""
    await record(model_id, ok=ok, source='traffic', latency_ms=latency_ms, error=error)


# ── Rollup ──────────────────────────────────────────────────────────────────


def _derive_status(
    sample_count: int,
    success_rate: float | None,
    consecutive_failures: int,
    latency_p50: int | None,
) -> Status:
    """Turn window statistics into a status.

    Order matters: a model with three straight failures is down even if the
    window average still looks acceptable, because the average is describing a
    past that no longer applies.
    """
    if sample_count == 0 or success_rate is None:
        return 'unknown'
    if consecutive_failures >= DOWN_AFTER_CONSECUTIVE:
        return 'down'
    if success_rate < DOWN_BELOW:
        return 'down'
    if success_rate < DEGRADED_BELOW:
        return 'degraded'
    if latency_p50 is not None and latency_p50 > DEGRADED_LATENCY_MS:
        return 'degraded'
    return 'healthy'


async def recompute_states() -> int:
    """Recompute `model_health_state` from the event window.

    One pass in SQL rather than a query per model: with 23 models and a probe
    every ten minutes this is trivial either way, but it keeps the loop O(1) in
    round-trips as the catalog grows.
    """
    if async_session is None:
        return 0

    cutoff = datetime.now(timezone.utc) - WINDOW
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                """
                SELECT model_id,
                       MAX(provider)                                  AS provider,
                       COUNT(*)                                       AS sample_count,
                       AVG(CASE WHEN ok THEN 1.0 ELSE 0.0 END)        AS success_rate,
                       PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY latency_ms)
                           FILTER (WHERE ok AND latency_ms IS NOT NULL)  AS p50,
                       PERCENTILE_DISC(0.95) WITHIN GROUP (ORDER BY latency_ms)
                           FILTER (WHERE ok AND latency_ms IS NOT NULL)  AS p95,
                       MAX(created_at) FILTER (WHERE ok)              AS last_ok_at,
                       MAX(created_at) FILTER (WHERE NOT ok)          AS last_error_at
                  FROM model_health_event
                 WHERE created_at >= :cutoff
                 GROUP BY model_id
                """
            ),
            {'cutoff': cutoff},
        )
        rows = [dict(r._mapping) for r in res.fetchall()]

        updated = 0
        for row in rows:
            model_id = row['model_id']

            # Consecutive trailing failures, newest first. Cheap because the
            # index is (model_id, created_at DESC) and we stop at the first ok.
            streak_res = await session.execute(
                sqlalchemy.text(
                    'SELECT ok FROM model_health_event WHERE model_id = :m '
                    'ORDER BY created_at DESC LIMIT 10'
                ),
                {'m': model_id},
            )
            consecutive = 0
            for (ok,) in streak_res.fetchall():
                if ok:
                    break
                consecutive += 1

            last_err_res = await session.execute(
                sqlalchemy.text(
                    'SELECT error FROM model_health_event '
                    'WHERE model_id = :m AND NOT ok AND error IS NOT NULL '
                    'ORDER BY created_at DESC LIMIT 1'
                ),
                {'m': model_id},
            )
            last_error_row = last_err_res.fetchone()

            success_rate = float(row['success_rate']) if row['success_rate'] is not None else None
            p50 = int(row['p50']) if row['p50'] is not None else None
            status = _derive_status(int(row['sample_count']), success_rate, consecutive, p50)

            await session.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO model_health_state
                        (model_id, provider, status, success_rate, latency_p50_ms,
                         latency_p95_ms, sample_count, consecutive_failures,
                         last_ok_at, last_error, last_error_at, checked_at, updated_at)
                    VALUES
                        (:m, :prov, :status, :rate, :p50, :p95, :n, :consec,
                         :last_ok, :last_error, :last_error_at, now(), now())
                    ON CONFLICT (model_id) DO UPDATE SET
                        provider             = EXCLUDED.provider,
                        status               = EXCLUDED.status,
                        success_rate         = EXCLUDED.success_rate,
                        latency_p50_ms       = EXCLUDED.latency_p50_ms,
                        latency_p95_ms       = EXCLUDED.latency_p95_ms,
                        sample_count         = EXCLUDED.sample_count,
                        consecutive_failures = EXCLUDED.consecutive_failures,
                        last_ok_at           = EXCLUDED.last_ok_at,
                        last_error           = EXCLUDED.last_error,
                        last_error_at        = EXCLUDED.last_error_at,
                        checked_at           = now(),
                        updated_at           = now()
                    """
                ),
                {
                    'm': model_id,
                    'prov': row.get('provider') or 'unknown',
                    'status': status,
                    'rate': success_rate,
                    'p50': p50,
                    'p95': int(row['p95']) if row['p95'] is not None else None,
                    'n': int(row['sample_count']),
                    'consec': consecutive,
                    'last_ok': row['last_ok_at'],
                    'last_error': last_error_row[0] if last_error_row else None,
                    'last_error_at': row['last_error_at'],
                },
            )
            updated += 1

        # Models with no samples in the window fall back to unknown rather than
        # keeping a stale "healthy" from an hour ago.
        await session.execute(
            sqlalchemy.text(
                "UPDATE model_health_state SET status = 'unknown', updated_at = now() "
                'WHERE checked_at < :cutoff AND status <> :unknown'
            ),
            {'cutoff': cutoff, 'unknown': 'unknown'},
        )

        # Mirror onto the catalog so existing availability-based queries and the
        # admin UI agree with the status page.
        await session.execute(
            sqlalchemy.text(
                """
                UPDATE model_catalog c SET availability = CASE s.status
                        WHEN 'healthy'  THEN 'available'
                        WHEN 'degraded' THEN 'degraded'
                        WHEN 'down'     THEN 'disabled'
                        ELSE c.availability
                    END,
                    last_verified_at = s.checked_at
                  FROM model_health_state s
                 WHERE (c.id = s.model_id OR c.provider_model_id = s.model_id)
                   AND c.provenance <> 'admin-approved'
                """
            )
        )
        await session.commit()

    try:
        await rds.delete(_SUMMARY_CACHE_KEY)
    except Exception:
        pass
    return updated


async def prune_events() -> int:
    """Drop samples past the retention horizon."""
    if async_session is None:
        return 0
    cutoff = datetime.now(timezone.utc) - RETENTION
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('DELETE FROM model_health_event WHERE created_at < :c'),
            {'c': cutoff},
        )
        await session.commit()
        return res.rowcount or 0


# ── Probing ─────────────────────────────────────────────────────────────────


async def _probe_targets() -> list[tuple[str, str]]:
    """(model_id, provider) pairs worth probing.

    Sourced from the catalog so the loop probes what we actually offer, not
    everything an upstream happens to expose.
    """
    if async_session is None:
        return []
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                "SELECT provider_model_id, COALESCE(upstream, provider) AS up "
                'FROM model_catalog '
                "WHERE availability <> 'maintenance'"
            )
        )
        return [(str(r.provider_model_id), str(r.up or 'unknown')) for r in res.fetchall()]


async def probe_sweep() -> dict[str, Any]:
    """Probe every catalog model once, recording a sample per model.

    If an upstream is entirely unreachable its models are recorded as failing
    with `upstream_down` rather than each being probed and timing out, which
    keeps a dead gateway from costing 23 timeouts per sweep.
    """
    providers = {p.name: p for p in configured_providers()}
    alive: dict[str, bool] = {}
    for name, p in providers.items():
        result = await upstream_alive(p)
        alive[name] = result.ok
        if not result.ok:
            logger.warning('upstream %s unreachable: %s', name, result.error)

    targets = await _probe_targets()
    if not targets:
        return {'probed': 0, 'upstreams': alive}

    sem = asyncio.Semaphore(PROBE_CONCURRENCY)
    probed = 0

    async def one(model_id: str, provider_name: str) -> None:
        nonlocal probed
        p = providers.get(provider_name) or providers.get('litellm')
        if p is None:
            return
        if not alive.get(p.name, False):
            await record(
                model_id, ok=False, source='probe',
                error='upstream_down', provider=p.name,
            )
            probed += 1
            return
        async with sem:
            result = await probe_model(p, model_id)
        await record(
            model_id,
            ok=result.ok,
            source='probe',
            latency_ms=result.latency_ms,
            error=result.error,
            provider=p.name,
        )
        probed += 1

    await asyncio.gather(*(one(m, prov) for m, prov in targets), return_exceptions=True)
    await recompute_states()
    return {'probed': probed, 'upstreams': alive}


async def health_loop() -> None:
    """Background sweep. Started from the app lifespan."""
    await asyncio.sleep(45)  # let migrations and the first requests settle
    while True:
        try:
            result = await probe_sweep()
            logger.info('probe sweep: %s', result)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning('probe sweep failed: %s', e)
        try:
            await prune_events()
        except Exception:
            pass
        await asyncio.sleep(PROBE_INTERVAL_S)


# ── Read API ────────────────────────────────────────────────────────────────


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

    upstreams = []
    for p in configured_providers():
        r = await upstream_alive(p)
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
