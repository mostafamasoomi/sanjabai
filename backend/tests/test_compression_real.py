"""Real guards for middleware/compression.py (PACKET P-COMP).

Context: headroom.compress() takes `messages: list[dict[str, Any]]`, not a
string -- the old code called `hr_compress(content, mode='smart')` with a
string, which always raised TypeError, always got swallowed by a bare
`except Exception`, and so compression has never actually run for anybody.
This file does NOT require the real `headroom` package -- every test fakes
it via `sys.modules['headroom']` plus `middleware.compression._has_headroom`,
so the suite is honest about compression's *wiring*, not about headroom's
own internals.

The skip rules (tool_calls, system/tool/function role, non-string content,
short content, preserve_last) are load-bearing for the tool-calling loop --
see module docstring in compression.py. Every test here proves the output
list has the same length and order as the input, always, even when nothing
is compressed.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import middleware.compression as compression
from tests.conftest import make_result, make_row


# ── Fake headroom plumbing ──────────────────────────────────────────────────

def _install_fake_headroom(monkeypatch, compress_fn):
    """Force compression.py down the "headroom is installed" path and make
    `from headroom import compress` resolve to `compress_fn`."""
    monkeypatch.setattr(compression, '_has_headroom', True)
    fake_module = SimpleNamespace(compress=compress_fn)
    monkeypatch.setitem(sys.modules, 'headroom', fake_module)


def _uppercase_compress(messages):
    """A fake headroom.compress that visibly transforms content (uppercases
    it) so splicing can be proven correct, not just length-preserving."""
    new_messages = [dict(m, content=m['content'].upper()) for m in messages]
    return SimpleNamespace(
        messages=new_messages,
        tokens_before=1000,
        tokens_after=500,
        tokens_saved=500,
        compression_ratio=0.5,
        transforms_applied=['fake-uppercase'],
    )


def _wrong_count_compress(messages):
    """A fake headroom.compress that drops a message -- the "cannot splice
    safely" case."""
    return SimpleNamespace(
        messages=messages[:-1] if len(messages) > 1 else [],
        tokens_before=1000,
        tokens_after=500,
        tokens_saved=500,
        compression_ratio=0.5,
        transforms_applied=[],
    )


@pytest.fixture(autouse=True)
def _reset_compression_state():
    """Isolate every test from every other test's module-level counters."""
    compression._stats.clear()
    compression._has_headroom = None
    yield
    compression._stats.clear()
    compression._has_headroom = None


def _long(text_marker: str, n: int = 320) -> str:
    """A content string >= 300 chars so it's eligible for compression
    unless some other skip rule stops it."""
    return (text_marker * ((n // len(text_marker)) + 1))[:n]


# ── compress_messages: skip-rule guards ─────────────────────────────────────

def test_tool_calls_message_survives_byte_identical(monkeypatch):
    _install_fake_headroom(monkeypatch, _uppercase_compress)
    msg = {'role': 'assistant', 'content': _long('call the tool please '), 'tool_calls': [{'id': 'x'}]}
    messages = [msg, {'role': 'user', 'content': 'hi'}, {'role': 'user', 'content': 'hi2'}]
    out = compression.compress_messages(messages, preserve_last=2)
    assert out[0] == msg
    assert out[0]['content'] == msg['content']  # not uppercased


@pytest.mark.parametrize('role', ['tool', 'system', 'function'])
def test_structural_roles_survive_byte_identical(monkeypatch, role):
    _install_fake_headroom(monkeypatch, _uppercase_compress)
    msg = {'role': role, 'content': _long('structural payload ')}
    messages = [msg, {'role': 'user', 'content': 'a'}, {'role': 'user', 'content': 'b'}]
    out = compression.compress_messages(messages, preserve_last=2)
    assert out[0] == msg
    assert out[0]['content'] == msg['content']


def test_multimodal_list_content_survives(monkeypatch):
    _install_fake_headroom(monkeypatch, _uppercase_compress)
    msg = {'role': 'user', 'content': [{'type': 'text', 'text': 'x' * 400}, {'type': 'image_url', 'image_url': {}}]}
    messages = [msg, {'role': 'user', 'content': 'a'}, {'role': 'user', 'content': 'b'}]
    out = compression.compress_messages(messages, preserve_last=2)
    assert out[0] == msg
    assert out[0]['content'] is msg['content'] or out[0]['content'] == msg['content']


def test_output_length_and_order_match_input_when_everything_compressible(monkeypatch):
    _install_fake_headroom(monkeypatch, _uppercase_compress)
    messages = [
        {'role': 'user', 'content': _long('old message one ')},
        {'role': 'assistant', 'content': _long('old message two ')},
        {'role': 'user', 'content': 'recent short'},
        {'role': 'assistant', 'content': 'also recent'},
    ]
    out = compression.compress_messages(messages, preserve_last=2)
    assert len(out) == len(messages)
    assert [m['role'] for m in out] == [m['role'] for m in messages]
    # the two eligible (old, long) messages were compressed
    assert out[0]['content'] == messages[0]['content'].upper()
    assert out[1]['content'] == messages[1]['content'].upper()
    # the two preserved (recent) messages were not touched
    assert out[2]['content'] == messages[2]['content']
    assert out[3]['content'] == messages[3]['content']


def test_output_length_and_order_match_input_when_everything_skipped(monkeypatch):
    _install_fake_headroom(monkeypatch, _uppercase_compress)
    messages = [
        {'role': 'system', 'content': _long('system prompt ')},
        {'role': 'tool', 'content': _long('{"json": "payload"} ')},
        {'role': 'user', 'content': 'short'},
    ]
    out = compression.compress_messages(messages, preserve_last=2)
    assert len(out) == len(messages)
    assert out == messages


def test_output_length_and_order_match_input_on_empty_list(monkeypatch):
    _install_fake_headroom(monkeypatch, _uppercase_compress)
    out = compression.compress_messages([], preserve_last=2)
    assert out == []


def test_headroom_not_installed_returns_unchanged(monkeypatch):
    monkeypatch.setattr(compression, '_has_headroom', False)
    messages = [
        {'role': 'user', 'content': _long('one ')},
        {'role': 'assistant', 'content': _long('two ')},
        {'role': 'user', 'content': 'recent'},
    ]
    out = compression.compress_messages(messages, preserve_last=1)
    assert out == messages
    assert out is not messages


def test_wrong_message_count_returns_original_and_counts_error(monkeypatch):
    _install_fake_headroom(monkeypatch, _wrong_count_compress)
    messages = [
        {'role': 'user', 'content': _long('one ')},
        {'role': 'assistant', 'content': _long('two ')},
        {'role': 'user', 'content': 'recent'},
    ]
    out = compression.compress_messages(messages, preserve_last=1)
    assert out == messages
    assert len(out) == len(messages)
    stats = compression.get_compression_stats()
    assert stats['errors'] == 1
    assert stats['working'] is False


def test_headroom_exception_returns_original_and_counts_error(monkeypatch):
    def _raising_compress(messages):
        raise RuntimeError('boom')
    _install_fake_headroom(monkeypatch, _raising_compress)
    messages = [
        {'role': 'user', 'content': _long('one ')},
        {'role': 'assistant', 'content': _long('two ')},
        {'role': 'user', 'content': 'recent'},
    ]
    out = compression.compress_messages(messages, preserve_last=1)
    assert out == messages
    stats = compression.get_compression_stats()
    assert stats['errors'] == 1


# ── get_compression_stats: 'working' must be honest ─────────────────────────

def test_working_is_false_before_any_successful_compression(monkeypatch):
    _install_fake_headroom(monkeypatch, _uppercase_compress)
    stats = compression.get_compression_stats()
    assert stats['enabled'] is True
    assert stats['working'] is False
    assert stats['total_calls'] == 0


def test_working_is_true_after_a_successful_compression(monkeypatch):
    _install_fake_headroom(monkeypatch, _uppercase_compress)
    assert compression.get_compression_stats()['working'] is False
    messages = [
        {'role': 'user', 'content': _long('one ')},
        {'role': 'assistant', 'content': _long('two ')},
        {'role': 'user', 'content': 'recent'},
    ]
    compression.compress_messages(messages, preserve_last=1)
    stats = compression.get_compression_stats()
    assert stats['working'] is True
    assert stats['total_calls'] == 1
    assert stats['tokens_before'] == 1000
    assert stats['tokens_after'] == 500


# ── compression_enabled_for ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compression_enabled_for_missing_user_is_false(mock_async_session):
    mock_async_session._execute_result = make_result(fetchone=None)
    assert await compression.compression_enabled_for(999) is False


@pytest.mark.asyncio
async def test_compression_enabled_for_db_error_is_false(mock_async_session):
    async def _raise(*args, **kwargs):
        raise RuntimeError('db down')
    mock_async_session.execute = _raise
    assert await compression.compression_enabled_for(1) is False


@pytest.mark.asyncio
async def test_compression_enabled_for_key_absent_is_false(mock_async_session):
    row = make_row(id=1, preferences={})
    mock_async_session._execute_result = make_result(fetchone=row)
    assert await compression.compression_enabled_for(1) is False


@pytest.mark.asyncio
async def test_compression_enabled_for_preferences_none_is_false(mock_async_session):
    row = make_row(id=1, preferences=None)
    mock_async_session._execute_result = make_result(fetchone=row)
    assert await compression.compression_enabled_for(1) is False


@pytest.mark.asyncio
async def test_compression_enabled_for_explicit_false_is_false(mock_async_session):
    row = make_row(id=1, preferences={'compression_enabled': False})
    mock_async_session._execute_result = make_result(fetchone=row)
    assert await compression.compression_enabled_for(1) is False


@pytest.mark.asyncio
async def test_compression_enabled_for_explicit_true_is_true(mock_async_session):
    row = make_row(id=1, preferences={'compression_enabled': True})
    mock_async_session._execute_result = make_result(fetchone=row)
    assert await compression.compression_enabled_for(1) is True
