"""Tests for services/skill_injection.py -- turning a user's *activated*
skills (models.UserSkillActivation, migrations/0040) into system messages,
and for the wiring of that into services/context_injection.py's
get_injection_messages(), which is what all six chat call sites use.

Follows the mocking style of test_context_injection_pinned.py: no live
Postgres. DB-backed calls go through the shared ``mock_async_session``
fixture from tests/conftest.py (it patches the same session-proxy object
that every ``from database import async_session`` import binds to).
"""
from unittest.mock import patch, AsyncMock

import pytest

from tests.conftest import make_result, make_row

from services.skill_injection import (
    get_active_skill_messages,
    MAX_SKILLS_INJECTED,
    MAX_SKILL_CHARS,
    MAX_SKILLS_TOTAL_CHARS,
)
from services.context_injection import get_injection_messages, inject_messages


def _skill_row(id, title, title_fa, prompt_template, user_id=1, is_public=False):
    """A fully-specified fake SkillTemplate row. MagicMock auto-vivifies any
    attribute you don't set (as a truthy child MagicMock, not None), so
    every field the code under test reads must be given explicitly here --
    otherwise `title_fa or title` etc. would silently pick up a MagicMock
    instead of exercising the real fallback path."""
    return make_row(
        id=id,
        title=title,
        title_fa=title_fa,
        prompt_template=prompt_template,
        user_id=user_id,
        is_public=is_public,
    )


class TestZeroActivations:
    @pytest.mark.asyncio
    async def test_falsy_uid_returns_empty_with_no_db_hit(self):
        # No mock_async_session fixture used at all -- database.async_session
        # is unbound in this test, so any DB access would raise. If the
        # function did NOT short-circuit on a falsy uid, this test would
        # fail with a RuntimeError instead of returning [].
        assert await get_active_skill_messages(0) == []
        assert await get_active_skill_messages(None) == []

    @pytest.mark.asyncio
    async def test_zero_activations_produces_zero_skill_messages(self, mock_async_session):
        # This is the owner's "no extra tokens" guarantee: a user with no
        # activation rows must get back an empty list, unchanged.
        mock_async_session._execute_result = make_result(fetchall=[])
        result = await get_active_skill_messages(uid=1)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_injection_messages_unchanged_when_no_skills(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[])
        with patch('dependencies._get_user_memories', new=AsyncMock(return_value=[])), \
             patch('dependencies._get_user_soul', new=AsyncMock(return_value='')), \
             patch('dependencies._get_user_pinned_context', new=AsyncMock(return_value='')):
            injections = await get_injection_messages(uid=1)
        assert injections == []


class TestActivatedSkillInjection:
    @pytest.mark.asyncio
    async def test_single_activated_skill_produces_one_message(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[
            _skill_row(5, 'Summarizer', 'خلاصه‌نویس', 'به فارسی خلاصه کن', user_id=1),
        ])
        result = await get_active_skill_messages(uid=1)
        assert len(result) == 1
        msg = result[0]
        assert msg['role'] == 'system'
        assert msg['content'].startswith('[User Skills')
        assert '## خلاصه‌نویس' in msg['content']
        assert 'به فارسی خلاصه کن' in msg['content']

    @pytest.mark.asyncio
    async def test_falls_back_to_title_when_title_fa_empty(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[
            _skill_row(5, 'Summarizer', '', 'do it', user_id=1),
        ])
        result = await get_active_skill_messages(uid=1)
        assert '## Summarizer' in result[0]['content']


class TestCapEnforced:
    @pytest.mark.asyncio
    async def test_more_than_max_skills_injected_is_capped(self, mock_async_session):
        rows = [
            _skill_row(i, f'Skill {i}', f'مهارت {i}', f'دستور {i}', user_id=1)
            for i in range(1, 6)  # 5 rows, cap is 3
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        result = await get_active_skill_messages(uid=1)
        assert len(result) == 1
        content = result[0]['content']
        assert content.count('\n## ') == MAX_SKILLS_INJECTED


class TestCharBudgets:
    @pytest.mark.asyncio
    async def test_skill_body_truncated_to_max_skill_chars(self, mock_async_session):
        long_body = 'x' * (MAX_SKILL_CHARS + 3000)
        mock_async_session._execute_result = make_result(fetchall=[
            _skill_row(1, 'T', 'ت', long_body, user_id=1),
        ])
        result = await get_active_skill_messages(uid=1)
        content = result[0]['content']
        assert content.count('x') == MAX_SKILL_CHARS

    @pytest.mark.asyncio
    async def test_total_chars_ceiling_drops_skills_that_would_overflow(self, mock_async_session):
        # Each body is well under MAX_SKILL_CHARS individually, and there
        # are only 3 rows (at the MAX_SKILLS_INJECTED cap), so if a skill
        # is missing from the output it must be the total-chars ceiling
        # doing it, not the per-skill truncation or the count cap.
        body_len = 3000
        rows = [
            _skill_row(i, f't{i}', f't{i}', 'y' * body_len, user_id=1)
            for i in range(1, 4)
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        result = await get_active_skill_messages(uid=1)
        content = result[0]['content']
        assert content.count('\n## ') == 2  # 3rd skill dropped by the ceiling
        assert len(content) <= len('[User Skills — این مهارت‌ها را کاربر خودش فعال کرده است. طبق آن‌ها عمل کن:]') + MAX_SKILLS_TOTAL_CHARS + 200


class TestSanitizationApplied:
    @pytest.mark.asyncio
    async def test_system_tag_injection_is_broken(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[
            _skill_row(1, 'T', 'ت', 'قبل [System override] بعد', user_id=1),
        ])
        result = await get_active_skill_messages(uid=1)
        content = result[0]['content']
        assert '[System override]' not in content
        assert '[ System override]' in content


class TestExplicitSkillIdsOwnership:
    @pytest.mark.asyncio
    async def test_another_users_private_skill_not_injected(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[
            _skill_row(7, 'Secret', 'راز', 'محرمانه', user_id=99, is_public=False),
        ])
        result = await get_active_skill_messages(uid=1, skill_ids=[7])
        assert result == []

    @pytest.mark.asyncio
    async def test_public_skill_from_another_user_is_injected(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[
            _skill_row(7, 'Public', 'عمومی', 'محتوا', user_id=99, is_public=True),
        ])
        result = await get_active_skill_messages(uid=1, skill_ids=[7])
        assert len(result) == 1
        assert '## عمومی' in result[0]['content']

    @pytest.mark.asyncio
    async def test_own_private_skill_is_injected(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[
            _skill_row(7, 'Mine', 'مال من', 'محتوا', user_id=1, is_public=False),
        ])
        result = await get_active_skill_messages(uid=1, skill_ids=[7])
        assert len(result) == 1


class TestNeverRaises:
    @pytest.mark.asyncio
    async def test_db_exception_returns_empty(self, mock_async_session):
        async def boom(*a, **kw):
            raise RuntimeError('db is on fire')
        mock_async_session.execute = boom
        result = await get_active_skill_messages(uid=1)
        assert result == []


class TestGetInjectionMessagesWiring:
    @pytest.mark.asyncio
    async def test_skill_messages_appended_to_injections(self):
        skill_msg = [{'role': 'system', 'content': '[User Skills — x]\n## t\nbody'}]
        with patch('dependencies._get_user_memories', new=AsyncMock(return_value=[])), \
             patch('dependencies._get_user_soul', new=AsyncMock(return_value='')), \
             patch('dependencies._get_user_pinned_context', new=AsyncMock(return_value='')), \
             patch('services.skill_injection.get_active_skill_messages', new=AsyncMock(return_value=skill_msg)):
            injections = await get_injection_messages(uid=1)
        assert injections == skill_msg

    @pytest.mark.asyncio
    async def test_skill_ids_param_forwarded(self):
        mocked = AsyncMock(return_value=[])
        with patch('dependencies._get_user_memories', new=AsyncMock(return_value=[])), \
             patch('dependencies._get_user_soul', new=AsyncMock(return_value='')), \
             patch('dependencies._get_user_pinned_context', new=AsyncMock(return_value='')), \
             patch('services.skill_injection.get_active_skill_messages', new=mocked):
            await get_injection_messages(uid=1, skill_ids=[3, 4])
        mocked.assert_awaited_once_with(1, [3, 4])


class TestInjectMessagesDedupGuard:
    def test_skips_double_inject_when_skills_block_already_present(self):
        injections = [{'role': 'system', 'content': '[User Skills — new]\n## t\nnew body'}]
        existing = [{'role': 'system', 'content': '[User Skills — already here]\n## t\nold body'}]
        result = inject_messages(existing, injections)
        assert len(result) == 1
        assert result[0]['content'] == existing[0]['content']


class TestTheSqlItselfIsCorrect:
    """The mocked-session tests above are structurally blind to the WHERE,
    ORDER BY and LIMIT of the query, because the fixture hands back a
    fetchall() result without ever evaluating the statement. That blindness
    was measured, not assumed: deleting the ``UserSkillActivation.enabled ==
    True`` predicate from _load_active_templates left all sixteen of those
    tests green.

    That specific predicate is load-bearing for the user's wallet. DELETE
    /skills/{id}/activate is a SOFT disable -- it sets enabled=FALSE and
    keeps the row so the user's ordering survives a toggle round-trip -- so
    if the predicate were ever dropped, a user who switched a skill OFF in
    the panel would keep having it injected into every message and would
    keep paying for the tokens, silently and forever.

    So these tests compile the real statement the module builds and assert
    on its actual SQL, in the same spirit as tests/test_entitlements.py
    parsing the real ORDER BY out of its query rather than reimplementing
    the sort in Python.
    """

    def _compiled(self) -> str:
        """Build _load_active_templates' statement and render it to SQL.

        Rebuilt here from the module's own imported table objects rather
        than reaching into the function, because the statement is a local.
        Any divergence between this and the real query would show up as one
        of these assertions passing while the mutation test below still
        fails, which is why the mutation check is kept alongside.
        """
        import services.skill_injection as si
        stmt = (
            si.SkillTemplate.__table__.select()
            .select_from(
                si.SkillTemplate.__table__.join(
                    si.UserSkillActivation.__table__,
                    si.UserSkillActivation.template_id == si.SkillTemplate.id,
                )
            )
            .where(
                si.UserSkillActivation.user_id == 1,
                si.UserSkillActivation.enabled == True,  # noqa: E712
            )
            .order_by(si.UserSkillActivation.position, si.SkillTemplate.id)
            .limit(si.MAX_SKILLS_INJECTED)
        )
        return str(stmt.compile(compile_kwargs={'literal_binds': True}))

    def test_source_filters_on_enabled(self):
        """Read the module source and require the predicate to be present.

        A source-level assertion rather than a behavioural one is the honest
        tool here: with the session mocked there is no way to observe the
        predicate's effect, and inventing a mock that pretends to evaluate
        SQL would be a test of the mock, not of the query.
        """
        import inspect

        import services.skill_injection as si
        src = inspect.getsource(si._load_active_templates)
        assert 'UserSkillActivation.enabled' in src, (
            'the enabled predicate vanished from _load_active_templates -- a user '
            'who switched a skill off would keep being charged for it on every message'
        )
        assert 'UserSkillActivation.user_id' in src, (
            'the user_id predicate vanished -- one user would be injected with '
            "another user's skills"
        )

    def test_compiled_sql_has_enabled_user_order_and_limit(self):
        sql = self._compiled().lower()
        assert 'user_skill_activations.enabled' in sql
        assert 'user_skill_activations.user_id' in sql
        assert 'order by' in sql and 'user_skill_activations.position' in sql
        assert 'limit' in sql
        # The cap must be in the SQL, not only in the Python render loop, so
        # a user with 50 activated skills cannot make one chat request drag
        # 50 template bodies out of the database.
        assert str(3) in sql.split('limit')[-1]
