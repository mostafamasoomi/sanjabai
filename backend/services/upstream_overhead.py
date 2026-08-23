"""Upstream prompt-overhead lookup: how many prompt_tokens a given upstream
route injects before the user's own text, so chat_billing.py can deduct it
from what the user is billed.

── The problem ──────────────────────────────────────────────────────────
Measured live on production, 2026-08-23: the identical two-token Persian
message "سلام" (max_tokens=3, temperature=0) reports wildly different
prompt_tokens depending only on which route served it, even for the SAME
underlying model in some cases -- see migration 0041's header for the
withdrawn/corrected numbers and the exact reasoning for why a single global
baseline was wrong. Some routes (measured worst: ninerouter's `cc/` and
`ag/` prefixes) add a system preamble/template server-side, after our
outgoing payload leaves us, and the upstream's own token accounting folds
that preamble into `prompt_tokens` -- so `chat_billing.py:199`, which takes
`prompt_tokens` straight from the response, was billing the user for text
they never wrote.

── Storage: app_setting, not a new table ──────────────────────────────────
Same reasoning as site_settings.py (read that module's docstring for the
full argument): app_setting (`key TEXT PRIMARY KEY, value JSONB NOT NULL,
updated_at`) is the generic settings store this project already has.
This module owns exactly one row, key ``upstream_prompt_overhead``, seeded
by migration 0041 (empty/inert until an admin runs a real measurement via
``POST /admin/upstream-overhead/measure`` in admin_overhead.py). Value
shape::

    {
        "version": 1,
        "measured_at": "<iso8601>" | null,
        "entries": {"<provider>:<prefix>": <int tokens>, ...},
        "provider_default": {"<provider>": <int tokens>, ...}
    }

``entries`` is keyed ``"<provider>:<first path segment of the provider's
model id>"`` because overhead has been measured to vary by upstream prefix
WITHIN one provider (not merely by provider) -- see migration 0041.
``provider_default`` is the fallback when a specific prefix has not been
measured yet.

── Fail-safe direction: 0, always ──────────────────────────────────────
:func:`get_prompt_overhead` never raises and returns ``0`` on ANY failure
(Redis down, DB down, malformed row, unknown provider, unknown prefix).
0 is the correct fail-safe value here -- unlike a feature flag defaulting
to "off" being the safe direction, here 0 means "apply no discount, charge
the user the full upstream-reported amount". A lookup failure must never
itself manufacture a discount; the one thing this module is never allowed
to do is make a request cheaper because something else broke.

Redis-cached with a short TTL (mirrors site_settings.py's pattern and its
``cache:`` key prefix convention) so a hot chat path is not a DB round trip
per request; ``admin_overhead.py`` deletes the cache key immediately after
writing a fresh measurement, same belt-and-suspenders pattern as
site_settings.py's flag writes.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy

from database import async_session, rds

logger = logging.getLogger(__name__)

_SETTING_KEY = 'upstream_prompt_overhead'
_CACHE_KEY = 'cache:upstream_overhead:map'
_CACHE_TTL_SECONDS = 60


def _prefix(model: str | None) -> str:
    """First path segment of a provider_model_id, e.g. 'cc' from
    'cc/claude-haiku-4-5-20251001'. A model with no '/' has no prefix
    distinct from itself, which is fine -- it just won't match any
    per-prefix entry and falls through to provider_default."""
    if not model:
        return ''
    return model.split('/', 1)[0]


async def _load_map() -> dict[str, Any] | None:
    """The stored map dict, or None on any lookup miss/error. Never raises."""
    try:
        cached = await rds.get(_CACHE_KEY)
        if cached is not None:
            return json.loads(cached)
    except Exception as e:
        logger.warning('upstream_overhead: cache read failed: %s', e)

    value: Any = None
    try:
        if async_session is None:
            return None
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text('SELECT value FROM app_setting WHERE key = :k'),
                {'k': _SETTING_KEY},
            )
            row = res.fetchone()
            value = row.value if row is not None else None
    except Exception as e:
        logger.warning('upstream_overhead: DB read failed: %s', e)
        return None

    try:
        await rds.setex(_CACHE_KEY, _CACHE_TTL_SECONDS, json.dumps(value))
    except Exception as e:
        logger.warning('upstream_overhead: cache write failed: %s', e)

    return value


async def get_prompt_overhead(provider: str | None, model: str | None) -> int:
    """Measured overhead (tokens) for ``provider``'s route to ``model``.

    Lookup order: exact ``"<provider>:<prefix>"`` entry, then
    ``provider_default[provider]``, then 0. Never raises; 0 on any error
    (see module docstring for why 0, specifically, is the fail-safe value).
    """
    try:
        if not provider:
            return 0
        data = await _load_map()
        if not isinstance(data, dict):
            return 0

        entries = data.get('entries')
        if isinstance(entries, dict):
            key = f'{provider}:{_prefix(model)}'
            if key in entries:
                try:
                    return max(0, int(entries[key]))
                except (TypeError, ValueError):
                    pass

        provider_default = data.get('provider_default')
        if isinstance(provider_default, dict) and provider in provider_default:
            try:
                return max(0, int(provider_default[provider]))
            except (TypeError, ValueError):
                pass

        return 0
    except Exception as e:
        logger.warning(
            'upstream_overhead: get_prompt_overhead failed provider=%r model=%r: %s',
            provider, model, e,
        )
        return 0


def discounted_input_tokens(raw_input_tokens: int, overhead: int, floor: int) -> int:
    """Pure arithmetic, trivially testable in isolation.

    Never bills below ``floor`` (the caller's own honest local estimate of
    what the user actually sent) and never below 1 token.
    """
    return max(int(raw_input_tokens) - int(overhead), int(floor), 1)


async def invalidate_cache() -> None:
    """Drop the cached map. Call after writing a new measurement so the
    next lookup sees it within request latency, not up to
    ``_CACHE_TTL_SECONDS`` later. Never raises."""
    try:
        await rds.delete(_CACHE_KEY)
    except Exception as e:
        logger.warning('upstream_overhead: cache invalidation failed: %s', e)
