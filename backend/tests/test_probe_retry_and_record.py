"""The two halves of the «تست زنده» deadlock, and the retry that stopped a
40-second cooldown from reading as a dead model.

Background (measured on the live catalog, 2026-08-25). 1,156 of the 1,200
catalog rows sat at `maintenance` with `model_health_state.last_ok_at IS
NULL`. services/probe_gate.py refuses to make such a model `available`, and
the admin panel's own hint said to press «تست زنده» first. Pressing it could
not help: admin_pricing.test_model called providers.probe_model, showed the
answer, and discarded it. Nothing wrote last_ok_at except the background
rollup, and the background sweep skipped `maintenance` rows outright. No
sequence of admin actions could enable any of those 1,156 models.

Separately, a sample of 82 parked models found the single-shot probe
condemning models on failures that were plainly momentary -- upstream bodies
reading "All credentials for model X are cooling down" and "You have reached
the limit ... reset after 41s". Re-probing exactly those turned 5 of 70
apparent failures into answers.

Style follows tests/test_model_health_rollup.py: a local minimal async
session double rather than conftest's TestClient machinery, since nothing
here goes through HTTP.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import model_health_record as record_mod
import providers
from providers import ProbeResult


# ── The retry ───────────────────────────────────────────────────────────

class TestProbeModelResilient:
    @pytest.mark.asyncio
    async def test_a_success_is_returned_without_a_second_call(self):
        probe = AsyncMock(return_value=ProbeResult(True, 120))
        with patch.object(providers, 'probe_model', probe):
            result = await providers.probe_model_resilient(_P(), 'm1')
        assert result.ok is True
        assert probe.await_count == 1

    @pytest.mark.asyncio
    async def test_a_transient_failure_is_retried_and_the_success_wins(self):
        """The exact live case: http_429 'cooling down, reset after 42s'."""
        probe = AsyncMock(side_effect=[
            ProbeResult(False, 300, 'http_429', 429),
            ProbeResult(True, 800, None, 200),
        ])
        with patch.object(providers, 'probe_model', probe), \
             patch.object(providers, 'PROBE_RETRY_DELAY_S', 0):
            result = await providers.probe_model_resilient(_P(), 'm1')
        assert result.ok is True
        assert probe.await_count == 2

    @pytest.mark.asyncio
    async def test_a_timeout_is_retried(self):
        probe = AsyncMock(side_effect=[
            ProbeResult(False, 20000, 'ReadTimeout'),
            ProbeResult(True, 2400, None, 200),
        ])
        with patch.object(providers, 'probe_model', probe), \
             patch.object(providers, 'PROBE_RETRY_DELAY_S', 0):
            assert (await providers.probe_model_resilient(_P(), 'm1')).ok is True

    @pytest.mark.asyncio
    async def test_a_permanent_failure_is_not_retried(self):
        """404 'No active credentials for provider' and 401/403 are facts
        about our account or the upstream's inventory, not about a moment.
        Retrying them only makes a sweep look like a retry storm."""
        for reason, code in (('http_404', 404), ('http_401', 401), ('http_403', 403),
                             ('http_400', 400)):
            probe = AsyncMock(return_value=ProbeResult(False, 90, reason, code))
            with patch.object(providers, 'probe_model', probe), \
                 patch.object(providers, 'PROBE_RETRY_DELAY_S', 0):
                result = await providers.probe_model_resilient(_P(), 'm1')
            assert result.ok is False
            assert probe.await_count == 1, f'{reason} must not be retried'

    @pytest.mark.asyncio
    async def test_the_last_result_is_returned_not_the_first(self):
        """The recorded reason must describe the final attempt. Reporting
        the first one would pin a stale 429 on a model that is now 502."""
        probe = AsyncMock(side_effect=[
            ProbeResult(False, 300, 'http_429', 429),
            ProbeResult(False, 300, 'http_502', 502),
        ])
        with patch.object(providers, 'probe_model', probe), \
             patch.object(providers, 'PROBE_RETRY_DELAY_S', 0):
            result = await providers.probe_model_resilient(_P(), 'm1')
        assert result.error == 'http_502'

    @pytest.mark.asyncio
    async def test_retries_are_bounded(self):
        """A permanently-cooling model must not spin. retries=1 means at
        most two calls, whatever the upstream keeps saying."""
        probe = AsyncMock(return_value=ProbeResult(False, 300, 'http_429', 429))
        with patch.object(providers, 'probe_model', probe), \
             patch.object(providers, 'PROBE_RETRY_DELAY_S', 0):
            await providers.probe_model_resilient(_P(), 'm1')
        assert probe.await_count == 2


class _P:
    """Minimal Provider stand-in -- probe_model is patched out, so nothing
    here is dereferenced beyond the call signature."""
    name = 'litellm'
    v1 = 'http://x/v1'

    def headers(self):
        return {}


# ── The recording ───────────────────────────────────────────────────────

class _FakeSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.committed = 0

    async def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params or {}))
        return None

    async def commit(self):
        self.committed += 1


class _Ctx:
    def __init__(self, s):
        self._s = s

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *a):
        return False


@pytest.mark.asyncio
class TestRecordProbeSample:
    async def test_a_successful_probe_writes_an_event_and_publishes_last_ok_at(self):
        """The deadlock fix. Without the second statement the admin could
        press «تست زنده», see «سالم», and still be refused by the gate."""
        session = _FakeSession()
        with patch.object(record_mod, 'async_session', lambda: _Ctx(session)):
            await record_mod.record_probe_sample('m1', ok=True, latency_ms=430,
                                                 provider='litellm')
        sqls = [s for s, _ in session.calls]
        assert any('INSERT INTO model_health_event' in s for s in sqls)
        state_sql = next(s for s in sqls if 'model_health_state' in s)
        assert 'last_ok_at' in state_sql
        params = next(p for s, p in session.calls if 'model_health_state' in s)
        assert params['ok'] is True

    async def test_the_event_is_recorded_as_a_probe_not_traffic(self):
        session = _FakeSession()
        with patch.object(record_mod, 'async_session', lambda: _Ctx(session)):
            await record_mod.record_probe_sample('m1', ok=True, provider='litellm')
        params = next(p for s, p in session.calls if 'model_health_event' in s)
        assert params['s'] == 'probe'

    async def test_a_failing_probe_does_not_erase_a_previous_success(self):
        """COALESCE, not EXCLUDED. A model that answered last week and is
        cooling down today has still been proven to work, and the gate's
        question is "has this ever answered", not "did it answer just now"."""
        session = _FakeSession()
        with patch.object(record_mod, 'async_session', lambda: _Ctx(session)):
            await record_mod.record_probe_sample('m1', ok=False, error='http_429',
                                                 provider='litellm')
        state_sql = next(s for s, _ in session.calls if 'model_health_state' in s)
        assert 'COALESCE(EXCLUDED.last_ok_at' in state_sql

    async def test_status_is_not_overwritten_on_an_existing_row(self):
        """One sample is not a window. Deriving a status from it is the bug
        MIN_SAMPLES_FOR_RATE exists to prevent, so the ON CONFLICT branch
        must leave `status` to the windowed rollup."""
        session = _FakeSession()
        with patch.object(record_mod, 'async_session', lambda: _Ctx(session)):
            await record_mod.record_probe_sample('m1', ok=True, provider='litellm')
        state_sql = next(s for s, _ in session.calls if 'model_health_state' in s)
        conflict = state_sql.split('DO UPDATE SET', 1)[1]
        assert 'status' not in conflict.replace('seed_status', '')

    async def test_a_database_failure_never_raises_on_the_caller(self):
        """Same contract as record(): health bookkeeping must not turn a
        working probe into a 500 for the admin who asked for it."""
        class _Boom(_FakeSession):
            async def execute(self, stmt, params=None):
                raise RuntimeError('database is on fire')

        with patch.object(record_mod, 'async_session', lambda: _Ctx(_Boom())):
            await record_mod.record_probe_sample('m1', ok=True, provider='litellm')

    async def test_no_session_is_a_no_op(self):
        with patch.object(record_mod, 'async_session', None):
            await record_mod.record_probe_sample('m1', ok=True, provider='litellm')


class TestProbeBudget:
    """The retry doubles the worst case from 20s to 43s. The admin panel
    reaches the API through a Next.js rewrite that hard-caps at 30s, past
    which a completed probe comes back to the user as a bare 500 -- so any
    request-path caller passes a budget and the retry respects it."""

    @pytest.mark.asyncio
    async def test_a_retry_that_cannot_finish_in_budget_is_not_started(self):
        """A slow transient failure eats the budget. Fake clock rather than
        real sleeping: the decision is about elapsed wall-clock, so the test
        has to be able to state how much of it has passed."""
        clock = iter([0.0, 19.0, 19.0])
        probe = AsyncMock(return_value=ProbeResult(False, 19000, 'http_502', 502))
        with patch.object(providers, 'probe_model', probe), \
             patch.object(providers.time, 'monotonic', lambda: next(clock)), \
             patch.object(providers, 'PROBE_RETRY_DELAY_S', 3):
            # 19s already gone; +3s delay +20s timeout would blow a 26s budget.
            await providers.probe_model_resilient(_P(), 'm1', timeout=20.0, budget_s=26)
        assert probe.await_count == 1

    @pytest.mark.asyncio
    async def test_a_fast_transient_failure_still_gets_its_retry(self):
        """The case the retry exists for: a 429 'cooling down' comes back in
        well under a second, so there is ample budget left."""
        probe = AsyncMock(side_effect=[
            ProbeResult(False, 200, 'http_429', 429),
            ProbeResult(True, 900, None, 200),
        ])
        with patch.object(providers, 'probe_model', probe), \
             patch.object(providers, 'PROBE_RETRY_DELAY_S', 0):
            result = await providers.probe_model_resilient(_P(), 'm1', timeout=5.0, budget_s=26)
        assert result.ok is True
        assert probe.await_count == 2

    @pytest.mark.asyncio
    async def test_no_budget_means_the_background_sweep_is_unconstrained(self):
        probe = AsyncMock(return_value=ProbeResult(False, 19000, 'http_502', 502))
        with patch.object(providers, 'probe_model', probe), \
             patch.object(providers, 'PROBE_RETRY_DELAY_S', 0):
            await providers.probe_model_resilient(_P(), 'm1', timeout=20.0)
        assert probe.await_count == 2
