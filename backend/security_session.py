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

        # Enforce concurrent session limit
        members = await security._get_redis().smembers(user_sessions_key)
        if members and len(members) > MAX_CONCURRENT_SESSIONS:
            # Find oldest session to revoke
            oldest_token = None
            oldest_time = None
            for tok in members:
                meta_raw = await security._get_redis().get(f'session_meta:{tok}')
                if meta_raw:
                    try:
                        meta = _json.loads(meta_raw)
                        created = meta.get('created_at', '')
                        if oldest_time is None or created < oldest_time:
                            oldest_time = created
                            oldest_token = tok
                    except (ValueError, KeyError):
                        pass
            if oldest_token and oldest_token != token:
                await _revoke_session(oldest_token, user_id)
                logger.info("Revoked oldest session %s for user %d (limit exceeded)", oldest_token[:8], user_id)

    except Exception as e:
        logger.warning("Session tracking error: %s", e)


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
