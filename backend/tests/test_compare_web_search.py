"""Regression test for /v1/compare web search (Task 2): before this fix
`/v1/compare` was the one chat mode with no way to ground its answer in a
live search -- `CompareRequest` had no `web_search` field at all.

Search must run EXACTLY ONCE on the shared prompt (not once per model,
which would fetch/pay for the same query twice), and both models must see
the identical grounded `messages` -- see chat_compare.py's
`compare_models` for the wiring (`_apply_web_search` runs once before the
`asyncio.gather` fan-out to `_call_model_once`).

Follows this suite's existing /v1/compare test conventions -- same fakes as
tests/test_compare_stream_guard.py / tests/_public_model_ids_chat_fakes.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database as _db
import chat as chat_mod
from tests._public_model_ids_chat_fakes import (
    AUTH_HEADERS,
    _billing_mock,
    _FakeProvider,
    _patch_resolve_db,
    _upstream_response,
)

SEARCH_SENTINEL = '• نتیجهٔ جستجوی زنده\n  خلاصه\n  http://example.com'


@pytest.fixture
def _bypass_pipeline():
    """Same bypass as test_compare_stream_guard.py's fixture of the same
    name: auth, billing reservation, and provider routing -- NOT
    check_and_consume, which is patched per-test below."""
    with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)), \
         patch.object(chat_mod, 'BillingService', _billing_mock()), \
         patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())):
        yield


def _post_compare(client, *, web_search):
    return client.post(
        '/v1/compare',
        json={
            'model_a': 'sanjab/mistral-large',
            'model_b': 'kr/claude-sonnet-4',
            'messages': [{'role': 'user', 'content': 'قیمت دلار امروز چند است؟'}],
            'stream': False,
            'web_search': web_search,
        },
        headers=AUTH_HEADERS,
    )


class TestCompareWebSearch:
    def test_web_search_runs_once_and_grounds_both_models(self, client, _bypass_pipeline):
        captured_calls = []

        fake_http = MagicMock()

        async def _post(url, json=None, headers=None, timeout=None):
            captured_calls.append(json)
            return _upstream_response({'choices': [{'message': {'content': 'پاسخ'}}],
                                        'usage': {'prompt_tokens': 5, 'completion_tokens': 5}})
        fake_http.post = _post

        with _patch_resolve_db(), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_web_search', AsyncMock(return_value=SEARCH_SENTINEL)) as mock_search, \
             patch.object(_db, '_real_http', fake_http):
            resp = _post_compare(client, web_search=True)

        assert resp.status_code == 200, resp.text

        # Searched exactly once for the shared prompt, not once per model.
        mock_search.assert_awaited_once()

        # Both upstream calls (model_a and model_b) received messages that
        # include the search-result system message.
        assert len(captured_calls) == 2, "both models must have been called upstream"
        for call_json in captured_calls:
            msgs = call_json['messages']
            assert any(
                isinstance(m, dict) and SEARCH_SENTINEL in str(m.get('content', ''))
                for m in msgs
            ), f"search result missing from a model's forwarded messages: {msgs}"

        # The raw `web_search` flag itself must never leak upstream.
        for call_json in captured_calls:
            assert 'web_search' not in call_json

    def test_web_search_false_never_calls_search(self, client, _bypass_pipeline):
        fake_http = MagicMock()
        fake_http.post = AsyncMock(return_value=_upstream_response(
            {'choices': [{'message': {'content': 'پاسخ'}}],
             'usage': {'prompt_tokens': 5, 'completion_tokens': 5}}
        ))

        with _patch_resolve_db(), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_web_search', AsyncMock()) as mock_search, \
             patch.object(_db, '_real_http', fake_http):
            resp = _post_compare(client, web_search=False)

        assert resp.status_code == 200, resp.text
        mock_search.assert_not_awaited()
