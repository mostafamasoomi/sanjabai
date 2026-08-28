"""Smart Mode's auto-selection, end to end from a fake catalog.

HISTORY, because this file's name and its assertions no longer match.
Hotfix H patched a live outage: `_select_smart_model`'s six hardcoded ids
were ALL unservable, and the rescue path answered with `_DEFAULT_MODEL` --
a member of the very set it had just rejected -- so 32/32 category x
balance combinations landed on an id that 404s upstream. The emergency
patch added `_cheapest_live_model`, a one-row "cheapest priced+probed
catalog row" lookup, and this file pinned its SQL, its cache and its
wiring.

That whole mechanism is now DELETED and superseded by
services/smart_router.py (`candidate_pool` + `select_by_rules`), which
does the same job for the whole pool instead of one row, with its own
tests (tests/test_smart_router.py, including the SQL predicates this file
used to assert as strings -- against a real SQLite database rather than a
substring match).

So this file keeps only the claims that OUTLIVED the hotfix, and it makes
them end to end through `/v1/smart-chat` against a fake catalog rather
than against a deleted helper:

  1. The label the user sees is the public_id, never the provider route.
  2. The reservation is priced on the model's real per-million rates.
  3. A DB that cannot answer does not raise -- and, unlike Hotfix H, does
     not answer with a guessed model id either.

Assertions about the deleted helper's own mechanics (its cache TTL, its
"return the stale cache" behaviour, its last-resort return of
`_DEFAULT_MODEL`) are gone: the first two moved to
tests/test_smart_router.py with the code, and the third is now the exact
defect being removed. tests/test_smart_chat_v2_gates.py covers the gate
order, the empty-pool refusal and the provider-leak rule.

Style mirrors tests/test_web_search.py (module-level patches on `chat`
bypassing auth/billing/routing so only the code under test runs).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import chat_smart as chat_smart_mod
import database as _db
import services.smart_router as sr


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def _reset_pool_cache():
    """The router's pool cache is module-level global state -- reset it
    around every test so one test's pool can't leak into the next."""
    sr._pool_cache = []
    sr._pool_cache_at = 0.0
    yield
    sr._pool_cache = []
    sr._pool_cache_at = 0.0


# ── A fake catalog behind the router's real SQL ──────────────────────────
#
# The pool query is executed for real (its string is asserted against a
# live SQLite database in tests/test_smart_router.py); here the session
# just replays catalog rows, so what is under test is chat_smart.py's
# wiring: which row it routes to, what it calls the row, and what it
# reserves for it.

def _catalog_row(**kwargs):
    fields = dict(provider_model_id='up/cheap', public_id='sanjab/cheap',
                  input_per_million=2_000_000, output_per_million=3_000_000,
                  context_window=128_000, upstream='bynara')
    fields.update(kwargs)
    return SimpleNamespace(**fields)


_CHEAP_ROW = _catalog_row()


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, rows=None, raises=False):
        self.rows = rows if rows is not None else []
        self.raises = raises
        self.sql: list[str] = []

    async def execute(self, stmt, *a, **k):
        self.sql.append(str(stmt))
        if self.raises:
            raise RuntimeError('database is on fire')
        return _Result(self.rows)

    async def commit(self):
        """The reservation block commits its own session; without this the
        route falls through to its legacy quota path and the reservation
        assertions below would be testing the wrong branch."""
        return None


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *a):
        return False


def _maker(session):
    return MagicMock(return_value=_Ctx(session))


AUTH_HEADERS = {'Authorization': 'Bearer test-token'}


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


class _SmartChatEnv:
    """Bypasses auth/free-tier/premium/entitlement/routing and points the
    router's pool query at `session`."""

    def __init__(self, session):
        self.billing = MagicMock()
        self.billing.reserve = AsyncMock(return_value={'reservation_id': 'test-reservation'})
        self.billing.release = AsyncMock(return_value=None)
        self.billing.settle = AsyncMock(return_value=None)
        self.http = _patched_http()
        self._patches = (
            patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)),
            patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)),
            patch.object(chat_mod, 'premium_check_and_consume', AsyncMock(return_value=None)),
            patch.object(chat_mod, 'BillingService', MagicMock(return_value=self.billing)),
            patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())),
            patch.object(chat_mod, 'async_session', _maker(session)),
            patch.object(chat_smart_mod, '_get_user_balance', AsyncMock(return_value=50_000)),
            patch.object(chat_smart_mod, 'covering_entitlement', AsyncMock(return_value=None)),
            patch.object(chat_smart_mod, 'covers_request', AsyncMock(return_value=False)),
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


def _post(client):
    return client.post(
        '/v1/smart-chat',
        json={'model': 'auto', 'messages': [{'role': 'user', 'content': 'سلام'}],
              'stream': False},
        headers=AUTH_HEADERS,
    )


# ── 1. The label the user sees (KEPT from Hotfix H) ──────────────────────

class TestTheUserSeesThePublicId:
    """KEPT: Hotfix H's claim that an auto-selected model is labelled by
    public_id and never by the raw provider route still holds word for
    word -- only the source of the pick changed."""

    def test_label_is_the_public_id_not_the_provider_model_id(self, client):
        with _SmartChatEnv(_Session([_CHEAP_ROW])):
            resp = _post(client)
        assert resp.status_code == 200, resp.text
        assert resp.headers['X-Smart-Model'] == 'sanjab/cheap'
        assert resp.headers['X-Smart-Model'] != 'up/cheap'

    def test_no_response_header_carries_the_upstream_name(self, client):
        """The route is not the user's business -- the upstream on the
        chosen row is 'bynara' and must appear in no header."""
        with _SmartChatEnv(_Session([_CHEAP_ROW])):
            resp = _post(client)
        assert resp.status_code == 200, resp.text
        assert 'bynara' not in ' '.join(resp.headers.values())


# ── 2. The reservation price (KEPT from Hotfix H, retargeted) ────────────

class TestReservationTracksTheRealRates:
    """KEPT: Hotfix H's claim that the reservation must reflect the chosen
    model's real per-million rates, not a flat constant. The arithmetic now
    lives in smart_router.estimate_cost_toman, so this asserts against that
    single source of truth instead of re-deriving it."""

    def test_reservation_is_priced_on_the_chosen_rows_rates(self, client):
        with _SmartChatEnv(_Session([_CHEAP_ROW])) as env:
            resp = _post(client)
        assert resp.status_code == 200, resp.text
        env.billing.reserve.assert_awaited()
        money = env.billing.reserve.await_args.args[1]
        expected = (2000 * 2_000_000 + 800 * 3_000_000) // 1_000_000
        assert money.toman == expected == 6400
        # Money is integer Toman, never a float and never a rial detour.
        assert isinstance(money.toman, int)

    def test_a_dearer_row_reserves_more(self, client):
        """Sanity that the price branch is live: swapping the catalog row
        for a dearer one must move the reserved amount, or the assertion
        above could pass against a constant."""
        dear = _catalog_row(provider_model_id='up/dear', public_id='sanjab/dear',
                            input_per_million=4_000_000, output_per_million=6_000_000)
        with _SmartChatEnv(_Session([dear])) as env:
            resp = _post(client)
        assert resp.status_code == 200, resp.text
        money = env.billing.reserve.await_args.args[1]
        assert money.toman == 12_800
        # The flat number this replaces, which under-reserved every dear model.
        assert money.toman != 1000 and money.toman != 5000


# ── 3. A DB that cannot answer (KEPT claim, opposite outcome) ────────────

class TestDatabaseFailureDoesNotRaise:
    """KEPT: "a DB failure does not raise" -- that claim outlived the
    hotfix. What CHANGED is the answer. Hotfix H fell through to
    `_DEFAULT_MODEL`, a hardcoded id that 404s; there is now no hardcoded
    id to fall through to, so the honest answer is a 503 that tells the
    user to pick a model manually."""

    def test_a_broken_db_refuses_instead_of_raising(self, client):
        with _SmartChatEnv(_Session(raises=True)) as env:
            resp = _post(client)
        assert resp.status_code == 503, resp.text
        assert 'حالت هوشمند' in resp.json()['detail']
        assert env.http.post.await_count == 0, 'no upstream call on a refusal'
        env.billing.reserve.assert_not_awaited()

    def test_an_empty_catalog_refuses_rather_than_guessing_an_id(self, client):
        with _SmartChatEnv(_Session([])) as env:
            resp = _post(client)
        assert resp.status_code == 503, resp.text
        env.billing.reserve.assert_not_awaited()

    def test_an_unbound_session_refuses_rather_than_raising(self, client):
        with _SmartChatEnv(_Session([])), \
             patch.object(chat_mod, 'async_session', None):
            resp = _post(client)
        assert resp.status_code == 503, resp.text
