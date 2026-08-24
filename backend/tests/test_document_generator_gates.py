"""Tests for the billing/gating pipeline added to
backend/document_generator.py::generate_document.

Before this fix, POST /v1/documents/generate posted straight to the
upstream model with no reservation, no settle, no free-tier gate, no
package quota gate, no content moderation, and no catalog validation of
the client-supplied `model` -- a straight revenue-loss + "no free models"
policy violation (see document_generator.py's module docstring for the
full writeup). This file pins the fix in the exact order that docstring
describes: model validation -> chat_enabled -> moderation -> free-tier ->
quota -> BillingService.reserve() -> upstream call -> bill -> release --
and that document_ai.generate_content's internal resilience retry cannot
turn into a double charge.

Mocking style mirrors tests/test_task_execution_gates.py (same repo, same
class of fix): `BillingService` is swapped out entirely, the `chat`-module
symbols document_generator.py late-binds (`_resolve_public_model`,
`_safe_default_model`, `_is_model_allowed`, `is_working_model`,
`_bill_stream_usage`) are patched directly on the `chat` module, and the
gates document_generator.py imports at its own module scope
(`get_site_flag`, `screen_request`, `check_and_consume`,
`_user_quota_check`, `generate_content`, `async_session`) are patched
directly on `document_generator` itself. `Verdict` is the real dataclass
from services/moderation_rules.py, not a hand-rolled stand-in, so these
tests pin the actual contract `screen_request` returns.

House rule: a mock that returns a canned value regardless of WHERE it is
called from proves nothing -- every test below asserts on CALL COUNTS
(`assert_not_called` / `assert_awaited_once`) of the gates and of
`generate_content`/`_bill_stream_usage`/`reserve`/`release`, not just on
the final HTTP status code, so a gate that is wired in the wrong order (or
not wired at all) fails these tests even if it happens to also return the
right status code for one specific case.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import chat as chat_mod
import document_ai as document_ai_mod
import document_generator as document_generator_mod
from services.moderation import BLOCK_MESSAGE_FA
from services.moderation_rules import Verdict


def _fake_request(body: dict):
    req = MagicMock()

    async def _json():
        return body

    req.json = _json
    return req


class _FakeAsyncSession:
    def __init__(self):
        self.commit = AsyncMock(return_value=None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _billing_mock(reserve_result=None):
    instance = MagicMock()
    instance.reserve = AsyncMock(
        return_value=reserve_result or {'reservation_id': 'resv-1', 'hold_amount': 4000}
    )
    instance.settle = AsyncMock(return_value=None)
    instance.release = AsyncMock(return_value=None)
    return MagicMock(return_value=instance), instance


_DEFAULT_DATA = {
    'title': 'عنوان تستی',
    'slides': [{'title': 'اسلاید ۱', 'content': ['نکته اول']}],
}
_DEFAULT_USAGE = {'prompt_tokens': 40, 'completion_tokens': 200, 'total_tokens': 240}


class _Patches:
    """Bundles every patch a single `generate_document` call needs. Defaults
    are the happy path -- model allowed, chat enabled, moderation allows,
    both quota gates pass, reserve/upstream/bill all succeed -- so each
    test only overrides what it is specifically exercising."""

    def __init__(self, *, uid=42, model_allowed=True, resolved_model='sanjab/resolved-model',
                 chat_enabled=True, verdict=None, ft_gate=None, q_gate=None,
                 reserve_result=None, generate_content_result=None,
                 generate_content_side_effect=None, bill_result=None,
                 default_model_available=True):
        self.uid = uid
        self.session = _FakeAsyncSession()
        self.billing_cls, self.billing_instance = _billing_mock(reserve_result)
        self.verdict = verdict if verdict is not None else Verdict(decision='allow')
        self.model_allowed = model_allowed
        self.resolved_model = resolved_model
        self.default_model_available = default_model_available
        self.chat_enabled = chat_enabled
        self.ft_gate = ft_gate
        self.q_gate = q_gate
        self.bill_result = bill_result or {
            'cost': 321, 'input_tokens': 40, 'output_tokens': 200, 'balance_after': 999,
        }
        self.generate_content_result = generate_content_result or (
            dict(_DEFAULT_DATA), dict(_DEFAULT_USAGE), resolved_model,
        )
        self.generate_content_side_effect = generate_content_side_effect

    def __enter__(self):
        self.get_user_id = AsyncMock(return_value=self.uid)
        self.get_site_flag = AsyncMock(return_value=self.chat_enabled)
        self.screen_request = AsyncMock(return_value=self.verdict)
        self.check_and_consume = AsyncMock(return_value=self.ft_gate)
        self.user_quota_check = AsyncMock(return_value=self.q_gate)

        self.resolve_public_model = AsyncMock(side_effect=lambda m: m)
        self.safe_default_model = AsyncMock(
            return_value=self.resolved_model if self.default_model_available else ''
        )
        self.is_model_allowed = AsyncMock(return_value=self.model_allowed)
        self.is_working_model = AsyncMock(return_value=True)
        self.bill_stream_usage = AsyncMock(return_value=self.bill_result)

        if self.generate_content_side_effect is not None:
            self.generate_content = AsyncMock(side_effect=self.generate_content_side_effect)
        else:
            self.generate_content = AsyncMock(return_value=self.generate_content_result)

        self._patches = [
            patch.object(document_generator_mod, '_get_user_id', self.get_user_id),
            patch.object(document_generator_mod, 'get_site_flag', self.get_site_flag),
            patch.object(document_generator_mod, 'screen_request', self.screen_request),
            patch.object(document_generator_mod, 'check_and_consume', self.check_and_consume),
            patch.object(document_generator_mod, '_user_quota_check', self.user_quota_check),
            patch.object(document_generator_mod, 'BillingService', self.billing_cls),
            patch.object(document_generator_mod, 'async_session', MagicMock(return_value=self.session)),
            patch.object(document_generator_mod, 'generate_content', self.generate_content),
            patch.object(chat_mod, '_resolve_public_model', self.resolve_public_model),
            patch.object(chat_mod, '_safe_default_model', self.safe_default_model),
            patch.object(chat_mod, '_is_model_allowed', self.is_model_allowed),
            patch.object(chat_mod, 'is_working_model', self.is_working_model),
            patch.object(chat_mod, '_bill_stream_usage', self.bill_stream_usage),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self._patches:
            p.stop()


def _body(**overrides):
    b = {'prompt': 'یک ارائه دربارهٔ انرژی خورشیدی بساز', 'type': 'pptx', 'model': 'evil-model'}
    b.update(overrides)
    return b


# ── Gate 1: model validation ────────────────────────────────────────────

class TestModelValidationGate:
    @pytest.mark.asyncio
    async def test_unknown_model_never_reaches_upstream_or_opens_a_reservation(self):
        with _Patches(model_allowed=False) as p:
            resp = await document_generator_mod.generate_document(_fake_request(_body()))

        assert resp.status_code == 400
        p.generate_content.assert_not_called()
        p.billing_instance.reserve.assert_not_called()
        p.screen_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_default_model_available_is_refused_not_forwarded(self):
        with _Patches(model_allowed=False, default_model_available=False) as p:
            resp = await document_generator_mod.generate_document(
                _fake_request(_body(model=''))
            )

        assert resp.status_code == 400
        p.generate_content.assert_not_called()
        p.billing_instance.reserve.assert_not_called()


# ── Gate 3: moderation ──────────────────────────────────────────────────

_BLOCK_MESSAGE = (
    'این درخواست با قوانین محتوایی سنجاب همخوانی ندارد و ارسال نشد. '
    'لطفاً پیام را به‌گونه‌ای دیگر بازنویسی کنید.'
)


class TestModerationGate:
    @pytest.mark.asyncio
    async def test_blocked_prompt_never_reaches_upstream_never_reserves_never_burns_free_tier(self):
        verdict = Verdict(decision='block', category='sexual', severity='high',
                           rule_id=7, message_fa=_BLOCK_MESSAGE)

        with _Patches(verdict=verdict) as p:
            resp = await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model'))
            )

        assert resp.status_code == 403
        body = json.loads(resp.body)
        assert body['error']['message'] == _BLOCK_MESSAGE
        assert body['error']['code'] == 'content_blocked'
        p.generate_content.assert_not_called()
        p.billing_instance.reserve.assert_not_called()
        p.check_and_consume.assert_not_called()
        p.user_quota_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_block_message_falls_back_to_the_module_constant(self):
        verdict = Verdict(decision='block', category='other', severity='high', message_fa=None)

        with _Patches(verdict=verdict) as p:
            resp = await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model'))
            )

        body = json.loads(resp.body)
        assert body['error']['message'] == BLOCK_MESSAGE_FA
        p.billing_instance.reserve.assert_not_called()

    @pytest.mark.asyncio
    async def test_moderation_screens_the_prompt_as_a_user_message(self):
        with _Patches() as p:
            await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model', prompt='یک تست ساده'))
            )

        p.screen_request.assert_awaited_once()
        call_args = p.screen_request.await_args
        assert call_args.args[0] == 42
        assert call_args.args[1] == [{'role': 'user', 'content': 'یک تست ساده'}]


# ── Gate 4/5: free-tier + package quota ─────────────────────────────────

class TestFreeTierAndQuotaGates:
    @pytest.mark.asyncio
    async def test_free_tier_exhausted_user_is_refused_before_the_upstream_call(self):
        ft_gate = {'code': 'free_lifetime_exhausted', 'message': 'سقف رایگان پر شده', 'retry_after_seconds': 0}

        with _Patches(ft_gate=ft_gate) as p:
            resp = await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model'))
            )

        assert resp.status_code == 429
        body = json.loads(resp.body)
        assert body['error']['message'] == 'سقف رایگان پر شده'
        p.generate_content.assert_not_called()
        p.billing_instance.reserve.assert_not_called()

    @pytest.mark.asyncio
    async def test_package_quota_exhausted_user_is_refused_before_the_upstream_call(self):
        q_gate = {'limit': 50, 'used': 50, 'source': 'package', 'retry_after_seconds': 120}

        with _Patches(q_gate=q_gate) as p:
            resp = await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model'))
            )

        assert resp.status_code == 429
        p.generate_content.assert_not_called()
        p.billing_instance.reserve.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_disabled_kill_switch_blocks_before_moderation_and_upstream(self):
        with _Patches(chat_enabled=False) as p:
            resp = await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model'))
            )

        assert resp.status_code == 503
        p.screen_request.assert_not_called()
        p.check_and_consume.assert_not_called()
        p.generate_content.assert_not_called()
        p.billing_instance.reserve.assert_not_called()


# ── Gate order, end to end ───────────────────────────────────────────────

class TestGateOrdering:
    @pytest.mark.asyncio
    async def test_gate_order_matches_the_module_docstring(self):
        order: list[str] = []

        async def _is_allowed(m):
            order.append('model_validation')
            return True

        async def _flag(key):
            order.append('chat_enabled')
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

        with _Patches() as p, \
             patch.object(chat_mod, '_is_model_allowed', _is_allowed), \
             patch.object(document_generator_mod, 'get_site_flag', _flag), \
             patch.object(document_generator_mod, 'screen_request', _screen), \
             patch.object(document_generator_mod, 'check_and_consume', _ft), \
             patch.object(document_generator_mod, '_user_quota_check', _q):
            original_reserve = p.billing_instance.reserve

            async def _reserve(*a, **k):
                order.append('reserve')
                return await original_reserve(*a, **k)
            p.billing_instance.reserve = _reserve

            await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model'))
            )

        # `_is_model_allowed` ("model_validation") is also checked a second
        # time AFTER `reserve` in the happy path -- resolving document_ai's
        # fallback candidate, done late deliberately so a request an
        # earlier gate rejects never pays for that extra lookup (see
        # generate_document's Gate 7 comment). So assert relative order via
        # FIRST occurrence rather than an exact, repeat-sensitive sequence.
        assert order[0] == 'model_validation'
        first_seen = {name: order.index(name) for name in
                      ('model_validation', 'chat_enabled', 'moderation', 'free_tier', 'quota', 'reserve')}
        assert (first_seen['model_validation'] < first_seen['chat_enabled']
                < first_seen['moderation'] < first_seen['free_tier']
                < first_seen['quota'] < first_seen['reserve'])


# ── Happy path: reserve -> call -> bill -> release (never settle) ───────

class TestHappyPathBilling:
    @pytest.mark.asyncio
    async def test_happy_path_reserves_calls_bills_and_releases(self):
        with _Patches(resolved_model='sanjab/resolved-model',
                       generate_content_result=(dict(_DEFAULT_DATA), dict(_DEFAULT_USAGE),
                                                 'sanjab/resolved-model')) as p:
            resp = await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model'))
            )

        assert resp.status_code == 200, resp.body
        p.billing_instance.reserve.assert_awaited_once()
        p.generate_content.assert_awaited_once()
        p.bill_stream_usage.assert_awaited_once()
        p.billing_instance.release.assert_awaited_once()
        # The reservation is RELEASED, never SETTLED -- the real charge is
        # applied directly to wallet.balance by _bill_stream_usage, exactly
        # like task_execution.py's step 6.
        p.billing_instance.settle.assert_not_called()

        # Billing used the ACTUAL model that served the request, not just
        # whatever the client asked for.
        bill_call = p.bill_stream_usage.await_args
        assert bill_call.args[1]['model'] == 'sanjab/resolved-model'
        assert bill_call.args[2] == _DEFAULT_USAGE

    @pytest.mark.asyncio
    async def test_a_failure_after_reserve_releases_the_reservation_and_bills_nothing(self):
        with _Patches(generate_content_side_effect=RuntimeError('upstream exploded')) as p:
            resp = await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model'))
            )

        assert resp.status_code == 500
        p.billing_instance.reserve.assert_awaited_once()
        p.billing_instance.release.assert_awaited_once()
        p.bill_stream_usage.assert_not_called()
        p.billing_instance.settle.assert_not_called()


# ── The retry loop inside document_ai.generate_content cannot double-bill ─

class TestRetryCannotDoubleCharge:
    @pytest.mark.asyncio
    async def test_a_flaky_first_attempt_that_succeeds_on_retry_bills_exactly_once(self):
        """Exercises the REAL document_ai.generate_content (not a mock of
        it) so the internal `for attempt in range(2)` retry actually runs
        twice against a patched HTTP client -- proving the one-call-site
        billing structure holds even when the upstream itself is flaky,
        not merely when generate_content is mocked to return once."""
        ok_body = {
            'choices': [{'message': {'content': json.dumps(_DEFAULT_DATA, ensure_ascii=False)}}],
            'usage': dict(_DEFAULT_USAGE),
        }
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json = MagicMock(return_value=ok_body)
        ok_resp.raise_for_status = MagicMock(return_value=None)

        fake_http = MagicMock()
        fake_http.post = AsyncMock(
            side_effect=[httpx.TimeoutException('upstream timed out'), ok_resp]
        )

        with _Patches(resolved_model='sanjab/resolved-model') as p, \
             patch.object(document_generator_mod, 'generate_content', document_ai_mod.generate_content), \
             patch.object(document_ai_mod, '_http', fake_http):
            resp = await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model'))
            )

        assert resp.status_code == 200, resp.body
        assert fake_http.post.await_count == 2  # the retry really happened
        p.billing_instance.reserve.assert_awaited_once()
        p.bill_stream_usage.assert_awaited_once()  # exactly once despite 2 upstream attempts
        p.billing_instance.release.assert_awaited_once()
        p.billing_instance.settle.assert_not_called()
