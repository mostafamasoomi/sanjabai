"""A probe may not put a paid-upstream model on sale.

services/margin.py's guard covers the admin routes (set price, toggle,
bulk-enable, markup). It does NOT cover the health sweep, which mirrors probe
results onto `model_catalog.availability` — and that mirror promoted a row on
nothing more than "healthy probe AND input_per_million > 0". `priced` answers
"would this bill the user", not "do we make a margin on it", so a healthy
probe was enough to sell a model at a loss with no margin check anywhere on
the path. Found while verifying Phase F's OpenRouter groundwork.

Dormant when written: every catalog row sits on a free upstream
(litellm/ninerouter/omniroute), so there is no live loss today. It is the
gate on enabling a paid upstream like OpenRouter, which is exactly when it
stops being dormant.
"""
from __future__ import annotations

import pytest

from model_health_policy import _target_catalog_state


def _state(**kw):
    base = dict(
        status='healthy',
        current_availability='maintenance',
        input_per_million=100000.0,   # priced — the old promotion trigger
        health_quarantine_reason='http_429',
        provider_fault_only=False,
        fault_reason=None,
        upstream='litellm',
    )
    base.update(kw)
    return _target_catalog_state(**base)


class TestPaidUpstreamIsNeverPromoted:
    @pytest.mark.parametrize('upstream', ['openrouter', 'bynara', 'gemini-api', 'anything-else'])
    def test_a_healthy_priced_paid_row_is_not_put_on_sale(self, upstream):
        availability, _ = _state(upstream=upstream)
        assert availability != 'available', (
            f'{upstream} row auto-promoted by a probe, bypassing the margin guard'
        )

    def test_a_disabled_paid_row_stays_disabled(self):
        # `_probe_targets` excludes only 'maintenance', so 'disabled' rows are
        # probed too — that was the reachable half of the bypass.
        availability, _ = _state(current_availability='disabled', upstream='openrouter')
        assert availability == 'disabled'

    def test_promotion_of_a_free_upstream_row_still_works(self):
        # The guard must not freeze the catalog we actually sell today.
        availability, reason = _state(upstream='litellm')
        assert availability == 'available'
        assert reason is None

    @pytest.mark.parametrize('upstream', ['litellm', 'ninerouter', 'omniroute'])
    def test_every_free_upstream_still_promotes(self, upstream):
        availability, _ = _state(upstream=upstream)
        assert availability == 'available'

    def test_a_missing_upstream_is_treated_as_paid_and_not_promoted(self):
        # Unknown provenance must fail closed: "we don't know what this costs"
        # is not a reason to start selling it.
        availability, _ = _state(upstream=None)
        assert availability != 'available'


class TestSickPaidRowsAreStillParked:
    """Refusing to *promote* must not become refusing to *protect*."""

    def test_a_down_paid_row_is_still_taken_out_of_availability(self):
        availability, _ = _state(
            status='down', current_availability='available', upstream='openrouter',
        )
        assert availability != 'available'
