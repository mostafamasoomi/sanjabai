"""Admin-editable Telegram alerting credentials, with an env fallback.

Three places in this backend send a Telegram alert, and until migration
0044 all three read the same two PLAIN ENVIRONMENT VARIABLES:

  * ``backend/security_lockout.py::_send_lockout_alert`` -- account lockout
  * ``backend/watchdog.py::_send_telegram``           -- financial anomalies
  * ``backend/services/moderation_store.py::_send_alert`` -- content safety

Changing either credential therefore meant an SSH session, an edit of
``.env`` and a container restart. This module makes them rows in
``app_setting`` (keys :data:`KEY_BOT_TOKEN` / :data:`KEY_CHAT_ID`, seeded
empty by migration 0044) that an admin can edit from the panel, WITHOUT
taking the environment variables away from anyone already using them.

── Precedence, and why it is this way round ────────────────────────────────
For each credential independently:

    non-empty DB row  >  non-empty environment variable  >  '' (inert)

DB first, because the whole point is that the panel is authoritative once
an admin has typed a value -- an env var that silently won would make the
panel a button that confirms success and does nothing. Env second, because
the deploy that ships this must not turn alerting off for an operator who
configured it the old way. Empty is not a value, it is "unset, defer" --
which is exactly what the panel writes when the admin clears the field, so
clearing hands control back to the environment rather than disabling
alerts outright. The two credentials resolve independently, so a
DB-configured chat id can pair with an env-configured token.

── Fail-open contract -- READ THIS before adding a call site ──────────────
:func:`get_watchdog_credentials` NEVER raises and never blocks. On any
Redis or DB error it returns the environment values, i.e. exactly today's
behaviour, and logs a warning. That is not cosmetic: ``_send_alert`` is
reached from ``services.moderation.screen_request``, which sits on the
CHAT HOT PATH -- every user message passes through it. A hiccup in the
alerting *configuration* store must degrade alerting, never chat. Same
idiom as :func:`site_settings.get_site_flag`; the difference from the
admin GET in ``admin_watchdog.py`` (direct DB, no cache, no fail-open) is
the same difference documented there -- an admin control panel must never
render "not configured" when the truth is unknown.

── Why the reader is injectable ───────────────────────────────────────────
``watchdog.py`` runs as its OWN container (``sanjabai_watchdog`` in
docker-compose.yml, ``command: python watchdog.py``). That process has no
FastAPI lifespan, so ``database.async_session`` is never initialised there,
and it is not even given ``ADMIN_TOKEN`` -- so merely importing
``database`` inside it raises ``RuntimeError`` at import time. Hence two
things: every import of ``database`` below is lazy and guarded, and
:func:`get_watchdog_credentials` accepts a ``reader`` callable so
``watchdog.py`` can serve the same two rows off the asyncpg pool it
already owns. Without that hook the watchdog container would keep reading
env-only forever while the panel claimed the credentials were live -- the
dishonest-label failure this codebase refuses.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

KEY_BOT_TOKEN = 'watchdog_bot_token'
KEY_CHAT_ID = 'watchdog_chat_id'
SETTING_KEYS = (KEY_BOT_TOKEN, KEY_CHAT_ID)

ENV_BOT_TOKEN = 'WATCHDOG_BOT_TOKEN'
ENV_CHAT_ID = 'WATCHDOG_CHAT_ID'

# Both credentials travel as ONE cached blob rather than two keys: they are
# always read together and always written together, so a single round trip
# is strictly cheaper and cannot go half-stale. TTL matches site_settings'
# 30s -- an admin who fixes a bad token wants the next alert to use it, and
# the write endpoint additionally invalidates this key immediately, so the
# TTL only bounds what a CONCURRENT reader in another process waits out.
_CACHE_TTL_SECONDS = 30
_CACHE_KEY = 'cache:watchdog_settings:creds'

# An async callable taking the tuple of setting keys and returning
# {key: raw_json_value}. See the module docstring for why this exists.
RawReader = Callable[[tuple[str, ...]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class WatchdogCredentials:
    """Resolved credentials plus where each half actually came from.

    ``*_source`` is one of ``'db'``, ``'env'`` or ``'none'`` and is what the
    admin panel renders. It is deliberately part of the return value rather
    than something the panel guesses: "alerting is on" and "alerting is on
    because of a value you can see in this form" are different claims, and
    only the second one is actionable.
    """

    bot_token: str = ''
    chat_id: str = ''
    bot_token_source: str = 'none'
    chat_id_source: str = 'none'

    @property
    def active(self) -> bool:
        """True only when an alert would actually be sent -- BOTH halves
        present. Every one of the three call sites requires both, so a
        token without a chat id is exactly as inert as neither."""
        return bool(self.bot_token and self.chat_id)

    def as_tuple(self) -> tuple[str, str]:
        """``(bot_token, chat_id)`` -- the shape the three call sites want."""
        return self.bot_token, self.chat_id


def _coerce(raw: Any, key: str) -> str:
    """A stored value becomes a credential only if it is genuinely a string.

    Every write path stores ``json.dumps(str)`` and migration 0044 seeds
    ``'""'``, so anything else is corrupt or hand-edited. Falling back to
    ``''`` (which then defers to the environment) is the only safe read of
    a malformed row -- coercing with ``str(raw)`` would happily turn a
    stray ``true`` into the literal bot token ``"True"`` and make every
    alert fail against Telegram with a 404 that nothing explains.
    """
    if raw is None:
        return ''
    if isinstance(raw, str):
        return raw.strip()
    logger.warning(
        'watchdog_settings: value for %r is %r (%s), not a string -- '
        'treating it as unset and deferring to the environment; '
        'this row needs fixing',
        key, raw, type(raw).__name__,
    )
    return ''


def _env(name: str) -> str:
    return (os.getenv(name, '') or '').strip()


def _resolve(db_value: str, env_value: str) -> tuple[str, str]:
    """One credential -> ``(value, source)``. See the precedence block."""
    if db_value:
        return db_value, 'db'
    if env_value:
        return env_value, 'env'
    return '', 'none'


def _from_db_values(db: dict[str, Any]) -> WatchdogCredentials:
    token, token_src = _resolve(_coerce(db.get(KEY_BOT_TOKEN), KEY_BOT_TOKEN),
                                _env(ENV_BOT_TOKEN))
    chat, chat_src = _resolve(_coerce(db.get(KEY_CHAT_ID), KEY_CHAT_ID),
                              _env(ENV_CHAT_ID))
    return WatchdogCredentials(
        bot_token=token, chat_id=chat,
        bot_token_source=token_src, chat_id_source=chat_src,
    )


def env_only_credentials() -> WatchdogCredentials:
    """What the resolver degrades to when the database is unreachable --
    i.e. byte-for-byte the behaviour every call site had before 0044."""
    return _from_db_values({})


async def _read_via_session() -> dict[str, Any] | None:
    """Read both rows through the API process's SQLAlchemy session.

    Returns ``None`` (not ``{}``) when the session is unavailable or the
    read fails, so the caller can tell "no rows stored" apart from "could
    not look" and decline to cache the second one.
    """
    try:
        import sqlalchemy
        from database import async_session
    except Exception as e:  # pragma: no cover - only in the watchdog process
        logger.debug('watchdog_settings: no database module available (%s)', e)
        return None
    if async_session is None:
        return None
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text(
                    'SELECT key AS setting_key, value FROM app_setting '
                    'WHERE key = ANY(:keys)'
                ),
                {'keys': list(SETTING_KEYS)},
            )
            return {r.setting_key: r.value for r in res.fetchall()}
    except Exception as e:
        logger.warning('watchdog_settings DB read failed (%s) -- '
                       'falling back to environment variables', e)
        return None


async def get_watchdog_credentials(reader: RawReader | None = None) -> WatchdogCredentials:
    """The read helper every alert call site should use. Never raises.

    ``reader`` overrides how the two rows are fetched -- ``watchdog.py``
    passes one backed by its own asyncpg pool because it cannot import
    ``database`` (see the module docstring). When it is given, the Redis
    cache is skipped entirely: that process has its own Redis handle, alerts
    there are rare and cooldown-gated, and a second cache of the same two
    rows would only add a way for the two processes to disagree.
    """
    if reader is not None:
        try:
            return _from_db_values(await reader(SETTING_KEYS) or {})
        except Exception as e:
            logger.warning('watchdog_settings custom reader failed (%s) -- '
                           'falling back to environment variables', e)
            return env_only_credentials()

    # Cache first. A cache miss is normal; a cache ERROR is not fatal --
    # it just means we pay for the DB read.
    try:
        from database import rds
        cached = await rds.get(_CACHE_KEY)
        if cached is not None:
            return _from_db_values(json.loads(cached))
    except Exception as e:
        logger.warning('watchdog_settings cache read failed: %s', e)

    db = await _read_via_session()
    if db is None:
        return env_only_credentials()

    try:
        from database import rds
        await rds.setex(
            _CACHE_KEY, _CACHE_TTL_SECONDS,
            json.dumps({k: db.get(k) for k in SETTING_KEYS}),
        )
    except Exception as e:
        logger.warning('watchdog_settings cache write failed: %s', e)

    return _from_db_values(db)


async def invalidate_cache() -> None:
    """Drop the cached blob so the next read sees a just-written value.

    Called by the admin write endpoint. Best-effort by design -- a failed
    invalidation costs at most :data:`_CACHE_TTL_SECONDS` of staleness, so
    it must never turn a successful save into an error the admin sees.
    """
    try:
        from database import rds
        await rds.delete(_CACHE_KEY)
    except Exception as e:
        logger.warning('watchdog_settings cache invalidation failed: %s', e)
