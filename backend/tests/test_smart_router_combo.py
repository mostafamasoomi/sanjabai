"""Tests for services/smart_router.select_for_combo -- picking a model from
a user's saved combo (migration 0050's user_model_combo tables).

WHY THESE TESTS EXECUTE REAL SQL, same reasoning as tests/test_smart_router.py
(read its header first): the two clauses that matter most here --
`c.user_id = :uid` and `c.enabled = true` -- are enforced INSIDE the SQL, so
a Python fake session that re-implements its own WHERE would keep enforcing
the old rule and stay green while production started serving one user's
combo to another. The fake session below runs the module's REAL
`sqlalchemy.text()` string against an in-memory SQLite database instead, so
deleting a clause from the statement turns these tests red on behaviour.

`chat._resolve_public_model` and `security._get_redis` are patched on the
real `chat` / `security` module objects, never on `services.smart_router`,
because that module does `import chat` / `import security` and reads
`chat.<name>` / `security._get_redis()` at call time -- the same
IMPORT/MONKEYPATCH CONTRACT security_lockout.py and chat_smart.py document.
"""
from __future__ import annotations

import ast
import pathlib
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import chat as chat_mod
import security as security_mod
import services.smart_router as sr


# ── SQLite-backed fake session ───────────────────────────────────────────

_SCHEMA = """
CREATE TABLE user_model_combo (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    policy TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT 1
);
CREATE TABLE user_model_combo_item (
    id INTEGER PRIMARY KEY,
    combo_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    model_public_id TEXT NOT NULL
);
"""

_OWNER = 7
_STRANGER = 8

# combo_id -> (user_id, name, policy, enabled)
_COMBOS = [
    (1, _OWNER, 'seq', 'sequential', 1),
    (2, _OWNER, 'rr', 'round_robin', 1),
    (3, _OWNER, 'disabled', 'sequential', 0),
    (4, _STRANGER, 'not-yours', 'sequential', 1),
    (5, _OWNER, 'empty', 'sequential', 1),
    (6, _OWNER, 'all-dead', 'sequential', 1),
    (7, _OWNER, 'half-dead', 'sequential', 1),
    (8, _OWNER, 'rr-half-dead', 'round_robin', 1),
]

_ITEMS = [
    # (id, combo_id, position, model_public_id)
    (1, 1, 0, 'sanjab/a'), (2, 1, 1, 'sanjab/b'), (3, 1, 2, 'sanjab/c'),
    (4, 2, 0, 'sanjab/a'), (5, 2, 1, 'sanjab/b'), (6, 2, 2, 'sanjab/c'),
    (7, 3, 0, 'sanjab/a'), (8, 3, 1, 'sanjab/b'),
    (9, 4, 0, 'sanjab/a'), (10, 4, 1, 'sanjab/b'),
    # combo 5 deliberately has no items at all
    (11, 6, 0, 'sanjab/gone'), (12, 6, 1, 'sanjab/alsogone'),
    # combo 7: the FIRST item is withdrawn, the survivors follow
    (13, 7, 0, 'sanjab/gone'), (14, 7, 1, 'sanjab/b'), (15, 7, 2, 'sanjab/c'),
    (16, 8, 0, 'sanjab/gone'), (17, 8, 1, 'sanjab/b'), (18, 8, 2, 'sanjab/c'),
]

# What the catalog still knows: public_id -> provider_model_id. Anything not
# in here resolves to itself (chat._resolve_public_model's real behaviour for
# an unknown string) and therefore matches nothing in the pool.
_RESOLVE = {
    'sanjab/a': 'up/a',
    'sanjab/b': 'up/b',
    'sanjab/c': 'up/c',
    # 'sanjab/gone' / 'sanjab/alsogone' are withdrawn: no entry on purpose.
}


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _SqliteSession:
    def __init__(self, conn, calls):
        self._conn = conn
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        self._calls.append(str(stmt))
        cur = self._conn.execute(str(stmt), params or {})
        cols = [d[0] for d in cur.description]
        return _FakeResult([SimpleNamespace(**dict(zip(cols, r))) for r in cur.fetchall()])


class _SessionFactory:
    def __init__(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.executescript(_SCHEMA)
        self.conn.executemany('INSERT INTO user_model_combo VALUES (?,?,?,?,?)', _COMBOS)
        self.conn.executemany('INSERT INTO user_model_combo_item VALUES (?,?,?,?)', _ITEMS)
        self.calls: list[str] = []

    def __call__(self):
        return _SqliteSession(self.conn, self.calls)


class _BoomFactory:
    """A session factory whose query always blows up, for the never-raises
    contract."""

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        raise RuntimeError('connection reset by peer')


def _cand(public_id: str, blended: int) -> sr.Candidate:
    return sr.Candidate(
        provider_model_id=f"up/{public_id.split('/')[-1]}",
        public_id=public_id,
        input_per_million=blended // 4,
        output_per_million=blended - 3 * (blended // 4),
        context_window=100_000,
        upstream='bynara',
        blended=blended,
    )


# The servable pool. 'sanjab/gone' is NOT here -- that is what makes a saved
# combo item dead.
_POOL = [_cand('sanjab/a', 40_000), _cand('sanjab/b', 80_000), _cand('sanjab/c', 160_000)]


@pytest.fixture
def db(monkeypatch):
    factory = _SessionFactory()
    monkeypatch.setattr(chat_mod, 'async_session', factory)

    async def _resolve(model: str) -> str:
        return _RESOLVE.get(model, model)

    monkeypatch.setattr(chat_mod, '_resolve_public_model', _resolve)
    return factory


def _redis(monkeypatch, *, incr):
    """Point security._get_redis at a double whose incr does `incr`."""
    fake = SimpleNamespace(incr=incr)
    monkeypatch.setattr(security_mod, '_get_redis', lambda: fake)
    return fake


# ── sequential ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sequential_returns_the_first_item(db):
    picked = await sr.select_for_combo(_OWNER, 1, _POOL)
    assert picked is not None and picked.public_id == 'sanjab/a'


@pytest.mark.asyncio
async def test_sequential_is_stable_across_calls(db):
    picks = [(await sr.select_for_combo(_OWNER, 1, _POOL)).public_id for _ in range(4)]
    assert picks == ['sanjab/a'] * 4


@pytest.mark.asyncio
async def test_items_are_taken_in_position_order_not_row_order(db):
    """The ORDER BY is the only thing that makes "first item" mean the
    user's first choice; rows come back in whatever order the planner
    likes without it."""
    db.conn.execute('DELETE FROM user_model_combo_item WHERE combo_id = 1')
    db.conn.executemany(
        'INSERT INTO user_model_combo_item VALUES (?,?,?,?)',
        [(101, 1, 2, 'sanjab/a'), (102, 1, 0, 'sanjab/c'), (103, 1, 1, 'sanjab/b')],
    )
    picked = await sr.select_for_combo(_OWNER, 1, _POOL)
    assert picked.public_id == 'sanjab/c', 'position 0 must win, not the lowest row id'


# ── ownership and enabled ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_another_users_combo_is_invisible(db):
    """A combo owned by someone else must be indistinguishable from one
    that does not exist -- and it must certainly not be routed on. Combo 4
    belongs to _STRANGER and its items are all live, so an ownership check
    that got dropped would return sanjab/a here instead of None."""
    assert await sr.select_for_combo(_OWNER, 4, _POOL) is None


@pytest.mark.asyncio
async def test_a_users_own_combo_is_visible_only_to_them(db):
    """The mirror of the test above: combo 1 works for its owner and is
    invisible to the stranger, so the filter is on user_id, not on nothing."""
    assert (await sr.select_for_combo(_OWNER, 1, _POOL)).public_id == 'sanjab/a'
    assert await sr.select_for_combo(_STRANGER, 1, _POOL) is None


@pytest.mark.asyncio
async def test_disabled_combo_is_not_used(db):
    """Combo 3 is owned by the caller and full of live models; only
    `enabled = true` keeps it out."""
    assert await sr.select_for_combo(_OWNER, 3, _POOL) is None


@pytest.mark.asyncio
async def test_unknown_combo_id_returns_none(db):
    assert await sr.select_for_combo(_OWNER, 999, _POOL) is None


# ── dead entries degrade, never break ────────────────────────────────────

@pytest.mark.asyncio
async def test_dead_first_item_is_skipped_not_fatal(db):
    """Combo 7's first item was withdrawn from the catalog. A saved combo
    must degrade to its surviving members -- failing the whole combo would
    let one withdrawn model silently disable every combo naming it."""
    picked = await sr.select_for_combo(_OWNER, 7, _POOL)
    assert picked is not None, 'a dead item must not kill the combo'
    assert picked.public_id == 'sanjab/b'


@pytest.mark.asyncio
async def test_item_that_resolves_but_is_not_in_the_pool_is_dead_too(db):
    """Resolving is not enough: a model that resolves but has since been
    quarantined/unpriced is gone from the pool and must be skipped."""
    pool_without_a = [c for c in _POOL if c.public_id != 'sanjab/a']
    picked = await sr.select_for_combo(_OWNER, 1, pool_without_a)
    assert picked.public_id == 'sanjab/b'


@pytest.mark.asyncio
async def test_all_items_dead_returns_none_so_the_caller_falls_back(db):
    assert await sr.select_for_combo(_OWNER, 6, _POOL) is None


@pytest.mark.asyncio
async def test_combo_with_no_items_returns_none(db):
    """The LEFT JOIN yields one all-NULL filler row for combo 5; it must not
    be mistaken for an item."""
    assert await sr.select_for_combo(_OWNER, 5, _POOL) is None


@pytest.mark.asyncio
async def test_empty_pool_returns_none(db):
    assert await sr.select_for_combo(_OWNER, 1, []) is None


# ── round_robin ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_round_robin_rotates_with_the_redis_counter(db, monkeypatch):
    counter = {'n': 0}

    async def _incr(key):
        counter['n'] += 1
        return counter['n']

    _redis(monkeypatch, incr=_incr)
    picks = [(await sr.select_for_combo(_OWNER, 2, _POOL)).public_id for _ in range(6)]
    # counter % 3 over a three-member combo: every member is served, and the
    # sequence repeats with period 3.
    assert picks[:3] == ['sanjab/b', 'sanjab/c', 'sanjab/a']
    assert picks[3:] == picks[:3]
    assert len(set(picks)) == 3, 'round_robin must not pin one model'


@pytest.mark.asyncio
async def test_round_robin_counter_key_is_per_combo(db, monkeypatch):
    seen: list[str] = []

    async def _incr(key):
        seen.append(key)
        return 1

    _redis(monkeypatch, incr=_incr)
    await sr.select_for_combo(_OWNER, 2, _POOL)
    assert seen == ['smart:combo_rr:2']


@pytest.mark.asyncio
async def test_round_robin_rotates_only_over_the_live_members(db, monkeypatch):
    """Combo 8 is round_robin with a dead first item. The modulo must be
    over the SURVIVORS, or the rotation would index past the end of the
    list (or serve the dead entry) instead of degrading."""
    counter = {'n': 0}

    async def _incr(key):
        counter['n'] += 1
        return counter['n']

    _redis(monkeypatch, incr=_incr)
    picks = [(await sr.select_for_combo(_OWNER, 8, _POOL)).public_id for _ in range(4)]
    assert set(picks) == {'sanjab/b', 'sanjab/c'}
    assert 'sanjab/gone' not in picks


@pytest.mark.asyncio
async def test_round_robin_degrades_to_sequential_when_redis_raises(db, monkeypatch):
    """A rotation counter is a nicety. Losing Redis must cost the rotation,
    never the request: the combo still answers, from position 0."""
    async def _incr(key):
        raise RuntimeError('Connection refused: redis unavailable')

    _redis(monkeypatch, incr=_incr)
    picks = [(await sr.select_for_combo(_OWNER, 2, _POOL)).public_id for _ in range(3)]
    assert picks == ['sanjab/a'] * 3


@pytest.mark.asyncio
async def test_round_robin_degrades_when_redis_client_is_missing(db, monkeypatch):
    """`_get_redis()` returning None (the client was never initialised) must
    degrade the same way an exception does, not blow up the request."""
    monkeypatch.setattr(security_mod, '_get_redis', lambda: None)
    picked = await sr.select_for_combo(_OWNER, 2, _POOL)
    assert picked is not None and picked.public_id == 'sanjab/a'


@pytest.mark.asyncio
async def test_round_robin_degrades_on_a_non_numeric_counter(db, monkeypatch):
    """A corrupt/garbage value in the counter key must not raise either."""
    _redis(monkeypatch, incr=AsyncMock(return_value='not-a-number'))
    picked = await sr.select_for_combo(_OWNER, 2, _POOL)
    assert picked is not None and picked.public_id == 'sanjab/a'


@pytest.mark.asyncio
async def test_sequential_policy_never_touches_redis(db, monkeypatch):
    """A sequential combo has nothing to rotate; spending a Redis round trip
    on it would be pure latency."""
    async def _incr(key):
        raise AssertionError('sequential must not call INCR')

    _redis(monkeypatch, incr=_incr)
    assert (await sr.select_for_combo(_OWNER, 1, _POOL)).public_id == 'sanjab/a'


# ── never raises ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_db_error_returns_none_never_raises(monkeypatch):
    monkeypatch.setattr(chat_mod, 'async_session', _BoomFactory())
    assert await sr.select_for_combo(_OWNER, 1, _POOL) is None


@pytest.mark.asyncio
async def test_no_session_returns_none(monkeypatch):
    monkeypatch.setattr(chat_mod, 'async_session', None)
    assert await sr.select_for_combo(_OWNER, 1, _POOL) is None


@pytest.mark.asyncio
async def test_a_raising_resolver_returns_none_never_raises(db, monkeypatch):
    async def _boom(model):
        raise RuntimeError('resolver exploded')

    monkeypatch.setattr(chat_mod, '_resolve_public_model', _boom)
    assert await sr.select_for_combo(_OWNER, 1, _POOL) is None


@pytest.mark.asyncio
async def test_garbage_arguments_return_none_never_raise(db):
    assert await sr.select_for_combo(_OWNER, None, _POOL) is None
    assert await sr.select_for_combo(None, 1, _POOL) is None
    assert await sr.select_for_combo(_OWNER, 1, None) is None


# ── SQL contract ─────────────────────────────────────────────────────────

_SRC = pathlib.Path(sr.__file__).read_text()


def test_combo_sql_is_a_plain_string_literal():
    """scripts/sql_schema_audit.py only EXPLAINs literal text() arguments;
    an f-string would drop the combo query out of the audit, and both
    tables really exist in production, so a wrong column name would
    otherwise survive to a live request."""
    tree = ast.parse(_SRC)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        f = node.func
        if not isinstance(f, ast.Attribute) or f.attr != 'text':
            continue
        if 'sqlalchemy' not in ast.unparse(f.value):
            continue
        arg = node.args[0]
        assert isinstance(arg, ast.Constant) and isinstance(arg.value, str), (
            f'sqlalchemy.text() argument at line {node.lineno} is not a plain '
            f'string literal ({type(arg).__name__}) -- the SQL audit will skip it'
        )


def test_combo_sql_keeps_every_load_bearing_clause():
    sql = str(sr._COMBO_SQL)
    for clause in (
        'c.id = :combo_id',
        'c.user_id = :uid',
        'c.enabled = true',
        'ORDER BY i.position',
    ):
        assert clause in sql, f'combo query lost its {clause!r} clause'


def test_round_robin_key_shape():
    assert sr._COMBO_RR_KEY.format(42) == 'smart:combo_rr:42'
