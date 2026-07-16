# Phase 1 Security Fix Report

**Date:** 2026-07-16
**Engineer:** Senior Security Engineer (Inspector Phase 1)
**File Modified:** `backend/security.py`

---

## 1. Tiered Rate Limits for Chat Endpoints

### Problem
The chat rate limiter was a flat 120 req/min for all users regardless of subscription plan. Free-tier users had the same throughput as Pro and Enterprise users.

### Fix
Replaced the single `chat_limiter` with three tiered limiters:

| Tier       | Limiter Variable           | Limit      |
|------------|----------------------------|------------|
| Free       | `chat_free_limiter`        | 30 req/min |
| Pro        | `chat_pro_limiter`         | 120 req/min|
| Enterprise | `chat_enterprise_limiter`  | 300 req/min|

### Implementation Details

- **`_extract_user_id(request)`** (new, line 173): Extracts user_id from the session token (Authorization header or `session` cookie) by querying Redis. Returns `None` for unauthenticated requests.

- **`_get_user_plan(uid)`** (new, line 195): Lazy-imports `_get_user_plan` from `chat` module to avoid circular imports. Falls back to `'free'` on any error (same behavior as in `chat.py`).

- **`RateLimitMiddleware.dispatch`** (modified, line 140-152): For paths starting with `/v1/chat/`, now resolves the user's plan and selects the appropriate tiered limiter. Unauthenticated requests default to the free tier.

- **`select_limiter`** (line 122-123): Default chat limiter updated to `chat_pro_limiter` (was `chat_limiter`). This is the fallback used when the dispatch path doesn't apply.

### Behavior
- Fail-closed: Redis unavailable → deny traffic (unchanged from original)
- `_get_user_plan` DB failure → defaults to `'free'` (safe fallback)
- Non-chat endpoints (auth, login, signup, admin) remain completely unchanged
- `_get_user_plan` only called for chat paths, minimizing overhead

---

## 2. X-Forwarded-For Validation

### Problem
`get_client_identifier()` blindly trusted the `X-Forwarded-For` header without verifying the request came from a trusted proxy. An attacker could spoof the header to bypass IP-based rate limits or poison rate limit counters.

### Fix

- **`TRUSTED_PROXY_IPS`** (new, line 90-92): Set of trusted proxy IPs parsed from the `TRUSTED_PROXY_IPS` environment variable (comma-separated). Empty by default, meaning XFF is never trusted unless explicitly configured.

- **`get_real_ip(request)`** (new, line 95-109): Only trusts `X-Forwarded-For` when:
  1. `TRUSTED_PROXY_IPS` is non-empty (explicitly configured), AND
  2. The direct connecting IP (`request.client.host`) is in the trusted set
  
  When trusted, returns the leftmost IP from the XFF chain (original client). Otherwise falls back to `request.client.host`.

- **`get_client_identifier`** (modified, line 83): Replaced raw `request.headers.get('x-forwarded-for', ...)` with `get_real_ip(request)`.

### Configuration
```bash
# In .env or environment:
TRUSTED_PROXY_IPS=10.0.0.1,10.0.0.2,172.16.0.1
```

---

## 3. Verification

```
$ python3 -m py_compile backend/security.py
(exit 0, no errors)
```

---

## 4. Non-Regression Notes

- Auth/signup/login/forgot-password/admin limiters are completely untouched
- `_get_user_plan` lazy import from `chat` module avoids any circular import risk
- `select_limiter` still returns `chat_pro_limiter` as default for chat — the tier override happens in the dispatch method
- The `get_client_identifier` token-based user resolution path is unchanged
- All existing security headers, CSRF middleware, input validation, and password validation remain intact
- Model whitelist (`_is_model_allowed` / `_WORKING_SET`) is already done in `chat.py` — not duplicated