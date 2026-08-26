"""Pure pricing-math unit tests for services/margin.py: paid-upstream
classification, USD-per-million -> Toman cost conversion, and the
per-model evaluate_price() verdict.

Split out of the original tests/test_margin_guard.py (which grew past the
500-line cap) -- the DB-facing refuse_if_loss_making() guard and the five
admin decision points that must consult it now live in
tests/test_margin_guard_wiring.py. See that module's docstring for the
project law both files together enforce:

  * «هیچ درخواستی نباید ضررده باشد» -- a listed price under MIN_MARGIN_PCT
    over upstream cost is REFUSED (HTTP 400, Persian detail naming the
    numbers), never silently accepted and never auto-corrected.
  * A model whose upstream cost is unknown is costed at the CEILING of its
    upstream's price band, never the average.
  * Integer Toman throughout. Nothing here multiplies or divides by 10.

None of the tests in this file touch the probe gate, the DB, or an admin
route -- they call margin_mod's pure functions directly, so (unlike
tests/test_margin_guard_wiring.py) no probe-gate isolation fixture is
needed here.
"""
from __future__ import annotations

import pytest

from services import margin as margin_mod


class TestPaidUpstreamClassification:
    """Which upstreams cost us money per token.

    Today every enabled upstream is the owner's own aggregating
    infrastructure (~zero marginal cost); OpenRouter is the first real
    paid one. An upstream nobody classified must be assumed PAID -- the
    fail-safe direction, because assuming "free" is what silently sells
    at a loss.
    """

    @pytest.mark.parametrize('name', ['litellm', 'ninerouter', 'omniroute'])
    def test_owner_infrastructure_is_free(self, name):
        assert margin_mod.is_paid_upstream(name) is False

    def test_openrouter_is_paid(self):
        assert margin_mod.is_paid_upstream('openrouter') is True

    def test_unknown_upstream_is_assumed_paid(self):
        assert margin_mod.is_paid_upstream('some-new-router') is True

    def test_missing_upstream_is_assumed_paid(self):
        assert margin_mod.is_paid_upstream(None) is True

    def test_classification_ignores_case_and_whitespace(self):
        assert margin_mod.is_paid_upstream('  NineRouter ') is False


class TestUpstreamCostToman:
    """USD-per-million from the catalog -> integer Toman-per-million cost.

    model_catalog.usd_input_per_million / usd_output_per_million hold the
    upstream's own list price in USD (content.py's price sync writes them
    straight from OpenRouter's public pricing). Multiplying by the live
    USD->IRT rate is the only conversion that happens here: Toman in,
    Toman out, no Rial anywhere.
    """

    def test_converts_usd_per_million_to_toman(self):
        # 3 USD/M at 191,400 Toman/USD == 574,200 Toman/M
        assert margin_mod.upstream_cost_toman(3.0, 191_400, ceiling_usd_per_million=99.0) == 574_200

    def test_rounds_cost_up_never_down(self):
        """Cost is rounded UP: an under-stated upstream cost is the one
        rounding direction that can let a loss-making price through."""
        assert margin_mod.upstream_cost_toman(0.0001, 191_400, ceiling_usd_per_million=99.0) == 20

    def test_result_is_a_plain_int(self):
        value = margin_mod.upstream_cost_toman(1.5, 191_400, ceiling_usd_per_million=99.0)
        assert isinstance(value, int) and not isinstance(value, bool)

    def test_unknown_usd_price_falls_back_to_the_category_ceiling(self):
        """Project law: a model with no known price is costed at the
        CEILING of its category, never the average."""
        assert margin_mod.upstream_cost_toman(None, 191_400, ceiling_usd_per_million=15.0) == 2_871_000

    def test_zero_usd_price_is_treated_as_unknown_not_as_free(self):
        """The catalog stores 0 for "never synced", not for "genuinely
        free" -- 0 must not be read as a free upstream."""
        assert margin_mod.upstream_cost_toman(0, 191_400, ceiling_usd_per_million=15.0) == 2_871_000

    def test_unknown_price_and_unknown_ceiling_is_not_costed_at_zero(self):
        """When even the category ceiling is unknown the answer must not
        be "free" -- the caller has to refuse, so this returns None."""
        assert margin_mod.upstream_cost_toman(None, 191_400, ceiling_usd_per_million=None) is None


def _priced(**overrides):
    """Kwargs for evaluate_price: a model on a PAID upstream, 3 USD/M in,
    15 USD/M out, at 191,400 Toman/USD -> upstream cost 574,200 in /
    2,871,000 out. Listed prices default to a comfortable 100% margin."""
    kwargs = dict(
        upstream='openrouter',
        listed_input_per_million=1_148_400,
        listed_output_per_million=5_742_000,
        usd_input_per_million=3.0,
        usd_output_per_million=15.0,
        rate_irt=191_400,
        ceiling_usd_input_per_million=15.0,
        ceiling_usd_output_per_million=75.0,
    )
    kwargs.update(overrides)
    return kwargs


class TestEvaluatePrice:
    """The whole-model verdict: None when safe to sell, a PriceRefusal
    carrying Persian text and the numbers otherwise."""

    def test_free_upstream_never_refuses_even_at_price_zero(self):
        """Today's production reality: every enabled upstream is the
        owner's own infrastructure, so the guard must stay a no-op there."""
        verdict = margin_mod.evaluate_price(
            'kr/claude-sonnet-4',
            **_priced(upstream='ninerouter', listed_input_per_million=0,
                      listed_output_per_million=0),
        )
        assert verdict is None

    def test_healthy_margin_on_a_paid_upstream_passes(self):
        assert margin_mod.evaluate_price('openrouter/gpt-5', **_priced()) is None

    def test_price_below_upstream_cost_is_refused(self):
        verdict = margin_mod.evaluate_price(
            'openrouter/gpt-5', **_priced(listed_input_per_million=100_000),
        )
        assert verdict is not None
        assert verdict.model_id == 'openrouter/gpt-5'

    def test_refusal_names_both_numbers_and_the_floor(self):
        verdict = margin_mod.evaluate_price(
            'openrouter/gpt-5', **_priced(listed_input_per_million=100_000),
        )
        assert '100,000' in verdict.detail, 'refusal must name the listed price'
        assert '574,200' in verdict.detail, 'refusal must name the upstream cost'
        assert '20' in verdict.detail, 'refusal must name the minimum margin'

    def test_refusal_text_is_persian(self):
        verdict = margin_mod.evaluate_price(
            'openrouter/gpt-5', **_priced(listed_input_per_million=100_000),
        )
        assert 'ضررده' in verdict.detail

    def test_margin_just_under_the_floor_is_refused(self):
        """574,200 * 1.19 = 683,298 -> 19% margin, under the 20% floor."""
        verdict = margin_mod.evaluate_price(
            'openrouter/gpt-5', **_priced(listed_input_per_million=683_298),
        )
        assert verdict is not None

    def test_margin_exactly_at_the_floor_is_accepted(self):
        """574,200 * 1.20 = 689,040 -> exactly 20%, the floor is inclusive."""
        assert margin_mod.evaluate_price(
            'openrouter/gpt-5', **_priced(listed_input_per_million=689_040),
        ) is None

    def test_output_side_is_checked_independently_of_input(self):
        """A fat input margin must not paper over a loss-making output
        rate -- output tokens are where the money actually is."""
        verdict = margin_mod.evaluate_price(
            'openrouter/gpt-5', **_priced(listed_output_per_million=1_000_000),
        )
        assert verdict is not None
        assert 'خروجی' in verdict.detail

    def test_unknown_upstream_cost_is_costed_at_the_category_ceiling(self):
        """No usd price for this row: cost falls back to the ceiling
        (15 USD/M in = 2,871,000 Toman), which the previously-fine
        1,148,400 listed price no longer clears."""
        verdict = margin_mod.evaluate_price(
            'openrouter/gpt-5', **_priced(usd_input_per_million=None),
        )
        assert verdict is not None
        assert '2,871,000' in verdict.detail

    def test_unknown_cost_with_no_ceiling_is_refused_not_assumed_free(self):
        verdict = margin_mod.evaluate_price(
            'openrouter/gpt-5',
            **_priced(usd_input_per_million=None, ceiling_usd_input_per_million=None),
        )
        assert verdict is not None
        assert 'نامعلوم' in verdict.detail

    def test_audit_payload_carries_the_raw_numbers(self):
        verdict = margin_mod.evaluate_price(
            'openrouter/gpt-5', **_priced(listed_input_per_million=100_000),
        )
        assert verdict.audit['model'] == 'openrouter/gpt-5'
        assert verdict.audit['upstream'] == 'openrouter'
        assert verdict.audit['token_kind'] == 'input'
        assert verdict.audit['listed_per_million'] == 100_000
        assert verdict.audit['upstream_cost_per_million'] == 574_200
        assert verdict.audit['min_margin_pct'] == 20
        assert verdict.audit['currency'] == 'IRT'
