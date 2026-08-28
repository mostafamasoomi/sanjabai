"""Tests for the tool registry (services/chat_tools.py, Phase 8 packet B3).

No live Postgres/Redis. `services.task_service` and `services.assistant_service`
are real, lightweight imports (no DB touched at import time) with their
`create_task`/`create_assistant` monkeypatched per test for isolation.
`services.smart_router` is NOT imported for real anywhere in this file: it
does `import chat` at module scope, and `chat.py` imports
`services.token_budget` / `middleware.compression`, both being edited by
other packets concurrently -- a real import here would make collection of
this file depend on the state of files this packet does not own. Instead a
minimal fake module is injected into `sys.modules['services.smart_router']`
before `chat_tools._list_models()`'s lazy `from services.smart_router import
...` ever runs.

No pytest-asyncio plugin is installed in this suite (see
tests/test_free_tier.py's `_run` helper, mirrored here) -- every async body
is driven through `asyncio.run()` from a plain sync `test_*` function.
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
import types
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database as _database
from services import chat_tools


def _run(coro):
    return asyncio.run(coro)


# ── Fake DB session (mirrors tests/conftest.py's mock_async_session, but
# patches database._real_async_session directly so this file never needs
# to import `app` -- see module docstring for why that import is avoided) ──

@pytest.fixture
def fake_db_session():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    maker = MagicMock(return_value=_Ctx())
    with patch.object(_database, '_real_async_session', maker):
        yield session


# ── Fake services.smart_router, injected only for list_models tests ───────

@dataclass(frozen=True)
class _FakeCandidate:
    provider_model_id: str
    public_id: str
    upstream: str | None
    blended: int


def _install_fake_smart_router(monkeypatch, pool):
    fake_module = types.ModuleType('services.smart_router')

    async def fake_candidate_pool():
        return pool

    def fake_band_thresholds(p):
        if not p:
            return (0, 0)
        values = sorted(c.blended for c in p)
        last = len(values) - 1
        return (values[(last * 33) // 100], values[(last * 67) // 100])

    def fake_band_of(c, thresholds):
        p33, p67 = thresholds
        if c.blended <= p33:
            return 1
        if c.blended <= p67:
            return 2
        return 3

    fake_module.candidate_pool = fake_candidate_pool
    fake_module.band_thresholds = fake_band_thresholds
    fake_module.band_of = fake_band_of
    monkeypatch.setitem(sys.modules, 'services.smart_router', fake_module)


# ── unknown tool / malformed arguments ─────────────────────────────────────

def test_unknown_tool_name_does_not_raise():
    async def _body():
        return await chat_tools.dispatch(1, 'high', 'delete_everything', '{}')

    assert _run(_body()) == {'ok': False, 'error': 'unknown_tool'}


def test_truncated_json_arguments_return_bad_arguments_not_an_exception():
    # A model output cut off by max_tokens mid-object.
    truncated = '{"title": "پیش‌نویس گزارش هفتگی", "prompt": "بنویس'

    async def _body():
        return await chat_tools.dispatch(1, 'high', 'create_task', truncated)

    assert _run(_body()) == {'ok': False, 'error': 'bad_arguments'}


def test_non_object_json_arguments_return_bad_arguments():
    async def _body():
        return await chat_tools.dispatch(1, 'high', 'create_task', '"just a string"')

    assert _run(_body()) == {'ok': False, 'error': 'bad_arguments'}


# ── create_task: is_active/next_run_at are never negotiable ───────────────

def test_create_task_is_always_inactive_even_when_model_asks_for_active(monkeypatch, fake_db_session):
    """Boundary 2, asserted at the INSERT rather than after it.

    This test used to assert that a corrective UPDATE ran with `is_active =
    false` hardcoded in its SQL. That guarded the wrong thing: it proved the
    row was fixed, not that it was never wrong. Between the insert's commit
    and the correction's, a model-authored task was armed and schedulable.
    The senior closed the window by giving `create_task` an explicit
    `activate` flag, so what must be asserted now is the flag itself -- and
    that no second statement follows the insert at all.
    """
    captured = {}

    async def fake_create_task(uid, spec, *, activate=True):
        assert uid == 7
        assert spec.title == 'یادآوری روزانه'
        captured['activate'] = activate
        return {'id': 42, 'title': spec.title}

    monkeypatch.setattr('services.task_service.create_task', fake_create_task)

    args = json.dumps({
        'title': 'یادآوری روزانه', 'prompt': 'یک خلاصه بده',
        'cron_expression': '0 9 * * *',
        # A model trying to sneak activation through -- must be ignored.
        'is_active': True, 'next_run_at': '2026-01-01T00:00:00Z',
    })

    async def _body():
        return await chat_tools.dispatch(7, 'high', 'create_task', args)

    result = _run(_body())

    assert result == {'ok': True, 'id': 42, 'title': 'یادآوری روزانه', 'needs_activation': True}
    assert captured['activate'] is False, 'the tool armed a model-authored task'
    # No follow-up statement: the row is born dormant, not repaired. A
    # reintroduced corrective UPDATE would show up here.
    fake_db_session.execute.assert_not_awaited()


def test_create_task_bad_cron_never_reaches_the_service_core(monkeypatch):
    create_task_mock = AsyncMock()
    monkeypatch.setattr('services.task_service.create_task', create_task_mock)

    args = json.dumps({'title': 'x', 'prompt': 'y', 'cron_expression': '0 0 30 2 *'})

    async def _body():
        return await chat_tools.dispatch(1, 'high', 'create_task', args)

    result = _run(_body())

    assert result == {'ok': False, 'error': 'bad_cron'}
    create_task_mock.assert_not_awaited()


# ── create_assistant: is_public is never negotiable ────────────────────────

def test_create_assistant_is_always_private_even_when_model_asks_public(monkeypatch):
    captured = {}

    async def fake_create_assistant(uid, spec):
        captured['uid'] = uid
        captured['spec'] = spec
        return {'status': 'ok', 'id': 9}

    monkeypatch.setattr('services.assistant_service.create_assistant', fake_create_assistant)

    args = json.dumps({
        'name': 'دستیار من', 'system_prompt': 'همیشه فارسی جواب بده.',
        # A model trying to sneak visibility/model routing through.
        'is_public': True, 'model_id': 'sanjab/some-model',
    })

    async def _body():
        return await chat_tools.dispatch(3, 'high', 'create_assistant', args)

    result = _run(_body())

    assert result == {'ok': True, 'id': 9, 'name': 'دستیار من'}
    assert captured['spec'].is_public is False
    assert captured['spec'].model_id == ''
    assert captured['uid'] == 3


# ── identity: uid is a closure argument, never a tool argument ────────────

def test_user_id_tool_argument_is_ignored_uid_comes_from_the_caller(monkeypatch):
    captured = {}

    async def fake_create_task(uid, spec, *, activate=True):
        captured['uid'] = uid
        return {'id': 1, 'title': spec.title}

    monkeypatch.setattr('services.task_service.create_task', fake_create_task)

    args = json.dumps({
        'title': 'x', 'prompt': 'y', 'cron_expression': '0 9 * * *',
        'user_id': 999999, 'uid': 999999, 'owner': 999999,
    })

    async def _body():
        return await chat_tools.dispatch(7, 'high', 'create_task', args)

    _run(_body())

    assert captured['uid'] == 7


# ── autonomy gate ───────────────────────────────────────────────────────

def test_low_autonomy_announces_only_list_models():
    assert chat_tools.announced_tools('low') == frozenset({'list_models'})


def test_medium_autonomy_announces_all_three_tools():
    assert chat_tools.announced_tools('medium') == chat_tools.TOOL_NAMES


def test_high_autonomy_announces_all_three_tools():
    assert chat_tools.announced_tools('high') == chat_tools.TOOL_NAMES


def test_medium_autonomy_requires_confirmation_and_writes_nothing(monkeypatch):
    create_task_mock = AsyncMock()
    monkeypatch.setattr('services.task_service.create_task', create_task_mock)

    args = json.dumps({'title': 'x', 'prompt': 'y', 'cron_expression': '0 9 * * *'})

    async def _body():
        return await chat_tools.dispatch(1, 'medium', 'create_task', args)

    result = _run(_body())

    assert result['ok'] is False
    assert result['needs_confirmation'] is True
    assert result['preview']['title'] == 'x'
    create_task_mock.assert_not_awaited()


def test_low_autonomy_also_requires_confirmation_if_dispatched_anyway(monkeypatch):
    # The loop is expected to never even offer create_task at `low`
    # (announced_tools), but dispatch() must not silently auto-create if
    # it is called anyway -- defense in depth.
    create_task_mock = AsyncMock()
    monkeypatch.setattr('services.task_service.create_task', create_task_mock)

    args = json.dumps({'title': 'x', 'prompt': 'y', 'cron_expression': '0 9 * * *'})

    async def _body():
        return await chat_tools.dispatch(1, 'low', 'create_task', args)

    result = _run(_body())

    assert result['ok'] is False
    assert result['needs_confirmation'] is True
    create_task_mock.assert_not_awaited()


def test_high_autonomy_dispatches_create_assistant_without_confirmation(monkeypatch):
    async def fake_create_assistant(uid, spec):
        return {'status': 'ok', 'id': 5}

    monkeypatch.setattr('services.assistant_service.create_assistant', fake_create_assistant)

    args = json.dumps({'name': 'x', 'system_prompt': 'y'})

    async def _body():
        return await chat_tools.dispatch(1, 'high', 'create_assistant', args)

    assert _run(_body()) == {'ok': True, 'id': 5, 'name': 'x'}


# ── list_models: public_id only, cap 20 ────────────────────────────────────

def test_list_models_never_leaks_provider_model_id_or_upstream(monkeypatch):
    pool = [
        _FakeCandidate(
            provider_model_id='9router/internal-real-name-1', public_id='sanjab/agnes-2.0',
            upstream='some-secret-upstream', blended=100,
        ),
    ]
    _install_fake_smart_router(monkeypatch, pool)

    async def _body():
        return await chat_tools.dispatch(1, 'high', 'list_models', '{}')

    result = _run(_body())

    assert result['ok'] is True
    encoded = json.dumps(result)
    assert 'provider_model_id' not in encoded
    assert '9router/internal-real-name-1' not in encoded
    assert 'some-secret-upstream' not in encoded
    assert result['models'] == [{'id': 'sanjab/agnes-2.0', 'name_fa': 'agnes-2.0', 'tier': 'ارزان'}]


def test_list_models_caps_at_20_rows(monkeypatch):
    pool = [
        _FakeCandidate(
            provider_model_id=f'upstream/model-{i}', public_id=f'sanjab/model-{i}',
            upstream='u', blended=i,
        )
        for i in range(25)
    ]
    _install_fake_smart_router(monkeypatch, pool)

    async def _body():
        return await chat_tools.dispatch(1, 'high', 'list_models', '{}')

    result = _run(_body())

    assert len(result['models']) == 20


# ── validation boundaries ──────────────────────────────────────────────────

def test_task_title_boundary_100_ok_101_fails():
    ok, err = chat_tools._validate_task_args({
        'title': 'x' * 100, 'prompt': 'y', 'cron_expression': '0 9 * * *',
    })
    assert err is None and ok['title'] == 'x' * 100

    ok, err = chat_tools._validate_task_args({
        'title': 'x' * 101, 'prompt': 'y', 'cron_expression': '0 9 * * *',
    })
    assert ok is None and err == 'bad_title'


def test_task_title_empty_string_fails():
    ok, err = chat_tools._validate_task_args({
        'title': '', 'prompt': 'y', 'cron_expression': '0 9 * * *',
    })
    assert ok is None and err == 'bad_title'


def test_task_prompt_boundary_10000_ok_10001_fails():
    ok, err = chat_tools._validate_task_args({
        'title': 'x', 'prompt': 'y' * 10_000, 'cron_expression': '0 9 * * *',
    })
    assert err is None

    ok, err = chat_tools._validate_task_args({
        'title': 'x', 'prompt': 'y' * 10_001, 'cron_expression': '0 9 * * *',
    })
    assert ok is None and err == 'bad_prompt'


def test_task_description_boundary_500_ok_501_fails():
    ok, err = chat_tools._validate_task_args({
        'title': 'x', 'prompt': 'y', 'cron_expression': '0 9 * * *', 'description': 'd' * 500,
    })
    assert err is None

    ok, err = chat_tools._validate_task_args({
        'title': 'x', 'prompt': 'y', 'cron_expression': '0 9 * * *', 'description': 'd' * 501,
    })
    assert ok is None and err == 'bad_description'


def test_task_bad_cron_expression_rejected():
    ok, err = chat_tools._validate_task_args({
        'title': 'x', 'prompt': 'y', 'cron_expression': 'not a cron expression',
    })
    assert ok is None and err == 'bad_cron'


def test_task_cron_that_never_matches_rejected():
    # February 30th never happens -- compute_next_run returns None rather
    # than raising, and that must still be bad_cron.
    ok, err = chat_tools._validate_task_args({
        'title': 'x', 'prompt': 'y', 'cron_expression': '0 0 30 2 *',
    })
    assert ok is None and err == 'bad_cron'


def test_assistant_name_boundary_100_ok_101_fails():
    ok, err = chat_tools._validate_assistant_args({'name': 'n' * 100, 'system_prompt': 'p'})
    assert err is None

    ok, err = chat_tools._validate_assistant_args({'name': 'n' * 101, 'system_prompt': 'p'})
    assert ok is None and err == 'bad_name'


def test_assistant_system_prompt_boundary_8000_ok_8001_fails():
    ok, err = chat_tools._validate_assistant_args({'name': 'n', 'system_prompt': 'p' * 8000})
    assert err is None

    ok, err = chat_tools._validate_assistant_args({'name': 'n', 'system_prompt': 'p' * 8001})
    assert ok is None and err == 'bad_system_prompt'


def test_assistant_description_boundary_500_ok_501_fails():
    ok, err = chat_tools._validate_assistant_args({
        'name': 'n', 'system_prompt': 'p', 'description': 'd' * 500,
    })
    assert err is None

    ok, err = chat_tools._validate_assistant_args({
        'name': 'n', 'system_prompt': 'p', 'description': 'd' * 501,
    })
    assert ok is None and err == 'bad_description'


def test_assistant_icon_falls_back_to_chat_when_not_allow_listed():
    ok, err = chat_tools._validate_assistant_args({
        'name': 'n', 'system_prompt': 'p', 'icon': 'definitely-not-a-real-icon',
    })
    assert err is None and ok['icon'] == 'chat'


def test_assistant_icon_allow_listed_value_passes_through():
    ok, err = chat_tools._validate_assistant_args({
        'name': 'n', 'system_prompt': 'p', 'icon': 'sparkles',
    })
    assert err is None and ok['icon'] == 'sparkles'


# ── result capping ─────────────────────────────────────────────────────

def test_oversized_result_is_truncated_under_the_char_cap():
    huge = {
        'ok': False, 'needs_confirmation': True,
        'preview': {'title': 'x', 'prompt': 'y' * 10_000, 'cron_expression': '0 9 * * *'},
    }
    capped = chat_tools._cap_result(huge)
    assert capped.get('truncated') is True
    assert len(json.dumps(capped, ensure_ascii=False)) <= chat_tools._MAX_RESULT_CHARS


def test_small_result_passes_through_unchanged():
    small = {'ok': True, 'models': []}
    assert chat_tools._cap_result(small) == small


# ── closed action space, made mechanical (boundary 4) ──────────────────────

def test_module_source_has_no_eval_exec_or_dynamic_getattr():
    with open(chat_tools.__file__, encoding='utf-8') as f:
        source = f.read()
    tree = ast.parse(source)

    banned_names = set()
    bad_getattr_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in ('eval', 'exec'):
            banned_names.add(node.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'getattr':
            # This module never needs getattr at all -- the action space
            # is closed (frozenset membership), not filtered.
            bad_getattr_calls.append(node)

    assert not banned_names, f'eval/exec found: {banned_names}'
    assert not bad_getattr_calls, 'getattr() must never appear in chat_tools.py'


def test_tool_names_is_exactly_three_and_frozen():
    assert chat_tools.TOOL_NAMES == frozenset({'list_models', 'create_task', 'create_assistant'})
    assert isinstance(chat_tools.TOOL_NAMES, frozenset)
