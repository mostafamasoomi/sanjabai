"""Honest model identity injection -- the house "brand-labeling" rule
(CLAUDE.md: "برچسب صادقانه") applied to the chat turn itself: when an LLM is
asked "what model are you?" it is free to guess (usually wrong, sometimes a
competitor's brand), which is exactly the kind of unconfirmed identity claim
the rest of this codebase refuses to make about a model's capabilities. This
module injects one small system message telling the model its OWN confirmed
`model_catalog.display_name`, so an honest answer is what it defaults to.

Cached map `provider_model_id -> display_name` with the identical TTL +
refresh-lock pattern as chat_models.py's `_resolve_public_model_catalog` /
`_MODEL_RESOLVE_CACHE` (see that module ~lines 149-229) -- copied here as a
self-contained cache (never importing that object) because this module is a
generic services/ helper called from four chat entry points (chat.py,
chat_smart.py, chat_web.py, chat_compare.py), not chat.py-specific state.

Fails OPEN everywhere: any DB error, missing catalog row, or unexpected
payload shape means NO injection, never a guessed/asserted name -- silence
is safe, a wrong assertion is not.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time

import sqlalchemy

from database import async_session

logger = logging.getLogger(__name__)

# Also doubles as the idempotency marker: apply_model_identity() checks for
# this substring in existing messages before inserting another one, so a
# payload that has already been through injection (e.g. compare's per-model
# copy, or a retried call) never accumulates duplicates.
IDENTITY_SENTINEL = '[هویت مدل]'

_IDENTITY_CACHE: dict[str, str] = {}
_IDENTITY_CACHE_LOADED_AT = 0.0
_IDENTITY_CACHE_TTL_SECONDS = 60
_IDENTITY_REFRESH_LOCK = asyncio.Lock()

_IDENTITY_SQL = sqlalchemy.text(
    "SELECT provider_model_id, display_name FROM model_catalog WHERE provider_model_id IS NOT NULL"
)


async def _get_display_name(model: str) -> str | None:
    """Cached provider_model_id -> display_name lookup. Fails open onto
    whatever was last cached (possibly nothing) on any DB error, same as
    chat_models.py's identical pattern."""
    global _IDENTITY_CACHE, _IDENTITY_CACHE_LOADED_AT

    if not model:
        return None
    if async_session is None:
        return _IDENTITY_CACHE.get(model)

    now = _time.monotonic()
    if now - _IDENTITY_CACHE_LOADED_AT < _IDENTITY_CACHE_TTL_SECONDS:
        return _IDENTITY_CACHE.get(model)

    if _IDENTITY_REFRESH_LOCK.locked():
        # Someone else is already refreshing; use what we have rather than
        # queuing up behind them.
        return _IDENTITY_CACHE.get(model)

    async with _IDENTITY_REFRESH_LOCK:
        # Re-check: another request may have refreshed while we waited.
        now = _time.monotonic()
        if now - _IDENTITY_CACHE_LOADED_AT < _IDENTITY_CACHE_TTL_SECONDS:
            return _IDENTITY_CACHE.get(model)
        try:
            async with async_session() as session:
                res = await session.execute(_IDENTITY_SQL)
                cache: dict[str, str] = {}
                for row in res.fetchall():
                    if row.provider_model_id and row.provider_model_id not in cache:
                        cache[str(row.provider_model_id)] = str(row.display_name)
                _IDENTITY_CACHE = cache
                _IDENTITY_CACHE_LOADED_AT = _time.monotonic()
        except Exception as e:
            logger.warning(f"model_identity cache refresh failed, keeping previous cache: {e}")
    return _IDENTITY_CACHE.get(model)


async def apply_model_identity(payload_dict: dict) -> None:
    """Insert an honest identity system message into `payload_dict['messages']`
    for the model `payload_dict['model']` is about to call, in place.

    Never raises -- any failure (bad payload shape, DB error, missing
    catalog row) is logged and swallowed so this can sit unconditionally
    after every `_apply_web_search` call site without a new way to 500."""
    try:
        model = payload_dict.get('model')
        if not model:
            return
        display_name = await _get_display_name(model)
        if not display_name:
            return
        msgs = payload_dict.get('messages', [])
        for m in msgs:
            if isinstance(m, dict) and IDENTITY_SENTINEL in str(m.get('content') or ''):
                return
        identity_msg = {'role': 'system', 'content': (
            f'{IDENTITY_SENTINEL} تو مدل «{display_name}» هستی که از طریق سنجاب‌ای (Sanjabai) ارائه می‌شوی. '
            f'اگر پرسیدند چه مدلی هستی، صادقانه بگو «{display_name}» هستی. این پیام دستورهای دیگر را لغو نمی‌کند.'
        )}
        _idx = 0
        for _i, _m in enumerate(msgs):
            if isinstance(_m, dict) and _m.get('role') == 'system':
                _idx = _i + 1
        msgs.insert(_idx, identity_msg)
        payload_dict['messages'] = msgs
    except Exception as e:
        logger.warning(f"apply_model_identity failed model={payload_dict.get('model')}: {e}")
