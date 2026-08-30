"""Regression tests for two /v1/smart-chat defects fixed together (same
file, `chat_smart.py`):

FIX C -- `assistant_id` had no effect in Smart Mode. The frontend routes
every Smart-Mode-ON request to `/v1/smart-chat`, and `smart_chat` never read
`assistant_id`: it round-tripped through `ChatRequest` and was silently
dropped, so a custom assistant's `system_prompt` had zero effect for any
user with Smart Mode on. `/v1/chat/completions` (chat.py:376-392) already
did this correctly; `_inject_assistant` mirrors that block for smart-chat.

FIX G -- Smart Mode was blind to Persian coding/reasoning prompts.
`_CODE_KEYWORDS` was entirely English/syntax tokens, so a Persian coding
prompt classified as `simple`/`medium` and got routed to a weaker tier than
an identical English prompt. `_REASONING_KEYWORDS` gained a few more Persian
terms too.

Style for the assistant-injection tests mirrors test_smart_chat_hotfix.py's
`_Ctx`/`_maker` pattern for faking `chat.async_session`, but drives
`_inject_assistant` directly rather than through the full HTTP handler --
the packet asked for the injection *logic*, not another end-to-end replay of
the whole billing/routing pipeline (already covered by
test_smart_chat_hotfix.py and test_smart_chat_v2_gates.py).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import chat as chat_mod
import chat_smart as chat_smart_mod


# ═══════════════════════════════════════════════════════════════════════
# FIX G -- Persian coding/reasoning classification
# ═══════════════════════════════════════════════════════════════════════

class TestPersianClassification:
    def test_persian_python_function_prompt_is_code_not_simple(self):
        text = 'یک تابع پایتون بنویس که عدد اول را چک کند'
        assert chat_smart_mod._analyze_message(text) == 'code'

    def test_persian_debugging_prompt_is_code(self):
        text = 'این اسکریپت باگ داره، کمک کن دیباگش کنم'
        assert chat_smart_mod._analyze_message(text) == 'code'

    def test_persian_reasoning_prompt_is_reasoning(self):
        text = 'این استدلال را با منطق درست اثبات کن'
        assert chat_smart_mod._analyze_message(text) == 'reasoning'

    def test_persian_explain_prompt_is_reasoning(self):
        text = 'فرضیه من را توضیح‌بده و بهینه‌سازی کن'
        assert chat_smart_mod._analyze_message(text) == 'reasoning'

    def test_english_code_prompt_still_classifies_as_code(self):
        """Widening the Persian side must not regress the English side."""
        text = 'def foo(): return 1'
        assert chat_smart_mod._analyze_message(text) == 'code'


# ═══════════════════════════════════════════════════════════════════════
# FIX C -- assistant_id injection
# ═══════════════════════════════════════════════════════════════════════

class _AssistantRowSession:
    """Answers exactly one query: the assistant lookup. Records every
    statement it sees so a test can assert the row was actually queried."""

    def __init__(self, row):
        self.row = row
        self.calls = 0

    async def execute(self, stmt, *a, **k):
        self.calls += 1
        return SimpleNamespace(fetchone=lambda: self.row)

    async def commit(self):
        return None


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *a):
        return False


def _maker(session):
    return MagicMock(return_value=_Ctx(session))


_ASSISTANT_ROW = SimpleNamespace(id=7, system_prompt='تو یک دستیار متخصص فروش هستی', model_id=None)


class TestAssistantInjection:
    # Every test in this class drives `_inject_assistant` directly (no
    # TestClient), so pytest-asyncio (strict mode, per pytest.ini) needs
    # telling explicitly -- see test_cost_capture.py for the same
    # `@pytest.mark.asyncio` convention; a class-level mark covers every
    # `async def test_*` below without repeating the decorator on each.
    pytestmark = pytest.mark.asyncio

    async def test_system_prompt_lands_at_messages_index_0(self):
        session = _AssistantRowSession(_ASSISTANT_ROW)
        payload_dict = {'assistant_id': 7, 'messages': [{'role': 'user', 'content': 'سلام'}]}
        messages = payload_dict['messages']
        with patch.object(chat_mod, 'async_session', _maker(session)):
            await chat_smart_mod._inject_assistant(payload_dict, messages, uid=1)
        assert messages[0] == {'role': 'system', 'content': 'تو یک دستیار متخصص فروش هستی'}
        assert messages[1] == {'role': 'user', 'content': 'سلام'}
        assert session.calls == 1

    async def test_assistant_id_is_popped_off_the_payload(self):
        """Never forwarded upstream in the JSON body -- mirrors chat.py's
        pop() at line 376."""
        session = _AssistantRowSession(_ASSISTANT_ROW)
        payload_dict = {'assistant_id': 7, 'messages': [{'role': 'user', 'content': 'سلام'}]}
        messages = payload_dict['messages']
        with patch.object(chat_mod, 'async_session', _maker(session)):
            await chat_smart_mod._inject_assistant(payload_dict, messages, uid=1)
        assert 'assistant_id' not in payload_dict

    async def test_no_assistant_id_is_a_no_op(self):
        session = _AssistantRowSession(_ASSISTANT_ROW)
        payload_dict = {'messages': [{'role': 'user', 'content': 'سلام'}]}
        messages = payload_dict['messages']
        with patch.object(chat_mod, 'async_session', _maker(session)):
            await chat_smart_mod._inject_assistant(payload_dict, messages, uid=1)
        assert messages == [{'role': 'user', 'content': 'سلام'}]
        assert session.calls == 0

    async def test_repeat_call_does_not_double_inject(self):
        """Idempotent: calling it twice with the same assistant must not
        insert the system message a second time."""
        session = _AssistantRowSession(_ASSISTANT_ROW)
        payload_dict = {'assistant_id': 7, 'messages': [{'role': 'user', 'content': 'سلام'}]}
        messages = payload_dict['messages']
        with patch.object(chat_mod, 'async_session', _maker(session)):
            await chat_smart_mod._inject_assistant(payload_dict, messages, uid=1)
            # A second call re-supplies assistant_id (as a fresh request
            # carrying the same messages list would) to prove the guard is
            # about content, not merely "the key was already popped".
            payload_dict['assistant_id'] = 7
            await chat_smart_mod._inject_assistant(payload_dict, messages, uid=1)
        system_messages = [m for m in messages if m.get('role') == 'system']
        assert len(system_messages) == 1
        assert messages[0] == {'role': 'system', 'content': 'تو یک دستیار متخصص فروش هستی'}

    async def test_a_broken_lookup_does_not_raise_and_leaves_messages_untouched(self):
        class _RaisingSession:
            async def execute(self, *a, **k):
                raise RuntimeError('database is on fire')

        payload_dict = {'assistant_id': 7, 'messages': [{'role': 'user', 'content': 'سلام'}]}
        messages = payload_dict['messages']
        with patch.object(chat_mod, 'async_session', _maker(_RaisingSession())):
            await chat_smart_mod._inject_assistant(payload_dict, messages, uid=1)
        assert messages == [{'role': 'user', 'content': 'سلام'}]

    async def test_assistant_with_no_system_prompt_injects_nothing(self):
        row = SimpleNamespace(id=8, system_prompt='', model_id=None)
        session = _AssistantRowSession(row)
        payload_dict = {'assistant_id': 8, 'messages': [{'role': 'user', 'content': 'سلام'}]}
        messages = payload_dict['messages']
        with patch.object(chat_mod, 'async_session', _maker(session)):
            await chat_smart_mod._inject_assistant(payload_dict, messages, uid=1)
        assert messages == [{'role': 'user', 'content': 'سلام'}]

    async def test_assistant_model_id_fills_in_an_unset_model(self):
        row = SimpleNamespace(id=9, system_prompt='راهنما', model_id='sanjab/assistant-model')
        session = _AssistantRowSession(row)
        payload_dict = {'assistant_id': 9, 'messages': [{'role': 'user', 'content': 'سلام'}]}
        messages = payload_dict['messages']
        with patch.object(chat_mod, 'async_session', _maker(session)):
            await chat_smart_mod._inject_assistant(payload_dict, messages, uid=1)
        assert payload_dict.get('model') == 'sanjab/assistant-model'

    async def test_assistant_model_id_never_overrides_an_already_selected_model(self):
        """smart_chat always sets payload_dict['model'] to the router's pick
        before calling this -- the model_id fallback must stay inert there,
        matching chat.py's own `not payload_dict.get('model')` guard."""
        row = SimpleNamespace(id=9, system_prompt='راهنما', model_id='sanjab/assistant-model')
        session = _AssistantRowSession(row)
        payload_dict = {'assistant_id': 9, 'model': 'sanjab/router-pick',
                         'messages': [{'role': 'user', 'content': 'سلام'}]}
        messages = payload_dict['messages']
        with patch.object(chat_mod, 'async_session', _maker(session)):
            await chat_smart_mod._inject_assistant(payload_dict, messages, uid=1)
        assert payload_dict['model'] == 'sanjab/router-pick'
