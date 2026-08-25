"""Tests for services/exchange_sources.py -- Bonbast.com as a USD->IRT
source alongside tgju.org, admin-added custom_regex sources, the sanity
band every fetched candidate must pass, and the DB-backed flat Toman
markup (owner's ask, 2026-08-25 -- see NEXT-SESSION.md).

Style mirrors tests/test_exchange_rate_source.py and tests/test_markup.py:
exercises the module's functions directly (patching content._http /
content.async_session-backed session / content.rds) rather than only going
through HTTP, since the interesting logic lives entirely here.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import content as content_mod
import services.exchange_sources as es
from tests.conftest import make_result, make_row


# ── is_plausible_usd_irt_toman ────────────────────────────────────────────

class TestSanityBand:
    def test_typical_rate_is_plausible(self):
        assert es.is_plausible_usd_irt_toman(203_700) is True

    def test_way_too_low_is_implausible(self):
        # A Rial figure mistaken for Toman (10x too small) would land here.
        assert es.is_plausible_usd_irt_toman(1_000) is False

    def test_way_too_high_is_implausible(self):
        # A Toman figure mistaken for Rial (10x too large) would land here.
        assert es.is_plausible_usd_irt_toman(50_000_000) is False

    def test_non_numeric_is_implausible(self):
        assert es.is_plausible_usd_irt_toman('garbage') is False
        assert es.is_plausible_usd_irt_toman(None) is False

    def test_nan_and_inf_are_implausible(self):
        assert es.is_plausible_usd_irt_toman(float('nan')) is False
        assert es.is_plausible_usd_irt_toman(float('inf')) is False

    def test_boundary_values_are_inclusive(self):
        assert es.is_plausible_usd_irt_toman(es.SANITY_MIN_TOMAN) is True
        assert es.is_plausible_usd_irt_toman(es.SANITY_MAX_TOMAN) is True
        assert es.is_plausible_usd_irt_toman(es.SANITY_MIN_TOMAN - 1) is False
        assert es.is_plausible_usd_irt_toman(es.SANITY_MAX_TOMAN + 1) is False


class TestApplyUnit:
    def test_toman_passes_through(self):
        assert es._apply_unit(203_700, 'toman') == 203_700

    def test_rial_divides_by_ten(self):
        assert es._apply_unit(2_037_000, 'rial') == 203_700.0


# ── validate_source_url (SSRF guard) ──────────────────────────────────────

class TestValidateSourceUrl:
    def test_accepts_a_normal_https_url(self):
        assert es.validate_source_url('https://example.com/rate') is None

    def test_rejects_http(self):
        assert es.validate_source_url('http://example.com/rate') is not None

    def test_rejects_localhost(self):
        assert es.validate_source_url('https://localhost/rate') is not None

    def test_rejects_loopback_ip(self):
        assert es.validate_source_url('https://127.0.0.1/rate') is not None

    def test_rejects_private_ip(self):
        assert es.validate_source_url('https://10.0.0.5/rate') is not None

    def test_rejects_known_internal_service_name(self):
        assert es.validate_source_url('https://sanjabai_pg/rate') is not None

    def test_rejects_empty(self):
        assert es.validate_source_url('') is not None

    def test_rejects_overlong(self):
        assert es.validate_source_url('https://example.com/' + 'a' * 3000) is not None


# ── validate_custom_regex_pattern (ReDoS guard) ───────────────────────────

class TestValidateCustomRegexPattern:
    def test_accepts_a_reasonable_pattern(self):
        assert es.validate_custom_regex_pattern(r'USD\s*=\s*([\d,]+)') is None

    def test_rejects_empty(self):
        assert es.validate_custom_regex_pattern('') is not None

    def test_rejects_no_capture_group(self):
        assert es.validate_custom_regex_pattern(r'\d+') is not None

    def test_rejects_overlong_pattern(self):
        assert es.validate_custom_regex_pattern('(' + 'a' * 300 + ')') is not None

    def test_rejects_invalid_regex_syntax(self):
        assert es.validate_custom_regex_pattern('(unclosed') is not None

    def test_rejects_classic_redos_shape(self):
        assert es.validate_custom_regex_pattern(r'(.*)+') is not None
        assert es.validate_custom_regex_pattern(r'(a+)+') is not None


class TestBoundedSearch:
    def test_matches_within_cap(self):
        m = es._bounded_search(r'usd=(\d+)', 'prefix usd=12345 suffix')
        assert m and m.group(1) == '12345'

    def test_target_past_cap_is_not_found_not_crashed(self):
        # Anything past _MAX_EXTRACT_TEXT_BYTES is simply invisible to the
        # search -- a deliberate bound, not a bug -- and must not raise.
        haystack = ('x' * (es._MAX_EXTRACT_TEXT_BYTES + 100)) + 'usd=99999'
        m = es._bounded_search(r'usd=(\d+)', haystack)
        assert m is None

    def test_no_match_returns_none(self):
        assert es._bounded_search(r'usd=(\d+)', 'nothing here') is None


# ── get_flat_markup_toman ─────────────────────────────────────────────────

class TestGetFlatMarkupToman:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value(self):
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=json.dumps(3500.0))):
            value = await es.get_flat_markup_toman()
        assert value == 3500.0

    @pytest.mark.asyncio
    async def test_cache_miss_reads_db_value(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(value=3500))
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(content_mod.rds, 'setex', new=AsyncMock()):
            value = await es.get_flat_markup_toman()
        assert value == 3500.0

    @pytest.mark.asyncio
    async def test_missing_row_falls_back_to_default_not_zero(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(content_mod.rds, 'setex', new=AsyncMock()):
            value = await es.get_flat_markup_toman()
        assert value == content_mod.USD_IRT_FLAT_MARKUP
        assert value != 0

    @pytest.mark.asyncio
    async def test_db_error_falls_back_to_default_not_zero(self):
        broken_session_maker = MagicMock(side_effect=Exception('db down'))
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=None)), \
             patch.object(es, 'async_session', broken_session_maker):
            value = await es.get_flat_markup_toman()
        assert value == content_mod.USD_IRT_FLAT_MARKUP

    @pytest.mark.asyncio
    async def test_cache_read_wrong_shape_degrades_to_db_not_crash(self, mock_async_session):
        # Mirrors get_global_markup_pct()'s resilience: a value cached under
        # the WRONG key shape (e.g. a dict from a blanket-mocked rds.get in
        # another code path) must not raise -- it must fall through to the DB.
        mock_async_session._execute_result = make_result(fetchone=make_row(value=4000))
        with patch.object(content_mod.rds, 'get', new=AsyncMock(return_value=json.dumps({'not': 'a number'}))), \
             patch.object(content_mod.rds, 'setex', new=AsyncMock()):
            value = await es.get_flat_markup_toman()
        assert value == 4000.0


# ── resolve_configured_sources ────────────────────────────────────────────

class TestResolveConfiguredSources:
    @pytest.mark.asyncio
    async def test_no_rows_returns_none_none(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[])
        rate, source = await es.resolve_configured_sources()
        assert (rate, source) == (None, None)

    @pytest.mark.asyncio
    async def test_bonbast_row_success_wins(self, mock_async_session):
        row = make_row(source_key='bonbast', display_name='Bonbast.com', kind='bonbast',
                        url=None, unit='toman', extract_regex=None, timeout_s=8)
        mock_async_session._execute_result = make_result(fetchall=[row])
        with patch.object(es, '_fetch_bonbast_rate', new=AsyncMock(return_value=203_700.0)):
            rate, source = await es.resolve_configured_sources()
        assert (rate, source) == (203_700.0, 'bonbast')

    @pytest.mark.asyncio
    async def test_implausible_rate_is_rejected_and_skipped(self, mock_async_session):
        row = make_row(source_key='bonbast', display_name='Bonbast.com', kind='bonbast',
                        url=None, unit='toman', extract_regex=None, timeout_s=8)
        mock_async_session._execute_result = make_result(fetchall=[row])
        with patch.object(es, '_fetch_bonbast_rate', new=AsyncMock(return_value=5.0)):  # absurdly low
            rate, source = await es.resolve_configured_sources()
        assert (rate, source) == (None, None)

    @pytest.mark.asyncio
    async def test_fetch_failure_falls_through_to_next_row(self, mock_async_session):
        bonbast_row = make_row(source_key='bonbast', display_name='Bonbast.com', kind='bonbast',
                                url=None, unit='toman', extract_regex=None, timeout_s=8)
        custom_row = make_row(source_key='mysite', display_name='My Site', kind='custom_regex',
                               url='https://example.com/x', unit='toman', extract_regex=r'usd=(\d+)', timeout_s=5)
        mock_async_session._execute_result = make_result(fetchall=[bonbast_row, custom_row])
        with patch.object(es, '_fetch_bonbast_rate', new=AsyncMock(return_value=None)), \
             patch.object(es, '_fetch_custom_regex_rate', new=AsyncMock(return_value=210_000.0)):
            rate, source = await es.resolve_configured_sources()
        assert (rate, source) == (210_000.0, 'mysite')

    @pytest.mark.asyncio
    async def test_unknown_kind_is_skipped_not_crashed(self, mock_async_session):
        row = make_row(source_key='mystery', display_name='?', kind='not_a_real_kind',
                        url=None, unit='toman', extract_regex=None, timeout_s=5)
        mock_async_session._execute_result = make_result(fetchall=[row])
        rate, source = await es.resolve_configured_sources()
        assert (rate, source) == (None, None)

    @pytest.mark.asyncio
    async def test_db_read_failure_returns_none_none_not_crash(self):
        broken_session_maker = MagicMock(side_effect=Exception('db down'))
        with patch.object(es, 'async_session', broken_session_maker):
            rate, source = await es.resolve_configured_sources()
        assert (rate, source) == (None, None)


# ── Bonbast fetcher ────────────────────────────────────────────────────────

def _mock_bonbast_http(token_page: str, json_body: dict):
    page_resp = MagicMock()
    page_resp.raise_for_status = MagicMock()
    page_resp.text = token_page
    json_resp = MagicMock()
    json_resp.raise_for_status = MagicMock()
    json_resp.json = MagicMock(return_value=json_body)
    http = MagicMock()
    http.get = AsyncMock(return_value=page_resp)
    http.post = AsyncMock(return_value=json_resp)
    return http


class TestFetchBonbastRate:
    @pytest.mark.asyncio
    async def test_happy_path_extracts_usd1_as_toman_no_conversion(self):
        page = 'blah $.post(\'/json\', {param: "abc123,XYZ,2026-08-25-00-00-00"}, function(json){...'
        http = _mock_bonbast_http(page, {'usd1': '203,700', 'usd2': '203600'})
        with patch.object(content_mod, '_http', http):
            rate = await es._fetch_bonbast_rate()
        assert rate == 203_700.0
        # token from the page was forwarded as the POST body's `param` field
        _, kwargs = http.post.call_args
        assert kwargs['data']['param'] == 'abc123,XYZ,2026-08-25-00-00-00'

    @pytest.mark.asyncio
    async def test_reset_response_is_treated_as_failure(self):
        page = '$.post(\'/json\', {param: "abc123,XYZ,2026-08-25-00-00-00"}, function(json){...'
        http = _mock_bonbast_http(page, {'reset': '1'})
        with patch.object(content_mod, '_http', http):
            rate = await es._fetch_bonbast_rate()
        assert rate is None

    @pytest.mark.asyncio
    async def test_missing_token_in_page_is_none_not_crash(self):
        http = _mock_bonbast_http('no token here at all', {'usd1': '203700'})
        with patch.object(content_mod, '_http', http):
            rate = await es._fetch_bonbast_rate()
        assert rate is None

    @pytest.mark.asyncio
    async def test_network_error_is_none_not_raised(self):
        http = MagicMock()
        http.get = AsyncMock(side_effect=Exception('connection reset'))
        with patch.object(content_mod, '_http', http):
            rate = await es._fetch_bonbast_rate()
        assert rate is None


# ── Custom regex fetcher ───────────────────────────────────────────────────

class TestFetchCustomRegexRate:
    @pytest.mark.asyncio
    async def test_toman_source_no_conversion(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.text = 'the rate is usd=203700 today'
        http = MagicMock()
        http.get = AsyncMock(return_value=resp)
        row = make_row(source_key='mysite', url='https://example.com', unit='toman',
                        extract_regex=r'usd=(\d+)', timeout_s=5)
        with patch.object(content_mod, '_http', http):
            rate = await es._fetch_custom_regex_rate(row)
        assert rate == 203_700.0
        assert http.get.call_args.kwargs['follow_redirects'] is False

    @pytest.mark.asyncio
    async def test_rial_source_divides_by_ten(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.text = 'rate=2037000'
        http = MagicMock()
        http.get = AsyncMock(return_value=resp)
        row = make_row(source_key='mysite', url='https://example.com', unit='rial',
                        extract_regex=r'rate=(\d+)', timeout_s=5)
        with patch.object(content_mod, '_http', http):
            rate = await es._fetch_custom_regex_rate(row)
        assert rate == 203_700.0

    @pytest.mark.asyncio
    async def test_no_regex_match_is_none(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.text = 'nothing useful here'
        http = MagicMock()
        http.get = AsyncMock(return_value=resp)
        row = make_row(source_key='mysite', url='https://example.com', unit='toman',
                        extract_regex=r'usd=(\d+)', timeout_s=5)
        with patch.object(content_mod, '_http', http):
            rate = await es._fetch_custom_regex_rate(row)
        assert rate is None

    @pytest.mark.asyncio
    async def test_fetch_exception_is_none_not_raised(self):
        http = MagicMock()
        http.get = AsyncMock(side_effect=Exception('timeout'))
        row = make_row(source_key='mysite', url='https://example.com', unit='toman',
                        extract_regex=r'usd=(\d+)', timeout_s=5)
        with patch.object(content_mod, '_http', http):
            rate = await es._fetch_custom_regex_rate(row)
        assert rate is None


# ── content.py integration: the new tier composes with the old ladder ────

class TestComputeExchangeRateWithConfiguredSources:
    """content._compute_exchange_rate() must still exist and still call
    services.exchange_sources when tgju fails -- this is the one seam
    between the two files, asserted here so a future edit to either side
    trips a test instead of silently breaking the wiring."""

    @pytest.mark.asyncio
    async def test_configured_source_wins_when_tgju_fails(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(content_mod, '_fetch_tgju_rate', new=AsyncMock(return_value=None)), \
             patch.object(es, 'resolve_configured_sources', new=AsyncMock(return_value=(210_000.0, 'bonbast'))):
            rate, pct, source = await content_mod._compute_exchange_rate()
        assert (rate, source) == (210_000.0, 'bonbast')

    @pytest.mark.asyncio
    async def test_tgju_success_never_reaches_configured_sources(self, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(content_mod, '_fetch_tgju_rate', new=AsyncMock(return_value=1_000_000.0)), \
             patch.object(es, 'resolve_configured_sources', new=AsyncMock()) as mock_resolve:
            rate, pct, source = await content_mod._compute_exchange_rate()
        assert source == 'tgju'
        mock_resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_implausible_tgju_rate_is_rejected_then_falls_through(self, mock_async_session):
        # 100 Toman/USD is absurd -- must not be trusted even though tgju
        # "succeeded" in the sense of returning a number.
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(content_mod, '_fetch_tgju_rate', new=AsyncMock(return_value=1_000.0)), \
             patch.object(es, 'resolve_configured_sources', new=AsyncMock(return_value=(None, None))), \
             patch.object(content_mod, '_http', MagicMock(get=AsyncMock(side_effect=Exception('down')))):
            rate, pct, source = await content_mod._compute_exchange_rate()
        assert source == 'hardcoded_fallback'
