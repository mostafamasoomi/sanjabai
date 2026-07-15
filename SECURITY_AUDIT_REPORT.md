# 🔒 Multiai Security Audit Report

**Audit Date:** 2026-07-15  
**Auditor:** Hermes Agent (Automated Security Review)  
**Scope:** `/root/multiai/backend/app.py` (~5,325 lines, ~114 endpoints), `security.py`, `docker-compose.multiai.yml`, `.env.example`, frontend source  
**Application:** Persian AI Gateway — FastAPI backend with Next.js frontend, LiteLLM proxy, PostgreSQL, Redis  

---

## Executive Summary

The Multiai project demonstrates **above-average security awareness** for a self-hosted AI gateway. It uses server-side sessions with Redis, PBKDF2 password hashing, CSRF protection, rate limiting, audit logging, and parameterized SQL queries. However, several **High and Critical severity issues** were identified, primarily around broken access control in one endpoint, an effectively disabled rate limiter on chat endpoints, and information leakage through error messages.

| Severity | Count |
|----------|-------|
| 🔴 Critical | 2 |
| 🟠 High | 5 |
| 🟡 Medium | 8 |
| 🔵 Low | 6 |
| ⚪ Info | 5 |

---

## 🔴 Critical Findings

### C-1: Missing `await` on `admin_required()` — Broken Access Control on Skill Templates

**Location:** `app.py:2827`  
**Line:**
```python
if not uid or (data.get('user_id') != uid and not admin_required(request)):
```

**Issue:** `admin_required()` is an `async` function. Calling it without `await` returns a **coroutine object**, which is always truthy in Python. This means `not admin_required(request)` is **always `False`**, so the admin fallback check **never executes**. Non-public skill templates are only protected by the `user_id` check, meaning an admin cannot actually access other users' private templates through this path — but the intent is broken and the code is misleading. If the `user_id` check were ever weakened, this would become a direct access control bypass.

**Impact:** Non-public skill templates may be incorrectly accessible or denied. The intended admin bypass does not work.

**Recommendation:** Add `await`:
```python
if not uid or (data.get('user_id') != uid and not await admin_required(request)):
```

---

### C-2: Chat Rate Limiter Set to 9,999 — Effectively Disabled

**Location:** `security.py:58`  
**Line:**
```python
chat_limiter = RateLimiter(window_seconds=60, max_requests=9999)  # 120 req/min (streaming needs headroom)
```

**Issue:** The comment says "120 req/min" but the actual limit is **9,999 requests per minute**. This effectively disables rate limiting on all `/v1/chat/*` endpoints (`/v1/chat/completions`, `/v1/chat/with-file`, `/v1/smart-chat`). An attacker can flood the backend with unlimited LLM requests, causing:

- **Financial abuse**: Unlimited token consumption charged to any authenticated user's wallet
- **Resource exhaustion**: Overwhelming the LiteLLM proxy and upstream providers
- **Denial of service**: Starving other users of compute resources

**Impact:** Unlimited abuse of paid AI resources, potential financial loss.

**Recommendation:** Set to a realistic value:
```python
chat_limiter = RateLimiter(window_seconds=60, max_requests=120)
```
Consider implementing per-user token quotas with tighter enforcement.

---

## 🟠 High Findings

### H-1: Race Condition in Conversation Update — TOCTOU Vulnerability

**Location:** `app.py:2511-2526`

**Issue:** The ownership check and the update are separate operations:
```python
# Step 1: Check ownership (line 2511)
res = await session.execute(
    Conversation.__table__.select().where(Conversation.id == conv_id, Conversation.user_id == uid)
)
conv = res.fetchone()
if not conv:
    return JSONResponse(...)

# Step 2: Update WITHOUT user_id filter (line 2522)
await session.execute(
    Conversation.__table__.update().where(Conversation.id == conv_id),  # Missing user_id!
    update_data
)
```

Between Step 1 and Step 2, if the conversation's `user_id` were changed (e.g., via an admin action or race), the update would succeed on a conversation the user no longer owns.

**Impact:** Potential IDOR via race condition in conversation updates.

**Recommendation:** Include `user_id` in the UPDATE WHERE clause:
```python
await session.execute(
    Conversation.__table__.update().where(Conversation.id == conv_id, Conversation.user_id == uid),
    update_data
)
```

---

### H-2: Rate Limiter Session Invalidation — Substring Match Bug

**Location:** `app.py:3175-3181`

**Issue:** When banning a user, the session invalidation code uses substring matching:
```python
keys = await rds.keys('session:*')
for key in keys:
    val = await rds.get(key)
    if val and str(uid) in val:  # BUG: substring match!
        await rds.delete(key)
```

If `uid=1`, this will also match sessions for `uid=11`, `uid=121`, `uid=1001`, etc., **invalidating innocent users' sessions**. Additionally, `rds.keys('session:*')` scans the entire Redis keyspace, which is O(N) and can block Redis in production.

**Impact:** Banning user ID 1 could log out users 10, 11, 121, etc. Performance degradation on large user bases.

**Recommendation:**
```python
# Use the session set index instead of scanning all keys
tokens = await rds.smembers(f'sessions:{uid}')
for token in tokens:
    await rds.delete(f'session:{token}')
await rds.delete(f'sessions:{uid}')
```

---

### H-3: Stream Error Leaks Internal Exception Details

**Location:** `app.py:5125` and `app.py:1157`

**Issue:** Exception details are sent directly to the client:
```python
yield f'data: {{"error": "upstream unavailable: {e}"}}\n\n'  # Line 5125
```

This can leak internal hostnames, port numbers, connection strings, and stack traces to attackers.

**Impact:** Information disclosure of internal infrastructure details.

**Recommendation:** Return generic error messages:
```python
yield f'data: {{"error": "Service temporarily unavailable", "code": "gateway_error"}}\n\n'
```
Log the actual exception server-side for debugging.

---

### H-4: Inconsistent Auth Token Key in Frontend — Token Confusion

**Location:** `frontend/lib/auth.tsx` vs `frontend/app/*/page.tsx`

**Issue:** The auth library stores the token under `'multiai_auth_token'` (line 28), but multiple pages read it from `'auth_token'` (lines 73, 123, 165, 195 in `memory/page.tsx`; line 39 in `profile/page.tsx`; line 38 in `Playground.tsx`). This means:

- Some pages may send `null` as the auth token, causing "unauthorized" errors
- Users may appear logged out on some pages while logged in on others
- If both keys exist (from a migration), stale tokens may be used

**Impact:** Authentication inconsistency; some API calls may fail silently or use stale tokens.

**Recommendation:** Standardize on a single token key across all frontend code.

---

### H-5: WebSocket Auth via Query Parameter — Token Exposure

**Location:** `app.py:5269`

**Issue:** The WebSocket endpoint accepts authentication tokens via query parameter:
```python
token = ws.query_params.get('token', '')
```

Query parameters are logged in server access logs, proxy logs, CDN logs, browser history, and Referer headers. The code even acknowledges this with a deprecation warning, but still accepts it.

**Impact:** Session tokens may be leaked through logs and browser history.

**Recommendation:** Remove query param auth entirely. Use the first-message auth pattern exclusively (already implemented as fallback).

---

## 🟡 Medium Findings

### M-1: SSRF Protection Incomplete for Proxy Configuration

**Location:** `app.py:1529-1535`

**Issue:** The internal address blocklist is incomplete:
```python
if hostname in ('localhost', '127.0.0.1', '0.0.0.0', '::1') or \
   hostname.startswith('10.') or hostname.startswith('192.168.') or \
   hostname.startswith('172.'):
```

**Missing:**
- `169.254.0.0/16` (link-local / cloud metadata at 169.254.169.254)
- `fd00::/8` (IPv6 private addresses)
- DNS rebinding (hostname resolves to internal IP after validation)
- `172.` prefix blocks all 172.0.0.0/8, not just 172.16.0.0/12

**Impact:** Potential SSRF to cloud metadata services (AWS, GCP, Azure) via link-local addresses.

**Recommendation:** Use `ipaddress` module for proper CIDR checks:
```python
import ipaddress
ip = ipaddress.ip_address(hostname)
if ip.is_private or ip.is_loopback or ip.is_link_local:
    return JSONResponse(...)
```

---

### M-2: Admin Endpoints Accept Raw `request.json()` Without Validation

**Location:** `app.py:4139`, `app.py:4219`

**Issue:** Admin plan and credit package creation endpoints parse JSON directly:
```python
payload = await request.json()
```

This bypasses Pydantic validation, allowing arbitrary JSON structures. Combined with the dynamic SQL building (though field names are from an allowlist), this increases the attack surface.

**Impact:** Unvalidated input on admin endpoints; potential for unexpected behavior.

**Recommendation:** Use Pydantic models for all request bodies.

---

### M-3: CORS Allows `localhost` in Default Configuration

**Location:** `app.py:458`

**Issue:**
```python
allow_origins=os.getenv('CORS_ORIGINS', 'https://multiai.ir,http://localhost:3003').split(','),
```

If `CORS_ORIGINS` is not explicitly set in production, `http://localhost:3003` is allowed. Combined with `allow_credentials=False`, this is low risk, but indicates a development default leaking into production.

**Impact:** Limited — credentials are not sent. But any localhost-based attacker (browser extension, malware) could make cross-origin requests.

**Recommendation:** Ensure `CORS_ORIGINS` is explicitly set in production `.env`. Consider removing the localhost default entirely.

---

### M-4: CSP Allows `unsafe-inline` and `unsafe-eval`

**Location:** `security.py:148`

**Issue:**
```python
'Content-Security-Policy': (
    "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
    "connect-src 'self' wss: https:;"
),
```

`unsafe-inline` and `unsafe-eval` in `script-src` largely negate CSP's XSS protection. An attacker who achieves XSS can execute arbitrary JavaScript.

**Impact:** CSP provides minimal protection against XSS.

**Recommendation:** Use nonce-based CSP or move all inline scripts to external files.

---

### M-5: Redis Deployed Without Authentication

**Location:** `docker-compose.multiai.yml:19-31`

**Issue:** Redis is configured without a password:
```yaml
command: ["redis-server", "--save", "60", "--appendonly", "yes"]
```

While Redis is on an internal Docker network, if any container is compromised, the attacker has unrestricted access to all session data, rate limit counters, admin sessions, and CSRF tokens.

**Impact:** Full session hijacking if network is breached.

**Recommendation:** Add Redis authentication:
```yaml
command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}", ...]
```

---

### M-6: PostgreSQL Uses Weak Default Password

**Location:** `docker-compose.multiai.yml:8`

**Issue:**
```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-multiai}
```

The default password `multiai` is trivially guessable. If `.env` is not properly configured, the database is accessible with known credentials.

**Impact:** Database compromise if defaults are used.

**Recommendation:** Remove the default fallback and fail if not set:
```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}
```

---

### M-7: Silent Exception Swallowing Masks Security Issues

**Location:** Throughout `app.py` (20+ occurrences)

**Issue:** Many critical code paths silently swallow exceptions:
```python
except Exception:
    pass  # fail-open
```

Examples:
- `_check_quota_pre` (line 870): Quota check failure allows unlimited requests
- `_track_usage` (line 1257): Billing failures go unnoticed
- `_record_usage` (line 1241): Metering data silently lost
- Session invalidation on ban (line 3182): Failed invalidation not reported

**Impact:** Security controls fail silently; billing discrepancies; inability to detect attacks.

**Recommendation:** At minimum, log all swallowed exceptions. For critical paths (billing, quota), fail closed rather than open.

---

### M-8: Hardcoded Internal Network Topology in Docker Compose

**Location:** `docker-compose.multiai.yml:45-46`

**Issue:**
```yaml
HTTP_PROXY: http://10.10.11.2:8888
HTTPS_PROXY: http://10.10.11.2:8888
```

Internal proxy IP addresses are hardcoded in the compose file. If this file is committed to a public repository, it exposes the internal network topology.

**Impact:** Information disclosure of internal infrastructure.

**Recommendation:** Move proxy URLs to `.env` file.

---

## 🔵 Low Findings

### L-1: Password Reset Flow Non-Functional

**Location:** `app.py:2205-2210`

**Issue:** The forgot-password endpoint generates a reset token but never sends it:
```python
# In production, send email here
_logging.getLogger(__name__).warning('Password reset token generated for user %s (email delivery not configured)', user.id)
```

Users who forget their password have no recovery path.

**Impact:** Users permanently locked out if they forget their password.

**Recommendation:** Implement email delivery or remove the endpoint.

---

### L-2: `X-XSS-Protection` Header is Deprecated

**Location:** `security.py:142`

**Issue:** `X-XSS-Protection: 1; mode=block` is deprecated and can actually introduce vulnerabilities in some browsers. Modern browsers have removed XSS auditors entirely.

**Impact:** Minimal — may cause issues in older browsers.

**Recommendation:** Remove the header or set to `0` and rely on CSP instead.

---

### L-3: No Account Lockout After Failed Login Attempts

**Location:** `app.py:2016-2032`

**Issue:** The login endpoint rate-limits at 30 req/min but does not lock accounts after repeated failures. An attacker can brute-force passwords at ~30 attempts/minute indefinitely.

**Impact:** Slow brute-force attack possible.

**Recommendation:** Implement progressive account lockout (e.g., lock for 15 minutes after 5 failed attempts).

---

### L-4: API Key Hash Uses SHA-256 (Fast Hash)

**Location:** `app.py:1832-1834`

**Issue:**
```python
def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(API_KEY_PEPPER + raw_key.encode()).hexdigest()
```

SHA-256 is a fast hash. If the database is compromised, API keys can be brute-forced quickly (especially since they follow a predictable `sk-` prefix pattern).

**Impact:** API key recovery from database breach.

**Recommendation:** Use a slow hash like PBKDF2 or Argon2 for API key storage, similar to password hashing.

---

### L-5: Session Token Returned in Response Body

**Location:** `app.py:2011`, `app.py:2029`

**Issue:**
```python
return JSONResponse({'token': token, 'user': {'id': user.id, 'email': user.email}})
```

The session token is returned in the JSON response body. While needed for SPA architecture, it means the token exists in browser memory, network traces, and potentially logging middleware.

**Impact:** Token exposure in non-cookie contexts.

**Recommendation:** Document this as an accepted risk. Consider using HTTP-only cookies exclusively and removing token from response body.

---

### L-6: `INTERNAL_TOKEN` Not Validated at Startup

**Location:** `app.py:2264`

**Issue:**
```python
INTERNAL_TOKEN = os.getenv('INTERNAL_TOKEN', '')
```

Unlike `ADMIN_TOKEN` and `API_KEY_PEPPER`, `INTERNAL_TOKEN` defaults to empty string without raising an error. If not configured, the telegram-token endpoint is effectively disabled (returns 401), which is fail-closed — but there's no startup warning.

**Impact:** Silent misconfiguration possible.

**Recommendation:** Either require it at startup (like ADMIN_TOKEN) or log a warning.

---

## ⚪ Informational Findings

### I-1: Strong Security Foundations

The project demonstrates good security practices:
- ✅ Server-side sessions with Redis (not JWT in localStorage for backend)
- ✅ PBKDF2 with 100,000 iterations for password hashing
- ✅ Constant-time comparison (`hmac.compare_digest`) for tokens
- ✅ CSRF protection via custom header requirement
- ✅ Security headers middleware (HSTS, X-Frame-Options, etc.)
- ✅ Audit logging for admin actions
- ✅ Session rotation on password change
- ✅ Parameterized SQL queries (SQLAlchemy ORM + `sqlalchemy.text()` with `:param` bindings)
- ✅ API keys hashed at rest with server-side pepper
- ✅ API key secret shown only once at creation
- ✅ `HttpOnly` and `Secure` flags on session cookies
- ✅ `SameSite=Lax` on cookies
- ✅ Admin session isolated from user sessions
- ✅ Admin CSRF token system
- ✅ Rate limiting with Redis-backed sliding window
- ✅ File upload size limits (10MB hard cap)
- ✅ PDF page limits (100 pages max)
- ✅ Docker container runs as non-root user (`appuser`)
- ✅ Docker containers have memory limits
- ✅ Backend port bound to `127.0.0.1` (not `0.0.0.0`)
- ✅ `API_KEY_PEPPER` required at startup (refuses to start without it)
- ✅ `ADMIN_TOKEN` required at startup (refuses to start without it)
- ✅ OpenAPI/docs disabled in production

### I-2: SQL Injection Protection Status

**Assessment: LOW RISK** ✅

All database queries use one of:
1. SQLAlchemy ORM with parameterized column comparisons
2. `sqlalchemy.text()` with `:parameter` bindings

The dynamic SQL in admin plan/credit-package endpoints (`app.py:4157-4168`) uses field names from a hardcoded allowlist (`fields = ['name_fa', 'name_en', ...]`), not user input. The values use parameterized `:param` bindings. **No SQL injection vulnerabilities found.**

### I-3: XSS Prevention Status

**Assessment: LOW RISK** ✅

The backend returns JSON responses exclusively (no HTML rendering). XSS would need to occur in the frontend. The frontend uses React, which auto-escapes JSX output. No `dangerouslySetInnerHTML` or `innerHTML` usage was found in the frontend source.

### I-4: Environment Variable Handling

**Assessment: GOOD** ✅

- `.env` file is mounted read-only in Docker: `./.env:/app/.env:ro`
- `.env.example` has placeholder values, not real secrets
- Critical secrets (`ADMIN_TOKEN`, `API_KEY_PEPPER`) refuse to start if not set
- `BYNARA_API_KEY` uses Docker Compose validation: `${BYNARA_API_KEY:?must be set}`

### I-5: Dependency Security

**Assessment: NOT VERIFIED** ⚠️

The `requirements.txt` was not available for review. Recommend running:
```bash
pip audit
safety check
```

---

## Summary of Recommendations (Priority Order)

| # | Severity | Finding | Fix Effort |
|---|----------|---------|------------|
| 1 | 🔴 Critical | C-2: Chat rate limiter at 9999 | 1 line change |
| 2 | 🔴 Critical | C-1: Missing `await` on `admin_required` | 1 line change |
| 3 | 🟠 High | H-1: TOCTOU in conversation update | 1 line change |
| 4 | 🟠 High | H-2: Ban session invalidation substring match | 5 line refactor |
| 5 | 🟠 High | H-3: Stream error info leakage | 1 line change |
| 6 | 🟠 High | H-4: Frontend inconsistent token keys | Find-replace |
| 7 | 🟠 High | H-5: WebSocket query param auth | Remove ~5 lines |
| 8 | 🟡 Medium | M-1: SSRF protection gaps | Add ipaddress checks |
| 9 | 🟡 Medium | M-2: Raw JSON parsing on admin endpoints | Add Pydantic models |
| 10 | 🟡 Medium | M-5: Redis without auth | Add requirepass |
| 11 | 🟡 Medium | M-6: Weak PostgreSQL default password | Remove default |
| 12 | 🟡 Medium | M-7: Silent exception swallowing | Add logging |

---

*This report was generated by automated static analysis. Manual penetration testing is recommended to validate findings and identify issues that static analysis cannot detect (e.g., business logic flaws, race conditions in production).*
