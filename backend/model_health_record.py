"""
Model health, recording lane: appending one sample and publishing what a
single deliberate probe proves.

Split out of model_health.py when that file passed the project's 500-line
cap. The seam is deliberate rather than arbitrary: everything here is a
*write of one observation*, depends on nothing but the database, and imports
neither the rollup nor the probe loop — so it can be imported from a request
path (admin_pricing.py's «تست زنده») without dragging the background
machinery in. model_health.py re-exports all three functions, so existing
imports of them from that module keep working unchanged.
"""
from __future__ import annotations

import logging
from typing import Literal

import sqlalchemy

from database import async_session

logger = logging.getLogger('model_health')


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


async def record_probe_sample(
    model_id: str, *, ok: bool, latency_ms: int | None = None,
    error: str | None = None, provider: str = 'unknown',
) -> None:
    """Record one deliberate probe AND publish its outcome to
    `model_health_state` immediately, without waiting for the next rollup.

    This exists because of a deadlock found in production. The admin panel's
    «تست زنده» button called providers.probe_model and showed the answer to
    the admin -- and then threw it away. Nothing was recorded, so
    `model_health_state.last_ok_at` never moved. services/probe_gate.py
    refuses to make a model `available` until that column is non-NULL, and the
    panel's own hint told the admin to "press تست زنده first". Pressing it
    could not possibly help: the only two writers of last_ok_at were the
    background rollup and the probe sweep, and the sweep skips `maintenance`
    rows -- which is 1,156 of the 1,200 catalog rows. Those models could
    never be enabled by any sequence of admin actions.

    `status` is deliberately NOT overwritten on an existing row. One sample is
    not a window, and deriving a status from it is exactly the bug
    MIN_SAMPLES_FOR_RATE was added to fix. The windowed rollup owns status and
    corrects a newly-inserted row within one sweep; this function only asserts
    the two things a single probe genuinely proves -- that we called the model
    at this instant, and whether it answered.
    """
    await record(model_id, ok=ok, source='probe', latency_ms=latency_ms,
                 error=error, provider=provider)
    if async_session is None:
        return
    try:
        async with async_session() as session:
            await session.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO model_health_state (model_id, provider, status,
                        sample_count, consecutive_failures, last_ok_at,
                        last_error, last_error_at, checked_at, updated_at)
                    VALUES (:m, :prov, :seed_status, 1, :consec,
                        CASE WHEN :ok THEN now() END, :err,
                        CASE WHEN :ok THEN NULL ELSE now() END, now(), now())
                    ON CONFLICT (model_id) DO UPDATE SET
                        provider = EXCLUDED.provider,
                        -- COALESCE, not EXCLUDED: a failing probe must not
                        -- erase the proof that this model once answered.
                        last_ok_at = COALESCE(EXCLUDED.last_ok_at,
                                              model_health_state.last_ok_at),
                        last_error = CASE WHEN :ok THEN model_health_state.last_error
                                          ELSE EXCLUDED.last_error END,
                        last_error_at = COALESCE(EXCLUDED.last_error_at,
                                                 model_health_state.last_error_at),
                        consecutive_failures = CASE WHEN :ok THEN 0
                            ELSE model_health_state.consecutive_failures + 1 END,
                        checked_at = now(), updated_at = now()
                    """
                ),
                # 'unknown' on a first-ever failing probe: honest, and the
                # rollup replaces it. A first-ever *successful* probe is what
                # _derive_status(1, 1.0, 0, ...) already calls healthy, so
                # seeding that costs no new policy.
                {'m': model_id, 'prov': provider, 'ok': ok,
                 'seed_status': 'healthy' if ok else 'unknown',
                 'consec': 0 if ok else 1, 'err': None if ok else error},
            )
            await session.commit()
    except Exception as e:
        # Same contract as record(): health bookkeeping never turns a working
        # probe into a 500 for the admin who asked for it.
        logger.warning('probe state publish failed for %s: %s', model_id, e)
