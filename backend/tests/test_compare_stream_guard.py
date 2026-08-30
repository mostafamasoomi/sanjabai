"""``/v1/compare`` silently dropped ``stream: true`` -- ``CompareRequest.stream``
(chat.py) was parsed but never read, and chat_compare.py's
``_call_model_once`` hardcodes ``'stream': False`` upstream. A client asking
to stream got a buffered JSON body with no signal that its request was
downgraded -- a silent contract violation. Dual-SSE fan-out for /compare is
out of scope for this fix; the correct first cut is to REJECT streaming
explicitly, with a 400, before any wallet motion (reservation) or upstream
call.

Follows this suite's existing /v1/compare test conventions (see
tests/test_public_model_ids_chat.py's
``TestChatCanonicalizesBeforeUpstreamCall`` class and its shared fakes in
tests/_public_model_ids_chat_fakes.py) rather than inventing a new fixture
style.
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


@pytest.fixture
def _bypass_pipeline():
    """Same bypass as test_public_model_ids_chat.py's fixture of the same
    name: auth, billing reservation, and provider routing -- NOT
    check_and_consume, which is patched per-test below."""
    with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=42)), \
         patch.object(chat_mod, 'BillingService', _billing_mock()), \
         patch.object(chat_mod, '_resolve_provider', AsyncMock(return_value=_FakeProvider())):
        yield


def _post_compare(client, *, stream):
    return client.post(
        '/v1/compare',
        json={
            'model_a': 'sanjab/mistral-large',
            'model_b': 'kr/claude-sonnet-4',
            'messages': [{'role': 'user', 'content': 'hi'}],
            'stream': stream,
        },
        headers=AUTH_HEADERS,
    )


class TestStreamRejected:
    def test_stream_true_returns_400_with_stream_unsupported(self, client, _bypass_pipeline):
        billing = chat_mod.BillingService(None)  # the mocked instance _bypass_pipeline installed
        fake_http = MagicMock()
        fake_http.post = AsyncMock(return_value=_upstream_response())

        with _patch_resolve_db(), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(_db, '_real_http', fake_http):
            resp = _post_compare(client, stream=True)

        assert resp.status_code == 400, resp.text
        body = resp.json()['error']
        assert body['code'] == 'stream_unsupported'
        assert body['message'] == 'مقایسه هم‌زمان دو مدل فعلاً به‌صورت جریانی پشتیبانی نمی‌شود.'
        assert body['message_en'] == 'Streaming is not supported for model comparison yet.'
        # Must return before any wallet motion or upstream call.
        billing.reserve.assert_not_awaited()
        fake_http.post.assert_not_awaited()

    def test_stream_default_false_reaches_the_normal_path(self, client, _bypass_pipeline):
        """A request that omits `stream` (default False, chat.py:135) must be
        completely unaffected by the new guard -- still a normal 200 through
        the existing non-streaming pipeline."""
        fake_http = MagicMock()
        fake_http.post = AsyncMock(return_value=_upstream_response(
            {'choices': [{'message': {'content': 'ok'}}],
             'usage': {'prompt_tokens': 5, 'completion_tokens': 5}}
        ))

        with _patch_resolve_db(), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(_db, '_real_http', fake_http):
            resp = _post_compare(client, stream=False)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['model_a']['model'] == 'sanjab/mistral-large'
        assert body['model_b']['model'] == 'kr/claude-sonnet-4'
        assert fake_http.post.await_count == 2, "both models must still be called upstream"
