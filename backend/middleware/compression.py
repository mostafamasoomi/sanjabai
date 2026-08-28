"""
Token compression middleware using headroom-ai.

Reduces LLM token usage by compressing older conversation messages.
Only compresses request messages (not responses). Last N messages
are preserved intact for immediate context.

Compression is opt-in per user (see `compression_enabled_for`) — default
is off, so existing users see no change in token counts unless they
explicitly enable it via their profile preferences.

Graceful degradation: if headroom is not installed, if headroom raises,
or if headroom hands back a message list of a different length than it
was given (which would make splicing unsafe), the original messages are
returned unchanged. Compression must never be able to fail a chat request.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from database import async_session
from models import User

logger = logging.getLogger(__name__)

# ── Stats tracking ────────────────────────────────────────────────────────────

_stats: dict[str, float | int] = defaultdict(int)
_has_headroom: bool | None = None


def _check_headroom() -> bool:
    global _has_headroom
    if _has_headroom is None:
        try:
            import headroom  # noqa: F401
            _has_headroom = True
        except ImportError:
            _has_headroom = False
            logger.info('headroom-ai not installed — compression disabled (graceful degradation)')
    return _has_headroom


def _should_skip(msg: dict[str, Any], index: int, n: int, preserve_last: int) -> bool:
    """True if `msg` must pass through byte-identical (see module docstring
    on compress_messages for why each rule exists)."""
    if 'tool_calls' in msg:
        return True
    if index >= n - preserve_last:
        return True
    content = msg.get('content', '')
    if not isinstance(content, str) or len(content) < 300:
        return True
    if msg.get('role', '') in ('system', 'tool', 'function'):
        return True
    return False


def compress_messages(messages: list[dict], preserve_last: int = 2) -> list[dict]:
    """Compress chat messages to reduce token usage.

    Preserves the last N messages intact (immediate context).
    Strategy:
      - system: keep intact (instructions must stay clear)
      - tool: keep intact (its string `content` is a JSON payload the model
        parses structurally, not prose -- "smart" compression hands it
        malformed JSON or silently altered data, not a shorter summary)
      - any message carrying a `tool_calls` key, whatever its role: keep
        intact, byte-identical -- a client that reads content/tool_calls as
        one turn must never see them desync
      - non-string content (e.g. multimodal content lists): untouched
      - content shorter than 300 chars: untouched
      - last `preserve_last` messages: untouched
      - everything else: compressed via headroom, as a single batch call

    headroom.compress() takes a *list* of messages, not a string -- so the
    messages that pass every skip rule above are collected (in their
    original relative order) into one prefix list, compressed in one
    headroom call, and the results spliced back into their original
    positions. If headroom hands back a different number of messages than
    it was given, splicing would silently misalign message N with message
    N+1's content -- in that case the whole call is treated as failed and
    the original messages are returned unchanged.

    Returns a new list, same length and same order as the input, always.
    Original list/dicts are not mutated. Gracefully returns
    `[dict(m) for m in messages]` if headroom is unavailable or anything
    goes wrong.
    """
    if not _check_headroom() or not messages:
        return [dict(m) for m in messages]

    try:
        from headroom import compress as hr_compress
    except ImportError:
        return [dict(m) for m in messages]

    n = len(messages)
    result: list[dict | None] = [None] * n
    eligible_indices: list[int] = []
    eligible_msgs: list[dict] = []

    for i, msg in enumerate(messages):
        msg_copy = dict(msg)
        if _should_skip(msg_copy, i, n, preserve_last):
            result[i] = msg_copy
        else:
            eligible_indices.append(i)
            eligible_msgs.append(msg_copy)

    if not eligible_msgs:
        return result  # type: ignore[return-value]

    try:
        hr_result = hr_compress(eligible_msgs)
        compressed_msgs = hr_result.messages

        if len(compressed_msgs) != len(eligible_msgs):
            logger.warning(
                'headroom returned %d messages for %d input messages -- '
                'cannot splice safely, returning original messages unchanged',
                len(compressed_msgs), len(eligible_msgs),
            )
            _stats['compression_errors'] += 1
            return [dict(m) for m in messages]

        for idx, compressed_msg in zip(eligible_indices, compressed_msgs):
            result[idx] = dict(compressed_msg)

        _stats['total_calls'] += 1
        _stats['successes'] += 1
        _stats['tokens_before'] += int(getattr(hr_result, 'tokens_before', 0) or 0)
        _stats['tokens_after'] += int(getattr(hr_result, 'tokens_after', 0) or 0)
    except Exception as e:
        # If compression fails, keep every original message -- a partially
        # spliced result is worse than no compression at all.
        logger.debug(f'headroom compress failed: {e}')
        _stats['compression_errors'] += 1
        return [dict(m) for m in messages]

    return result  # type: ignore[return-value]


async def compression_enabled_for(uid: int) -> bool:
    """Whether user `uid` has opted into message compression.

    Reads `users.preferences->>'compression_enabled'`. Default is False --
    this is a deliberate product decision (see PACKET P-COMP): compression
    must be an explicit per-user opt-in, so any error, missing user, or
    missing/falsy key resolves to False. Never raises.
    """
    try:
        async with async_session() as session:
            res = await session.execute(User.__table__.select().where(User.id == uid))
            user = res.fetchone()
            if not user:
                return False
            prefs = user.preferences or {}
            return bool(prefs.get('compression_enabled', False))
    except Exception as e:
        logger.debug(f'compression_enabled_for failed for uid={uid}: {e}')
        return False


def estimate_savings(original: list[dict], compressed: list[dict]) -> dict:
    """Calculate character-level savings (approximate, not exact tokens)."""
    orig_chars = sum(len(str(m.get('content', ''))) for m in original)
    comp_chars = sum(len(str(m.get('content', ''))) for m in compressed)
    saved = orig_chars - comp_chars
    pct = round((saved / orig_chars * 100), 1) if orig_chars > 0 else 0
    return {
        'original_chars': orig_chars,
        'compressed_chars': comp_chars,
        'saved_chars': saved,
        'savings_pct': pct,
    }


def get_compression_stats() -> dict:
    """Return aggregated compression stats for the health endpoint.

    `enabled` means only "the headroom library imports" -- it says nothing
    about whether compression has ever actually run. `working` is the
    honest signal: True only once at least one compression call has
    actually succeeded.
    """
    total_calls = int(_stats.get('total_calls', 0))
    successes = int(_stats.get('successes', 0))
    errors = int(_stats.get('compression_errors', 0))
    tokens_before = int(_stats.get('tokens_before', 0))
    tokens_after = int(_stats.get('tokens_after', 0))
    tokens_saved = tokens_before - tokens_after
    avg_pct = round((tokens_saved / tokens_before * 100), 1) if tokens_before > 0 else 0
    return {
        'enabled': _check_headroom(),
        'working': successes > 0,
        'total_calls': total_calls,
        'errors': errors,
        'tokens_before': tokens_before,
        'tokens_after': tokens_after,
        'tokens_saved': tokens_saved,
        'avg_savings_pct': avg_pct,
    }
