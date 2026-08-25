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

This is now three files. This one owns recording samples, the rollup, and the
probe loop (all DB-touching). model_health_policy.py holds the pure decision
functions (`_derive_status` and friends) — no database, directly unit-
testable. model_health_api.py is the read side: `health_map`,
`healthy_model_ids`, and the `/models/health` endpoint. `router` and
`health_map` are re-exported below so existing imports of them from this
module (app.py, admin_monitoring.py, content.py) keep working unchanged.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import sqlalchemy

from database import async_session, rds
# _derive_status: unused directly below, but this re-exports it so
# tests/test_model_health.py's `from model_health import _derive_status` keeps working.
from model_health_policy import (
    PARKED_PROBE_SLICE, PROBE_CONCURRENCY, PROBE_INTERVAL_S, PROVIDER_FAULT_REASONS,
    RETENTION, WINDOW, _SUMMARY_CACHE_KEY, _build_mirror_target, _derive_status,
    _is_quarantine_recheck_sweep, _plan_catalog_mirror,
)
# router/health_map: unused directly below, re-exported so app.py's
# `from model_health import router` and admin_monitoring.py's/content.py's
# `from model_health import health_map` keep working unchanged.
from model_health_api import health_map, router
# The recording lane moved to its own file when this one passed the 500-line
# cap; re-exported here so chat.py's `from model_health import record_traffic`
# and every other existing import keeps working unchanged.
from model_health_record import record, record_probe_sample, record_traffic
from providers import (
    Provider, configured_providers, list_models, probe_model_resilient, upstream_alive,
)

logger = logging.getLogger('model_health')

_CATALOG_CACHE_KEYS = ('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')

#: Sweep counter for the quarantine slow lane. Module-level, not Redis: one
#: background task in one process — losing it on restart costs one extra cycle.
_sweep_count = 0


# ── Rollup (DB-touching; pure decisions live in model_health_policy.py) ───
async def recompute_states() -> int:
    """Recompute `model_health_state` from the event window and mirror it
    onto the catalog. Returns the number of model_health_state rows upserted."""
    if async_session is None:
        return 0

    cutoff = datetime.now(timezone.utc) - WINDOW
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                """
                SELECT model_id, MAX(provider) AS provider, COUNT(*) AS sample_count,
                       AVG(CASE WHEN ok THEN 1.0 ELSE 0.0 END) AS success_rate,
                       PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY latency_ms)
                           FILTER (WHERE ok AND latency_ms IS NOT NULL) AS p50,
                       PERCENTILE_DISC(0.95) WITHIN GROUP (ORDER BY latency_ms)
                           FILTER (WHERE ok AND latency_ms IS NOT NULL) AS p95,
                       MAX(created_at) FILTER (WHERE ok) AS last_ok_at,
                       MAX(created_at) FILTER (WHERE NOT ok) AS last_error_at
                  FROM model_health_event WHERE created_at >= :cutoff GROUP BY model_id
                """
            ),
            {'cutoff': cutoff},
        )
        rows = [dict(r._mapping) for r in res.fetchall()]

        updated = 0
        # Keyed by health-event model_id (== catalog id or provider_model_id);
        # only models with samples this window, i.e. that can change status.
        mirror_targets: dict[str, dict[str, Any]] = {}
        for row in rows:
            model_id = row['model_id']

            # Consecutive trailing failures, newest first; stop at first ok.
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

            # Last failing reason + provider-fault classification (how many
            # failures were our account/quota/gateway, not the model) in one
            # query, for the catalog mirror below.
            fault_res = await session.execute(
                sqlalchemy.text(
                    "SELECT COUNT(*) FILTER (WHERE NOT ok) AS failures, "
                    "COUNT(*) FILTER (WHERE NOT ok AND error IN :reasons) "
                    "    AS provider_fault_failures, "
                    "(ARRAY_AGG(error ORDER BY created_at DESC) "
                    "    FILTER (WHERE NOT ok AND error IS NOT NULL))[1] AS last_error "
                    "FROM model_health_event WHERE model_id = :m AND created_at >= :cutoff"
                ).bindparams(sqlalchemy.bindparam('reasons', expanding=True)),
                {'m': model_id, 'cutoff': cutoff, 'reasons': tuple(PROVIDER_FAULT_REASONS)},
            )
            fault_row = fault_res.fetchone()
            last_error = fault_row.last_error if fault_row else None

            success_rate = float(row['success_rate']) if row['success_rate'] is not None else None
            p50 = int(row['p50']) if row['p50'] is not None else None
            mirror_targets[model_id] = _build_mirror_target(
                int(row['sample_count']), success_rate, consecutive, p50,
                int(fault_row.failures or 0) if fault_row else 0,
                int(fault_row.provider_fault_failures or 0) if fault_row else 0,
                last_error,
            )
            status = mirror_targets[model_id]['status']

            await session.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO model_health_state (model_id, provider, status,
                        success_rate, latency_p50_ms, latency_p95_ms, sample_count,
                        consecutive_failures, last_ok_at, last_error, last_error_at,
                        checked_at, updated_at)
                    VALUES (:m, :prov, :status, :rate, :p50, :p95, :n, :consec,
                        :last_ok, :last_error, :last_error_at, now(), now())
                    ON CONFLICT (model_id) DO UPDATE SET
                        provider = EXCLUDED.provider, status = EXCLUDED.status,
                        success_rate = EXCLUDED.success_rate,
                        latency_p50_ms = EXCLUDED.latency_p50_ms,
                        latency_p95_ms = EXCLUDED.latency_p95_ms,
                        sample_count = EXCLUDED.sample_count,
                        consecutive_failures = EXCLUDED.consecutive_failures,
                        last_ok_at = EXCLUDED.last_ok_at, last_error = EXCLUDED.last_error,
                        last_error_at = EXCLUDED.last_error_at,
                        checked_at = now(), updated_at = now()
                    """
                ),
                {
                    'm': model_id, 'prov': row.get('provider') or 'unknown', 'status': status,
                    'rate': success_rate, 'p50': p50, 'consec': consecutive,
                    'p95': int(row['p95']) if row['p95'] is not None else None,
                    'n': int(row['sample_count']), 'last_ok': row['last_ok_at'],
                    'last_error': last_error, 'last_error_at': row['last_error_at'],
                },
            )
            updated += 1

        # No samples this window falls back to unknown, not a stale status.
        await session.execute(
            sqlalchemy.text(
                "UPDATE model_health_state SET status = 'unknown', updated_at = now() "
                'WHERE checked_at < :cutoff AND status <> :unknown'
            ),
            {'cutoff': cutoff, 'unknown': 'unknown'},
        )

        # Mirror onto the catalog. EXISTS, not a bare provenance filter: of
        # 1126 non-admin-approved rows only ~58 ever have a health-state
        # entry; the rest can never appear in mirror_targets, so fetching
        # all 1126 every sweep was wasted work.
        catalog_res = await session.execute(
            sqlalchemy.text(
                "SELECT id, provider_model_id, availability, provenance, "
                "input_per_million, health_quarantine_reason, upstream "
                "FROM model_catalog c WHERE provenance <> 'admin-approved' "
                "AND EXISTS (SELECT 1 FROM model_health_state s "
                "            WHERE c.id = s.model_id OR c.provider_model_id = s.model_id)"
            )
        )
        catalog_rows = [dict(r._mapping) for r in catalog_res.fetchall()]

        # The decision (what changes, to what, and why) is pure and lives in
        # _plan_catalog_mirror; this loop only executes and logs it.
        plan = _plan_catalog_mirror(catalog_rows, mirror_targets)
        any_changed = any(p['changed'] for p in plan)
        for p in plan:
            if p['changed']:
                logger.info(
                    'catalog availability %s: %s -> %s (health=%s, reason=%s)',
                    p['id'], p['from_a'], p['avail'], p['hstatus'], p['reason_log'],
                )
                # UPDATE + audit row share a CTE: recorded only if it happens.
                await session.execute(
                    sqlalchemy.text(
                        """
                        WITH upd AS (
                            UPDATE model_catalog SET availability = :avail,
                                health_quarantine_reason = CAST(:reason AS text),
                                health_quarantined_at = CASE
                                    WHEN CAST(:reason AS text) IS NOT NULL
                                    THEN now() END,
                                last_verified_at = now(), updated_at = now()
                            WHERE id = :id RETURNING id
                        )
                        INSERT INTO model_availability_change (model_id, from_availability,
                            to_availability, reason, health_status, success_rate, sample_count)
                        SELECT :id, :from_a, :avail, :reason_log, :hstatus, :rate, :n FROM upd
                        """
                    ),
                    p,
                )
            else:
                # No transition: refresh timestamps only, no audit row.
                await session.execute(
                    sqlalchemy.text(
                        # CAST is required, not decorative: asyncpg infers a
                        # parameter's type from where it is used, and a bare
                        # placeholder tested only with IS NOT NULL gives it
                        # nothing to go on -- it fails the whole sweep with
                        # AmbiguousParameterError. Seen in production.
                        'UPDATE model_catalog SET '
                        'health_quarantine_reason = CAST(:reason AS text), '
                        'health_quarantined_at = CASE '
                        '  WHEN CAST(:reason AS text) IS NOT NULL THEN now() '
                        '  ELSE health_quarantined_at END, '
                        'last_verified_at = now() WHERE id = :id'
                    ),
                    p,
                )

        # `available` with no public_id is silently invisible to the public.
        no_public_id_res = await session.execute(
            sqlalchemy.text(
                "SELECT id FROM model_catalog WHERE availability = 'available' "
                'AND public_id IS NULL'
            )
        )
        orphaned = [r[0] for r in no_public_id_res.fetchall()]
        if orphaned:
            logger.warning(
                "available with no public_id (invisible to the public catalog): %s",
                orphaned,
            )

        await session.commit()

    try:
        await rds.delete(_SUMMARY_CACHE_KEY)
    except Exception:
        pass
    if any_changed:
        try:
            await rds.delete(*_CATALOG_CACHE_KEYS)
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


async def _probe_targets(recheck_quarantine: bool = False) -> list[tuple[str, str]]:
    """(model_id, provider) pairs worth probing.

    Sourced from the catalog so the loop probes what we actually offer, not
    everything an upstream happens to expose. Three lanes:

    1. everything not `maintenance` — the models we serve or might serve;
    2. rows THIS mechanism quarantined, on a slow lane so a self-parked model
       is not parked forever (see QUARANTINE_RECHECK_EVERY);
    3. a rotating slice of rows an admin parked or discovery landed
       (`maintenance`, no quarantine reason), least-recently-checked first.

    Lane 3 is new, and it is the fix for a hard deadlock. Parked rows used to
    be excluded outright, on the reasoning that a probe must never undo an
    admin's parking. The parking is still never undone — that guarantee moved
    into _target_catalog_state, where it belongs, so the mirror ignores what
    this lane finds. But *excluding them from measurement* meant their
    `model_health_state.last_ok_at` stayed NULL forever, and
    services/probe_gate.py refuses to make such a model available. 1,156 of
    1,200 catalog rows sat in that state: unprobeable, therefore un-enableable,
    therefore permanently invisible however well they actually worked. A live
    sample of 82 of them found ~12% answering on the first try.

    Least-recently-checked ordering (NULLS FIRST, so never-checked rows go
    first) makes the rotation self-balancing without a persisted cursor.
    """
    if async_session is None:
        return []
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                "SELECT provider_model_id, COALESCE(upstream, provider) AS up "
                'FROM model_catalog '
                "WHERE availability <> 'maintenance' "
                '   OR (health_quarantine_reason IS NOT NULL AND :recheck)'
            ),
            {'recheck': recheck_quarantine},
        )
        targets = [(str(r.provider_model_id), str(r.up or 'unknown')) for r in res.fetchall()]

        if PARKED_PROBE_SLICE > 0:
            parked = await session.execute(
                sqlalchemy.text(
                    'SELECT c.provider_model_id, COALESCE(c.upstream, c.provider) AS up '
                    'FROM model_catalog c '
                    'LEFT JOIN model_health_state s '
                    '  ON s.model_id = c.provider_model_id OR s.model_id = c.id '
                    "WHERE c.availability = 'maintenance' "
                    '  AND c.health_quarantine_reason IS NULL '
                    'ORDER BY s.checked_at ASC NULLS FIRST, c.provider_model_id '
                    'LIMIT :slice'
                ),
                {'slice': PARKED_PROBE_SLICE},
            )
            seen = {m for m, _ in targets}
            for r in parked.fetchall():
                m = str(r.provider_model_id)
                if m not in seen:
                    targets.append((m, str(r.up or 'unknown')))
                    seen.add(m)
        return targets


async def probe_sweep() -> dict[str, Any]:
    """Probe every catalog model once, recording a sample per model.

    If an upstream is entirely unreachable its models are recorded as failing
    with `upstream_down` rather than each being probed and timing out, which
    keeps a dead gateway from costing 23 timeouts per sweep.
    """
    global _sweep_count
    _sweep_count += 1
    recheck_quarantine = _is_quarantine_recheck_sweep(_sweep_count)

    providers = {p.name: p for p in configured_providers()}
    alive: dict[str, bool] = {}
    for name, p in providers.items():
        # timeout=15.0, not the 5s default (same reasoning as models_health's
        # gather in model_health_api.py): a false "down" here now mass-parks
        # every model behind this upstream into 'maintenance' via
        # PROVIDER_FAULT_REASONS, not just one bad probe.
        result = await upstream_alive(p, timeout=15.0)
        alive[name] = result.ok
        if not result.ok:
            logger.warning('upstream %s unreachable: %s', name, result.error)

    targets = await _probe_targets(recheck_quarantine)
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
            await record(model_id, ok=False, source='probe', error='upstream_down', provider=p.name)
            probed += 1
            return
        async with sem:
            # Resilient, not bare: a router that answers "cooling down, reset
            # after 42s" is not a broken model, and one such sample used to be
            # enough to park it. Measured on the live catalog, retrying only
            # the transient reasons rescued 5 of 70 apparent failures.
            result = await probe_model_resilient(p, model_id)
        await record(model_id, ok=result.ok, source='probe', latency_ms=result.latency_ms,
                     error=result.error, provider=p.name)
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

