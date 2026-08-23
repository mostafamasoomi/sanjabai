"""Regression tests for /v1/chat/with-file web search support.

chat_with_file previously had no `web_search` parameter at all and never
called _apply_web_search, unlike /v1/chat/completions and /v1/smart-chat.
These tests pin the fix using the same bypass style as test_web_search.py
(auth/billing/provider-routing patched out; only the web_search wiring
itself is under test). No test makes a real network call -- upstream HTTP
is always mocked.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import database as _db


def _upstream_response(body=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value=body or {'choices': [{'message': {'content': 'پاسخ نمونه'}}]})
    resp.content = b'{}'
    return resp


class TestWithFileWebSearch:
    @pytest.fixture(autouse=True)
    def _bypass_pipeline(self):
        billing_instance = MagicMock()
        billing_instance.reserve = AsyncMock(return_value={'reservation_id': 'test-reservation'})
        billing_instance.release = AsyncMock(return_value=None)
        billing_instance.settle = AsyncMock(return_value=None)

        class _FakeProvider:
            v1 = 'http://fake-upstream/v1'

            def headers(self):
                return {'Content-Type': 'application/json'}

        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing_instance)), \
             patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'get_injection_messages', AsyncMock(return_value=[])):
            yield

    def test_with_file_triggers_web_search_when_flag_set(self, client):
        capture = {}

        async def fake_post(url, json=None, headers=None, timeout=None):
            capture['json'] = json
            return _upstream_response()

        fake_http = MagicMock()
        fake_http.post = fake_post

        with patch.object(chat_mod, '_web_search', AsyncMock(return_value='• نتیجه\n  خلاصه\n  http://example.com')) as mock_search, \
             patch.object(_db, '_real_http', fake_http), \
             patch.object(chat_mod, '_track_usage', AsyncMock(return_value=None)):
            resp = client.post(
                '/v1/chat/with-file',
                data={
                    'model': 'tencent-hy3',
                    'messages': json.dumps([{'role': 'user', 'content': 'قیمت طلا امروز چند است؟'}]),
                    'stream': 'false',
                    'web_search': 'true',
                },
                files={'file': ('note.txt', b'hello world', 'text/plain')},
            )

        assert resp.status_code == 200, resp.text
        mock_search.assert_awaited_once()
        # Web search runs BEFORE the file's extracted text is appended, so
        # the query is the user's actual question -- not the file content
        # (which would otherwise become the "last user message").
        assert mock_search.await_args.args[0] == 'قیمت طلا امروز چند است؟'
        # The injected search-results system message must actually be in the
        # payload sent upstream, not just observed by the mock.
        sent_messages = capture['json']['messages']
        assert any('نتایج جستجوی وب' in m.get('content', '') for m in sent_messages if isinstance(m, dict))

    def test_with_file_never_forwards_raw_web_search_flag_upstream(self, client):
        capture = {}

        async def fake_post(url, json=None, headers=None, timeout=None):
            capture['json'] = json
            return _upstream_response()

        fake_http = MagicMock()
        fake_http.post = fake_post

        with patch.object(chat_mod, '_web_search', AsyncMock(return_value='• x\n  y\n  http://z')), \
             patch.object(_db, '_real_http', fake_http), \
             patch.object(chat_mod, '_track_usage', AsyncMock(return_value=None)):
            resp = client.post(
                '/v1/chat/with-file',
                data={
                    'model': 'tencent-hy3',
                    'messages': json.dumps([{'role': 'user', 'content': 'سلام'}]),
                    'stream': 'false',
                    'web_search': 'true',
                },
                files={'file': ('note.txt', b'hello world', 'text/plain')},
            )

        assert resp.status_code == 200, resp.text
        assert 'web_search' not in capture['json']

    def test_with_file_skips_search_when_flag_absent_default(self, client):
        """Backward compatibility: existing callers that never send
        `web_search` at all (the field defaults to False) must see identical
        behavior to before this change -- no search performed."""
        capture = {}

        async def fake_post(url, json=None, headers=None, timeout=None):
            capture['json'] = json
            return _upstream_response()

        fake_http = MagicMock()
        fake_http.post = fake_post

        with patch.object(chat_mod, '_web_search', AsyncMock(return_value='should not be called')) as mock_search, \
             patch.object(_db, '_real_http', fake_http), \
             patch.object(chat_mod, '_track_usage', AsyncMock(return_value=None)):
            resp = client.post(
                '/v1/chat/with-file',
                data={
                    'model': 'tencent-hy3',
                    'messages': json.dumps([{'role': 'user', 'content': 'سلام'}]),
                    'stream': 'false',
                },
                files={'file': ('note.txt', b'hello world', 'text/plain')},
            )

        assert resp.status_code == 200, resp.text
        mock_search.assert_not_awaited()
        assert 'web_search' not in capture['json']
