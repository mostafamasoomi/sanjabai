"""
Pure decision policy for model health: tuning constants and the functions
that turn window statistics into a status, and a status into a catalog
availability decision. Nothing here touches a database or Redis — that's
what makes it directly unit-testable and safe to import from anywhere.

Model health is now three files: this one (pure decisions), model_health.py
(measurement — recording samples, the rollup, the probe loop, all DB-
touching), and model_health_api.py (the read side — health_map,
healthy_model_ids, the `/models/health` endpoint). All three exist because
one file no longer fit under the project's 500-line cap. model_health.py
re-exports `_derive_status`, `router`, and `health_map` (imported from here /
model_health_api.py respectively) so external imports that predate the split
— tests/test_model_health.py's `from model_health import _derive_status`,
app.py's `from model_health import router`, admin_monitoring.py's/content.py's
`from model_health import health_map` — keep working unchanged.
"""
from __future__ import annotations

import os
from datetime import timedelta
from typing import Literal

from services.margin import is_paid_upstream

Status = Literal['healthy', 'degraded', 'down', 'unknown']

#: The summary-cache key, shared between model_health.py (which invalidates
#: it after a rollup changes anything) and model_health_api.py (which reads/
#: populates it). Defined here, not in either of those, so neither has to
#: import the other and risk a cycle — model_health.py already imports
#: model_health_api.py for the router/health_map re-export above.
_SUMMARY_CACHE_KEY = 'cache:model_health:summary'

# ── Tuning ──────────────────────────────────────────────────────────────────

#: How far back a sample still counts toward the current rollup. 180 min at
#: the default 600s probe interval is ~18 samples/model — enough for the rate
#: rules below to see a trend. The old 30 min default held exactly 3 samples
#: with no real traffic, so 1-of-3 failing crossed DEGRADED_BELOW and 2-of-3
#: crossed DOWN_BELOW -> disabled, flipping back next sweep. See
#: MIN_SAMPLES_FOR_RATE for the rest of that fix.
WINDOW = timedelta(minutes=int(os.getenv('MODEL_HEALTH_WINDOW_MIN', '180')))

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

#: The rate rules above only fire once a window holds this many samples.
#: Division of labour: DOWN_AFTER_CONSECUTIVE catches a hard break fast (3
#: straight failures is down regardless of sample count); the rate rules
#: catch a *flaky* model instead, and a rate from a handful of samples is
#: noise, not a trend. Below this threshold only the consecutive-failure and
#: latency rules may act.
MIN_SAMPLES_FOR_RATE = int(os.getenv('MODEL_HEALTH_MIN_SAMPLES', '5'))

#: Consecutive failures that mark a model down regardless of rate — catches a
#: model that just broke without waiting for the window average to sag.
DOWN_AFTER_CONSECUTIVE = int(os.getenv('MODEL_HEALTH_DOWN_AFTER', '3'))

#: A model answering this slowly is usable but not healthy.
DEGRADED_LATENCY_MS = int(os.getenv('MODEL_HEALTH_SLOW_MS', '15000'))

#: Samples older than this are deleted; the status page only shows the window.
RETENTION = timedelta(days=int(os.getenv('MODEL_HEALTH_RETENTION_DAYS', '7')))

#: Reason codes meaning "we currently cannot reach this model because of our
#: account, quota, or the gateway" — not "this model is broken". A model
#: whose window failures are entirely one of these is parked (`maintenance`,
#: reason recorded) instead of disabled, which reads as "broken" and isn't
#: true here. A *mixed* failure set (some real, some provider-fault) keeps
#: the existing disable behaviour.
PROVIDER_FAULT_REASONS = frozenset({
    'http_401', 'http_402', 'http_403', 'http_429', 'upstream_down',
})

#: How many admin-parked / discovery-landed `maintenance` rows one sweep
#: measures (lane 3 in _probe_targets). They are never promoted by the probe —
#: the point is purely to give them a truthful `last_ok_at`, without which
#: services/probe_gate.py can never let an admin enable them. At 40 a sweep,
#: 1,156 parked rows are covered in ~29 sweeps. Deliberately not "all of
#: them": health_loop sleeps PROBE_INTERVAL_S *after* a sweep returns, so a
#: sweep that probes 1,156 models at PROBE_CONCURRENCY does not overlap the
#: next one — it just starves the models we actually serve of fresh samples.
#: 0 disables the lane entirely.
PARKED_PROBE_SLICE = int(os.getenv('MODEL_HEALTH_PARKED_SLICE', '40'))

#: Sweeps between rechecks of a health-quarantined model. `_probe_targets`
#: normally skips `maintenance` entirely so an admin's/discovery's parking is
#: never undone by a probe — but a row *this* mechanism parked must not stay
#: parked forever, so it gets probed on this slow lane instead.
QUARANTINE_RECHECK_EVERY = int(os.getenv('MODEL_HEALTH_QUARANTINE_RECHECK', '6'))


# ── Decisions ───────────────────────────────────────────────────────────────


def _derive_status(
    sample_count: int,
    success_rate: float | None,
    consecutive_failures: int,
    latency_p50: int | None,
) -> Status:
    """Turn window statistics into a status.

    Order matters: three straight failures are down even if the window
    average still looks acceptable, because the average describes a past
    that no longer applies. The rate rules only fire once sample_count >=
    MIN_SAMPLES_FOR_RATE (see that constant) — below it, only the
    consecutive-failure and latency rules, which don't need a large window,
    may act. This is the fix for the live regression that motivated it: 3
    samples, 2 old failures, the latest a success (consecutive == 0) used to
    compute success_rate = 0.333 and get marked down despite just answering.

    Below MIN_SAMPLES_FOR_RATE and short of DOWN_AFTER_CONSECUTIVE, a window
    of ALL failures (success_rate == 0.0) used to fall through to the final
    `return 'healthy'` below -- e.g. (1, 0.0, 1, None) or (2, 0.0, 2, None):
    a model that has never once answered, reported healthy right up until
    its third straight failure. success_rate == 0.0 already means "zero
    successes among sample_count samples" by construction (it's an average
    of 1.0/0.0 per sample) -- no extra "ever succeeded" input is needed, and
    at sample_count >= MIN_SAMPLES_FOR_RATE this same value is already caught
    above (0.0 < DOWN_BELOW -> 'down'), so this only ever fires in the gap
    the rate rules don't cover. 'unknown' is the existing status for "no
    verdict yet" (see health_map/healthy_model_ids), not a new value.
    """
    if sample_count == 0 or success_rate is None:
        return 'unknown'
    if consecutive_failures >= DOWN_AFTER_CONSECUTIVE:
        return 'down'
    if sample_count >= MIN_SAMPLES_FOR_RATE:
        if success_rate < DOWN_BELOW:
            return 'down'
        if success_rate < DEGRADED_BELOW:
            return 'degraded'
    if latency_p50 is not None and latency_p50 > DEGRADED_LATENCY_MS:
        return 'degraded'
    if success_rate == 0.0:
        return 'unknown'
    return 'healthy'


def _is_provider_fault_only(failure_count: int, provider_fault_failure_count: int) -> bool:
    """True when every window failure was a provider-fault reason.

    Zero failures is never "provider-fault-only" — nothing to attribute —
    so this only matters together with a 'down' status.
    """
    return failure_count > 0 and provider_fault_failure_count == failure_count


def _target_catalog_state(
    *,
    status: Status,
    current_availability: str,
    input_per_million: float | None,
    health_quarantine_reason: str | None,
    provider_fault_only: bool,
    fault_reason: str | None,
    upstream: str | None = None,
) -> tuple[str, str | None]:
    """Decide a catalog row's next (availability, health_quarantine_reason).

    health_quarantine_reason is only ever non-NULL together with
    'maintenance', and only for rows THIS function parked — never a row an
    admin hid or discovery landed (NULL reason while still 'maintenance'),
    which must never be auto-promoted by a probe.

    A row on a PAID upstream is never auto-promoted here. `priced` asks "would
    this bill the user", which is not the same question as "do we make a
    margin on it" — a healthy probe plus any positive price was enough to put
    a model on sale, with no margin check anywhere on this path. That is the
    one bypass left around services/margin.py's guard (which covers the admin
    routes), and it is what gates enabling a paid upstream like OpenRouter.
    Promotion of a paid row belongs to an admin, who goes through the guard.
    Inert today: every catalog row sits on a free upstream.
    """
    priced = (input_per_million or 0) > 0

    # A row parked by an admin or landed by discovery — `maintenance` with no
    # quarantine reason — is not this mechanism's to touch, in EITHER
    # direction. Measurement may probe it (and must, or its last_ok_at can
    # never become non-NULL and services/probe_gate.py can never let an admin
    # enable it); the mirror may not act on what measurement finds.
    #
    # Without this, extending the sweep to parked rows would quietly do three
    # things nobody asked for: a `degraded` reading would move the row to
    # 'degraded' (visible), a provider-fault `down` reading would stamp a
    # quarantine reason on it — which is precisely the flag that makes a row
    # auto-promotable on the next healthy probe — and a plain `down` reading
    # would rewrite an admin's parking as 'disabled'. Promotion of a parked
    # model stays an admin action, taken through the guards.
    if current_availability == 'maintenance' and health_quarantine_reason is None:
        return 'maintenance', None

    if is_paid_upstream(upstream):
        # Never *promote*; parking/disabling a sick paid row still proceeds.
        if current_availability != 'available':
            return current_availability, health_quarantine_reason

    if status == 'healthy':
        if current_availability == 'maintenance':
            # Only a row we quarantined, and only once priced (unpriced
            # would bill nothing), may be auto-promoted.
            if health_quarantine_reason is not None and priced:
                return 'available', None
            return 'maintenance', health_quarantine_reason
        return ('available', health_quarantine_reason) if priced else \
            ('maintenance', health_quarantine_reason)

    if status == 'degraded':
        # Existing unconditional behaviour; leaving 'maintenance' clears the
        # reason since the column must stay meaningful (non-NULL implies
        # 'maintenance').
        return 'degraded', None

    if status == 'down':
        if provider_fault_only and fault_reason:
            return 'maintenance', fault_reason
        return 'disabled', None

    return current_availability, health_quarantine_reason


def _is_quarantine_recheck_sweep(sweep_count: int) -> bool:
    """True on the slow-lane sweep that rechecks health-quarantined models.

    Pure so it is testable without a database. Sweep counting starts at 1
    (probe_sweep increments before probing), so this is True on sweep
    QUARANTINE_RECHECK_EVERY, 2x that, ... — once an hour by default.
    """
    return QUARANTINE_RECHECK_EVERY > 0 and sweep_count % QUARANTINE_RECHECK_EVERY == 0


def _build_mirror_target(
    sample_count: int,
    success_rate: float | None,
    consecutive: int,
    p50: int | None,
    failures: int,
    provider_fault_failures: int,
    last_error: str | None,
) -> dict:
    """Package one model's window stats into the shape recompute_states needs
    both for the model_health_state upsert (status) and the catalog mirror
    decision below (provider_fault_only/fault_reason). Pure — everything here
    is already-fetched query results, no DB access of its own.
    """
    status = _derive_status(sample_count, success_rate, consecutive, p50)
    provider_fault_only = _is_provider_fault_only(failures, provider_fault_failures)
    return {
        'status': status,
        'success_rate': success_rate,
        'sample_count': sample_count,
        'provider_fault_only': provider_fault_only,
        # Failures were all provider-fault, so the latest one is necessarily
        # one of those codes — reused as the parking reason.
        'fault_reason': last_error if provider_fault_only else None,
        'last_error': last_error,
    }


def _plan_catalog_mirror(
    catalog_rows: list[dict],
    mirror_targets: dict[str, dict],
) -> list[dict]:
    """For each catalog row with a health target this sweep, decide its next
    availability/quarantine state and package everything the caller needs to
    execute the UPDATE and log/audit it. Pure — no DB access; catalog_rows and
    mirror_targets are already-fetched dicts.
    """
    plan = []
    for c in catalog_rows:
        target = mirror_targets.get(c['id']) or mirror_targets.get(c['provider_model_id'])
        if target is None:
            continue  # no samples in this window; leave the row alone
        new_availability, new_reason = _target_catalog_state(
            status=target['status'],
            current_availability=c['availability'],
            input_per_million=c['input_per_million'],
            health_quarantine_reason=c['health_quarantine_reason'],
            provider_fault_only=target['provider_fault_only'],
            fault_reason=target['fault_reason'],
            upstream=c.get('upstream'),
        )
        changed = new_availability != c['availability']
        # Reason recorded on a transition: the parking reason when we park,
        # the last failing probe when we disable, else None.
        reason_for_log = new_reason if new_availability == 'maintenance' else (
            target['last_error'] if new_availability == 'disabled' else None
        )
        plan.append({
            'id': c['id'], 'avail': new_availability, 'reason': new_reason,
            'from_a': c['availability'], 'reason_log': reason_for_log,
            'hstatus': target['status'], 'rate': target['success_rate'],
            'n': target['sample_count'], 'changed': changed,
        })
    return plan
