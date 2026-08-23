"""Phase C P4 -- proof that the logical model layer is actually wired.

services/model_resolver.py resolve_logical_model() was complete and had its
own passing test file since the sixth session, yet a grep over the whole
backend on 2026-08-23 found no production call site at all -- only the
definition, two mentions inside its own docstrings, and its own test. A
tested function nothing calls is exactly the "switch that stored a value and
controlled nothing" pattern this project has already been burned by twice
(preferences.panel with zero readers, the six site flags wired to nothing).

So these tests deliberately do NOT test resolve_logical_model -- that is
tests/test_model_resolver.py's job and it already passes. They test the one
thing that was missing: that chat_models._resolve_public_model, the single
early canonicalization point every chat path funnels through, actually
consults it, actually respects the flag, and actually cannot break a model
that resolves today.
"""
from unittest.mock import AsyncMock, patch

import pytest

import chat_models


@pytest.fixture
def _cache():
    """Install a known resolve cache and keep it fresh for the whole test.

    _resolve_public_model_catalog reads chat._MODEL_RESOLVE_CACHE and only
    refreshes it once _MODEL_RESOLVE_CACHE_TTL_SECONDS has elapsed, so
    stamping LOADED_AT to "now" keeps every test on the cached path and out
    of the database.
    """
    import time as _t

    import chat as chat_mod
    prev_cache = chat_mod._MODEL_RESOLVE_CACHE
    prev_at = chat_mod._MODEL_RESOLVE_CACHE_LOADED_AT
    chat_mod._MODEL_RESOLVE_CACHE = {
        'sanjab/claude-sonnet-5': 'cc/claude-sonnet-5',
        'cc/claude-sonnet-5': 'cc/claude-sonnet-5',
        'catalog-row-id': 'cc/claude-sonnet-5',
    }
    chat_mod._MODEL_RESOLVE_CACHE_LOADED_AT = _t.monotonic()
    yield chat_mod
    chat_mod._MODEL_RESOLVE_CACHE = prev_cache
    chat_mod._MODEL_RESOLVE_CACHE_LOADED_AT = prev_at


class TestFlagOffIsTodaysBehaviour:
    """The phase's stated acceptance criterion -- flag off must be
    byte-for-byte the behaviour that shipped before the logical layer."""

    @pytest.mark.asyncio
    async def test_unknown_model_unchanged_when_flag_off(self, _cache):
        with patch('site_settings.get_site_flag', AsyncMock(return_value=False)) as flag, \
             patch('services.model_resolver.resolve_logical_model', AsyncMock()) as resolver:
            out = await chat_models._resolve_public_model('claude-sonnet-5')
        assert out == 'claude-sonnet-5'
        assert flag.await_count == 1
        # The decisive assertion: the resolver is not merely ignored, it is
        # never even consulted, so a flag-off request costs zero extra work.
        resolver.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_known_model_still_canonicalizes_when_flag_off(self, _cache):
        with patch('site_settings.get_site_flag', AsyncMock(return_value=False)):
            out = await chat_models._resolve_public_model('sanjab/claude-sonnet-5')
        assert out == 'cc/claude-sonnet-5'


class TestFlagOnResolvesLogicalKeys:

    @pytest.mark.asyncio
    async def test_logical_key_resolves_to_physical_model(self, _cache):
        with patch('site_settings.get_site_flag', AsyncMock(return_value=True)), \
             patch('services.model_resolver.resolve_logical_model',
                   AsyncMock(return_value='catalog-row-id')) as resolver:
            out = await chat_models._resolve_public_model('claude-sonnet-5')
        # Not the logical key, and not the catalog row id either -- the
        # provider_model_id, which is what routing, health and above all
        # _record_usage's price lookup are keyed on. Returning the catalog
        # id here would miss that lookup and silently bill the fallback
        # ceiling rate.
        assert out == 'cc/claude-sonnet-5'
        resolver.assert_awaited_once_with('claude-sonnet-5')

    @pytest.mark.asyncio
    async def test_catalog_wins_over_logical_layer(self, _cache):
        """A string the catalog knows must never reach the logical layer,
        even with the flag on. This is what makes turning the flag on unable
        to reroute any model that works today."""
        with patch('site_settings.get_site_flag', AsyncMock(return_value=True)), \
             patch('services.model_resolver.resolve_logical_model', AsyncMock()) as resolver:
            out = await chat_models._resolve_public_model('sanjab/claude-sonnet-5')
        assert out == 'cc/claude-sonnet-5'
        resolver.assert_not_awaited()


class TestFailuresFallBack:
    """resolve_logical_model's documented contract is that it never raises
    and that None means "fall back to today's behaviour". These pin that the
    call site actually honours both."""

    @pytest.mark.asyncio
    async def test_none_falls_back(self, _cache):
        with patch('site_settings.get_site_flag', AsyncMock(return_value=True)), \
             patch('services.model_resolver.resolve_logical_model', AsyncMock(return_value=None)):
            out = await chat_models._resolve_public_model('claude-sonnet-5')
        assert out == 'claude-sonnet-5'

    @pytest.mark.asyncio
    async def test_resolver_raising_falls_back(self, _cache):
        with patch('site_settings.get_site_flag', AsyncMock(return_value=True)), \
             patch('services.model_resolver.resolve_logical_model',
                   AsyncMock(side_effect=RuntimeError('boom'))):
            out = await chat_models._resolve_public_model('claude-sonnet-5')
        assert out == 'claude-sonnet-5'

    @pytest.mark.asyncio
    async def test_flag_read_raising_falls_back(self, _cache):
        with patch('site_settings.get_site_flag', AsyncMock(side_effect=RuntimeError('redis down'))):
            out = await chat_models._resolve_public_model('claude-sonnet-5')
        assert out == 'claude-sonnet-5'

    @pytest.mark.asyncio
    async def test_logical_row_pointing_at_unknown_catalog_id_falls_back(self, _cache):
        """A logical row whose pinned/selected candidate is not in the
        catalog cache must NOT be forwarded upstream half-resolved -- an
        unresolved id both 502s upstream and misses the price lookup."""
        with patch('site_settings.get_site_flag', AsyncMock(return_value=True)), \
             patch('services.model_resolver.resolve_logical_model',
                   AsyncMock(return_value='id-that-is-not-in-the-cache')):
            out = await chat_models._resolve_public_model('claude-sonnet-5')
        assert out == 'claude-sonnet-5'


class TestEveryReturnPathIsCovered:
    """The pre-split shape of _resolve_public_model had four early returns
    plus the post-refresh one. Wiring the logical layer into only some of
    them would produce a flag that works only on a cold cache -- a bug that
    would be invisible in production for as long as the cache stayed warm."""

    @pytest.mark.asyncio
    async def test_empty_model_short_circuit_still_wrapped(self, _cache):
        with patch('site_settings.get_site_flag', AsyncMock(return_value=True)), \
             patch('services.model_resolver.resolve_logical_model', AsyncMock()) as resolver:
            out = await chat_models._resolve_public_model('')
        assert out == ''
        resolver.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_session_path_is_wrapped(self, _cache):
        """chat.async_session is None -- the first early return."""
        import chat as chat_mod
        prev = chat_mod.async_session
        chat_mod.async_session = None
        try:
            with patch('site_settings.get_site_flag', AsyncMock(return_value=True)), \
                 patch('services.model_resolver.resolve_logical_model',
                       AsyncMock(return_value='catalog-row-id')):
                out = await chat_models._resolve_public_model('claude-sonnet-5')
        finally:
            chat_mod.async_session = prev
        assert out == 'cc/claude-sonnet-5'


class TestCanonicalIdIsNotTreatedAsUnknown:
    """The gate is membership in the resolve cache, not ``resolved !=
    model``. A caller passing an already-canonical provider_model_id gets
    the same string back, so an equality test would misclassify a
    perfectly well-known model as unknown and drag it through the logical
    layer -- and a flag read -- on every single request.
    """

    @pytest.mark.asyncio
    async def test_canonical_provider_model_id_skips_logical_layer(self, _cache):
        with patch('site_settings.get_site_flag', AsyncMock(return_value=True)) as flag, \
             patch('services.model_resolver.resolve_logical_model', AsyncMock()) as resolver:
            out = await chat_models._resolve_public_model('cc/claude-sonnet-5')
        assert out == 'cc/claude-sonnet-5'
        resolver.assert_not_awaited()
        # Not even the flag is read -- the hot path stays free of an extra
        # Redis/DB round trip for every ordinary request.
        assert flag.await_count == 0
