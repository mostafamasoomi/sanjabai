"""Regression tests for services/model_identity.py -- the honest model
identity injection (see that module's docstring for the "برچسب صادقانه"
rationale). Pure unit tests against `apply_model_identity` directly: no
app/DB/HTTP fixtures needed, since the module's own DB access
(`_get_display_name`) is monkeypatched out here exactly the way the module
docstring says it must fail open around.

The fourth class is a WIRING GUARD, not a behavior test: new code that is
never called is not done (house rule) -- it greps the four chat entry-point
source files for an actual call to `apply_model_identity` so a future edit
that silently drops the wiring turns this suite red instead of shipping
quietly broken.
"""
from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock, patch

import pytest

import services.model_identity as model_identity


BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent


class TestAppliesIdentityWhenDisplayNameKnown:
    @pytest.mark.asyncio
    async def test_injects_system_message_with_display_name_and_sentinel(self):
        payload = {
            'model': 'bynara/opus-4.6',
            'messages': [{'role': 'user', 'content': 'سلام'}],
        }
        with patch.object(model_identity, '_get_display_name', AsyncMock(return_value='Opus 4.6')):
            await model_identity.apply_model_identity(payload)

        system_msgs = [m for m in payload['messages'] if m.get('role') == 'system']
        assert len(system_msgs) == 1
        assert 'Opus 4.6' in system_msgs[0]['content']
        assert model_identity.IDENTITY_SENTINEL in system_msgs[0]['content']

    @pytest.mark.asyncio
    async def test_no_model_key_is_a_noop(self):
        payload = {'messages': [{'role': 'user', 'content': 'سلام'}]}
        with patch.object(model_identity, '_get_display_name', AsyncMock(return_value='Opus 4.6')) as mock_lookup:
            await model_identity.apply_model_identity(payload)
        mock_lookup.assert_not_awaited()
        assert payload['messages'] == [{'role': 'user', 'content': 'سلام'}]

    @pytest.mark.asyncio
    async def test_unknown_model_fails_open_no_injection(self):
        """No confirmed display_name -> no injection, never a guessed name."""
        payload = {
            'model': 'some/unlisted-model',
            'messages': [{'role': 'user', 'content': 'سلام'}],
        }
        with patch.object(model_identity, '_get_display_name', AsyncMock(return_value=None)):
            await model_identity.apply_model_identity(payload)
        assert payload['messages'] == [{'role': 'user', 'content': 'سلام'}]

    @pytest.mark.asyncio
    async def test_never_raises_on_db_lookup_error(self):
        payload = {
            'model': 'bynara/opus-4.6',
            'messages': [{'role': 'user', 'content': 'سلام'}],
        }
        with patch.object(model_identity, '_get_display_name', AsyncMock(side_effect=RuntimeError('db down'))):
            await model_identity.apply_model_identity(payload)  # must not raise
        assert payload['messages'] == [{'role': 'user', 'content': 'سلام'}]


class TestIdempotent:
    @pytest.mark.asyncio
    async def test_second_call_on_same_payload_adds_nothing(self):
        payload = {
            'model': 'bynara/opus-4.6',
            'messages': [{'role': 'user', 'content': 'سلام'}],
        }
        with patch.object(model_identity, '_get_display_name', AsyncMock(return_value='Opus 4.6')):
            await model_identity.apply_model_identity(payload)
            await model_identity.apply_model_identity(payload)

        system_msgs = [m for m in payload['messages'] if m.get('role') == 'system']
        assert len(system_msgs) == 1


class TestNeverClobbersLeadingSystemPrompt:
    @pytest.mark.asyncio
    async def test_identity_lands_after_existing_system_message(self):
        original_system = {'role': 'system', 'content': 'TASK-DISTINCTIVE-PERSONA-XYZ: تو یک دستیار متخصص هستی.'}
        payload = {
            'model': 'bynara/opus-4.6',
            'messages': [dict(original_system), {'role': 'user', 'content': 'سلام'}],
        }
        with patch.object(model_identity, '_get_display_name', AsyncMock(return_value='Opus 4.6')):
            await model_identity.apply_model_identity(payload)

        assert payload['messages'][0] == original_system, "assistant persona at index 0 must stay first, byte-identical"
        assert payload['messages'][1]['role'] == 'system'
        assert model_identity.IDENTITY_SENTINEL in payload['messages'][1]['content']


class TestWiringGuard:
    """New code that nothing calls is not done -- prove each of the four
    chat entry points actually calls apply_model_identity."""

    @pytest.mark.parametrize('filename', ['chat.py', 'chat_smart.py', 'chat_web.py', 'chat_compare.py'])
    def test_call_site_present(self, filename):
        src = (BACKEND_DIR / filename).read_text(encoding='utf-8')
        assert 'apply_model_identity(' in src, f"{filename} never calls apply_model_identity"
