"""Tests proving the DB-flag-OR-env-var wiring for the two flags that gate
a *synchronous, module-level, already-running* subsystem rather than a
single request handler:

* services/task_scheduler.py's scheduler_loop() -- gated by
  TASK_SCHEDULER_ENABLED (env) OR the task_scheduler_enabled DB flag.
* providers.py's configured_providers() -- the OpenRouter branch, gated by
  OPENROUTER_ENABLED (env) OR the openrouter_enabled DB flag.

Both must satisfy: env on + DB off -> on; env off + DB on -> on;
env off + DB off -> off; a DB flag *read failure* must fall back to
env-var-only behaviour (never silently enable, never crash the caller).

For the scheduler specifically, the loop is long-lived, so a one-shot
check at startup would mean an admin's panel toggle only takes effect
after a container restart. TestSchedulerPerTickReevaluation proves the
flag is actually re-read on every tick (not cached from loop entry) by
flipping the mocked DB flag value *while the loop is running* and
observing the effective state change mid-run.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import providers
import services.task_scheduler as sched_mod


# ═══════════════════════════════════════════════════════════════════════
# task_scheduler_enabled
# ═══════════════════════════════════════════════════════════════════════

class TestSchedulerEnvDbOr:
    @pytest.mark.asyncio
    async def test_env_on_db_off_is_on(self, monkeypatch):
        monkeypatch.setattr(sched_mod, 'TASK_SCHEDULER_ENABLED', True)
        with patch.object(sched_mod, '_db_scheduler_flag', new=AsyncMock(return_value=False)):
            assert await sched_mod._effective_scheduler_enabled() is True

    @pytest.mark.asyncio
    async def test_env_off_db_on_is_on(self, monkeypatch):
        monkeypatch.setattr(sched_mod, 'TASK_SCHEDULER_ENABLED', False)
        with patch.object(sched_mod, '_db_scheduler_flag', new=AsyncMock(return_value=True)):
            assert await sched_mod._effective_scheduler_enabled() is True

    @pytest.mark.asyncio
    async def test_env_off_db_off_is_off(self, monkeypatch):
        monkeypatch.setattr(sched_mod, 'TASK_SCHEDULER_ENABLED', False)
        with patch.object(sched_mod, '_db_scheduler_flag', new=AsyncMock(return_value=False)):
            assert await sched_mod._effective_scheduler_enabled() is False

    @pytest.mark.asyncio
    async def test_db_read_failure_falls_back_to_env_only_behaviour(self, monkeypatch):
        """_db_scheduler_flag() itself must swallow the error and report
        'off' rather than raise -- so a DB outage degrades exactly to
        env-var-only behaviour, never crashes the loop and never spends
        money it shouldn't."""
        monkeypatch.setattr(sched_mod, 'TASK_SCHEDULER_ENABLED', False)

        async def _boom(*a, **k):
            raise RuntimeError('db down')

        with patch('site_settings.get_site_flag', new=_boom):
            assert await sched_mod._db_scheduler_flag() is False
            assert await sched_mod._effective_scheduler_enabled() is False

        # And with env ON, the same DB failure must not stop the scheduler
        # (env-only fallback means env alone is still authoritative).
        monkeypatch.setattr(sched_mod, 'TASK_SCHEDULER_ENABLED', True)
        with patch('site_settings.get_site_flag', new=_boom):
            assert await sched_mod._effective_scheduler_enabled() is True


class TestSchedulerPerTickReevaluation:
    @pytest.mark.asyncio
    async def test_flag_flip_mid_run_takes_effect_within_one_tick(self, monkeypatch):
        """Proves re-evaluation happens on every tick, not once at loop
        entry: start the loop OFF, let a couple of ticks pass with no
        claims, flip the mocked DB flag ON, let a couple more ticks pass,
        and confirm scheduler_tick() only ever ran after the flip."""
        monkeypatch.setattr(sched_mod, 'TASK_SCHEDULER_ENABLED', False)
        monkeypatch.setattr(sched_mod, 'TASK_SCHEDULER_TICK_SECONDS', 0.02)

        db_flag_value = {'on': False}

        async def fake_db_flag():
            return db_flag_value['on']

        tick_calls: list[int] = []

        async def fake_tick():
            tick_calls.append(1)
            return 0

        with patch.object(sched_mod, '_db_scheduler_flag', new=fake_db_flag), \
             patch.object(sched_mod, 'scheduler_tick', new=fake_tick):
            task = asyncio.create_task(sched_mod.scheduler_loop())
            try:
                # A few ticks while OFF: no calls should land.
                await asyncio.sleep(0.02 * 5)
                calls_while_off = len(tick_calls)
                assert calls_while_off == 0

                # Flip DB flag ON *while the loop is already running* --
                # a one-shot startup check could never observe this.
                db_flag_value['on'] = True
                await asyncio.sleep(0.02 * 5)
                calls_while_on = len(tick_calls)
                assert calls_while_on > calls_while_off
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

    @pytest.mark.asyncio
    async def test_state_change_logged_once_not_per_tick(self, monkeypatch, caplog):
        """The transition log line must appear once per actual change, not
        once per tick -- otherwise a long-disabled scheduler spams the log
        forever."""
        import logging
        monkeypatch.setattr(sched_mod, 'TASK_SCHEDULER_ENABLED', False)
        monkeypatch.setattr(sched_mod, 'TASK_SCHEDULER_TICK_SECONDS', 0.02)

        with patch.object(sched_mod, '_db_scheduler_flag', new=AsyncMock(return_value=False)), \
             patch.object(sched_mod, 'scheduler_tick', new=AsyncMock(return_value=0)), \
             caplog.at_level(logging.INFO, logger='services.task_scheduler'):
            task = asyncio.create_task(sched_mod.scheduler_loop())
            try:
                await asyncio.sleep(0.02 * 6)
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

        state_change_lines = [r for r in caplog.records if 'effective enabled state changed' in r.message]
        # Exactly one: the initial None -> False transition at loop entry.
        assert len(state_change_lines) == 1


# ═══════════════════════════════════════════════════════════════════════
# openrouter_enabled
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _reset_openrouter_cache():
    """Isolate providers._openrouter_flag_cache across tests -- it is
    process-global module state."""
    original = dict(providers._openrouter_flag_cache)
    providers._openrouter_flag_cache.update({'value': False, 'checked_at': 0.0, 'refreshing': False})
    yield
    providers._openrouter_flag_cache.clear()
    providers._openrouter_flag_cache.update(original)


def _fresh_cache(value: bool) -> None:
    """Set the OpenRouter DB-flag cache to a non-stale value directly, so
    configured_providers() reads it deterministically without depending on
    the fire-and-forget background refresh's timing."""
    import time
    providers._openrouter_flag_cache.update({'value': value, 'checked_at': time.monotonic(), 'refreshing': False})


class TestOpenRouterEnvDbOr:
    def test_env_on_db_off_is_on(self, monkeypatch):
        monkeypatch.setenv('OPENROUTER_ENABLED', 'true')
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
        _fresh_cache(False)
        names = [p.name for p in providers.configured_providers()]
        assert 'openrouter' in names

    def test_env_off_db_on_is_on(self, monkeypatch):
        monkeypatch.delenv('OPENROUTER_ENABLED', raising=False)
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
        _fresh_cache(True)
        names = [p.name for p in providers.configured_providers()]
        assert 'openrouter' in names

    def test_env_off_db_off_is_off(self, monkeypatch):
        monkeypatch.delenv('OPENROUTER_ENABLED', raising=False)
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
        _fresh_cache(False)
        names = [p.name for p in providers.configured_providers()]
        assert 'openrouter' not in names

    def test_db_on_but_no_api_key_still_skipped(self, monkeypatch):
        """The DB flag is a second switch, never a replacement for the key
        requirement (see the long comment in providers.py above the
        OpenRouter branch)."""
        monkeypatch.delenv('OPENROUTER_ENABLED', raising=False)
        monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
        _fresh_cache(True)
        names = [p.name for p in providers.configured_providers()]
        assert 'openrouter' not in names

    @pytest.mark.asyncio
    async def test_db_read_failure_falls_back_to_env_only_behaviour(self, monkeypatch):
        """A refresh failure must leave the cache exactly where env-only
        behaviour would have it (False, since it starts False and nothing
        ever confirmed a DB read) -- never fall back to "enabled"."""
        providers._openrouter_flag_cache.update({'value': False, 'checked_at': 0.0, 'refreshing': False})

        async def _boom(*a, **k):
            raise RuntimeError('db down')

        with patch('site_settings.get_site_flag', new=_boom):
            await providers._refresh_openrouter_db_flag()

        assert providers._openrouter_flag_cache['value'] is False

        monkeypatch.delenv('OPENROUTER_ENABLED', raising=False)
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
        names = [p.name for p in providers.configured_providers()]
        assert 'openrouter' not in names

    def test_stale_cache_schedules_background_refresh_without_blocking(self, monkeypatch):
        """configured_providers() must return immediately even when the
        cache is stale and a running loop is present to refresh it on --
        proving the sync/async bridge doesn't block."""
        import asyncio as _asyncio
        monkeypatch.delenv('OPENROUTER_ENABLED', raising=False)
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
        providers._openrouter_flag_cache.update({'value': False, 'checked_at': 0.0, 'refreshing': False})

        async def _run():
            with patch('site_settings.get_site_flag', new=AsyncMock(return_value=True)):
                names = [p.name for p in providers.configured_providers()]
                # First call: cache was stale and starts at False -> not yet on.
                assert 'openrouter' not in names
                # Give the scheduled background refresh a chance to run.
                await _asyncio.sleep(0)
                await _asyncio.sleep(0)

        _asyncio.run(_run())
        assert providers._openrouter_flag_cache['value'] is True
