"""Tests for the two gates added to backend/task_execution.py::_execute_task
so a scheduled task cannot escape Phase J content screening or the admin
`chat_enabled` kill switch -- the same gates `chat_web._chat_preflight`
already runs for the four interactive chat routes.

Before this fix, `grep -c moderation task_execution.py` and
`grep -c 'chat_disabled|chat_enabled' task_execution.py` were both 0: a
scheduled task's prompt reached the upstream model completely unscreened
(no `moderation_event` row, no alert), and scheduled tasks kept burning
upstream credit while an admin had chat turned off. This file pins the fix
in the same order `chat_web._chat_preflight` uses -- chat_enabled, then
moderation, then the pre-existing free-tier/quota gates -- and BEFORE
`BillingService.reserve()`, so a blocked task opens no wallet reservation
and consumes no free-tier/quota allowance.

Mocking style mirrors tests/test_task_billing.py (same repo, same module):
`BillingService` is swapped out entirely, the chat.py/tasks.py symbols this
module late-binds (`is_working_model`, `_resolve_provider`,
`_bill_stream_usage`, `_resolve_task_model`) are patched directly on the
`chat`/`tasks` modules, and the two new gates -- `get_site_flag` and
`screen_request` -- are patched directly on `task_execution` itself, since
this module imports both at module scope (same pattern chat_web.py uses for
the same two symbols). `Verdict` is the real dataclass from
services/moderation_rules.py, not a hand-rolled stand-in, so these tests
pin the actual contract `screen_request` returns rather than a guess at its
shape.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import tasks as tasks_mod
import task_execution as task_execution_mod
from models import ScheduledTask, TaskExecution
from services.moderation_rules import Verdict


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
    """Mirrors tests/test_task_billing.py's `_FakeSession` (itself mirroring
    tests/test_tasks_default_model.py's): answers based on which ORM entity
    the statement targets. BillingService is mocked out entirely below, so
    no Wallet/Ledger-shaped statement is ever issued against this session."""

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


def _billing_mock(reserve_result=None):
    instance = MagicMock()
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

_BLOCK_MESSAGE = (
    'این درخواست با قوانین محتوایی سنجاب همخوانی ندارد و ارسال نشد. '
    'لطفاً پیام را به‌گونه‌ای دیگر بازنویسی کنید.'
)


class _Patches:
    """Bundles every patch a single `_execute_task` call needs. Defaults are
    the happy path -- chat enabled, moderation allows, both quota gates
    pass, reserve/upstream/bill all succeed -- so each test only overrides
    what it is specifically exercising."""

    def __init__(self, *, task, chat_enabled=True, verdict=None, http_post=None,
                 ft_gate=None, q_gate=None, reserve_result=None, bill_result=None,
                 resolved_model='bynara/resolved-model'):
        self.session = _FakeSession(task=task)
        self.billing_cls, self.billing_instance = _billing_mock(reserve_result)
        self.fake_http = MagicMock()
        self.fake_http.post = http_post or AsyncMock(return_value=_upstream_response(body=_DEFAULT_BODY))
        self.verdict = verdict if verdict is not None else Verdict(decision='allow')
        self._chat_enabled = chat_enabled
        self.ft_gate = ft_gate
        self.q_gate = q_gate
        self.resolved_model = resolved_model
        self.bill_result = bill_result or {
            'cost': 123, 'input_tokens': 20, 'output_tokens': 22, 'balance_after': 999,
        }

    def __enter__(self):
        self.get_site_flag = AsyncMock(return_value=self._chat_enabled)
        self.screen_request = AsyncMock(return_value=self.verdict)
        self.check_and_consume = AsyncMock(return_value=self.ft_gate)
        self.user_quota_check = AsyncMock(return_value=self.q_gate)
        self.bill_mock = AsyncMock(return_value=self.bill_result)
        # Neither an entitlement nor the free tier covers this request by
        # default -- the normal wallet reservation path, matching every
        # test below written before these two gates existed at this call
        # site.
        self.covering_entitlement = AsyncMock(return_value=None)
        self.covers_request = AsyncMock(return_value=False)
        self._patches = [
            patch.object(task_execution_mod, 'async_session', MagicMock(return_value=self.session)),
            patch.object(task_execution_mod, '_http', self.fake_http),
            patch.object(task_execution_mod, 'BillingService', self.billing_cls),
            patch.object(task_execution_mod, 'get_site_flag', self.get_site_flag),
            patch.object(task_execution_mod, 'screen_request', self.screen_request),
            patch.object(task_execution_mod, 'check_and_consume', self.check_and_consume),
            patch.object(task_execution_mod, '_user_quota_check', self.user_quota_check),
            patch.object(task_execution_mod, 'covering_entitlement', self.covering_entitlement),
            patch.object(task_execution_mod, 'covers_request', self.covers_request),
            patch.object(tasks_mod, '_resolve_task_model', AsyncMock(return_value=self.resolved_model)),
            patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)),
            patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_fake_provider())),
            patch.object(chat_mod, '_bill_stream_usage', self.bill_mock),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self._patches:
            p.stop()


# ── Moderation blocks before reserve/upstream and burns no quota ───────────

class TestModerationGate:
    @pytest.mark.asyncio
    async def test_blocked_task_never_reaches_upstream_or_opens_a_reservation(self):
        task = _fake_task()
        verdict = Verdict(decision='block', category='sexual', severity='high',
                           rule_id=7, message_fa=_BLOCK_MESSAGE)

        with _Patches(task=task, verdict=verdict) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'failed'
        assert result['error'] == _BLOCK_MESSAGE
        assert result['error_code'] == 'content_blocked'
        p.billing_instance.reserve.assert_not_called()
        p.fake_http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocked_task_never_consumes_the_free_tier_gate(self):
        """The "blocked request burns no quota" claim, made concrete: the
        free-tier gate (services.free_tier.check_and_consume, patched here
        as task_execution.check_and_consume) must not even be called when
        moderation blocks first."""
        task = _fake_task()
        verdict = Verdict(decision='block', category='violence', severity='high',
                           rule_id=3, message_fa=_BLOCK_MESSAGE)

        with _Patches(task=task, verdict=verdict) as p:
            await task_execution_mod._execute_task(task, 42)

        p.check_and_consume.assert_not_called()
        p.user_quota_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_moderation_message_falls_back_to_block_message_fa_constant(self):
        """screen_request's contract (services/moderation_rules.py): a block
        Verdict does not always carry a populated `message_fa` (it is
        `None` unless the block came from the rule-hit path) -- mirrors
        `moderation_preflight`'s own `verdict.message_fa or BLOCK_MESSAGE_FA`
        fallback, so this pins that task_execution.py does the same rather
        than surfacing an empty error string."""
        from services.moderation import BLOCK_MESSAGE_FA
        task = _fake_task()
        verdict = Verdict(decision='block', category='other', severity='high', message_fa=None)

        with _Patches(task=task, verdict=verdict) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['error'] == BLOCK_MESSAGE_FA
        p.billing_instance.reserve.assert_not_called()

    @pytest.mark.asyncio
    async def test_screen_request_is_called_with_the_task_prompt_as_a_user_message(self):
        task = _fake_task(prompt='این یک پیام آزمایشی است')

        with _Patches(task=task) as p:
            await task_execution_mod._execute_task(task, 42)

        p.screen_request.assert_awaited_once()
        call_args = p.screen_request.await_args
        assert call_args.args[0] == 42
        assert call_args.args[1] == [{'role': 'user', 'content': 'این یک پیام آزمایشی است'}]


# ── chat_enabled kill switch blocks before reserve/upstream ────────────────

class TestChatEnabledGate:
    @pytest.mark.asyncio
    async def test_task_execution_while_chat_disabled_never_reaches_upstream(self):
        task = _fake_task()

        with _Patches(task=task, chat_enabled=False) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'failed'
        assert result['error'] == task_execution_mod._CHAT_DISABLED_MESSAGE
        assert result['error_code'] == 'chat_disabled'
        p.billing_instance.reserve.assert_not_called()
        p.fake_http.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_disabled_short_circuits_before_moderation_is_even_checked(self):
        """Same order chat_web._chat_preflight uses: the disabled-switch is
        gate ONE, moderation is gate TWO -- a disabled chat should not even
        pay for a moderation screen."""
        task = _fake_task()

        with _Patches(task=task, chat_enabled=False) as p:
            await task_execution_mod._execute_task(task, 42)

        p.screen_request.assert_not_called()
        p.check_and_consume.assert_not_called()


# ── A clean task passes through both new gates untouched ───────────────────

class TestCleanTaskUnaffected:
    @pytest.mark.asyncio
    async def test_clean_task_still_completes_byte_for_byte_unchanged(self):
        task = _fake_task()

        with _Patches(task=task) as p:
            result = await task_execution_mod._execute_task(task, 42)

        assert result['status'] == 'completed'
        assert result['error'] is None
        assert result['result'] == 'پاسخ کامل و معتبر'
        assert result['cost_toman'] == 123
        p.get_site_flag.assert_awaited_once_with('chat_enabled')
        p.screen_request.assert_awaited_once()
        p.billing_instance.reserve.assert_awaited_once()
        p.bill_mock.assert_awaited_once()
        p.billing_instance.release.assert_awaited_once()
        p.billing_instance.settle.assert_not_called()


# ── Ordering: chat_enabled -> moderation -> free-tier -> quota -> reserve ──

class TestGateOrdering:
    @pytest.mark.asyncio
    async def test_gate_order_matches_chat_preflight(self):
        order: list[str] = []
        task = _fake_task()

        async def _flag(key):
            order.append('chat_enabled')
            assert key == 'chat_enabled'
            return True

        async def _screen(uid, messages, conversation_id=None):
            order.append('moderation')
            return Verdict(decision='allow')

        async def _ft(uid, models):
            order.append('free_tier')
            return None

        async def _q(uid):
            order.append('quota')
            return None

        with _Patches(task=task) as p, \
             patch.object(task_execution_mod, 'get_site_flag', _flag), \
             patch.object(task_execution_mod, 'screen_request', _screen), \
             patch.object(task_execution_mod, 'check_and_consume', _ft), \
             patch.object(task_execution_mod, '_user_quota_check', _q):
            original_reserve = p.billing_instance.reserve

            async def _reserve(*a, **k):
                order.append('reserve')
                return await original_reserve(*a, **k)
            p.billing_instance.reserve = _reserve

            await task_execution_mod._execute_task(task, 42)

        assert order == ['chat_enabled', 'moderation', 'free_tier', 'quota', 'reserve']
