"""Tests for backend/services/model_resolver.py -- the logical-key ->
physical model_catalog.id resolver (migrations/0025_logical_models.sql).

Style mirrors tests/test_site_settings.py's TestGetSiteFlag: no live
Postgres, `mock_async_session` fixture from conftest.py stands in for the
DB, `session._execute_result` (or a hand-rolled `session.execute`) drives
what a query "returns", and `services.model_resolver.rds` is patched
directly for the cache layer.

Every eligibility rule is proven with a mutation: break the code path the
test guards, watch the test fail, restore, watch it pass again. That
protocol is executed manually outside pytest and reported alongside this
file rather than automated as a meta-test.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

import services.model_resolver as model_resolver
from tests.conftest import make_result, make_row


def _row(
    catalog_id=None,
    priority=100,
    input_per_million=0,
    output_per_million=0,
    lm_availability='available',
    lm_routing_policy='cheapest_healthy',
    lm_pinned_candidate_id=None,
    candidate_state='approved',
    candidate_enabled=True,
    catalog_availability='available',
):
    """Builds one joined result row. Defaults make an already-eligible
    candidate (approved, enabled, catalog available) so tests that are not
    specifically about eligibility don't have to restate it every time."""
    return make_row(
        lm_availability=lm_availability,
        lm_routing_policy=lm_routing_policy,
        lm_pinned_candidate_id=lm_pinned_candidate_id,
        catalog_id=catalog_id,
        priority=priority,
        candidate_state=candidate_state,
        candidate_enabled=candidate_enabled,
        catalog_availability=catalog_availability,
        input_per_million=input_per_million,
        output_per_million=output_per_million,
    )


def _no_cache():
    """Patch rds so every test starts from a clean cache miss and a
    no-op cache write, unless the test overrides one explicitly."""
    return (
        patch.object(model_resolver.rds, 'get', new=AsyncMock(return_value=None)),
        patch.object(model_resolver.rds, 'setex', new=AsyncMock()),
    )


# ── Routing policies ────────────────────────────────────────────────────

class TestPinnedPolicy:
    @pytest.mark.asyncio
    async def test_pinned_candidate_wins_when_eligible(self, mock_async_session):
        rows = [
            _row(catalog_id='model-a', priority=50, input_per_million=100, output_per_million=200,
                 lm_routing_policy='pinned', lm_pinned_candidate_id='model-a'),
            _row(catalog_id='model-b', priority=10, input_per_million=1, output_per_million=1,
                 lm_routing_policy='pinned', lm_pinned_candidate_id='model-a'),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-a'

    @pytest.mark.asyncio
    async def test_pinned_candidate_ineligible_returns_none_not_a_substitute(self, mock_async_session):
        """The pinned target is not among the eligible rows at all (e.g. it
        was rejected, disabled, or its catalog row went unhealthy -- any of
        those means it simply never appears in the query result). The
        resolver must return None, never quietly pick model-b instead."""
        rows = [
            _row(catalog_id='model-b', priority=10, input_per_million=1, output_per_million=1,
                 lm_routing_policy='pinned', lm_pinned_candidate_id='model-a'),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result is None

    @pytest.mark.asyncio
    async def test_pinned_with_no_pinned_id_set_returns_none(self, mock_async_session):
        rows = [
            _row(catalog_id='model-b', priority=10, input_per_million=1, output_per_million=1,
                 lm_routing_policy='pinned', lm_pinned_candidate_id=None),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result is None


class TestPriorityPolicy:
    @pytest.mark.asyncio
    async def test_lowest_priority_wins(self, mock_async_session):
        rows = [
            _row(catalog_id='model-a', priority=50, lm_routing_policy='priority'),
            _row(catalog_id='model-b', priority=10, lm_routing_policy='priority'),
            _row(catalog_id='model-c', priority=90, lm_routing_policy='priority'),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-b'

    @pytest.mark.asyncio
    async def test_priority_ties_break_on_catalog_id_ascending(self, mock_async_session):
        rows = [
            _row(catalog_id='model-z', priority=10, lm_routing_policy='priority'),
            _row(catalog_id='model-a', priority=10, lm_routing_policy='priority'),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-a'


class TestCheapestHealthyPolicy:
    @pytest.mark.asyncio
    async def test_lowest_priced_candidate_wins(self, mock_async_session):
        rows = [
            _row(catalog_id='model-expensive', priority=100, input_per_million=1000, output_per_million=1000),
            _row(catalog_id='model-cheap', priority=100, input_per_million=10, output_per_million=10),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-cheap'

    @pytest.mark.asyncio
    async def test_unpriced_candidate_never_wins_on_price(self, mock_async_session):
        """A 0-priced row must be treated as the category ceiling, not as
        a free bargain -- otherwise it would sort to the top of a naive
        ascending price sort."""
        rows = [
            _row(catalog_id='model-unpriced', priority=100, input_per_million=0, output_per_million=0),
            _row(catalog_id='model-priced', priority=100, input_per_million=500, output_per_million=500),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-priced'

    @pytest.mark.asyncio
    async def test_unpriced_candidate_still_wins_if_it_is_the_only_option(self, mock_async_session):
        rows = [
            _row(catalog_id='model-unpriced', priority=100, input_per_million=0, output_per_million=0),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-unpriced'

    @pytest.mark.asyncio
    async def test_price_ties_break_on_priority_then_catalog_id(self, mock_async_session):
        rows = [
            _row(catalog_id='model-b', priority=20, input_per_million=100, output_per_million=100),
            _row(catalog_id='model-a', priority=10, input_per_million=100, output_per_million=100),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-a'


# ── Eligibility filters (_is_eligible, proven with mutation below) ──────

class TestEligibility:
    @pytest.mark.asyncio
    async def test_no_candidate_at_all_returns_none(self, mock_async_session):
        """catalog_id=None is what the LEFT JOIN produces when a logical
        model has zero candidate rows at all."""
        rows = [_row(catalog_id=None)]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result is None

    @pytest.mark.asyncio
    async def test_proposed_candidate_is_never_selected(self, mock_async_session):
        """1054 of 1154 production candidate rows are `proposed`, held back
        deliberately for admin review. A proposed row must never win even
        when it is priced far cheaper than the one approved alternative."""
        rows = [
            _row(catalog_id='model-proposed-cheap', priority=1,
                 input_per_million=1, output_per_million=1,
                 candidate_state='proposed'),
            _row(catalog_id='model-approved-expensive', priority=100,
                 input_per_million=9999, output_per_million=9999,
                 candidate_state='approved'),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-approved-expensive'

    @pytest.mark.asyncio
    async def test_rejected_candidate_is_never_selected(self, mock_async_session):
        rows = [
            _row(catalog_id='model-rejected', priority=1, input_per_million=1, output_per_million=1,
                 candidate_state='rejected'),
            _row(catalog_id='model-ok', priority=100, input_per_million=9999, output_per_million=9999),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-ok'

    @pytest.mark.asyncio
    async def test_disabled_candidate_is_never_selected(self, mock_async_session):
        rows = [
            _row(catalog_id='model-disabled', priority=1, input_per_million=1, output_per_million=1,
                 candidate_enabled=False),
            _row(catalog_id='model-ok', priority=100, input_per_million=9999, output_per_million=9999),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-ok'

    @pytest.mark.asyncio
    async def test_unavailable_catalog_row_is_skipped(self, mock_async_session):
        rows = [
            _row(catalog_id='model-maintenance', priority=1, input_per_million=1, output_per_million=1,
                 catalog_availability='maintenance'),
            _row(catalog_id='model-ok', priority=100, input_per_million=9999, output_per_million=9999,
                 catalog_availability='available'),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-ok'

    @pytest.mark.asyncio
    async def test_no_logical_model_row_returns_none(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[])
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('missing-key')
        assert result is None

    @pytest.mark.asyncio
    async def test_non_available_logical_model_returns_none(self, mock_async_session):
        rows = [
            _row(catalog_id='model-a', priority=1, input_per_million=1, output_per_million=1,
                 lm_availability='maintenance'),
        ]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_routing_policy_returns_none(self, mock_async_session):
        rows = [_row(catalog_id='model-a', priority=1, lm_routing_policy='not_a_real_policy')]
        mock_async_session._execute_result = make_result(fetchall=rows)
        g, s = _no_cache()
        with g, s:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result is None


# ── Caching ──────────────────────────────────────────────────────────────

class TestCaching:
    @pytest.mark.asyncio
    async def test_cache_hit_avoids_db(self, mock_async_session):
        async def _boom(*a, **k):
            raise AssertionError('DB must not be queried on a cache hit')
        mock_async_session.execute = _boom
        with patch.object(model_resolver.rds, 'get', new=AsyncMock(return_value=json.dumps('model-cached'))):
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-cached'

    @pytest.mark.asyncio
    async def test_cache_hit_of_null_returns_none_without_db(self, mock_async_session):
        async def _boom(*a, **k):
            raise AssertionError('DB must not be queried on a cache hit')
        mock_async_session.execute = _boom
        with patch.object(model_resolver.rds, 'get', new=AsyncMock(return_value=json.dumps(None))):
            result = await model_resolver.resolve_logical_model('some-key')
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_miss_populates_cache(self, mock_async_session):
        rows = [_row(catalog_id='model-a', priority=1, input_per_million=1, output_per_million=1)]
        mock_async_session._execute_result = make_result(fetchall=rows)
        with patch.object(model_resolver.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(model_resolver.rds, 'setex', new=AsyncMock()) as mock_setex:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-a'
        mock_setex.assert_awaited_once_with(
            model_resolver._cache_key('some-key'), 30, json.dumps('model-a'),
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize('junk', ['1', '3.5', '[]', '{}', 'not json at all', ''])
    async def test_malformed_cached_value_is_not_trusted_falls_back_to_db(self, junk, mock_async_session):
        """A cached value that is neither a JSON null nor a non-empty JSON
        string must never be handed back as a resolution -- it must be
        treated as a cache miss and re-resolved from the DB."""
        rows = [_row(catalog_id='model-a', priority=1, input_per_million=1, output_per_million=1)]
        mock_async_session._execute_result = make_result(fetchall=rows)
        with patch.object(model_resolver.rds, 'get', new=AsyncMock(return_value=junk)), \
             patch.object(model_resolver.rds, 'setex', new=AsyncMock()):
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-a'

    @pytest.mark.asyncio
    async def test_db_error_returns_none_and_does_not_raise(self, mock_async_session):
        async def _boom(*a, **k):
            raise RuntimeError('db down')
        mock_async_session.execute = _boom
        with patch.object(model_resolver.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(model_resolver.rds, 'setex', new=AsyncMock()) as mock_setex:
            result = await model_resolver.resolve_logical_model('some-key')
        assert result is None
        mock_setex.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_redis_get_error_falls_through_to_db(self, mock_async_session):
        rows = [_row(catalog_id='model-a', priority=1, input_per_million=1, output_per_million=1)]
        mock_async_session._execute_result = make_result(fetchall=rows)
        with patch.object(model_resolver.rds, 'get', new=AsyncMock(side_effect=Exception('redis down'))), \
             patch.object(model_resolver.rds, 'setex', new=AsyncMock()):
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-a'

    @pytest.mark.asyncio
    async def test_redis_setex_error_does_not_raise(self, mock_async_session):
        rows = [_row(catalog_id='model-a', priority=1, input_per_million=1, output_per_million=1)]
        mock_async_session._execute_result = make_result(fetchall=rows)
        with patch.object(model_resolver.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(model_resolver.rds, 'setex', new=AsyncMock(side_effect=Exception('redis down'))):
            result = await model_resolver.resolve_logical_model('some-key')
        assert result == 'model-a'

    @pytest.mark.asyncio
    async def test_no_db_configured_returns_none(self):
        with patch.object(model_resolver, 'async_session', None), \
             patch.object(model_resolver.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(model_resolver.rds, 'setex', new=AsyncMock()):
            result = await model_resolver.resolve_logical_model('some-key')
        assert result is None


class TestInputGuard:
    @pytest.mark.asyncio
    async def test_empty_key_returns_none_without_touching_anything(self):
        with patch.object(model_resolver.rds, 'get', new=AsyncMock()) as mock_get:
            result = await model_resolver.resolve_logical_model('')
        assert result is None
        mock_get.assert_not_awaited()
