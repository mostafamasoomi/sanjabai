"""chat.py side of the public model id indirection (migrations/0028_public_model_ids.sql).

Split out of the original tests/test_public_model_ids.py (which grew past
the 500-line cap) -- the content.py/`/v1/models`+`/catalog/models` listing
side and the conversations.py read-time-translation side now live in
tests/test_public_model_ids_catalog.py, and the fake DB session / fake
upstream http client this file needs live in
tests/_public_model_ids_chat_fakes.py. See that catalog test file's
docstring for the `content.py` half of the background; this file covers the
`chat.py` half:

  `_resolve_public_model()` canonicalizes ANY incoming model string
  (public_id, provider_model_id, or the legacy `id`) to `provider_model_id`
  -- the id routing/health/billing have always used -- exactly once, as
  early as possible in every chat/compare/smart-chat call site, before the
  free-tier gate/reservation/validation/upstream call. This is always-on
  (never gated by content.py's PUBLIC_MODEL_IDS_ENABLED flag): an
  unresolved `sanjab/*` id would otherwise 502 upstream (LiteLLM/9router
  have never heard of it) AND silently overcharge, because
  `_record_usage`'s price lookup (`WHERE provider_model_id = :mid`) would
  miss and fall through to the fallback CEILING rate.

No test in this file makes a real network or DB call: the DB session proxy
and the outbound httpx client are always faked, following this suite's
existing conventions (see test_web_search.py's bypass fixture and
test_billing_loss_paths.py's `_FakeSession`).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import content as content_mod
import database as _db
from tests._public_model_ids_chat_fakes import (
    AUTH_HEADERS,
    _billing_mock,
    _FakeProvider,
    _patch_resolve_db,
    _patched_http,
    _price,
    _RecordUsageFakeSession,
    _upstream_response,
)


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


# ── 2. Billing regression: canonical id reaches the price lookup ────────

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

        async def _post(url, json=None, headers=None, timeout=None):
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


# ── 2b. _record_usage price lookup: canonical id hits, raw sanjab id misses ──

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


# ── 3. Collision loser: absent from public listings, still a valid chat id ──

class TestCollisionLoserStillWorksAsChatId:
    def test_absent_from_public_catalog_item_mapping(self, monkeypatch):
        """A collision loser's row has public_id IS NULL -- _load_catalog_rows
        already filters those out at the SQL level when the flag is on (see
        test_public_model_ids_catalog.py's TestLoadCatalogRowsFilterSql), so
        this row shape never reaches _catalog_row_to_item in practice; that
        file's TestCatalogRowMappingNoLeak double-checks the mapping function
        itself doesn't invent a public-looking id for it either. This test
        covers the chat.py side only: the collision loser must still resolve
        and be accepted as a chat model id below."""
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
        listed. `public_id IS NULL` gates *listing*, never *acceptance*.

        This used to assert the same thing with no DB configured at all,
        because the id happened to sit in chat.py's hardcoded verified
        working set. That set is gone (it had drifted to eight models the
        catalog could no longer serve), so the invariant is now proved where
        it actually lives: against the catalog itself.

        Honest scope note: acceptance is defended twice -- the working-set
        fast path AND `_is_model_allowed`'s direct row-exists query -- so no
        single-site mutation turns this red; it takes both paths dropping
        public_id-NULL rows (verified). Read it as a redundancy check over
        the pair, not as coverage of either path alone.
        """
        with _patch_resolve_db():
            chat_mod._WORKING_SET_CACHE = None
            allowed = await chat_mod._is_model_allowed('mistral-large')
        assert allowed is True

    @pytest.mark.asyncio
    async def test_rejected_when_db_is_down_and_cache_is_cold(self):
        """Deliberate counterpart to the test above: with no DB *and* nothing
        ever cached, acceptance fails closed.

        Guards the removal of the hardcoded working set. That set answered
        True here, which meant a model an admin had explicitly disabled in
        the catalog became reachable again the moment the DB blinked -- the
        one moment nothing could verify the decision. A cold-start rejection
        is the safe direction: during a real outage billing and reservations
        are down too, so the request could not have completed anyway.
        """
        with patch.object(_db, '_real_async_session', None):
            chat_mod._WORKING_SET_CACHE = None
            allowed = await chat_mod._is_model_allowed('mistral-large')
        assert allowed is False

    @pytest.mark.asyncio
    async def test_resolver_leaves_collision_loser_id_unchanged(self):
        """The resolver must not invent a public_id for a row that
        deliberately has none -- it passes through to itself."""
        with _patch_resolve_db():
            assert await chat_mod._resolve_public_model('mistral-large') == 'mistral-large'


# ── 4. smart_chat forced model resolves via public_id, not slash-splitting ──

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


# ── 5. Free-tier: old id and new id share one quota bucket ──────────────

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
