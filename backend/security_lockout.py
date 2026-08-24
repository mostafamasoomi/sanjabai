"""Account lockout system, split out of security.py (house 500-line cap).

MODULE SPLIT: security.py used to be one 570-line file holding the account
lockout system, rate limiting (RateLimiter engine + limiter instances +
RateLimitMiddleware), session-concurrency tracking, and the security
headers / CSRF middleware. Rate limiting, headers, and CSRF stayed in
security.py itself -- app.py imports SecurityHeadersMiddleware,
CsrfMiddleware, and RateLimitMiddleware directly from `security`, and a
regression test (tests/test_security_release.py) greps the literal text of
security.py for the RateLimiter fail-closed line, so that code was left in
place rather than moved. Only the account lockout system (this file) and
session-concurrency tracking (security_session.py) were self-contained
enough to move safely.

IMPORT/MONKEYPATCH CONTRACT: this module does a plain `import security` at
module scope (safe against the circular import -- nothing here touches a
`security` attribute until a function actually runs, by which point
security.py has finished executing and re-exporting from this module). Every
call site below that needs `_get_redis` or `get_real_ip` reaches them via
`security._get_redis()` / `security.get_real_ip(...)` at call time, never via
`from security import X` and never via a bare intra-module reference to a
locally-defined copy. This matters because tests monkeypatch
`security._get_redis` directly (see tests/test_concurrent_session_limit.py's
`patch.object(security, '_get_redis', lambda: r)`) -- Python resolves a bare
global against the *defining* module's namespace, so a `from security import
_get_redis` binding here would freeze the pre-patch function object and the
test's patch would silently not apply. `security.py` re-exports every public
name from this module (`record_failed_attempt`, `clear_lockout`,
`_get_lockout_identifier`, `get_lockout_info`, `check_lockout`,
`_send_lockout_alert`) so `from security import ...` and `security.<name>`
both keep resolving exactly as before the split, for auth.py, admin_mfa.py,
and tests/test_watchdog_settings.py.
"""
import logging
import time
from fastapi import Request

import security

logger = logging.getLogger('security')  # keep all security*.py logs under the pre-split 'security' logger name

# Escalating lockout durations (attempt threshold → seconds)
_LOCKOUT_THRESHOLDS: list[tuple[int, int]] = [
    (5,  15 * 60),    # 5 failures  → 15 minutes
    (10, 60 * 60),    # 10 failures → 1 hour
    (15, 24 * 60 * 60),  # 15 failures → 24 hours
]

# Redis key prefixes
_LOCKOUT_KEY = 'lockout:{}'           # lockout:{identifier} → TTL-based lock
_ATTEMPTS_KEY = 'login_attempts:{}'   # login_attempts:{identifier} → count
_LOCKOUT_WINDOW = 24 * 60 * 60        # 24h window for counting attempts


async def _get_lockout_identifier(request: Request) -> str | None:
    """Get lockout identifier from request (email or IP-based).

    Only returns an identifier for login-related endpoints.
    """
    path = request.url.path
    if path not in ('/auth/login', '/admin/login'):
        return None
    # For /auth/login, try to extract email from request body
    # For /admin/login, use IP-based identifier
    if path == '/admin/login':
        ip = security.get_real_ip(request)
        return f'admin_ip:{ip}'
    # For regular login, use IP as identifier (email extraction is done at the endpoint level)
    ip = security.get_real_ip(request)
    return f'login_ip:{ip}'


async def check_lockout(identifier: str) -> bool:
    """Check if an identifier is currently locked out.

    Returns True if locked, False otherwise.
    """
    try:
        lockout_ttl = await security._get_redis().ttl(_LOCKOUT_KEY.format(identifier))
        return lockout_ttl > 0
    except Exception as e:
        logger.warning("Lockout check Redis error: %s", e)
        return False  # Fail open if Redis is down


async def record_failed_attempt(identifier: str) -> None:
    """Record a failed login attempt and apply lockout if threshold exceeded.

    Escalating lockout:
      - 5 failures  → 15 minutes
      - 10 failures → 1 hour
      - 15 failures → 24 hours
    """
    try:
        key = _ATTEMPTS_KEY.format(identifier)
        count = await security._get_redis().incr(key)
        if count == 1:
            await security._get_redis().expire(key, _LOCKOUT_WINDOW)

        # Determine lockout duration based on attempt count
        lockout_seconds = 0
        for threshold, duration in reversed(_LOCKOUT_THRESHOLDS):
            if count >= threshold:
                lockout_seconds = duration
                break

        if lockout_seconds > 0:
            lockout_key = _LOCKOUT_KEY.format(identifier)
            await security._get_redis().setex(lockout_key, lockout_seconds, str(count))
            logger.warning(
                "Account lockout applied: identifier=%s attempts=%d lockout=%ds",
                identifier, count, lockout_seconds,
            )
            # Send Telegram alert for lockout
            await _send_lockout_alert(identifier, count, lockout_seconds)

    except Exception as e:
        logger.warning("Failed to record attempt: %s", e)


async def clear_lockout(identifier: str) -> None:
    """Clear lockout and attempt counter for an identifier (on successful login)."""
    try:
        await security._get_redis().delete(
            _LOCKOUT_KEY.format(identifier),
            _ATTEMPTS_KEY.format(identifier),
        )
    except Exception as e:
        logger.warning("Failed to clear lockout: %s", e)


async def get_lockout_info(identifier: str) -> dict:
    """Get current lockout information for an identifier."""
    try:
        lockout_ttl = await security._get_redis().ttl(_LOCKOUT_KEY.format(identifier))
        attempts_raw = await security._get_redis().get(_ATTEMPTS_KEY.format(identifier))
        attempts = int(attempts_raw) if attempts_raw else 0
        return {
            'locked': lockout_ttl > 0,
            'attempts': attempts,
            'lockout_remaining_seconds': max(0, lockout_ttl),
        }
    except Exception:
        return {'locked': False, 'attempts': 0, 'lockout_remaining_seconds': 0}


async def _send_lockout_alert(identifier: str, attempts: int, lockout_seconds: int) -> None:
    """Send Telegram alert on account lockout (best-effort).

    Credentials come from services/watchdog_settings.py (admin-editable
    ``app_setting`` rows since migration 0044, falling back to the
    WATCHDOG_BOT_TOKEN / WATCHDOG_CHAT_ID environment variables this
    function used to read directly). The resolver never raises, but the
    lookup is inside the same guard as the send anyway -- an alerting
    lookup must never be able to break a login path.
    """
    try:
        from services.watchdog_settings import get_watchdog_credentials
        creds = await get_watchdog_credentials()
        bot_token, chat_id = creds.as_tuple()
    except Exception as e:
        logger.warning("Failed to resolve watchdog credentials: %s", e)
        return
    if not bot_token or not chat_id:
        return
    try:
        import httpx
        duration_label = f"{lockout_seconds // 60}min" if lockout_seconds < 3600 else f"{lockout_seconds // 3600}hr"
        msg = (
            f"🔒 Account Lockout Alert\n"
            f"Identifier: {identifier}\n"
            f"Failed attempts: {attempts}\n"
            f"Lockout duration: {duration_label}\n"
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
        )
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f'https://api.telegram.org/bot{bot_token}/sendMessage',
                json={'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML'},
            )
    except Exception as e:
        logger.warning("Failed to send lockout alert: %s", e)
