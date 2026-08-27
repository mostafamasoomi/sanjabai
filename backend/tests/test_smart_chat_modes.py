"""Smart Mode's three selection strategies behind the `X-Smart-Mode`
request header: the rules (`auto`), the optional LLM router (`router`) and
a user's saved combo (`combo:<id>`), plus what the response reports back.

What this file pins, and why each one exists:

  1. MALFORMED IS NEVER AN ERROR. The header is attacker-controllable, so
     `combo:abc`, `combo:-1`, an empty value, a 40-digit id and plain
     garbage all degrade to `auto`. A 400 here would let one stray proxy
     header take Smart Mode down for a user.

  2. THE LLM ROUTER IS OPT-IN. `X-Smart-Mode: router` IS gate 1 of the
     three gates services/smart_router_llm.py documents. `llm_route` spends
     real money on every message it runs for, so `auto` and `combo:*` must
     never reach it -- and the call must carry `uid`, or the router's own
     spend writes no usage_event and goes invisible in the profit report.

  3. THE RESPONSE REPORTS WHAT RAN, NOT WHAT WAS ASKED. Both optional
     selectors return None to mean "cannot serve this" and fall back to the
     rules; a fallback must read `auto`. A client told `combo:7` while the
     rules actually picked would have no way to know its combo is dead.

  4. EVERY PICK IS PRICED THE SAME WAY. `smart_router.estimate_cost_toman`
     prices the reservation for a combo pick and a router pick exactly as
     it does for a rules pick -- the flat 1000/5000 it replaced had no
     relation to any price and under-reserved the dearest models by 12x.

  5. A COMBO BELONGS TO ITS OWNER. The ownership clause lives in
     `select_for_combo`'s SQL and is enforced against the AUTHENTICATED
     uid; the combo tests below therefore run that real statement against
     an in-memory SQLite database (same technique, and same reasoning, as
     tests/test_smart_router_combo.py) rather than against a fake that
     re-implements the WHERE and would stay green.

  6. IMPORT SHAPE. chat_smart_mode.py must not import
     services.smart_router_llm at module scope: that module does
     `from services.smart_router import Candidate`, and in the router-first
     order services.smart_router is only initialised as far as its own
     `import chat` line when chat_smart_mode is reached. Both orders run in
     a real subprocess here because that failure only exists at import time.

KNOWN GAP, pinned deliberately: the STREAM path reports no mode. The
`smart_info` SSE event is emitted by chat_stream.py, whose
`_smart_chat_stream` signature would have to change to carry one; that file
is out of scope for this change, so `test_the_stream_path_is_not_half_wired`
below asserts the call is exactly what it was, rather than smuggling the
mode through a second channel.

Style mirrors tests/test_smart_chat_v2_gates.py (module-level patches on
`chat` bypassing auth/billing/routing so only the code under test runs).
"""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import chat_smart as chat_smart_mod
import chat_smart_mode as mode_mod
import database as _db
import services.smart_router as sr
import services.smart_router_llm as srl

_BACKEND = Path(__file__).resolve().parents[1]
_MODE_SOURCE = (_BACKEND / 'chat_smart_mode.py').read_text()

AUTH_HEADERS = {'Authorization': 'Bearer test-token'}
UID = 42
STRANGER = 7


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def _reset_pool_cache():
    """The router's pool cache is module-level global state."""
    sr._pool_cache = []
    sr._pool_cache_at = 0.0
    yield
    sr._pool_cache = []
    sr._pool_cache_at = 0.0


# ── Hand-built candidates (same rates as test_smart_chat_v2_gates.py) ─────
#
#   cheap     -> estimate_cost_toman == 1000 (the floor)
#   expensive -> estimate_cost_toman == 12,800

def _cand(**kw) -> sr.Candidate:
    fields = dict(
        provider_model_id='up/cheap', public_id='sanjab/cheap',
        input_per_million=50_000, output_per_million=150_000,
        context_window=128_000, upstream='ninerouter',
    )
    fields.update(kw)
    fields['blended'] = 3 * fields['input_per_million'] + fields['output_per_million']
    return sr.Candidate(**fields)


CHEAP = _cand()
EXPENSIVE = _cand(
    provider_model_id='up/expensive', public_id='sanjab/expensive',
    input_per_million=4_000_000, output_per_million=6_000_000,
    context_window=1_000_000, upstream='omniroute',
)


class _FakeProvider:
    v1 = 'http://fake-upstream/v1'

    def headers(self):
        return {'Content-Type': 'application/json'}


def _upstream_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value={'choices': [{'message': {'content': 'پاسخ نمونه'}}]})
    resp.content = b'{}'
    return resp


# ── SQLite-backed combo storage ──────────────────────────────────────────
#
# The REAL `_COMBO_SQL` runs against this, so deleting `c.user_id = :uid`
# or `c.enabled = true` from the statement -- or handing the selector the
# wrong uid from chat_smart_mode.py -- turns the ownership tests red on
# behaviour rather than on a string match.

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

_COMBOS = [
    (1, UID, 'mine', 'sequential', 1),
    (2, UID, 'disabled', 'sequential', 0),
    (4, STRANGER, 'not-yours', 'sequential', 1),
]
_ITEMS = [
    (1, 1, 0, 'sanjab/expensive'),
    (2, 2, 0, 'sanjab/expensive'),
    (3, 4, 0, 'sanjab/expensive'),
]

_RESOLVE = {'sanjab/expensive': 'up/expensive', 'sanjab/cheap': 'up/cheap'}


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _SqliteSession:
    """Enough of an AsyncSession for select_for_combo and the billing block
    (whose BillingService is mocked, so only `commit` is reached here)."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        return None

    async def execute(self, stmt, params=None):
        cur = self._conn.execute(str(stmt), params or {})
        if cur.description is None:
            return _FakeResult([])
        cols = [d[0] for d in cur.description]
        return _FakeResult([SimpleNamespace(**dict(zip(cols, r))) for r in cur.fetchall()])


class _SessionFactory:
    def __init__(self):
        # check_same_thread=False: the TestClient runs the app in its own
        # thread, so the connection is created here and used there. One
        # request at a time, so there is nothing to serialise.
        self.conn = sqlite3.connect(':memory:', check_same_thread=False)
        self.conn.executescript(_SCHEMA)
        self.conn.executemany('INSERT INTO user_model_combo VALUES (?,?,?,?,?)', _COMBOS)
        self.conn.executemany('INSERT INTO user_model_combo_item VALUES (?,?,?,?)', _ITEMS)
        self.conn.commit()

    def __call__(self):
        return _SqliteSession(self.conn)


# ── Test environment ─────────────────────────────────────────────────────

class _Env:
    """Bypasses auth/free-tier/premium/entitlement/routing/usage so only
    selection and reporting run. `select_by_rules` is the REAL one: a combo
    or router pick has to differ from what the rules would have chosen for
    the pick to prove anything.

    `combo` / `router` are the picks the two optional selectors return;
    None means "declined", which is their documented fallback answer.
    """

    def __init__(self, pool, *, combo=None, router=None, balance=50_000, combo_db=None):
        self.billing = MagicMock()
        self.billing.reserve = AsyncMock(return_value={'reservation_id': 'r1'})
        self.billing.release = AsyncMock(return_value=None)
        self.http = MagicMock()
        self.http.post = AsyncMock(return_value=_upstream_response())
        self.stream = AsyncMock(return_value=MagicMock())
        self.llm_route = AsyncMock(return_value=router)
        self.free_tier = AsyncMock(return_value=None)
        self.premium = AsyncMock(return_value=None)
        self.combo_db = combo_db
        # A real combo store (SQLite) exercises select_for_combo's own SQL;
        # otherwise the selector itself is mocked.
        self.select_for_combo = (sr.select_for_combo if combo_db is not None
                                 else AsyncMock(return_value=combo))
        self._patches = [
            patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=UID)),
            patch.object(chat_mod, 'check_and_consume', self.free_tier),
            patch.object(chat_mod, 'premium_check_and_consume', self.premium),
            patch.object(chat_mod, 'BillingService', MagicMock(return_value=self.billing)),
            patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())),
            patch.object(chat_mod, '_smart_chat_stream', self.stream),
            patch.object(chat_mod, 'get_injection_messages', AsyncMock(return_value=[])),
            patch.object(chat_mod, '_track_usage', AsyncMock(return_value=None)),
            patch.object(chat_smart_mod, 'covering_entitlement', AsyncMock(return_value=None)),
            patch.object(chat_smart_mod, '_get_user_balance', AsyncMock(return_value=balance)),
            patch.object(sr, 'candidate_pool', AsyncMock(return_value=pool)),
            patch.object(sr, 'select_for_combo', self.select_for_combo),
            patch.object(srl, 'llm_route', self.llm_route),
            patch.object(_db, '_real_http', self.http),
        ]
        if combo_db is not None:
            self._patches += [
                patch.object(chat_mod, 'async_session', combo_db),
                patch.object(chat_mod, '_resolve_public_model',
                             AsyncMock(side_effect=lambda pid: _RESOLVE.get(pid, pid))),
            ]

    def __enter__(self):
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False

    def reserved_toman(self) -> int:
        self.billing.reserve.assert_awaited()
        return self.billing.reserve.await_args.args[1].toman


def _post(client, mode=None, headers=None, stream=False, content='سلام'):
    hdrs = {**AUTH_HEADERS, **(headers or {})}
    if mode is not None:
        hdrs['X-Smart-Mode'] = mode
    return client.post(
        '/v1/smart-chat',
        json={'model': 'auto', 'messages': [{'role': 'user', 'content': content}],
              'stream': stream},
        headers=hdrs,
    )


# ── 1. Parsing: malformed degrades, never errors ─────────────────────────

_PARSES = [
    (None, (mode_mod.MODE_AUTO, None)),
    ('', (mode_mod.MODE_AUTO, None)),
    ('   ', (mode_mod.MODE_AUTO, None)),
    ('auto', (mode_mod.MODE_AUTO, None)),
    ('AUTO', (mode_mod.MODE_AUTO, None)),
    ('router', (mode_mod.MODE_ROUTER, None)),
    ('  Router ', (mode_mod.MODE_ROUTER, None)),
    ('combo:7', (mode_mod.MODE_COMBO, 7)),
    ('COMBO:7', (mode_mod.MODE_COMBO, 7)),
    ('combo:123456789', (mode_mod.MODE_COMBO, 123456789)),
    # Everything below is malformed and must land on auto.
    ('combo:abc', (mode_mod.MODE_AUTO, None)),
    ('combo:-1', (mode_mod.MODE_AUTO, None)),
    ('combo:0', (mode_mod.MODE_AUTO, None)),
    ('combo:007', (mode_mod.MODE_AUTO, None)),
    ('combo:', (mode_mod.MODE_AUTO, None)),
    ('combo', (mode_mod.MODE_AUTO, None)),
    ('combo:7x', (mode_mod.MODE_AUTO, None)),
    ('combo:7;DROP TABLE users', (mode_mod.MODE_AUTO, None)),
    ('combo:99999999999999999999', (mode_mod.MODE_AUTO, None)),
    # Persian digits: int('۱۲') is 12, so a lookalike must be rejected in
    # the regex rather than left to int().
    ('combo:۱۲', (mode_mod.MODE_AUTO, None)),
    ('rules', (mode_mod.MODE_AUTO, None)),
    ('router router', (mode_mod.MODE_AUTO, None)),
]


@pytest.mark.parametrize('raw,expected', _PARSES, ids=[repr(p[0]) for p in _PARSES])
def test_parse_mode(raw, expected):
    assert mode_mod.parse_mode(raw) == expected


def test_mode_label_is_the_wire_form():
    assert mode_mod.mode_label(mode_mod.MODE_AUTO, None) == 'auto'
    assert mode_mod.mode_label(mode_mod.MODE_ROUTER, None) == 'router'
    assert mode_mod.mode_label(mode_mod.MODE_COMBO, 9) == 'combo:9'


class TestMalformedModeDegrades:
    @pytest.mark.parametrize('raw', ['combo:abc', 'combo:-1', 'combo:', '', 'garbage',
                                     'combo:99999999999999999999'])
    def test_a_malformed_mode_answers_normally_instead_of_400(self, client, raw):
        with _Env(pool=[CHEAP, EXPENSIVE]) as env:
            resp = _post(client, mode=raw)
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Mode'] == 'auto'
        assert resp.headers['X-Smart-Model'] == 'sanjab/cheap'
        env.llm_route.assert_not_awaited()
        env.select_for_combo.assert_not_awaited()


# ── 2. The LLM router is opt-in, and carries the uid ─────────────────────

class TestRouterOptIn:
    @pytest.mark.parametrize('mode', [None, 'auto', 'combo:3', 'combo:abc'])
    def test_llm_route_is_not_called_unless_the_mode_is_router(self, client, mode):
        with _Env(pool=[CHEAP, EXPENSIVE], combo=EXPENSIVE) as env:
            assert _post(client, mode=mode).status_code == 200
        env.llm_route.assert_not_awaited()

    def test_router_mode_calls_llm_route_with_the_message_pool_and_balance(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], router=EXPENSIVE, balance=50_000) as env:
            resp = _post(client, mode='router', content='سلام')
        assert resp.status_code == 200, resp.text
        env.llm_route.assert_awaited_once()
        args = env.llm_route.await_args.args
        assert args[0] == 'سلام'
        assert args[1] == [CHEAP, EXPENSIVE]
        assert args[2] == 50_000

    def test_llm_route_is_told_the_uid_or_its_spend_is_never_metered(self, client):
        """usage_events.user_id is NOT NULL, so `_meter` writes no row at all
        without a uid -- the router's own spend would vanish from the profit
        report while still being paid for upstream."""
        with _Env(pool=[CHEAP, EXPENSIVE], router=EXPENSIVE) as env:
            assert _post(client, mode='router').status_code == 200
        assert env.llm_route.await_args.kwargs.get('uid') == UID

    def test_a_router_pick_is_served_and_reported(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], router=EXPENSIVE) as env:
            resp = _post(client, mode='router')
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Mode'] == 'router'
        assert resp.headers['X-Smart-Model'] == 'sanjab/expensive'
        assert env.reserved_toman() == sr.estimate_cost_toman(EXPENSIVE) == 12_800


# ── 3. The response reports what RAN, not what was asked ─────────────────

class TestTheReportedModeIsWhatActuallyRan:
    def test_a_declining_router_falls_back_and_reports_auto(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], router=None) as env:
            resp = _post(client, mode='router')
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Mode'] == 'auto', (
            'the header must report the strategy that produced the model, '
            'not the one the client asked for'
        )
        assert resp.headers['X-Smart-Model'] == 'sanjab/cheap'
        assert env.reserved_toman() == sr.estimate_cost_toman(CHEAP)

    def test_a_declining_combo_falls_back_and_reports_auto(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], combo=None) as env:
            resp = _post(client, mode='combo:3')
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Mode'] == 'auto'
        assert resp.headers['X-Smart-Model'] == 'sanjab/cheap'
        env.select_for_combo.assert_awaited_once()

    def test_the_default_path_reports_auto(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE]):
            resp = _post(client)
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Mode'] == 'auto'

    def test_no_response_header_carries_an_upstream_name(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], router=EXPENSIVE) as env:
            resp = _post(client, mode='router')
        assert 'X-Smart-Provider' not in resp.headers
        leaked = {k: v for k, v in resp.headers.items()
                  if v.strip().lower() in {'ninerouter', 'omniroute', 'litellm', 'bynara'}}
        assert not leaked, f'upstream name leaked in response headers: {leaked}'


# ── 4. Every pick is priced through estimate_cost_toman ──────────────────

class TestEveryPickIsPricedTheSameWay:
    def test_a_combo_pick_is_priced_on_the_model_not_a_flat_number(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], combo=EXPENSIVE) as env:
            resp = _post(client, mode='combo:3')
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Mode'] == 'combo:3'
        assert env.reserved_toman() == sr.estimate_cost_toman(EXPENSIVE) == 12_800, (
            'a combo pick reserved a flat number instead of what the model '
            'costs -- the loss-making shape the product rule forbids'
        )
        assert env.billing.reserve.await_args.kwargs['model'] == 'up/expensive'

    def test_a_router_pick_is_priced_on_the_model_not_a_flat_number(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], router=EXPENSIVE) as env:
            assert _post(client, mode='router').status_code == 200
        assert env.reserved_toman() == sr.estimate_cost_toman(EXPENSIVE) == 12_800

    def test_the_reserved_amount_is_an_integer_toman(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], combo=EXPENSIVE) as env:
            assert _post(client, mode='combo:3').status_code == 200
            money = env.billing.reserve.await_args.args[1]
        assert isinstance(money.toman, int) and not isinstance(money.toman, bool)


# ── 5. A combo belongs to its owner (real SQL) ───────────────────────────

class TestComboOwnership:
    def test_the_users_own_combo_is_served(self, client):
        db = _SessionFactory()
        with _Env(pool=[CHEAP, EXPENSIVE], combo_db=db) as env:
            resp = _post(client, mode='combo:1')
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Mode'] == 'combo:1'
        assert resp.headers['X-Smart-Model'] == 'sanjab/expensive'
        assert env.reserved_toman() == 12_800

    def test_another_users_combo_is_not_usable(self, client):
        """Combo 4 belongs to user 7; the request is user 42's. The rules
        must answer instead -- and the header must not claim combo:4."""
        db = _SessionFactory()
        with _Env(pool=[CHEAP, EXPENSIVE], combo_db=db) as env:
            resp = _post(client, mode='combo:4')
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Model'] == 'sanjab/cheap', (
            "another user's combo picked the model"
        )
        assert resp.headers['X-Smart-Mode'] == 'auto'
        assert env.reserved_toman() == sr.estimate_cost_toman(CHEAP)

    def test_a_disabled_combo_falls_back_to_the_rules(self, client):
        db = _SessionFactory()
        with _Env(pool=[CHEAP, EXPENSIVE], combo_db=db):
            resp = _post(client, mode='combo:2')
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Model'] == 'sanjab/cheap'
        assert resp.headers['X-Smart-Mode'] == 'auto'

    def test_an_unknown_combo_id_falls_back_to_the_rules(self, client):
        db = _SessionFactory()
        with _Env(pool=[CHEAP, EXPENSIVE], combo_db=db):
            resp = _post(client, mode='combo:987654321')
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Mode'] == 'auto'

    def test_select_for_combo_is_handed_the_authenticated_uid(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], combo=EXPENSIVE) as env:
            assert _post(client, mode='combo:3').status_code == 200
        assert env.select_for_combo.await_args.args[0] == UID
        assert env.select_for_combo.await_args.args[1] == 3


# ── 6. What mode must NOT change ─────────────────────────────────────────

class TestModeDoesNotDisturbTheRestOfThePath:
    def test_a_forced_model_outranks_the_mode_header(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], router=EXPENSIVE, combo=EXPENSIVE) as env, \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='up/cheap')), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)):
            resp = _post(client, mode='router', headers={'X-Smart-Model': 'sanjab/cheap'})
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Model'] == 'sanjab/cheap'
        assert resp.headers['X-Smart-Mode'] == 'auto'
        env.llm_route.assert_not_awaited()
        env.select_for_combo.assert_not_awaited()

    def test_an_empty_pool_still_refuses_honestly_under_every_mode(self, client):
        for mode in (None, 'router', 'combo:1'):
            with _Env(pool=[], combo=None, router=None) as env:
                resp = _post(client, mode=mode)
            assert resp.status_code == 503, (mode, resp.text)
            assert 'حالت هوشمند' in resp.json()['detail']
            assert 'X-Smart-Mode' not in resp.headers
            env.billing.reserve.assert_not_awaited()
            assert env.http.post.await_count == 0

    def test_the_gates_still_receive_the_resolved_provider_model_id(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], combo=EXPENSIVE) as env:
            assert _post(client, mode='combo:3').status_code == 200
        assert env.free_tier.await_args.args[1] == ['up/expensive']
        assert env.premium.await_args.args[1] == ['up/expensive']

    def test_the_free_tier_gate_still_blocks_a_combo_pick(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE], combo=EXPENSIVE) as env:
            env.free_tier.return_value = {'reason': 'quota'}
            resp = _post(client, mode='combo:3')
        assert resp.status_code != 200
        env.billing.reserve.assert_not_awaited()
        assert env.http.post.await_count == 0

    def test_the_stream_path_reports_the_mode_that_actually_ran(self, client):
        """The browser only ever takes the stream path -- it reads no
        response headers at all, and the Next proxy rebuilds the response
        without them -- so the non-stream `X-Smart-Mode` header alone would
        leave the UI unable to say which strategy ran. `smart_mode` is now
        handed to chat_stream._smart_chat_stream, which puts it in the
        `smart_info` SSE event the frontend already listens for.

        This test previously asserted the OPPOSITE (`kwargs == ['display_model']`),
        pinning the stream as deliberately unwired while chat_stream.py was
        out of that packet's scope. The senior owns that file and wired it;
        the assertion is inverted rather than deleted, because the claim it
        guards -- the stream reports the mode through exactly one channel,
        not a smuggled second one -- is the same claim either way.
        """
        with _Env(pool=[CHEAP, EXPENSIVE], combo=EXPENSIVE) as env:
            _post(client, mode='combo:3', stream=True)
        env.stream.assert_awaited()
        assert sorted(env.stream.await_args.kwargs) == ['display_model', 'smart_mode']
        assert env.stream.await_args.kwargs['smart_mode'] == 'combo:3'
        assert env.stream.await_args.args[2] == 'up/expensive'

    def test_the_stream_reports_auto_when_the_combo_declines(self, client):
        """Same rule as the header: report what ran, not what was asked."""
        with _Env(pool=[CHEAP, EXPENSIVE], combo=None) as env:
            _post(client, mode='combo:3', stream=True)
        assert env.stream.await_args.kwargs['smart_mode'] == 'auto'


# ── 7. Import shape ──────────────────────────────────────────────────────

_IMPORT_ORDERS = [
    ('chat-first', 'import chat, services.smart_router, chat_smart'),
    ('router-first', 'import services.smart_router, chat, chat_smart'),
    ('mode-first', 'import chat_smart_mode'),
]


@pytest.mark.parametrize('label,stmt', _IMPORT_ORDERS, ids=[o[0] for o in _IMPORT_ORDERS])
def test_every_import_order_resolves_the_mode_module(label, stmt):
    """The router-first order is the trap: services.smart_router imports
    chat, chat.py's last line imports chat_smart, and chat_smart imports
    chat_smart_mode -- which must not, at that moment, pull in
    services.smart_router_llm and its `from services.smart_router import
    Candidate`. The `_llm_route` call below proves the deferred import
    resolves once everything has finished executing."""
    env = {**os.environ,
           'ADMIN_TOKEN': os.environ.get('ADMIN_TOKEN', 'test-admin-token'),
           'API_KEY_PEPPER': os.environ.get('API_KEY_PEPPER', 'test-api-key-pepper')}
    program = (
        stmt + '\n'
        'import asyncio, sys\n'
        'import chat_smart, chat_smart_mode, services.smart_router as sr\n'
        'assert chat_smart.chat_smart_mode is chat_smart_mode\n'
        'assert chat_smart_mode.smart_router is sr\n'
        'assert chat_smart_mode.parse_mode("combo:5") == ("combo", 5)\n'
        'assert asyncio.run(chat_smart_mode._llm_route("hi", [], 0, uid=1)) is None\n'
        'assert "services.smart_router_llm" in sys.modules\n'
    )
    proc = subprocess.run([sys.executable, '-c', program], cwd=str(_BACKEND),
                          env=env, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, f'import order {label} failed:\n{proc.stderr}'


def test_the_llm_router_is_never_imported_at_module_scope():
    # Unindented, i.e. module scope, is the failure -- the import inside
    # `_llm_route` is indented and is the whole point.
    assert not re.search(r'^(import|from) services\.smart_router_llm', _MODE_SOURCE, re.M), (
        'services.smart_router_llm must be imported inside the function: it '
        'from-imports services.smart_router, which is only half-initialised '
        'when the router-first order reaches this module.'
    )
    assert re.search(r'^\s+import services\.smart_router_llm', _MODE_SOURCE, re.M)
    assert 'import services.smart_router as smart_router' in _MODE_SOURCE
    assert not re.search(r'^\s*from services\.smart_router import', _MODE_SOURCE, re.M)
