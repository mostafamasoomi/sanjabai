"""Margin guard wiring (Phase F1).

`services/margin.py` shipped with `check_margin()` fully unit-tested and
ZERO production callers -- deliberate debt recorded in its own module
docstring ("meant to be called wherever a model's listed price is set or
an upstream is approved"). These tests are the wiring: they pin the
decision points in admin_pricing.py / admin_catalog.py where a model's
price or availability is chosen, and the DB-facing `refuse_if_loss_making`
guard those decision points must consult BEFORE writing, enforcing the
project law that:

  * «هیچ درخواستی نباید ضررده باشد» -- a listed price under MIN_MARGIN_PCT
    over upstream cost is REFUSED (HTTP 400, Persian detail naming the
    numbers), never silently accepted and never auto-corrected.
  * A model whose upstream cost is unknown is costed at the CEILING of its
    upstream's price band, never the average.
  * Integer Toman throughout. Nothing here multiplies or divides by 10.
  * Every refusal and every accepted change lands in audit_log via the
    existing `_write_audit_log` helper.

Split out of the original tests/test_margin_guard.py (which grew past the
500-line cap) -- the pure pricing-math unit tests for is_paid_upstream(),
upstream_cost_toman(), and evaluate_price() now live in
tests/test_margin_guard_pricing.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services import probe_gate as probe_gate_mod

from services import margin as margin_mod

import content as content_mod
from tests.conftest import make_result, make_row

import admin_catalog as admin_catalog_mod
import admin_pricing as admin_pricing_mod


@pytest.fixture(autouse=True)
def _probe_gate_allows():
    """Isolate the margin guard from the probe gate.

    Both gates now run on the endpoints this file exercises, and the probe
    gate runs FIRST (services/probe_gate.py -- «مدل فقط بعد از پروب زنده
    موفق ارائه می‌شود»). Without this, every test here that expects a
    margin refusal gets a probe refusal instead: right status, wrong
    reason, wrong audit event. The probe gate has its own file --
    tests/test_admin_probe_gate.py -- so here it always says yes.
    """
    allow = AsyncMock(return_value=None)
    with patch.object(probe_gate_mod, 'refuse_if_unprobed', new=allow):
        yield


# ── The DB-facing guard: refuse_if_loss_making ──────────────────────────


def _catalog_row(**overrides):
    """A model_catalog row shaped like refuse_if_loss_making's SELECT."""
    row = dict(
        id='openrouter/gpt-5', upstream='openrouter',
        usd_input_per_million=3.0, usd_output_per_million=15.0,
        input_per_million=574_200, output_per_million=2_871_000,
        markup_pct=None, ceiling_usd_input=15.0, ceiling_usd_output=75.0,
    )
    row.update(overrides)
    return make_row(**row)


class _Session:
    """Async session double that records SQL and replays queued results."""

    def __init__(self, rows, raises=False):
        self.rows = rows
        self.raises = raises
        self.sql = []

    async def execute(self, stmt, params=None, *a, **k):
        self.sql.append(str(stmt))
        if self.raises:
            raise RuntimeError('database is on fire')
        return make_result(fetchall=self.rows)


@pytest.fixture
def priced_world():
    """Global markup 100%, USD at 191,400 Toman."""
    with patch.object(content_mod, 'get_global_markup_pct', new=AsyncMock(return_value=100.0)), \
         patch.object(content_mod, '_get_exchange_rate', new=AsyncMock(return_value=(191_400.0, 0))):
        yield


@pytest.mark.anyio
class TestRefuseIfLossMaking:
    @pytest.fixture
    def anyio_backend(self):
        return 'asyncio'

    async def test_free_upstream_rows_are_waved_through(self, priced_world):
        """Production today: every enabled upstream is the owner's own
        infrastructure, so the guard must cost nothing and refuse nothing."""
        session = _Session([_catalog_row(id='kr/x', upstream='ninerouter',
                                         input_per_million=1, output_per_million=1)])
        assert await margin_mod.refuse_if_loss_making(session, ['kr/x']) is None

    async def test_free_upstream_never_touches_the_exchange_rate(self):
        """No paid row means no USD conversion is needed at all -- a tgju
        outage must not be able to block ordinary catalog admin."""
        rate = AsyncMock(side_effect=AssertionError('exchange rate must not be fetched'))
        with patch.object(content_mod, '_get_exchange_rate', new=rate):
            session = _Session([_catalog_row(upstream='litellm')])
            assert await margin_mod.refuse_if_loss_making(session, ['openrouter/gpt-5']) is None

    async def test_paid_upstream_at_a_healthy_margin_passes(self, priced_world):
        # base 574,200 + 100% markup = 1,148,400 listed vs 574,200 cost = 100%
        session = _Session([_catalog_row()])
        assert await margin_mod.refuse_if_loss_making(session, ['openrouter/gpt-5']) is None

    async def test_paid_upstream_at_zero_markup_is_refused(self):
        """The price sync writes input_per_million = usd * rate exactly, i.e.
        cost price. With no markup that is a 0% margin -- the loss-making
        configuration the guard exists to catch."""
        with patch.object(content_mod, 'get_global_markup_pct', new=AsyncMock(return_value=0.0)), \
             patch.object(content_mod, '_get_exchange_rate', new=AsyncMock(return_value=(191_400.0, 0))):
            session = _Session([_catalog_row()])
            refusal = await margin_mod.refuse_if_loss_making(session, ['openrouter/gpt-5'])
        assert refusal is not None
        assert 'ضررده' in refusal.detail

    async def test_proposed_base_price_overrides_the_stored_one(self, priced_world):
        """The set-price call site must be judged on the price it is about
        to write, not on the row still in the table."""
        session = _Session([_catalog_row()])
        refusal = await margin_mod.refuse_if_loss_making(
            session, ['openrouter/gpt-5'], input_per_million=1000, output_per_million=2000,
        )
        assert refusal is not None
        assert '2,000' in refusal.detail or '1,000' in refusal.detail

    async def test_proposed_markup_override_is_applied(self, priced_world):
        """Lowering a model's markup is a price decision and must be
        guarded, or a model approved at 100% can be walked down to 0%."""
        session = _Session([_catalog_row()])
        refusal = await margin_mod.refuse_if_loss_making(
            session, ['openrouter/gpt-5'], markup_pct=0.0, markup_pct_provided=True,
        )
        assert refusal is not None

    async def test_clearing_a_markup_override_falls_back_to_the_global(self, priced_world):
        """markup_pct: null means "inherit the global" (100% here), which
        still clears the floor."""
        session = _Session([_catalog_row(markup_pct=0)])
        assert await margin_mod.refuse_if_loss_making(
            session, ['openrouter/gpt-5'], markup_pct=None, markup_pct_provided=True,
        ) is None

    async def test_per_model_markup_override_wins_over_the_global(self):
        with patch.object(content_mod, 'get_global_markup_pct', new=AsyncMock(return_value=500.0)), \
             patch.object(content_mod, '_get_exchange_rate', new=AsyncMock(return_value=(191_400.0, 0))):
            session = _Session([_catalog_row(markup_pct=0)])
            refusal = await margin_mod.refuse_if_loss_making(session, ['openrouter/gpt-5'])
        assert refusal is not None, 'a 0% per-model override must not inherit the safe global'

    async def test_unknown_usd_price_uses_the_joined_category_ceiling(self, priced_world):
        session = _Session([_catalog_row(usd_input_per_million=None, ceiling_usd_input=15.0)])
        refusal = await margin_mod.refuse_if_loss_making(session, ['openrouter/gpt-5'])
        assert refusal is not None
        assert '2,871,000' in refusal.detail

    async def test_ids_not_in_the_catalog_are_not_invented(self, priced_world):
        session = _Session([])
        assert await margin_mod.refuse_if_loss_making(session, ['nope']) is None

    async def test_empty_id_list_short_circuits_without_a_query(self, priced_world):
        session = _Session([_catalog_row()])
        assert await margin_mod.refuse_if_loss_making(session, []) is None
        assert session.sql == []

    async def test_a_failing_query_refuses_rather_than_waving_through(self, priced_world):
        """Fail closed: if the guard cannot prove the price is safe, it is
        not safe. Never raises on the caller."""
        session = _Session([], raises=True)
        refusal = await margin_mod.refuse_if_loss_making(session, ['openrouter/gpt-5'])
        assert refusal is not None
        assert 'ضررده' in refusal.detail or 'بررسی' in refusal.detail

    async def test_the_first_offender_in_a_bulk_batch_is_reported(self, priced_world):
        session = _Session([
            _catalog_row(id='safe/one'),
            _catalog_row(id='bad/two', markup_pct=0),
        ])
        refusal = await margin_mod.refuse_if_loss_making(session, ['safe/one', 'bad/two'])
        assert refusal is not None
        assert refusal.model_id == 'bad/two'


# ── The five decision points that must consult the guard ────────────────
#
# Every admin route that can make a model sellable, or change what it sells
# for, has to go through refuse_if_loss_making BEFORE it writes. Missing any
# one of them is a bypass: a model approved at a safe margin could still be
# walked down to a loss-making one through the endpoint that was left out.


@pytest.fixture
def admin_ok():
    with patch('admin_catalog.admin_required', new=AsyncMock(return_value=True)), \
         patch('admin.admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def guard_refuses():
    """Guard says no. Records the kwargs each call site passed it."""
    refusal = margin_mod.PriceRefusal(
        model_id='openrouter/gpt-5',
        detail='فروش «openrouter/gpt-5» ضررده است: … هیچ درخواستی نباید ضررده باشد.',
        audit={'model': 'openrouter/gpt-5', 'upstream': 'openrouter', 'token_kind': 'input',
               'listed_per_million': 1, 'upstream_cost_per_million': 574_200,
               'margin_pct': -99.9, 'min_margin_pct': 20, 'currency': 'IRT'},
    )
    calls = []

    async def _guard(session, ids, **kwargs):
        calls.append({'ids': list(ids), **kwargs})
        return refusal

    with patch.object(margin_mod, 'refuse_if_loss_making', new=_guard):
        yield calls


@pytest.fixture
def guard_allows():
    calls = []

    async def _guard(session, ids, **kwargs):
        calls.append({'ids': list(ids), **kwargs})
        return None

    with patch.object(margin_mod, 'refuse_if_loss_making', new=_guard):
        yield calls


@pytest.fixture
def rowcount_1(mock_async_session):
    """Every UPDATE in these endpoints reports one affected row."""
    executed = []

    async def _execute(stmt, params=None, *a, **k):
        executed.append((str(stmt), params))
        result = make_result(fetchone=make_row(availability='disabled'))
        result.rowcount = 1
        return result

    mock_async_session.execute = _execute
    mock_async_session._executed = executed
    return mock_async_session


def _updates(session):
    return [sql for sql, _ in session._executed if 'UPDATE model_catalog' in sql]


class TestSetPricingIsGuarded:
    """POST /admin/pricing -- the set-price decision point."""

    def test_refusal_returns_400_with_the_persian_detail(self, client, admin_ok, rowcount_1, guard_refuses):
        resp = client.post('/admin/pricing', json={
            'model': 'openrouter/gpt-5', 'input_per_million': 1, 'output_per_million': 1})
        assert resp.status_code == 400
        assert 'ضررده' in resp.json()['detail']

    def test_refusal_writes_nothing(self, client, admin_ok, rowcount_1, guard_refuses):
        client.post('/admin/pricing', json={
            'model': 'openrouter/gpt-5', 'input_per_million': 1, 'output_per_million': 1})
        assert _updates(rowcount_1) == [], 'a refused price must not reach model_catalog'

    def test_guard_is_asked_about_the_proposed_price_not_the_stored_one(
            self, client, admin_ok, rowcount_1, guard_refuses):
        client.post('/admin/pricing', json={
            'model': 'openrouter/gpt-5', 'input_per_million': 7, 'output_per_million': 9})
        assert guard_refuses[0]['ids'] == ['openrouter/gpt-5']
        assert guard_refuses[0]['input_per_million'] == 7
        assert guard_refuses[0]['output_per_million'] == 9

    def test_refusal_is_audited_with_the_numbers(self, client, admin_ok, rowcount_1, guard_refuses):
        with patch.object(admin_pricing_mod, '_write_audit_log', new=AsyncMock()) as audit:
            client.post('/admin/pricing', json={
                'model': 'openrouter/gpt-5', 'input_per_million': 1, 'output_per_million': 1})
        audit.assert_awaited()
        action, kwargs = audit.await_args.args[0], audit.await_args.kwargs
        assert action == 'admin.margin.refused'
        assert kwargs['details']['upstream_cost_per_million'] == 574_200

    def test_a_safe_price_still_goes_through(self, client, admin_ok, rowcount_1, guard_allows):
        with patch.object(admin_pricing_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/pricing', json={
                'model': 'openrouter/gpt-5', 'input_per_million': 1_000_000, 'output_per_million': 2_000_000})
        assert resp.status_code == 200
        assert _updates(rowcount_1), 'an accepted price must still be written'


class TestToggleModelIsGuarded:
    """POST /admin/models/{id}/toggle -- the single-model approve decision.

    Turning one model back on is the same decision as the bulk endpoint
    makes; leaving it unguarded would be a one-click bypass.
    """

    def test_enabling_a_loss_making_model_is_refused(self, client, admin_ok, rowcount_1, guard_refuses):
        resp = client.post('/admin/models/openrouter/gpt-5/toggle')
        assert resp.status_code == 400
        assert 'ضررده' in resp.json()['detail']
        assert _updates(rowcount_1) == []

    def test_disabling_is_never_blocked(self, client, admin_ok, mock_async_session, guard_refuses):
        """Taking a model OFF sale can never be loss-making, and must stay
        possible even while the guard is refusing to sell it."""
        async def _execute(stmt, params=None, *a, **k):
            result = make_result(fetchone=make_row(availability='available'))
            result.rowcount = 1
            return result

        mock_async_session.execute = _execute
        with patch.object(admin_pricing_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/models/openrouter/gpt-5/toggle')
        assert resp.status_code == 200
        assert resp.json()['availability'] == 'disabled'
        assert guard_refuses == [], 'no margin question to ask when withdrawing a model'


class TestBulkAvailabilityIsGuarded:
    """POST /admin/models/bulk-availability -- the bulk approve decision."""

    def test_bulk_enable_is_refused_when_any_model_is_loss_making(
            self, client, admin_ok, rowcount_1, guard_refuses):
        resp = client.post('/admin/models/bulk-availability', json={
            'ids': ['a', 'openrouter/gpt-5'], 'availability': 'available'})
        assert resp.status_code == 400
        assert 'ضررده' in resp.json()['detail']
        assert _updates(rowcount_1) == [], 'the whole batch is refused, not partially applied'

    def test_the_guard_sees_every_id_in_the_batch(self, client, admin_ok, rowcount_1, guard_refuses):
        client.post('/admin/models/bulk-availability', json={
            'ids': ['a', 'b', 'c'], 'availability': 'available'})
        assert guard_refuses[0]['ids'] == ['a', 'b', 'c']

    @pytest.mark.parametrize('availability', ['disabled', 'maintenance', 'degraded'])
    def test_non_selling_states_are_not_guarded(self, client, admin_ok, rowcount_1,
                                                guard_refuses, availability):
        with patch.object(admin_catalog_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/models/bulk-availability', json={
                'ids': ['a'], 'availability': availability})
        assert resp.status_code == 200
        assert guard_refuses == []

    def test_refusal_is_audited(self, client, admin_ok, rowcount_1, guard_refuses):
        with patch.object(admin_catalog_mod, '_write_audit_log', new=AsyncMock()) as audit:
            client.post('/admin/models/bulk-availability', json={
                'ids': ['openrouter/gpt-5'], 'availability': 'available'})
        assert audit.await_args.args[0] == 'admin.margin.refused'


class TestMarkupEndpointsAreGuarded:
    """Markup is the second half of the listed price. An unguarded markup
    endpoint would let an approved model be walked down to 0% afterwards."""

    def test_single_model_markup_cut_is_refused(self, client, admin_ok, rowcount_1, guard_refuses):
        resp = client.post('/admin/markup/models/openrouter/gpt-5', json={'markup_pct': 0})
        assert resp.status_code == 400
        assert _updates(rowcount_1) == []
        assert guard_refuses[0]['markup_pct'] == 0
        assert guard_refuses[0]['markup_pct_provided'] is True

    def test_clearing_a_markup_override_is_still_guarded(self, client, admin_ok, rowcount_1, guard_refuses):
        """markup_pct: null hands the model back to the global percentage,
        which may itself be under the floor -- still a price decision."""
        resp = client.post('/admin/markup/models/openrouter/gpt-5', json={'markup_pct': None})
        assert resp.status_code == 400
        assert guard_refuses[0]['markup_pct_provided'] is True

    def test_bulk_markup_cut_is_refused(self, client, admin_ok, rowcount_1, guard_refuses):
        resp = client.post('/admin/markup/models/bulk', json={'ids': ['a', 'b'], 'markup_pct': 0})
        assert resp.status_code == 400
        assert guard_refuses[0]['ids'] == ['a', 'b']
        assert _updates(rowcount_1) == []

    def test_a_safe_markup_still_goes_through(self, client, admin_ok, rowcount_1, guard_allows):
        with patch.object(admin_catalog_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/markup/models/openrouter/gpt-5', json={'markup_pct': 100})
        assert resp.status_code == 200
        assert _updates(rowcount_1)


class TestSetUpstreamIsGuarded:
    """POST /admin/models/{id}/set-upstream.

    Moving a model from a free upstream to a paid one turns an upstream
    cost of zero into a real one WITHOUT touching the price -- so a price
    that was fine a moment ago can become loss-making by this route alone.
    The guard has to be asked about the upstream being moved TO, not the
    one still stored on the row.
    """

    def test_moving_onto_a_paid_upstream_is_refused_when_loss_making(
            self, client, admin_ok, rowcount_1, guard_refuses):
        with patch('providers.configured_providers', return_value=_fake_providers()):
            resp = client.post('/admin/models/kr/gpt-5/set-upstream',
                               json={'upstream': 'openrouter'})
        assert resp.status_code == 400
        assert 'ضررده' in resp.json()['detail']
        assert _updates(rowcount_1) == []

    def test_guard_is_asked_about_the_target_upstream(self, client, admin_ok, rowcount_1, guard_refuses):
        with patch('providers.configured_providers', return_value=_fake_providers()):
            client.post('/admin/models/kr/gpt-5/set-upstream', json={'upstream': 'openrouter'})
        assert guard_refuses[0]['upstream'] == 'openrouter'

    def test_moving_onto_a_free_upstream_still_works(self, client, admin_ok, rowcount_1, guard_allows):
        with patch('providers.configured_providers', return_value=_fake_providers()), \
             patch.object(admin_catalog_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/models/kr/gpt-5/set-upstream', json={'upstream': 'ninerouter'})
        assert resp.status_code == 200
        assert _updates(rowcount_1)


def _fake_providers():
    from providers import Provider
    return [Provider(name='ninerouter', base_url='http://x', api_key=''),
            Provider(name='openrouter', base_url='http://y', api_key='k')]


class TestUpstreamOverrideInTheGuard:
    """refuse_if_loss_making must judge the proposed upstream."""

    @pytest.fixture
    def anyio_backend(self):
        return 'asyncio'

    @pytest.mark.anyio
    async def test_a_free_row_moved_to_a_paid_upstream_is_costed(self, priced_world):
        """Stored upstream is free (cost 0, always fine); the proposed one
        is paid, and at 0% markup the stored price is exactly cost."""
        with patch.object(content_mod, 'get_global_markup_pct', new=AsyncMock(return_value=0.0)):
            session = _Session([_catalog_row(upstream='ninerouter')])
            refusal = await margin_mod.refuse_if_loss_making(
                session, ['openrouter/gpt-5'], upstream='openrouter')
        assert refusal is not None
        assert refusal.audit['upstream'] == 'openrouter'
