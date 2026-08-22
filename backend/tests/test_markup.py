"""Tests for the profit-percentage markup feature (owner request, 2026-08-22;
see docs/NEXT-SESSION.md section 12 and migrations/0030_markup_pct.sql).

Two levels, resolved the same way everywhere a price is produced: a
per-model override (model_catalog.markup_pct) wins when it is set (not
NULL); a model with no override inherits the global percentage (app_setting
row 'global_markup_pct'). content.py's get_global_markup_pct() /
resolve_markup_pct() / get_effective_markup_pct() / apply_markup() are the
single resolver every price consumer must call.

chat.py's billing path (_record_usage) is NOT owned by this change (see the
coordinator report) and still needs to be wired to call the same resolver --
that wiring could not be done or tested end-to-end here. TestSharedResolver
ContractForBilling below instead proves the CONTRACT the billing path must
follow: given the same (base price, model override, global pct) inputs, the
shared resolver functions produce one deterministic number, so once chat.py
is wired to call apply_markup()/get_effective_markup_pct() (not reimplement
the arithmetic) the billed price is mechanically guaranteed to match the
displayed one.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import content as content_mod
from tests.conftest import make_result, make_row


@pytest.fixture
def admin_ok():
    with patch('admin_catalog.admin_required', new=AsyncMock(return_value=True)):
        yield


class _MappingRow:
    """Minimal stand-in for a SQLAlchemy Row exposing `_mapping` (same
    helper as tests/test_catalog_endpoint.py) -- `dict(r._mapping)` is what
    `_load_catalog_rows()` uses to build each catalog dict."""

    def __init__(self, **kwargs):
        self._mapping = dict(kwargs)


def _catalog_row(**overrides):
    """A full model_catalog row shaped like `_load_catalog_rows()`'s SELECT,
    including markup_pct, so `_catalog_row_to_item` never hits a missing key."""
    row = dict(
        id='tencent-hy3', provider_model_id='tencent/hy3', provider='bynara',
        display_name='Tencent Hy3', description=None,
        modalities={'input': ['text'], 'output': ['text']}, capabilities=['chat'],
        recommended_for=[], context_window=32000, max_output_tokens=None,
        currency='IRT', input_per_million=1000, output_per_million=2000,
        cached_input_per_million=None, reasoning_per_million=None,
        price_version='v1', effective_from='2026-01-01T00:00:00Z',
        availability='available', audience=['consumer', 'developer'],
        rate_limit=None, deprecated_at=None, last_verified_at='2026-01-01T00:00:00Z',
        provenance='admin-approved', usd_input_per_million=0.01,
        usd_output_per_million=0.02, public_id=None, markup_pct=None,
    )
    row.update(overrides)
    return _MappingRow(**row)


# ── apply_markup: pure arithmetic, integer toman, no float drift ───────

class TestApplyMarkup:
    def test_zero_pct_is_a_noop(self):
        assert content_mod.apply_markup(1000, 0) == 1000

    def test_ten_percent_rises_by_exactly_that_proportion(self):
        assert content_mod.apply_markup(1000, 10) == 1100

    def test_result_is_always_a_plain_int(self):
        result = content_mod.apply_markup(333, 12.5)
        assert isinstance(result, int)
        assert not isinstance(result, bool)
        assert result == round(333 * 1.125)

    def test_none_base_treated_as_zero(self):
        assert content_mod.apply_markup(None, 50) == 0

    def test_none_pct_treated_as_zero(self):
        assert content_mod.apply_markup(1000, None) == 1000

    def test_malformed_base_treated_as_zero_not_a_crash(self):
        assert content_mod.apply_markup('not-a-number', 10) == 0


# ── resolve_markup_pct: per-model override vs. global inheritance ──────

class TestResolveMarkupPct:
    def test_no_override_inherits_global(self):
        assert content_mod.resolve_markup_pct(None, 15) == 15

    def test_override_wins_over_global(self):
        assert content_mod.resolve_markup_pct(5, 15) == 5

    def test_zero_override_is_a_real_override_not_missing(self):
        """0 is a deliberate override (e.g. "no markup on this one model
        even though the global is nonzero") and must NOT be treated as
        "no override" -- only None means inherit."""
        assert content_mod.resolve_markup_pct(0, 15) == 0

    def test_malformed_override_falls_back_to_global(self):
        assert content_mod.resolve_markup_pct('not-a-number', 15) == 15


# ── get_global_markup_pct: caching + fail-open-to-zero guarantee ───────

class TestGetGlobalMarkupPct:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value(self):
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value='12.5')):
            pct = await content_mod.get_global_markup_pct()
        assert pct == 12.5

    @pytest.mark.asyncio
    async def test_cache_miss_reads_db_and_populates_cache(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(value=20))
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(content_mod.rds, 'setex', new=AsyncMock()) as mock_setex:
            pct = await content_mod.get_global_markup_pct()
        assert pct == 20.0
        mock_setex.assert_awaited_once()
        assert mock_setex.await_args.args[0] == content_mod.MARKUP_CACHE_KEY

    @pytest.mark.asyncio
    async def test_no_row_in_db_defaults_to_zero(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(content_mod.rds, 'setex', new=AsyncMock()):
            pct = await content_mod.get_global_markup_pct()
        assert pct == 0.0

    @pytest.mark.asyncio
    async def test_redis_read_failure_falls_through_to_db_not_straight_to_zero(self, mock_async_session):
        """Mirrors _get_exchange_rate's existing idiom: a cache-read error
        alone must not throw away a real DB-backed value."""
        mock_async_session._execute_result = make_result(fetchone=make_row(value=7))
        with patch.object(content_mod.rds, 'get', new=AsyncMock(side_effect=Exception('redis down'))), \
             patch.object(content_mod.rds, 'setex', new=AsyncMock()):
            pct = await content_mod.get_global_markup_pct()
        assert pct == 7.0

    @pytest.mark.asyncio
    async def test_db_error_degrades_to_zero_never_a_default_markup(self, mock_async_session):
        async def _boom(*a, **k):
            raise RuntimeError('db down')
        mock_async_session.execute = _boom
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(content_mod.rds, 'setex', new=AsyncMock()):
            pct = await content_mod.get_global_markup_pct()
        assert pct == 0.0

    @pytest.mark.asyncio
    async def test_no_db_configured_degrades_to_zero(self):
        with patch.object(content_mod, 'async_session', None), \
             patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(content_mod.rds, 'setex', new=AsyncMock()):
            pct = await content_mod.get_global_markup_pct()
        assert pct == 0.0


class TestGetEffectiveMarkupPct:
    @pytest.mark.asyncio
    async def test_model_override_wins_even_if_global_is_nonzero(self):
        """The per-model override must win in the final resolution
        regardless of what the (still-fetched) global percentage is --
        proven here by making the global lookup return an obviously
        different value the assertion would catch if it leaked through."""
        with patch.object(content_mod, 'get_global_markup_pct', new=AsyncMock(return_value=999)):
            pct = await content_mod.get_effective_markup_pct(5)
        assert pct == 5

    @pytest.mark.asyncio
    async def test_no_override_uses_the_global(self):
        with patch.object(content_mod, 'get_global_markup_pct', new=AsyncMock(return_value=15)):
            pct = await content_mod.get_effective_markup_pct(None)
        assert pct == 15


# ── _catalog_row_to_item: per-model override vs. global, end to end ────

class TestCatalogRowToItemMarkup:
    def test_no_override_applies_the_global(self):
        row = _catalog_row(input_per_million=1000, output_per_million=2000, markup_pct=None)
        item = content_mod._catalog_row_to_item(row._mapping, 126488, 10)
        assert item['pricing']['inputPerMillion'] == 1100
        assert item['pricing']['outputPerMillion'] == 2200

    def test_per_model_override_wins_over_global(self):
        row = _catalog_row(input_per_million=1000, output_per_million=2000, markup_pct=50)
        item = content_mod._catalog_row_to_item(row._mapping, 126488, 10)
        assert item['pricing']['inputPerMillion'] == 1500
        assert item['pricing']['outputPerMillion'] == 3000

    def test_zero_global_is_a_strict_no_op_on_prices(self):
        """The migration seeds the global at 0 specifically so applying it
        changes nothing until an admin opts in."""
        row = _catalog_row(input_per_million=1234, output_per_million=5678, markup_pct=None)
        item = content_mod._catalog_row_to_item(row._mapping, 126488, 0)
        assert item['pricing']['inputPerMillion'] == 1234
        assert item['pricing']['outputPerMillion'] == 5678

    def test_prices_stay_integer_toman(self):
        row = _catalog_row(input_per_million=333, output_per_million=777, markup_pct=12.5)
        item = content_mod._catalog_row_to_item(row._mapping, 126488, 0)
        assert isinstance(item['pricing']['inputPerMillion'], int)
        assert isinstance(item['pricing']['outputPerMillion'], int)


# ── /catalog/models end-to-end: global + per-model override ────────────

class TestCatalogModelsEndpointMarkup:
    def test_global_markup_applies_to_unoverridden_model(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[
            _catalog_row(id='m1', input_per_million=1000, output_per_million=2000, markup_pct=None)
        ])
        with patch('content._get_exchange_rate', new=AsyncMock(return_value=(126488, 0))), \
             patch('content.get_global_markup_pct', new=AsyncMock(return_value=20)):
            resp = client.get('/catalog/models')
        assert resp.status_code == 200
        item = resp.json()['data'][0]
        assert item['pricing']['inputPerMillion'] == 1200
        assert item['pricing']['outputPerMillion'] == 2400

    def test_per_model_override_ignores_the_global(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[
            _catalog_row(id='m1', input_per_million=1000, output_per_million=2000, markup_pct=5)
        ])
        with patch('content._get_exchange_rate', new=AsyncMock(return_value=(126488, 0))), \
             patch('content.get_global_markup_pct', new=AsyncMock(return_value=20)):
            resp = client.get('/catalog/models')
        assert resp.status_code == 200
        item = resp.json()['data'][0]
        assert item['pricing']['inputPerMillion'] == 1050
        assert item['pricing']['outputPerMillion'] == 2100


# ── The critical requirement: displayed price and billed price agree ───

class TestSharedResolverContractForBilling:
    """The owner's explicit ask (NEXT-SESSION.md section 12): the percentage
    must land on both the displayed price and the billed price identically.

    chat.py's `_record_usage` (billing) is outside this change's file
    ownership, so it cannot be edited or exercised end-to-end here -- see
    the coordinator report for the exact change still required there
    (import content.get_effective_markup_pct/apply_markup and apply them to
    the price_row it already reads by provider_model_id). What CAN be
    proven here is that the shared resolver is deterministic and pure: for
    a fixed (base price, model override, global pct), calling the same two
    functions content.py's display path calls gives byte-identical output
    to what chat.py's billing path would get by calling the SAME functions
    with the SAME inputs -- which is the actual guarantee the "one number,
    not two parallel implementations" requirement rests on.
    """

    @pytest.mark.asyncio
    async def test_display_and_billing_style_lookups_agree_no_override(self):
        base_input, base_output = 1000, 2000
        global_pct = 17

        # "Display" side: content.py's catalog path resolves per-row via
        # resolve_markup_pct() against an already-fetched global.
        display_pct = content_mod.resolve_markup_pct(None, global_pct)
        display_input = content_mod.apply_markup(base_input, display_pct)
        display_output = content_mod.apply_markup(base_output, display_pct)

        # "Billing" side: the single-model entry point chat.py's
        # _record_usage should call once it is wired up (get_effective_markup_pct).
        with patch.object(content_mod, 'get_global_markup_pct', new=AsyncMock(return_value=global_pct)):
            billed_pct = await content_mod.get_effective_markup_pct(None)
        billed_input = content_mod.apply_markup(base_input, billed_pct)
        billed_output = content_mod.apply_markup(base_output, billed_pct)

        assert display_input == billed_input == 1170
        assert display_output == billed_output == 2340

    @pytest.mark.asyncio
    async def test_display_and_billing_style_lookups_agree_with_override(self):
        base_input, base_output = 1000, 2000
        model_override = 40
        global_pct = 17  # must be ignored -- override wins

        display_pct = content_mod.resolve_markup_pct(model_override, global_pct)
        display_input = content_mod.apply_markup(base_input, display_pct)

        with patch.object(content_mod, 'get_global_markup_pct', new=AsyncMock(return_value=global_pct)):
            billed_pct = await content_mod.get_effective_markup_pct(model_override)
        billed_input = content_mod.apply_markup(base_input, billed_pct)

        assert display_input == billed_input == 1400


# ── Admin API (admin_catalog.py): global + per-model read/write ────────

class TestAdminMarkupGlobal:
    def test_get_requires_admin(self, client):
        resp = client.get('/admin/markup/global')
        assert resp.status_code == 401

    def test_get_returns_current_global_pct(self, client, admin_ok):
        # The endpoint does `from content import get_global_markup_pct`
        # locally at call time, so patching content's module-level name is
        # what actually takes effect (not an admin_catalog-level name).
        with patch.object(content_mod, 'get_global_markup_pct', new=AsyncMock(return_value=12.5)):
            resp = client.get('/admin/markup/global')
        assert resp.status_code == 200
        assert resp.json() == {'markup_pct': 12.5}

    def test_set_requires_admin(self, client):
        resp = client.post('/admin/markup/global', json={'markup_pct': 10})
        assert resp.status_code == 401

    def test_set_writes_app_setting_and_invalidates_caches(self, client, admin_ok, mock_async_session):
        with patch.object(content_mod.rds, 'delete', new=AsyncMock()) as mock_delete:
            resp = client.post('/admin/markup/global', json={'markup_pct': 25})
        assert resp.status_code == 200
        assert resp.json() == {'status': 'ok', 'markup_pct': 25.0}
        mock_delete.assert_awaited_once_with(
            'cache:markup:global_pct', 'cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing'
        )

    def test_set_rejects_negative_pct(self, client, admin_ok, mock_async_session):
        resp = client.post('/admin/markup/global', json={'markup_pct': -5})
        assert resp.status_code == 400

    def test_set_rejects_non_numeric_pct(self, client, admin_ok, mock_async_session):
        resp = client.post('/admin/markup/global', json={'markup_pct': 'lots'})
        assert resp.status_code == 400


class TestAdminMarkupModels:
    def test_list_requires_admin(self, client):
        resp = client.get('/admin/markup/models')
        assert resp.status_code == 401

    def test_list_returns_rows(self, client, admin_ok, mock_async_session):
        # admin_catalog.list_model_markups does `dict(r._mapping)` -- a plain
        # make_row() MagicMock's auto-mocked `_mapping` isn't dict-like (see
        # tests/test_catalog_endpoint.py's _MappingRow for the same issue).
        mock_async_session._execute_result = make_result(fetchall=[
            _MappingRow(id='m1', display_name='Model One', input_per_million=1000,
                        output_per_million=2000, markup_pct=None),
        ])
        resp = client.get('/admin/markup/models')
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]['id'] == 'm1'
        assert body[0]['markup_pct'] is None

    def test_set_single_model_override(self, client, admin_ok, mock_async_session):
        async def _execute(stmt, params=None, *a, **k):
            result = make_result(fetchone=None)
            result.rowcount = 1
            return result
        mock_async_session.execute = _execute
        resp = client.post('/admin/markup/models/m1', json={'markup_pct': 8})
        assert resp.status_code == 200
        assert resp.json()['markup_pct'] == 8.0

    def test_set_single_model_override_404_for_unknown_model(self, client, admin_ok, mock_async_session):
        async def _execute(stmt, params=None, *a, **k):
            result = make_result(fetchone=None)
            result.rowcount = 0
            return result
        mock_async_session.execute = _execute
        resp = client.post('/admin/markup/models/does-not-exist', json={'markup_pct': 8})
        assert resp.status_code == 404

    def test_clear_single_model_override_accepts_null(self, client, admin_ok, mock_async_session):
        async def _execute(stmt, params=None, *a, **k):
            assert params['p'] is None, 'markup_pct: null must clear the override, not reject it'
            result = make_result(fetchone=None)
            result.rowcount = 1
            return result
        mock_async_session.execute = _execute
        resp = client.post('/admin/markup/models/m1', json={'markup_pct': None})
        assert resp.status_code == 200
        assert resp.json()['markup_pct'] is None

    def test_set_single_model_rejects_negative(self, client, admin_ok, mock_async_session):
        resp = client.post('/admin/markup/models/m1', json={'markup_pct': -1})
        assert resp.status_code == 400

    def test_bulk_set_requires_ids(self, client, admin_ok, mock_async_session):
        resp = client.post('/admin/markup/models/bulk', json={'markup_pct': 10})
        assert resp.status_code == 400

    def test_bulk_set_updates_many(self, client, admin_ok, mock_async_session):
        async def _execute(stmt, params=None, *a, **k):
            result = make_result(fetchone=None)
            result.rowcount = 3
            return result
        mock_async_session.execute = _execute
        with patch.object(content_mod.rds, 'delete', new=AsyncMock()) as mock_delete:
            resp = client.post('/admin/markup/models/bulk', json={'ids': ['m1', 'm2', 'm3'], 'markup_pct': 15})
        assert resp.status_code == 200
        body = resp.json()
        assert body['updated'] == 3
        mock_delete.assert_awaited_once_with('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')

    def test_bulk_set_rejects_negative(self, client, admin_ok, mock_async_session):
        resp = client.post('/admin/markup/models/bulk', json={'ids': ['m1'], 'markup_pct': -10})
        assert resp.status_code == 400
