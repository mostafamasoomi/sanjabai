"""Regression tests for backend/tasks.py's scheduled-task model resolution.

Previously `ScheduledTaskCreate.model` hardcoded the literal catalog id
'mimo-v2.5', which the catalog marks `maintenance` -- so every task that
didn't pick its own model, plus `run_task()` posting `task.model` straight
to LiteLLM with no canonicalization at all, was broken. See tasks.py's
`_DEFAULT_MODEL_SENTINEL` / `_default_model()` / `_resolve_task_model()`
docstrings for the fix.

No test makes a real network call or touches a live database -- the DB
session and upstream HTTP client are always mocked, in the same spirit as
conftest.py's mock_async_session fixture.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import tasks as tasks_mod
import chat as chat_mod
import database as _db
import task_execution as task_execution_mod
from models import ScheduledTask, TaskExecution


def _fake_provider():
    """A chat._resolve_provider() stand-in -- task_execution.py's upstream
    call reads `.v1` and calls `.headers()` on whatever it resolves to."""
    provider = MagicMock()
    provider.v1 = 'http://fake-upstream/v1'
    provider.headers = MagicMock(return_value={})
    return provider


def _billing_double(reserve_result=None):
    """A BillingService stand-in for task_execution.reserve()/release() --
    same pattern as tests/test_images.py's `_billing_mock()`. These tests
    are about proving the resolved model reaches the upstream call, not
    about wallet/reservation mechanics (that is covered exhaustively by
    tests/test_task_billing.py), so billing itself is a double here."""
    instance = MagicMock()
    instance.reserve = AsyncMock(
        return_value=reserve_result or {'reservation_id': 'resv-1', 'hold_amount': 1000}
    )
    instance.release = AsyncMock(return_value=None)
    return MagicMock(return_value=instance), instance


@pytest.fixture(autouse=True)
def _reset_tasks_default_model_cache():
    """_default_model() caches its result in a module global; make every
    test start cold so one test's catalog stub can't leak into another."""
    tasks_mod._DEFAULT_MODEL_CACHE = None
    tasks_mod._DEFAULT_MODEL_CACHE_LOADED_AT = 0.0
    yield
    tasks_mod._DEFAULT_MODEL_CACHE = None
    tasks_mod._DEFAULT_MODEL_CACHE_LOADED_AT = 0.0


def _make_row(**kwargs):
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


class _FakeSession:
    """A minimal async session whose execute() answers based on which ORM
    entity the statement targets, so a single fake can stand in for the
    several different `select(...)` calls run_task() issues in sequence
    (ScheduledTask lookup, TaskExecution insert/refresh, then both again to
    record the result) without needing a real database.
    """

    def __init__(self, *, catalog_row=None, task=None, execution=None, raise_on_execute=None):
        self.catalog_row = catalog_row
        self.task = task
        self.execution = execution
        self.raise_on_execute = raise_on_execute
        self.added = []

    async def execute(self, stmt, *args, **kwargs):
        if self.raise_on_execute:
            raise self.raise_on_execute
        result = MagicMock()
        desc = getattr(stmt, 'column_descriptions', None)
        entity = desc[0]['entity'] if desc else None
        if entity is ScheduledTask:
            result.scalar_one_or_none.return_value = self.task
            result.scalar_one.return_value = self.task
        elif entity is TaskExecution:
            result.scalar_one_or_none.return_value = self.execution
            result.scalar_one.return_value = self.execution
        else:
            # Raw SQL text() query -- used by _default_model()'s catalog lookup.
            result.fetchone.return_value = self.catalog_row
        return result

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, TaskExecution) and self.execution is None:
            self.execution = obj

    async def commit(self):
        pass

    async def refresh(self, obj):
        if getattr(obj, 'id', None) is None:
            obj.id = 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _install_session(session: _FakeSession):
    return patch.object(_db, '_real_async_session', MagicMock(return_value=session))


def _fake_task(**overrides):
    task = MagicMock(spec=ScheduledTask)
    task.id = 1
    task.user_id = 1
    task.model = ''
    task.prompt = 'سلام'
    for k, v in overrides.items():
        setattr(task, k, v)
    return task


class TestDefaultModel:
    def test_create_payload_no_longer_hardcodes_maintenance_model(self):
        """The old default was the literal string 'mimo-v2.5', a catalog row
        that is `maintenance` -- see the docstring on _DEFAULT_MODEL_SENTINEL.
        The new default must be the empty sentinel, resolved dynamically at
        run time, never that (or any other) baked-in model id."""
        payload = tasks_mod.ScheduledTaskCreate(title='t', prompt='p')
        assert payload.model == ''
        assert payload.model != 'mimo-v2.5'

    @pytest.mark.asyncio
    async def test_default_model_picks_cheapest_available_public_model(self):
        row = _make_row(provider_model_id='bynara/mimo-v2.5-free')
        with _install_session(_FakeSession(catalog_row=row)):
            result = await tasks_mod._default_model()
        assert result == 'bynara/mimo-v2.5-free'

    @pytest.mark.asyncio
    async def test_default_model_empty_when_catalog_has_nothing_available(self):
        with _install_session(_FakeSession(catalog_row=None)):
            result = await tasks_mod._default_model()
        assert result == ''

    @pytest.mark.asyncio
    async def test_default_model_fails_open_to_empty_on_db_error(self):
        with _install_session(_FakeSession(raise_on_execute=RuntimeError('db down'))):
            result = await tasks_mod._default_model()
        assert result == ''

    @pytest.mark.asyncio
    async def test_default_model_is_cached_within_ttl(self):
        row = _make_row(provider_model_id='sanjab/cheap')
        session = _FakeSession(catalog_row=row)
        with _install_session(session):
            first = await tasks_mod._default_model()
            # Change what a fresh DB read would return -- the cached value
            # must win within the TTL window, so this is *not* a live re-query
            # on every call.
            session.catalog_row = _make_row(provider_model_id='sanjab/other')
            second = await tasks_mod._default_model()
        assert first == second == 'sanjab/cheap'


class TestResolveTaskModel:
    @pytest.mark.asyncio
    async def test_empty_model_falls_back_to_default_then_resolves(self):
        with patch.object(tasks_mod, '_default_model', AsyncMock(return_value='bynara/mimo-v2.5-free')) as default_mock, \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='bynara/mimo-v2.5-free')) as resolve_mock:
            result = await tasks_mod._resolve_task_model('')
        default_mock.assert_awaited_once()
        resolve_mock.assert_awaited_once_with('bynara/mimo-v2.5-free')
        assert result == 'bynara/mimo-v2.5-free'

    @pytest.mark.asyncio
    async def test_explicit_model_skips_default_but_still_gets_canonicalized(self):
        """A user-picked public/legacy id must go through the same
        _resolve_public_model canonicalization chat.py's other entry points
        use -- this is what the old code skipped entirely by posting
        `task.model` straight to LiteLLM."""
        with patch.object(tasks_mod, '_default_model', AsyncMock(return_value='should-not-be-used')) as default_mock, \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='bynara/mimo-v2.5-free')) as resolve_mock:
            result = await tasks_mod._resolve_task_model('sanjab/mimo-v2.5')
        default_mock.assert_not_called()
        resolve_mock.assert_awaited_once_with('sanjab/mimo-v2.5')
        assert result == 'bynara/mimo-v2.5-free'

    @pytest.mark.asyncio
    async def test_returns_empty_when_nothing_is_available_anywhere(self):
        with patch.object(tasks_mod, '_default_model', AsyncMock(return_value='')):
            result = await tasks_mod._resolve_task_model('')
        assert result == ''


class TestRunTaskEndToEnd:
    """Exercises the real run_task() handler (not just the helper) with a
    mocked DB session and a mocked upstream HTTP call, so the resolved
    model is proven to be what actually lands in the request sent to
    LiteLLM -- not just what a helper function returns in isolation.

    run_task() now wraps the upstream call in task_execution._execute_task's
    billing bracket (reserve -> upstream -> settle -> release -- see
    task_execution.py's module docstring); BillingService and
    chat._bill_stream_usage are doubled out here (see `_billing_double` /
    `_fake_provider` above) so these tests stay focused on their original
    purpose -- proving the RESOLVED model, never an empty string and never
    the old hardcoded 'mimo-v2.5' literal, is what reaches the upstream call
    -- rather than duplicating the wallet/reservation mechanics that
    tests/test_task_billing.py already covers exhaustively.
    """

    @pytest.mark.asyncio
    async def test_run_task_sends_resolved_default_model_upstream_not_empty_string(self):
        task = _fake_task(model='')
        session = _FakeSession(task=task)
        captured = {}

        async def fake_post(url, json=None, headers=None):
            captured['url'] = url
            captured['json'] = json
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                'choices': [{'message': {'content': 'پاسخ'}}],
                'usage': {'total_tokens': 12},
            }
            return resp

        fake_http = MagicMock()
        fake_http.post = fake_post
        billing_cls, _billing_instance = _billing_double()

        with _install_session(session), \
             patch.object(_db, '_real_http', fake_http), \
             patch.object(tasks_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(tasks_mod, '_default_model', AsyncMock(return_value='bynara/mimo-v2.5-free')), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(side_effect=lambda m: m)), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)), \
             patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_fake_provider())), \
             patch.object(chat_mod, '_bill_stream_usage', AsyncMock(return_value={'cost': 10})), \
             patch.object(task_execution_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(task_execution_mod, 'BillingService', billing_cls):
            resp = await tasks_mod.run_task(MagicMock(), 1)

        body = json.loads(resp.body)
        assert body['status'] == 'completed', body
        assert captured['json']['model'] == 'bynara/mimo-v2.5-free'
        assert captured['json']['model'] != ''
        assert captured['json']['model'] != 'mimo-v2.5'

    @pytest.mark.asyncio
    async def test_run_task_resolves_explicit_legacy_model_before_dispatch(self):
        """A task saved with the old hardcoded default (or any other
        explicit model string) must still be canonicalized before hitting
        LiteLLM -- proving run_task doesn't bypass _resolve_public_model the
        way the pre-fix code did."""
        task = _fake_task(model='sanjab/mimo-v2.5')
        session = _FakeSession(task=task)
        captured = {}

        async def fake_post(url, json=None, headers=None):
            captured['json'] = json
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {'choices': [{'message': {'content': 'ok'}}], 'usage': {}}
            return resp

        fake_http = MagicMock()
        fake_http.post = fake_post
        billing_cls, _billing_instance = _billing_double()

        with _install_session(session), \
             patch.object(_db, '_real_http', fake_http), \
             patch.object(tasks_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='bynara/mimo-v2.5-free')) as resolve_mock, \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)), \
             patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_fake_provider())), \
             patch.object(chat_mod, '_bill_stream_usage', AsyncMock(return_value={'cost': 10})), \
             patch.object(task_execution_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(task_execution_mod, 'BillingService', billing_cls):
            resp = await tasks_mod.run_task(MagicMock(), 1)

        body = json.loads(resp.body)
        assert body['status'] == 'completed', body
        resolve_mock.assert_awaited_once_with('sanjab/mimo-v2.5')
        assert captured['json']['model'] == 'bynara/mimo-v2.5-free'

    @pytest.mark.asyncio
    async def test_run_task_fails_gracefully_without_calling_upstream_when_no_model_available(self):
        task = _fake_task(model='')
        session = _FakeSession(task=task)
        fake_http = MagicMock()
        fake_http.post = AsyncMock()

        with _install_session(session), \
             patch.object(_db, '_real_http', fake_http), \
             patch.object(tasks_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(tasks_mod, '_default_model', AsyncMock(return_value='')):
            resp = await tasks_mod.run_task(MagicMock(), 1)

        body = json.loads(resp.body)
        assert body['status'] == 'failed'
        fake_http.post.assert_not_called()
