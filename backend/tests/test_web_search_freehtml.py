"""Tests for the DuckDuckGo HTML SERP source added to `_web_search` on
2026-08-30 (`_parse_ddg_html_results` / `_unwrap_ddg_redirect` in
chat_search.py).

Why this exists
----------------
Before this change, `_web_search`'s only keyless sources were the
DuckDuckGo Instant Answer API and Wikipedia intro extracts -- both
encyclopedic and unable to answer a time-sensitive query at all (live-tested:
"قیمت طلای امروز" returned the Wikipedia article on gold, not a price).
A fresh probe from this server on 2026-08-30 found html.duckduckgo.com/html/
returns real 200 pages with organic results in bursts of ~7 requests before
its anomaly detector flips it to a 202 challenge page for a while -- see
`_web_search`'s docstring for the full evidence. This suite pins:

  1. the network path: a 200 HTML page is parsed into real bullet results
     containing the fixture's titles/URLs (including a DDG-internal
     redirect link correctly unwrapped to its real target);
  2. the never-raises contract: a timeout/exception on this source must
     degrade to the next source (Wikipedia) rather than propagate;
  3. `_parse_ddg_html_results` and `_unwrap_ddg_redirect` directly, against
     both a hand-written fixture and a real page saved live from DDG.

No test makes a real network call -- httpx.AsyncClient is replaced entirely,
same pattern as tests/test_web_search.py.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import chat_search


FIXTURES_DIR = Path(__file__).parent / 'fixtures'
REAL_SERP_HTML = (FIXTURES_DIR / 'ddg_html_serp.html').read_text(encoding='utf-8')

# Small, hand-written fixture matching DDG HTML SERP markup precisely (result
# container div, result__a, result__snippet) -- kept short and separate from
# the full page saved live so the network-path test only depends on the
# container/anchor shape being right, not on any real page staying
# byte-identical over time. First result uses a direct href; second uses the
# `//duckduckgo.com/l/?uddg=...` redirect shape also observed live, so this
# fixture alone proves both href shapes are handled.
SMALL_SERP_HTML = """
<div class="serp__results">
  <div class="result results_links results_links_deep web-result ">
    <div class="links_main links_deep result__body">
      <h2 class="result__title">
        <a rel="nofollow" class="result__a" href="https://example.com/gold-price">قیمت طلای امروز - سایت مثال</a>
      </h2>
      <a class="result__snippet" href="https://example.com/gold-price">امروز <b>قیمت طلا</b> به ۴٬۵۰۰٬۰۰۰ تومان رسید.</a>
    </div>
  </div>
  <div class="result results_links results_links_deep web-result ">
    <div class="links_main links_deep result__body">
      <h2 class="result__title">
        <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnews.example.org%2Fgold&amp;rut=abc123">نرخ لحظه‌ای طلا - نیوز مثال</a>
      </h2>
      <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnews.example.org%2Fgold&amp;rut=abc123">نرخ لحظه‌ای طلا در بازار امروز اعلام شد.</a>
    </div>
  </div>
</div>
"""

# A stand-in for the 202 "anomaly" bot-challenge page DDG serves once a
# source IP has sent too many requests too fast -- observed live on
# 2026-08-30 (see chat_search.py). It has zero `result__a` occurrences.
ANOMALY_HTML = """
<html><body>
<form id="img-form" action="//duckduckgo.com/anomaly.js?sv=html&cc=botnet&ti=123"></form>
</body></html>
"""

_KEY_VARS = ['WEB_SEARCH_PROVIDER', 'BRAVE_SEARCH_API_KEY', 'TAVILY_API_KEY', 'SERPER_API_KEY']


@pytest.fixture(autouse=True)
def _clear_search_env(monkeypatch):
    """No keyed provider leaks in from the ambient environment -- these
    tests must reliably reach the DDG-HTML tier, not the keyed tier. Also
    neutralize SEARXNG_URL: SearXNG is now the primary keyless source (tried
    before DDG-HTML), so leaving it set would make _web_search reach for the
    internal SearXNG host first; setting it empty skips that tier so these
    DDG-focused tests exercise exactly the path they pin. The SearXNG tier
    has its own suite (test_web_search_searxng.py)."""
    for var in _KEY_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('SEARXNG_URL', '')


def _fake_response(status_code=200, text=''):
    """A minimal stand-in for an httpx.Response used by the HTML tier:
    only `.status_code` and `.text` are read on this path."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


def _fake_json_response(status_code=200, data=None):
    """A minimal stand-in for an httpx.Response used by the IA/Wikipedia
    tiers: `.status_code` and a sync `.json()`."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=data if data is not None else {})
    return resp


def _fake_async_client(get_fn):
    """Stand-in for httpx.AsyncClient exposing only the async `.get()` this
    module actually calls -- `get_fn(url, params)` decides the response, or
    can raise to simulate a network failure/timeout."""
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


class TestDdgHtmlNetworkPath:
    """1. A real 200 HTML page from html.duckduckgo.com/html/ must be parsed
    into bullet results containing the fixture's titles/URLs, and must
    short-circuit the DDG-IA/Wikipedia sources below it entirely."""

    @pytest.mark.asyncio
    async def test_html_serp_results_are_parsed_and_returned(self, monkeypatch):
        def _respond(url, params):
            if url == 'https://html.duckduckgo.com/html/':
                assert params['q'] == 'قیمت طلای امروز'
                return _fake_response(200, SMALL_SERP_HTML)
            raise AssertionError(f'no source below DDG-HTML should be reached: {url}')

        monkeypatch.setattr('httpx.AsyncClient', _fake_async_client(_respond))
        result = await chat_search._web_search('قیمت طلای امروز')

        assert 'قیمت طلای امروز - سایت مثال' in result
        assert 'https://example.com/gold-price' in result
        assert 'امروز' in result and 'تومان' in result
        # second result's DDG-redirect href must be unwrapped to its real
        # target, not left as a useless protocol-relative DDG-internal link
        assert 'نرخ لحظه‌ای طلا - نیوز مثال' in result
        assert 'https://news.example.org/gold' in result
        assert 'duckduckgo.com/l/' not in result

    @pytest.mark.asyncio
    async def test_anomaly_challenge_page_degrades_to_next_source(self, monkeypatch):
        """A 200 response whose body is the anomaly-challenge page (not real
        results) must NOT be reported as a hit -- it has to fall through to
        DDG-IA, same as a non-200 or a network failure would."""
        calls = []

        def _respond(url, params):
            calls.append(url)
            if url == 'https://html.duckduckgo.com/html/':
                return _fake_response(200, ANOMALY_HTML)
            if url == 'https://api.duckduckgo.com/':
                return _fake_json_response(200, {
                    'Heading': 'Gold',
                    'AbstractText': 'Gold is a chemical element.',
                    'AbstractURL': 'https://en.wikipedia.org/wiki/Gold',
                    'RelatedTopics': [],
                })
            raise AssertionError(f'unexpected URL: {url}')

        monkeypatch.setattr('httpx.AsyncClient', _fake_async_client(_respond))
        result = await chat_search._web_search('gold price today')

        assert 'Gold is a chemical element.' in result
        assert 'https://html.duckduckgo.com/html/' in calls
        assert 'https://api.duckduckgo.com/' in calls


class TestDdgHtmlNeverRaises:
    """2. Timeout/exception on the DDG-HTML source must degrade to the next
    source (Wikipedia) rather than propagate -- the documented never-raises
    contract `_web_search` already holds for every other source."""

    @pytest.mark.asyncio
    async def test_timeout_on_html_serp_falls_through_to_wikipedia(self, monkeypatch):
        def _respond(url, params):
            if url == 'https://html.duckduckgo.com/html/':
                raise TimeoutError('simulated DDG-HTML timeout')
            if url == 'https://api.duckduckgo.com/':
                return _fake_json_response(200, {'AbstractText': '', 'RelatedTopics': []})
            if 'wikipedia.org' in url:
                return _fake_json_response(200, {'query': {'pages': {
                    '1': {'index': 1, 'title': 'Gold', 'extract': 'Gold is a chemical element with symbol Au.'},
                }}})
            raise AssertionError(f'unexpected URL: {url}')

        monkeypatch.setattr('httpx.AsyncClient', _fake_async_client(_respond))
        result = await chat_search._web_search('gold')

        assert 'Gold is a chemical element with symbol Au.' in result

    @pytest.mark.asyncio
    async def test_timeout_on_html_serp_with_all_sources_failing_returns_empty(self, monkeypatch):
        def _respond(url, params):
            if url == 'https://html.duckduckgo.com/html/':
                raise TimeoutError('simulated DDG-HTML timeout')
            return _fake_response(500, '')

        monkeypatch.setattr('httpx.AsyncClient', _fake_async_client(_respond))
        result = await chat_search._web_search('چیزی که پیدا نمی‌شود')

        assert result == ''


class TestParseDdgHtmlResultsDirectly:
    """3a. Unit-test the pure parser directly -- no network, no _web_search
    involved -- against a saved real page and a hand-written fixture."""

    def test_hand_written_fixture_both_href_shapes(self):
        hits = chat_search._parse_ddg_html_results(SMALL_SERP_HTML, max_results=5)
        assert len(hits) == 2
        assert hits[0]['title'] == 'قیمت طلای امروز - سایت مثال'
        assert hits[0]['url'] == 'https://example.com/gold-price'
        assert 'قیمت طلا' in hits[0]['snippet']
        # DDG-redirect href unwrapped to the real target
        assert hits[1]['url'] == 'https://news.example.org/gold'

    def test_real_saved_page_parses_ten_results(self):
        """Fixture captured live from html.duckduckgo.com/html/ on
        2026-08-30 for query 'قیمت طلای امروز' -- a real 200 page, not a
        synthetic one, so this pins the parser against actual upstream
        markup rather than only against a fixture we wrote ourselves."""
        hits = chat_search._parse_ddg_html_results(REAL_SERP_HTML, max_results=10)
        assert len(hits) == 10
        assert all(h['title'] and h['url'] for h in hits)
        # every URL must be a real destination, never a DDG-internal link
        assert all('duckduckgo.com' not in h['url'] for h in hits)
        titles = ' '.join(h['title'] for h in hits)
        assert 'قیمت' in titles

    def test_max_results_caps_output(self):
        hits = chat_search._parse_ddg_html_results(REAL_SERP_HTML, max_results=3)
        assert len(hits) == 3

    def test_anomaly_page_parses_to_empty_list(self):
        assert chat_search._parse_ddg_html_results(ANOMALY_HTML, max_results=5) == []

    def test_empty_string_parses_to_empty_list(self):
        assert chat_search._parse_ddg_html_results('', max_results=5) == []


class TestUnwrapDdgRedirectDirectly:
    """3b. Unit-test the redirect-unwrap helper on its own."""

    def test_direct_href_passed_through_unchanged(self):
        assert chat_search._unwrap_ddg_redirect('https://example.com/page') == 'https://example.com/page'

    def test_ddg_redirect_href_unwrapped_to_real_target(self):
        href = '//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.tgju.org%2F&rut=0be24e0a1a98'
        assert chat_search._unwrap_ddg_redirect(href) == 'https://www.tgju.org/'

    def test_bare_protocol_relative_href_upgraded_to_https(self):
        assert chat_search._unwrap_ddg_redirect('//example.com/page') == 'https://example.com/page'
