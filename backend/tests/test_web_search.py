"""Regression tests for the web_search bug.

Root cause (see chat.py's module docstring / NEXT-SESSION notes): there is no
tool-calling in this backend at all. Web search is prompt injection --
`/v1/chat/completions` pops `web_search` off the request and, if truthy,
injects DuckDuckGo/Wikipedia results as a system message (see
`_apply_web_search` in chat.py). `/v1/smart-chat` used to never read the flag
at all: it silently dropped the user's request AND forwarded the stray
`web_search` key upstream, unread, in the JSON body sent to the provider.

Both handlers now call the same `_apply_web_search(payload_dict, handler=...)`
helper so they cannot drift apart again. These tests pin that behavior:

  1. `/v1/smart-chat` triggers the injection when `web_search: true` is sent.
  2. Neither handler forwards the raw `web_search` key upstream.
  3. `_web_search` is never called when the flag is absent/false.

No test makes a real network call: `_web_search` and the upstream HTTP client
are always mocked. Auth, free-tier throttling, billing reservation, and
provider routing are bypassed via module-level patches on `chat` so these
tests exercise only the web_search wiring, not the rest of the request
pipeline (that's covered elsewhere -- test_billing*.py, test_free_tier.py).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import chat_web
import database as _db


AUTH_HEADERS = {'Authorization': 'Bearer test-token'}

# X-Smart-Model forces smart-chat's model selection so tests don't depend on
# _analyze_message's category heuristics -- tencent-hy3 is in chat.py's
# hardcoded working set, so the whitelist check passes without touching a DB.
SMART_HEADERS = {**AUTH_HEADERS, 'X-Smart-Model': 'tencent-hy3'}


class _FakeProvider:
    v1 = 'http://fake-upstream/v1'

    def headers(self):
        return {'Content-Type': 'application/json'}


def _billing_mock():
    """A BillingService replacement whose reserve()/release() never touch a
    real DB -- these tests care about web_search wiring, not billing."""
    instance = MagicMock()
    instance.reserve = AsyncMock(return_value={'reservation_id': 'test-reservation'})
    instance.release = AsyncMock(return_value=None)
    instance.settle = AsyncMock(return_value=None)
    return MagicMock(return_value=instance)


def _upstream_response(body: dict | None = None, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=body or {'choices': [{'message': {'content': 'پاسخ نمونه'}}]})
    resp.content = b'{}'
    return resp


@pytest.fixture(autouse=True)
def _bypass_pipeline():
    """Bypass auth, free-tier throttling, billing reservation, and provider
    routing for every test in this file -- none of that is what's under test.
    """
    with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)), \
         patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
         patch.object(chat_mod, 'BillingService', _billing_mock()), \
         patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())):
        yield


def _patched_http(capture: dict | None = None, body: dict | None = None):
    """A fake `_real_http` whose .post optionally records its `json=` kwarg."""
    fake = MagicMock()

    if capture is not None:
        async def _post(url, json=None, headers=None, timeout=None):
            capture['json'] = json
            capture['url'] = url
            return _upstream_response(body)
        fake.post = _post
    else:
        fake.post = AsyncMock(return_value=_upstream_response(body))
    return fake


class TestSmartChatTriggersWebSearch:
    """1. /v1/smart-chat must trigger the same injection chat/completions does."""

    def test_smart_chat_awaits_web_search_with_last_user_message(self, client):
        with patch.object(chat_mod, '_web_search', AsyncMock(return_value='• نتیجه\n  خلاصه\n  http://example.com')) as mock_search, \
             patch.object(_db, '_real_http', _patched_http()):
            resp = client.post(
                '/v1/smart-chat',
                json={
                    'model': 'tencent-hy3',
                    'messages': [{'role': 'user', 'content': 'قیمت دلار امروز در بازار آزاد چند است؟'}],
                    'web_search': True,
                    'stream': False,
                },
                headers=SMART_HEADERS,
            )

        assert resp.status_code == 200, resp.text
        mock_search.assert_awaited_once()
        awaited_query = mock_search.await_args.args[0]
        assert awaited_query == 'قیمت دلار امروز در بازار آزاد چند است؟'

    def test_chat_completions_still_awaits_web_search_regression(self, client):
        """Same behavior on the endpoint that always worked -- guards against
        the shared helper accidentally changing chat/completions' behavior."""
        with patch.object(chat_mod, '_web_search', AsyncMock(return_value='• x\n  y\n  http://z')) as mock_search, \
             patch.object(_db, '_real_http', _patched_http()):
            resp = client.post(
                '/v1/chat/completions',
                json={
                    'model': 'tencent-hy3',
                    'messages': [{'role': 'user', 'content': 'وضعیت آب و هوای تهران امروز'}],
                    'web_search': True,
                    'stream': False,
                },
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 200, resp.text
        mock_search.assert_awaited_once()
        assert mock_search.await_args.args[0] == 'وضعیت آب و هوای تهران امروز'


class TestWebSearchNeverForwardedUpstream:
    """2. Regression: `web_search` must never appear in the JSON body sent to
    the provider -- from EITHER endpoint. This is the silent-forwarding half
    of the original bug (smart-chat used `model_dump(exclude_none=True)` and
    never popped the flag before proxying the payload upstream)."""

    def test_chat_completions_does_not_forward_web_search_key(self, client):
        captured: dict = {}
        with patch.object(chat_mod, '_web_search', AsyncMock(return_value='• result\n  snip\n  http://x')), \
             patch.object(_db, '_real_http', _patched_http(captured)):
            resp = client.post(
                '/v1/chat/completions',
                json={
                    'model': 'tencent-hy3',
                    'messages': [{'role': 'user', 'content': 'جستجو کن قیمت طلا امروز'}],
                    'web_search': True,
                    'stream': False,
                },
                headers=AUTH_HEADERS,
            )

        assert resp.status_code == 200, resp.text
        assert 'json' in captured, 'upstream _http.post was never called'
        assert 'web_search' not in captured['json']

    def test_smart_chat_does_not_forward_web_search_key(self, client):
        captured: dict = {}
        with patch.object(chat_mod, '_web_search', AsyncMock(return_value='• result\n  snip\n  http://x')), \
             patch.object(_db, '_real_http', _patched_http(captured)):
            resp = client.post(
                '/v1/smart-chat',
                json={
                    'model': 'tencent-hy3',
                    'messages': [{'role': 'user', 'content': 'جستجو کن قیمت طلا امروز'}],
                    'web_search': True,
                    'stream': False,
                },
                headers=SMART_HEADERS,
            )

        assert resp.status_code == 200, resp.text
        assert 'json' in captured, 'upstream _http.post was never called'
        assert 'web_search' not in captured['json']


class TestWebSearchNotCalledWhenAbsentOrFalse:
    """3. _web_search must not run at all when the flag is missing/false --
    on either endpoint."""

    def test_chat_completions_flag_false(self, client):
        with patch.object(chat_mod, '_web_search', AsyncMock()) as mock_search, \
             patch.object(_db, '_real_http', _patched_http()):
            resp = client.post(
                '/v1/chat/completions',
                json={
                    'model': 'tencent-hy3',
                    'messages': [{'role': 'user', 'content': 'سلام، حالت چطوره؟'}],
                    'web_search': False,
                    'stream': False,
                },
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        mock_search.assert_not_awaited()

    def test_chat_completions_flag_absent(self, client):
        with patch.object(chat_mod, '_web_search', AsyncMock()) as mock_search, \
             patch.object(_db, '_real_http', _patched_http()):
            resp = client.post(
                '/v1/chat/completions',
                json={
                    'model': 'tencent-hy3',
                    'messages': [{'role': 'user', 'content': 'سلام، حالت چطوره؟'}],
                    'stream': False,
                },
                headers=AUTH_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        mock_search.assert_not_awaited()

    def test_smart_chat_flag_absent(self, client):
        with patch.object(chat_mod, '_web_search', AsyncMock()) as mock_search, \
             patch.object(_db, '_real_http', _patched_http()):
            resp = client.post(
                '/v1/smart-chat',
                json={
                    'model': 'tencent-hy3',
                    'messages': [{'role': 'user', 'content': 'سلام، حالت چطوره؟'}],
                    'stream': False,
                },
                headers=SMART_HEADERS,
            )
        assert resp.status_code == 200, resp.text
        mock_search.assert_not_awaited()


class TestWebSearchObservability:
    """Part B of the fix: web_search requests must be logged (handler, a
    truncated query, and whether the search returned results) so an incident
    like the one that motivated this fix is diagnosable from logs."""

    def test_smart_chat_logs_handler_and_query_on_request(self, client, caplog):
        with patch.object(chat_mod, '_web_search', AsyncMock(return_value='• r\n  s\n  http://u')), \
             patch.object(_db, '_real_http', _patched_http()):
            with caplog.at_level('INFO', logger='chat'):
                resp = client.post(
                    '/v1/smart-chat',
                    json={
                        'model': 'tencent-hy3',
                        'messages': [{'role': 'user', 'content': 'اخبار امروز ایران چیست؟'}],
                        'web_search': True,
                        'stream': False,
                    },
                    headers=SMART_HEADERS,
                )
        assert resp.status_code == 200, resp.text
        messages = [r.message for r in caplog.records]
        assert any('web_search requested handler=smart-chat' in m and 'اخبار امروز ایران' in m for m in messages)
        assert any('web_search succeeded handler=smart-chat' in m for m in messages)


def _fake_response(status_code=200, data=None):
    """A minimal stand-in for an httpx.Response: sync .json(), no I/O."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=data if data is not None else {})
    return resp


def _fake_async_client(response_fn, captured_urls=None):
    """Return a class standing in for httpx.AsyncClient. `response_fn(url,
    params)` decides what each GET gets back; every requested URL is
    recorded (in call order) into `captured_urls` when given, so tests can
    assert which sources were (or were NOT) hit, and in what order --
    that's the whole point of the fa/en language-ordering tests below.
    """
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None, headers=None):
            if captured_urls is not None:
                captured_urls.append(url)
            return response_fn(url, params)

    return _FakeAsyncClient


# DDG-IA response with nothing usable, so _web_search always falls through to
# the Wikipedia fallback -- used by every test below that cares about the
# Wikipedia language ordering rather than the DDG-IA source itself.
_EMPTY_DDG = {'AbstractText': '', 'RelatedTopics': []}


class TestWebSearchRealImplementation:
    """Tests against the actual `_web_search` network/parsing logic (not the
    mocked stand-in used everywhere else in this file). No test makes a real
    network call -- httpx.AsyncClient is replaced entirely."""

    @pytest.mark.asyncio
    async def test_persian_query_tries_fa_wikipedia_before_en(self):
        """Language-aware fallback: a query containing Arabic-script
        characters must hit fa.wikipedia.org, and must never fall through to
        en.wikipedia.org once fa has already returned usable results."""
        captured: list = []

        def _respond(url, params):
            if 'duckduckgo.com' in url:
                return _fake_response(200, _EMPTY_DDG)
            if 'fa.wikipedia.org' in url:
                return _fake_response(200, {'query': {'pages': {
                    '1': {'index': 1, 'title': 'پایتخت ایران', 'extract': 'تهران پایتخت ایران است.'},
                }}})
            raise AssertionError(f'unexpected URL hit before fa succeeded: {url}')

        with patch('httpx.AsyncClient', _fake_async_client(_respond, captured)):
            result = await chat_web._web_search('پایتخت ایران کجاست')

        assert 'تهران' in result
        assert any('fa.wikipedia.org' in u for u in captured)
        assert not any('en.wikipedia.org' in u for u in captured)

    @pytest.mark.asyncio
    async def test_latin_query_tries_en_wikipedia_before_fa(self):
        """The mirror case: a Latin-script query must hit en.wikipedia.org
        first and never fall through to fa.wikipedia.org once en succeeds."""
        captured: list = []

        def _respond(url, params):
            if 'duckduckgo.com' in url:
                return _fake_response(200, _EMPTY_DDG)
            if 'en.wikipedia.org' in url:
                return _fake_response(200, {'query': {'pages': {
                    '1': {'index': 1, 'title': 'Tehran', 'extract': 'Tehran is the capital of Iran.'},
                }}})
            raise AssertionError(f'unexpected URL hit before en succeeded: {url}')

        with patch('httpx.AsyncClient', _fake_async_client(_respond, captured)):
            result = await chat_web._web_search('What is the capital of Iran')

        assert 'Tehran is the capital of Iran' in result
        assert any('en.wikipedia.org' in u for u in captured)
        assert not any('fa.wikipedia.org' in u for u in captured)

    @pytest.mark.asyncio
    async def test_output_is_html_unescaped(self):
        """Regression: the old output contained literal `&quot;` etc.
        straight from upstream JSON. Every title/snippet/extract must be
        passed through html.unescape() before formatting."""
        def _respond(url, params):
            if 'duckduckgo.com' in url:
                return _fake_response(200, {
                    'Heading': 'Tehran',
                    'AbstractText': 'Tehran is the &quot;capital&quot; of Iran &amp; its largest city.',
                    'AbstractURL': 'https://en.wikipedia.org/wiki/Tehran',
                    'RelatedTopics': [],
                })
            raise AssertionError(f'Wikipedia should not be reached: {url}')

        with patch('httpx.AsyncClient', _fake_async_client(_respond)):
            result = await chat_web._web_search('Tehran')

        assert '&quot;' not in result
        assert '&amp;' not in result
        assert '"capital"' in result
        assert 'Iran & its largest city' in result

    @pytest.mark.asyncio
    async def test_ddg_instant_answer_json_is_parsed(self):
        """DDG-IA's AbstractText/AbstractURL plus RelatedTopics (each with
        Text + FirstURL) must be parsed into the bullet list, and a
        successful DDG-IA result must short-circuit the Wikipedia fallback
        entirely."""
        def _respond(url, params):
            if 'duckduckgo.com' in url:
                assert params['q'] == 'Iran'
                return _fake_response(200, {
                    'Heading': 'Iran',
                    'AbstractText': 'Iran is a country in Western Asia.',
                    'AbstractURL': 'https://en.wikipedia.org/wiki/Iran',
                    'RelatedTopics': [
                        {'Text': 'Tehran - capital of Iran', 'FirstURL': 'https://duckduckgo.com/Tehran'},
                        {'Name': 'Geography', 'Topics': []},  # nested category group -- must be skipped, no Text/FirstURL
                    ],
                })
            raise AssertionError(f'Wikipedia should not be reached after DDG-IA succeeds: {url}')

        with patch('httpx.AsyncClient', _fake_async_client(_respond)):
            result = await chat_web._web_search('Iran')

        assert 'Iran is a country in Western Asia.' in result
        assert 'https://en.wikipedia.org/wiki/Iran' in result
        assert 'Tehran - capital of Iran' in result
        assert 'https://duckduckgo.com/Tehran' in result

    @pytest.mark.asyncio
    async def test_all_sources_fail_returns_empty_string_never_raises(self):
        def _respond(url, params):
            return _fake_response(500, {})

        with patch('httpx.AsyncClient', _fake_async_client(_respond)):
            result = await chat_web._web_search('چیزی که پیدا نمی‌شود')

        assert result == ''


class TestHonestyFix:
    """The system message injected around search results must no longer
    forbid the model from admitting the search was useless -- see
    _apply_web_search's docstring/comment for the incident this fixes."""

    @pytest.mark.asyncio
    async def test_injected_message_drops_banned_phrase_and_allows_saying_nothing_relevant(self):
        payload = {
            'messages': [{'role': 'user', 'content': 'پایتخت ایران کجاست'}],
            'web_search': True,
        }
        with patch.object(chat_mod, '_web_search', AsyncMock(
            return_value='• تهران (ویکی‌پدیا)\n  تهران پایتخت ایران است.\n  https://fa.wikipedia.org/wiki/تهران'
        )):
            await chat_web._apply_web_search(payload, handler='test')

        injected = next(m['content'] for m in payload['messages'] if isinstance(m, dict) and m.get('role') == 'system')
        assert 'هرگز نگو' not in injected
        assert 'به اینترنت دسترسی ندارم' not in injected
        assert 'نتیجهٔ مرتبطی پیدا نکرد' in injected
