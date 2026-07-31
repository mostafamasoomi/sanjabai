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


class TestProviderConfiguration:
    """9Router is opt-in; LiteLLM is always present."""

    def _reload(self):
        import providers

        return importlib.reload(providers)

    def test_ninerouter_absent_by_default(self, monkeypatch):
        monkeypatch.delenv('NINEROUTER_URL', raising=False)
        monkeypatch.delenv('NINEROUTER_ENABLED', raising=False)
        providers = self._reload()
        names = [p.name for p in providers.configured_providers()]
        assert names == ['litellm']

    def test_ninerouter_enabled_by_url(self, monkeypatch):
        monkeypatch.setenv('NINEROUTER_URL', 'http://9router.test:20128')
        providers = self._reload()
        by_name = {p.name: p for p in providers.configured_providers()}
        assert 'ninerouter' in by_name
        nine = by_name['ninerouter']
        # base_url is an origin; /v1 is appended by the adapter, and /health
        # deliberately sits outside it.
        assert nine.v1 == 'http://9router.test:20128/v1'
        assert nine.health_path == '/health'

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
