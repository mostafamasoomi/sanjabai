"""Regression test for GET /tasks/{id}/executions (backend/tasks.py's
list_task_executions): the response dict omitted `cost_toman` even though
TaskExecution.cost_toman is a real, populated column (backed by the live
task_executions.cost_toman integer column -- confirmed via `\\d
task_executions` against the running Postgres, not guessed) and the
frontend (frontend/app/tasks/page.tsx) types and renders `Execution.cost_toman`.
Without it every execution's cost silently showed as undefined in the UI.

Follows tests/test_tasks_default_model.py's _FakeSession pattern: execute()
answers based on which ORM entity the statement targets, no live DB/Redis.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import tasks as tasks_mod
import database as _db
from models import ScheduledTask, TaskExecution


def _fake_task(**overrides):
    task = MagicMock(spec=ScheduledTask)
    task.id = 1
    task.user_id = 1
    for k, v in overrides.items():
        setattr(task, k, v)
    return task


def _fake_execution(**overrides):
    ex = MagicMock(spec=TaskExecution)
    ex.id = 1
    ex.task_id = 1
    ex.status = 'completed'
    ex.result = 'ok'
    ex.tokens_used = 100
    ex.cost_toman = 456  # integer toman, never scaled
    ex.error = None
    ex.started_at = datetime(2026, 1, 1)
    ex.completed_at = datetime(2026, 1, 1)
    ex.created_at = datetime(2026, 1, 1)
    for k, v in overrides.items():
        setattr(ex, k, v)
    return ex


class _FakeSession:
    def __init__(self, *, task=None, executions=None):
        self.task = task
        self.executions = executions or []

    async def execute(self, stmt, *args, **kwargs):
        result = MagicMock()
        desc = getattr(stmt, 'column_descriptions', None)
        entity = desc[0]['entity'] if desc else None
        if entity is ScheduledTask:
            result.scalar_one_or_none.return_value = self.task
        elif entity is TaskExecution:
            result.scalars.return_value.all.return_value = self.executions
        return result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _install_session(session: _FakeSession):
    return patch.object(_db, '_real_async_session', MagicMock(return_value=session))


class TestListTaskExecutionsCost:
    @pytest.mark.asyncio
    async def test_cost_toman_is_included_and_unscaled(self):
        task = _fake_task()
        execution = _fake_execution(cost_toman=9_995_511)
        session = _FakeSession(task=task, executions=[execution])

        with _install_session(session), \
             patch.object(tasks_mod, '_get_user_id', AsyncMock(return_value=1)):
            resp = await tasks_mod.list_task_executions(MagicMock(), 1)

        assert resp.status_code == 200
        import json
        body = json.loads(resp.body)
        assert len(body) == 1
        assert 'cost_toman' in body[0], f'cost_toman missing from response: {body[0]!r}'
        # Must be the raw integer-toman value, not divided/multiplied by 10
        # (the Rial/Toman scaling trap documented project-wide).
        assert body[0]['cost_toman'] == 9_995_511

    @pytest.mark.asyncio
    async def test_zero_cost_execution_still_reports_the_field(self):
        task = _fake_task()
        execution = _fake_execution(cost_toman=0)
        session = _FakeSession(task=task, executions=[execution])

        with _install_session(session), \
             patch.object(tasks_mod, '_get_user_id', AsyncMock(return_value=1)):
            resp = await tasks_mod.list_task_executions(MagicMock(), 1)

        import json
        body = json.loads(resp.body)
        assert body[0]['cost_toman'] == 0

    @pytest.mark.asyncio
    async def test_multiple_executions_each_carry_their_own_cost(self):
        task = _fake_task()
        execs = [_fake_execution(id=1, cost_toman=100), _fake_execution(id=2, cost_toman=250)]
        session = _FakeSession(task=task, executions=execs)

        with _install_session(session), \
             patch.object(tasks_mod, '_get_user_id', AsyncMock(return_value=1)):
            resp = await tasks_mod.list_task_executions(MagicMock(), 1)

        import json
        body = json.loads(resp.body)
        assert [e['cost_toman'] for e in body] == [100, 250]
