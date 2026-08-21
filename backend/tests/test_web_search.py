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
        async def _post(url, json=None, headers=None):
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
