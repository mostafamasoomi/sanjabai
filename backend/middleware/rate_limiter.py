"""
Rate limiting middleware using Redis sliding window.
Applies to auth endpoints: /auth/login, /auth/signup.
5 attempts per 10 minutes per IP.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from fastapi import Request, JSONResponse, status, FastAPI
from database import rds, async_session

RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "5"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "600"))  # 10 minutes


async def rate_limiter_middleware(request: Request, call_next):
    """Skip rate limiter for admin routes and if Redis is not available."""
    if request.url.path.startswith("/admin"):
        return await call_next(request)
    if rds is None:
        return await call_next(request)

    ip = request.client.host if request.client else "unknown"
    key = f"rate_limit:{ip}:{request.url.path}"
    now = datetime.now(timezone.utc).timestamp()

    try:
        pipe = rds.pipeline()
        pipe.zadd(key, {f"{now}": now})
        pipe.zremrangebyscore(key, 0, now - RATE_LIMIT_WINDOW)
        pipe.zcard(key)
        pipe.expire(key, RATE_LIMIT_WINDOW)
        result = await pipe.execute()
        count = int(result[2])
    except Exception:
        # Redis failure -> allow through (fail open)
        return await call_next(request)

    if count > RATE_LIMIT_MAX:
        remaining = RATE_LIMIT_WINDOW - int(now - (await rds.get(key)))  # fallback
        return JSONResponse(
            {"detail": "تعداد درخواست‌ها از حد مجاز بیشتر است", "retry_after": 60},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": "60"},
        )

    return await call_next(request)


async def auth_login_rate(request: Request, call_next):
    """Specific limiter for login endpoint that also increments attempt count on failure."""
    if request.url.path == "/api/auth/login":
        ip = request.client.host if request.client else "unknown"
        key = f"login_attempt:{ip}"
        now = datetime.now(timezone.utc).timestamp()
        try:
            pipe = rds.pipeline()
            pipe.zadd(key, {f"{now}": now})
            pipe.zremrangebyscore(key, 0, now - 300)  # 5 minutes window
            pipe.zcard(key)
            pipe.expire(key, 300)
            result = await pipe.execute()
            if int(result[2]) > 3:
                return JSONResponse(
                    {"detail": "تلاش‌های-login بیش از حد است. دوباره بعداً سعی کنید"},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
        except Exception:
            pass
    return await call_next(request)


def setup_rate_limiting(app: FastAPI):
    """Attach rate limiting middleware to the app."""
    @app.middleware("http")
    async def rate_limit_http(request: Request):
        # Use the per-route login limiter first
        if request.url.path == "/api/auth/login":
            return await auth_login_rate(request, lambda: (None, None))  # placeholder
        # General rate limiting for signup and other sensitive endpoints
        if request.url.path in ("/api/auth/signup", "/api/auth/forgot-password"):
            return await rate_limiter_middleware(request, lambda: await call_next_dummy(request))
        return await call_next_dummy(request)


async def call_next_dummy(request: Request):
    from fastapi import Response
    return JSONResponse({"status": "ok"}, status=200)
