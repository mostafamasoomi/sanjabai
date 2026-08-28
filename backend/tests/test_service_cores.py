"""Tests for the P-B2 refactor: services/task_service.py and
services/assistant_service.py.

Before this refactor, `tasks.py`'s POST /tasks and `assistants.py`'s POST
/assistants read `uid` from the incoming Request and inserted the row
inline -- uncallable from anywhere that has no Request (e.g. a future LLM
tool-calling loop) without forging one, which is a classic identity-
confusion bug, worse here than usual because this project runs two
parallel auth mechanisms (session cookie + hashed API key). This module
pins:

  1. the service core, called directly with an explicit uid, creates a row
     owned by exactly that uid (and a different uid produces a different
     owner -- proving `uid` isn't ignored/hardcoded/read from ambient
     state);
  2. the HTTP route, unchanged from the caller's point of view: same
     status codes, same body shape, same Persian validation messages;
  3. the service modules never import Request and never touch session/
     cookie state, via an AST walk over their source (stronger than a grep:
     it distinguishes an import/reference from an unrelated substring, e.g.
     a docstring mentioning "Request" in prose);
  4. an unauthenticated call to each HTTP route still returns 401.

No live Postgres/Redis/network -- same doubles as
tests/test_tasks_default_model.py's _FakeSession / conftest's
mock_async_session.
"""
from __future__ import annotations

import ast
import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import assistants as assistants_mod
import tasks as tasks_mod
import services.assistant_service as assistant_service_mod
import services.task_service as task_service_mod
from services.assistant_service import AssistantSpec, create_assistant
from services.task_service import TaskSpec, TaskValidationError, create_task


# ── Fakes ──────────────────────────────────────────────────────────────────

class _FakeSession:
    """Records every ORM object passed to add(); refresh() assigns an
    incrementing id, mirroring conftest.mock_async_session's refresh()
    behaviour (assigns id=1 the first time id is unset) without needing the
    fixture itself, since these tests want to assert on the exact object
    add() was called with.
    """

    def __init__(self):
        self.added: list = []
        self._next_id = 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        if getattr(obj, 'id', None) is None:
            obj.id = self._next_id
            self._next_id += 1


def _install_task_session(session):
    return patch.object(task_service_mod, 'async_session', MagicMock(return_value=session))


def _install_assistant_session(session):
    return patch.object(assistant_service_mod, 'async_session', MagicMock(return_value=session))


# ── 1. Service core: explicit uid owns the created row ──────────────────────

class TestTaskServiceCoreOwnership:
    @pytest.mark.asyncio
    async def test_create_task_row_is_owned_by_the_explicit_uid(self):
        session = _FakeSession()
        spec = TaskSpec(title='گزارش روزانه', prompt='خلاصه کن', cron_expression='0 9 * * *')
        with _install_task_session(session):
            result = await create_task(7, spec)
        assert len(session.added) == 1
        assert session.added[0].user_id == 7
        assert result['id'] == 1
        assert result['title'] == 'گزارش روزانه'

    @pytest.mark.asyncio
    async def test_different_uids_own_different_rows(self):
        spec = TaskSpec(title='t', prompt='p', cron_expression='0 9 * * *')
        session_a = _FakeSession()
        with _install_task_session(session_a):
            await create_task(1, spec)
        session_b = _FakeSession()
        with _install_task_session(session_b):
            await create_task(2, spec)
        assert session_a.added[0].user_id == 1
        assert session_b.added[0].user_id == 2

    @pytest.mark.asyncio
    async def test_bad_cron_raises_validation_error_with_persian_message(self):
        session = _FakeSession()
        spec = TaskSpec(title='t', prompt='p', cron_expression='not a cron at all')
        with _install_task_session(session):
            with pytest.raises(TaskValidationError) as exc:
                await create_task(1, spec)
        assert exc.value.message_fa.startswith('عبارت زمان‌بندی نامعتبر است')
        assert 'Invalid schedule expression' in exc.value.message_en
        # A rejected task is never inserted.
        assert session.added == []


class TestAssistantServiceCoreOwnership:
    @pytest.mark.asyncio
    async def test_create_assistant_row_is_owned_by_the_explicit_uid(self):
        session = _FakeSession()
        spec = AssistantSpec(name='دستیار من', system_prompt='مفید باش')
        with _install_assistant_session(session):
            result = await create_assistant(9, spec)
        assert len(session.added) == 1
        assert session.added[0].user_id == 9
        assert session.added[0].is_public is False
        assert result == {'status': 'ok', 'id': 1}

    @pytest.mark.asyncio
    async def test_different_uids_own_different_rows(self):
        spec = AssistantSpec(name='a')
        session_a = _FakeSession()
        with _install_assistant_session(session_a):
            await create_assistant(3, spec)
        session_b = _FakeSession()
        with _install_assistant_session(session_b):
            await create_assistant(4, spec)
        assert session_a.added[0].user_id == 3
        assert session_b.added[0].user_id == 4

    @pytest.mark.asyncio
    async def test_is_public_true_in_spec_is_still_honored_by_the_core(self):
        """The service core itself does not force is_public=False -- that
        guardrail belongs to whatever caller builds the AssistantSpec (a
        later packet's tool wrapper hardcodes is_public=False before this
        function ever sees it, per the design doc's ss-3 contract). This
        pins that the core is a faithful, unopinionated write path, not a
        second place enforcing that product rule."""
        session = _FakeSession()
        spec = AssistantSpec(name='a', is_public=True)
        with _install_assistant_session(session):
            await create_assistant(1, spec)
        assert session.added[0].is_public is True


# ── 2. HTTP route behaviour is unchanged ────────────────────────────────────

class TestTaskRouteUnchanged:
    @pytest.mark.asyncio
    async def test_create_task_route_success_shape(self):
        session = _FakeSession()
        request = MagicMock()
        payload = tasks_mod.ScheduledTaskCreate(title='t', prompt='p')
        with _install_task_session(session), \
             patch.object(tasks_mod, '_get_user_id', AsyncMock(return_value=1)):
            resp = await tasks_mod.create_task(request, payload)
        assert resp.status_code == 200
        body = json.loads(resp.body)
        assert body['title'] == 't'
        assert body['prompt'] == 'p'
        assert 'id' in body and 'next_run_at' in body

    @pytest.mark.asyncio
    async def test_create_task_route_bad_cron_is_400_with_persian_message(self):
        """Byte-for-byte the same 400 body the inline handler used to build
        directly -- now round-tripped through TaskValidationError."""
        session = _FakeSession()
        request = MagicMock()
        payload = tasks_mod.ScheduledTaskCreate(title='t', prompt='p', cron_expression='garbage')
        with _install_task_session(session), \
             patch.object(tasks_mod, '_get_user_id', AsyncMock(return_value=1)):
            resp = await tasks_mod.create_task(request, payload)
        assert resp.status_code == 400
        body = json.loads(resp.body)
        assert body['detail'].startswith('عبارت زمان‌بندی نامعتبر است')
        assert session.added == []

    @pytest.mark.asyncio
    async def test_create_task_route_unauthenticated_is_401(self):
        request = MagicMock()
        payload = tasks_mod.ScheduledTaskCreate(title='t', prompt='p')
        with patch.object(tasks_mod, '_get_user_id', AsyncMock(return_value=None)):
            resp = await tasks_mod.create_task(request, payload)
        assert resp.status_code == 401
        body = json.loads(resp.body)
        assert body['detail'] == 'لطفاً وارد حساب خود شوید'


class TestAssistantRouteUnchanged:
    @pytest.mark.asyncio
    async def test_create_assistant_route_success_shape(self):
        session = _FakeSession()
        request = MagicMock()
        payload = assistants_mod.AssistantCreate(name='a')
        with _install_assistant_session(session), \
             patch.object(assistants_mod, '_get_user_id', AsyncMock(return_value=1)):
            resp = await assistants_mod.create_assistant(request, payload)
        assert resp.status_code == 200
        body = json.loads(resp.body)
        assert body == {'status': 'ok', 'id': 1}

    @pytest.mark.asyncio
    async def test_create_assistant_route_unauthenticated_is_401(self):
        request = MagicMock()
        payload = assistants_mod.AssistantCreate(name='a')
        with patch.object(assistants_mod, '_get_user_id', AsyncMock(return_value=None)):
            resp = await assistants_mod.create_assistant(request, payload)
        assert resp.status_code == 401
        body = json.loads(resp.body)
        assert body['detail'] == 'لطفاً وارد حساب خود شوید'


# ── 3. Service cores never touch Request/session state ─────────────────────

class TestServiceCoresHaveNoRequestOrSessionAccess:
    """AST walk over the two new modules' source, honest per the packet's
    own admission that a grep is weaker: this distinguishes an actual
    import/Name reference to `Request` (or FastAPI/session-cookie helpers)
    from the string "Request" merely appearing in a comment/docstring, and
    catches an import under any alias.
    """

    _FORBIDDEN_IMPORT_NAMES = {'Request', '_get_user_id', '_get_session_user_id', 'fastapi', 'starlette'}
    _FORBIDDEN_NAME_REFERENCES = {'Request', 'request'}

    def _tree_for(self, module) -> ast.Module:
        return ast.parse(inspect.getsource(module))

    def _assert_clean(self, module):
        tree = self._tree_for(module)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split('.')[0] not in self._FORBIDDEN_IMPORT_NAMES, (
                        f"{module.__name__} imports {alias.name!r}"
                    )
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or '').split('.')[0] not in self._FORBIDDEN_IMPORT_NAMES, (
                    f"{module.__name__} imports from {node.module!r}"
                )
                for alias in node.names:
                    assert alias.name not in self._FORBIDDEN_IMPORT_NAMES, (
                        f"{module.__name__} imports {alias.name!r} from {node.module!r}"
                    )
            elif isinstance(node, ast.Name):
                assert node.id not in self._FORBIDDEN_NAME_REFERENCES, (
                    f"{module.__name__} references name {node.id!r}"
                )
            elif isinstance(node, ast.arg):
                assert node.arg not in self._FORBIDDEN_NAME_REFERENCES, (
                    f"{module.__name__} has a parameter named {node.arg!r}"
                )

    def test_task_service_module_has_no_request_or_session_access(self):
        self._assert_clean(task_service_mod)

    def test_assistant_service_module_has_no_request_or_session_access(self):
        self._assert_clean(assistant_service_mod)

    def test_task_service_create_task_signature_is_uid_first(self):
        sig = inspect.signature(create_task)
        params = list(sig.parameters)
        assert params[0] == 'uid'
        assert params[1] == 'spec'

    def test_assistant_service_create_assistant_signature_is_uid_first(self):
        sig = inspect.signature(create_assistant)
        params = list(sig.parameters)
        assert params[0] == 'uid'
        assert params[1] == 'spec'
