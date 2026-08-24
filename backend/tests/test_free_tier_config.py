"""Tests for services/free_tier_config.py -- the coercion and fail-safe
logic that turns app_setting JSONB rows into the three free-tier numbers.

The DB read path (_load/get_config) is exercised against the live DB
elsewhere; here we pin down _coerce_int, which is the part that must never
let a malformed row poison the gate with a bad number.
"""
from __future__ import annotations

from services import free_tier_config as cfg


class TestCoerceInt:
    def test_plain_int(self):
        assert cfg._coerce_int(30, 99) == 30

    def test_json_number_as_float(self):
        assert cfg._coerce_int(30.0, 99) == 30

    def test_json_string_number(self):
        # app_setting rows sometimes store a JSON string like '"30"'.
        assert cfg._coerce_int('30', 99) == 30

    def test_negative_falls_back(self):
        assert cfg._coerce_int(-5, 99) == 99

    def test_garbage_string_falls_back(self):
        assert cfg._coerce_int('not-a-number', 99) == 99

    def test_none_falls_back(self):
        assert cfg._coerce_int(None, 99) == 99

    def test_zero_is_kept(self):
        # 0 is a legal limit ("free tier closed"), not a fallback trigger.
        assert cfg._coerce_int(0, 99) == 0


def test_defaults_match_the_documented_values():
    assert cfg.DEFAULT_HOURLY_LIMIT == 3
    assert cfg.DEFAULT_LIFETIME_LIMIT == 30
    assert cfg.DEFAULT_MAX_INPUT_PER_MILLION == 60000
    assert cfg._DEFAULTS == {
        'free_hourly_limit': 3,
        'free_lifetime_limit': 30,
        'free_tier_max_input_per_million': 60000,
    }


def test_invalidate_clears_the_cache():
    cfg._cache = {'free_hourly_limit': 1, 'free_lifetime_limit': 1,
                  'free_tier_max_input_per_million': 1}
    cfg._cache_at = 999999.0
    cfg.invalidate()
    assert cfg._cache is None
