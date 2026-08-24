"""Tests for the moderation gate added to backend/images.py.

Before this fix, `grep -c moderation images.py` was 0 at HEAD: POST
/v1/images/generations already billed correctly (reserve/settle/release)
but had ZERO content screening -- a user could prompt for anything and
nothing inspected it.

Mocking style mirrors tests/test_images.py (images.router mounted on a
throwaway app, every chat.py-family symbol images.py imports is patched at
the images.py call site). `Verdict` is the real dataclass from
services/moderation_rules.py, so these tests pin the actual contract
`moderation_preflight` returns, not a hand-rolled guess.

The companion RAG-side gates (moderation + free-tier + quota + billing on
services/rag.py::query_documents) live in tests/test_rag_gates_billing.py
-- split out purely to keep both files under the house 500-line cap.
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import images as images_mod
import services.moderation as moderation_mod
from services.moderation_rules import Verdict

_BLOCK_MESSAGE = (
    'این درخواست با قوانین محتوایی سنجاب همخوانی ندارد و ارسال نشد. '
    'لطفاً پیام را به‌گونه‌ای دیگر بازنویسی کنید.'
)


def _make_images_client() -> TestClient:
    app = FastAPI()
    app.include_router(images_mod.router)
    return TestClient(app)


def _image_row(availability='available', price=1000, markup_pct=0):
    return types.SimpleNamespace(
        provider_model_id='pollinations/flux',
        availability=availability,
        image_price_per_unit=price,
        markup_pct=markup_pct,
    )


def _images_billing_mock():
    instance = MagicMock()
    instance.reserve = AsyncMock(return_value={'reservation_id': 'resv-1', 'hold_amount': 0})
    instance.settle = AsyncMock(return_value=None)
    instance.release = AsyncMock(return_value=None)
    return MagicMock(return_value=instance), instance


def _images_fake_async_session():
    class _Ctx:
        async def __aenter__(self):
            session = MagicMock()
            session.commit = AsyncMock(return_value=None)
            return session

        async def __aexit__(self, *a):
            return None

    return MagicMock(return_value=_Ctx())


def _fake_provider():
    p = MagicMock()
    p.v1 = 'http://fake-upstream/v1'
    p.headers = MagicMock(return_value={'Content-Type': 'application/json'})
    return p


def _upstream_image_response(status_code=200, body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(
        return_value=body if body is not None else {'data': [{'url': 'https://example.com/a.png'}]}
    )
    resp.content = b'{}'
    return resp


def _preflight_mock(verdict: Verdict) -> AsyncMock:
    """A moderation_preflight stand-in that reproduces the real function's
    contract (services/moderation.py): None on allow/flag, a 403
    JSONResponse carrying verdict.message_fa (or BLOCK_MESSAGE_FA) on
    block -- without touching Redis/DB."""
    if verdict.decision != 'block':
        return AsyncMock(return_value=None)
    from fastapi.responses import JSONResponse
    return AsyncMock(return_value=JSONResponse(
        {'error': {'message': verdict.message_fa or _BLOCK_MESSAGE,
                   'type': 'content_policy', 'code': 'content_blocked'}},
        status_code=403,
    ))


class _ImagesPatches:
    """Same shape as tests/test_images.py's `_BasePatches`, plus
    `moderation_preflight` -- the one gate this session adds to images.py."""

    def __init__(self, *, row=None, verdict=None, http_post=None):
        self.row = row or _image_row()
        self.billing_cls, self.billing_instance = _images_billing_mock()
        self.release_spy = AsyncMock(return_value=None)
        self.fake_http = MagicMock()
        self.fake_http.post = http_post or AsyncMock(return_value=_upstream_image_response())
        self.verdict = verdict if verdict is not None else Verdict(decision='allow')
        self.moderation_preflight = _preflight_mock(self.verdict)

    def __enter__(self):
        self._patches = [
            patch.object(images_mod, '_get_user_id', AsyncMock(return_value=42)),
            patch.object(images_mod, '_resolve_public_model', AsyncMock(side_effect=lambda m: m)),
            patch.object(images_mod, '_resolve_provider', AsyncMock(return_value=_fake_provider())),
            patch.object(images_mod, '_release_reservation', self.release_spy),
            patch.object(images_mod, '_load_image_model', AsyncMock(return_value=self.row)),
            patch.object(images_mod, 'get_effective_markup_pct', AsyncMock(return_value=0)),
            patch.object(images_mod, 'async_session', _images_fake_async_session()),
            patch.object(images_mod, 'BillingService', self.billing_cls),
            patch.object(images_mod, '_http', self.fake_http),
            patch.object(images_mod, 'moderation_preflight', self.moderation_preflight),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self._patches:
            p.stop()


@pytest.fixture
def images_client():
    return _make_images_client()


class TestImagesModerationGate:
    def test_blocked_prompt_never_reaches_upstream_or_opens_a_reservation(self, images_client):
        verdict = Verdict(decision='block', category='sexual', severity='high',
                           rule_id=7, message_fa=_BLOCK_MESSAGE)
        with _ImagesPatches(verdict=verdict) as p:
            resp = images_client.post(
                '/v1/images/generations',
                json={'model': 'pollinations/flux', 'prompt': 'یک تصویر ممنوعه'},
            )
        assert resp.status_code == 403
        assert resp.json()['error']['code'] == 'content_blocked'
        assert resp.json()['error']['message'] == _BLOCK_MESSAGE
        p.fake_http.post.assert_not_called()
        p.billing_instance.reserve.assert_not_called()
        p.release_spy.assert_not_called()

    def test_moderation_runs_before_model_resolution(self, images_client):
        """Screening must run before Gate 0's canonicalization: prove it by
        asserting _resolve_public_model is never even called on a block."""
        verdict = Verdict(decision='block', category='violence', severity='high', message_fa=_BLOCK_MESSAGE)
        with _ImagesPatches(verdict=verdict):
            resolve_mock = AsyncMock(side_effect=lambda m: m)
            with patch.object(images_mod, '_resolve_public_model', resolve_mock):
                images_client.post(
                    '/v1/images/generations',
                    json={'model': 'pollinations/flux', 'prompt': 'x'},
                )
            resolve_mock.assert_not_called()

    def test_clean_prompt_passes_through_byte_for_byte_unchanged_and_bills(self, images_client):
        prompt = 'یک گربه‌ی نارنجی روی مبل آبی، سبک نقاشی واقع‌گرایانه'
        with _ImagesPatches() as p:
            resp = images_client.post(
                '/v1/images/generations',
                json={'model': 'pollinations/flux', 'prompt': prompt, 'n': 1},
            )
        assert resp.status_code == 200, resp.text
        p.fake_http.post.assert_awaited_once()
        _, kwargs = p.fake_http.post.await_args
        assert kwargs['json']['prompt'] == prompt
        p.billing_instance.reserve.assert_awaited_once()
        p.billing_instance.settle.assert_awaited_once()

    def test_moderation_preflight_called_with_prompt_as_a_user_message(self, images_client):
        prompt = 'متن آزمایشی درخواست تصویر'
        with _ImagesPatches() as p:
            images_client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': prompt})
        p.moderation_preflight.assert_awaited_once()
        call_args = p.moderation_preflight.await_args
        assert call_args.args[0] == 42
        assert call_args.args[1] == [{'role': 'user', 'content': prompt}]

    def test_detector_failure_fails_open_and_still_reaches_upstream(self, images_client):
        """The REAL moderation_preflight/screen_request, exercised end to
        end (not the AsyncMock stand-in): an internal detector failure
        (_load_config raising) must ALLOW the request, never raise, and
        never block -- services/moderation.py's documented fail-safe."""
        with _ImagesPatches() as p:
            with patch.object(images_mod, 'moderation_preflight', moderation_mod.moderation_preflight), \
                 patch.object(moderation_mod, '_load_config', AsyncMock(side_effect=RuntimeError('detector down'))):
                resp = images_client.post(
                    '/v1/images/generations',
                    json={'model': 'pollinations/flux', 'prompt': 'a cat'},
                )
        assert resp.status_code == 200, resp.text
        p.fake_http.post.assert_awaited_once()


class TestImagesAuthUnaffected:
    def test_unauthenticated_still_rejected_before_moderation(self, images_client):
        """Pre-existing gate (auth) must still run, and must still run
        BEFORE moderation -- an anonymous caller must not trigger a
        moderation event."""
        with _ImagesPatches() as p:
            with patch.object(images_mod, '_get_user_id', AsyncMock(return_value=None)):
                resp = images_client.post(
                    '/v1/images/generations',
                    json={'model': 'pollinations/flux', 'prompt': 'a cat'},
                )
            assert resp.status_code == 401
            p.moderation_preflight.assert_not_called()
