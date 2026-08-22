"""Tests for backend/services/task_scheduler.py -- the 5-field cron
evaluator and the background scheduling loop for scheduled tasks.

No live Postgres/network. The cron evaluator is pure Python, tested
directly. The atomic-claim tests use a minimal fake session that simulates
the Postgres `UPDATE ... RETURNING` row-visibility rule that actually
prevents two overlapping ticks from double-running the same task in
production: once a row's next_run_at is set to NULL by a claim, a second
claim sees nothing to claim for that row.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import services.task_scheduler as sched_mod


# ── _parse_cron_field: numbers, *, */n, ranges, lists ───────────────────

class TestParseCronField:
    def test_wildcard(self):
        assert sched_mod._parse_cron_field('*', 0, 4) == {0, 1, 2, 3, 4}

    def test_single_number(self):
        assert sched_mod._parse_cron_field('9', 0, 23) == {9}

    def test_step(self):
        assert sched_mod._parse_cron_field('*/15', 0, 59) == {0, 15, 30, 45}

    def test_range(self):
        assert sched_mod._parse_cron_field('1-5', 0, 7) == {1, 2, 3, 4, 5}

    def test_stepped_range(self):
        assert sched_mod._parse_cron_field('0-10/2', 0, 23) == {0, 2, 4, 6, 8, 10}

    def test_list(self):
        assert sched_mod._parse_cron_field('1,3,5', 0, 7) == {1, 3, 5}

    def test_list_of_mixed_forms(self):
        assert sched_mod._parse_cron_field('0,10-12,*/20', 0, 23) == {0, 10, 11, 12, 20}

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            sched_mod._parse_cron_field('99', 0, 23)

    def test_zero_step_raises(self):
        with pytest.raises(ValueError):
            sched_mod._parse_cron_field('*/0', 0, 59)

    def test_empty_field_raises(self):
        with pytest.raises(ValueError):
            sched_mod._parse_cron_field('', 0, 59)


class TestCompileCronValidation:
    def test_wrong_field_count_raises(self):
        with pytest.raises(ValueError):
            sched_mod._compile_cron('0 9 * *')

    def test_valid_five_fields_compiles(self):
        compiled = sched_mod._compile_cron('*/5 9-17 * * 1-5')
        assert compiled['minutes'] == {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}
        assert compiled['hours'] == set(range(9, 18))
        assert compiled['dom_restricted'] is False
        assert compiled['dow_restricted'] is True


# ── cron_matches: naive AND tz-aware datetimes ──────────────────────────

class TestCronMatchesNaiveAndAware:
    def test_matches_naive_utc(self):
        dt = datetime(2026, 8, 22, 9, 0)
        assert sched_mod.cron_matches('0 9 * * *', dt) is True

    def test_matches_tz_aware_utc(self):
        dt = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)
        assert sched_mod.cron_matches('0 9 * * *', dt) is True

    def test_tz_aware_non_utc_is_normalized_before_matching(self):
        # 12:00 at UTC+3 is 09:00 UTC.
        tz_plus3 = timezone(timedelta(hours=3))
        dt = datetime(2026, 8, 22, 12, 0, tzinfo=tz_plus3)
        assert sched_mod.cron_matches('0 9 * * *', dt) is True

    def test_naive_and_aware_agree_for_the_same_instant(self):
        naive = datetime(2026, 8, 22, 9, 30)
        aware = naive.replace(tzinfo=timezone.utc)
        assert sched_mod.cron_matches('30 9 * * *', naive) is True
        assert sched_mod.cron_matches('30 9 * * *', aware) is True

    def test_non_matching_minute_is_false_for_both(self):
        naive = datetime(2026, 8, 22, 9, 1)
        aware = naive.replace(tzinfo=timezone.utc)
        assert sched_mod.cron_matches('0 9 * * *', naive) is False
        assert sched_mod.cron_matches('0 9 * * *', aware) is False


class TestCronDayOfWeekOrQuirk:
    def test_dom_or_dow_when_both_restricted(self):
        # 2026-08-22 is a Saturday (Python weekday()==5); cron Saturday==6.
        dt = datetime(2026, 8, 22, 9, 0)
        assert dt.weekday() == 5
        # day-of-month=1 does NOT match (22 != 1), but day-of-week=6 does --
        # standard cron ORs the two when both are restricted.
        assert sched_mod.cron_matches('0 9 1 * 6', dt) is True

    def test_dom_only_when_dow_is_wildcard(self):
        assert sched_mod.cron_matches('0 9 1 * *', datetime(2026, 8, 1, 9, 0)) is True
        assert sched_mod.cron_matches('0 9 1 * *', datetime(2026, 8, 2, 9, 0)) is False

    def test_dow_only_when_dom_is_wildcard(self):
        # Sunday = 0 in cron numbering; 2026-08-23 is a Sunday.
        dt = datetime(2026, 8, 23, 9, 0)
        assert dt.isoweekday() == 7
        assert sched_mod.cron_matches('0 9 * * 0', dt) is True
        assert sched_mod.cron_matches('0 9 * * 0', dt + timedelta(days=1)) is False

    def test_dow_7_also_means_sunday(self):
        dt = datetime(2026, 8, 23, 9, 0)
        assert sched_mod.cron_matches('0 9 * * 7', dt) is True


# ── compute_next_run ─────────────────────────────────────────────────────

class TestComputeNextRun:
    def test_daily_next_run_same_day_if_time_not_passed(self):
        after = datetime(2026, 8, 22, 8, 0)
        assert sched_mod.compute_next_run('0 9 * * *', after) == datetime(2026, 8, 22, 9, 0)

    def test_next_run_is_strictly_after_not_equal(self):
        after = datetime(2026, 8, 22, 9, 0)  # exactly at 9:00
        assert sched_mod.compute_next_run('0 9 * * *', after) == datetime(2026, 8, 23, 9, 0)

    def test_hourly_step(self):
        after = datetime(2026, 8, 22, 9, 5)
        assert sched_mod.compute_next_run('0 */2 * * *', after) == datetime(2026, 8, 22, 10, 0)

    def test_impossible_cron_returns_none(self):
        # February never has a 30th, in any year.
        assert sched_mod.compute_next_run('0 0 30 2 *', datetime(2026, 1, 1)) is None

    def test_accepts_tz_aware_input_and_returns_naive(self):
        after = datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc)
        result = sched_mod.compute_next_run('0 9 * * *', after)
        assert result == datetime(2026, 8, 22, 9, 0)
        assert result.tzinfo is None

    def test_invalid_expression_raises_immediately(self):
        with pytest.raises(ValueError):
            sched_mod.compute_next_run('not a cron', datetime(2026, 1, 1))


# ── Atomic claim: two overlapping ticks cannot double-run a task ────────

class _FakeClaimSession:
    """Simulates the Postgres UPDATE ... RETURNING semantics that actually
    prevent double-claiming in production: once a row's next_run_at is set
    to NULL, a second claim attempt against the same rows finds nothing."""

    def __init__(self, rows):
        self._rows = rows  # list of plain dicts

    async def execute(self, stmt, params):
        now = params['now']
        claimed = []
        for row in self._rows:
            if row['is_active'] and row['next_run_at'] is not None and row['next_run_at'] <= now:
                row['next_run_at'] = None
                claimed.append(MagicMock(**{k: v for k, v in row.items() if k != 'is_active'}))
        result = MagicMock()
        result.fetchall.return_value = claimed
        return result

    async def commit(self):
        return None


class TestClaimDueTasksAtomicity:
    @pytest.mark.asyncio
    async def test_second_overlapping_claim_gets_nothing(self):
        now = datetime(2026, 8, 22, 9, 0)
        rows = [{
            'id': 1, 'user_id': 7, 'model': 'm', 'prompt': 'p',
            'cron_expression': '0 9 * * *', 'is_active': True, 'next_run_at': now,
        }]
        session = _FakeClaimSession(rows)

        first = await sched_mod.claim_due_tasks(session, now)
        second = await sched_mod.claim_due_tasks(session, now)

        assert len(first) == 1
        assert first[0].id == 1
        assert second == []

    @pytest.mark.asyncio
    async def test_inactive_task_never_claimed(self):
        now = datetime(2026, 8, 22, 9, 0)
        rows = [{
            'id': 2, 'user_id': 7, 'model': 'm', 'prompt': 'p',
            'cron_expression': '0 9 * * *', 'is_active': False, 'next_run_at': now,
        }]
        session = _FakeClaimSession(rows)
        assert await sched_mod.claim_due_tasks(session, now) == []

    @pytest.mark.asyncio
    async def test_future_task_not_yet_claimed(self):
        now = datetime(2026, 8, 22, 9, 0)
        rows = [{
            'id': 3, 'user_id': 7, 'model': 'm', 'prompt': 'p',
            'cron_expression': '0 9 * * *', 'is_active': True,
            'next_run_at': now + timedelta(hours=1),
        }]
        session = _FakeClaimSession(rows)
        assert await sched_mod.claim_due_tasks(session, now) == []

    @pytest.mark.asyncio
    async def test_already_claimed_task_has_no_next_run_at_to_match_again(self):
        now = datetime(2026, 8, 22, 9, 0)
        rows = [{
            'id': 4, 'user_id': 7, 'model': 'm', 'prompt': 'p',
            'cron_expression': '0 9 * * *', 'is_active': True, 'next_run_at': None,
        }]
        session = _FakeClaimSession(rows)
        assert await sched_mod.claim_due_tasks(session, now) == []


# ── TASK_SCHEDULER_ENABLED gate defaults OFF ────────────────────────────

class TestEnvFlagParsing:
    def test_default_false_when_unset(self, monkeypatch):
        monkeypatch.delenv('SOME_FLAG', raising=False)
        assert sched_mod._env_flag('SOME_FLAG') is False

    @pytest.mark.parametrize('value', ['1', 'true', 'True', 'yes', 'on'])
    def test_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv('SOME_FLAG', value)
        assert sched_mod._env_flag('SOME_FLAG') is True

    @pytest.mark.parametrize('value', ['0', 'false', 'no', 'off', ''])
    def test_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv('SOME_FLAG', value)
        assert sched_mod._env_flag('SOME_FLAG') is False


class TestSchedulerLoopGatedByDefault:
    def test_module_level_flag_defaults_off_in_this_test_environment(self):
        """No .env/CI config sets TASK_SCHEDULER_ENABLED -- this pins that
        assumption so a stray env var flip is caught immediately."""
        assert sched_mod.TASK_SCHEDULER_ENABLED is False

    @pytest.mark.asyncio
    async def test_loop_does_no_work_while_disabled(self, monkeypatch):
        """While disabled the loop must never claim or run a task.

        DELIBERATE CONTRACT CHANGE -- read before "fixing" this test back.
        This assertion used to be `scheduler_loop()` *returns* within one
        second when the flag is off, which was correct while the only
        source of truth was the `TASK_SCHEDULER_ENABLED` env var: an env
        var cannot change without a process restart, so a one-shot check
        at entry lost nothing.

        The gate is now `env var OR the task_scheduler_enabled DB flag`,
        and the whole point of that DB flag is that an admin can flip it
        from the panel without an SSH session and a container restart. A
        loop that returned at startup could never observe the flip, so the
        panel switch would silently do nothing -- exactly the class of
        fake control this project is trying to eliminate. The loop
        therefore keeps ticking while disabled, purely to re-read the
        flag.

        What actually matters -- and what this test now pins -- is the
        real invariant behind the original assertion: while disabled, no
        work happens and no money is spent. `scheduler_tick` is what
        claims and runs due tasks, so "never called" is the honest
        version of "the loop is off". The companion proof that a mid-run
        flip is picked up lives in
        tests/test_env_flag_db_override.py::test_flag_flip_mid_run_takes_effect_within_one_tick.
        """
        import asyncio

        monkeypatch.setattr(sched_mod, 'TASK_SCHEDULER_ENABLED', False)
        # DB flag off too, so the effective state is off.
        async def _db_off():
            return False
        monkeypatch.setattr(sched_mod, '_db_scheduler_flag', _db_off)

        tick_calls = []

        async def _spy_tick():
            tick_calls.append(1)
            return 0
        monkeypatch.setattr(sched_mod, 'scheduler_tick', _spy_tick)

        # Collapse the sleep so several ticks elapse in negligible time --
        # otherwise this test would have to wait TASK_SCHEDULER_TICK_SECONDS
        # (60s) to see even one iteration.
        #
        # `sched_mod.asyncio` IS the global asyncio module object, so this
        # patch is process-wide for the duration of the test: the real
        # sleep has to be captured up front, or the yield below re-enters
        # this same fake and records a bogus 0-second entry.
        real_sleep = asyncio.sleep
        sleeps = []

        async def _fast_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= 5:
                raise asyncio.CancelledError
            await real_sleep(0)
        monkeypatch.setattr(sched_mod.asyncio, 'sleep', _fast_sleep)

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(sched_mod.scheduler_loop(), timeout=5)

        assert tick_calls == [], 'scheduler_tick ran while the scheduler was disabled'
        # It really did keep looping (rather than returning early), which is
        # what makes a later flag flip observable at all.
        assert len(sleeps) >= 5
        assert all(s == sched_mod.TASK_SCHEDULER_TICK_SECONDS for s in sleeps)
