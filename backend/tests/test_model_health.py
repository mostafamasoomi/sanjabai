"""
Unit tests for model health derivation and provider configuration.

These cover the pure logic — turning a window of samples into a status, and
deciding which upstreams are configured. The database-backed parts
(recompute_states, probe_sweep) need a live Postgres and are exercised in
integration, not here.
"""
import importlib
import os

import pytest

from model_health import _derive_status


class TestDeriveStatus:
    """Status is a function of the rolling window, not of the last sample."""

    def test_no_samples_is_unknown(self):
        # Distinct from 'down': nobody has exercised the model, which is the
        # normal state of a freshly deployed catalog entry.
        assert _derive_status(0, None, 0, None) == 'unknown'
        assert _derive_status(0, None, 5, None) == 'unknown'

    def test_all_successful_is_healthy(self):
        assert _derive_status(10, 1.0, 0, 800) == 'healthy'

    def test_single_good_sample_is_healthy(self):
        assert _derive_status(1, 1.0, 0, 120) == 'healthy'

    @pytest.mark.parametrize('rate', [0.86, 0.9, 0.99])
    def test_just_above_threshold_stays_healthy(self, rate):
        assert _derive_status(20, rate, 0, 500) == 'healthy'

    @pytest.mark.parametrize('rate', [0.84, 0.7, 0.5])
    def test_flaky_is_degraded(self, rate):
        assert _derive_status(20, rate, 0, 500) == 'degraded'

    @pytest.mark.parametrize('rate', [0.39, 0.2, 0.0])
    def test_mostly_failing_is_down(self, rate):
        assert _derive_status(20, rate, 0, 500) == 'down'

    def test_consecutive_failures_beat_a_good_average(self):
        # A model that worked all hour and has now failed three times running
        # is down. The window average still describes a past that no longer
        # applies, so the streak has to win or a freshly broken model stays in
        # the picker until the average sags.
        assert _derive_status(100, 0.97, 3, 500) == 'down'

    def test_streak_below_threshold_does_not_trip(self):
        assert _derive_status(100, 1.0, 2, 500) == 'healthy'

    def test_slow_but_answering_is_degraded(self):
        # Succeeding is not the same as being usable.
        assert _derive_status(10, 1.0, 0, 20_000) == 'degraded'

    def test_latency_is_ignored_when_unmeasured(self):
        assert _derive_status(10, 1.0, 0, None) == 'healthy'

    def test_down_takes_precedence_over_slow(self):
        assert _derive_status(10, 0.1, 0, 20_000) == 'down'


class TestNeverSucceededIsNotHealthy:
    """A window with zero successes must never read 'healthy' -- that is the
    exact input an admin or an automated promotion path would trust that a
    model has been live-probed and answered (see services/probe_gate.py's
    "«مدل فقط بعد از پروب زنده موفق ارائه می‌شود»" rule). Below
    MIN_SAMPLES_FOR_RATE and short of DOWN_AFTER_CONSECUTIVE, the rate rules
    and the consecutive-failure rule both stay silent, so the function used
    to fall through to 'healthy'. Reproduces the production symptom:
    model_health_state rows with status='healthy' AND last_ok_at IS NULL.
    """

    def test_one_failure_is_not_healthy(self):
        assert _derive_status(1, 0.0, 1, None) != 'healthy'
        assert _derive_status(1, 0.0, 1, None) == 'unknown'

    def test_two_failures_is_not_healthy(self):
        assert _derive_status(2, 0.0, 2, None) != 'healthy'
        assert _derive_status(2, 0.0, 2, None) == 'unknown'

    def test_third_consecutive_failure_is_still_down(self):
        # DOWN_AFTER_CONSECUTIVE must still win once the streak reaches it --
        # the new 'unknown' branch must not outrank the existing down rule.
        assert _derive_status(3, 0.0, 3, None) == 'down'

    def test_zero_consecutive_but_zero_rate_is_still_not_healthy(self):
        # The function doesn't require consecutive_failures to agree with
        # success_rate -- any zero-success window below both thresholds must
        # resolve to 'unknown', not 'healthy'.
        assert _derive_status(2, 0.0, 0, None) == 'unknown'

    def test_slow_zero_rate_sample_stays_degraded(self):
        # Latency still outranks the new branch -- order is unchanged.
        assert _derive_status(1, 0.0, 1, 20_000) == 'degraded'

    def test_a_real_success_keeps_healthy_even_with_failures_mixed_in(self):
        # No regression: a model that HAS answered at least once, with an
        # acceptable rate, must not be pulled into the new branch.
        assert _derive_status(4, 0.75, 0, None) == 'healthy'
        assert _derive_status(1, 1.0, 0, None) == 'healthy'


class TestDeriveStatusRegressionTable:
    """Table-drive the pre-fix behaviour of every branch this function has,
    and assert the post-fix function is byte-identical everywhere except the
    zero-success/low-sample/low-streak cases the fix targets. Each row's
    `before` value was the function's actual output prior to this change
    (verified against the previous source, reproduced in the handoff packet
    for the first two rows) -- this proves the fix moved exactly one thing.
    """

    # (sample_count, success_rate, consecutive_failures, latency_p50, before)
    TABLE = [
        (0, None, 0, None, 'unknown'),
        (0, None, 5, None, 'unknown'),
        (10, 1.0, 0, 800, 'healthy'),
        (1, 1.0, 0, 120, 'healthy'),
        (20, 0.86, 0, 500, 'healthy'),
        (20, 0.9, 0, 500, 'healthy'),
        (20, 0.99, 0, 500, 'healthy'),
        (20, 0.84, 0, 500, 'degraded'),
        (20, 0.7, 0, 500, 'degraded'),
        (20, 0.5, 0, 500, 'degraded'),
        (20, 0.39, 0, 500, 'down'),
        (20, 0.2, 0, 500, 'down'),
        (20, 0.0, 0, 500, 'down'),
        (100, 0.97, 3, 500, 'down'),
        (100, 1.0, 2, 500, 'healthy'),
        (10, 1.0, 0, 20_000, 'degraded'),
        (10, 1.0, 0, None, 'healthy'),
        (10, 0.1, 0, 20_000, 'down'),
        # zero-success cases: 'before' is what the buggy function returned;
        # these are the ones the fix is allowed to change.
        (1, 0.0, 1, None, 'healthy'),
        (2, 0.0, 2, None, 'healthy'),
        (3, 0.0, 3, None, 'down'),
        (4, 0.0, 2, None, 'healthy'),
        (2, 0.0, 0, None, 'healthy'),
        (1, 0.0, 1, 20_000, 'degraded'),
    ]

    # Exactly the rows above where the fix is expected to change the result.
    CHANGED_INPUTS = {
        (1, 0.0, 1, None),
        (2, 0.0, 2, None),
        (4, 0.0, 2, None),
        (2, 0.0, 0, None),
    }

    def test_unchanged_everywhere_except_the_targeted_cases(self):
        for sample_count, success_rate, consecutive, p50, before in self.TABLE:
            after = _derive_status(sample_count, success_rate, consecutive, p50)
            key = (sample_count, success_rate, consecutive, p50)
            if key in self.CHANGED_INPUTS:
                assert after == 'unknown', key
                assert after != before, key
            else:
                assert after == before, key


class TestProviderConfiguration:
    """9Router is opt-in; LiteLLM is always present."""

    def _reload(self):
        import providers

        return importlib.reload(providers)

    def test_ninerouter_absent_by_default(self, monkeypatch):
        # Hermetic: clear every env var that can add a non-litellm provider,
        # not just the NINEROUTER_* ones -- a real .env (e.g. this
        # deployment's, which also sets OMNIROUTER_URL/OMNIROUTER_ENABLED)
        # must not leak an extra provider into this "absent by default"
        # assertion. See providers.configured_providers() for the full set.
        for var in (
            'NINEROUTER_URL', 'NINEROUTER_ENABLED', 'NINEROUTER_API_KEY',
            'OMNIROUTER_URL', 'OMNIROUTER_ENABLED', 'OMNIROUTER_API_KEY',
            'OPENROUTER_ENABLED', 'OPENROUTER_API_KEY', 'OPENROUTER_BASE_URL',
        ):
            monkeypatch.delenv(var, raising=False)
        providers = self._reload()
        names = [p.name for p in providers.configured_providers()]
        assert names == ['litellm']

    def test_ninerouter_enabled_by_url(self, monkeypatch):
        monkeypatch.setenv('NINEROUTER_URL', 'http://9router.test:20128')
        providers = self._reload()
        by_name = {p.name: p for p in providers.configured_providers()}
        assert 'ninerouter' in by_name
        nine = by_name['ninerouter']
        # base_url is an origin; /v1 is appended by the adapter, and
        # /api/health deliberately sits outside it. (/health, /healthz,
        # /v1/health and /status all 404 against the real upstream; only
        # /api/health answers 200.)
        assert nine.v1 == 'http://9router.test:20128/v1'
        assert nine.health_path == '/api/health'

    def test_trailing_slash_is_not_doubled(self, monkeypatch):
        monkeypatch.setenv('NINEROUTER_URL', 'http://9router.test:20128/')
        providers = self._reload()
        nine = {p.name: p for p in providers.configured_providers()}['ninerouter']
        assert nine.v1 == 'http://9router.test:20128/v1'

    def test_chat_provider_defaults_to_litellm(self, monkeypatch):
        # Enabling 9Router for discovery and health must not silently move
        # billed user traffic onto it.
        monkeypatch.setenv('NINEROUTER_URL', 'http://9router.test:20128')
        monkeypatch.delenv('CHAT_PROVIDER', raising=False)
        providers = self._reload()
        assert providers.chat_provider().name == 'litellm'

    def test_chat_provider_switchable(self, monkeypatch):
        monkeypatch.setenv('NINEROUTER_URL', 'http://9router.test:20128')
        monkeypatch.setenv('CHAT_PROVIDER', 'ninerouter')
        providers = self._reload()
        assert providers.chat_provider().name == 'ninerouter'

    def test_unknown_chat_provider_falls_back(self, monkeypatch):
        monkeypatch.setenv('CHAT_PROVIDER', 'does-not-exist')
        providers = self._reload()
        assert providers.chat_provider().name == 'litellm'

    def test_auth_header_omitted_without_key(self, monkeypatch):
        monkeypatch.setenv('NINEROUTER_URL', 'http://9router.test:20128')
        monkeypatch.delenv('NINEROUTER_API_KEY', raising=False)
        providers = self._reload()
        nine = {p.name: p for p in providers.configured_providers()}['ninerouter']
        assert 'Authorization' not in nine.headers()

    def test_auth_header_present_with_key(self, monkeypatch):
        monkeypatch.setenv('NINEROUTER_URL', 'http://9router.test:20128')
        monkeypatch.setenv('NINEROUTER_API_KEY', 'sk-test')
        providers = self._reload()
        nine = {p.name: p for p in providers.configured_providers()}['ninerouter']
        assert nine.headers()['Authorization'] == 'Bearer sk-test'


class TestDiscoveryHelpers:
    def test_display_name_is_readable(self):
        from model_discovery import _display_name

        assert _display_name('deepseek-v4-pro') == 'Deepseek V4 Pro'
        assert _display_name('openai/gpt-oss-120b') == 'Gpt Oss 120b'

    def test_provider_guessed_from_id(self):
        from model_discovery import _guess_provider

        assert _guess_provider('gemini-3.5-flash') == 'google'
        assert _guess_provider('gemma-4-31b-it') == 'google'
        assert _guess_provider('llama-3.3-70b') == 'meta'
        assert _guess_provider('deepseek-v4-pro') == 'deepseek'
        assert _guess_provider('gpt-oss-120b') == 'openai'
        assert _guess_provider('something-unheard-of') == 'other'

    def test_explicit_prefix_wins(self):
        from model_discovery import _guess_provider

        assert _guess_provider('anthropic/claude-haiku') == 'anthropic'

    def test_context_window_prefers_reported_value(self):
        from model_discovery import _context_window

        assert _context_window({'context_length': 128000}) == 128000
        assert _context_window({'max_input_tokens': 32000}) == 32000
        # The column is NOT NULL with a positive check, so a default is needed.
        assert _context_window({}) == 8192
        assert _context_window({'context_length': 0}) == 8192
