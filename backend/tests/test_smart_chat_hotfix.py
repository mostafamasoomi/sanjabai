"""Hotfix H: smart-mode's auto-selection rescue path.

Measured against the live DB before this fix: `_select_smart_model`'s six
hardcoded ids are ALL unservable (two have zero `model_catalog` rows, four
are `disabled`/`maintenance`), and `_select_smart_model_safe`'s rescue path
returned `_DEFAULT_MODEL` -- a member of the very set it had just rejected
-- unchecked. 32/32 category x balance combinations landed on
`('tencent-hy3', 'bynara')`, and that id 404s on the live LiteLLM proxy.

This file covers, in order:
  1. `_cheapest_live_model`'s SQL shape (string-level, since the DB is
     mocked here -- a real Postgres never runs these predicates in CI) and
     its cache/never-raises behaviour.
  2. `_select_smart_model_safe`'s fallback wiring.
  3. The end-to-end `/v1/smart-chat` response: the label the user sees and
     the price the reservation opens for, when the fallback fires.

Style mirrors tests/test_admin_probe_gate.py (hand-rolled async session
double recording SQL) and tests/test_web_search.py (module-level patches on
`chat` bypassing auth/billing/routing so only the code under test runs).
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import chat_smart as chat_smart_mod
import database as _db
from tests.conftest import make_row


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def _reset_cheapest_cache():
    """The cache is module-level global state -- reset it around every test
    so one test's cached row can't leak into the next."""
    chat_smart_mod._cheapest_cache = None
    chat_smart_mod._cheapest_cache_at = 0.0
    yield
    chat_smart_mod._cheapest_cache = None
    chat_smart_mod._cheapest_cache_at = 0.0


# ── A hand-rolled async session double, same shape as test_admin_probe_gate
# ── and test_margin_guard's `_Session`: records the SQL it was given and
# ── replays a queued row (or raises).

class _Session:
    def __init__(self, rows=None, raises=False):
        self.rows = rows if rows is not None else []
        self.raises = raises
        self.sql = []

    async def execute(self, stmt, *a, **k):
        self.sql.append(str(stmt))
        if self.raises:
            raise RuntimeError('database is on fire')
        result = MagicMock()
        result.fetchone.return_value = self.rows[0] if self.rows else None
        return result


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *a):
        return False


def _maker(session):
    return MagicMock(return_value=_Ctx(session))


def _row(**kwargs):
    defaults = dict(provider_model_id='cheap-real', public_id='cheap-public',
                     input_per_million=200, output_per_million=600, upstream='bynara')
    defaults.update(kwargs)
    return make_row(**defaults)


# ── 1. _cheapest_live_model ──────────────────────────────────────────────

@pytest.mark.anyio
class TestCheapestLiveModelQuery:
    """String-level assertions on the SQL predicates/ordering -- the double
    above never runs real Postgres, so a wrong predicate can only be caught
    here as a query-shape check, exactly like
    test_admin_probe_gate.py's 'last_ok_at IS NOT NULL' assertions."""

    async def test_unpriced_predicate_is_gt_zero_not_is_not_null(self):
        session = _Session([])
        with patch.object(chat_mod, 'async_session', _maker(session)):
            await chat_smart_mod._cheapest_live_model()
        sql = session.sql[0]
        assert 'c.input_per_million > 0' in sql
        assert 'c.output_per_million > 0' in sql

    async def test_requires_a_confirmed_live_probe(self):
        session = _Session([])
        with patch.object(chat_mod, 'async_session', _maker(session)):
            await chat_smart_mod._cheapest_live_model()
        assert 's.last_ok_at IS NOT NULL' in session.sql[0]

    async def test_requires_public_id(self):
        session = _Session([])
        with patch.object(chat_mod, 'async_session', _maker(session)):
            await chat_smart_mod._cheapest_live_model()
        assert 'c.public_id IS NOT NULL' in session.sql[0]

    async def test_ordering_blends_input_and_output_price(self):
        session = _Session([])
        with patch.object(chat_mod, 'async_session', _maker(session)):
            await chat_smart_mod._cheapest_live_model()
        assert '3 * c.input_per_million + c.output_per_million' in session.sql[0]


@pytest.mark.anyio
class TestCheapestLiveModelBehaviour:
    async def test_returns_the_row_the_db_gives(self):
        session = _Session([_row()])
        with patch.object(chat_mod, 'async_session', _maker(session)):
            result = await chat_smart_mod._cheapest_live_model()
        assert result == chat_smart_mod._CheapestModel(
            'cheap-real', 'cheap-public', 200, 600, 'bynara')

    async def test_no_row_is_none(self):
        session = _Session([])
        with patch.object(chat_mod, 'async_session', _maker(session)):
            result = await chat_smart_mod._cheapest_live_model()
        assert result is None

    async def test_db_exception_with_cold_cache_returns_none_not_raise(self):
        session = _Session([], raises=True)
        with patch.object(chat_mod, 'async_session', _maker(session)):
            result = await chat_smart_mod._cheapest_live_model()
        assert result is None

    async def test_db_exception_with_stale_cache_returns_the_cached_value(self):
        cached = chat_smart_mod._CheapestModel('old-real', 'old-public', 50, 150, 'bynara')
        chat_smart_mod._cheapest_cache = cached
        chat_smart_mod._cheapest_cache_at = time.monotonic() - 61  # force a refresh attempt
        session = _Session([], raises=True)
        with patch.object(chat_mod, 'async_session', _maker(session)):
            result = await chat_smart_mod._cheapest_live_model()
        assert result == cached
        assert session.sql, 'expected a refresh attempt against the stale cache'

    async def test_fresh_cache_is_served_without_touching_the_db(self):
        cached = chat_smart_mod._CheapestModel('c', 'p', 1, 1, 'bynara')
        chat_smart_mod._cheapest_cache = cached
        chat_smart_mod._cheapest_cache_at = time.monotonic()
        session = _Session([], raises=True)  # would raise if the DB were touched
        with patch.object(chat_mod, 'async_session', _maker(session)):
            result = await chat_smart_mod._cheapest_live_model()
        assert result == cached
        assert session.sql == []

    async def test_unbound_session_returns_cache_without_querying(self):
        chat_smart_mod._cheapest_cache = None
        with patch.object(chat_mod, 'async_session', None):
            result = await chat_smart_mod._cheapest_live_model()
        assert result is None


# ── 2. _select_smart_model_safe ──────────────────────────────────────────

@pytest.mark.anyio
class TestSelectSmartModelSafe:
    async def test_fallback_uses_the_cheapest_live_model_not_the_hardcoded_default(self):
        cheapest = chat_smart_mod._CheapestModel('cheap-real', 'cheap-public', 200, 600, 'bynara')
        with patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=False)), \
             patch.object(chat_smart_mod, '_cheapest_live_model', AsyncMock(return_value=cheapest)):
            model, provider, price_row = await chat_smart_mod._select_smart_model_safe('simple', 50000)
        assert model == 'cheap-real'
        assert model != chat_smart_mod._DEFAULT_MODEL[0]
        assert price_row == cheapest

    async def test_last_resort_still_returns_default_when_lookup_returns_none(self):
        with patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=False)), \
             patch.object(chat_smart_mod, '_cheapest_live_model', AsyncMock(return_value=None)):
            model, provider, price_row = await chat_smart_mod._select_smart_model_safe('simple', 50000)
        assert (model, provider) == chat_smart_mod._DEFAULT_MODEL
        assert price_row is None

    async def test_working_model_short_circuits_with_no_price_row(self):
        with patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)):
            model, provider, price_row = await chat_smart_mod._select_smart_model_safe('simple', 50000)
        assert price_row is None


# ── 3. End-to-end /v1/smart-chat: label + reservation price ─────────────

AUTH_HEADERS = {'Authorization': 'Bearer test-token'}

_CHEAP_ROW = chat_smart_mod._CheapestModel(
    provider_model_id='cheap-real', public_id='cheap-public',
    input_per_million=200, output_per_million=600, upstream='bynara',
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


def _patched_http():
    fake = MagicMock()
    fake.post = AsyncMock(return_value=_upstream_response())
    return fake


class TestSmartChatFallbackEndToEnd:
    """Bypasses auth/free-tier/premium/routing (same technique as
    test_web_search.py's `_bypass_pipeline`) and forces the rescue path by
    making every hardcoded id look unservable, so both requests below hit
    exactly the fallback branch this hotfix adds."""

    @pytest.fixture(autouse=True)
    def _bypass(self):
        instance = MagicMock()
        instance.reserve = AsyncMock(return_value={'reservation_id': 'test-reservation'})
        instance.release = AsyncMock(return_value=None)
        instance.settle = AsyncMock(return_value=None)
        self.billing_instance = instance
        billing_cls = MagicMock(return_value=instance)
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'BillingService', billing_cls), \
             patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=False)), \
             patch.object(chat_smart_mod, '_cheapest_live_model', AsyncMock(return_value=_CHEAP_ROW)), \
             patch.object(chat_smart_mod, 'covering_entitlement', AsyncMock(return_value=None)):
            yield

    def _post(self, client):
        with patch.object(_db, '_real_http', _patched_http()):
            return client.post(
                '/v1/smart-chat',
                json={
                    'model': 'auto',
                    'messages': [{'role': 'user', 'content': 'سلام'}],
                    'stream': False,
                },
                headers=AUTH_HEADERS,
            )

    def test_fallback_label_is_the_public_id_not_the_provider_model_id(self, client):
        resp = self._post(client)
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Model'] == 'cheap-public'
        assert resp.headers['X-Smart-Model'] != 'cheap-real'

    def test_fallback_reservation_is_priced_on_the_real_rates(self, client):
        resp = self._post(client)
        assert resp.status_code == 200, resp.text
        self.billing_instance.reserve.assert_awaited()
        money_arg = self.billing_instance.reserve.await_args.args[1]
        expected = max(1000, (2000 * 200 + 800 * 600) // 1_000_000)
        assert money_arg.toman == expected
        # Sanity: the flat estimate this replaces would have been 5000
        # (is_working_model is forced False for every id in this test) --
        # pin that the two numbers actually differ, or the price-row branch
        # could be dead and this test would pass vacuously.
        assert money_arg.toman != 5000
