"""Tests for the self-hosted SearXNG source added to `_web_search` on
2026-08-30 (the "0.5" tier in chat_search.py).

Why this exists
----------------
The owner asked for reliable free real-time web search without a paid key.
The prior keyless path (DuckDuckGo HTML SERP) works but this server's IP gets
throttled to a 202 anomaly page after ~7 rapid requests, so under sustained
chat traffic many searches silently fall through to the encyclopedic tiers.
We now run our own SearXNG instance (sanjabai_searxng, internal net only) and
query it at format=json as the PRIMARY keyless source, before DDG-HTML.

This suite pins:
  1. the network path: a 200 JSON payload from SearXNG is parsed into real
     bullet results (title, hostname, snippet, url) and short-circuits every
     source below it;
  2. the never-raises / degrade contract: a dead instance (connection error),
     a non-200, malformed JSON, or an empty results list must degrade to the
     DDG-HTML tier rather than propagate;
  3. that SEARXNG_URL='' disables the tier entirely (the escape hatch the
     other web-search suites rely on).

No test makes a real network call -- httpx.AsyncClient is replaced entirely,
same pattern as tests/test_web_search_freehtml.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import chat_search


_KEY_VARS = ['WEB_SEARCH_PROVIDER', 'BRAVE_SEARCH_API_KEY', 'TAVILY_API_KEY', 'SERPER_API_KEY']

SEARX_URL = 'http://sanjabai_searxng:8080/search'

# A realistic SearXNG format=json payload: a list of result dicts each with
# title/url/content (the fields chat_search reads). Mirrors the live shape
# verified on 2026-08-30 (tgju.org gold-price results).
SEARX_JSON = {
    'query': 'قیمت طلا امروز',
    'number_of_results': 0,
    'results': [
        {
            'title': 'قیمت طلای 18 عیار امروز - TGJU',
            'url': 'https://www.tgju.org/gold-price',
            'content': 'نرخ فعلی طلای ۱۸ عیار: ۲۱۸٬۳۹۶٬۰۰۰ ریال',
        },
        {
            'title': 'قیمت لحظه‌ای طلا و سکه',
            'url': 'https://alanchand.com/gold-price',
            'content': 'قیمت هر گرم طلای ۱۸ عیار در بازار امروز',
        },
    ],
}


@pytest.fixture(autouse=True)
def _clear_search_env(monkeypatch):
    """No keyed provider leaks in (so the keyed tier is skipped and we reach
    SearXNG), and SEARXNG_URL is pinned to a known value for the tests that
    need the tier active."""
    for var in _KEY_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('SEARXNG_URL', SEARX_URL)


def _fake_json_response(status_code=200, data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=data if data is not None else {})
    return resp


def _fake_async_client(get_fn):
    """Stand-in for httpx.AsyncClient exposing only the async `.get()` the
    module calls. `get_fn(url, params)` decides the response, or raises to
    simulate a network failure/timeout/connection-refused."""
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None, headers=None):
            return get_fn(url, params)

    return _FakeAsyncClient


class TestSearxngNetworkPath:
    @pytest.mark.asyncio
    async def test_searxng_json_is_parsed_and_short_circuits(self, monkeypatch):
        """A 200 JSON payload from SearXNG must be parsed into bullet results
        and must NOT reach any source below it (DDG-HTML etc.)."""
        def _respond(url, params):
            if url == SEARX_URL:
                assert params['q'] == 'قیمت طلا امروز'
                assert params['format'] == 'json'
                return _fake_json_response(200, SEARX_JSON)
            raise AssertionError(f'no source below SearXNG should be reached: {url}')

        monkeypatch.setattr('httpx.AsyncClient', _fake_async_client(_respond))
        result = await chat_search._web_search('قیمت طلا امروز')

        assert 'قیمت طلای 18 عیار امروز - TGJU' in result
        assert 'https://www.tgju.org/gold-price' in result
        assert 'tgju.org' in result           # hostname tag
        assert '۲۱۸٬۳۹۶٬۰۰۰' in result          # snippet content preserved
        assert 'alanchand.com' in result

    @pytest.mark.asyncio
    async def test_connection_error_degrades_to_next_source(self, monkeypatch):
        """A dead SearXNG instance (connection refused / timeout) must fall
        through to the DDG-HTML tier, not raise."""
        reached = []

        def _respond(url, params):
            reached.append(url)
            if url == SEARX_URL:
                raise ConnectionError('connection refused')
            # DDG-HTML tier: return a non-200 so it too degrades; the point is
            # that we got past SearXNG without raising.
            resp = MagicMock()
            resp.status_code = 500
            resp.text = ''
            resp.json = MagicMock(return_value={})
            return resp

        monkeypatch.setattr('httpx.AsyncClient', _fake_async_client(_respond))
        result = await chat_search._web_search('قیمت طلا امروز')  # must not raise

        assert SEARX_URL in reached
        assert any('duckduckgo' in u for u in reached), 'must degrade to a DDG source'
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_non_200_degrades(self, monkeypatch):
        reached = []

        def _respond(url, params):
            reached.append(url)
            if url == SEARX_URL:
                return _fake_json_response(502, {})
            resp = MagicMock()
            resp.status_code = 500
            resp.text = ''
            resp.json = MagicMock(return_value={})
            return resp

        monkeypatch.setattr('httpx.AsyncClient', _fake_async_client(_respond))
        result = await chat_search._web_search('x')

        assert any('duckduckgo' in u for u in reached)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_empty_results_degrades(self, monkeypatch):
        """A 200 with an empty results list is not a hit -- degrade."""
        reached = []

        def _respond(url, params):
            reached.append(url)
            if url == SEARX_URL:
                return _fake_json_response(200, {'results': []})
            resp = MagicMock()
            resp.status_code = 500
            resp.text = ''
            resp.json = MagicMock(return_value={})
            return resp

        monkeypatch.setattr('httpx.AsyncClient', _fake_async_client(_respond))
        result = await chat_search._web_search('x')

        assert any('duckduckgo' in u for u in reached)

    @pytest.mark.asyncio
    async def test_malformed_json_degrades(self, monkeypatch):
        """`.json()` raising (non-JSON body) must degrade, not propagate."""
        reached = []

        def _respond(url, params):
            reached.append(url)
            if url == SEARX_URL:
                resp = MagicMock()
                resp.status_code = 200
                resp.json = MagicMock(side_effect=ValueError('not json'))
                return resp
            resp = MagicMock()
            resp.status_code = 500
            resp.text = ''
            resp.json = MagicMock(return_value={})
            return resp

        monkeypatch.setattr('httpx.AsyncClient', _fake_async_client(_respond))
        result = await chat_search._web_search('x')  # must not raise

        assert any('duckduckgo' in u for u in reached)


class TestSearxngDisabled:
    @pytest.mark.asyncio
    async def test_empty_url_skips_tier_entirely(self, monkeypatch):
        """SEARXNG_URL='' must skip the tier without any network call to it."""
        monkeypatch.setenv('SEARXNG_URL', '')
        reached = []

        def _respond(url, params):
            reached.append(url)
            resp = MagicMock()
            resp.status_code = 500
            resp.text = ''
            resp.json = MagicMock(return_value={})
            return resp

        monkeypatch.setattr('httpx.AsyncClient', _fake_async_client(_respond))
        await chat_search._web_search('x')

        assert SEARX_URL not in reached, 'disabled tier must not be contacted'
        # Also catch a broken guard that runs the tier anyway: with the tier
        # disabled it would GET '' (the empty url), so an empty-string request
        # is proof the `if _searx_url:` guard was bypassed. (qa finding
        # 2026-08-30: without this, an `if True:` mutation slipped through
        # because GET '' != SEARX_URL.)
        assert '' not in reached, 'disabled tier must issue NO searxng request at all'
