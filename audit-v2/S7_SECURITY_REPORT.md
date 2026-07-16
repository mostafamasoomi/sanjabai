# S7: Security & Abuse Prevention Report

**Audit Date:** 2026-07-16
**Scope:** Backend security.py, auth.py, dependencies.py, chat.py, frontend token handling
**Severity Scale:** CRITICAL > HIGH > MEDIUM > LOW > INFO

---

## Executive Summary

The codebase demonstrates a **mature security posture** for its size. Core protections (server-side sessions, CSRF defense-in-depth, rate limiting with fail-closed Redis, password hashing with PBKDF2+salt, API key hashing with pepper) are correctly implemented. No CRITICAL or HIGH vulnerabilities were found. The remaining findings are MEDIUM/LOW items that harden the posture further.

---

## Findings

### M-1: Chat `model` parameter not validated against whitelist [MEDIUM]

**Location:** `chat.py:68-70`, `chat.py:245`

**Description:** The `model` field from `ChatRequest` is passed directly to LiteLLM without validation against `model_catalog`. An authenticated user could send an arbitrary model ID (e.g., `gpt-4-turbo`, `claude-3-opus`) that LiteLLM may proxy to expensive upstream providers, bypassing the per-model pricing in `model_catalog`.

**Impact:** Billing bypass — user gets access to premium models at the cheapest-tier fallback rate (`total_tokens // 1000`), or triggers unexpected upstream costs.

**Evidence:**
```python
# chat.py:245 — model is user-controlled, no whitelist check
payload['model'] = selected_model  # from ChatRequest, user-supplied
r = await _http.post(f"{LITELLM_HOST}/v1/chat/completions", json=payload, ...)
```

**Fix:** Validate `model` against `model_catalog.provider_model_id WHERE availability='available'` before forwarding. Reject unknown models with 400.

---

### M-2: No per-user token-based rate limiting [MEDIUM]

**Location:** `security.py:85-88`

**Description:** `chat_limiter` is set to 120 req/min globally per user (identified by session token or IP). There is no tiered limiting — free and paid users share the same limit. More importantly, the limiter is per-identifier, not per-endpoint-weight. A user could send 120 lightweight chat requests in 1 minute without proportional cost, exhausting downstream capacity.

**Impact:** Resource exhaustion; disproportionate usage by free-tier users.

**Fix:** Add tiered limits: free = 30/min, pro = 120/min, enterprise = 300/min. Base tier on user plan (available via `_get_user_plan()`).

---

### M-3: Rate limiter uses fixed-window, not true sliding window [MEDIUM]

**Location:** `security.py:28-39`

**Description:** Despite the docstring saying "sliding window," the implementation is a fixed-window counter: `now = int(time.time() / self.window)` creates discrete 60-second buckets. A user can send 120 requests at 0:00:59 and 120 more at 0:01:00 — 240 requests in ~2 seconds. The `expire = window * 2` mitigates slightly but doesn't fix the boundary burst.

**Impact:** Burst abuse at window boundaries.

**Fix:** Use Redis sorted sets (ZREMRANGEBYSCORE + ZCARD) for true sliding window, or use `INCR` with a sliding-window log.

---

### M-4: X-Forwarded-For spoofable for rate limiter identification [MEDIUM]

**Location:** `security.py:82`

**Description:** `get_client_identifier()` falls back to IP identification using `x-forwarded-for` header. Without a trusted reverse proxy that overwrites this header, an attacker can rotate `X-Forwarded-For` values to bypass IP-based rate limiting entirely.

**Impact:** Complete rate limit bypass for unauthenticated requests.

**Fix:** Only trust `X-Forwarded-For` from known proxy IPs, or strip it at the edge proxy (Nginx/Caddy) and use `request.client.host` directly.

---

### L-1: No CSRF protection on `/v1/chat/*` endpoints [LOW]

**Location:** `security.py:169-171`

**Description:** `_CSRF_PROTECTED_PREFIXES` covers `/auth/`, `/api-keys`, `/referral/` but NOT `/v1/chat/`. Chat endpoints use API key / session auth. While API key auth doesn't need CSRF (it's a header), session-cookie-authenticated chat requests could be CSRF-attacked if a user visits a malicious page. However, SameSite=Lax on the session cookie provides strong CSRF protection for POST requests, so this is LOW risk.

**Impact:** Minimal due to SameSite=Lax; only exploitable if SameSite is bypassed (subdomain XSS).

**Fix:** Add `/v1/chat/` to `_CSRF_PROTECTED_PREFIXES`, or document why it's excluded.

---

### L-2: CSP allows 'unsafe-inline' and 'unsafe-eval' [LOW]

**Location:** `security.py:205-207`

**Description:** Content-Security-Policy includes `'unsafe-inline'` and `'unsafe-eval'` for scripts, significantly weakening XSS protection.

**Fix:** Migrate to nonce-based CSP. Most Next.js setups support this via `next.config.js` headers.

---

### L-3: WebSocket auth via query param (deprecated, still present) [LOW]

**Location:** `websocket.py:30`

**Description:** The websocket module logs a deprecation warning for query-param auth but the code path still exists. Query-param tokens appear in server logs, browser history, and Referer headers.

**Fix:** Remove the query-param auth path entirely. Only accept session cookie or Authorization header.

---

### L-4: No token-based API key rate limiting [LOW]

**Location:** `security.py:85-88`

**Description:** When rate limiting falls back to IP (no session token), API key requests are grouped by IP hash. Multiple API keys from the same IP share a single rate limit bucket, causing false positives. Conversely, API keys used behind NAT share limits.

**Fix:** Use the API key hash as a rate limit identifier when present (API key auth should bypass session lookup).

---

### L-5: Session token exposed in smart-chat response headers [LOW]

**Location:** `chat.py:370-373`

**Description:** `X-Smart-Model`, `X-Smart-Category`, `X-Smart-Provider` headers leak internal routing decisions to the client. While not a direct vulnerability, an attacker can use these to fingerprint model selection logic and optimize abuse.

**Fix:** Remove these headers in production, or gate behind an admin/debug flag.

---

### I-1: Frontend — no localStorage token storage detected [INFO, POSITIVE]

The frontend source (`/root/multiai/frontend/src/`) contains **zero** references to `localStorage`, `sessionStorage`, `innerHTML`, `dangerouslySetInnerHTML`, or `eval()`. Authentication appears to be entirely cookie-based (httponly, secure, SameSite=Lax), which is the correct pattern. No XSS vectors via client-side token storage.

---

### I-2: Password hashing — PBKDF2 with proper salt [INFO, POSITIVE]

`_hash_password()` uses `pbkdf2_hmac('sha256', ..., 100000)` with a random 16-byte hex salt. `_verify_password()` uses `hmac.compare_digest()` for constant-time comparison. This is solid.

---

### I-3: API key hashing with server-side pepper [INFO, POSITIVE]

`_hash_api_key()` applies `sha256(PEPPER + raw_key)` with a startup-enforced pepper from env. Keys are never stored in plaintext. Revocation is supported via `revoked_at` and `expires_at` checks.

---

### I-4: Admin CSRF protection [INFO, POSITIVE]

Admin endpoints have dual protection: (1) `CsrfMiddleware` requires `X-Requested-With` header for cookie-authenticated mutations, and (2) admin session includes a separate CSRF token validated via `x-csrf-token` header.

---

### I-5: Rate limiter fails closed on Redis outage [INFO, POSITIVE]

```python
except Exception as e:
    logger.warning("Rate limiter Redis unavailable, failing closed: %s", e)
    return False, 0  # Fail closed: deny traffic when Redis is down
```

Correctly denies all traffic when Redis is unavailable, preventing unlimited abuse during outages.

---

### I-6: Input validation and banned domains [INFO, POSITIVE]

`validate_email()` blocks disposable email domains. `validate_password()` enforces 8+ chars with alpha+digit. `sanitize_input()` truncates to 32K chars. `MAX_FILE_SIZE` caps uploads at 10MB.

---

## Summary Table

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| M-1 | MEDIUM | Model param not whitelisted | Open |
| M-2 | MEDIUM | No tiered rate limits | Open |
| M-3 | MEDIUM | Fixed-window (not sliding) rate limiter | Open |
| M-4 | MEDIUM | X-Forwarded-For spoofable | Open |
| L-1 | LOW | No CSRF on chat endpoints | Low risk (SameSite=Lax) |
| L-2 | LOW | CSP unsafe-inline/eval | Open |
| L-3 | LOW | WS auth via query param | Open |
| L-4 | LOW | No per-API-key rate limiting | Open |
| L-5 | LOW | Internal routing headers leaked | Open |

---

## Recommendations (Priority Order)

1. **[M-1] Validate model against whitelist** — highest impact, simplest fix
2. **[M-3] Implement true sliding window** — fixes boundary burst abuse
3. **[M-4] Strip/validate X-Forwarded-For at proxy** — infrastructure change
4. **[M-2] Add tiered rate limits** — requires plan lookup integration
5. **[L-1] Add chat to CSRF prefixes** — one-line fix
6. **[L-2] Nonce-based CSP** — requires build pipeline changes
7. **[L-3] Remove WS query param auth** — deprecation cleanup
