"""Tests for backend/combos.py: user model-combo CRUD.

Style mirrors tests/test_admin_user_ops.py: combos.py is not wired into
app.py yet (the coordinator's job -- see combos.py's own docstring), so
these tests mount just its router in a throwaway FastAPI app and drive it
through a small in-memory fake AsyncSession modelled on
test_admin_user_ops.py's `_FakeWalletSession`.

`chat._resolve_public_model` / `chat._is_model_allowed` are patched on the
real `chat` module object (not on `combos`), because combos.py does
`import chat` and reads `chat.<name>` at call time -- exactly the pattern
document_generator.py and the other chat_*.py siblings use, and the reason
combos.py's docstring gives for choosing `import chat` over
`from chat import ...`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy
from fastapi import FastAPI
from starlette.testclient import TestClient

import chat
import combos
from combos import router as combos_router


# ── Fake session ─────────────────────────────────────────────────────────

class _FakeComboSession:
    """An in-memory double for exactly the statements combos.py issues.

    Dispatches on the literal SQL text (available as `stmt.text` on a
    `sqlalchemy.text()` TextClause without compiling it) rather than
    reimplementing a full SQL engine -- combos.py's queries are all fixed
    string literals (never f-strings, per this repo's SQL-audit rule), so
    matching on a stable prefix/substring of each is enough to route to the
    right in-memory table operation.
    """

    def __init__(self):
        self.combos: dict[int, dict] = {}
        self.items: dict[int, list[dict]] = {}
        self._next_combo_id = 1
        self.committed = False

    def seed_combo(self, *, user_id: int, name: str, policy='sequential', enabled=True,
                   items: list[str] | None = None) -> int:
        combo_id = self._next_combo_id
        self._next_combo_id += 1
        now = datetime.now(timezone.utc)
        self.combos[combo_id] = {
            'id': combo_id, 'user_id': user_id, 'name': name, 'policy': policy,
            'enabled': enabled, 'created_at': now, 'updated_at': now,
        }
        self.items[combo_id] = [
            {'position': i, 'model_public_id': mid} for i, mid in enumerate(items or [])
        ]
        return combo_id

    async def execute(self, stmt, params=None):
        text = stmt.text
        params = params or {}
        result = MagicMock()

        if text.startswith('SELECT COUNT(*) AS c FROM user_model_combo'):
            count = sum(1 for c in self.combos.values() if c['user_id'] == params['uid'])
            result.fetchone.return_value = SimpleNamespace(c=count)
            return result

        if text.startswith('INSERT INTO user_model_combo (user_id'):
            for c in self.combos.values():
                if c['user_id'] == params['uid'] and c['name'] == params['name']:
                    raise sqlalchemy.exc.IntegrityError('insert combo', params, Exception('dup name'))
            combo_id = self._next_combo_id
            self._next_combo_id += 1
            now = datetime.now(timezone.utc)
            row = {
                'id': combo_id, 'user_id': params['uid'], 'name': params['name'],
                'policy': params['policy'], 'enabled': params['enabled'],
                'created_at': now, 'updated_at': now,
            }
            self.combos[combo_id] = row
            self.items[combo_id] = []
            result.fetchone.return_value = SimpleNamespace(**{k: v for k, v in row.items() if k != 'user_id'})
            return result

        if text.startswith('INSERT INTO user_model_combo_item'):
            self.items.setdefault(params['combo_id'], []).append(
                {'position': params['position'], 'model_public_id': params['model_public_id']}
            )
            return result

        if text.startswith('SELECT id, name, policy, enabled, created_at, updated_at FROM user_model_combo'):
            # Ownership is derived from the WHERE clause actually present in
            # `text`, not hardcoded here -- so a production mutation that
            # drops "AND user_id = :uid" from the SQL is faithfully
            # reproduced by this double instead of being masked by a second,
            # independent ownership check living only in the test.
            filters_by_owner = 'user_id = :uid' in text
            combo = self.combos.get(params['id'])
            if combo is None or (filters_by_owner and combo['user_id'] != params['uid']):
                result.fetchone.return_value = None
            else:
                result.fetchone.return_value = SimpleNamespace(
                    **{k: v for k, v in combo.items() if k != 'user_id'}
                )
            return result

        if text.startswith('UPDATE user_model_combo SET name'):
            filters_by_owner = 'user_id = :uid' in text
            combo = self.combos.get(params['id'])
            owned = combo is not None and (not filters_by_owner or combo['user_id'] == params['uid'])
            if owned:
                for cid, c in self.combos.items():
                    if cid != params['id'] and c['user_id'] == params['uid'] and c['name'] == params['name']:
                        raise sqlalchemy.exc.IntegrityError('update combo', params, Exception('dup name'))
                combo['name'] = params['name']
                combo['policy'] = params['policy']
                combo['enabled'] = params['enabled']
                combo['updated_at'] = datetime.now(timezone.utc)
            return result

        if text.startswith('DELETE FROM user_model_combo_item'):
            self.items[params['id']] = []
            return result

        if text.startswith('SELECT position, model_public_id FROM user_model_combo_item'):
            rows = sorted(self.items.get(params['id'], []), key=lambda r: r['position'])
            result.fetchall.return_value = [SimpleNamespace(**r) for r in rows]
            return result

        if text.startswith('DELETE FROM user_model_combo WHERE id'):
            filters_by_owner = 'user_id = :uid' in text
            combo = self.combos.get(params['id'])
            owned = combo is not None and (not filters_by_owner or combo['user_id'] == params['uid'])
            if owned:
                del self.combos[params['id']]
                self.items.pop(params['id'], None)
            return result

        if 'LEFT JOIN user_model_combo_item' in text:
            # Owner filtering is derived from the SQL text, never hardcoded
            # here -- same reason as the _fetch_combo branch above. A double
            # that enforces ownership on its own would stay green when the
            # production query stops filtering, which is precisely the bug
            # the ownership tests exist to catch.
            filters_by_owner = 'c.user_id = :uid' in text
            rows = []
            for cid, combo in sorted(self.combos.items()):
                if filters_by_owner and combo['user_id'] != params['uid']:
                    continue
                combo_items = sorted(self.items.get(cid, []), key=lambda r: r['position'])
                base = dict(combo_id=cid, name=combo['name'], policy=combo['policy'],
                            enabled=combo['enabled'], created_at=combo['created_at'],
                            updated_at=combo['updated_at'])
                if not combo_items:
                    rows.append(SimpleNamespace(**base, position=None, model_public_id=None))
                for it in combo_items:
                    rows.append(SimpleNamespace(**base, position=it['position'],
                                                 model_public_id=it['model_public_id']))
            result.fetchall.return_value = rows
            return result

        raise AssertionError(f'unexpected SQL in fake session: {text!r}')

    async def commit(self):
        self.committed = True


def _make_client(session):
    app = FastAPI()
    app.include_router(combos_router)

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    maker = MagicMock(return_value=_Ctx())
    return TestClient(app), maker


def _auth(uid):
    return patch.object(combos, '_get_user_id', new=AsyncMock(return_value=uid))


def _model_checks_pass():
    """Default happy-path stand-in for the two chat.py gates: every
    submitted id resolves to itself and is allowed."""
    return (
        patch.object(chat, '_resolve_public_model', new=AsyncMock(side_effect=lambda m: m)),
        patch.object(chat, '_is_model_allowed', new=AsyncMock(return_value=True)),
    )


# ── Auth ─────────────────────────────────────────────────────────────────

class TestAuth:
    def test_list_requires_auth(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        with _auth(None), patch.object(combos, 'async_session', maker):
            resp = client.get('/me/combos')
        assert resp.status_code == 401

    def test_create_requires_auth(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        with _auth(None), patch.object(combos, 'async_session', maker):
            resp = client.post('/me/combos', json={'name': 'x', 'items': [
                {'model_public_id': 'sanjab/a'}, {'model_public_id': 'sanjab/b'}]})
        assert resp.status_code == 401

    def test_update_requires_auth(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        with _auth(None), patch.object(combos, 'async_session', maker):
            resp = client.put('/me/combos/1', json={'enabled': False})
        assert resp.status_code == 401

    def test_delete_requires_auth(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        with _auth(None), patch.object(combos, 'async_session', maker):
            resp = client.delete('/me/combos/1')
        assert resp.status_code == 401


# ── Ownership: another user's combo == a nonexistent one ─────────────────

class TestOwnership:
    def test_put_on_someone_elses_combo_is_404_not_403(self):
        session = _FakeComboSession()
        combo_id = session.seed_combo(user_id=1, name='mine', items=['sanjab/a', 'sanjab/b'])
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        with _auth(2), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.put(f'/me/combos/{combo_id}', json={'enabled': False})
        assert resp.status_code == 404
        assert session.combos[combo_id]['enabled'] is True  # untouched

    def test_delete_on_someone_elses_combo_is_404_not_403(self):
        session = _FakeComboSession()
        combo_id = session.seed_combo(user_id=1, name='mine', items=['sanjab/a', 'sanjab/b'])
        client, maker = _make_client(session)
        with _auth(2), patch.object(combos, 'async_session', maker):
            resp = client.delete(f'/me/combos/{combo_id}')
        assert resp.status_code == 404
        assert combo_id in session.combos  # not deleted

    def test_list_returns_only_the_callers_combos(self):
        """The listing query must filter by owner too.

        The three tests above all go through `_fetch_combo`, so they only
        cover the single-combo path. `GET /me/combos` runs a completely
        separate query, and dropping `c.user_id = :uid` from it leaked every
        user's combos to everyone while all other ownership tests stayed
        green -- verified by mutation, which is how this gap was found.
        """
        session = _FakeComboSession()
        mine = session.seed_combo(user_id=1, name='mine', items=['sanjab/a', 'sanjab/b'])
        theirs = session.seed_combo(user_id=2, name='theirs', items=['sanjab/c', 'sanjab/d'])
        client, maker = _make_client(session)
        with _auth(1), patch.object(combos, 'async_session', maker):
            resp = client.get('/me/combos')
        assert resp.status_code == 200
        ids = [c['id'] for c in resp.json()['combos']]
        assert ids == [mine]
        assert theirs not in ids
        names = [c['name'] for c in resp.json()['combos']]
        assert 'theirs' not in names

    def test_nonexistent_combo_gives_the_same_404(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        with _auth(1), patch.object(combos, 'async_session', maker):
            resp = client.delete('/me/combos/999')
        assert resp.status_code == 404


# ── Cap: at most 10 combos per user ───────────────────────────────────────

class TestCombosCap:
    def test_eleventh_combo_is_rejected(self):
        session = _FakeComboSession()
        for i in range(10):
            session.seed_combo(user_id=1, name=f'c{i}', items=['sanjab/a', 'sanjab/b'])
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        with _auth(1), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.post('/me/combos', json={'name': 'eleventh', 'items': [
                {'model_public_id': 'sanjab/a'}, {'model_public_id': 'sanjab/b'}]})
        assert resp.status_code == 400
        assert len(session.combos) == 10

    def test_tenth_combo_is_allowed(self):
        session = _FakeComboSession()
        for i in range(9):
            session.seed_combo(user_id=1, name=f'c{i}', items=['sanjab/a', 'sanjab/b'])
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        with _auth(1), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.post('/me/combos', json={'name': 'tenth', 'items': [
                {'model_public_id': 'sanjab/a'}, {'model_public_id': 'sanjab/b'}]})
        assert resp.status_code == 201
        assert len(session.combos) == 10


# ── Item count bounds: 2..5 inclusive ─────────────────────────────────────

class TestItemBounds:
    def test_one_item_is_rejected(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        with _auth(1), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.post('/me/combos', json={'name': 'x', 'items': [
                {'model_public_id': 'sanjab/a'}]})
        assert resp.status_code == 400
        assert session.combos == {}

    def test_six_items_is_rejected(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        items = [{'model_public_id': f'sanjab/{i}'} for i in range(6)]
        with _auth(1), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.post('/me/combos', json={'name': 'x', 'items': items})
        assert resp.status_code == 400
        assert session.combos == {}

    def test_two_items_is_allowed(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        with _auth(1), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.post('/me/combos', json={'name': 'x', 'items': [
                {'model_public_id': 'sanjab/a'}, {'model_public_id': 'sanjab/b'}]})
        assert resp.status_code == 201

    def test_five_items_is_allowed(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        items = [{'model_public_id': f'sanjab/{i}'} for i in range(5)]
        with _auth(1), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.post('/me/combos', json={'name': 'x', 'items': items})
        assert resp.status_code == 201


# ── Policy ────────────────────────────────────────────────────────────────

class TestPolicy:
    def test_invalid_policy_rejected(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        with _auth(1), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.post('/me/combos', json={
                'name': 'x', 'policy': 'random',
                'items': [{'model_public_id': 'sanjab/a'}, {'model_public_id': 'sanjab/b'}],
            })
        assert resp.status_code == 400
        assert session.combos == {}

    def test_round_robin_is_allowed(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        with _auth(1), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.post('/me/combos', json={
                'name': 'x', 'policy': 'round_robin',
                'items': [{'model_public_id': 'sanjab/a'}, {'model_public_id': 'sanjab/b'}],
            })
        assert resp.status_code == 201
        assert resp.json()['policy'] == 'round_robin'


# ── Model resolution / servability ────────────────────────────────────────

class TestModelValidation:
    def test_unresolvable_model_rejected_no_partial_write(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        with _auth(1), patch.object(combos, 'async_session', maker), \
             patch.object(chat, '_resolve_public_model', new=AsyncMock(side_effect=lambda m: m)), \
             patch.object(chat, '_is_model_allowed', new=AsyncMock(return_value=False)):
            resp = client.post('/me/combos', json={'name': 'x', 'items': [
                {'model_public_id': 'sanjab/a'}, {'model_public_id': 'sanjab/ghost'}]})
        assert resp.status_code == 400
        assert session.combos == {}
        assert session.items == {}

    def test_second_item_failing_still_rejects_whole_request(self):
        """No partial writes: if item 1 of 2 would pass but item 2 fails,
        neither is persisted."""
        session = _FakeComboSession()
        client, maker = _make_client(session)

        async def allowed(model_id):
            return model_id != 'sanjab/bad'

        with _auth(1), patch.object(combos, 'async_session', maker), \
             patch.object(chat, '_resolve_public_model', new=AsyncMock(side_effect=lambda m: m)), \
             patch.object(chat, '_is_model_allowed', new=AsyncMock(side_effect=allowed)):
            resp = client.post('/me/combos', json={'name': 'x', 'items': [
                {'model_public_id': 'sanjab/good'}, {'model_public_id': 'sanjab/bad'}]})
        assert resp.status_code == 400
        assert session.combos == {}


# ── Duplicate model in one combo ──────────────────────────────────────────

class TestDuplicateModel:
    def test_same_model_twice_rejected(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        with _auth(1), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.post('/me/combos', json={'name': 'x', 'items': [
                {'model_public_id': 'sanjab/a'}, {'model_public_id': 'sanjab/a'}]})
        assert resp.status_code == 400
        assert session.combos == {}


# ── Server-assigned positions ──────────────────────────────────────────────

class TestPositionAssignment:
    def test_positions_follow_submission_order_not_client_value(self):
        session = _FakeComboSession()
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        # Client claims position 99/0 (reversed) -- server must ignore this
        # and number 0, 1 by submission order instead.
        with _auth(1), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.post('/me/combos', json={'name': 'x', 'items': [
                {'model_public_id': 'sanjab/first', 'position': 99},
                {'model_public_id': 'sanjab/second', 'position': 0},
            ]})
        assert resp.status_code == 201
        body = resp.json()
        assert body['items'] == [
            {'position': 0, 'model_public_id': 'sanjab/first'},
            {'position': 1, 'model_public_id': 'sanjab/second'},
        ]
        combo_id = body['id']
        stored = sorted(session.items[combo_id], key=lambda r: r['position'])
        assert stored == [
            {'position': 0, 'model_public_id': 'sanjab/first'},
            {'position': 1, 'model_public_id': 'sanjab/second'},
        ]


# ── GET list ────────────────────────────────────────────────────────────

class TestListCombos:
    def test_list_returns_only_callers_combos_with_ordered_items(self):
        session = _FakeComboSession()
        mine = session.seed_combo(user_id=1, name='mine', items=['sanjab/a', 'sanjab/b'])
        session.seed_combo(user_id=2, name='not-mine', items=['sanjab/c', 'sanjab/d'])
        client, maker = _make_client(session)
        with _auth(1), patch.object(combos, 'async_session', maker):
            resp = client.get('/me/combos')
        assert resp.status_code == 200
        body = resp.json()['combos']
        assert len(body) == 1
        assert body[0]['id'] == mine
        assert body[0]['items'] == [
            {'position': 0, 'model_public_id': 'sanjab/a'},
            {'position': 1, 'model_public_id': 'sanjab/b'},
        ]

    def test_list_never_echoes_provider_route_fields(self):
        session = _FakeComboSession()
        session.seed_combo(user_id=1, name='mine', items=['sanjab/a', 'sanjab/b'])
        client, maker = _make_client(session)
        with _auth(1), patch.object(combos, 'async_session', maker):
            resp = client.get('/me/combos')
        raw = resp.text
        assert 'provider_model_id' not in raw
        assert 'upstream' not in raw


# ── PUT update ─────────────────────────────────────────────────────────────

class TestUpdateCombo:
    def test_partial_update_leaves_items_untouched(self):
        session = _FakeComboSession()
        combo_id = session.seed_combo(user_id=1, name='mine', items=['sanjab/a', 'sanjab/b'])
        client, maker = _make_client(session)
        with _auth(1), patch.object(combos, 'async_session', maker):
            resp = client.put(f'/me/combos/{combo_id}', json={'enabled': False})
        assert resp.status_code == 200
        body = resp.json()
        assert body['enabled'] is False
        assert body['items'] == [
            {'position': 0, 'model_public_id': 'sanjab/a'},
            {'position': 1, 'model_public_id': 'sanjab/b'},
        ]

    def test_full_item_replace_resets_positions(self):
        session = _FakeComboSession()
        combo_id = session.seed_combo(user_id=1, name='mine', items=['sanjab/a', 'sanjab/b'])
        client, maker = _make_client(session)
        p1, p2 = _model_checks_pass()
        with _auth(1), patch.object(combos, 'async_session', maker), p1, p2:
            resp = client.put(f'/me/combos/{combo_id}', json={
                'items': [{'model_public_id': 'sanjab/x'}, {'model_public_id': 'sanjab/y'},
                          {'model_public_id': 'sanjab/z'}],
            })
        assert resp.status_code == 200
        assert resp.json()['items'] == [
            {'position': 0, 'model_public_id': 'sanjab/x'},
            {'position': 1, 'model_public_id': 'sanjab/y'},
            {'position': 2, 'model_public_id': 'sanjab/z'},
        ]

    def test_update_invalid_policy_rejected(self):
        session = _FakeComboSession()
        combo_id = session.seed_combo(user_id=1, name='mine', items=['sanjab/a', 'sanjab/b'])
        client, maker = _make_client(session)
        with _auth(1), patch.object(combos, 'async_session', maker):
            resp = client.put(f'/me/combos/{combo_id}', json={'policy': 'nonsense'})
        assert resp.status_code == 400
        assert session.combos[combo_id]['policy'] == 'sequential'

    def test_update_item_bounds_enforced(self):
        session = _FakeComboSession()
        combo_id = session.seed_combo(user_id=1, name='mine', items=['sanjab/a', 'sanjab/b'])
        client, maker = _make_client(session)
        with _auth(1), patch.object(combos, 'async_session', maker):
            resp = client.put(f'/me/combos/{combo_id}', json={
                'items': [{'model_public_id': 'sanjab/only-one'}],
            })
        assert resp.status_code == 400
        assert len(session.items[combo_id]) == 2


# ── DELETE ──────────────────────────────────────────────────────────────

class TestDeleteCombo:
    def test_delete_happy_path(self):
        session = _FakeComboSession()
        combo_id = session.seed_combo(user_id=1, name='mine', items=['sanjab/a', 'sanjab/b'])
        client, maker = _make_client(session)
        with _auth(1), patch.object(combos, 'async_session', maker):
            resp = client.delete(f'/me/combos/{combo_id}')
        assert resp.status_code == 200
        assert resp.json()['status'] == 'deleted'
        assert combo_id not in session.combos

    def test_delete_twice_is_404_the_second_time(self):
        session = _FakeComboSession()
        combo_id = session.seed_combo(user_id=1, name='mine', items=['sanjab/a', 'sanjab/b'])
        client, maker = _make_client(session)
        with _auth(1), patch.object(combos, 'async_session', maker):
            first = client.delete(f'/me/combos/{combo_id}')
            second = client.delete(f'/me/combos/{combo_id}')
        assert first.status_code == 200
        assert second.status_code == 404
