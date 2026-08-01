"""Tests for the per-user 'pinned context' injection (profile-level
persistent note / pasted .md file, injected into every chat regardless of
conversation or assistant) added alongside the existing memory/soul
injection in services/context_injection.py."""
from unittest.mock import patch, AsyncMock

import pytest

from services.context_injection import get_injection_messages, inject_messages, MAX_PINNED_CONTEXT_CHARS


class TestPinnedContextInjection:
    @pytest.mark.asyncio
    async def test_pinned_context_included_when_set(self):
        with patch('dependencies._get_user_memories', new=AsyncMock(return_value=[])), \
             patch('dependencies._get_user_soul', new=AsyncMock(return_value='')), \
             patch('dependencies._get_user_pinned_context', new=AsyncMock(return_value='من پایتون‌کارم و فارسی جواب می‌خوام.')):
            injections = await get_injection_messages(uid=1)
        assert any('[User Pinned Context' in i['content'] for i in injections)
        pinned = next(i for i in injections if '[User Pinned Context' in i['content'])
        assert 'پایتون‌کارم' in pinned['content']

    @pytest.mark.asyncio
    async def test_absent_when_not_set(self):
        with patch('dependencies._get_user_memories', new=AsyncMock(return_value=[])), \
             patch('dependencies._get_user_soul', new=AsyncMock(return_value='')), \
             patch('dependencies._get_user_pinned_context', new=AsyncMock(return_value='')):
            injections = await get_injection_messages(uid=1)
        assert injections == []

    @pytest.mark.asyncio
    async def test_truncated_to_budget(self):
        long_note = 'a' * (MAX_PINNED_CONTEXT_CHARS + 5000)
        with patch('dependencies._get_user_memories', new=AsyncMock(return_value=[])), \
             patch('dependencies._get_user_soul', new=AsyncMock(return_value='')), \
             patch('dependencies._get_user_pinned_context', new=AsyncMock(return_value=long_note)):
            injections = await get_injection_messages(uid=1)
        pinned = next(i for i in injections if '[User Pinned Context' in i['content'])
        # content = marker line + '\n' + up to MAX_PINNED_CONTEXT_CHARS of body
        assert len(pinned['content']) <= len('[User Pinned Context — یادداشت دائمی کاربر که در تمام چت‌ها باید در نظر گرفته شود:]\n') + MAX_PINNED_CONTEXT_CHARS

    @pytest.mark.asyncio
    async def test_coexists_with_memories_and_soul(self):
        with patch('dependencies._get_user_memories', new=AsyncMock(return_value=['fact one'])), \
             patch('dependencies._get_user_soul', new=AsyncMock(return_value='be concise')), \
             patch('dependencies._get_user_pinned_context', new=AsyncMock(return_value='pinned note')):
            injections = await get_injection_messages(uid=1)
        markers = [i['content'].split('\n')[0] for i in injections]
        assert any('[User Memories]' in m for m in markers)
        assert any('[User Soul' in m for m in markers)
        assert any('[User Pinned Context' in m for m in markers)

    def test_dedup_guard_skips_if_already_present(self):
        injections = [{'role': 'system', 'content': '[User Pinned Context — x]\nnote'}]
        existing = [{'role': 'system', 'content': '[User Pinned Context — already here]\nold note'}]
        result = inject_messages(existing, injections)
        # Only the original message should remain -- no duplicate injected.
        assert len(result) == 1
