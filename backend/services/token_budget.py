"""Phase E — outbound token budget: the only ceiling on what we send upstream.

Until session 10 the 9router upstream ran its own `caveman` compression,
which capped long threads as a side effect. That compression was turned off
(it degraded Persian quality and the decision was not ours), leaving NO
ceiling at all on outbound payload size. This module is that ceiling.

Three concerns, one place each, called from the chat modules -- never
copy-pasted into them:

  E1  apply_history_window()   caps the number of conversation messages
  E2  resolve_max_tokens()     caps output tokens when the client sent none
  E3  should_inject_context()  gates a LARGE memory/soul/pinned/skills block

NOT IN SCOPE, and must not be added here: counting tokens locally for
billing while sending a different (compressed) payload upstream. That
divergence is exactly what `caveman` was, it has no owner approval, and
billing must keep counting what we actually send. Everything this module
drops is dropped from the real outbound payload, so billing follows for free.

Hot-path contract: every public function is total. A failure in windowing,
capping or gating degrades to "send what we had" and is logged -- it must
never turn a user's chat into a 500.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time as _time
from typing import Any

import sqlalchemy

from database import async_session

logger = logging.getLogger(__name__)

# E1 -- ceiling on conversation (non-system) messages sent upstream.
# 20 == 10 user/assistant exchanges. compress_messages(preserve_last=2)
# already trims the *characters* of older messages but has no count cap, so
# a 300-message thread still went upstream in full. Ten exchanges covers a
# normal support/coding thread while bounding the conversational half of the
# payload; system/injected messages are exempt and budgeted separately (see
# services/context_injection.py's MAX_* constants).
MAX_HISTORY_MESSAGES = int(os.getenv('MAX_HISTORY_MESSAGES', '20') or '20')

# Deterministic, model-free "summary" of what was dropped. A rolling summary
# produced by a model call would double the per-request upstream cost, which
# breaks the rule that no request may be loss-making.
HISTORY_TRIM_NOTE = (
    '[یادداشت سیستم: پیام‌های قدیمی‌تر این گفتگو برای رعایت محدودیت طول حذف شده‌اند. '
    'فقط بخش پایانی گفتگو در دسترس است.]'
)


def _is_system(msg: Any) -> bool:
    return isinstance(msg, dict) and msg.get('role') == 'system'


def apply_history_window(
    messages: list[dict[str, Any]] | Any,
    max_messages: int | None = None,
) -> list[dict[str, Any]] | Any:
    """Cap the conversation to the newest MAX_HISTORY_MESSAGES non-system
    messages, keeping every system/injected message where it is.

    Returns a new list; the caller's list is not mutated. Idempotent: a
    payload already inside the window comes back unchanged, so applying it
    twice on a path that goes through two modules is harmless.
    """
    try:
        if not isinstance(messages, list):
            return [] if messages is None else messages
        if not messages:
            return messages
        limit = MAX_HISTORY_MESSAGES if max_messages is None else int(max_messages)
        if limit <= 0:
            return list(messages)

        body = [i for i, m in enumerate(messages) if not _is_system(m)]
        if len(body) <= limit:
            return list(messages)

        dropped = set(body[: len(body) - limit])
        kept = [m for i, m in enumerate(messages) if i not in dropped]
        if not any(
            isinstance(m, dict) and m.get('content') == HISTORY_TRIM_NOTE for m in kept
        ):
            first_body = next(
                (i for i, m in enumerate(kept) if not _is_system(m)), len(kept)
            )
            kept.insert(first_body, {'role': 'system', 'content': HISTORY_TRIM_NOTE})
        return kept
    except Exception as e:
        logger.warning(f'apply_history_window failed, sending unwindowed: {e}')
        return messages


# E2 -- ceiling on output tokens when the client sends no max_tokens.
# 4096 tokens is a multi-screen Persian answer; the catalog's own
# max_output_tokens values (64k-131k live) are the model's *capability*, not
# a sane chat default, so they cannot serve as the ceiling on their own.
DEFAULT_MAX_OUTPUT_TOKENS = int(os.getenv('DEFAULT_MAX_OUTPUT_TOKENS', '4096') or '4096')

# model_catalog.max_output_tokens changes only when an admin edits the
# catalog, so a long TTL is fine; the point of caching at all is to keep a
# full-table read off every chat request.
_MAX_OUT_CACHE_TTL_SECONDS = 300
_MAX_OUT_CACHE: dict[str, int] = {}
_MAX_OUT_CACHE_LOADED_AT: float = 0.0
_MAX_OUT_REFRESH_LOCK = asyncio.Lock()


async def _get_model_max_output_tokens(model: str) -> int | None:
    """model_catalog.max_output_tokens for ``model``, or None when the column
    is NULL / the model is unknown / the DB is unreachable.

    Keyed by both `id` and `provider_model_id` because the hot path has
    already canonicalized to provider_model_id by the time it gets here.
    On a read failure the previous cache is kept, never cleared -- stale
    ceilings beat no ceiling.
    """
    global _MAX_OUT_CACHE, _MAX_OUT_CACHE_LOADED_AT
    if not model:
        return None
    now = _time.monotonic()
    if now - _MAX_OUT_CACHE_LOADED_AT >= _MAX_OUT_CACHE_TTL_SECONDS and not _MAX_OUT_REFRESH_LOCK.locked():
        async with _MAX_OUT_REFRESH_LOCK:
            try:
                async with async_session() as session:
                    res = await session.execute(sqlalchemy.text(
                        'SELECT id, provider_model_id, max_output_tokens FROM model_catalog '
                        'WHERE max_output_tokens IS NOT NULL'
                    ))
                    cache: dict[str, int] = {}
                    for row in res.fetchall():
                        limit = int(row.max_output_tokens)
                        cache[str(row.id)] = limit
                        cache[str(row.provider_model_id)] = limit
                    _MAX_OUT_CACHE = cache
                    _MAX_OUT_CACHE_LOADED_AT = _time.monotonic()
            except Exception as e:
                logger.warning(f'_get_model_max_output_tokens read failed, keeping previous cache: {e}')
    return _MAX_OUT_CACHE.get(model)


async def resolve_max_tokens(model: str, requested: Any) -> int:
    """The max_tokens value to actually send upstream.

    A client-supplied value is never raised, only clamped down by the
    model's catalog ceiling. An absent (or non-positive / non-integer)
    value gets DEFAULT_MAX_OUTPUT_TOKENS, itself clamped by that ceiling.
    """
    try:
        want = int(requested) if isinstance(requested, (int, float)) and not isinstance(requested, bool) else 0
    except Exception:
        want = 0
    if want <= 0:
        want = DEFAULT_MAX_OUTPUT_TOKENS
    try:
        catalog_limit = await _get_model_max_output_tokens(model)
    except Exception as e:
        logger.warning(f'resolve_max_tokens catalog lookup failed model={model}: {e}')
        catalog_limit = None
    if catalog_limit and catalog_limit > 0:
        want = min(want, catalog_limit)
    return want


# E3 -- how often the memory/soul/pinned/skills block is re-injected.
# That block costs up to 10,693 characters at full budget (measured:
# services/context_injection.py MAX_SOUL_CHARS 2000 + 5x MAX_MEMORY_ENTRY 500
# + MAX_PINNED_CONTEXT_CHARS 6000 + markers) and was paid on EVERY message.
# Re-injecting on turns 1, 5, 9, ... cuts that by ~73% over a 30-turn thread
# while never leaving the model more than 3 turns without re-grounding.
INJECT_CONTEXT_EVERY_N_TURNS = int(os.getenv('INJECT_CONTEXT_EVERY_N_TURNS', '4') or '4')

# Below this, the block is re-sent every turn regardless of the turn gate.
# Injections are ephemeral per request -- they are NOT part of the history
# the client sends back -- so a gated turn means the model sees NO memory at
# all, not "it already saw it". Measured on live production the whole block
# is 102 chars; skipping it there blinds the model on 3 turns in 4 to save
# ~0.03% of a payload. 1500 chars (~400 tokens) is the point where the block
# stops being noise next to the messages it rides along with, and the turn
# gate starts being worth its quality cost.
INJECT_ALWAYS_UNDER_CHARS = int(os.getenv('INJECT_ALWAYS_UNDER_CHARS', '1500') or '1500')


def should_inject_context(
    messages: list[dict[str, Any]] | Any,
    injection_chars: int | None = None,
) -> bool:
    """True on the first user turn and every INJECT_CONTEXT_EVERY_N_TURNS
    turns after it (1, 5, 9, ... at the default of 4) -- unless the block is
    small enough (``injection_chars`` < INJECT_ALWAYS_UNDER_CHARS) to be
    worth re-sending every turn, in which case always True.

    Turn number == count of user messages in the outbound payload; system
    and injected messages are not turns. ``injection_chars`` of None means
    "size unknown" and falls back to the turn gate alone. Anything
    unrecognizable degrades to True -- a gate that cannot count must not
    silently strip the user's memories.
    """
    try:
        if not isinstance(messages, list) or not messages:
            return True
        if INJECT_CONTEXT_EVERY_N_TURNS <= 1:
            return True
        if injection_chars is not None and injection_chars < INJECT_ALWAYS_UNDER_CHARS:
            return True
        turns = sum(
            1 for m in messages if isinstance(m, dict) and m.get('role') == 'user'
        )
        if turns <= 1:
            return True
        return (turns - 1) % INJECT_CONTEXT_EVERY_N_TURNS == 0
    except Exception as e:
        logger.warning(f'should_inject_context failed, injecting anyway: {e}')
        return True


async def apply_outbound_budget(payload: dict[str, Any] | Any) -> dict[str, Any] | Any:
    """Apply E1 + E2 to a fully-assembled outbound payload, in place.

    The single call every chat path makes just before the payload leaves us
    (chat.py, chat_stream.py x2, chat_web.py, chat_smart.py,
    chat_compare.py). Idempotent, so a path that goes through two of those
    modules is not double-penalized, and total: a failure here leaves the
    payload exactly as it was rather than failing the user's chat.
    """
    if not isinstance(payload, dict):
        return payload
    try:
        payload['messages'] = apply_history_window(payload.get('messages') or [])
    except Exception as e:
        logger.warning(f'apply_outbound_budget: windowing skipped: {e}')
    try:
        payload['max_tokens'] = await resolve_max_tokens(
            str(payload.get('model') or ''), payload.get('max_tokens')
        )
    except Exception as e:
        logger.warning(f'apply_outbound_budget: max_tokens ceiling skipped: {e}')
    return payload
