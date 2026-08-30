"""Compare history + continue (migration 0054, backend/chat_compare.py's
`POST /v1/compare` addition + backend/chat_compare_sessions.py's four new
routes) -- docs/superpowers/specs/2026-08-30-compare-history-continue-
design.md.

Covers: session creation on the first /v1/compare call, continue-both
persisting both threads, continue-a/continue-b persisting ONLY the
targeted thread and leaving the other one byte-for-byte untouched,
ownership (404 on another user's session id), and billing reserve/release
scoped to exactly the model(s) in scope for that turn.

Follows this suite's existing /v1/compare test conventions (same fakes as
tests/test_compare_web_search.py / tests/test_compare_stream_guard.py)
rather than inventing a new fixture style -- extended here with a small
in-memory `compare_sessions` table double (`_CompareSessionsFakeSession`)
since none of the existing fakes cover that table.
"""
from __future__ import annotations

import re
import types
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database as _db
import chat as chat_mod
import chat_compare_sessions as ccs_mod
from models import CompareSession
from tests._public_model_ids_chat_fakes import (
    AUTH_HEADERS,
    _billing_mock,
    _CatalogFakeSession,
    _FAKE_CATALOG,
    _FakeProvider,
    _table_name,
    _upstream_response,
)

MODEL_A_REQ = 'sanjab/mistral-large'
MODEL_B_REQ = 'sanjab/claude-sonnet-4'
MODEL_A_CANON = 'bynara/mistral-large'
MODEL_B_CANON = 'kr/claude-sonnet-4'


class _CompareSessionsStore:
    """In-memory `compare_sessions` table, keyed by id -- shared across the
    several short-lived `chat.async_session()` blocks one route opens
    (reserve/release/persist each get their own, same idiom
    compare_models() already uses), because every test constructs exactly
    ONE store + fake-session-maker pair and reuses it for the whole
    request."""

    def __init__(self):
        self.rows: dict[int, types.SimpleNamespace] = {}
        self._next_id = 1

    def seed(self, **kw) -> types.SimpleNamespace:
        defaults = dict(
            id=None, user_id=42,
            model_a=MODEL_A_CANON, model_b=MODEL_B_CANON,
            model_a_requested=MODEL_A_REQ, model_b_requested=MODEL_B_REQ,
            title='t', thread_a=[], thread_b=[],
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        defaults.update(kw)
        if defaults['id'] is None:
            defaults['id'] = self._next_id
        self._next_id = max(self._next_id, defaults['id'] + 1)
        row = types.SimpleNamespace(**defaults)
        self.rows[row.id] = row
        return row


def _match_row(store: _CompareSessionsStore, compiled_sql: str):
    id_m = re.search(r'compare_sessions\.id = (\d+)', compiled_sql) or re.search(r'\bid = (\d+)', compiled_sql)
    if not id_m:
        return None
    row = store.rows.get(int(id_m.group(1)))
    if row is None:
        return None
    uid_m = re.search(r'user_id = (\d+)', compiled_sql)
    if uid_m and row.user_id != int(uid_m.group(1)):
        return None
    return row


class _CompareSessionsFakeSession:
    """Delegates every query NOT touching `compare_sessions` to a
    `_CatalogFakeSession` (model_catalog / price-lookup queries
    `_call_model_once`/`chat._track_usage` need -- same fake the sibling
    /v1/compare tests already rely on) -- and handles the `compare_sessions`
    table itself against a shared `_CompareSessionsStore`."""

    def __init__(self, store: _CompareSessionsStore, catalog=_FAKE_CATALOG):
        self.store = store
        self._catalog = _CatalogFakeSession(catalog)
        self.added: list = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        for obj in self.added:
            if isinstance(obj, CompareSession):
                new_id = self.store._next_id
                self.store._next_id += 1
                self.store.rows[new_id] = types.SimpleNamespace(
                    id=new_id, user_id=obj.user_id, model_a=obj.model_a, model_b=obj.model_b,
                    model_a_requested=obj.model_a_requested, model_b_requested=obj.model_b_requested,
                    title=obj.title, thread_a=obj.thread_a, thread_b=obj.thread_b,
                    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                )
                obj.id = new_id
        self.added = []
        return None

    async def refresh(self, obj, *a, **k):
        return None

    async def execute(self, stmt, params=None, *a, **k):
        text_sql = str(stmt)
        if 'compare_sessions' in text_sql or _table_name(stmt) == 'compare_sessions':
            return self._handle_compare_sessions(stmt, params or {}, text_sql)
        return await self._catalog.execute(stmt, params, *a, **k)

    def _handle_compare_sessions(self, stmt, params, text_sql):
        result = MagicMock()
        kind = type(stmt).__name__
        if kind == 'TextClause':
            uid = params.get('uid')
            rows = [r for r in self.store.rows.values() if r.user_id == uid]
            rows.sort(key=lambda r: r.updated_at, reverse=True)
            if 'count(*)' in text_sql.lower():
                result.fetchone.return_value = types.SimpleNamespace(c=len(rows))
            else:
                off = params.get('off', 0)
                lim = params.get('lim', len(rows))
                result.fetchall.return_value = rows[off: off + lim]
            return result
        compiled = str(stmt.compile(compile_kwargs={'literal_binds': True}))
        row = _match_row(self.store, compiled)
        if kind == 'Select':
            result.fetchone.return_value = row
        elif kind == 'Update':
            if row is not None:
                for k, v in params.items():
                    setattr(row, k, v)
        elif kind == 'Delete':
            if row is not None:
                self.store.rows.pop(row.id, None)
        return result


def _patch_compare_sessions_db(store: _CompareSessionsStore):
    session = _CompareSessionsFakeSession(store)

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return None

    maker = MagicMock(return_value=_Ctx())
    return patch.object(_db, '_real_async_session', maker)


@pytest.fixture
def _bypass_pipeline():
    """Same bypass as the sibling /v1/compare tests: auth, billing
    reservation, and provider routing -- NOT check_and_consume /
    premium_check_and_consume, patched per-test below."""
    with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)), \
         patch.object(chat_mod, 'BillingService', _billing_mock()), \
         patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())):
        yield


def _fake_http(*, calls_expected: int):
    fake_http = MagicMock()
    captured = []

    async def _post(url, json=None, headers=None, timeout=None):
        captured.append(json)
        return _upstream_response({
            'choices': [{'message': {'content': f'پاسخ {len(captured)}'}}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 5},
        })

    fake_http.post = _post
    return fake_http, captured


class TestPostCompareCreatesSession:
    def test_post_compare_returns_session_id_and_persists_row(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        fake_http, captured = _fake_http(calls_expected=2)
        with _patch_compare_sessions_db(store), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(_db, '_real_http', fake_http):
            resp = client.post(
                '/v1/compare',
                json={
                    'model_a': MODEL_A_REQ, 'model_b': MODEL_B_REQ,
                    'messages': [{'role': 'user', 'content': 'قیمت طلا امروز چند است؟'}],
                    'stream': False,
                },
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Strictly additive: every field the stateless endpoint already
        # returned is still there, plus the new session_id.
        assert body['model_a']['model'] == MODEL_A_REQ
        assert body['model_b']['model'] == MODEL_B_REQ
        assert 'faster' in body and 'cheaper' in body and 'messages' in body
        assert body['session_id'] is not None

        row = store.rows[body['session_id']]
        assert row.user_id == 42
        assert row.model_a == MODEL_A_CANON and row.model_b == MODEL_B_CANON
        assert row.model_a_requested == MODEL_A_REQ and row.model_b_requested == MODEL_B_REQ
        assert row.title  # auto-generated from the first user message
        assert [m['role'] for m in row.thread_a] == ['user', 'assistant']
        assert [m['role'] for m in row.thread_b] == ['user', 'assistant']


class TestContinueBoth:
    def test_continue_both_calls_both_models_and_persists_both_threads(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        row = store.seed(
            thread_a=[{'role': 'user', 'content': 'سلام'}, {'role': 'assistant', 'content': 'سلام!'}],
            thread_b=[{'role': 'user', 'content': 'سلام'}, {'role': 'assistant', 'content': 'درود!'}],
        )
        fake_http, captured = _fake_http(calls_expected=2)

        with _patch_compare_sessions_db(store), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'premium_check_and_consume', AsyncMock(return_value=None)), \
             patch.object(_db, '_real_http', fake_http):
            resp = client.post(
                f'/v1/compare/sessions/{row.id}/continue',
                json={'target': 'both', 'content': 'ادامه بده'},
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['model_a'] is not None and body['model_b'] is not None
        assert body['model_a']['model'] == MODEL_A_REQ
        assert body['model_b']['model'] == MODEL_B_REQ
        assert len(captured) == 2, "both models must have been called upstream"

        assert len(row.thread_a) == 4  # +user +assistant
        assert len(row.thread_b) == 4
        assert row.thread_a[-2] == {'role': 'user', 'content': 'ادامه بده'}
        assert row.thread_b[-2] == {'role': 'user', 'content': 'ادامه بده'}

    def test_continue_both_scopes_billing_to_both_models(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        row = store.seed()
        fake_http, _ = _fake_http(calls_expected=2)
        billing = chat_mod.BillingService(None)  # the mocked instance _bypass_pipeline installed

        ft_spy = AsyncMock(return_value=None)
        premium_spy = AsyncMock(return_value=None)
        with _patch_compare_sessions_db(store), \
             patch.object(chat_mod, 'check_and_consume', ft_spy), \
             patch.object(chat_mod, 'premium_check_and_consume', premium_spy), \
             patch.object(ccs_mod, 'covering_entitlement', AsyncMock(return_value=None)), \
             patch.object(ccs_mod, 'covers_request', AsyncMock(return_value=False)), \
             patch.object(_db, '_real_http', fake_http):
            resp = client.post(
                f'/v1/compare/sessions/{row.id}/continue',
                json={'target': 'both', 'content': 'ادامه بده'},
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 200, resp.text
        ft_spy.assert_awaited_once_with(42, [MODEL_A_CANON, MODEL_B_CANON])
        premium_spy.assert_awaited_once_with(42, [MODEL_A_CANON, MODEL_B_CANON])
        assert billing.reserve.await_count == 2
        assert billing.release.await_count == 2


class TestContinueSoloTarget:
    def test_continue_target_a_touches_only_a_thread_and_billing(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        row = store.seed(
            thread_a=[{'role': 'user', 'content': 'سلام'}],
            thread_b=[{'role': 'user', 'content': 'سلام'}, {'role': 'assistant', 'content': 'قبلا جواب دادم'}],
        )
        original_thread_b = list(row.thread_b)
        fake_http, captured = _fake_http(calls_expected=1)
        billing = chat_mod.BillingService(None)

        ft_spy = AsyncMock(return_value=None)
        premium_spy = AsyncMock(return_value=None)
        with _patch_compare_sessions_db(store), \
             patch.object(chat_mod, 'check_and_consume', ft_spy), \
             patch.object(chat_mod, 'premium_check_and_consume', premium_spy), \
             patch.object(ccs_mod, 'covering_entitlement', AsyncMock(return_value=None)), \
             patch.object(ccs_mod, 'covers_request', AsyncMock(return_value=False)), \
             patch.object(_db, '_real_http', fake_http):
            resp = client.post(
                f'/v1/compare/sessions/{row.id}/continue',
                json={'target': 'a', 'content': 'فقط برای تو'},
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['model_a'] is not None
        assert body['model_b'] is None
        assert body['faster'] is None and body['cheaper'] is None
        assert len(captured) == 1, "only model A may be called upstream"

        # ONLY model A's gates/reservation/release fire -- never model B's.
        ft_spy.assert_awaited_once_with(42, [MODEL_A_CANON])
        premium_spy.assert_awaited_once_with(42, [MODEL_A_CANON])
        assert billing.reserve.await_count == 1
        assert billing.release.await_count == 1

        # The untouched side's thread array is byte-for-byte unchanged --
        # same length AND same content (acceptance check #4).
        assert row.thread_b == original_thread_b
        assert len(row.thread_a) == 3  # seeded 1 + user + assistant

    def test_continue_target_b_touches_only_b_thread(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        row = store.seed(
            thread_a=[{'role': 'user', 'content': 'سلام'}, {'role': 'assistant', 'content': 'قبلا جواب دادم'}],
            thread_b=[{'role': 'user', 'content': 'سلام'}],
        )
        original_thread_a = list(row.thread_a)
        fake_http, captured = _fake_http(calls_expected=1)

        with _patch_compare_sessions_db(store), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'premium_check_and_consume', AsyncMock(return_value=None)), \
             patch.object(_db, '_real_http', fake_http):
            resp = client.post(
                f'/v1/compare/sessions/{row.id}/continue',
                json={'target': 'b', 'content': 'فقط برای تو'},
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['model_a'] is None
        assert body['model_b'] is not None
        assert len(captured) == 1

        assert row.thread_a == original_thread_a
        assert len(row.thread_b) == 3  # seeded 1 + user + assistant


class TestContinueValidation:
    def test_invalid_target_returns_400(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        row = store.seed()
        with _patch_compare_sessions_db(store):
            resp = client.post(
                f'/v1/compare/sessions/{row.id}/continue',
                json={'target': 'c', 'content': 'x'},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 400, resp.text
        assert resp.json()['error']['code'] == 'invalid_target'

    def test_continue_another_users_session_404s(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        row = store.seed(user_id=999)  # not caller (42)
        with _patch_compare_sessions_db(store):
            resp = client.post(
                f'/v1/compare/sessions/{row.id}/continue',
                json={'target': 'both', 'content': 'x'},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 404, resp.text
        # No mutation happened to the victim's row.
        assert row.thread_a == [] and row.thread_b == []


class TestSessionHistoryCrud:
    def test_list_paginated_ordered_desc_excludes_threads(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        store.seed(title='اول', updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        store.seed(title='دوم', updated_at=datetime(2026, 1, 3, tzinfo=timezone.utc))
        store.seed(title='سوم', updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
        store.seed(title='مال دیگری', user_id=999, updated_at=datetime(2026, 1, 5, tzinfo=timezone.utc))

        with _patch_compare_sessions_db(store):
            resp = client.get('/v1/compare/sessions', headers=AUTH_HEADERS)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['total'] == 3  # only caller's own rows
        titles = [item['title'] for item in body['items']]
        assert titles == ['دوم', 'سوم', 'اول']  # updated_at DESC
        assert 'thread_a' not in body['items'][0]
        assert 'thread_b' not in body['items'][0]

    def test_list_limit_capped_at_100(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        with _patch_compare_sessions_db(store):
            resp = client.get('/v1/compare/sessions?limit=500', headers=AUTH_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json()['limit'] == 100

    def test_get_session_returns_both_threads(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        row = store.seed(thread_a=[{'role': 'user', 'content': 'a'}], thread_b=[{'role': 'user', 'content': 'b'}])
        with _patch_compare_sessions_db(store):
            resp = client.get(f'/v1/compare/sessions/{row.id}', headers=AUTH_HEADERS)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['thread_a'] == [{'role': 'user', 'content': 'a'}]
        assert body['thread_b'] == [{'role': 'user', 'content': 'b'}]

    def test_get_another_users_session_404s(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        row = store.seed(user_id=999)
        with _patch_compare_sessions_db(store):
            resp = client.get(f'/v1/compare/sessions/{row.id}', headers=AUTH_HEADERS)
        assert resp.status_code == 404, resp.text

    def test_delete_removes_owned_session(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        row = store.seed()
        with _patch_compare_sessions_db(store):
            resp = client.delete(f'/v1/compare/sessions/{row.id}', headers=AUTH_HEADERS)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {'status': 'deleted'}
        assert row.id not in store.rows

    def test_delete_another_users_session_404s_and_does_not_delete(self, client, _bypass_pipeline):
        store = _CompareSessionsStore()
        row = store.seed(user_id=999)
        with _patch_compare_sessions_db(store):
            resp = client.delete(f'/v1/compare/sessions/{row.id}', headers=AUTH_HEADERS)
        assert resp.status_code == 404, resp.text
        assert row.id in store.rows  # untouched
