"""Per-user opt-out for the LLM-backed smart router (services/smart_router_llm.py).

Split out of smart_router_llm.py on purpose: that file is at the 500-line
cap, and this is a single, self-contained concern -- reading one JSON key
off `users.preferences` -- that does not need to live in the hot-path
module to be imported by it.

── THE CONTRACT ────────────────────────────────────────────────────────────
`smart_llm_router_enabled` (site_settings.py) is the master kill switch: if
it is off, nobody gets the router, full stop. Within that, each user can
turn the router off for themselves via `preferences['smart_router_enabled']`
(a plain JSON bool on the `users` row) -- default **True**, so turning the
site flag on hands the router to everyone who has not explicitly opted out.

This module answers exactly one question -- "does this user, individually,
allow the router?" -- and never touches the site flag; `smart_router_llm.
llm_route` is responsible for checking both, IN ORDER, site flag first
(cheap) and this (a Postgres read) last. See llm_route's own gate-order
comment for why the order matters.

FAIL OPEN, same reasoning as the rest of smart_router_llm.py: a user with
no row, no `preferences` dict, no key in it, an unreadable database, or no
`uid` at all is ALLOWED, never blocked. The only thing that can turn the
router off for a user is an explicit `false` this module can actually read;
every other outcome here is inert with the site flag as the real gate.
"""
from __future__ import annotations

import logging

from database import async_session
from models import User

logger = logging.getLogger('chat')  # same logger name as the rest of the chat path

# users.preferences JSON key. Absent -> default True (opted in).
_PREF_KEY = 'smart_router_enabled'


async def user_allows_router(uid: int | None) -> bool:
    """True unless `uid` has an explicit `false` for `smart_router_enabled`
    in their `preferences`.

    `uid=None` means the caller had nothing to look up (llm_route's own
    `uid` argument is optional) -- there is no user to have opted out of
    anything, so this returns True rather than treating "no uid" as a
    reason to block.

    Never raises: `async_session` is a proxy that RAISES when unset, it is
    never literally None, so this goes through try/except rather than an
    `is None` check (see auth_profile.py's identical idiom); any failure --
    unset session, a dead connection, a malformed `preferences` value --
    fails OPEN (True), matching every other "doubt -> don't block" answer
    in this feature. The site flag remains the real gate.
    """
    if uid is None:
        return True
    try:
        async with async_session() as session:
            res = await session.execute(User.__table__.select().where(User.id == uid))
            user = res.fetchone()
            if not user:
                return True
            prefs = user.preferences or {}
            return bool(prefs.get(_PREF_KEY, True))
    except Exception as e:
        logger.warning(f"smart_router preference read failed uid={uid}, allowing: {e}")
        return True
