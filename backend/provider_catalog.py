"""
Cached, background-refreshed provider model lists.

Calling a provider's `GET /v1/models` directly can be slow — 9Router's
endpoint takes about 9.5 seconds to return its ~823 models. That latency must
never land on a request a logged-in user can trigger.

This module is the only sanctioned way for the rest of the backend to read a
provider's model list on a request path: `cached_provider_models` always
reads Redis and NEVER calls upstream synchronously. On a cache miss it
returns whatever it has (possibly an empty list) and schedules a background
refresh instead of blocking the caller.

A periodic loop (`refresh_loop`, started from the app lifespan) refreshes
every configured provider on an interval so the cache stays warm without any
request ever having to pay for it. The cache TTL is set well beyond the
refresh interval so a single slow/failed upstream refresh cycle never empties
the cache before the next attempt lands.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from database import rds
from providers import configured_providers, list_models as _upstream_list_models

logger = logging.getLogger('provider_catalog')

#: How often the background loop refreshes every provider's model list.
REFRESH_INTERVAL_S = int(os.getenv('PROVIDER_CATALOG_REFRESH_INTERVAL', '900'))  # 15 minutes

#: Cache TTL comfortably outlives the refresh interval so an upstream blip
#: never empties the cache before the next scheduled refresh lands.
CACHE_TTL_S = REFRESH_INTERVAL_S * 3

_CACHE_KEY_PREFIX = 'cache:provider_models:'

#: Guards against overlapping refreshes of the same provider when a
#: cache-miss-triggered refresh and the periodic loop land at the same time.
_refresh_locks: dict[str, asyncio.Lock] = {}


def _cache_key(provider_name: str) -> str:
    return f'{_CACHE_KEY_PREFIX}{provider_name}'


async def cached_provider_models(provider_name: str) -> list[dict[str, Any]]:
    """A provider's model list, from cache only.

    Never calls upstream synchronously. On a miss this schedules a background
    refresh and returns an empty list immediately — callers must tolerate an
    empty/stale result; the cache self-heals on the next refresh cycle.
    """
    try:
        cached = await rds.get(_cache_key(provider_name))
    except Exception as e:
        logger.warning('redis read failed for %s: %s', provider_name, e)
        cached = None

    if cached:
        try:
            return json.loads(cached)
        except Exception as e:
            logger.warning('cached payload for %s was not valid JSON: %s', provider_name, e)

    # Miss (or corrupt cache entry): fire off a background refresh and return
    # nothing now rather than block this call on the upstream.
    asyncio.create_task(_refresh_one_safe(provider_name))
    return []


async def _refresh_one_safe(provider_name: str) -> None:
    try:
        await refresh_provider(provider_name)
    except Exception as e:
        logger.warning('background refresh failed for %s: %s', provider_name, e)


async def refresh_provider(provider_name: str) -> dict[str, Any]:
    """Fetch one provider's model list from upstream and refresh its cache entry."""
    lock = _refresh_locks.setdefault(provider_name, asyncio.Lock())
    if lock.locked():
        return {'provider': provider_name, 'skipped': 'refresh_in_progress'}
    async with lock:
        provider = next((p for p in configured_providers() if p.name == provider_name), None)
        if provider is None:
            return {'provider': provider_name, 'error': 'not_configured'}
        models = await _upstream_list_models(provider)
        if models:
            try:
                await rds.setex(_cache_key(provider_name), CACHE_TTL_S, json.dumps(models))
            except Exception as e:
                logger.warning('redis write failed for %s: %s', provider_name, e)
        return {'provider': provider_name, 'count': len(models)}


async def refresh_all() -> list[dict[str, Any]]:
    """Refresh every configured provider's model list. Best-effort per provider."""
    out: list[dict[str, Any]] = []
    for p in configured_providers():
        try:
            out.append(await refresh_provider(p.name))
        except Exception as e:
            logger.warning('refresh_all failed for %s: %s', p.name, e)
            out.append({'provider': p.name, 'error': type(e).__name__})
    return out


async def refresh_loop() -> None:
    """Background sweep. Started from the app lifespan."""
    await asyncio.sleep(15)  # let the app finish booting first
    while True:
        try:
            result = await refresh_all()
            logger.info('provider catalog refresh: %s', result)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning('provider catalog refresh loop error: %s', e)
        await asyncio.sleep(REFRESH_INTERVAL_S)
