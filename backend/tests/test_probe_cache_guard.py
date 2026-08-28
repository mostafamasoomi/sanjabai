"""A probe answered from cache is not a live probe.

providers.probe_model used to send a fixed 'ping' as its only content, and
omniroute caches on request content. Measured against the live router on
2026-08-28 (antigravity/gemini-3.5-flash-low):

    content='ping'         -> x-omniroute-cache: HIT   (twice running)
    content='ping <nonce>' -> x-omniroute-cache: MISS

A cached 200 made record_probe_sample write ok=True, which fills
model_health_state.last_ok_at, which is the ONLY condition
services/probe_gate.py:97 checks before a model may be put on sale. So a
model whose supplying account had gone 401/402/403 could still pass the gate
whose entire job is to stop that -- and the 402s are not hypothetical: 13 of
them appear in audit_logs' admin.model.test history for today alone.

Two independent guards are pinned here, because either alone rots:
  * the nonce, which is what makes a probe reach an account at all;
  * the explicit cache-hit rejection, which turns "a router stopped keying
    its cache on content" into a visible probe failure instead of a silent
    return to the original bug.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import database as _db
from providers import Provider, TRANSIENT_PROBE_REASONS, probe_model

_PROVIDERS_PY = Path(__file__).resolve().parent.parent / 'providers.py'


@contextmanager
def _http_returning(response):
    """Install a fake HTTP client through database.set_http.

    providers._http is a proxy that raises on attribute access until a client
    is installed, so patching an attribute ON it does not work -- the client
    has to be swapped the same way app.py's lifespan swaps it. Yields the post
    mock so a test can inspect what was actually sent.
    """
    post = AsyncMock(return_value=response)
    previous = _db._real_http
    _db.set_http(SimpleNamespace(post=post))
    try:
        yield post
    finally:
        _db.set_http(previous)


class _Resp:
    """Minimal stand-in for an httpx response: only what probe_model reads."""

    def __init__(self, status_code=200, headers=None, body=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body if body is not None else {'choices': [{'message': {}}]}

    def json(self):
        return self._body


def _provider() -> Provider:
    return Provider(name='omniroute', base_url='http://router.invalid', api_key='')


@pytest.mark.asyncio
class TestACachedAnswerIsNotAProbe:
    async def test_a_cache_hit_is_refused_even_though_it_is_a_well_formed_200(self):
        """The whole point: this response looks perfect. 200, real choices.
        It still proves nothing about any supplying account."""
        resp = _Resp(headers={'x-omniroute-cache-hit': 'true'})
        with _http_returning(resp):
            result = await probe_model(_provider(), 'some/model')
        assert result.ok is False
        assert result.error == 'cached_response'

    async def test_the_header_is_matched_case_and_whitespace_insensitively(self):
        """A router that answers 'TRUE ' must not slip past on formatting."""
        resp = _Resp(headers={'x-omniroute-cache-hit': ' TRUE '})
        with _http_returning(resp):
            result = await probe_model(_provider(), 'some/model')
        assert result.ok is False, 'a differently-cased cache hit was accepted'

    async def test_a_cache_miss_still_passes(self):
        """The guard must not condemn the ordinary case it was added beside."""
        resp = _Resp(headers={'x-omniroute-cache-hit': 'false'})
        with _http_returning(resp):
            result = await probe_model(_provider(), 'some/model')
        assert result.ok is True
        assert result.error is None

    async def test_upstreams_that_send_no_cache_header_are_unaffected(self):
        """ninerouter and litellm send no such header; they must be untouched."""
        with _http_returning(_Resp()):
            result = await probe_model(_provider(), 'some/model')
        assert result.ok is True


@pytest.mark.asyncio
class TestEveryProbeCarriesAFreshNonce:
    @staticmethod
    def _sent_content(post_mock) -> str:
        return post_mock.await_args.kwargs['json']['messages'][0]['content']

    async def test_two_probes_do_not_send_the_same_content(self):
        """If they did, the router could answer the second from cache -- which
        is the original bug, not a variation of it."""
        with _http_returning(_Resp()) as post:
            await probe_model(_provider(), 'some/model')
            first = self._sent_content(post)
            await probe_model(_provider(), 'some/model')
            second = self._sent_content(post)
        assert first != second, f'probe content is fixed: {first!r}'

    async def test_the_content_is_not_the_bare_string_that_caused_this(self):
        with _http_returning(_Resp()) as post:
            await probe_model(_provider(), 'some/model')
            content = self._sent_content(post)
        assert content != 'ping'
        assert len(content) > len('ping'), 'the nonce carries no entropy'


class TestTheRetryCanActuallyResolveIt:
    def test_cached_response_is_treated_as_transient(self):
        """The retry regenerates the nonce, so a second attempt genuinely can
        reach an account. Classifying it permanent would park live models."""
        assert 'cached_response' in TRANSIENT_PROBE_REASONS

    def test_probe_model_imports_secrets(self):
        """Guards the nonce against a NameError that would take every model
        health check down at once -- secrets was NOT imported before this
        change, so the import is load-bearing, not incidental."""
        tree = ast.parse(_PROVIDERS_PY.read_text(encoding='utf-8'))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert 'secrets' in imported
