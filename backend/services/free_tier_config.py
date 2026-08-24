"""Admin-tunable numbers for the free tier, read from app_setting.

Three values, seeded by migration 0045 and edited live from the admin panel
(backend/admin_free_tier.py):

* ``free_hourly_limit``               -- messages a free user may send per hour
* ``free_lifetime_limit``             -- messages a free user may EVER send
* ``free_tier_max_input_per_million`` -- the "cheap models only" price ceiling
  (Toman per million input tokens); a free user may only send to a model at or
  below this base input price.

Cached for 60 seconds in a module-level dict (same TTL and spirit as the
moderation-config cache), because these are read on the hot path of every
free-tier chat request. :func:`invalidate` clears it so an admin edit takes
effect at once; admin_free_tier.py calls it after a successful write.

Every read FAILS SAFE to the hardcoded defaults below -- if app_setting is
unreadable, or the migration has not been applied yet, the gate still runs
with sane numbers rather than raising or, worse, treating "unreadable" as
"no limit". The defaults equal the values migration 0045 seeds, so behaviour
before and after that migration is identical until an admin changes a value.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

import sqlalchemy

from database import async_session

logger = logging.getLogger(__name__)

# Fail-safe defaults. MUST equal the seeds in migration 0045 so the gate
# behaves identically whether or not the migration has run yet.
DEFAULT_HOURLY_LIMIT = 3
DEFAULT_LIFETIME_LIMIT = 30
DEFAULT_MAX_INPUT_PER_MILLION = 60000

_KEYS = ('free_hourly_limit', 'free_lifetime_limit', 'free_tier_max_input_per_million')
_DEFAULTS = {
    'free_hourly_limit': DEFAULT_HOURLY_LIMIT,
    'free_lifetime_limit': DEFAULT_LIFETIME_LIMIT,
    'free_tier_max_input_per_million': DEFAULT_MAX_INPUT_PER_MILLION,
}

_CACHE_TTL = 60  # seconds
_cache: Optional[dict[str, int]] = None
_cache_at: float = 0.0

_SELECT_SQL = sqlalchemy.text(
    'SELECT key AS setting_key, value FROM app_setting WHERE key = ANY(:keys)'
)


def invalidate() -> None:
    """Drop the cache so the next read reflects a just-written admin change."""
    global _cache, _cache_at
    _cache = None
    _cache_at = 0.0


def _coerce_int(value, fallback: int) -> int:
    """app_setting.value is JSONB. A number comes back as int/float; a string
    (some rows historically store JSON strings) is parsed. Anything that will
    not become a non-negative int falls back to the seeded default rather than
    poisoning the gate with a bad number."""
    try:
        if isinstance(value, str):
            value = json.loads(value)
        n = int(value)
        return n if n >= 0 else fallback
    except Exception:
        return fallback


async def _load() -> dict[str, int]:
    """Read all three values from app_setting, each falling back to its
    default if its row is missing or malformed. Never raises."""
    result = dict(_DEFAULTS)
    try:
        if async_session is None:
            return result
        async with async_session() as session:
            res = await session.execute(_SELECT_SQL, {'keys': list(_KEYS)})
            for row in res.fetchall():
                m = row._mapping
                key = m['setting_key']
                if key in _DEFAULTS:
                    result[key] = _coerce_int(m['value'], _DEFAULTS[key])
    except Exception as e:
        logger.warning(f"free_tier_config load failed, using defaults: {e}")
        return dict(_DEFAULTS)
    return result


async def get_config() -> dict[str, int]:
    """The three numbers, cached for 60s. Always returns a complete dict with
    every key present (defaults fill any gap). Never raises."""
    global _cache, _cache_at
    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < _CACHE_TTL:
        return _cache
    loaded = await _load()
    _cache = loaded
    _cache_at = now
    return loaded
