"""Tests for backend/task_execution.py -- the billed execution core for
scheduled tasks (backend/tasks.py's POST /tasks/{id}/run and
services/task_scheduler.py's background loop both call `_execute_task`).

Before this module existed, `run_task` posted straight to LiteLLM with no
reservation, no settle, and no usage record -- a straight revenue-loss
path. These tests pin the fix: reserve -> upstream -> settle -> release, in
that order, with every failure path releasing the reservation and billing
nothing.

No live Postgres/Redis/network: `BillingService` is swapped out entirely
(same pattern as tests/test_images.py's `_billing_mock()`), the chat.py
symbols this module late-binds into (`is_working_model`, `_resolve_provider`,
`_bill_stream_usage`) are patched directly on the `chat` module, and
`tasks._resolve_task_model` is patched directly on the `tasks` module --
task_execution.py never imports either at module scope (see its docstring
for why: chat.py is being restructured by another agent concurrently, and
this is exactly the late-binding pattern that keeps monkeypatching working
regardless). The DB session double mirrors
tests/test_tasks_default_model.py's `_FakeSession`: it answers based on
which ORM entity a statement targets.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import tasks as tasks_mod
import task_execution as task_execution_mod
from models import ScheduledTask, TaskExecution
from services.billing import InsufficientBalanceError


def _fake_task(**overrides):
    task = MagicMock(spec=ScheduledTask)
    task.id = 1
    task.user_id = 42
    task.model = 'sanjab/some-model'
    task.prompt = 'سلام، وضعیت بازار را خلاصه کن'
    task.cron_expression = '0 9 * * *'
    task.run_count = 0
    for k, v in overrides.items():
        setattr(task, k, v)
    return task


class _FakeSession:
    """Mirrors tests/test_tasks_default_model.py's _FakeSession: answers
    based on which ORM entity the statement targets. Only TaskExecution and
    ScheduledTask selects are ever issued directly against this session by
    task_execution.py -- BillingService is mocked out entirely below, so no
    Wallet/Ledger-shaped statement ever needs to be answered here."""

    def __init__(self, *, task=None):
        self.task = task
        self.execution = None

    async def execute(self, stmt, params=None, *a, **k):
        result = MagicMock()
        desc = getattr(stmt, 'column_descriptions', None)
        entity = desc[0]['entity'] if desc else None
        if entity is TaskExecution:
            result.scalar_one_or_none.return_value = self.execution
        elif entity is ScheduledTask:
            result.scalar_one_or_none.return_value = self.task
        return result

    def add(self, obj):
        if isinstance(obj, TaskExecution):
            self.execution = obj

    async def commit(self):
        return None

    async def refresh(self, obj):
        if getattr(obj, 'id', None) is None:
            obj.id = 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _billing_mock(reserve_result=None, reserve_side_effect=None):
    """Same shape as tests/test_images.py's `_billing_mock()`: a
    BillingService replacement whose reserve/release never touch a real DB
    and can be asserted against directly."""
    instance = MagicMock()
    if reserve_side_effect is not None:
        instance.reserve = AsyncMock(side_effect=reserve_side_effect)
    else:
        instance.reserve = AsyncMock(
            return_value=reserve_result or {'reservation_id': 'resv-1', 'hold_amount': 1000}
        )
    instance.settle = AsyncMock(return_value=None)
    instance.release = AsyncMock(return_value=None)
    return MagicMock(return_value=instance), instance


def _upstream_response(status_code=200, body=None, text=''):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=body if body is not None else {})
    resp.text = text
    return resp


def _fake_provider():
    p = MagicMock()
    p.v1 = 'http://fake-upstream/v1'
    p.headers = MagicMock(return_value={'Content-Type': 'application/json'})
    return p


_DEFAULT_BODY = {
    'choices': [{'message': {'content': 'پاسخ کامل و معتبر'}}],
    'usage': {'total_tokens': 42, 'prompt_tokens': 20, 'completion_tokens': 22},
}


class _Patches:
    """Bundles every patch a single `_execute_task` call needs, mirroring
    tests/test_images.py's `_BasePatches`. Each test layers `http_post`,
    `ft_gate`, `reserve_result`/`reserve_side_effect`, and
    `bill_result`/`bill_side_effect` on top for its own scenario."""

    def __init__(self, *, task, resolved_model='bynara/some-model', is_working=True,
                 http_post=None, ft_gate=None, q_gate=None, reserve_result=None, reserve_side_effect=None,
                 bill_result=None, bill_side_effect=None):
        self.session = _FakeSession(task=task)
        self.billing_cls, self.billing_instance = _billing_mock(reserve_result, reserve_side_effect)
        self.fake_http = MagicMock()
        self.fake_http.post = http_post or AsyncMock(return_value=_upstream_response(body=_DEFAULT_BODY))
        self.resolved_model = resolved_model
        self.is_working = is_working
        self.ft_gate = ft_gate
        # None = the aggregate package quota lets the task through (the default:
        # the free tier and balance users are exempt from it). A dict = blocked.
        self.q_gate = q_gate
        self.bill_result = bill_result if bill_result is not None else {
            'cost': 123, 'input_tokens': 20, 'output_tokens': 22, 'balance_after': 999,
        }
        self.bill_side_effect = bill_side_effect

    def __enter__(self):
        bill_mock = (
            AsyncMock(side_effect=self.bill_side_effect) if self.bill_side_effect
            else AsyncMock(return_value=self.bill_result)
        )
        self.bill_mock = bill_mock
        self._patches = [
            patch.object(task_execution_mod, 'async_session', MagicMock(return_value=self.session)),
            patch.object(task_execution_mod, '_http', self.fake_http),
            patch.object(task_execution_mod, 'BillingService', self.billing_cls),
            patch.object(task_execution_mod, 'check_and_consume', AsyncMock(return_value=self.ft_gate)),
            patch.object(task_execution_mod, '_user_quota_check', AsyncMock(return_value=self.q_gate)),
            # Neither an entitlement nor the free tier covers this request by
            # default -- the normal wallet reservation path, matching every
            # test below written before these two gates existed at this
            # call site.
            patch.object(task_execution_mod, 'covering_entitlement', AsyncMock(return_value=None)),
            patch.object(task_execution_mod, 'covers_request', AsyncMock(return_value=False)),
            patch.object(tasks_mod, '_resolve_task_model', AsyncMock(return_value=self.resolved_model)),
            patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=self.is_working)),
            patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_fake_provider())),
            patch.object(chat_mod, '_bill_stream_usage', bill_mock),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self._patches:
            p.stop()


# ── Success path ────────────────────────────────────────────────────────

class TestSuccessPath:
    @pytest.mark.asyncio
    async def test_success_bills_exactly_once_and_releases_reservation(self):
        task = _fake_task()
        with _Patches(task=task) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'completed'
        assert result['error'] is None
        assert result['result'] == 'پاسخ کامل و معتبر'
        assert result['cost_toman'] == 123

        p.billing_instance.reserve.assert_awaited_once()
        p.bill_mock.assert_awaited_once()
        p.billing_instance.release.assert_awaited_once()
        # The pre-flight hold is RELEASED, never settled via BillingService --
        # the real charge is applied directly to wallet.balance inside
        # chat._bill_stream_usage/_record_usage, the same pattern chat.py's
        # own non-streaming handler uses. See task_execution.py's docstring.
        p.billing_instance.settle.assert_not_called()

    @pytest.mark.asyncio
    async def test_model_is_resolved_before_the_free_tier_gate_and_reserve(self):
        """Order matters (FINANCIAL RULE): resolve first, then gate, then
        reserve -- an unresolved model id would miss the price lookup."""
        order: list[str] = []
        task = _fake_task()

        async def _resolve(model):
            order.append('resolve')
            return 'bynara/resolved-model'

        async def _gate(uid, models):
            order.append('free_tier')
            assert models == ['bynara/resolved-model']
            return None

        with _Patches(task=task) as p, \
             patch.object(tasks_mod, '_resolve_task_model', _resolve), \
             patch.object(task_execution_mod, 'check_and_consume', _gate):
            original_reserve = p.billing_instance.reserve

            async def _reserve(*a, **k):
                order.append('reserve')
                return await original_reserve(*a, **k)
            p.billing_instance.reserve = _reserve

            await task_execution_mod._execute_task(task, 42)

        assert order == ['resolve', 'free_tier', 'reserve']


# ── Failure paths bill nothing and always release ──────────────────────

class TestUpstreamFailureBillsNothing:
    @pytest.mark.asyncio
    async def test_upstream_non_200_bills_nothing_and_releases(self):
        task = _fake_task()
        with _Patches(
            task=task,
            http_post=AsyncMock(return_value=_upstream_response(status_code=502, text='bad gateway')),
        ) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'failed'
        p.billing_instance.reserve.assert_awaited_once()
        p.bill_mock.assert_not_called()
        p.billing_instance.release.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upstream_exception_bills_nothing_and_releases(self):
        task = _fake_task()

        async def _boom(*a, **k):
            raise TimeoutError('upstream took too long')

        with _Patches(task=task, http_post=_boom) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'failed'
        p.bill_mock.assert_not_called()
        p.billing_instance.release.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_response_content_bills_nothing_and_releases(self):
        task = _fake_task()
        body = {'choices': [{'message': {'content': ''}}], 'usage': {}}
        with _Patches(task=task, http_post=AsyncMock(return_value=_upstream_response(body=body))) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'failed'
        p.bill_mock.assert_not_called()
        p.billing_instance.release.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_choices_at_all_bills_nothing_and_releases(self):
        task = _fake_task()
        body = {'usage': {}}
        with _Patches(task=task, http_post=AsyncMock(return_value=_upstream_response(body=body))) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'failed'
        p.bill_mock.assert_not_called()
        p.billing_instance.release.assert_awaited_once()


# ── Insufficient balance never reaches the upstream call ────────────────

class TestInsufficientBalance:
    @pytest.mark.asyncio
    async def test_insufficient_balance_never_reaches_upstream_and_bills_nothing(self):
        task = _fake_task()

        async def _boom(*a, **k):
            raise InsufficientBalanceError('insufficient balance')

        with _Patches(task=task, reserve_side_effect=_boom) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'failed'
        assert result['error_code'] == 'insufficient_balance'
        assert 'موجودی' in result['error']
        p.fake_http.post.assert_not_called()
        p.bill_mock.assert_not_called()
        # reserve() itself raised -- there is no reservation to release.
        p.billing_instance.release.assert_not_called()


# ── Free-tier gate blocks before any reservation is opened ──────────────

class TestFreeTierGate:
    @pytest.mark.asyncio
    async def test_free_tier_throttle_blocks_before_reserve_and_upstream(self):
        task = _fake_task()
        with _Patches(task=task, ft_gate={'model': 'bynara/some-model', 'retry_after_seconds': 120}) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'failed'
        p.billing_instance.reserve.assert_not_called()
        p.fake_http.post.assert_not_called()
        p.bill_mock.assert_not_called()


# ── Aggregate package quota also gates a scheduled task ─────────────────

class TestPackageQuotaGate:
    @pytest.mark.asyncio
    async def test_package_quota_blocks_before_reserve_and_upstream(self):
        """A package holder over their window quota is stopped here too, so a
        scheduled task cannot escape the aggregate cap the chat path enforces.
        Blocks before any reservation or upstream call, like the free tier."""
        task = _fake_task()
        with _Patches(
            task=task,
            q_gate={'limit': 200, 'used': 200, 'source': 'package', 'retry_after_seconds': 60},
        ) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'failed'
        p.billing_instance.reserve.assert_not_called()
        p.fake_http.post.assert_not_called()
        p.bill_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_free_tier_pass_still_runs_the_quota_gate(self):
        """The two gates are independent: passing the free tier (q_gate=None
        default is the pass case) must still let a normal task complete."""
        task = _fake_task()
        with _Patches(task=task, ft_gate=None, q_gate=None) as p:
            result = await task_execution_mod._execute_task(task, 42)
        assert result['status'] == 'completed'
        p.billing_instance.reserve.assert_awaited_once()


# ── No model available fails before free-tier gate and reserve ─────────

class TestNoModelAvailable:
    @pytest.mark.asyncio
    async def test_no_model_available_fails_before_free_tier_and_reserve(self):
        task = _fake_task()
        gate = AsyncMock(return_value=None)
        with _Patches(task=task, resolved_model='') as p, \
             patch.object(task_execution_mod, 'check_and_consume', gate):
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'failed'
        gate.assert_not_called()
        p.billing_instance.reserve.assert_not_called()
        p.fake_http.post.assert_not_called()


# ── The same execution cannot be billed twice ───────────────────────────

class TestCannotBeBilledTwice:
    @pytest.mark.asyncio
    async def test_bill_stream_usage_invoked_exactly_once_per_execution(self):
        """A single _execute_task call must settle exactly once, even
        though the upstream call and the settle call are two independent
        awaits -- guards against a future refactor accidentally calling the
        billing step from two branches (e.g. once inline and once in a
        retry path)."""
        task = _fake_task()
        with _Patches(task=task) as p:
            await task_execution_mod._execute_task(task, 42)
        assert p.bill_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_settle_failure_still_only_calls_bill_once_and_still_releases(self):
        """If billing itself raises after a successful upstream response,
        the task is still marked completed (the response was already
        generated and delivered -- same reasoning as images.py's
        settle-failure comment) but the billing call is not retried, and
        the reservation is still released exactly once."""
        task = _fake_task()

        async def _boom(*a, **k):
            raise RuntimeError('ledger write failed')

        with _Patches(task=task, bill_side_effect=_boom) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert p.bill_mock.await_count == 1
        assert result['status'] == 'completed'
        p.billing_instance.release.assert_awaited_once()


# ── Insufficient balance surfaces as 429 through the router ─────────────

class TestRunTaskEndpointTranslatesInsufficientBalance:
    @pytest.mark.asyncio
    async def test_run_task_returns_429_with_persian_message_on_insufficient_balance(self):
        import database as _db
        import json as _json

        task = _fake_task()
        session = _FakeSession(task=task)

        async def _boom(*a, **k):
            raise InsufficientBalanceError('insufficient balance')

        with patch.object(_db, '_real_async_session', MagicMock(return_value=session)), \
             patch.object(tasks_mod, '_get_user_id', AsyncMock(return_value=42)), \
             patch.object(tasks_mod, '_resolve_task_model', AsyncMock(return_value='bynara/some-model')), \
             patch.object(task_execution_mod, 'async_session', MagicMock(return_value=session)), \
             patch.object(task_execution_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(task_execution_mod, 'covering_entitlement', AsyncMock(return_value=None)), \
             patch.object(task_execution_mod, 'covers_request', AsyncMock(return_value=False)), \
             patch.object(task_execution_mod, 'BillingService', _billing_mock(reserve_side_effect=_boom)[0]):
            resp = await tasks_mod.run_task(MagicMock(), 1)

        assert resp.status_code == 429
        body = _json.loads(resp.body)
        assert body['status'] == 'failed'
        assert 'موجودی' in body['error']
