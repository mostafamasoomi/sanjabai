"""Tests for the public model id indirection (migrations/0028_public_model_ids.sql).

Background: public model ids used to leak the upstream route (bynara/, kr/,
cc/, cx/, ag/, gemini-api/models/, nvidia/...) and four said "-free",
violating two product rules ("a user never sees the provider/route", "we have
no free models"). The migration adds model_catalog.public_id (e.g.
"sanjab/mistral-large") and this backend change wires it in on two sides:

  1. chat.py: `_resolve_public_model()` canonicalizes ANY incoming model
     string (public_id, provider_model_id, or the legacy `id`) to
     `provider_model_id` -- the id routing/health/billing have always used --
     exactly once, as early as possible in every chat/compare/smart-chat call
     site, before the free-tier gate/reservation/validation/upstream call.
     This is always-on (never gated by the flag below): an unresolved
     `sanjab/*` id would otherwise 502 upstream (LiteLLM/9router have never
     heard of it) AND silently overcharge, because `_record_usage`'s price
     lookup (`WHERE provider_model_id = :mid`) would miss and fall through to
     the fallback CEILING rate.

  2. content.py: `/v1/models` and `/catalog/models` (+pricing) serve
     `public_id` instead of `id`/`provider_model_id` -- gated behind
     `PUBLIC_MODEL_IDS_ENABLED` (default off, so today's behavior is
     preserved byte-for-byte until deliberately flipped on).

No test in this file makes a real network or DB call: the DB session proxy
and the outbound httpx client are always faked, following this suite's
existing conventions (see test_web_search.py's bypass fixture and
test_billing_loss_paths.py's `_FakeSession`).
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import content as content_mod
import database as _db


# ── Shared fixtures / fakes ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_resolve_cache():
    """chat._resolve_public_model caches the whole resolution table for 60s
    (same TTL pattern as chat._get_model_upstream); chat.get_working_models()
    has its own process-wide cache (_WORKING_SET_CACHE). Reset both before
    AND after every test in this file so tests never leak cached state into
    each other, or into other test files sharing this same process, and
    never pick up a stale table from a previous test's fake DB."""
    chat_mod._MODEL_RESOLVE_CACHE = {}
    chat_mod._MODEL_RESOLVE_CACHE_LOADED_AT = 0.0
    chat_mod._WORKING_SET_CACHE = None
    yield
    chat_mod._MODEL_RESOLVE_CACHE = {}
    chat_mod._MODEL_RESOLVE_CACHE_LOADED_AT = 0.0
    chat_mod._WORKING_SET_CACHE = None


# A small fake catalog mirroring migrations/0028_public_model_ids.sql's shape.
# id == provider_model_id always in this codebase (model_discovery.py's
# sync_provider upserts both from the same upstream string), public_id is
# None for rows the migration deliberately leaves unlisted (collision losers,
# or anything an admin hasn't named yet).
_FAKE_CATALOG = [
    {'id': 'bynara/mistral-large', 'provider_model_id': 'bynara/mistral-large', 'public_id': 'sanjab/mistral-large'},
    # Collision loser: a bare, pre-migration id for a degraded litellm route
    # that lost the public_id assignment to 'bynara/mistral-large' above.
    # Keeps its own id/route/price, must still work as a chat id, but must
    # never appear in public listings.
    {'id': 'mistral-large', 'provider_model_id': 'mistral-large', 'public_id': None},
    {'id': 'bynara/mimo-v2.5-free', 'provider_model_id': 'bynara/mimo-v2.5-free', 'public_id': 'sanjab/mimo-v2.5'},
    {'id': 'kr/claude-sonnet-4', 'provider_model_id': 'kr/claude-sonnet-4', 'public_id': 'sanjab/claude-sonnet-4'},
    {'id': 'tencent-hy3', 'provider_model_id': 'tencent-hy3', 'public_id': None},
    # Precedence fixture: 'sanjab/collide' is BOTH a real public_id (winning
    # row -> 'winner/collide') and the raw `id` of a completely unrelated
    # row (-> 'legacy/collide-loser'). public_id must win.
    {'id': 'sanjab/collide', 'provider_model_id': 'legacy/collide-loser', 'public_id': None},
    {'id': 'winner/collide', 'provider_model_id': 'winner/collide', 'public_id': 'sanjab/collide'},
]


def _resolve_rows(catalog):
    """Build the (key, provider_model_id) rows chat._MODEL_RESOLVE_SQL's
    `ORDER BY rnk` would produce for `catalog`: every public_id row first
    (rnk 0), then every provider_model_id row (rnk 1), then every id row
    (rnk 2) -- matching the UNION ALL ... ORDER BY rnk query exactly, so the
    cache-build loop's "first occurrence per key wins" logic is exercised
    the same way it would be against a real Postgres."""
    rows = []
    for c in catalog:
        if c.get('public_id'):
            rows.append(types.SimpleNamespace(key=c['public_id'], provider_model_id=c['provider_model_id']))
    for c in catalog:
        if c.get('provider_model_id'):
            rows.append(types.SimpleNamespace(key=c['provider_model_id'], provider_model_id=c['provider_model_id']))
    for c in catalog:
        if c.get('id'):
            rows.append(types.SimpleNamespace(key=c['id'], provider_model_id=c['provider_model_id']))
    return rows


class _CatalogFakeSession:
    """Fake AsyncSession serving every model_catalog-related query chat.py
    issues, backed by one small in-memory `catalog` (list of
    {id, provider_model_id, public_id} dicts) -- shared by
    _resolve_public_model's resolve query, get_working_models(), and
    _is_model_allowed()'s direct-row-exists fallback, so all three see a
    mutually consistent picture instead of three unrelated canned results."""

    def __init__(self, catalog):
        self.catalog = catalog
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, stmt, params=None, *a, **k):
        text_sql = str(stmt)
        result = MagicMock()
        if 'precedence' in text_sql:
            # chat._MODEL_RESOLVE_SQL
            result.fetchall.return_value = _resolve_rows(self.catalog)
            return result
        if 'SELECT 1 FROM model_catalog' in text_sql:
            # chat._is_model_allowed's direct-row-exists fallback
            mid = (params or {}).get('mid')
            hit = any(
                c.get('provider_model_id') == mid or c.get('id') == mid or c.get('public_id') == mid
                for c in self.catalog
            )
            result.fetchone.return_value = (1,) if hit else None
            return result
        if 'input_per_million' in text_sql:
            # chat._record_usage's price lookup (`WHERE provider_model_id = :mid`).
            # Returns a small sane price row for any known provider_model_id,
            # None otherwise (the real L2 fallback-ceiling path) -- this must
            # never return an unconfigured MagicMock, which would make
            # `int(price_row.input_per_million or 0)` blow up downstream.
            mid = (params or {}).get('mid')
            hit = any(c.get('provider_model_id') == mid for c in self.catalog)
            result.fetchone.return_value = (
                types.SimpleNamespace(input_per_million=1000, output_per_million=1000) if hit else None
            )
            return result
        if 'FROM model_catalog' in text_sql and 'availability' in text_sql:
            # chat.get_working_models()
            rows = [
                types.SimpleNamespace(
                    provider_model_id=c['provider_model_id'], id=c['id'], public_id=c.get('public_id'),
                )
                for c in self.catalog
            ]
            result.fetchall.return_value = rows
            return result
        result.fetchall.return_value = []
        result.fetchone.return_value = None
        return result

    async def commit(self):
        return None


def _patch_resolve_db(catalog=_FAKE_CATALOG):
    """Patch database._real_async_session (the state backing every module's
    shared `async_session` proxy -- see conftest.py's mock_async_session
    fixture docstring) so every `async with async_session() as session` in
    chat.py yields a `_CatalogFakeSession` backed by `catalog`."""
    session = _CatalogFakeSession(catalog)

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return None

    maker = MagicMock(return_value=_Ctx())
    return patch.object(_db, '_real_async_session', maker)


# ── 1. Resolver: precedence, passthrough, unknown ids ───────────────────

class TestResolverPrecedenceAndPassthrough:
    @pytest.mark.asyncio
    async def test_public_id_resolves_to_provider_model_id(self):
        with _patch_resolve_db():
            resolved = await chat_mod._resolve_public_model('sanjab/mistral-large')
        assert resolved == 'bynara/mistral-large'

    @pytest.mark.asyncio
    async def test_old_ids_pass_through_to_themselves_indefinitely(self):
        """An id that never got a public_id (or that already IS the
        provider_model_id) must keep resolving to itself -- no deprecation
        window, ever."""
        with _patch_resolve_db():
            assert await chat_mod._resolve_public_model('kr/claude-sonnet-4') == 'kr/claude-sonnet-4'
            assert await chat_mod._resolve_public_model('tencent-hy3') == 'tencent-hy3'
            # The collision-loser bare id: never gets a public_id, but must
            # still resolve (to itself) so it keeps working as a chat id.
            assert await chat_mod._resolve_public_model('mistral-large') == 'mistral-large'

    @pytest.mark.asyncio
    async def test_unknown_model_passed_through_unchanged(self):
        """A model string matching nothing in the catalog must fall through
        unchanged, so it still hits the existing 'model not available' path
        instead of crashing the request."""
        with _patch_resolve_db():
            assert await chat_mod._resolve_public_model('totally-unknown-model-xyz') == 'totally-unknown-model-xyz'

    @pytest.mark.asyncio
    async def test_empty_model_short_circuits(self):
        with _patch_resolve_db():
            assert await chat_mod._resolve_public_model('') == ''

    @pytest.mark.asyncio
    async def test_explicit_precedence_public_id_beats_id(self):
        """'sanjab/collide' matches a real public_id (-> winner/collide) AND
        a different row's raw `id` (-> legacy/collide-loser). public_id must
        win -- this is exactly what _MODEL_RESOLVE_SQL's `ORDER BY rnk`
        (public_id=0, provider_model_id=1, id=2) is for; it must not be an
        accident of iteration order."""
        with _patch_resolve_db():
            assert await chat_mod._resolve_public_model('sanjab/collide') == 'winner/collide'


# ── 2 & 3. No-leak contract on / flag-off byte-for-byte identical ───────

def _seeded_public_row(**overrides):
    row = dict(
        id='bynara/mistral-large', provider_model_id='bynara/mistral-large',
        public_id='sanjab/mistral-large', display_name='Mistral Large',
        context_window=32000,
    )
    row.update(overrides)
    return row


class TestCatalogRowMappingNoLeak:
    """Unit-tests _catalog_row_to_item directly -- the exact function that
    decides what `id` a normal user sees. WHERE-clause filtering
    (`public_id IS NOT NULL`) is covered separately below
    (TestLoadCatalogRowsFilterSql); this class covers the id substitution."""

    def test_flag_on_serves_public_id(self, monkeypatch):
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        row = _seeded_public_row()
        item = content_mod._catalog_row_to_item(row)
        assert item['id'] == 'sanjab/mistral-large'
        assert not item['id'].startswith('bynara/')

    def test_flag_off_serves_raw_id_unchanged(self, monkeypatch):
        """This is the rollback guarantee: flag OFF (including simply unset,
        the real default) must reproduce today's exact behavior."""
        monkeypatch.delenv('PUBLIC_MODEL_IDS_ENABLED', raising=False)
        row = _seeded_public_row()
        item = content_mod._catalog_row_to_item(row)
        assert item['id'] == 'bynara/mistral-large'

    def test_flag_on_but_no_public_id_falls_back_to_raw_id(self, monkeypatch):
        """Defense in depth: _load_catalog_rows already filters to
        `public_id IS NOT NULL` when the flag is on, so this row shape isn't
        expected from a real query -- but the mapping function itself must
        not crash or silently serve None if it's ever handed one anyway."""
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        row = _seeded_public_row(public_id=None)
        item = content_mod._catalog_row_to_item(row)
        assert item['id'] == 'bynara/mistral-large'

    def test_no_leaked_ids_have_route_prefix_or_free_when_flag_on(self, monkeypatch):
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        rows = [
            _seeded_public_row(id='bynara/mistral-large', provider_model_id='bynara/mistral-large', public_id='sanjab/mistral-large'),
            _seeded_public_row(id='bynara/mimo-v2.5-free', provider_model_id='bynara/mimo-v2.5-free', public_id='sanjab/mimo-v2.5'),
            _seeded_public_row(id='gemini-api/models/gemini-3-flash-preview', provider_model_id='gemini-api/models/gemini-3-flash-preview', public_id='sanjab/gemini-3-flash-preview'),
        ]
        route_prefixes = ('bynara/', 'kr/', 'cc/', 'cx/', 'ag/', 'gemini-api/models/', 'nvidia/')
        for row in rows:
            item = content_mod._catalog_row_to_item(row)
            assert item['id'].startswith('sanjab/'), item['id']
            assert '-free' not in item['id'], item['id']
            assert not any(item['id'].startswith(p) for p in route_prefixes), item['id']


class TestLoadCatalogRowsFilterSql:
    """_load_catalog_rows must add `AND public_id IS NOT NULL` to its SQL
    only when the flag is on -- flag off must send the exact same query as
    before this migration (the rollback guarantee)."""

    @pytest.mark.asyncio
    async def test_flag_on_adds_public_id_filter(self, monkeypatch, mock_async_session):
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        captured = {}

        async def _execute(stmt, *a, **k):
            captured['sql'] = str(stmt)
            result = MagicMock()
            result.fetchall.return_value = []
            return result

        mock_async_session.execute = _execute
        await content_mod._load_catalog_rows()
        assert 'public_id IS NOT NULL' in captured['sql']

    @pytest.mark.asyncio
    async def test_flag_off_omits_public_id_filter(self, monkeypatch, mock_async_session):
        monkeypatch.delenv('PUBLIC_MODEL_IDS_ENABLED', raising=False)
        captured = {}

        async def _execute(stmt, *a, **k):
            captured['sql'] = str(stmt)
            result = MagicMock()
            result.fetchall.return_value = []
            return result

        mock_async_session.execute = _execute
        await content_mod._load_catalog_rows()
        assert 'public_id IS NOT NULL' not in captured['sql']


class TestListModelsEndpointFlagBehavior:
    """/v1/models: same contract as _load_catalog_rows, exercised through the
    real endpoint via the TestClient."""

    def test_flag_off_v1_models_unchanged(self, client, mock_async_session, monkeypatch):
        from tests.conftest import make_result, make_row
        monkeypatch.delenv('PUBLIC_MODEL_IDS_ENABLED', raising=False)
        mock_async_session._execute_result = make_result(fetchall=[
            make_row(
                id='bynara/mistral-large', provider_model_id='bynara/mistral-large',
                display_name='Mistral Large', context_window=32000, availability='available',
                input_per_million=0, output_per_million=0, currency='IRT',
                usd_input_per_million=0, usd_output_per_million=0,
            )
        ])
        resp = client.get('/v1/models')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data
        assert data[0]['id'] == 'bynara/mistral-large'

    def test_flag_on_v1_models_serves_public_id(self, client, mock_async_session, monkeypatch):
        from tests.conftest import make_result, make_row
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        mock_async_session._execute_result = make_result(fetchall=[
            make_row(
                id='bynara/mistral-large', provider_model_id='bynara/mistral-large',
                public_id='sanjab/mistral-large',
                display_name='Mistral Large', context_window=32000, availability='available',
                input_per_million=0, output_per_million=0, currency='IRT',
                usd_input_per_million=0, usd_output_per_million=0,
            )
        ])
        resp = client.get('/v1/models')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data
        assert data[0]['id'] == 'sanjab/mistral-large'
        assert not data[0]['id'].startswith('bynara/')


# ── 4. Billing regression: canonical id reaches the price lookup ────────

class _FakeProvider:
    v1 = 'http://fake-upstream/v1'

    def headers(self):
        return {'Content-Type': 'application/json'}


def _billing_mock():
    """A BillingService replacement whose reserve()/release() never touch a
    real DB -- mirrors test_web_search.py's helper of the same name."""
    instance = MagicMock()
    instance.reserve = AsyncMock(return_value={'reservation_id': 'test-reservation'})
    instance.release = AsyncMock(return_value=None)
    instance.settle = AsyncMock(return_value=None)
    return MagicMock(return_value=instance)


def _upstream_response(body: dict | None = None, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=body or {'choices': [{'message': {'content': 'پاسخ نمونه'}}]})
    resp.content = b'{}'
    return resp


def _patched_http(capture: dict | None = None, body: dict | None = None):
    fake = MagicMock()
    if capture is not None:
        async def _post(url, json=None, headers=None):
            capture['json'] = json
            capture['url'] = url
            return _upstream_response(body)
        fake.post = _post
    else:
        fake.post = AsyncMock(return_value=_upstream_response(body))
    return fake


AUTH_HEADERS = {'Authorization': 'Bearer test-token'}


@pytest.fixture
def _bypass_pipeline():
    """Bypass auth, billing reservation, and provider routing -- NOT
    check_and_consume, which several tests below want to observe/spy on."""
    with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)), \
         patch.object(chat_mod, 'BillingService', _billing_mock()), \
         patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())):
        yield


class TestChatCanonicalizesBeforeUpstreamCall:
    """Proves _resolve_public_model runs on the SAME payload_dict that later
    feeds the free-tier gate, the reservation, the upstream call, and (via
    _track_usage/_record_usage) the price lookup -- i.e. canonicalizing once,
    early, covers the whole pipeline rather than just the upstream call."""

    def test_chat_completions_sends_canonical_model_upstream(self, client, _bypass_pipeline):
        capture: dict = {}
        with _patch_resolve_db(), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(_db, '_real_http', _patched_http(capture)):
            resp = client.post(
                '/v1/chat/completions',
                json={'model': 'sanjab/mistral-large', 'messages': [{'role': 'user', 'content': 'سلام'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        assert capture['json']['model'] == 'bynara/mistral-large'
        assert capture['json']['model'] != 'sanjab/mistral-large'

    def test_chat_with_file_sends_canonical_model_upstream(self, client, _bypass_pipeline):
        capture: dict = {}
        with _patch_resolve_db(), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(_db, '_real_http', _patched_http(capture)):
            resp = client.post(
                '/v1/chat/with-file',
                data={'model': 'sanjab/mistral-large', 'messages': '[]'},
                files={'file': ('note.txt', b'hello world', 'text/plain')},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        assert capture['json']['model'] == 'bynara/mistral-large'

    def test_compare_sends_canonical_models_upstream_but_echoes_requested_ids(self, client, _bypass_pipeline):
        """/v1/compare must route+bill on the canonical provider_model_id but
        must echo back exactly what the caller requested in its response --
        otherwise a sanjab/* request would get the raw upstream id leaked
        back to it in the JSON body."""
        posted_models = []

        async def _post(url, json=None, headers=None):
            posted_models.append(json['model'])
            return _upstream_response({'choices': [{'message': {'content': 'ok'}}], 'usage': {'prompt_tokens': 5, 'completion_tokens': 5}})

        fake_http = MagicMock()
        fake_http.post = _post

        with _patch_resolve_db(), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(_db, '_real_http', fake_http):
            resp = client.post(
                '/v1/compare',
                json={'model_a': 'sanjab/mistral-large', 'model_b': 'kr/claude-sonnet-4', 'messages': [{'role': 'user', 'content': 'hi'}]},
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        assert 'bynara/mistral-large' in posted_models
        assert 'kr/claude-sonnet-4' in posted_models
        body = resp.json()
        # Echoed back exactly what was requested -- not the resolved
        # provider_model_id (which would leak the route the public id hid).
        assert body['model_a']['model'] == 'sanjab/mistral-large'
        assert body['model_b']['model'] == 'kr/claude-sonnet-4'


# ── 4b. _record_usage price lookup: canonical id hits, raw sanjab id misses ──

def _table_name(stmt):
    try:
        return stmt.table.name
    except AttributeError:
        pass
    try:
        for f in stmt.get_final_froms():
            name = getattr(f, "name", None)
            if name:
                return name
    except Exception:
        pass
    return None


class _RecordUsageFakeSession:
    """Minimal session double covering exactly the statements
    chat._record_usage / SqlBillingRepo issue -- same shape as
    test_billing_loss_paths.py's `_FakeSession` (kept local to this file so
    it doesn't need to import another test module)."""

    def __init__(self, wallet_balance, price_by_mid=None):
        self.wallet = types.SimpleNamespace(user_id=1, balance=wallet_balance, reserved=0)
        self.price_by_mid = price_by_mid or {}
        self.added = []
        self.last_price_lookup_mid = None

    async def execute(self, stmt, params=None, *a, **k):
        result = MagicMock()
        result.fetchone.return_value = None
        text_sql = str(stmt)
        if "model_catalog" in text_sql:
            mid = (params or {}).get('mid')
            self.last_price_lookup_mid = mid
            result.fetchone.return_value = self.price_by_mid.get(mid)
            return result
        tname = _table_name(stmt)
        if tname == "wallet":
            if type(stmt).__name__ == "Update":
                p = stmt.compile().params
                if "balance" in p:
                    self.wallet.balance = p["balance"]
            else:
                result.fetchone.return_value = (self.wallet,)
            return result
        if tname == "quota":
            if type(stmt).__name__ == "Update":
                return result
            result.fetchone.return_value = None
            return result
        return result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


def _price(inp=1_000_000, out=1_000_000):
    return types.SimpleNamespace(input_per_million=inp, output_per_million=out)


class TestBillingPriceLookupNeedsCanonicalId:
    @pytest.mark.asyncio
    async def test_unresolved_sanjab_id_misses_price_and_bills_fallback_ceiling(self):
        """The hazard this whole change exists to close: if a `sanjab/*`
        string ever reached _record_usage unresolved, the price lookup
        (`WHERE provider_model_id = :mid`) would MISS -- because the DB only
        knows about 'bynara/mistral-large' -- and silently bill at the
        fallback CEILING rate instead of the model's real price."""
        session = _RecordUsageFakeSession(
            wallet_balance=10_000_000,
            price_by_mid={'bynara/mistral-large': _price(inp=1000, out=1000)},
        )
        usage = {"prompt_tokens": 800, "completion_tokens": 200}
        result = await chat_mod._record_usage(
            session, uid=1,
            payload={"model": "sanjab/mistral-large", "messages": []},
            usage=usage,
        )
        assert session.last_price_lookup_mid == 'sanjab/mistral-large'
        expected_fallback = max(
            1,
            (800 * chat_mod.FALLBACK_PRICE_PER_MILLION_IN
             + 200 * chat_mod.FALLBACK_PRICE_PER_MILLION_OUT + 500_000) // 1_000_000,
        )
        assert result['cost'] == expected_fallback

    @pytest.mark.asyncio
    async def test_resolved_canonical_id_hits_real_price_not_fallback(self):
        """Once chat.py's endpoints canonicalize `model` before calling
        _track_usage/_record_usage (as they now all do -- see
        TestChatCanonicalizesBeforeUpstreamCall above), the SAME price
        lookup hits the model's real row instead of the fallback ceiling."""
        session = _RecordUsageFakeSession(
            wallet_balance=10_000_000,
            price_by_mid={'bynara/mistral-large': _price(inp=1000, out=1000)},
        )
        usage = {"prompt_tokens": 800, "completion_tokens": 200}
        result = await chat_mod._record_usage(
            session, uid=1,
            payload={"model": "bynara/mistral-large", "messages": []},
            usage=usage,
        )
        assert session.last_price_lookup_mid == 'bynara/mistral-large'
        # 800*1000 + 200*1000 = 1,000,000 -> +500,000 rounding // 1,000,000 = 1
        assert result['cost'] == 1
        fallback = max(
            1,
            (800 * chat_mod.FALLBACK_PRICE_PER_MILLION_IN
             + 200 * chat_mod.FALLBACK_PRICE_PER_MILLION_OUT + 500_000) // 1_000_000,
        )
        assert result['cost'] != fallback


# ── 5. Collision loser: absent from public listings, still a valid chat id ──

class TestCollisionLoserStillWorksAsChatId:
    def test_absent_from_public_catalog_item_mapping(self, monkeypatch):
        """A collision loser's row has public_id IS NULL -- _load_catalog_rows
        already filters those out at the SQL level when the flag is on (see
        TestLoadCatalogRowsFilterSql), so this row shape never reaches
        _catalog_row_to_item in practice; this just double-checks the
        mapping function doesn't invent a public-looking id for it either."""
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        loser_row = dict(
            id='mistral-large', provider_model_id='mistral-large',
            public_id=None, display_name='Mistral Large (legacy)',
            context_window=32000,
        )
        item = content_mod._catalog_row_to_item(loser_row)
        assert item['id'] == 'mistral-large'
        assert not item['id'].startswith('sanjab/')

    @pytest.mark.asyncio
    async def test_still_accepted_as_a_chat_model(self):
        """'mistral-large' (the bare collision loser) must keep working as a
        chat id -- it keeps its own id/route/price, it's just not publicly
        listed. It's in chat.py's hardcoded verified working set, so this
        must pass even with no DB configured at all."""
        with patch.object(_db, '_real_async_session', None):
            chat_mod._WORKING_SET_CACHE = None
            allowed = await chat_mod._is_model_allowed('mistral-large')
        assert allowed is True

    @pytest.mark.asyncio
    async def test_resolver_leaves_collision_loser_id_unchanged(self):
        """The resolver must not invent a public_id for a row that
        deliberately has none -- it passes through to itself."""
        with _patch_resolve_db():
            assert await chat_mod._resolve_public_model('mistral-large') == 'mistral-large'


# ── 6. smart_chat forced model resolves via public_id, not slash-splitting ──

class TestSmartChatForcedModelResolution:
    def test_forced_sanjab_public_id_routes_to_real_provider_model_id(self, client, _bypass_pipeline):
        """Regression for the exact hazard described for smart_chat: the old
        code did `force_model.split('/', 1)[1]` on 'sanjab/mistral-large',
        landing on the bare 'mistral-large' -- a DIFFERENT physical
        model_catalog row (a degraded litellm one) with its own route and
        price. The resolver must instead land on 'bynara/mistral-large'."""
        capture: dict = {}
        with _patch_resolve_db(), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(_db, '_real_http', _patched_http(capture)):
            resp = client.post(
                '/v1/smart-chat',
                json={'messages': [{'role': 'user', 'content': 'سلام'}], 'stream': False},
                headers={**AUTH_HEADERS, 'X-Smart-Model': 'sanjab/mistral-large'},
            )
        assert resp.status_code == 200, resp.text
        assert capture['json']['model'] == 'bynara/mistral-large'
        assert capture['json']['model'] != 'mistral-large'
        # The response header must echo back what the caller sent, not the
        # resolved provider_model_id (route-hiding rule -- see chat.py).
        assert resp.headers['X-Smart-Model'] == 'sanjab/mistral-large'


# ── 7. Free-tier: old id and new id share one quota bucket ──────────────

class TestFreeTierSharedBucket:
    def test_old_and_new_ids_hit_check_and_consume_with_the_same_canonical_model(self, client, _bypass_pipeline):
        """services/free_tier.py keys its Redis bucket as
        `freetier:msg:{uid}:{model}` off exactly the string it's handed.
        Canonicalizing BEFORE check_and_consume is what makes an old raw id
        and its new sanjab/* alias land in the identical bucket instead of
        each getting their own 5-message allowance."""
        spy = AsyncMock(return_value=None)
        with _patch_resolve_db(), \
             patch.object(chat_mod, 'check_and_consume', spy), \
             patch.object(_db, '_real_http', _patched_http()):
            resp1 = client.post(
                '/v1/chat/completions',
                json={'model': 'bynara/mistral-large', 'messages': [{'role': 'user', 'content': 'a'}]},
                headers=AUTH_HEADERS,
            )
            resp2 = client.post(
                '/v1/chat/completions',
                json={'model': 'sanjab/mistral-large', 'messages': [{'role': 'user', 'content': 'b'}]},
                headers=AUTH_HEADERS,
            )
        assert resp1.status_code == 200, resp1.text
        assert resp2.status_code == 200, resp2.text
        assert spy.await_count == 2
        models_seen = [call.args[1] for call in spy.await_args_list]
        assert models_seen[0] == ['bynara/mistral-large']
        assert models_seen[1] == ['bynara/mistral-large']


# ── conversations.py: historical usage translated at read time only ─────

class TestConversationAnalyticsTranslatesAtReadTimeOnly:
    """usage_events/ledger/wallet_reservations/conversations are append-only
    and must never be rewritten -- the model string a historical row was
    billed under stays exactly as-is forever. Translation for display must
    happen only at READ time, via a LEFT JOIN against model_catalog."""

    def _capture_sqls(self, mock_async_session):
        captured: list[str] = []

        async def _execute(stmt, params=None, *a, **k):
            captured.append(str(stmt))
            result = MagicMock()
            result.fetchone.return_value = types.SimpleNamespace(c=0, total_tokens=0, total_cost=0)
            result.fetchall.return_value = []
            return result

        mock_async_session.execute = _execute
        return captured

    def test_flag_off_groups_by_raw_stored_model_no_join(self, client, mock_async_session, auth_headers, monkeypatch):
        monkeypatch.delenv('PUBLIC_MODEL_IDS_ENABLED', raising=False)
        captured = self._capture_sqls(mock_async_session)
        resp = client.get('/conversations/analytics', headers=auth_headers)
        assert resp.status_code == 200, resp.text
        models_sql = next(s for s in captured if 'GROUP BY' in s and 'usage_events' in s)
        assert 'model_catalog' not in models_sql
        assert 'GROUP BY model' in models_sql

    def test_flag_on_joins_model_catalog_never_touches_usage_events_rows(self, client, mock_async_session, auth_headers, monkeypatch):
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        captured = self._capture_sqls(mock_async_session)
        resp = client.get('/conversations/analytics', headers=auth_headers)
        assert resp.status_code == 200, resp.text
        models_sql = next(s for s in captured if 'GROUP BY' in s and 'usage_events' in s)
        assert 'LEFT JOIN model_catalog' in models_sql
        assert 'COALESCE(mc.public_id, ue.model)' in models_sql or 'COALESCE(mc.public_id,ue.model)' in models_sql.replace(' ', '')
        # Never an UPDATE/DELETE against the append-only usage_events table.
        assert not any('UPDATE usage_events' in s or 'DELETE FROM usage_events' in s for s in captured)
