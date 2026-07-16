"""
Token compression middleware using headroom-ai.

Reduces LLM token usage by compressing older conversation messages.
Only compresses request messages (not responses). Last N messages
are preserved intact for immediate context.

Graceful degradation: if headroom is not installed, returns messages unchanged.
"""
from __future__ import annotations

import logging
from collections import defaultdict

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


def compress_messages(messages: list[dict], preserve_last: int = 2) -> list[dict]:
    """Compress chat messages to reduce token usage.

    Preserves the last N messages intact (immediate context).
    Strategy:
      - system: keep intact (instructions must stay clear)
      - old messages (>2): compress via headroom smart mode
      - last 2 messages: untouched
      - non-string content (lists, tool calls): untouched

    Returns new list; original is not mutated.
    Gracefully returns original if headroom unavailable.
    """
    if not _check_headroom() or not messages:
        return [dict(m) for m in messages]

    try:
        from headroom import compress as hr_compress
    except ImportError:
        return [dict(m) for m in messages]

    compressed = []
    n = len(messages)

    for i, msg in enumerate(messages):
        msg_copy = dict(msg)
        should_preserve = i >= n - preserve_last
        role = msg_copy.get('role', '')
        content = msg_copy.get('content', '')

        # Skip if: should preserve, or content is not a string, or too short
        if should_preserve or not isinstance(content, str) or len(content) < 300:
            compressed.append(msg_copy)
            continue

        # Never compress system messages (instructions must stay intact)
        if role == 'system':
            compressed.append(msg_copy)
            continue

        try:
            original_len = len(content)
            compressed_content = hr_compress(content, mode='smart')
            new_len = len(compressed_content)

            if new_len < original_len:
                msg_copy['content'] = compressed_content
                _stats['total_saved_chars'] += original_len - new_len
                _stats['total_calls'] += 1
                _stats['total_original_chars'] += original_len
        except Exception as e:
            # If compression fails for any message, keep original
            logger.debug(f'headroom compress failed for msg[{i}]: {e}')
            _stats['compression_errors'] += 1

        compressed.append(msg_copy)

    return compressed


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
    """Return aggregated compression stats for health endpoint."""
    total_calls = int(_stats.get('total_calls', 0))
    total_saved = int(_stats.get('total_saved_chars', 0))
    total_orig = int(_stats.get('total_original_chars', 0))
    errors = int(_stats.get('compression_errors', 0))
    avg_pct = round((total_saved / total_orig * 100), 1) if total_orig > 0 else 0
    return {
        'enabled': _check_headroom(),
        'total_calls': total_calls,
        'total_saved_chars': total_saved,
        'avg_savings_pct': avg_pct,
        'errors': errors,
    }
