"""
Security middleware: rate limiting, security headers, input validation.
All rate limits use Redis for persistence across restarts.
"""
import logging
import time
import hashlib
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# ── Lazy Redis import (avoids circular import) ────────────

_rds = None

def _get_redis():
    global _rds
    if _rds is None:
        from app import rds as _redis
        _rds = _redis
    return _rds

# ── Rate Limiting ──────────────────────────────────────────

class RateLimiter:
    """Sliding window rate limiter using Redis"""

    def __init__(self, window_seconds: int = 60, max_requests: int = 30):
        self.window = window_seconds
        self.max = max_requests

    def _key(self, identifier: str) -> str:
        now = int(time.time() / self.window)
        return f'ratelimit:{identifier}:{now}'

    def is_allowed(self, identifier: str) -> tuple[bool, int]:
        """Returns (allowed, remaining)"""
        key = self._key(identifier)
        try:
            count = _get_redis().incr(key)
            if count == 1:
                _get_redis().expire(key, self.window * 2)
            remaining = max(0, self.max - count)
            return count <= self.max, remaining
        except Exception as e:
            logger.warning("Rate limiter Redis unavailable, failing closed: %s", e)
            return False, 0  # Fail closed: deny traffic when Redis is down


# Different rate limits for different endpoint types
general_limiter = RateLimiter(window_seconds=60, max_requests=60)     # 60 req/min
auth_limiter = RateLimiter(window_seconds=60, max_requests=10)       # 10 req/min
chat_limiter = RateLimiter(window_seconds=60, max_requests=120)      # 120 req/min (streaming needs headroom)
admin_limiter = RateLimiter(window_seconds=60, max_requests=30)      # 30 req/min


def get_client_identifier(request: Request) -> str:
    """Get unique client identifier: prefer user_id, fallback to IP"""
    # Try auth token first
    token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if token:
        try:
            import json as _json
            session_data = _get_redis().get(f'session:{token}')
            if session_data:
                try:
                    uid = (_json.loads(session_data) or {}).get('user_id')
                    if uid:
                        return f'user:{uid}'
                except (ValueError, AttributeError):
                    return f'user:{session_data}'
        except Exception:
            pass
    # Fallback to IP + User-Agent hash
    ip = request.headers.get('x-forwarded-for', request.client.host if request.client else 'unknown')
    ua = request.headers.get('user-agent', '')
    return f'ip:{hashlib.sha256(f"{ip}:{ua}".encode()).hexdigest()[:12]}'


def select_limiter(path: str) -> RateLimiter:
    """Choose appropriate rate limiter based on path"""
    if path.startswith('/auth/'):
        return auth_limiter
    if path.startswith('/v1/chat/'):
        return chat_limiter
    if path.startswith('/admin/'):
        return admin_limiter
    return general_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for FastAPI"""

    async def dispatch(self, request: Request, call_next):
        # Skip health check and static
        if request.url.path in ['/health', '/health/live', '/health/ready', '/health/detailed', '/']:
            return await call_next(request)

        identifier = get_client_identifier(request)
        limiter = select_limiter(request.url.path)
        allowed, remaining = limiter.is_allowed(identifier)

        if not allowed:
            return JSONResponse(
                {'detail': 'rate limit exceeded. try again later.', 'retry_after': limiter.window},
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
_CSRF_PROTECTED_PREFIXES = ('/auth/', '/api-keys', '/referral/')
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
                {'detail': 'missing X-Requested-With header (CSRF protection)'},
                status_code=403,
            )

        return await call_next(request)


def validate_email(email: str) -> tuple[bool, str]:
    """Validate email format and domain"""
    if not email or len(email) > MAX_EMAIL_LENGTH:
        return False, 'email too long'
    if '@' not in email or '.' not in email.split('@')[-1]:
        return False, 'invalid email format'
    domain = email.split('@')[-1].lower()
    if domain in BANNED_EMAIL_DOMAINS:
        return False, 'disposable email not allowed'
    return True, ''


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength with complexity requirements."""
    if len(password) < 8:
        return False, 'password must be at least 8 characters'
    if len(password) > MAX_PASSWORD_LENGTH:
        return False, 'password too long'
    if not any(c.isdigit() for c in password):
        return False, 'password must contain at least one digit'
    if not any(c.isalpha() for c in password):
        return False, 'password must contain at least one letter'
    return True, ''


def sanitize_input(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """Truncate and strip input"""
    if not text:
        return ''
    return text.strip()[:max_length]