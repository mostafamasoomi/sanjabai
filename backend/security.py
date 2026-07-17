"""
Security middleware: rate limiting, security headers, input validation,
account lockout, and session security.
All rate limits use Redis for persistence across restarts.
"""
import logging
import os
import time
import hashlib
import json as _json
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# ── Lazy Redis import (avoids circular import) ────────────

_rds = None

def _get_redis():
    global _rds
    if _rds is None:
        from database import rds as _redis
        _rds = _redis
    return _rds


# ── Account Lockout System ──────────────────────────────────

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
        ip = get_real_ip(request)
        return f'admin_ip:{ip}'
    # For regular login, use IP as identifier (email extraction is done at the endpoint level)
    ip = get_real_ip(request)
    return f'login_ip:{ip}'


async def check_lockout(identifier: str) -> bool:
    """Check if an identifier is currently locked out.

    Returns True if locked, False otherwise.
    """
    try:
        lockout_ttl = await _get_redis().ttl(_LOCKOUT_KEY.format(identifier))
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
        count = await _get_redis().incr(key)
        if count == 1:
            await _get_redis().expire(key, _LOCKOUT_WINDOW)

        # Determine lockout duration based on attempt count
        lockout_seconds = 0
        for threshold, duration in reversed(_LOCKOUT_THRESHOLDS):
            if count >= threshold:
                lockout_seconds = duration
                break

        if lockout_seconds > 0:
            lockout_key = _LOCKOUT_KEY.format(identifier)
            await _get_redis().setex(lockout_key, lockout_seconds, str(count))
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
        await _get_redis().delete(
            _LOCKOUT_KEY.format(identifier),
            _ATTEMPTS_KEY.format(identifier),
        )
    except Exception as e:
        logger.warning("Failed to clear lockout: %s", e)


async def get_lockout_info(identifier: str) -> dict:
    """Get current lockout information for an identifier."""
    try:
        lockout_ttl = await _get_redis().ttl(_LOCKOUT_KEY.format(identifier))
        attempts_raw = await _get_redis().get(_ATTEMPTS_KEY.format(identifier))
        attempts = int(attempts_raw) if attempts_raw else 0
        return {
            'locked': lockout_ttl > 0,
            'attempts': attempts,
            'lockout_remaining_seconds': max(0, lockout_ttl),
        }
    except Exception:
        return {'locked': False, 'attempts': 0, 'lockout_remaining_seconds': 0}


async def _send_lockout_alert(identifier: str, attempts: int, lockout_seconds: int) -> None:
    """Send Telegram alert on account lockout (best-effort)."""
    bot_token = os.getenv('WATCHDOG_BOT_TOKEN', '')
    chat_id = os.getenv('WATCHDOG_CHAT_ID', '')
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


# ── Rate Limiting ──────────────────────────────────────────

class RateLimiter:
    """Sliding window rate limiter using Redis"""

    def __init__(self, window_seconds: int = 60, max_requests: int = 30):
        self.window = window_seconds
        self.max = max_requests

    def _key(self, identifier: str) -> str:
        now = int(time.time() / self.window)
        return f'ratelimit:{identifier}:{now}'

    async def is_allowed(self, identifier: str) -> tuple[bool, int]:
        """Returns (allowed, remaining)"""
        key = self._key(identifier)
        try:
            count = await _get_redis().incr(key)
            if count == 1:
                await _get_redis().expire(key, self.window * 2)
            remaining = max(0, self.max - count)
            return count <= self.max, remaining
        except Exception as e:
            logger.warning("Rate limiter Redis unavailable, failing closed: %s", e)
            return False, 0  # Fail closed: deny traffic when Redis is down


# Different rate limits for different endpoint types
general_limiter = RateLimiter(window_seconds=60, max_requests=60)     # 60 req/min
login_limiter = RateLimiter(window_seconds=60, max_requests=30)       # 30 req/min
signup_limiter = RateLimiter(window_seconds=60, max_requests=5)        # 5 req/min
forgot_password_limiter = RateLimiter(window_seconds=60, max_requests=20)  # 20 req/min
auth_limiter = RateLimiter(window_seconds=60, max_requests=60)        # 60 req/min (general auth)
chat_free_limiter = RateLimiter(window_seconds=60, max_requests=30)        # 30 req/min (free tier)
chat_pro_limiter = RateLimiter(window_seconds=60, max_requests=120)       # 120 req/min (pro tier)
chat_enterprise_limiter = RateLimiter(window_seconds=60, max_requests=300)  # 300 req/min (enterprise tier)
admin_limiter = RateLimiter(window_seconds=60, max_requests=30)      # 30 req/min
# RAG endpoints — stricter limits to protect embedding/LLM compute + storage
rag_upload_limiter = RateLimiter(window_seconds=60, max_requests=5)   # 5 uploads/min
rag_query_limiter = RateLimiter(window_seconds=60, max_requests=20)   # 20 queries/min
rag_general_limiter = RateLimiter(window_seconds=60, max_requests=60) # 60/min other RAG


async def get_client_identifier(request: Request) -> str:
    """Get unique client identifier: prefer user_id, fallback to IP"""
    # Try auth token first
    token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if token:
        try:
            session_data = await _get_redis().get(f'session:{token}')
            if session_data:
                try:
                    uid = (_json.loads(session_data) or {}).get('user_id')
                    if uid:
                        return f'user:{uid}'
                except (ValueError, AttributeError):
                    return f'user:{session_data}'
        except Exception:
            pass
    # Fallback to IP + User-Agent hash (using validated real IP)
    ip = get_real_ip(request)
    ua = request.headers.get('user-agent', '')
    return f'ip:{hashlib.sha256(f"{ip}:{ua}".encode()).hexdigest()[:12]}'


# ── X-Forwarded-For validation ─────────────────────────────

TRUSTED_PROXY_IPS: set[str] = set(
    ip.strip() for ip in os.getenv('TRUSTED_PROXY_IPS', '').split(',') if ip.strip()
)


def get_real_ip(request: Request) -> str:
    """Get the real client IP, validating X-Forwarded-For against trusted proxies.

    Only trusts XFF header when the connecting IP is a known proxy.
    Falls back to request.client.host when XFF is not trusted or absent.
    """
    xff = request.headers.get('x-forwarded-for', '')
    if xff and TRUSTED_PROXY_IPS:
        connecting_ip = request.client.host if request.client else None
        if connecting_ip and connecting_ip in TRUSTED_PROXY_IPS:
            # X-Forwarded-For: client, proxy1, proxy2
            # The leftmost IP is the original client
            return xff.split(',')[0].strip()
    # Fallback to direct connection IP
    return request.client.host if request.client else 'unknown'


def select_limiter(path: str) -> RateLimiter:
    """Choose appropriate rate limiter based on path"""
    if path == '/auth/login':
        return login_limiter
    if path == '/auth/signup':
        return signup_limiter
    if path == '/auth/forgot-password':
        return forgot_password_limiter
    if path.startswith('/auth/'):
        return auth_limiter
    if path.startswith('/v1/chat/'):
        return chat_pro_limiter
    if path.startswith('/admin/'):
        return admin_limiter
    if path == '/v1/rag/upload':
        return rag_upload_limiter
    if path == '/v1/rag/query':
        return rag_query_limiter
    if path.startswith('/v1/rag/'):
        return rag_general_limiter
    return general_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for FastAPI"""

    async def dispatch(self, request: Request, call_next):
        # Skip health check and static
        if request.url.path in ['/health', '/health/live', '/health/ready', '/health/detailed', '/']:
            return await call_next(request)

        # Account lockout check for login endpoints
        lockout_id = await _get_lockout_identifier(request)
        if lockout_id and await check_lockout(lockout_id):
            return JSONResponse(
                {'detail': 'حساب شما به دلیل تلاش‌های ناموفق زیاد موقتاً قفل شده است', 'retry_after': 900},
                status_code=423,
                headers={'Retry-After': '900'},
            )

        identifier = await get_client_identifier(request)
        limiter = select_limiter(request.url.path)

        # Tiered rate limits for chat endpoints
        if request.url.path.startswith('/v1/chat/'):
            uid = await _extract_user_id(request)
            if uid is not None:
                plan = await _get_user_plan(uid)
                if plan == 'enterprise':
                    limiter = chat_enterprise_limiter
                elif plan == 'pro':
                    limiter = chat_pro_limiter
                else:
                    limiter = chat_free_limiter
            else:
                limiter = chat_free_limiter  # unauthenticated = free tier

        allowed, remaining = await limiter.is_allowed(identifier)

        if not allowed:
            return JSONResponse(
                {'detail': 'محدودیت نرخ درخواست. لطفاً بعداً تلاش کنید.', 'retry_after': limiter.window},
                status_code=429,
                headers={
                    'Retry-After': str(limiter.window),
                    'X-RateLimit-Limit': str(limiter.max),
                    'X-RateLimit-Remaining': '0',
                },
            )

        response = await call_next(request)
        response.headers['X-RateLimit-Limit'] = str(limiter.max)
        response.headers['X-RateLimit-Remaining'] = str(remaining)
        return response


async def _extract_user_id(request: Request) -> int | None:
    """Extract user_id from session token (without full session resolution)."""
    token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if not token:
        token = request.cookies.get('session')
    if not token:
        return None
    try:
        session_data = await _get_redis().get(f'session:{token}')
        if session_data:
            try:
                uid = (_json.loads(session_data) or {}).get('user_id')
                if uid:
                    return int(uid)
            except (ValueError, AttributeError):
                return int(session_data)
    except Exception:
        pass
    return None


async def _get_user_plan(uid: int) -> str:
    """Lazy-import _get_user_plan from chat module to avoid circular imports."""
    from chat import _get_user_plan as _gup
    return await _gup(uid)


# ── Session Security ────────────────────────────────────────

MAX_CONCURRENT_SESSIONS = 3


async def track_session(token: str, user_id: int, request: Request) -> None:
    """Track session metadata and enforce concurrent session limit.

    Stores session metadata (IP, user-agent, created_at) in Redis.
    If user exceeds MAX_CONCURRENT_SESSIONS, revokes the oldest session.
    """
    try:
        metadata = {
            'user_id': user_id,
            'ip': get_real_ip(request),
            'user_agent': request.headers.get('user-agent', '')[:200],
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'last_seen': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }
        session_key = f'session_meta:{token}'
        await _get_redis().setex(session_key, 86400 * 7, _json.dumps(metadata))

        # Track active sessions per user for concurrent limit
        user_sessions_key = f'active_sessions:{user_id}'
        await _get_redis().sadd(user_sessions_key, token)
        await _get_redis().expire(user_sessions_key, 86400 * 7)

        # Enforce concurrent session limit
        members = await _get_redis().smembers(user_sessions_key)
        if members and len(members) > MAX_CONCURRENT_SESSIONS:
            # Find oldest session to revoke
            oldest_token = None
            oldest_time = None
            for tok in members:
                meta_raw = await _get_redis().get(f'session_meta:{tok}')
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
    """Revoke a single session and clean up tracking data."""
    try:
        await _get_redis().delete(f'session:{token}', f'session_meta:{token}')
        await _get_redis().srem(f'active_sessions:{user_id}', token)
    except Exception:
        pass


async def update_session_last_seen(token: str) -> None:
    """Update the last_seen timestamp for a session."""
    try:
        meta_raw = await _get_redis().get(f'session_meta:{token}')
        if meta_raw:
            meta = _json.loads(meta_raw)
            meta['last_seen'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            await _get_redis().setex(f'session_meta:{token}', 86400 * 7, _json.dumps(meta))
    except Exception:
        pass


async def get_session_info(token: str) -> dict | None:
    """Get session metadata (IP, user-agent, timestamps)."""
    try:
        meta_raw = await _get_redis().get(f'session_meta:{token}')
        if meta_raw:
            return _json.loads(meta_raw)
    except Exception:
        pass
    return None


# ── Security Headers ───────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security-related HTTP headers to all responses"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'X-DNS-Prefetch-Control': 'off',
            'Content-Security-Policy': (
                "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
                "connect-src 'self' wss: https:;"
            ),
        }

        for key, value in headers.items():
            if key not in response.headers:
                response.headers[key] = value

        return response


# ── Input Validation ───────────────────────────────────────

MAX_PAYLOAD_SIZE = 1024 * 1024  # 1MB
MAX_MESSAGE_LENGTH = 32000       # 32K chars
MAX_EMAIL_LENGTH = 254
MAX_PASSWORD_LENGTH = 128
BANNED_EMAIL_DOMAINS = {'mailinator.com', 'guerrillamail.com', '10minutemail.com', 'tempmail.com'}


# ── CSRF Defense-in-Depth ─────────────────────────────────

# Paths that are cookie-authenticated user mutation endpoints.
# Admin endpoints already have their own CSRF token system.
_CSRF_PROTECTED_PREFIXES = ('/auth/', '/api-keys', '/referral/', '/v1/rag/')
_SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')


class CsrfMiddleware(BaseHTTPMiddleware):
    """Require a custom header on cookie-authenticated mutation requests.

    Cross-origin forms cannot set custom headers, so requiring
    X-Requested-With prevents CSRF even if SameSite is bypassed.
    Only applies to paths that use session cookies for auth.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        path = request.url.path
        if not any(path.startswith(p) for p in _CSRF_PROTECTED_PREFIXES):
            return await call_next(request)

        # If no session cookie present, skip (API key auth doesn't need CSRF)
        session_cookie = request.cookies.get('session')
        if not session_cookie:
            return await call_next(request)

        # Require custom header for cookie-authenticated mutations
        xrw = request.headers.get('x-requested-with', '')
        if not xrw:
            return JSONResponse(
                {'detail': 'هدر X-Requested-With ارسال نشده (محافظت CSRF)'},
                status_code=403,
            )

        return await call_next(request)


def validate_email(email: str) -> tuple[bool, str]:
    """Validate email format and domain"""
    if not email or len(email) > MAX_EMAIL_LENGTH:
        return False, 'ایمیل بیش از حد طولانی است'
    if '@' not in email or '.' not in email.split('@')[-1]:
        return False, 'فرمت ایمیل نامعتبر است'
    domain = email.split('@')[-1].lower()
    if domain in BANNED_EMAIL_DOMAINS:
        return False, 'استفاده از ایمیل موقت مجاز نیست'
    return True, ''


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength with complexity requirements."""
    if len(password) < 8:
        return False, 'رمز عبور باید حداقل ۸ کاراکتر باشد'
    if len(password) > MAX_PASSWORD_LENGTH:
        return False, 'رمز عبور بیش از حد طولانی است'
    if not any(c.isdigit() for c in password):
        return False, 'رمز عبور باید حداقل شامل یک عدد باشد'
    if not any(c.isalpha() for c in password):
        return False, 'رمز عبور باید حداقل شامل یک حرف باشد'
    return True, ''


def sanitize_input(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """Truncate and strip input"""
    if not text:
        return ''
    return text.strip()[:max_length]
