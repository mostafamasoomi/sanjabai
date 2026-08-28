"""Smart Mode v2: chat_smart.py routed through services/smart_router.py.

What this file pins, and why each one exists:

  1. IMPORT SHAPE. `services/smart_router.py` does `import chat` at module
     scope and chat.py imports chat_smart.py at its last line, so importing
     the router FIRST re-enters a half-initialised module. A
     `from services.smart_router import candidate_pool` there raises
     ImportError; a module import does not. Both orders are run in a real
     subprocess here because that failure only exists at import time.

  2. NO HARDCODED MODEL LIST. The six ids in the deleted `_FREE_MODELS` /
     `_CODING_MODELS` / `_REASONING_MODELS` / `_CREATIVE_MODELS` /
     `_DEFAULT_MODEL` tuples are all unservable, and every category x
     balance combination landed on one of them and 404'd -- that is the
     production outage this rewrite closes. Reintroducing any of them, in
     any form, is the defect.

  3. THE EMPTY POOL REFUSES. `select_by_rules` returns None when there is
     nothing servable. The old code answered that with a hardcoded model
     id, which is exactly how a 404-ing model reached every user. It must
     be an honest Persian 503 instead, with no reservation and no upstream
     call.

  4. THE RESERVATION IS PRICED ON THE MODEL. It used to be a flat
     1000/5000 Toman with no relation to any price -- measured against the
     live catalog, sanjab/claude-fable-5 needs 11,436 Toman reserved and
     was getting 1,000.

  5. NO UPSTREAM LEAK. The response used to carry the raw upstream name in
     a header. A normal user never sees a provider or a route; only an
     admin does.

  6. GATE ORDER. preflight -> selection -> free-tier -> premium -> reserve,
     unchanged, with the gates taking the resolved provider_model_id and
     the client seeing only the public_id.

Style mirrors tests/test_web_search.py (module-level patches on `chat`
bypassing auth/billing/routing so only the code under test runs) and
tests/test_premium_quota_wiring.py (source scan for the ordering rule,
because a mock-driven test cannot prove a call site's position).
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import chat_smart as chat_smart_mod
import database as _db
import services.smart_router as sr

_BACKEND = Path(__file__).resolve().parents[1]
_SOURCE = (_BACKEND / 'chat_smart.py').read_text()

AUTH_HEADERS = {'Authorization': 'Bearer test-token'}


@pytest.fixture
def anyio_backend():
    return 'asyncio'


# ── Hand-built candidates ────────────────────────────────────────────────
#
# Rates are per million tokens, integer Toman, in the same order of
# magnitude as the live catalog. `estimate_cost_toman` charges a
# representative 2000-in/800-out turn, so:
#   cheap      -> (2000*50_000  + 800*150_000)  // 1e6 = 220 -> floored 1000
#   expensive  -> (2000*4_000_000 + 800*6_000_000) // 1e6 = 12,800
# i.e. the expensive model needs 12.8x the cheap one, and 2.5x the flat
# 5000 the old code would have reserved for either of them.

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


def _upstream_response(body=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=body or {'choices': [{'message': {'content': 'پاسخ نمونه'}}]})
    resp.content = b'{}'
    return resp


def _patched_http(capture: dict | None = None):
    fake = MagicMock()
    if capture is None:
        fake.post = AsyncMock(return_value=_upstream_response())
    else:
        async def _post(url, json=None, headers=None, timeout=None):
            capture['json'] = json
            capture['url'] = url
            return _upstream_response()
        fake.post = AsyncMock(side_effect=_post)
    return fake


class _Env:
    """Bypasses auth/free-tier/premium/entitlement/routing and records what
    the gates and the billing service were handed."""

    def __init__(self, pool, pick='__rules__', balance=50_000):
        self.billing = MagicMock()
        self.billing.reserve = AsyncMock(return_value={'reservation_id': 'r1'})
        self.billing.release = AsyncMock(return_value=None)
        self.billing.settle = AsyncMock(return_value=None)
        self.free_tier = AsyncMock(return_value=None)
        self.premium = AsyncMock(return_value=None)
        self.http = _patched_http()
        self.stream = AsyncMock(return_value=MagicMock())
        select = (sr.select_by_rules if pick == '__rules__'
                  else MagicMock(return_value=pick))
        self._patches = (
            patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)),
            patch.object(chat_mod, 'check_and_consume', self.free_tier),
            patch.object(chat_mod, 'premium_check_and_consume', self.premium),
            patch.object(chat_mod, 'BillingService', MagicMock(return_value=self.billing)),
            patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())),
            patch.object(chat_mod, '_smart_chat_stream', self.stream),
            patch.object(chat_smart_mod, 'covering_entitlement', AsyncMock(return_value=None)),
            patch.object(chat_smart_mod, 'covers_request', AsyncMock(return_value=False)),
            patch.object(chat_smart_mod, '_get_user_balance', AsyncMock(return_value=balance)),
            patch.object(sr, 'candidate_pool', AsyncMock(return_value=pool)),
            patch.object(sr, 'select_by_rules', select),
            patch.object(_db, '_real_http', self.http),
        )
        self._entered = []

    def __enter__(self):
        for p in self._patches:
            self._entered.append(p.start())
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False


def _post(client, headers=None, stream=False, content='سلام'):
    return client.post(
        '/v1/smart-chat',
        json={'model': 'auto', 'messages': [{'role': 'user', 'content': content}],
              'stream': stream},
        headers={**AUTH_HEADERS, **(headers or {})},
    )


# ── 1. Import shape ──────────────────────────────────────────────────────

# Both orders are real, not hypothetical: app.py reaches chat_smart through
# chat.py, while anything importing the router directly (a script, another
# service module, a test) hits the other order.
_IMPORT_ORDERS = [
    ('chat-first', 'import chat, services.smart_router, chat_smart'),
    ('router-first', 'import services.smart_router, chat, chat_smart'),
]


@pytest.mark.parametrize('label,stmt', _IMPORT_ORDERS, ids=[o[0] for o in _IMPORT_ORDERS])
def test_both_import_orders_resolve_the_same_router_module(label, stmt):
    env = {**os.environ,
           'ADMIN_TOKEN': os.environ.get('ADMIN_TOKEN', 'test-admin-token'),
           'API_KEY_PEPPER': os.environ.get('API_KEY_PEPPER', 'test-api-key-pepper')}
    program = (
        stmt + '\n'
        'import chat_smart, services.smart_router as sr\n'
        'assert chat_smart.smart_router is sr, "chat_smart bound a different module"\n'
        'assert callable(chat_smart.smart_router.candidate_pool)\n'
        'assert chat_smart.smart_chat.__module__ == "chat_smart"\n'
    )
    proc = subprocess.run([sys.executable, '-c', program], cwd=str(_BACKEND),
                          env=env, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, f'import order {label} failed:\n{proc.stderr}'


def test_the_router_is_imported_as_a_module_not_by_name():
    """A `from services.smart_router import ...` here is an ImportError the
    moment anything imports the router before chat.py -- see the module
    docstring. This is the cheap, fast guard on top of the subprocess ones."""
    assert 'import services.smart_router as smart_router' in _SOURCE
    assert not re.search(r'^\s*from services\.smart_router import', _SOURCE, re.M), (
        'chat_smart.py must not from-import services.smart_router: the '
        'router imports chat, and chat imports chat_smart, so the names are '
        'not bound yet when the router is imported first.'
    )


# ── 2. The hardcoded lists are gone ──────────────────────────────────────

# Deliberately spelled out once, in one place, so the grep that audits this
# rewrite has exactly one hit per name in the test tree and it is this
# assertion that they are ABSENT.
_DELETED_NAMES = (
    '_FREE_MODELS', '_CODING_MODELS', '_REASONING_MODELS', '_CREATIVE_MODELS',
    '_DEFAULT_MODEL', '_select_smart_model', '_select_smart_model_safe',
    '_CheapestModel', '_CHEAPEST_MODEL_SQL', '_cheapest_live_model',
    '_CHEAPEST_CACHE_TTL_SECONDS', '_cheapest_cache',
)


@pytest.mark.parametrize('name', _DELETED_NAMES)
def test_the_hardcoded_selection_machinery_is_gone(name):
    assert not hasattr(chat_smart_mod, name), (
        f'chat_smart.{name} is back. Every id those lists named is '
        f'unservable; selection belongs to services/smart_router.py.'
    )


def _code_string_literals(src: str) -> list[str]:
    """Every string literal in the module EXCEPT docstrings, and comments
    are invisible to `ast` entirely. A prose mention of a dead model id
    (chat_smart.py explains the old slash-split bug using one) is not a
    hardcoded id; a literal in executable code is."""
    tree = ast.parse(src)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, 'body', None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings]


def test_no_model_id_literal_is_hardcoded_in_the_selection_path():
    """The specific ids that took Smart Mode down must not reappear as a
    default, a fallback or a seed."""
    literals = _code_string_literals(_SOURCE)
    for dead_id in ('tencent-hy3', 'deepseek-v4-pro', 'deepseek-v4-flash-bynara',
                    'mistral-large', 'mistral-medium-3-5', 'mimo-v2.5-pro'):
        hits = [lit for lit in literals if dead_id in lit]
        assert not hits, f'{dead_id} is hardcoded in chat_smart.py again: {hits}'


# ── 3. Empty pool -> honest 503, never a guessed model ───────────────────

class TestNoCandidateRefusesHonestly:
    def test_empty_pool_answers_503_in_persian(self, client):
        with _Env(pool=[]) as env:
            resp = _post(client)
        assert resp.status_code == 503, resp.text
        body = resp.json()
        assert 'حالت هوشمند' in body['detail'], body
        assert 'دستی' in body['detail'], 'the refusal must invite a manual model choice'
        assert body['detail_en'], 'the English sibling must be filled in'
        assert env.http.post.await_count == 0, 'no upstream call on a refusal'

    def test_empty_pool_opens_no_reservation(self, client):
        with _Env(pool=[]) as env:
            resp = _post(client)
        assert resp.status_code == 503
        env.billing.reserve.assert_not_awaited()

    def test_a_none_pick_over_a_non_empty_pool_still_refuses(self, client):
        """`select_by_rules` swallows its own exceptions and returns None.
        A non-empty pool must not tempt the caller into picking for it."""
        with _Env(pool=[CHEAP, EXPENSIVE], pick=None) as env:
            resp = _post(client)
        assert resp.status_code == 503, resp.text
        env.billing.reserve.assert_not_awaited()
        assert env.http.post.await_count == 0


# ── 4. The reservation is priced on the chosen model ─────────────────────

def _reserved_toman(env) -> int:
    env.billing.reserve.assert_awaited()
    money = env.billing.reserve.await_args.args[1]
    return money.toman


class TestReservationIsPricedOnTheModel:
    def test_expensive_model_reserves_materially_more_than_a_cheap_one(self, client):
        with _Env(pool=[CHEAP], pick=CHEAP) as cheap_env:
            assert _post(client, content='سلام').status_code == 200
            cheap = _reserved_toman(cheap_env)
        with _Env(pool=[EXPENSIVE], pick=EXPENSIVE) as dear_env:
            assert _post(client, content='سلام').status_code == 200
            dear = _reserved_toman(dear_env)

        assert cheap == sr.estimate_cost_toman(CHEAP) == 1000
        assert dear == sr.estimate_cost_toman(EXPENSIVE) == 12_800
        assert dear > 10 * cheap, (
            f'expensive model reserved {dear} vs cheap {cheap} -- the '
            f'reservation is not tracking the model price'
        )
        # The flat number this replaces. The dearest model was reserving a
        # fraction of what it costs, which is the loss-making shape the
        # product rule forbids.
        assert dear > 5000

    def test_the_reserved_amount_is_an_integer_toman(self, client):
        with _Env(pool=[EXPENSIVE], pick=EXPENSIVE) as env:
            assert _post(client).status_code == 200
            money = env.billing.reserve.await_args.args[1]
        assert isinstance(money.toman, int) and not isinstance(money.toman, bool)
        assert money.toman == 12_800

    def test_reserve_is_told_the_provider_model_id_not_the_label(self, client):
        with _Env(pool=[EXPENSIVE], pick=EXPENSIVE) as env:
            assert _post(client).status_code == 200
        assert env.billing.reserve.await_args.kwargs['model'] == 'up/expensive'

    def test_forced_model_present_in_the_pool_is_priced_on_its_real_rates(self, client):
        with _Env(pool=[CHEAP, EXPENSIVE]) as env, \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='up/expensive')), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)):
            resp = _post(client, headers={'X-Smart-Model': 'sanjab/expensive'})
        assert resp.status_code == 200, resp.text
        assert _reserved_toman(env) == 12_800

    def test_forced_model_absent_from_the_pool_falls_back_to_the_flat_estimate(self, client):
        """Only this branch may use the old flat number, and only because
        an unpriced model has no rate to price on."""
        with _Env(pool=[CHEAP]) as env, \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='up/unknown')), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)):
            resp = _post(client, headers={'X-Smart-Model': 'sanjab/unknown'})
        assert resp.status_code == 200, resp.text
        assert _reserved_toman(env) == 1000


# ── 5. No upstream leak in the response headers ──────────────────────────

# Spelled once, here, for the same reason as _DELETED_NAMES above: this is
# the assertion that the header is ABSENT.
_FORBIDDEN_PROVIDER_HEADER = 'X-Smart-Provider'

_UPSTREAM_NAMES = {'ninerouter', 'omniroute', 'litellm', 'bynara', 'bynara2', 'ag', 'cc'}


class TestNoProviderLeak:
    def test_no_provider_header_is_sent(self, client):
        with _Env(pool=[EXPENSIVE], pick=EXPENSIVE):
            resp = _post(client)
        assert resp.status_code == 200, resp.text
        assert _FORBIDDEN_PROVIDER_HEADER not in resp.headers, (
            'the upstream name is back in the response headers -- /v1/* is '
            'served straight from the backend, so every API-key holder sees it'
        )

    def test_no_response_header_value_is_an_upstream_name(self, client):
        with _Env(pool=[EXPENSIVE], pick=EXPENSIVE):
            resp = _post(client)
        assert resp.status_code == 200, resp.text
        leaked = {k: v for k, v in resp.headers.items()
                  if v.strip().lower() in _UPSTREAM_NAMES}
        assert not leaked, f'upstream name leaked in response headers: {leaked}'

    def test_the_source_sets_no_provider_header(self):
        setters = [ln for ln in _SOURCE.splitlines()
                   if 'headers[' in ln and 'Provider' in ln]
        assert not setters, f'provider header set in chat_smart.py: {setters}'


# ── 6. Labelling, gates and gate order ───────────────────────────────────

class TestLabellingAndGates:
    def test_the_client_sees_the_public_id_never_the_route(self, client):
        with _Env(pool=[EXPENSIVE], pick=EXPENSIVE):
            resp = _post(client)
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Model'] == 'sanjab/expensive'
        assert resp.headers['X-Smart-Model'] != 'up/expensive'
        assert resp.headers['X-Smart-Category'] == 'greeting'

    def test_the_upstream_call_uses_the_provider_model_id(self, client):
        capture: dict = {}
        with _Env(pool=[EXPENSIVE], pick=EXPENSIVE) as env:
            env.http.post = _patched_http(capture).post
            resp = _post(client)
        assert resp.status_code == 200, resp.text
        assert capture['json']['model'] == 'up/expensive'

    def test_the_stream_path_is_handed_the_public_id_as_display_model(self, client):
        with _Env(pool=[EXPENSIVE], pick=EXPENSIVE) as env:
            _post(client, stream=True)
        env.stream.assert_awaited()
        assert env.stream.await_args.kwargs['display_model'] == 'sanjab/expensive'
        assert env.stream.await_args.args[2] == 'up/expensive', (
            'the stream must be routed on the provider_model_id'
        )

    def test_both_quota_gates_receive_the_resolved_provider_model_id(self, client):
        with _Env(pool=[EXPENSIVE], pick=EXPENSIVE) as env:
            assert _post(client).status_code == 200
        assert env.free_tier.await_args.args[1] == ['up/expensive']
        assert env.premium.await_args.args[1] == ['up/expensive']

    def test_the_free_tier_gate_still_blocks(self, client):
        """Selection running first must not have moved the gate off the
        path -- a blocked request reserves nothing."""
        with _Env(pool=[EXPENSIVE], pick=EXPENSIVE) as env:
            env.free_tier.return_value = {'reason': 'quota'}
            resp = _post(client)
        assert resp.status_code != 200
        env.billing.reserve.assert_not_awaited()
        assert env.http.post.await_count == 0


# `premium_check_and_consume` contains `check_and_consume`, so the free-tier
# pattern has to refuse to match it -- the same trap tests/
# test_premium_quota_wiring.py documents.
_GATE_ORDER = [
    ('preflight', re.compile(r'_chat_preflight\(')),
    ('selection', re.compile(r'smart_router\.candidate_pool\(')),
    ('free-tier', re.compile(r'(?<!premium_)check_and_consume\(\s*uid')),
    ('premium', re.compile(r'premium_check_and_consume\(\s*uid')),
    ('reserve', re.compile(r'\.reserve\(')),
]


def test_gate_order_is_preflight_selection_freetier_premium_reserve():
    """A source scan, because the whole class of bug here is a call site in
    the wrong place and a mock cannot prove position. A rejection must leave
    no reservation to unwind, and selection must precede the two gates
    because both are priced on the resolved model."""
    lines = _SOURCE.splitlines()
    seen = []
    for name, pattern in _GATE_ORDER:
        at = next((i for i, ln in enumerate(lines) if pattern.search(ln)), None)
        assert at is not None, f'chat_smart.py: no {name} call site found'
        seen.append((name, at + 1))
    assert seen == sorted(seen, key=lambda p: p[1]), (
        f'gate order broken, found at lines: {seen}'
    )
