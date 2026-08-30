"""services/memory_extractor.py used to hardcode "model": "tencent-hy3" in its
POST to LiteLLM. That route 404/429s on the live proxy, so every extraction
call silently failed and `_stats["last_extraction"]` stayed null forever --
auto-memory extraction never ran, with nothing visible anywhere to say so.

Two guards:
  * the model sent in the request body must come from the
    MEMORY_EXTRACT_MODEL env var (default "deepseek-v4-flash", confirmed
    working against the live litellm proxy), not a hardcoded literal;
  * a failed call (non-200 or exception) must be visible through
    get_auto_status() via last_error/error_count, not just swallowed into a
    log line nobody reads.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import database as _db
import services.memory_extractor as memory_extractor
from services.memory_extractor import extract_memories, get_auto_status


class _Resp:
    """Minimal stand-in for an httpx response: only what extract_memories reads."""

    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}

    def json(self):
        return self._body


def _messages():
    # extract_memories only proceeds past MIN_MSG_COUNT (3), so 4+ messages.
    return [
        {"role": "user", "content": "سلام"},
        {"role": "assistant", "content": "سلام، چطور می‌تونم کمک کنم؟"},
        {"role": "user", "content": "اسم من امیر است و برنامه‌نویسم"},
        {"role": "assistant", "content": "خوشحالم که آشنا شدیم امیر"},
    ]


@pytest.fixture(autouse=True)
def _reset_stats():
    """_stats is a module-level dict shared across tests -- reset it so one
    test's failure doesn't bleed into the next test's assertions."""
    before = dict(memory_extractor._stats)
    memory_extractor._stats.update({
        "enabled": True,
        "last_extraction": None,
        "total_extracted": 0,
        "last_error": None,
        "error_count": 0,
    })
    yield
    memory_extractor._stats.clear()
    memory_extractor._stats.update(before)


@pytest.fixture
def http_returning():
    """Install a fake HTTP client through database.set_http, the same way
    app.py's lifespan (and test_probe_cache_guard.py) swap it. Yields the
    `post` mock so a test can inspect what was actually sent."""
    def _install(response):
        post = AsyncMock(return_value=response)
        previous = _db._real_http
        _db.set_http(SimpleNamespace(post=post))
        return post, previous

    installed = []

    def _factory(response):
        post, previous = _install(response)
        installed.append(previous)
        return post

    yield _factory
    for previous in installed:
        _db.set_http(previous)


class TestGetAutoStatusExposesFailures:
    def test_new_keys_present_and_default_to_healthy(self):
        status = get_auto_status()
        assert "last_error" in status
        assert "error_count" in status
        assert status["last_error"] is None
        assert status["error_count"] == 0


class TestModelComesFromEnv:
    @pytest.mark.asyncio
    async def test_default_model_is_deepseek_v4_flash(self, http_returning, monkeypatch):
        monkeypatch.delenv("MEMORY_EXTRACT_MODEL", raising=False)
        post = http_returning(_Resp(200, {"choices": [{"message": {"content": "[]"}}]}))

        await extract_memories(1, _messages())

        assert post.await_count == 1
        sent_model = post.await_args.kwargs["json"]["model"]
        assert sent_model == "deepseek-v4-flash"

    @pytest.mark.asyncio
    async def test_env_override_is_actually_used(self, http_returning, monkeypatch):
        monkeypatch.setenv("MEMORY_EXTRACT_MODEL", "some-other-model")
        post = http_returning(_Resp(200, {"choices": [{"message": {"content": "[]"}}]}))

        await extract_memories(1, _messages())

        sent_model = post.await_args.kwargs["json"]["model"]
        assert sent_model == "some-other-model"


class TestFailuresAreVisible:
    @pytest.mark.asyncio
    async def test_non_200_sets_last_error_and_bumps_counter(self, http_returning):
        http_returning(_Resp(404, {}))

        await extract_memories(1, _messages())

        status = get_auto_status()
        # Enriched format includes the model name; failure must still be visible.
        assert "litellm 404" in status["last_error"]
        assert status["error_count"] == 1

    @pytest.mark.asyncio
    async def test_exception_sets_last_error_and_bumps_counter(self, http_returning):
        post = AsyncMock(side_effect=RuntimeError("boom"))
        previous = _db._real_http
        _db.set_http(SimpleNamespace(post=post))
        try:
            await extract_memories(1, _messages())
        finally:
            _db.set_http(previous)

        status = get_auto_status()
        # Enriched format prefixes the exception type; cause must still be visible.
        assert "boom" in status["last_error"]
        assert status["error_count"] == 1

    @pytest.mark.asyncio
    async def test_success_leaves_last_error_untouched(self, http_returning):
        http_returning(_Resp(200, {"choices": [{"message": {"content": "[]"}}]}))

        await extract_memories(1, _messages())

        status = get_auto_status()
        assert status["last_error"] is None
        assert status["error_count"] == 0
