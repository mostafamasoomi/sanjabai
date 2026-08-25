"""Concurrent-session tracking, split out of security.py (house 500-line cap).

See security_lockout.py's module docstring for the full split rationale and
the shared IMPORT/MONKEYPATCH CONTRACT: this module does a plain `import
security` at module scope and reaches `security._get_redis()` /
`security.get_real_ip(...)` at call time only, never via `from security
import X`. tests/test_concurrent_session_limit.py does
`patch.object(security, '_get_redis', lambda: r)` and expects `track_session`
/ `_revoke_session` (defined here) to observe it -- a bare-name import would
freeze the pre-patch function and silently break that test. security.py
re-exports `track_session`, `update_session_last_seen`, `get_session_info`,
and `MAX_CONCURRENT_SESSIONS` from this module so `from security import
track_session` (auth.py) and `security.track_session` (test_concurrent_
session_limit.py) both keep resolving exactly as before the split.
"""
import logging
import json as _json
import time
from fastapi import Request

import security

logger = logging.getLogger('security')  # keep all security*.py logs under the pre-split 'security' logger name

MAX_CONCURRENT_SESSIONS = 3


async def track_session(token: str, user_id: int, request: Request) -> None:
    """Track session metadata and enforce the concurrent-session limit.

    Stores session metadata (IP, user-agent, created_at) in Redis.
    If user exceeds MAX_CONCURRENT_SESSIONS, revokes the oldest session.

    The per-user set is `sessions:{uid}` -- the same one dependencies.py's
    `_create_session` writes and `/auth/logout-all` reads. This used to keep
    its own parallel `active_sessions:{uid}` set, which meant revoking a
    session here removed it from one set but left it in the other, so
    logout-all still walked a token that no longer existed and the limit was
    counted against a set nothing else maintained. One set, one truth.
    """
    try:
        metadata = {
            'user_id': user_id,
            'ip': security.get_real_ip(request),
            'user_agent': request.headers.get('user-agent', '')[:200],
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'last_seen': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }
        session_key = f'session_meta:{token}'
        await security._get_redis().setex(session_key, 86400 * 7, _json.dumps(metadata))

        user_sessions_key = f'sessions:{user_id}'
        await security._get_redis().sadd(user_sessions_key, token)

        await _enforce_session_limit(user_id, token)

    except Exception as e:
        logger.warning("Session tracking error: %s", e)


async def _session_age(token: str) -> str | None:
    """When this session was created, or None if it is not alive.

    Read from `session:{token}` -- the key dependencies._create_session
    writes and _get_session reads -- because that is the ONE key every live
    session has. Its payload already carries `created_at`, so nothing extra
    needs storing. `session_meta:` is only a fallback: it is written by
    track_session at login and signup, and NOT by _rotate_session, so a
    rotated session has no meta at all.

    That gap is what broke the limit in production. Measured on the live box
    2026-08-25: `sessions:1` held 8 members against a cap of 3 -- seven with
    a live `session:` and no meta, one an outright corpse. The old loop
    ordered purely by meta, so it could only ever see that single member,
    picked it every time, and left the other seven untouched. The cap never
    held, and each login killed the one session it could actually see --
    which is what "it keeps logging me out" looked like from the outside.
    """
    rds = security._get_redis()
    raw = await rds.get(f'session:{token}')
    if not raw:
        return None
    try:
        created = _json.loads(raw).get('created_at')
        if created:
            return str(created)
    except (ValueError, TypeError):
        pass
    meta_raw = await rds.get(f'session_meta:{token}')
    if meta_raw:
        try:
            created = _json.loads(meta_raw).get('created_at')
            if created:
                return str(created)
        except (ValueError, TypeError):
            pass
    return ''


async def _enforce_session_limit(user_id: int, keep_token: str) -> None:
    """Prune dead members, then evict oldest-first until the cap holds.

    Two things the previous version got wrong, both of which let the set
    grow without bound:

      * It never removed members whose session had already expired. Redis
        drops `session:{tok}` on its own TTL but nothing SREMs the token
        from `sessions:{uid}`, so corpses accumulate and inflate the count
        against the cap forever.
      * It evicted at most ONE session per login. Once the set had drifted
        above the cap it could never come back down, no matter how many
        logins happened.

    `keep_token` is the session that just logged in; it is never the victim.
    """
    rds = security._get_redis()
    key = f'sessions:{user_id}'
    members = await rds.smembers(key) or set()

    live: list[tuple[str, str]] = []
    for tok in members:
        if tok == keep_token:
            # The session that just logged in is alive by definition and is
            # never a victim. Exempting it from the liveness probe as well
            # matters: auth.py creates the session and then calls
            # track_session, and if that order were ever reversed a strict
            # probe would prune the caller's own brand-new token and log
            # them straight back out.
            live.append(('\uffff', tok))
            continue
        age = await _session_age(tok)
        if age is None:
            # Expired or revoked elsewhere -- drop it from the set and take
            # its orphaned metadata with it.
            await rds.srem(key, tok)
            await rds.delete(f'session_meta:{tok}')
            continue
        live.append((age, tok))

    # Oldest first. An unknown created_at sorts as '' -- i.e. oldest -- so a
    # session we cannot age is evicted before one we can. That is the safe
    # direction: the alternative is keeping an unidentifiable session
    # forever while killing ones we can account for.
    live.sort(key=lambda pair: pair[0])

    for age, tok in live:
        if len(live) <= MAX_CONCURRENT_SESSIONS:
            break
        if tok == keep_token:
            continue
        await _revoke_session(tok, user_id)
        logger.info("Revoked oldest session %s for user %d (limit exceeded)", tok[:8], user_id)
        live = [pair for pair in live if pair[1] != tok]


async def _revoke_session(token: str, user_id: int) -> None:
    """Revoke a single session and clean up its tracking data.

    Removes the token from `sessions:{uid}` -- the same set _create_session
    and /auth/logout-all use -- so a revoked session leaves nothing behind.
    """
    try:
        await security._get_redis().delete(f'session:{token}', f'session_meta:{token}')
        await security._get_redis().srem(f'sessions:{user_id}', token)
    except Exception:
        pass


async def update_session_last_seen(token: str) -> None:
    """Update the last_seen timestamp for a session."""
    try:
        meta_raw = await security._get_redis().get(f'session_meta:{token}')
        if meta_raw:
            meta = _json.loads(meta_raw)
            meta['last_seen'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            await security._get_redis().setex(f'session_meta:{token}', 86400 * 7, _json.dumps(meta))
    except Exception:
        pass


async def get_session_info(token: str) -> dict | None:
    """Get session metadata (IP, user-agent, timestamps)."""
    try:
        meta_raw = await security._get_redis().get(f'session_meta:{token}')
        if meta_raw:
            return _json.loads(meta_raw)
    except Exception:
        pass
    return None
