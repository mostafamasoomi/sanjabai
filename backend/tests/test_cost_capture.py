"""Guards for services/cost_capture.py -- what a request cost US.

`usage_events.charged_amount` has always recorded what the user paid.
Migration 0048 added the other half: what we paid upstream. These tests exist
because every failure mode of that second number is silent. A cost rounded
the wrong way, a package-covered request recorded as free, or a NULL that a
reader folds to zero all produce a dashboard that looks *better* than
reality, never worse -- nothing crashes, nobody notices, and the wrong number
is the one decisions get made on.

House convention (test_billing_loss_paths.py, test_entitlements.py): assert
against what the production code actually does, never against a Python
re-implementation of it. Every test here drives the real
`services.cost_capture` functions or the real `chat_billing._record_usage`.
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock

import pytest

import chat_billing
import services.cost_capture as cc


# ═══════════════════════════════════════════════════════════════════════
# Fakes
# ═══════════════════════════════════════════════════════════════════════

class _CeilingSession:
    """Session double whose only job is answering the category-ceiling query.

    Returns rows shaped like cost_capture's own GROUP BY: (upstream,
    ceiling_usd_input, ceiling_usd_output).
    """

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = 0

    async def execute(self, stmt, params=None, *a, **k):
        self.calls += 1
        result = MagicMock()
        result.fetchall.return_value = self.rows
        return result


def _ceiling_row(upstream, usd_in, usd_out):
    return types.SimpleNamespace(
        upstream=upstream, ceiling_usd_input=usd_in, ceiling_usd_output=usd_out,
    )


@pytest.fixture(autouse=True)
def _clear_ceiling_cache():
    """The ceiling cache is module state shared across tests.

    Without this reset a test that populates it leaks into the next one, and
    the 'unknown' cases would pass for the wrong reason -- they would be
    reading another test's ceilings instead of proving the absence of any.
    """
    cc._CEILING_CACHE = {}
    cc._CEILING_CACHE_LOADED_AT = 0.0
    yield
    cc._CEILING_CACHE = {}
    cc._CEILING_CACHE_LOADED_AT = 0.0


@pytest.fixture
def fx(monkeypatch):
    """Pin the exchange rate so cost arithmetic is hand-checkable."""
    def _set(rate=100_000.0):
        import content
        monkeypatch.setattr(content, '_get_exchange_rate', AsyncMock(return_value=(rate, 0)))
        return rate
    return _set


# ═══════════════════════════════════════════════════════════════════════
# Section 1: the arithmetic rounds UP
# ═══════════════════════════════════════════════════════════════════════

class TestRoundingDirection:
    """Understating cost is the one rounding direction that hides a loss."""

    def test_a_fraction_of_a_toman_costs_one_toman(self):
        # 1 token at 1 toman per MILLION tokens is 0.000001 toman. Rounding
        # to nearest (or down) records 0 -- a request that cost us something
        # filed as free. Only ceil records the truth that it was not free.
        assert cc._event_cost_toman(1, 1) == 1

    def test_exact_multiples_are_not_inflated(self):
        # Ceil must not become "always add one": 2,000,000 tokens at 3
        # toman/M is exactly 6, and reporting 7 would overstate every
        # ordinary request.
        assert cc._event_cost_toman(2_000_000, 3) == 6

    def test_just_over_a_boundary_rounds_up_not_to_nearest(self):
        # 1,000,001 tokens at 1 toman/M is 1.000001. Half-up -- what
        # services/metering._part does for the USER's charge -- gives 1.
        # Cost must give 2. This is the assertion that goes red if someone
        # "simplifies" this to reuse _part.
        assert cc._event_cost_toman(1_000_001, 1) == 2

    def test_zero_and_negative_inputs_are_free_not_negative(self):
        assert cc._event_cost_toman(0, 5_000) == 0
        assert cc._event_cost_toman(1_000, 0) == 0
        assert cc._event_cost_toman(-5, 5_000) == 0


# ═══════════════════════════════════════════════════════════════════════
# Section 2: the basis ladder
# ═══════════════════════════════════════════════════════════════════════

class TestBasisLadder:

    @pytest.mark.asyncio
    async def test_listed_price_is_used_when_present(self, fx):
        rate = fx(100_000.0)
        session = _CeilingSession()
        snap = await cc.capture_upstream_cost(
            session, upstream='openrouter',
            input_tokens=1_000_000, output_tokens=0,
            usd_input_per_million=2.0, usd_output_per_million=4.0,
        )
        assert snap.basis == 'listed'
        # 2 USD/M * 100,000 toman/USD = 200,000 toman/M; 1M tokens => 200,000.
        assert snap.cost_toman == 200_000
        assert snap.fx_rate_irt == rate
        assert (snap.usd_input_per_million, snap.usd_output_per_million) == (2.0, 4.0)
        # No ceiling query was needed: both sides had their own price.
        assert session.calls == 0

    @pytest.mark.asyncio
    async def test_missing_price_falls_back_to_the_category_ceiling(self, fx):
        fx(100_000.0)
        session = _CeilingSession([_ceiling_row('openrouter', 9.0, 30.0)])
        snap = await cc.capture_upstream_cost(
            session, upstream='openrouter',
            input_tokens=1_000_000, output_tokens=0,
            usd_input_per_million=None, usd_output_per_million=None,
        )
        # Project law: an unpriced model is costed at the MAXIMUM in its
        # category, never the average -- assuming the average is how an
        # expensive unpriced model gets quietly sold at a loss.
        assert snap.basis == 'category_ceiling'
        assert snap.cost_toman == 900_000
        assert snap.usd_input_per_million == 9.0

    @pytest.mark.asyncio
    async def test_one_listed_side_and_one_ceiling_side_reports_the_worse(self, fx):
        fx(100_000.0)
        session = _CeilingSession([_ceiling_row('openrouter', 9.0, 30.0)])
        snap = await cc.capture_upstream_cost(
            session, upstream='openrouter',
            input_tokens=0, output_tokens=0,
            usd_input_per_million=2.0, usd_output_per_million=None,
        )
        # An event that guessed one of its two sides IS a guessed event.
        # Calling it 'listed' would overstate how much of the history is
        # really measured.
        assert snap.basis == 'category_ceiling'
        assert snap.usd_input_per_million == 2.0
        assert snap.usd_output_per_million == 30.0

    @pytest.mark.asyncio
    async def test_no_price_and_no_ceiling_is_unknown_not_zero(self, fx):
        fx(100_000.0)
        session = _CeilingSession()  # no ceilings for anyone
        snap = await cc.capture_upstream_cost(
            session, upstream='openrouter',
            input_tokens=1_000_000, output_tokens=1_000_000,
            usd_input_per_million=None, usd_output_per_million=None,
        )
        # The whole point of the change. A cost we cannot know must not be
        # recorded as a cost of zero, because zero is indistinguishable from
        # "genuinely free" in every downstream sum.
        assert snap.basis == 'unknown'
        assert snap.cost_toman is None

    @pytest.mark.asyncio
    async def test_free_upstream_never_reads_the_exchange_rate(self, monkeypatch):
        # Not a style point. A free upstream consulted no rate, so recording
        # one would be a fabricated audit trail -- and a rate-source outage
        # must never be able to break a path that does not need a rate.
        # Mocking the rate to RAISE is what proves the short-circuit is
        # really before the lookup: move it one line later and this goes red.
        import content
        monkeypatch.setattr(
            content, '_get_exchange_rate',
            AsyncMock(side_effect=AssertionError('free path must not read FX')),
        )
        snap = await cc.capture_upstream_cost(
            _CeilingSession(), upstream='litellm',
            input_tokens=5_000_000, output_tokens=5_000_000,
            usd_input_per_million=None, usd_output_per_million=None,
        )
        assert (snap.cost_toman, snap.basis) == (0, 'free_upstream')
        assert snap.fx_rate_irt is None

    @pytest.mark.asyncio
    async def test_a_stray_upstream_alias_still_counts_as_free(self, monkeypatch):
        # model_catalog.upstream has historically held non-canonical values
        # from hand-run DB fixes ('9router' for the registered 'ninerouter').
        # margin.FREE_UPSTREAMS matches canonical names only, so without
        # normalization a stray alias is classified PAID and gets costed at
        # a ceiling it never paid -- phantom cost on free traffic.
        import content
        monkeypatch.setattr(
            content, '_get_exchange_rate',
            AsyncMock(side_effect=AssertionError('alias should resolve to a free upstream')),
        )
        snap = await cc.capture_upstream_cost(
            _CeilingSession(), upstream='9router',
            input_tokens=1_000, output_tokens=1_000,
            usd_input_per_million=None, usd_output_per_million=None,
        )
        assert (snap.cost_toman, snap.basis) == (0, 'free_upstream')

    @pytest.mark.asyncio
    async def test_an_unclassified_upstream_is_assumed_paid(self, fx):
        # margin.py's deliberate fail-safe, inherited here: an upstream
        # nobody has classified must NOT be assumed free. Assuming free is
        # precisely the mistake that sells at a loss.
        fx(100_000.0)
        snap = await cc.capture_upstream_cost(
            _CeilingSession(), upstream='some-new-reseller',
            input_tokens=1_000, output_tokens=0,
            usd_input_per_million=None, usd_output_per_million=None,
        )
        assert snap.basis == 'unknown'
        assert snap.cost_toman is None

    def test_upstream_normalization_does_not_reach_out_of_services(self):
        """The alias map must not come from an app module.

        Found by live verification, not by any test that existed at the
        time: `_normalize_upstream` used to do a deferred
        `from chat_models import _UPSTREAM_ALIASES`, and under one import
        order that raised. Because the lookup sits inside the never-raises
        guard, the result was not a crash -- it was EVERY event coming back
        basis='error' with a NULL cost, and a log line. Total, silent loss of
        the profit number, which is the precise failure this whole feature
        exists to prevent.

        services/ is framework-agnostic domain logic; the dependency must
        point from app modules into it, never back out.
        """
        import inspect
        src = inspect.getsource(cc)
        assert 'from chat_models import' not in src, (
            'services/cost_capture.py must not import an app module -- an '
            'import failure here silently blanks every cost'
        )
        # And the map really is single-sourced, not copied.
        from services.margin import UPSTREAM_ALIASES
        import chat_models
        assert chat_models._UPSTREAM_ALIASES is UPSTREAM_ALIASES

    @pytest.mark.asyncio
    async def test_capture_never_raises_and_reports_error(self, monkeypatch):
        import content
        monkeypatch.setattr(
            content, '_get_exchange_rate', AsyncMock(side_effect=RuntimeError('rate source down')),
        )
        snap = await cc.capture_upstream_cost(
            _CeilingSession(), upstream='openrouter',
            input_tokens=1_000, output_tokens=1_000,
            usd_input_per_million=1.0, usd_output_per_million=1.0,
        )
        # 'error' is deliberately distinct from 'unknown': unknown is a DATA
        # gap fixed by syncing prices, error is a CODE/infra gap that will
        # cluster after a bad deploy and is meant to be loud.
        assert (snap.cost_toman, snap.basis) == (None, 'error')


class TestBasisCoercion:

    @pytest.mark.parametrize('value', list(cc.BASES))
    def test_every_legal_basis_survives(self, value):
        assert cc.normalize_basis(value) == value

    @pytest.mark.parametrize('value', ['', None, 'free', 'LISTED ', 'made-up'])
    def test_anything_else_becomes_error_rather_than_leaking(self, value):
        # An invented basis reaching the database would show up in the report
        # as if it were a real category. It is a code defect, and 'error' is
        # exactly what a code defect means here.
        got = cc.normalize_basis(value)
        assert got in cc.BASES
        if str(value or '').strip().lower() not in cc.BASES:
            assert got == 'error'

    @pytest.mark.asyncio
    async def test_record_usage_coerces_instead_of_raising(self):
        # record_usage runs inside the billing transaction, next to the
        # wallet charge and the ledger row. Raising on a bad bookkeeping
        # string would roll those back and serve the request free.
        from services.metering import record_usage
        from services.money import Money
        repo = types.SimpleNamespace(append_usage_event=AsyncMock())
        data = await record_usage(
            repo, request_id='r', user_id=1, model='m',
            charge=Money(5), upstream_status='success',
            upstream_cost_toman=3, upstream_cost_basis='not-a-real-basis',
        )
        assert data['upstream_cost_basis'] == 'error'
        assert data['upstream_cost_toman'] == 3

    @pytest.mark.asyncio
    async def test_a_caller_that_knows_nothing_records_null_not_zero(self):
        from services.metering import record_usage
        from services.money import Money
        repo = types.SimpleNamespace(append_usage_event=AsyncMock())
        data = await record_usage(
            repo, request_id='r', user_id=1, model='m',
            charge=Money(5), upstream_status='success',
        )
        # Indistinguishable from the pre-0048 history, which is right: it
        # measured nothing. A default of 0 would silently claim it was free.
        assert data['upstream_cost_toman'] is None
        assert data['upstream_cost_basis'] is None


# ═══════════════════════════════════════════════════════════════════════
# Section 3: wiring into the real billing path
# ═══════════════════════════════════════════════════════════════════════

def _payload(model='gpt-x'):
    return {'model': model, 'messages': [{'role': 'user', 'content': 'سلام'}]}


def _usage(prompt=800, completion=200):
    return {'total_tokens': prompt + completion,
            'prompt_tokens': prompt, 'completion_tokens': completion}


class _RecordingSession:
    """The subset of session behaviour chat_billing._record_usage exercises."""

    def __init__(self, wallet_balance, price):
        self.wallet = types.SimpleNamespace(user_id=1, balance=wallet_balance, reserved=0)
        self.price = price
        self.added = []

    async def execute(self, stmt, params=None, *a, **k):
        result = MagicMock()
        result.fetchone.return_value = None
        text_sql = str(stmt)
        if 'GROUP BY upstream' in text_sql:
            result.fetchall.return_value = []
            return result
        if 'model_catalog' in text_sql:
            result.fetchone.return_value = self.price
            return result
        name = getattr(getattr(stmt, 'table', None), 'name', None)
        if name == 'wallet':
            if type(stmt).__name__ == 'Update':
                compiled = stmt.compile().params
                if 'balance' in compiled:
                    self.wallet.balance = compiled['balance']
            else:
                result.fetchone.return_value = (self.wallet,)
        return result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


def _catalog_row(upstream='litellm', usd_in=None, usd_out=None):
    return types.SimpleNamespace(
        input_per_million=1_000_000, output_per_million=1_000_000, markup_pct=0,
        upstream=upstream, usd_input_per_million=usd_in, usd_output_per_million=usd_out,
    )


@pytest.fixture
def captured(monkeypatch):
    """Record every record_usage call the billing path makes."""
    calls: list[dict] = []

    async def _spy(repo, **kwargs):
        calls.append(kwargs)
        return kwargs

    import services.metering as metering_mod
    monkeypatch.setattr(metering_mod, 'record_usage', _spy)
    return calls


class TestPackageCoveredRequests:
    """The trap: a package-covered request costs us money and earns none."""

    @pytest.mark.asyncio
    async def test_an_entitlement_request_records_zero_charge_and_a_real_cost(
        self, monkeypatch, captured, fx,
    ):
        fx(100_000.0)
        import services.entitlement_gate as gate_mod
        monkeypatch.setattr(
            gate_mod, 'consume_for_usage', AsyncMock(return_value={'id': 77}),
        )
        monkeypatch.setattr(
            gate_mod, 'covering_entitlement', AsyncMock(return_value=None), raising=False,
        )
        session = _RecordingSession(
            wallet_balance=1_000_000,
            price=_catalog_row(upstream='openrouter', usd_in=2.0, usd_out=6.0),
        )
        await chat_billing._record_usage(session, 1, _payload(), _usage())

        assert len(captured) == 1, 'the entitlement path must still meter the event'
        row = captured[0]
        # Charged nothing -- the package covered it.
        assert row['charge'].amount == 0
        # But it was NOT free to us. Without this, every package looks
        # infinitely profitable and the more we sell the better the
        # dashboard looks while the bill grows.
        assert row['upstream_cost_toman'] > 0
        assert row['upstream_cost_basis'] == 'listed'


class TestWalletPath:

    @pytest.mark.asyncio
    async def test_a_free_upstream_request_records_a_measured_zero(
        self, monkeypatch, captured,
    ):
        import services.entitlement_gate as gate_mod
        monkeypatch.setattr(gate_mod, 'consume_for_usage', AsyncMock(return_value=None))
        session = _RecordingSession(wallet_balance=1_000_000, price=_catalog_row('litellm'))
        await chat_billing._record_usage(session, 1, _payload(), _usage())

        row = captured[0]
        # 0 with basis 'free_upstream' is a MEASURED zero; NULL would mean
        # unmeasured. The report's coverage figure depends on the difference.
        assert row['upstream_cost_toman'] == 0
        assert row['upstream_cost_basis'] == 'free_upstream'

    @pytest.mark.asyncio
    async def test_cost_uses_raw_prompt_tokens_while_charge_uses_discounted(
        self, monkeypatch, captured, fx,
    ):
        """Revenue on discounted tokens, cost on raw tokens.

        When a provider pads the prompt with its own preamble we refuse to
        bill the user for the padding -- but the upstream still charges US
        for every token it processed. Swapping these two shrinks recorded
        cost on exactly the providers that pad hardest, which is the worst
        possible place to lose visibility.
        """
        fx(100_000.0)
        import services.entitlement_gate as gate_mod
        import services.upstream_overhead as overhead_mod
        import chat as chat_mod
        monkeypatch.setattr(gate_mod, 'consume_for_usage', AsyncMock(return_value=None))
        monkeypatch.setattr(
            chat_mod, '_resolve_provider',
            AsyncMock(return_value=types.SimpleNamespace(name='openrouter')),
        )
        monkeypatch.setattr(overhead_mod, 'get_prompt_overhead', AsyncMock(return_value=600))
        monkeypatch.setattr(
            overhead_mod, 'discounted_input_tokens', lambda raw, overhead, floor: 200,
        )
        seen: dict = {}

        async def _spy_capture(session, **kwargs):
            seen.update(kwargs)
            return cc.CostSnapshot(1, 'listed', 100_000.0, 2.0, 6.0)

        monkeypatch.setattr(cc, 'capture_upstream_cost', _spy_capture)

        session = _RecordingSession(
            wallet_balance=10_000_000,
            price=_catalog_row(upstream='openrouter', usd_in=2.0, usd_out=6.0),
        )
        await chat_billing._record_usage(session, 1, _payload(), _usage(prompt=800, completion=200))

        assert seen['input_tokens'] == 800, 'cost must be computed on RAW prompt tokens'
        assert captured[0]['input_tokens'] == 200, 'the user is billed the DISCOUNTED tokens'

    @pytest.mark.asyncio
    async def test_a_capture_failure_does_not_disturb_the_charge(
        self, monkeypatch, captured,
    ):
        """Cost accounting is worth exactly zero requests.

        capture_upstream_cost sits inside the billing transaction, beside the
        wallet charge and the ledger row. If it could raise, a bookkeeping
        bug would roll those back and serve the request free.
        """
        import services.entitlement_gate as gate_mod
        monkeypatch.setattr(gate_mod, 'consume_for_usage', AsyncMock(return_value=None))

        session = _RecordingSession(wallet_balance=1_000_000, price=_catalog_row('litellm'))
        clean = await chat_billing._record_usage(session, 1, _payload(), _usage())

        async def _boom(*a, **k):
            raise RuntimeError('cost capture exploded')

        # Patched on the inner function, NOT on snapshot_for_price_row: that
        # is what proves the wrapper's own try/except is doing the work. Patch
        # the wrapper instead and this test would only be checking that a
        # function which does not raise does not raise.
        monkeypatch.setattr(cc, 'capture_upstream_cost', _boom)
        broken_session = _RecordingSession(wallet_balance=1_000_000, price=_catalog_row('litellm'))
        broken = await chat_billing._record_usage(broken_session, 1, _payload(), _usage())

        assert broken['cost'] == clean['cost']
        assert broken['balance_after'] == clean['balance_after']
        assert len(broken_session.added) == len(session.added)
