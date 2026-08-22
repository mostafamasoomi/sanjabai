"""The markup percentage must reach the BILLED price, not just the shown one.

`markup_pct` was threaded through the pricing path long before it had a
value: `_catalog_row_to_item` accepted it, `_get_exchange_rate` returned it,
and all three sites that produced it were hardcoded to `0`. Migration 0030
gave it a real value (a global setting plus a per-model override), which
opened a specific way to lose money in the user's favour and trust in ours:
apply the percentage when rendering the catalog and forget it when charging
the wallet. The user would then be quoted one number and billed another.

These tests pin the two ends together. They drive the real
`chat._record_usage` -- the actual billing path, not a reimplementation of
it -- and compare what it charges against what `content._catalog_row_to_item`
puts on the price page for the same model at the same percentage.

The session double is deliberately the same shape as the one in
test_billing_loss_paths.py (quota select/update, a raw text() pricing
lookup, wallet select+update); see that file for why each branch exists.
"""
import types
from unittest.mock import MagicMock, patch

import pytest

import chat as chat_mod
import content as content_mod


def _table_name(stmt):
    """Same resolution order as test_billing_loss_paths.py's double."""
    try:
        return stmt.table.name
    except AttributeError:
        pass
    try:
        for f in stmt.get_final_froms():
            name = getattr(f, 'name', None)
            if name:
                return name
    except Exception:
        pass
    return None


class _PricingSession:
    """Covers exactly the statements `_record_usage` issues."""

    def __init__(self, price_row, wallet_balance=10_000_000_000):
        self.price_row = price_row
        self.wallet = types.SimpleNamespace(user_id=1, balance=wallet_balance, reserved=0)
        self.added = []

    async def execute(self, stmt, params=None, *a, **k):
        result = MagicMock()
        result.fetchone.return_value = None
        if 'model_catalog' in str(stmt):
            result.fetchone.return_value = self.price_row
            return result
        if _table_name(stmt) == 'wallet':
            if type(stmt).__name__ == 'Update':
                p = stmt.compile().params
                if 'balance' in p:
                    self.wallet.balance = p['balance']
            else:
                result.fetchone.return_value = (self.wallet,)
        return result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


def _price_row(inp, out, markup_pct=None):
    return types.SimpleNamespace(
        input_per_million=inp, output_per_million=out, markup_pct=markup_pct
    )


def _catalog_row(inp, out, markup_pct=None):
    """A model_catalog row shaped the way `_catalog_row_to_item` expects."""
    return {
        'id': 'prov/some-model',
        'public_id': 'sanjab/some-model',
        'provider_model_id': 'prov/some-model',
        'display_name': 'Some Model',
        'description': None,
        'provider': 'prov',
        'modalities': {'input': ['text'], 'output': ['text']},
        'capabilities': [],
        'recommended_for': [],
        'context_window': 100_000,
        'max_output_tokens': 4096,
        'currency': 'IRT',
        'input_per_million': inp,
        'output_per_million': out,
        'cached_input_per_million': None,
        'reasoning_per_million': None,
        'markup_pct': markup_pct,
        'price_version': 'v1',
        'effective_from': None,
        'availability': 'available',
        'audience': ['consumer'],
        'rate_limit': None,
        'deprecated_at': None,
        'last_verified_at': None,
        'provenance': 'provider',
    }


#: Exactly one million tokens on each side. `_record_usage` computes
#: `(in*inp_rate + out*out_rate + 500_000) // 1_000_000`, so at this token
#: count the cost collapses to `inp_rate + out_rate` with nothing lost to
#: rounding -- the two per-million rates are read back directly. Both sides
#: are non-zero on purpose: a zero side sends `_record_usage` down its
#: local-estimate branch, which measures the prompt text instead of using
#: the numbers handed to it.
_ONE_MILLION = 1_000_000


async def _billed_rate_sum(inp, out, markup_pct, global_pct):
    """Run the real billing path; returns inp_rate + out_rate as billed."""
    session = _PricingSession(_price_row(inp, out, markup_pct))
    with patch.object(content_mod, 'get_global_markup_pct', return_value=global_pct):
        result = await chat_mod._record_usage(
            session, uid=1,
            payload={'model': 'prov/some-model', 'messages': [{'role': 'user', 'content': 'x'}]},
            usage={
                'prompt_tokens': _ONE_MILLION,
                'completion_tokens': _ONE_MILLION,
                'total_tokens': 2 * _ONE_MILLION,
            },
            response_text='y',
        )
    return result['cost']


def _shown_rates(inp, out, markup_pct, global_pct):
    """What the catalog/price page puts in front of the user."""
    item = content_mod._catalog_row_to_item(
        _catalog_row(inp, out, markup_pct), rate_irt=100_000, global_markup_pct=global_pct
    )
    pricing = item['pricing']
    return {
        'input': pricing['inputPerMillion'],
        'output': pricing['outputPerMillion'],
    }


class TestShownPriceEqualsBilledPrice:
    """The number on the price page and the number taken from the wallet."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize('global_pct,override', [
        (0, None),        # nothing set anywhere -- the pre-0030 behaviour
        (25, None),       # global only; the model inherits it
        (25, 0),          # an explicit 0% override beats a 25% global
        (10, 60),         # per-model override wins over the global
        (0, 15),          # override with no global
        (7.5, None),      # fractional global -- rounding must agree too
    ])
    async def test_rates_agree(self, global_pct, override):
        inp, out = 71_475, 357_375  # real production rates (gemini-3.7-flash)
        billed = await _billed_rate_sum(inp, out, override, global_pct)
        shown = _shown_rates(inp, out, override, global_pct)
        assert billed == shown['input'] + shown['output'], (
            f"billed {billed} but the price page shows "
            f"{shown['input']} + {shown['output']} = {shown['input'] + shown['output']}"
        )

    @pytest.mark.asyncio
    async def test_markup_actually_raises_the_billed_amount(self):
        """Guard against both ends agreeing on the unmarked-up number --
        which would make the test above pass while the feature does nothing."""
        plain = await _billed_rate_sum(1_000_000, 1_000_000, None, 0)
        marked = await _billed_rate_sum(1_000_000, 1_000_000, None, 50)
        assert plain == 2_000_000
        assert marked == 3_000_000

    @pytest.mark.asyncio
    async def test_price_row_without_markup_column_still_bills(self):
        """A price row from before migration 0030 (or an older test double)
        has no `markup_pct` attribute at all. Billing must inherit the
        global rather than raising -- an AttributeError here would drop the
        request into the fallback-ceiling branch and overcharge the user."""
        session = _PricingSession(
            types.SimpleNamespace(input_per_million=1_000_000, output_per_million=1_000_000)
        )
        with patch.object(content_mod, 'get_global_markup_pct', return_value=20):
            result = await chat_mod._record_usage(
                session, uid=1,
                payload={'model': 'prov/some-model', 'messages': [{'role': 'user', 'content': 'x'}]},
                usage={
                    'prompt_tokens': _ONE_MILLION,
                    'completion_tokens': _ONE_MILLION,
                    'total_tokens': 2 * _ONE_MILLION,
                },
                response_text='y',
            )
        assert result['cost'] == 2_400_000

    @pytest.mark.asyncio
    async def test_billed_amount_is_integer_toman(self):
        """Money is integer Toman everywhere; a percentage must not leak a
        float into the ledger."""
        session = _PricingSession(_price_row(71_475, 357_375, 7.5))
        with patch.object(content_mod, 'get_global_markup_pct', return_value=0):
            result = await chat_mod._record_usage(
                session, uid=1,
                payload={'model': 'prov/some-model', 'messages': [{'role': 'user', 'content': 'x'}]},
                usage={'prompt_tokens': 3_333, 'completion_tokens': 777, 'total_tokens': 4_110},
                response_text='y',
            )
        assert isinstance(result['cost'], int)
        ledger = [o for o in session.added if type(o).__name__ == 'Ledger']
        assert ledger and isinstance(ledger[0].amount, int)
