"""The [User Memories] block must tell the model WHEN to use what it remembers.

Measured on production before this gate existed: user 1 has exactly one stored
memory -- "من یدونه گربه خونه دارم اسمش جیگرو هستش و یدونه سگم دارم اسمش خرو /
تهرانم زندگی میکنم" -- and it was injected verbatim under a bare `[User Memories]`
header with no instruction attached. Asked a pure Python question (sort a list of
dicts by several keys), sanjab/gemini-3.1-pro-low opened its answer with:

    «سلام! امیدوارم حال خودت، گربه‌ی قشنگت «جیگرو» و سگ باوفایت «خرو» توی تهران
     حسابی خوب باشه. 🐱🐶»

while the same model, same prompt, called directly on the same upstream went
straight to the answer. The header is the whole difference: `[User Soul` and
`[User Pinned Context` both carry an explicit instruction, `[User Memories]` did
not, so the model read it as context it was expected to acknowledge.

The literal marker `[User Memories]` must survive intact -- context_injection's
dedup guard (and inject_messages') is a substring test on exactly that string,
so any instruction has to be appended after it, never inside the brackets.
"""
from unittest.mock import AsyncMock, patch

import pytest

from services.context_injection import get_injection_messages, inject_messages


async def _memories(facts):
    with patch('dependencies._get_user_memories', new=AsyncMock(return_value=facts)), \
         patch('dependencies._get_user_soul', new=AsyncMock(return_value='')), \
         patch('dependencies._get_user_pinned_context', new=AsyncMock(return_value='')):
        injections = await get_injection_messages(uid=1)
    return next(i for i in injections if '[User Memories]' in i['content'])


class TestMemoryRelevanceGate:
    @pytest.mark.asyncio
    async def test_marker_still_exact_for_the_dedup_guard(self):
        """The instruction may not be written inside the brackets."""
        mem = await _memories(['من یک گربه دارم اسمش جیگرو'])
        assert '[User Memories]' in mem['content']

    @pytest.mark.asyncio
    async def test_header_instructs_the_model_to_ignore_irrelevant_memories(self):
        mem = await _memories(['من یک گربه دارم اسمش جیگرو'])
        head = mem['content'].split('\n- ')[0]
        # Persian-first product: the instruction the model actually reads is
        # Persian, so assert on its substance, not on an English paraphrase.
        assert 'مربوط' in head, f'no relevance instruction in header: {head!r}'
        assert 'نادیده' in head, f'no ignore instruction in header: {head!r}'

    @pytest.mark.asyncio
    async def test_facts_survive_the_header_change(self):
        mem = await _memories(['من یک گربه دارم اسمش جیگرو', 'تهران زندگی می‌کنم'])
        assert 'جیگرو' in mem['content']
        assert 'تهران زندگی می‌کنم' in mem['content']
        assert mem['role'] == 'system'

    @pytest.mark.asyncio
    async def test_dedup_guard_still_fires_on_the_new_header(self):
        """A second pass over a payload that already carries the block must
        not inject it twice -- the guard is a substring test on the marker."""
        mem = await _memories(['من یک گربه دارم اسمش جیگرو'])
        already = [{'role': 'system', 'content': mem['content']},
                   {'role': 'user', 'content': 'سلام'}]
        out = inject_messages(already, [mem])
        assert sum('[User Memories]' in (m.get('content') or '') for m in out) == 1
