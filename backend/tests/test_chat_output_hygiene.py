"""
Tests for chat.py's wiring of the three "garbled replies" fixes:

  FIX 1: leaked <thought>/<think> reasoning blocks are stripped from the
         visible answer (non-streaming: clean_response_dict(); streaming:
         ReasoningStreamFilter) -- see model_output.py for the pure-function
         unit tests (tests/test_model_output.py); this file only proves the
         wiring, not the string algorithms themselves.
  FIX 2: a Persian "write fluent, formal, full-sentence Persian" system
         message is prepended for ninerouter-routed requests that don't
         already carry a client system message (see
         _REASONING_INJECTING_PROVIDERS / _apply_persian_style_guard).
  FIX 3: an empty `model` field resolves to a live catalog default
         (_safe_default_model) instead of the dead 'tencent-hy3' literal,
         and the rejection message no longer suggests a model that was
         just rejected.

No test makes a real network or DB call -- auth, free-tier throttling,
billing, and provider routing are bypassed/faked the same way
test_web_search.py and test_public_model_ids.py already do.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import database as _db


AUTH_HEADERS = {'Authorization': 'Bearer test-token'}


class _FakeProvider:
    def __init__(self, name='litellm', v1='http://fake-upstream/v1'):
        self.name = name
        self.v1 = v1

    def headers(self):
        return {'Content-Type': 'application/json'}


class _NoNameProvider:
    """A provider double with NO `.name` attribute at all -- mirrors
    test_web_search.py's/test_public_model_ids.py's existing _FakeProvider
    fixtures elsewhere in this suite. _apply_persian_style_guard_for_model
    must survive this (getattr default), not 500 the whole request."""
    v1 = 'http://fake-upstream/v1'

    def headers(self):
        return {'Content-Type': 'application/json'}


def _billing_mock():
    instance = MagicMock()
    instance.reserve = AsyncMock(return_value={'reservation_id': 'test-reservation'})
    instance.release = AsyncMock(return_value=None)
    instance.settle = AsyncMock(return_value=None)
    return MagicMock(return_value=instance)


def _upstream_response(body: dict | None = None, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=body or {'choices': [{'message': {'content': 'پاسخ نمونه'}}]})
    resp.content = b'{}'
    return resp


def _patched_http(capture: dict | None = None, body: dict | None = None):
    fake = MagicMock()
    if capture is not None:
        async def _post(url, json=None, headers=None, timeout=None):
            capture['json'] = json
            capture['url'] = url
            return _upstream_response(body)
        fake.post = _post
    else:
        fake.post = AsyncMock(return_value=_upstream_response(body))
    return fake


@pytest.fixture
def _bypass_pipeline():
    """Auth + free-tier + billing bypassed; _resolve_provider defaults to a
    clean litellm double so tests that don't care about FIX 2 don't
    accidentally get the Persian system message injected."""
    with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)), \
         patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
         patch.object(chat_mod, 'BillingService', _billing_mock()), \
         patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)), \
         patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider(name='litellm'))):
        yield


# ── FIX 2: _apply_persian_style_guard (pure) ─────────────────────────────

class TestApplyPersianStyleGuard:
    def test_adds_system_message_for_injecting_provider_with_no_system_message(self):
        payload = {'messages': [{'role': 'user', 'content': 'سلام'}]}
        chat_mod._apply_persian_style_guard(payload, 'ninerouter')
        assert payload['messages'][0] == {'role': 'system', 'content': chat_mod._PERSIAN_STYLE_SYSTEM_MESSAGE}
        assert payload['messages'][1] == {'role': 'user', 'content': 'سلام'}

    def test_noop_for_litellm(self):
        original = [{'role': 'user', 'content': 'سلام'}]
        payload = {'messages': list(original)}
        chat_mod._apply_persian_style_guard(payload, 'litellm')
        assert payload['messages'] == original

    def test_noop_for_unknown_provider_name(self):
        original = [{'role': 'user', 'content': 'سلام'}]
        payload = {'messages': list(original)}
        chat_mod._apply_persian_style_guard(payload, 'omniroute')
        assert payload['messages'] == original

    def test_does_not_clobber_existing_client_system_message(self):
        original = [
            {'role': 'system', 'content': 'شما یک دستیار پزشکی هستید.'},
            {'role': 'user', 'content': 'سلام'},
        ]
        payload = {'messages': list(original)}
        chat_mod._apply_persian_style_guard(payload, 'ninerouter')
        assert payload['messages'] == original
        assert chat_mod._PERSIAN_STYLE_SYSTEM_MESSAGE not in [m['content'] for m in payload['messages']]

    def test_handles_empty_messages_list(self):
        payload = {'messages': []}
        chat_mod._apply_persian_style_guard(payload, 'ninerouter')
        assert payload['messages'] == [{'role': 'system', 'content': chat_mod._PERSIAN_STYLE_SYSTEM_MESSAGE}]


class TestApplyPersianStyleGuardForModel:
    @pytest.mark.asyncio
    async def test_empty_model_is_noop(self):
        payload = {'messages': [{'role': 'user', 'content': 'x'}]}
        with patch.object(chat_mod, '_resolve_provider', AsyncMock()) as mock_resolve:
            await chat_mod._apply_persian_style_guard_for_model(payload, '')
        mock_resolve.assert_not_awaited()
        assert payload['messages'] == [{'role': 'user', 'content': 'x'}]

    @pytest.mark.asyncio
    async def test_resolves_provider_and_applies_for_ninerouter(self):
        payload = {'messages': [{'role': 'user', 'content': 'x'}]}
        with patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider(name='ninerouter'))):
            await chat_mod._apply_persian_style_guard_for_model(payload, 'sanjab/mistral-large')
        assert payload['messages'][0]['role'] == 'system'

    @pytest.mark.asyncio
    async def test_survives_a_provider_double_with_no_name_attribute(self):
        """Regression: several existing test files' _FakeProvider doubles
        have no `.name` at all. This must never turn a style nicety into a
        500 for the whole request."""
        payload = {'messages': [{'role': 'user', 'content': 'x'}]}
        with patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_NoNameProvider())):
            await chat_mod._apply_persian_style_guard_for_model(payload, 'some-model')
        assert payload['messages'] == [{'role': 'user', 'content': 'x'}]

    @pytest.mark.asyncio
    async def test_survives_resolve_provider_raising(self):
        payload = {'messages': [{'role': 'user', 'content': 'x'}]}
        with patch.object(chat_mod, '_resolve_provider', AsyncMock(side_effect=RuntimeError('db down'))):
            await chat_mod._apply_persian_style_guard_for_model(payload, 'some-model')
        assert payload['messages'] == [{'role': 'user', 'content': 'x'}]


# ── FIX 3: _safe_default_model ───────────────────────────────────────────

class TestSafeDefaultModel:
    @pytest.mark.asyncio
    async def test_delegates_to_tasks_default_model(self):
        with patch('tasks._default_model', AsyncMock(return_value='bynara/mimo-v2.5-free')):
            result = await chat_mod._safe_default_model()
        assert result == 'bynara/mimo-v2.5-free'
        assert result != 'tencent-hy3'

    @pytest.mark.asyncio
    async def test_empty_when_catalog_has_nothing(self):
        with patch('tasks._default_model', AsyncMock(return_value='')):
            result = await chat_mod._safe_default_model()
        assert result == ''

    @pytest.mark.asyncio
    async def test_returns_empty_string_never_raises_on_failure(self):
        with patch('tasks._default_model', AsyncMock(side_effect=RuntimeError('db down'))):
            result = await chat_mod._safe_default_model()
        assert result == ''


# ── Integration: /v1/chat/completions and /v1/chat/with-file ────────────

class TestNoModelFieldNoLongerUsesDeadDefault:
    def test_chat_completions_uses_catalog_default_not_dead_literal(self, client, _bypass_pipeline):
        capture: dict = {}
        with patch.object(chat_mod, '_safe_default_model', AsyncMock(return_value='bynara/mimo-v2.5-free')), \
             patch.object(_db, '_real_http', _patched_http(capture)):
            resp = client.post(
                '/v1/chat/completions',
                json={'messages': [{'role': 'user', 'content': 'سلام'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        assert capture['json']['model'] == 'bynara/mimo-v2.5-free'
        assert capture['json']['model'] != 'tencent-hy3'

    def test_chat_completions_no_catalog_default_returns_honest_error_not_contradictory(self, client, _bypass_pipeline):
        with patch.object(chat_mod, '_safe_default_model', AsyncMock(return_value='')):
            resp = client.post(
                '/v1/chat/completions',
                json={'messages': [{'role': 'user', 'content': 'سلام'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 400, resp.text
        message = resp.json()['error']['message']
        # The old bug: the error suggested the EXACT model it just rejected
        # ("مدل تنست-hy3 در دسترس نیست | مدل پیشفرض tencent-hy3 را انتخاب کنید").
        # Must never recommend a specific model id it cannot actually serve.
        assert 'tencent-hy3' not in message

    def test_chat_with_file_uses_catalog_default_not_dead_literal(self, client, _bypass_pipeline):
        capture: dict = {}
        with patch.object(chat_mod, '_safe_default_model', AsyncMock(return_value='bynara/mimo-v2.5-free')), \
             patch.object(_db, '_real_http', _patched_http(capture)):
            resp = client.post(
                '/v1/chat/with-file',
                data={'messages': '[]'},
                files={'file': ('note.txt', b'hello world', 'text/plain')},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        assert capture['json']['model'] == 'bynara/mimo-v2.5-free'

    def test_chat_with_file_no_catalog_default_returns_honest_error(self, client, _bypass_pipeline):
        with patch.object(chat_mod, '_safe_default_model', AsyncMock(return_value='')):
            resp = client.post(
                '/v1/chat/with-file',
                data={'messages': '[]'},
                files={'file': ('note.txt', b'hello world', 'text/plain')},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 400, resp.text
        message = resp.json()['error']['message']
        assert 'tencent-hy3' not in message

    def test_explicit_model_still_rejected_by_name_without_false_suggestion(self, client, _bypass_pipeline):
        """A real (non-empty) but disallowed model must still be rejected,
        and the message must name only the model that was actually
        rejected -- no more bolted-on 'pick tencent-hy3 instead' suggestion
        that can itself be wrong."""
        with patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=False)):
            resp = client.post(
                '/v1/chat/completions',
                json={'model': 'totally-made-up-model', 'messages': [{'role': 'user', 'content': 'سلام'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 400, resp.text
        message = resp.json()['error']['message']
        assert 'totally-made-up-model' in message
        assert 'tencent-hy3' not in message


# ── Integration: FIX 2 end-to-end through the real handlers ──────────────

class TestPersianStyleGuardEndToEnd:
    def test_ninerouter_routed_chat_completions_gets_persian_system_message(self, client, _bypass_pipeline):
        capture: dict = {}
        with patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider(name='ninerouter'))), \
             patch.object(_db, '_real_http', _patched_http(capture)):
            resp = client.post(
                '/v1/chat/completions',
                json={'model': 'tencent-hy3', 'messages': [{'role': 'user', 'content': 'سلام'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        sent_messages = capture['json']['messages']
        assert sent_messages[0]['role'] == 'system'
        assert sent_messages[0]['content'] == chat_mod._PERSIAN_STYLE_SYSTEM_MESSAGE

    def test_litellm_routed_chat_completions_gets_no_extra_system_message(self, client, _bypass_pipeline):
        """_bypass_pipeline already fixes _resolve_provider to litellm --
        this pins that the clean control route pays none of FIX 2's cost."""
        capture: dict = {}
        with patch.object(_db, '_real_http', _patched_http(capture)):
            resp = client.post(
                '/v1/chat/completions',
                json={'model': 'tencent-hy3', 'messages': [{'role': 'user', 'content': 'سلام'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        sent_messages = capture['json']['messages']
        assert all(m.get('role') != 'system' for m in sent_messages)

    def test_client_supplied_system_message_is_not_clobbered_on_ninerouter(self, client, _bypass_pipeline):
        capture: dict = {}
        with patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider(name='ninerouter'))), \
             patch.object(_db, '_real_http', _patched_http(capture)):
            resp = client.post(
                '/v1/chat/completions',
                json={
                    'model': 'tencent-hy3',
                    'messages': [
                        {'role': 'system', 'content': 'شما یک دستیار حقوقی هستید.'},
                        {'role': 'user', 'content': 'سلام'},
                    ],
                },
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        sent_messages = capture['json']['messages']
        system_messages = [m for m in sent_messages if m.get('role') == 'system']
        assert len(system_messages) == 1
        assert system_messages[0]['content'] == 'شما یک دستیار حقوقی هستید.'

    def test_smart_chat_ninerouter_gets_persian_system_message(self, client, _bypass_pipeline):
        capture: dict = {}
        with patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider(name='ninerouter'))), \
             patch.object(_db, '_real_http', _patched_http(capture)):
            resp = client.post(
                '/v1/smart-chat',
                json={'model': 'tencent-hy3', 'messages': [{'role': 'user', 'content': 'سلام'}], 'stream': False},
                headers={**AUTH_HEADERS, 'X-Smart-Model': 'tencent-hy3'},
            )
        assert resp.status_code == 200, resp.text
        sent_messages = capture['json']['messages']
        assert sent_messages[0]['role'] == 'system'
        assert sent_messages[0]['content'] == chat_mod._PERSIAN_STYLE_SYSTEM_MESSAGE


# ── FIX 1 wiring: non-streaming response cleaning ────────────────────────

class TestNonStreamingResponseCleaning:
    def test_chat_completions_strips_leaked_thought_block_from_response(self, client, _bypass_pipeline):
        body = {'choices': [{'message': {'content': '<thought>*   </thought>'}}], 'usage': {'prompt_tokens': 5, 'completion_tokens': 3}}
        with patch.object(_db, '_real_http', _patched_http(body=body)):
            resp = client.post(
                '/v1/chat/completions',
                json={'model': 'tencent-hy3', 'messages': [{'role': 'user', 'content': 'hi'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()['choices'][0]['message']['content'] == ''

    def test_chat_completions_passes_through_clean_content_unchanged(self, client, _bypass_pipeline):
        body = {'choices': [{'message': {'content': 'پاسخ کاملا سالم و روان'}}], 'usage': {'prompt_tokens': 5, 'completion_tokens': 3}}
        with patch.object(_db, '_real_http', _patched_http(body=body)):
            resp = client.post(
                '/v1/chat/completions',
                json={'model': 'tencent-hy3', 'messages': [{'role': 'user', 'content': 'hi'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()['choices'][0]['message']['content'] == 'پاسخ کاملا سالم و روان'

    def test_compare_strips_leaked_thought_block_from_both_models(self, client, _bypass_pipeline):
        async def _post(url, json=None, headers=None, timeout=None):
            return _upstream_response({
                'choices': [{'message': {'content': '<think>reasoning</think>پاسخ نهایی'}}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 3},
            })
        fake_http = MagicMock()
        fake_http.post = _post
        with patch.object(_db, '_real_http', fake_http):
            resp = client.post(
                '/v1/compare',
                json={'model_a': 'tencent-hy3', 'model_b': 'mistral-large', 'messages': [{'role': 'user', 'content': 'hi'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data['model_a']['content'] == 'پاسخ نهایی'
        assert data['model_b']['content'] == 'پاسخ نهایی'
