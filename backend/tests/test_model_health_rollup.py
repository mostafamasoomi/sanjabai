"""
Regression tests for the model-health catalog rollup fix.

Covers the pure decision functions in model_health.py directly (no DB
needed) plus the couple of DB-touching helpers that are cheap to exercise
with a small fake session, following the mocking style used elsewhere in
this suite (test_provider_routing.py, conftest.py's mock_async_session):
Redis/asyncpg/migrate are mocked at import time in conftest.py, and
`pytest.ini` promotes un-awaited AsyncMock coroutines and the deprecated
httpx `app=` shortcut to hard errors, so neither is reintroduced here.

Background: model_catalog.availability was oscillating 37 -> 19 -> 30
available models because (1) the rollup window held exactly 3 samples, so
the success-rate thresholds were statistical noise, and (2) provider/account
faults (kr/* out of credit, openrouter/*:free quota exhausted) were charged
to the model as 'disabled' instead of parked as 'maintenance'. See
model_health.py's module-level comments for the full writeup.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import model_health
import model_health_policy as policy

# The pure decision layer (tuning constants, _derive_status,
# _is_provider_fault_only, _target_catalog_state, _is_quarantine_recheck_sweep)
# lives in model_health_policy.py -- split out of model_health.py to keep both
# files under the project's 500-line cap. Tests for that layer import `policy`
# directly; model_health.py only re-exports `_derive_status` (for the older
# tests/test_model_health.py), so anything else must come from `policy`.
# model_health._probe_targets is DB-touching and still lives in model_health.py.


class TestDeriveStatusSampleGating:
    """The exact live regression: 3 samples is not a trend."""

    def test_three_samples_one_success_most_recent_is_not_down(self):
        # sample_count=3, success_rate=0.333 (1 ok / 2 fail), but the streak
        # is broken (consecutive_failures=0 -- the latest probe succeeded).
        # Below MIN_SAMPLES_FOR_RATE the rate rule must not fire, so this
        # must not be 'down' -- that was the live sanjab/gemini-2.5-flash-lite
        # bug: disabled with consecutive_failures == 0.
        status = policy._derive_status(3, 0.333, 0, None)
        assert status != 'down'

    def test_three_samples_three_consecutive_failures_is_still_down(self):
        # Fast-break detection must survive: a hard break is down within one
        # window regardless of how few samples exist.
        assert policy._derive_status(3, 0.0, 3, None) == 'down'

    def test_twenty_samples_low_rate_is_down(self):
        # Once there is a real sample count, the rate rule must still work.
        assert policy._derive_status(20, 0.333, 0, None) == 'down'

    def test_below_min_samples_only_consecutive_and_latency_rules_act(self):
        # 4 samples < MIN_SAMPLES_FOR_RATE(5): a terrible rate alone must not
        # trip degraded/down, but a slow p50 still may (latency doesn't need
        # a large window to mean something).
        assert policy._derive_status(4, 0.1, 0, None) == 'healthy'
        assert policy._derive_status(4, 0.1, 0, 20_000) == 'degraded'

    def test_at_min_samples_rate_rule_activates(self):
        assert policy._derive_status(policy.MIN_SAMPLES_FOR_RATE, 0.1, 0, None) == 'down'


class TestProviderFaultClassifier:
    """http_402/429/upstream_down etc. are our account/quota, not the model."""

    def test_all_provider_fault_failures_is_provider_fault_only(self):
        assert policy._is_provider_fault_only(3, 3) is True

    def test_mixed_failures_is_not_provider_fault_only(self):
        assert policy._is_provider_fault_only(3, 2) is False

    def test_no_failures_is_not_provider_fault_only(self):
        assert policy._is_provider_fault_only(0, 0) is False

    def test_provider_fault_only_down_parks_instead_of_disabling(self):
        availability, reason = policy._target_catalog_state(
            status='down',
            current_availability='available',
            input_per_million=100,
            health_quarantine_reason=None,
            provider_fault_only=True,
            fault_reason='http_402',
        )
        assert (availability, reason) == ('maintenance', 'http_402')

    def test_mixed_failure_down_disables(self):
        availability, reason = policy._target_catalog_state(
            status='down',
            current_availability='available',
            input_per_million=100,
            health_quarantine_reason=None,
            provider_fault_only=False,
            fault_reason=None,
        )
        assert (availability, reason) == ('disabled', None)

    def test_healthy_promotes_a_health_quarantined_priced_row(self):
        availability, reason = policy._target_catalog_state(
            status='healthy',
            current_availability='maintenance',
            input_per_million=100,
            health_quarantine_reason='http_402',
            provider_fault_only=False,
            fault_reason=None,
            # Required, and this test failed for months without it: the
            # `upstream` kwarg was added later with a None default, and
            # is_paid_upstream(None) is True (see the test below), so
            # omitting it silently exercised the never-promote-a-paid-row
            # branch instead of the promotion this test is named for.
            upstream='litellm',
        )
        assert (availability, reason) == ('available', None)

    def test_an_unknown_upstream_is_treated_as_paid_and_never_promoted(self):
        """Fail-safe direction: we cannot prove a row costs us nothing, so
        we do not auto-put it on sale. Pinned because the whole point of the
        test above is that omitting `upstream` lands here by accident."""
        availability, _ = policy._target_catalog_state(
            status='healthy',
            current_availability='maintenance',
            input_per_million=100,
            health_quarantine_reason='http_402',
            provider_fault_only=False,
            fault_reason=None,
        )
        assert availability == 'maintenance'

    def test_healthy_never_promotes_admin_or_discovery_parked_row(self):
        # health_quarantine_reason is NULL -- this row was not parked by
        # health -- so a probe must never move it out of maintenance.
        availability, reason = policy._target_catalog_state(
            status='healthy',
            current_availability='maintenance',
            input_per_million=100,
            health_quarantine_reason=None,
            provider_fault_only=False,
            fault_reason=None,
        )
        assert availability == 'maintenance'

    def test_healthy_never_promotes_an_unpriced_quarantined_row(self):
        availability, reason = policy._target_catalog_state(
            status='healthy',
            current_availability='maintenance',
            input_per_million=0,
            health_quarantine_reason='http_402',
            provider_fault_only=False,
            fault_reason=None,
        )
        assert availability == 'maintenance'


class TestParkedRowsAreMeasuredButNeverRelabelled:
    """The invariant that makes the parked-model measurement lane safe.

    A `maintenance` row with NO quarantine reason was parked by an admin or
    landed by discovery. The probe may now measure it (lane 3 of
    _probe_targets) -- but the mirror must not act on what it finds, in
    either direction. Each test below is a way the mirror WOULD have acted
    before this guard existed.
    """

    def _parked(self, status, **kw):
        return policy._target_catalog_state(
            status=status, current_availability='maintenance',
            input_per_million=kw.pop('input_per_million', 100),
            health_quarantine_reason=None, provider_fault_only=kw.pop('pf', False),
            fault_reason=kw.pop('fault_reason', None), upstream=kw.pop('upstream', 'litellm'),
        )

    def test_healthy_does_not_promote_it(self):
        assert self._parked('healthy') == ('maintenance', None)

    def test_degraded_does_not_make_it_visible(self):
        """Would have returned ('degraded', None) -- and 'degraded' is a
        served state, so probing parked rows would have put models nobody
        approved in front of users."""
        assert self._parked('degraded') == ('maintenance', None)

    def test_provider_fault_down_does_not_stamp_a_quarantine_reason(self):
        """The nastiest one. Stamping a reason on an admin-parked row is
        what makes it auto-promotable on the next healthy probe -- so a
        failing probe followed by a passing one would have published it."""
        assert self._parked('down', pf=True, fault_reason='http_429') == ('maintenance', None)

    def test_plain_down_does_not_rewrite_the_parking_as_disabled(self):
        assert self._parked('down') == ('maintenance', None)

    def test_a_quarantined_row_is_still_this_mechanisms_to_manage(self):
        """The guard keys on the reason being NULL, so a row THIS mechanism
        parked keeps its existing recheck-and-promote behaviour."""
        availability, _ = policy._target_catalog_state(
            status='healthy', current_availability='maintenance', input_per_million=100,
            health_quarantine_reason='http_402', provider_fault_only=False,
            fault_reason=None, upstream='litellm',
        )
        assert availability == 'available'


class TestQuarantineRecheckSweep:
    """A quarantined model is probed on the slow lane, not every sweep."""

    def test_recheck_fires_every_nth_sweep(self):
        n = policy.QUARANTINE_RECHECK_EVERY
        assert policy._is_quarantine_recheck_sweep(n) is True
        assert policy._is_quarantine_recheck_sweep(2 * n) is True

    def test_recheck_skipped_on_other_sweeps(self):
        n = policy.QUARANTINE_RECHECK_EVERY
        for sweep in range(1, n):
            assert policy._is_quarantine_recheck_sweep(sweep) is False

    # calls[0], not calls[-1]: _probe_targets now issues a SECOND query for
    # the parked-model measurement lane (see TestParkedProbeLane below), so
    # the last call is no longer the serving-models one these assert on.
    @pytest.mark.asyncio
    async def test_probe_targets_passes_recheck_flag_through_to_the_query(self):
        session = _FakeSession(rows=[SimpleNamespace(provider_model_id='m1', up='litellm')])
        with patch.object(model_health, 'async_session', lambda: _FakeSessionCtx(session)):
            result = await model_health._probe_targets(recheck_quarantine=True)

        assert ('m1', 'litellm') in result
        sql, params = session.calls[0]
        assert 'health_quarantine_reason' in sql
        assert params == {'recheck': True}

    @pytest.mark.asyncio
    async def test_probe_targets_defaults_to_no_recheck(self):
        session = _FakeSession(rows=[])
        with patch.object(model_health, 'async_session', lambda: _FakeSessionCtx(session)):
            await model_health._probe_targets()

        _, params = session.calls[0]
        assert params == {'recheck': False}


class TestRecomputeStatesPreservesLastOkAt:
    """The P1 regression: recompute_states()'s ON CONFLICT upsert must not
    erase a model's proof-of-life just because the current 180-minute window
    happens to hold only failures.

    model_health_record.py's single-probe writer already guards this with
    COALESCE(EXCLUDED.last_ok_at, model_health_state.last_ok_at) (see the
    comment there) -- the windowed rollup upsert a few lines below it in this
    same table never got the same guard, so a bad window could null out a
    last_ok_at a fresh live probe had just set moments earlier, right back to
    "never proven to work" -- which services/probe_gate.py treats as
    never-servable.

    _FakeUpsertSession below does not hardcode the fix into the fake: it
    reads whichever SET clause the real code under test actually issues and
    applies THAT semantics to its in-memory state. Revert the COALESCE in
    model_health.py back to a bare `EXCLUDED.last_ok_at` and this test goes
    red on its own, because the fake now nulls the state exactly like a real
    Postgres ON CONFLICT DO UPDATE would.
    """

    @pytest.mark.asyncio
    async def test_all_failing_window_does_not_null_a_prior_last_ok_at(self):
        prior_last_ok_at = 'PRIOR-OK-TIMESTAMP'
        session = _FakeUpsertSession(
            event_row=_MappingRow(
                model_id='m1', provider='litellm', sample_count=3,
                success_rate=0.0, p50=None, p95=None,
                last_ok_at=None,  # the window itself has zero successes
                last_error_at='NEW-ERROR-TIMESTAMP',
            ),
            streak_rows=[(False,), (False,), (False,)],
            fault_row=SimpleNamespace(
                failures=3, provider_fault_failures=0, last_error='timeout',
            ),
            existing_last_ok_at=prior_last_ok_at,
        )
        with patch.object(model_health, 'async_session', lambda: _FakeSessionCtx(session)), \
             patch.object(model_health.rds, 'delete', AsyncMock()):
            await model_health.recompute_states()

        assert session.state['last_ok_at'] == prior_last_ok_at, (
            'an all-failing rollup window nulled a previously-recorded '
            'last_ok_at -- the model looks like it has never once answered'
        )

    @pytest.mark.asyncio
    async def test_a_window_with_a_success_still_advances_last_ok_at(self):
        """Sanity check on the other direction: COALESCE must not get stuck
        -- a window that DOES contain a success still has to move the
        watermark forward, not freeze it at the old value."""
        session = _FakeUpsertSession(
            event_row=_MappingRow(
                model_id='m1', provider='litellm', sample_count=3,
                success_rate=0.667, p50=200, p95=300,
                last_ok_at='NEW-OK-TIMESTAMP', last_error_at=None,
            ),
            streak_rows=[(True,)],
            fault_row=SimpleNamespace(
                failures=1, provider_fault_failures=0, last_error='timeout',
            ),
            existing_last_ok_at='OLD-OK-TIMESTAMP',
        )
        with patch.object(model_health, 'async_session', lambda: _FakeSessionCtx(session)), \
             patch.object(model_health.rds, 'delete', AsyncMock()):
            await model_health.recompute_states()

        assert session.state['last_ok_at'] == 'NEW-OK-TIMESTAMP'


class TestParkedProbeLane:
    """Lane 3 of _probe_targets: admin-parked / discovery-landed rows are
    MEASURED on a rotating slice so their model_health_state.last_ok_at can
    ever become non-NULL. Before this lane existed, 1,156 of 1,200 catalog
    rows were excluded from every probe -- and services/probe_gate.py refuses
    to make a model available until that column is non-NULL, so no sequence
    of admin actions could enable any of them."""

    @pytest.mark.asyncio
    async def test_parked_rows_are_queried_on_a_bounded_least_recent_slice(self):
        session = _FakeSession(rows=[SimpleNamespace(provider_model_id='p1', up='omniroute')])
        with patch.object(model_health, 'async_session', lambda: _FakeSessionCtx(session)):
            result = await model_health._probe_targets()

        sql, params = session.calls[-1]
        assert "c.availability = 'maintenance'" in sql
        assert 'c.health_quarantine_reason IS NULL' in sql
        # Least-recently-checked first, never-checked first of all: that is
        # what makes the rotation cover everything without a stored cursor.
        assert 'ORDER BY s.checked_at ASC NULLS FIRST' in sql
        assert params == {'slice': policy.PARKED_PROBE_SLICE}
        assert ('p1', 'omniroute') in result

    @pytest.mark.asyncio
    async def test_a_row_in_both_lanes_is_probed_once(self):
        """Both queries are answered with the same id by the fake. A model
        probed twice in one sweep would record two samples and skew its own
        success rate."""
        session = _FakeSession(rows=[SimpleNamespace(provider_model_id='dup', up='litellm')])
        with patch.object(model_health, 'async_session', lambda: _FakeSessionCtx(session)):
            result = await model_health._probe_targets()

        assert result.count(('dup', 'litellm')) == 1

    @pytest.mark.asyncio
    async def test_slice_of_zero_disables_the_lane_entirely(self):
        session = _FakeSession(rows=[])
        with patch.object(model_health, 'PARKED_PROBE_SLICE', 0), \
             patch.object(model_health, 'async_session', lambda: _FakeSessionCtx(session)):
            await model_health._probe_targets()

        assert len(session.calls) == 1


# ── Fakes ─────────────────────────────────────────────────────────────────
#
# Local and minimal on purpose: conftest.py's mock_async_session fixture
# patches app.async_session/_database._real_async_session for endpoint tests
# driven through TestClient, which is heavier machinery than a direct call
# into model_health._probe_targets needs.


class _MappingRow:
    """Minimal stand-in for a SQLAlchemy Row exposing `_mapping` -- same
    helper other test files in this suite use, since
    `dict(r._mapping)` is what recompute_states() calls on each row."""

    def __init__(self, **kwargs):
        self._mapping = dict(kwargs)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeUpsertSession:
    """Drives recompute_states() through a single model's worth of rows,
    with just enough SQL-text awareness to route each of its five queries
    (window aggregate, failure streak, fault classification, the
    model_health_state upsert, the stale-status sweep) plus the catalog
    mirror/orphan-check tail queries, which are given empty results so that
    part of recompute_states is a no-op here -- this test is only about the
    upsert's last_ok_at semantics.

    The upsert branch does NOT hardcode COALESCE: it inspects the literal SET
    clause the code under test issues and applies that semantics to
    ``self.state``, the same way a real ON CONFLICT DO UPDATE would. That is
    what makes a revert of the model_health.py fix turn this test red.
    """

    def __init__(self, event_row, streak_rows, fault_row, existing_last_ok_at):
        self._event_row = event_row
        self._streak_rows = streak_rows
        self._fault_row = fault_row
        self.state = {'last_ok_at': existing_last_ok_at}
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        params = params or {}
        self.calls.append((sql, params))

        if 'FROM model_health_event WHERE created_at >= :cutoff GROUP BY model_id' in sql:
            return _FakeResult([self._event_row])
        if 'ORDER BY created_at DESC LIMIT 10' in sql:
            return _FakeResult(self._streak_rows)
        if 'provider_fault_failures' in sql:
            return _FakeResult([self._fault_row])
        if 'INSERT INTO model_health_state' in sql:
            if 'last_ok_at = COALESCE(EXCLUDED.last_ok_at' in sql:
                if params.get('last_ok') is not None:
                    self.state['last_ok_at'] = params['last_ok']
                # else: preserve self.state['last_ok_at'] unchanged
            else:
                # Whatever else the SET clause says, a bare EXCLUDED
                # reference always takes the freshly-computed value —
                # including NULL, which is the bug this test guards.
                self.state['last_ok_at'] = params.get('last_ok')
            return _FakeResult([])
        if "SET status = 'unknown'" in sql:
            return _FakeResult([])
        if 'FROM model_catalog c WHERE' in sql:
            return _FakeResult([])
        if "availability = 'available'" in sql and 'public_id IS NULL' in sql:
            return _FakeResult([])
        return _FakeResult([])

    async def commit(self):
        pass


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params or {}))
        return _FakeResult(self._rows)

    async def commit(self):
        pass


class _FakeSessionCtx:
    def __init__(self, session: _FakeSession):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        pass
