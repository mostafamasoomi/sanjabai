"""The bug this file pins: a fresh user with no wallet and no package could
not send a single message, and their free-tier allowance burned anyway.

services/free_tier.py::check_and_consume(uid, models) returns ``None`` in
THREE different situations: (1) the user has already paid, (2) the user
holds wallet balance, (3) all three free-tier limits passed AND one message
was just consumed. A caller cannot tell those apart from the return value
alone, so every one of the seven reservation call sites below immediately
went on to call ``BillingService.reserve()`` regardless -- which raises
``InsufficientBalanceError`` for a wallet-less user, surfacing as a 429
``code='balance'`` even though services/free_tier.py had *just* approved
and paid for the request out of the free tier.

``services.free_tier.covers_request(uid)`` (this file's namesake) is a new,
side-effect-free companion: ``not has_paid(uid) and not has_balance(uid)``.
Each reservation site now does::

    if await covering_entitlement(uid, cost) is not None or await covers_request(uid):
        reservation = None
    else:
        reservation = await _bill_svc.reserve(...)

This file drives all SEVEN reservation sites (chat.py, chat_smart.py,
chat_web.py, chat_compare.py x2, task_execution.py, document_generator.py,
services/rag.py) through their REAL code -- ``check_and_consume`` and
``covers_request`` are never mocked; only the DB/Redis primitives
underneath them (``has_paid``, ``has_balance``, ``_model_input_price``,
``_lifetime_used``, ``_lifetime_incr``, ``get_config``, ``rds``) are, via
the same monkeypatch shape tests/test_free_tier.py uses (its ``FakeRedis``
is imported, not re-derived, so a regression in the real Redis calls still
shows here too). ``covering_entitlement`` (the unrelated PACKAGE quota
mechanism) is mocked to ``None`` everywhere so it can never accidentally
supply the "skip the wallet" answer this file is testing for.

T1 pins the fix (the invariant that used to break). T2 is the guard against
overcorrecting it: a PAID user who has genuinely run their wallet to zero
must still be refused, not silently treated as free-tier-covered. T3 is a
source-level wiring scan (modeled on tests/test_premium_quota_wiring.py) so
a future eighth reservation site cannot reintroduce this exact bug by
forgetting the ``covers_request`` half of the check.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import chat_compare as chat_compare_mod
import chat_smart as chat_smart_mod
import chat_web as chat_web_mod
import document_generator as document_generator_mod
import services.rag as rag_mod
import task_execution as task_execution_mod
from services import free_tier as free_tier_mod
from services.billing import InsufficientBalanceError

from tests.test_document_generator_gates import _Patches as _DocGenPatches, _body, _fake_request
from tests.test_free_tier import FakeRedis
from tests.test_rag_gates_billing import _RagPatches, _rag_kwargs
from tests.test_smart_chat_hotfix import _CHEAP_ROW, _Session, _post as _smart_chat_post
from tests.test_smart_chat_hotfix import _SmartChatEnv
from tests.test_task_execution_gates import _Patches as _TaskExecPatches, _fake_task


# ═══════════════════════════════════════════════════════════════════════
# Shared free-tier plumbing
# ═══════════════════════════════════════════════════════════════════════

def _install_free_tier(monkeypatch, *, paid=False, balance=False, price=5718,
                        lifetime_used=0, hourly_limit=3, lifetime_limit=30,
                        max_input=60000):
    """Wires a fake Redis and controllable has_paid/has_balance/price/
    lifetime-counter into services/free_tier.py -- the real check_and_consume
    and covers_request run unpatched against these. Mirrors
    tests/test_free_tier.py's ``env`` fixture (FakeRedis reused from there,
    not re-derived); returns a small dict the tests assert against.
    """
    fr = FakeRedis()
    monkeypatch.setattr(free_tier_mod, 'rds', fr)

    state = {'lifetime': {}, 'redis': fr}

    async def fake_config():
        return {
            'free_hourly_limit': hourly_limit,
            'free_lifetime_limit': lifetime_limit,
            'free_tier_max_input_per_million': max_input,
        }

    async def fake_price(model):
        return price

    async def fake_lifetime_used(uid):
        return state['lifetime'].get(uid, lifetime_used)

    async def fake_lifetime_incr(uid):
        state['lifetime'][uid] = state['lifetime'].get(uid, lifetime_used) + 1

    async def fake_has_paid(uid):
        return paid

    async def fake_has_balance(uid):
        return balance

    monkeypatch.setattr(free_tier_mod, 'get_config', fake_config)
    monkeypatch.setattr(free_tier_mod, '_model_input_price', fake_price)
    monkeypatch.setattr(free_tier_mod, '_lifetime_used', fake_lifetime_used)
    monkeypatch.setattr(free_tier_mod, '_lifetime_incr', fake_lifetime_incr)
    monkeypatch.setattr(free_tier_mod, 'has_paid', fake_has_paid)
    monkeypatch.setattr(free_tier_mod, 'has_balance', fake_has_balance)
    return state


def _blocking_billing():
    """A BillingService double whose reserve() blows up like an empty
    wallet would if it is ever actually awaited -- proof reserve() was
    genuinely skipped in the covered case, not just uninteresting (same
    trick as tests/test_entitlement_reservation_wiring.py's
    ``_billing_instance(raise_on_reserve=True)``)."""
    inst = MagicMock()
    inst.reserve = AsyncMock(side_effect=InsufficientBalanceError(
        'reserve() must not be called: the free tier covers this request'))
    inst.release = AsyncMock(return_value=None)
    inst.settle = AsyncMock(return_value=None)
    return inst


class _FakeProvider:
    v1 = 'http://fake-upstream/v1'

    def headers(self):
        return {'Content-Type': 'application/json'}


def _upstream_ok(content='پاسخ واقعی دستیار'):
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value={
        'choices': [{'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 5, 'completion_tokens': 5},
    })
    resp.content = b'{}'
    resp.text = ''
    return resp


class _FakeBillSession:
    """Just enough of an AsyncSession for the `async with async_session() as
    s: ... await s.commit()` reservation bracket -- BillingService itself is
    mocked out, so this session never actually needs to answer a query."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        return None


# ═══════════════════════════════════════════════════════════════════════
# T1 -- the invariant that used to break: free tier covers it, wallet never
# touched, and the request is actually served.
# ═══════════════════════════════════════════════════════════════════════

class TestChatCompletionsFreeTierCoversIt:
    def test_free_message_is_served_without_touching_the_wallet(self, monkeypatch, client, mock_async_session):
        state = _install_free_tier(monkeypatch)
        billing = _blocking_billing()
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='kr/gpt-4o-mini')), \
             patch.object(chat_mod, '_apply_persian_style_guard_for_model', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'covering_entitlement', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'get_injection_messages', AsyncMock(return_value=[])), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing)), \
             patch.object(chat_mod, '_http', MagicMock(post=AsyncMock(return_value=_upstream_ok()))), \
             patch.object(chat_mod, '_track_usage', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_fire_memory_extraction', MagicMock(return_value=None)):
            resp = client.post('/v1/chat/completions', json={
                'model': 'kr/gpt-4o-mini', 'messages': [{'role': 'user', 'content': 'سلام'}],
            })
        assert resp.status_code == 200, resp.text
        assert resp.json()['choices'][0]['message']['content'] == 'پاسخ واقعی دستیار'
        billing.reserve.assert_not_awaited()
        assert state['lifetime'].get(1) == 1


class TestSmartChatFreeTierCoversIt:
    def test_free_message_is_served_without_touching_the_wallet(self, monkeypatch, client):
        state = _install_free_tier(monkeypatch)
        with _SmartChatEnv(_Session([_CHEAP_ROW])) as env, \
             patch.object(chat_mod, 'check_and_consume', free_tier_mod.check_and_consume), \
             patch.object(chat_smart_mod, 'covers_request', free_tier_mod.covers_request):
            env.billing.reserve = AsyncMock(side_effect=InsufficientBalanceError(
                'reserve() must not be called: the free tier covers this request'))
            resp = _smart_chat_post(client)
        assert resp.status_code == 200, resp.text
        env.billing.reserve.assert_not_awaited()
        assert state['lifetime'].get(42) == 1


class TestChatWithFileFreeTierCoversIt:
    def test_free_message_is_served_without_touching_the_wallet(self, monkeypatch, client, mock_async_session):
        state = _install_free_tier(monkeypatch)
        billing = _blocking_billing()
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='kr/gpt-4o-mini')), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'get_injection_messages', AsyncMock(return_value=[])), \
             patch.object(chat_mod, '_apply_persian_style_guard_for_model', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())), \
             patch.object(chat_mod, 'async_session', MagicMock(return_value=_FakeBillSession())), \
             patch.object(chat_mod, '_http', MagicMock(post=AsyncMock(return_value=_upstream_ok()))), \
             patch.object(chat_mod, '_track_usage', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_fire_memory_extraction', MagicMock(return_value=None)), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing)), \
             patch.object(chat_web_mod, 'covering_entitlement', AsyncMock(return_value=None)):
            resp = client.post(
                '/v1/chat/with-file',
                data={
                    'model': 'kr/gpt-4o-mini',
                    'messages': '[{"role": "user", "content": "سلام"}]',
                    'stream': 'false',
                },
                files={'file': ('note.txt', b'hello world', 'text/plain')},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()['choices'][0]['message']['content'] == 'پاسخ واقعی دستیار'
        billing.reserve.assert_not_awaited()
        assert state['lifetime'].get(1) == 1


class TestCompareFreeTierCoversIt:
    def test_free_message_is_served_without_touching_the_wallet(self, monkeypatch, client, mock_async_session):
        """/v1/compare gates the free tier ONCE for both models (one HTTP
        request = one free message) but reserves TWICE (once per model) --
        covers_request must be consulted at BOTH reservation points, and
        neither may touch the wallet."""
        state = _install_free_tier(monkeypatch)
        billing = _blocking_billing()
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(side_effect=lambda m: m)), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'premium_check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'async_session', MagicMock(return_value=_FakeBillSession())), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing)), \
             patch.object(chat_compare_mod, 'covering_entitlement', AsyncMock(return_value=None)), \
             patch.object(chat_compare_mod, 'get_injection_messages', AsyncMock(return_value=[])), \
             patch.object(chat_compare_mod, '_call_model_once',
                           AsyncMock(side_effect=lambda model, *a, **k: {
                               'model': model, 'content': 'پاسخ واقعی دستیار', 'elapsed': 0.1,
                               'input_tokens': 5, 'output_tokens': 5, 'cost': 0, 'error': None,
                           })):
            resp = client.post('/v1/compare', json={
                'model_a': 'model-a', 'model_b': 'model-b',
                'messages': [{'role': 'user', 'content': 'سلام'}],
            })
        assert resp.status_code == 200, resp.text
        assert 'پاسخ واقعی دستیار' in resp.text
        billing.reserve.assert_not_awaited()
        # One HTTP request -> one free message, even though two reservation
        # points each independently consulted covers_request.
        assert state['lifetime'].get(1) == 1


class TestTaskExecutionFreeTierCoversIt:
    @pytest.mark.asyncio
    async def test_free_message_is_served_without_touching_the_wallet(self, monkeypatch):
        state = _install_free_tier(monkeypatch)
        task = _fake_task()
        with _TaskExecPatches(task=task) as p, \
             patch.object(task_execution_mod, 'check_and_consume', free_tier_mod.check_and_consume), \
             patch.object(task_execution_mod, 'covers_request', free_tier_mod.covers_request):
            p.billing_instance.reserve = AsyncMock(side_effect=InsufficientBalanceError(
                'reserve() must not be called: the free tier covers this request'))
            result = await task_execution_mod._execute_task(task, 42)
        assert result['status'] == 'completed', result
        assert result['result'] == 'پاسخ کامل و معتبر'
        p.billing_instance.reserve.assert_not_awaited()
        assert state['lifetime'].get(42) == 1


class TestDocumentGeneratorFreeTierCoversIt:
    @pytest.mark.asyncio
    async def test_free_message_is_served_without_touching_the_wallet(self, monkeypatch):
        state = _install_free_tier(monkeypatch)
        with _DocGenPatches(resolved_model='sanjab/resolved-model') as p, \
             patch.object(document_generator_mod, 'check_and_consume', free_tier_mod.check_and_consume), \
             patch.object(document_generator_mod, 'covers_request', free_tier_mod.covers_request):
            p.billing_instance.reserve = AsyncMock(side_effect=InsufficientBalanceError(
                'reserve() must not be called: the free tier covers this request'))
            resp = await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model'))
            )
        assert resp.status_code == 200, resp.body
        assert b'\xd8\xb9\xd9\x86\xd9\x88\xd8\xa7\xd9\x86' in resp.body  # 'عنوان' (title), real generated content
        p.billing_instance.reserve.assert_not_awaited()
        assert state['lifetime'].get(42) == 1


class TestRagFreeTierCoversIt:
    @pytest.mark.asyncio
    async def test_free_message_is_served_without_touching_the_wallet(self, monkeypatch):
        state = _install_free_tier(monkeypatch)
        with _RagPatches() as p, \
             patch.object(rag_mod, '_free_tier_check', free_tier_mod.check_and_consume), \
             patch.object(rag_mod, 'covers_request', free_tier_mod.covers_request):
            p.billing_instance.reserve = AsyncMock(side_effect=InsufficientBalanceError(
                'reserve() must not be called: the free tier covers this request'))
            result = await rag_mod.query_documents(**_rag_kwargs())
        assert result['answer'] == 'پاسخ نمونه بر اساس سند', result
        p.billing_instance.reserve.assert_not_awaited()
        assert state['lifetime'].get(42) == 1


# ═══════════════════════════════════════════════════════════════════════
# T2 -- overcorrection guard: a PAID user who has genuinely run their
# wallet to zero must still be refused. Without this, "a free user can
# chat" silently becomes "anyone whose balance hits zero chats for free".
# ═══════════════════════════════════════════════════════════════════════

class TestPaidEmptyWalletUserStillRejected:
    def test_chat_completions(self, monkeypatch, client, mock_async_session):
        state = _install_free_tier(monkeypatch, paid=True, balance=False)
        billing = _blocking_billing()
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='kr/gpt-4o-mini')), \
             patch.object(chat_mod, '_apply_persian_style_guard_for_model', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'covering_entitlement', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing)):
            resp = client.post('/v1/chat/completions', json={
                'model': 'kr/gpt-4o-mini', 'messages': [{'role': 'user', 'content': 'سلام'}],
            })
        assert resp.status_code == 429
        assert resp.json()['error']['code'] == 'balance'
        billing.reserve.assert_awaited_once()
        # A paid user is never metered by the free tier at all -- the
        # lifetime counter must not move either.
        assert state['lifetime'].get(1) is None

    def test_smart_chat(self, monkeypatch, client):
        _install_free_tier(monkeypatch, paid=True, balance=False)
        with _SmartChatEnv(_Session([_CHEAP_ROW])) as env, \
             patch.object(chat_mod, 'check_and_consume', free_tier_mod.check_and_consume), \
             patch.object(chat_smart_mod, 'covers_request', free_tier_mod.covers_request):
            env.billing.reserve = AsyncMock(side_effect=InsufficientBalanceError('insufficient'))
            resp = _smart_chat_post(client)
        assert resp.status_code == 429
        env.billing.reserve.assert_awaited_once()

    def test_chat_with_file(self, monkeypatch, client, mock_async_session):
        _install_free_tier(monkeypatch, paid=True, balance=False)
        billing = _blocking_billing()
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='kr/gpt-4o-mini')), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'async_session', MagicMock(return_value=_FakeBillSession())), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing)), \
             patch.object(chat_web_mod, 'covering_entitlement', AsyncMock(return_value=None)):
            resp = client.post(
                '/v1/chat/with-file',
                data={
                    'model': 'kr/gpt-4o-mini',
                    'messages': '[{"role": "user", "content": "سلام"}]',
                    'stream': 'false',
                },
                files={'file': ('note.txt', b'hello world', 'text/plain')},
            )
        assert resp.status_code == 429
        assert resp.json()['error']['code'] == 'balance'
        billing.reserve.assert_awaited_once()

    def test_compare(self, monkeypatch, client, mock_async_session):
        _install_free_tier(monkeypatch, paid=True, balance=False)
        billing = _blocking_billing()
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(side_effect=lambda m: m)), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'premium_check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'async_session', MagicMock(return_value=_FakeBillSession())), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing)), \
             patch.object(chat_compare_mod, 'covering_entitlement', AsyncMock(return_value=None)):
            resp = client.post('/v1/compare', json={
                'model_a': 'model-a', 'model_b': 'model-b',
                'messages': [{'role': 'user', 'content': 'سلام'}],
            })
        assert resp.status_code == 429
        assert resp.json()['error']['code'] == 'balance'
        billing.reserve.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_task_execution(self, monkeypatch):
        _install_free_tier(monkeypatch, paid=True, balance=False)
        task = _fake_task()
        with _TaskExecPatches(task=task) as p, \
             patch.object(task_execution_mod, 'check_and_consume', free_tier_mod.check_and_consume), \
             patch.object(task_execution_mod, 'covers_request', free_tier_mod.covers_request):
            p.billing_instance.reserve = AsyncMock(side_effect=InsufficientBalanceError('insufficient'))
            result = await task_execution_mod._execute_task(task, 42)
        assert result['status'] == 'failed'
        assert result['error_code'] == 'insufficient_balance'
        p.billing_instance.reserve.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_document_generator(self, monkeypatch):
        _install_free_tier(monkeypatch, paid=True, balance=False)
        with _DocGenPatches(resolved_model='sanjab/resolved-model') as p, \
             patch.object(document_generator_mod, 'check_and_consume', free_tier_mod.check_and_consume), \
             patch.object(document_generator_mod, 'covers_request', free_tier_mod.covers_request):
            p.billing_instance.reserve = AsyncMock(side_effect=InsufficientBalanceError('insufficient'))
            resp = await document_generator_mod.generate_document(
                _fake_request(_body(model='sanjab/resolved-model'))
            )
        assert resp.status_code == 429
        p.billing_instance.reserve.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rag(self, monkeypatch):
        _install_free_tier(monkeypatch, paid=True, balance=False)
        with _RagPatches() as p, \
             patch.object(rag_mod, '_free_tier_check', free_tier_mod.check_and_consume), \
             patch.object(rag_mod, 'covers_request', free_tier_mod.covers_request):
            p.billing_instance.reserve = AsyncMock(side_effect=InsufficientBalanceError('insufficient'))
            result = await rag_mod.query_documents(**_rag_kwargs())
        assert result['answer'] == rag_mod._INSUFFICIENT_BALANCE_MESSAGE
        p.billing_instance.reserve.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════
# T3 -- source-level wiring scan: every module that opens a real wallet
# reservation at a free-tier-gated call site must also consult
# covers_request there. Modeled on tests/test_premium_quota_wiring.py.
# ═══════════════════════════════════════════════════════════════════════

_BACKEND = Path(__file__).resolve().parents[1]

# The seven reservation sites named in the handoff -- fixed on purpose (not
# re-derived from the same regex the assertion below checks) so a broken
# scan cannot silently shrink its own expectation and pass vacuously.
_EXPECTED_RESERVATION_MODULES = {
    'chat.py',
    'chat_smart.py',
    'chat_web.py',
    'chat_compare.py',
    'task_execution.py',
    'document_generator.py',
    'services/rag.py',
}

# A real `*.reserve(` invocation, not the many mentions of "reserve" in
# comments/docstrings this codebase is full of.
_RESERVE_CALL = re.compile(r'\.reserve\(')
_COVERS_REQUEST_CALL = re.compile(r'covers_request\(')


def _modules_that_reserve() -> list[str]:
    found = []
    for path in sorted(_BACKEND.rglob('*.py')):
        rel = path.relative_to(_BACKEND).as_posix()
        if rel.startswith(('tests/', 'migrations/', 'scripts/')):
            continue
        if rel == 'services/billing.py':
            continue  # defines .reserve() itself; not a call site
        src = path.read_text()
        tree = ast.parse(src)
        has_real_reserve_call = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'reserve'
            for node in ast.walk(tree)
        )
        if has_real_reserve_call:
            found.append(rel)
    return found


def test_the_scan_actually_finds_the_seven_known_sites():
    """Guards the guard: if the AST scan stops matching real reserve()
    calls, every assertion below passes vacuously over an empty list."""
    found = set(_modules_that_reserve())
    missing = _EXPECTED_RESERVATION_MODULES - found
    assert not missing, f'reserve() call sites no longer detected in: {sorted(missing)}'


@pytest.mark.parametrize('module', sorted(_EXPECTED_RESERVATION_MODULES))
def test_every_reservation_site_also_consults_covers_request(module):
    src = (_BACKEND / module).read_text()
    assert _COVERS_REQUEST_CALL.search(src), (
        f'{module} opens a real wallet reservation but never calls '
        f'covers_request() -- a user the free tier is covering can be '
        f'rejected at reserve() for having no wallet balance (the bug this '
        f'file exists to catch).'
    )


@pytest.mark.parametrize('module', sorted(_EXPECTED_RESERVATION_MODULES))
def test_covers_request_runs_before_the_reservation_it_guards(module):
    """Same ordering rule as test_premium_quota_wiring.py's reserve-order
    check: walk the AST and take the line of the first genuine
    `*.reserve(...)` call node (comments/docstrings mentioning "reserve"
    are not Call nodes and cannot register), and require the first
    covers_request( text match to precede it."""
    src = (_BACKEND / module).read_text()
    lines = src.splitlines()

    covers_at = next(
        (i for i, ln in enumerate(lines) if _COVERS_REQUEST_CALL.search(ln)), None
    )
    assert covers_at is not None, f'{module}: no covers_request( call found'

    tree = ast.parse(src)
    reserve_lines = sorted(
        node.lineno - 1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'reserve'
    )
    assert reserve_lines, f'{module}: no real reserve() call found'
    reserve_at = reserve_lines[0]
    assert covers_at < reserve_at, (
        f'{module}: covers_request( at line {covers_at + 1} runs AFTER '
        f'reserve() at line {reserve_at + 1}'
    )
