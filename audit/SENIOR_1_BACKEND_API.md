# SENIOR 1 — Backend API Endpoints Deep Audit

**Auditor:** Senior Backend Engineer  
**Date:** 2026-07-14  
**File:** `/root/multiai/backend/app.py` (5140 lines, ~217KB)  
**Supporting:** `/root/multiai/backend/security.py` (224 lines)

---

## Executive Summary

The backend is a **monolithic FastAPI application** (~5140 lines) serving as an API gateway for a multi-model LLM platform. It uses SQLAlchemy async ORM with PostgreSQL, Redis for sessions/rate-limiting, and proxies to LiteLLM for model inference.

**Overall Assessment:** The codebase demonstrates solid security fundamentals (session-based auth, CSRF protection, rate limiting, parameterized queries) but has several critical issues that must be addressed before production use.

### Severity Breakdown
- 🔴 **CRITICAL (must fix):** 4 issues
- 🟡 **WARNING (should fix):** 12 issues
- 🟢 **SUGGESTION (nice to have):** 6 issues

---

## Endpoint-by-Endpoint Audit

### 1. Auth Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/auth/signup` | POST | Public | Pydantic `AuthSignup` + `validate_email` + `validate_password` | ✅ 400/409/500 | ✅ ORM | **PASS** |
| `/auth/login` | POST | Public | Pydantic `AuthLogin` | ✅ 401/500 | ✅ ORM | **PASS** |
| `/auth/logout` | POST | Cookie/Header | — | ✅ 200 always | ✅ Redis | **PASS** |
| `/auth/logout-all` | POST | Required | — | ✅ 401/200 | ✅ Redis | **PASS** |
| `/auth/change-password` | POST | Required | Pydantic `ChangePasswordRequest` + `validate_password` | ✅ 400/401/500 | ✅ ORM | **PASS** |
| `/auth/me` | GET | Required | — | ✅ 401/404/500 | ✅ ORM | **PASS** |
| `/auth/forgot-password` | POST | Public | Pydantic `ForgotPasswordRequest` | ✅ 200/500 | ✅ ORM | **WARN** — see C1 |
| `/auth/reset-password` | POST | Public | Pydantic `ResetPasswordRequest` + `validate_password` | ✅ 400/500 | ✅ ORM | **WARN** |
| `/auth/profile` | PUT | Required | Allowlist filter (`{'phone'}`) | ✅ 400/401/500 | ✅ ORM | **PASS** |
| `/auth/telegram-link` | POST | Required | Pydantic `TelegramLink` | ✅ 401/500 | ✅ ORM | **PASS** |
| `/auth/telegram-link` | GET | ❌ **NONE** | `tg_id` query param | ✅ 400/404/500 | ✅ ORM | **🔴 CRITICAL — C2** |
| `/auth/send-welcome` | POST | Required | — | ✅ 400/401/500 | ✅ ORM | **PASS** |

### 2. Chat Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/v1/chat/completions` | POST | Required | `dict[str, Any]` (loose) | ✅ 401/429/502 | ✅ ORM | **WARN** — see W1 |
| `/v1/chat/with-file` | POST | Required | File size (10MB), type check, Form fields | ✅ 400/401/429/502 | ✅ ORM | **PASS** |
| `/v1/smart-chat` | POST | Required | `dict[str, Any]` + model selection | ✅ 401/429/502 | ✅ ORM | **WARN** — see W1 |

### 3. Wallet Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/wallet` | GET | Required | — | ✅ 401/500 | ✅ Parameterized SQL | **PASS** |
| `/wallet/ledger` | GET | Required | — | ✅ 401/500 | ✅ ORM | **PASS** |
| `/wallet/topup` | POST | Required | Pydantic `TopupRequest`, amount > 0 | ✅ 400/401/500 | ✅ ORM | **🔴 CRITICAL — C3** |

### 4. API Keys Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/api-keys` | POST | Required | Pydantic `ApiKeyCreate`, ISO8601 date | ✅ 400/401/500 | ✅ ORM | **🔴 CRITICAL — C4** |
| `/api-keys` | GET | Required | — | ✅ 401/500 | ✅ ORM | **PASS** |
| `/api-keys/{key_id}` | DELETE | Required | — | ✅ 401/500 | ✅ ORM (user_id scoped) | **PASS** |

### 5. Conversations Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/conversations` | GET | Required | — | ✅ 401/500 | ✅ ORM | **PASS** |
| `/conversations` | POST | Required | Pydantic `ConvCreate` | ✅ 401/500 | ✅ ORM | **PASS** |
| `/conversations/{id}` | GET | Required | `conv_id: int` (path) | ✅ 401/404/500 | ✅ ORM (user_id scoped) | **PASS** |
| `/conversations/{id}` | PUT | Required | Pydantic `ConvUpdate` | ✅ 401/404/500 | ✅ ORM (user_id scoped) | **PASS** |
| `/conversations/{id}` | DELETE | Required | `conv_id: int` (path) | ✅ 401/404/500 | ✅ ORM (user_id scoped) | **PASS** |
| `/conversations/{id}/export` | GET | Required | `format` query (json/markdown/text) | ✅ 400/401/404/500 | ✅ ORM (user_id scoped) | **PASS** |
| `/conversations/search` | GET | Required | `q` query param | ✅ 401/500 | ✅ ORM | **🟡 WARN — W2** |
| `/conversations/analytics` | GET | Required | — | ✅ 401/500 | ✅ Parameterized SQL | **PASS** |

### 6. Models Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/v1/models` | GET | ❌ Public | — | ✅ (fail-open returns []) | ✅ HTTP proxy | **PASS** |
| `/catalog/models` | GET | ❌ Public | — | ✅ (DB + fallback) | ✅ ORM/raw SQL | **PASS** |
| `/catalog/pricing` | GET | ❌ Public | — | ✅ (fallback chain) | ✅ ORM | **PASS** |

### 7. Assistants Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/assistants` | GET | Optional | — | ✅ 500 | ✅ ORM | **PASS** |
| `/assistants` | POST | Required | Pydantic `AssistantCreate` | ✅ 401/500 | ✅ ORM | **PASS** |
| `/assistants/{id}` | GET | ❌ None | `assistant_id: int` | ✅ 404/500 | ✅ ORM | **🟡 WARN — W3** |
| `/assistants/{id}` | PUT | Required | `dict[str, Any]` + allowlist | ✅ 401/404/500 | ✅ ORM (user_id scoped) | **PASS** |
| `/assistants/{id}` | DELETE | Required | `assistant_id: int` | ✅ 401/404/500 | ✅ ORM (user_id scoped) | **PASS** |

### 8. Admin Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/admin/login` | POST | Public | Pydantic `AdminLogin` + HMAC compare | ✅ 401 | ✅ Redis | **PASS** |
| `/admin/logout` | POST | Cookie/CSRF | — | ✅ 200 | ✅ Redis | **PASS** |
| `/admin/analytics` | GET | Admin | — | ✅ 401/500 | ✅ Parameterized SQL | **PASS** |
| `/admin/users` | GET | Admin | `page`/`limit` query params | ✅ 401/500 | ✅ Parameterized SQL | **PASS** |
| `/admin/users/{uid}` | PUT | Admin | `await request.json()` (raw) | ✅ 401/500 | ✅ ORM + parameterized | **🟡 WARN — W4** |
| `/admin/users/{uid}/ban` | POST | Admin | — | ✅ 401/404/500 | ✅ ORM | **🟡 WARN — W5** |
| `/admin/pricing` | GET | Admin | — | ✅ 401/500 | ✅ ORM | **PASS** |
| `/admin/pricing` | POST | Admin | Manual validation (`model` required, int prices) | ✅ 400/401/500 | ✅ ORM | **PASS** |
| `/admin/features` | GET | Admin | — | ✅ 401/500 | ✅ ORM | **PASS** |
| `/admin/features` | POST | Admin | `dict[str, Any]` | ✅ 401/404/500 | ✅ ORM | **PASS** |
| `/admin/features/{fid}` | DELETE | Admin | `fid: int` | ✅ 401 | ✅ ORM | **PASS** |
| `/admin/discounts` | GET | Admin | — | ✅ 401/500 | ✅ ORM | **PASS** |
| `/admin/discounts` | POST | Admin | `code` required | ✅ 400/401/404/500 | ✅ ORM | **PASS** |
| `/admin/discounts/{did}` | DELETE | Admin | `did: int` | ✅ 401 | ✅ ORM | **PASS** |
| `/admin/about` | GET → `/about` | ❌ Public | — | ✅ 500 | ✅ ORM | **PASS** |
| `/admin/about` | POST | Admin | `dict[str, Any]` | ✅ 401 | ✅ ORM | **PASS** |
| `/admin/proxy` | GET | Admin | — | ✅ 401 | ✅ ORM | **PASS** |
| `/admin/proxy` | POST | Admin | `dict[str, Any]` | ✅ 401 | ✅ ORM | **🟡 WARN — W6** |
| `/admin/plans` | GET | Admin | — | ✅ 401/500 | ✅ Parameterized SQL | **PASS** |
| `/admin/plans` | POST | Admin | `id` required + field list | ✅ 400/401/500 | ✅ Parameterized SQL | **🟡 WARN — W7** |
| `/admin/credit-packages` | GET | Admin | — | ✅ 401/500 | ✅ Parameterized SQL | **PASS** |
| `/admin/credit-packages` | POST | Admin | `id` required + field list | ✅ 400/401/500 | ✅ Parameterized SQL | **🟡 WARN — W7** |
| `/admin/subscriptions` | GET | Admin | `page`/`limit` | ✅ 401/500 | ✅ Parameterized SQL | **PASS** |
| `/admin/export/ledger` | GET | Admin | — | ✅ 401/500 | ✅ ORM | **PASS** |
| `/admin/export/users` | GET | Admin | — | ✅ 401/500 | ✅ Parameterized SQL | **PASS** |
| `/admin/org-default-model` | POST | Admin | `default_model` from payload | ✅ 401/500 | ✅ ORM | **PASS** |

### 9. Settings / Org Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/org/default-model` | GET | ❌ Public | — | ✅ 500 | ✅ ORM | **PASS** |

### 10. Health Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/health/live` | GET | ❌ Public | — | ✅ | N/A | **PASS** |
| `/health/ready` | GET | ❌ Public | — | ✅ 200/503 | ✅ Connection check | **PASS** |
| `/health` | GET | ❌ Public | — | ✅ | ✅ Connection check | **PASS** |
| `/health/detailed` | GET | Admin | — | ✅ 401 | ✅ Connection check | **PASS** |

### 11. Pricing Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/plans` | GET | ❌ Public | — | ✅ 500 | ✅ ORM | **PASS** |
| `/plans/{plan_id}` | GET | ❌ Public | `plan_id: str` | ✅ 404/500 | ✅ Parameterized SQL | **PASS** |
| `/credit-packages` | GET | ❌ Public | — | ✅ 500 | ✅ Parameterized SQL | **PASS** |
| `/credit-packages/{pkg_id}` | GET | ❌ Public | `pkg_id: str` | ✅ 404/500 | ✅ Parameterized SQL | **PASS** |
| `/pricing` | GET | — | — | — | — | **🔴 MISSING** — see C5 |
| `/subscribe` | POST | Required | Pydantic `SubscribeRequest` | ✅ 401/404/500 | ✅ Parameterized SQL | **PASS** |
| `/subscription` | GET | Required | — | ✅ 401/500 | ✅ Parameterized SQL | **PASS** |
| `/subscription/cancel` | POST | Required | — | ✅ 401/404/500 | ✅ Parameterized SQL | **PASS** |
| `/subscription/renew` | POST | Required | — | ✅ 401/404/500 | ✅ Parameterized SQL | **PASS** |
| `/subscription/checkout` | POST | Required | Pydantic `SubscriptionCheckout` | ✅ 400/401/404/500 | ✅ ORM | **PASS** |
| `/credit-package/checkout` | POST | Required | Pydantic `CreditPackageCheckout` | ✅ 400/401/404/500 | ✅ ORM | **PASS** |
| `/payment/request` | POST | Required | Pydantic `PaymentRequest` | ✅ 400/401 | ✅ ORM | **PASS** |
| `/payment/callback` | GET | Public (Zarinpal redirect) | `Authority`/`Status` query | ✅ 400/500 | ✅ ORM | **PASS** |
| `/payment/history` | GET | Required | — | ✅ 401/500 | ✅ ORM | **PASS** |

### 12. Features Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/content/features` | GET | ❌ Public | — | ✅ 500 | ✅ ORM | **PASS** |
| `/content/discounts` | GET | ❌ Public | — | ✅ 500 | ✅ ORM | **PASS** |
| `/features` | GET | — | — | — | — | **🟡 WARN** — see W8 |

### 13. Discounts Endpoints

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/discounts/apply` | POST | — | — | — | — | **🟡 MISSING** — see W9 |

### 14. Other Endpoints (not in task scope but audited)

| Endpoint | Method | Auth | Validation | Error Handling | SQL Safety | Status |
|---|---|---|---|---|---|---|
| `/me/usage` | GET | Required | — | ✅ 401/500 | ✅ ORM | **PASS** |
| `/me/subscription` | GET | Required | — | ✅ 401/500 | ✅ ORM | **PASS** |
| `/me/billing` | GET/PUT | Required | Pydantic `BillingUpdate` | ✅ 401/500 | ✅ ORM | **PASS** |
| `/billing/settings` | GET/PUT | Required | Pydantic `BillingSettingsUpdate` | ✅ 401/500 | ✅ ORM | **PASS** |
| `/referral/stats` | GET | Required | — | ✅ 401/500 | ✅ Parameterized SQL | **PASS** |
| `/notifications` | GET | Required | — | ✅ 401/500 | ✅ ORM | **PASS** |
| `/notifications/{nid}/read` | POST | Required | `nid: int` | ✅ 401/500 | ✅ ORM (user_id scoped) | **PASS** |
| `/memories` | CRUD | Required | Pydantic models | ✅ | ✅ ORM (user_id scoped) | **PASS** |
| `/skills` | CRUD | Required/Public | Pydantic models | ✅ | ✅ ORM | **PASS** |
| `/tasks` | CRUD | Required | Pydantic models | ✅ | ✅ ORM (user_id scoped) | **PASS** |
| `/ws` | WebSocket | Token query param | — | ✅ | ✅ Redis | **🟡 WARN — W10** |

---

## 🔴 Critical Issues (Must Fix)

### C1: Password Reset Token Leak in Debug Mode
**File:** `app.py:2121-2125`
```python
return JSONResponse({
    'status': 'ok',
    'message': 'reset link sent to your email',
    'token': reset_token if os.getenv('DEBUG') else None,  # Only show in debug
})
```
**Risk:** If `DEBUG` env var is accidentally set in production, **anyone** can reset **any** user's password by calling `/auth/forgot-password` with their email and receiving the token in the response.  
**Fix:** Never return the token in the response body regardless of debug mode. Log it server-side only.

### C2: Authentication Bypass via `/auth/telegram-link` GET
**File:** `app.py:2175-2195`
```python
@app.get('/auth/telegram-link')
async def get_telegram_token(request: Request) -> JSONResponse:
    tg_id = request.query_params.get('tg_id')
    # NO AUTH CHECK — returns valid session token for any linked Telegram user
    ...
    token = _gen_token()
    rds.setex(f'session:{token}', SESSION_TTL, str(user.id))
    return JSONResponse({'token': token, 'user': {'id': user.id, 'email': user.email}})
```
**Risk:** Anyone who knows or guesses a `telegram_id` integer can obtain a **full session token** for the corresponding user account. This is a complete authentication bypass. Telegram IDs are sequential integers and easily guessable.  
**Fix:** This endpoint must require authentication (admin-only or require a Telegram-initiated cryptographic proof). Alternatively, implement a nonce-based flow where the Telegram bot initiates the link.

### C3: Unprotected Wallet Topup (No Payment Verification)
**File:** `app.py:2959-2980`
```python
@app.post('/wallet/topup')
async def topup(request: Request, payload: TopupRequest) -> JSONResponse:
    uid = await _get_user_id(request)
    # Directly adds credits to wallet — no payment gateway verification
    entry = Ledger(user_id=uid, amount=payload.amount, ...)
```
**Risk:** Any authenticated user can add arbitrary credits to their wallet by calling this endpoint directly, bypassing the Zarinpal payment flow entirely.  
**Fix:** Either remove this endpoint (payment should go through `/payment/request` → callback flow) or gate it behind admin auth. If it's for testing, restrict to dev environments only.

### C4: Unreachable Audit Log in API Key Creation
**File:** `app.py:3539-3549`
```python
    return JSONResponse({  # <-- returns here on line 3548
        'id': key.id,
        ...
    })
    await _write_audit_log('api_key.create', ...)  # NEVER EXECUTED
```
**Risk:** The audit log for API key creation is **dead code** — placed after a `return` statement. Security-relevant operations must be audit-logged.  
**Fix:** Move `_write_audit_log` before the `return` statement, or restructure to log then return.

### C5: Missing `/pricing` Endpoint
**Risk:** The task specification lists `GET /pricing` as a required endpoint, but the codebase only has `/catalog/pricing` and `/admin/pricing`. If the frontend or external consumers expect `/pricing`, they'll get a 404.  
**Fix:** Add a `GET /pricing` route (alias to `/catalog/pricing`) or document that `/catalog/pricing` is the canonical path.

---

## 🟡 Warnings (Should Fix)

### W1: Loose Chat Payload Validation
**Files:** `app.py:836`, `app.py:4809`
```python
async def chat(request: Request, payload: dict[str, Any]) -> Response:
```
The `/v1/chat/completions` and `/v1/smart-chat` endpoints accept a raw `dict[str, Any]` instead of a typed Pydantic model. No validation of `messages` structure, `model` field, `temperature` range, etc.  
**Risk:** Malformed payloads could cause unexpected behavior or errors deep in the proxy chain.  
**Fix:** Define a Pydantic model with required fields and constraints.

### W2: Conversation Search Performance / DoS Risk
**File:** `app.py:2240-2286`
```python
# Loads up to 200 conversations, then iterates ALL messages in Python
for r in all_rows:
    msgs = r.messages or []
    for msg in msgs:
        if isinstance(msg, dict) and q.lower() in (msg.get('content', '') or '').lower():
```
**Risk:** For users with many conversations containing large message histories, this is O(n×m) in Python — could cause memory exhaustion and slow responses.  
**Fix:** Implement PostgreSQL full-text search (`tsvector`/`tsquery`) or limit the Python-side search scope.

### W3: Assistant Detail Endpoint Has No Auth
**File:** `app.py:1599-1610`
```python
@app.get('/assistants/{assistant_id}')
async def get_assistant(assistant_id: int, request: Request) -> JSONResponse:
    # No auth check — any assistant (including private ones) is accessible by ID
```
**Risk:** Private (non-public) assistants can be accessed by anyone who knows/guesses the integer ID.  
**Fix:** Add ownership check: if `is_public=False`, require authentication and verify `user_id`.

### W4: Admin Edit User — No Pydantic Validation
**File:** `app.py:3052-3074`
```python
payload = await request.json()  # raw dict, no schema validation
```
**Risk:** Unstructured input could set unexpected fields. Also, `int(payload['daily_limit'])` will throw an unhandled exception on non-numeric input.  
**Fix:** Define a Pydantic model for the allowed fields.

### W5: Ban Implementation Uses `telegram_id` Field Abuse
**File:** `app.py:3026-3049`
```python
# Uses telegram_id = -1 as ban flag
await session.execute(
    User.__table__.update().where(User.id == uid),
    {'telegram_id': -1 if user.telegram_id != -1 else None}
)
```
**Risk:** Overwrites the user's Telegram ID to implement banning. If the user had a real Telegram ID linked, it's permanently lost.  
**Fix:** Add a dedicated `banned: Mapped[bool]` column to the User model.

### W6: Admin Proxy Config Affects All Outbound Traffic
**File:** `app.py:1490-1509`
**Risk:** Setting a malicious proxy URL could intercept/modify all LLM API traffic, including API keys sent to upstream providers. No validation that the proxy URL is a legitimate endpoint.  
**Fix:** Validate proxy URL against an allowlist or at minimum ensure it uses expected protocols (socks5/http).

### W7: Dynamic SQL Column Interpolation in Plan/Package Upserts
**File:** `app.py:3996-4008`, `app.py:4073-4085`
```python
set_parts.append(f'{f} = :{f}')  # f comes from hardcoded list, but string interpolation
```
**Risk:** While `f` comes from a hardcoded field list (not user input), this pattern is fragile. If the field list is ever modified to include user-controlled values, it becomes SQL injection.  
**Fix:** Use ORM `setattr` pattern or Pydantic model for updates instead of raw SQL interpolation.

### W8: No `/features` Route (Only `/content/features`)
**Risk:** If consumers expect `GET /features`, they'll get 404. The codebase has `/content/features` and `/admin/features`.  
**Fix:** Add redirect/alias or document the canonical path.

### W9: No `POST /discounts/apply` Endpoint
**Risk:** The task specification lists this endpoint, but it doesn't exist in the codebase. Discount codes can only be managed via admin endpoints (`/admin/discounts`). There's no user-facing endpoint to apply a discount code during checkout.  
**Fix:** Implement a `POST /discounts/apply` endpoint that validates a discount code, checks expiry/active status, and returns the discounted amount.

### W10: WebSocket Token in Query Parameter
**File:** `app.py:5099`
```python
token = ws.query_params.get('token', '')
```
**Risk:** Tokens in query parameters are logged in web server access logs, browser history, and potentially intermediary proxy logs.  
**Fix:** Use WebSocket subprotocol header or first-message authentication pattern.

### W11: Race Condition in Balance Deduction
**Files:** `app.py:768-832` (`_check_quota_pre`), `app.py:1110-1188` (`_track_usage`)
```python
# Read balance
res = await session.execute(sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) ...'))
current = row.balance
# ... later ...
if current >= cost:
    entry = Ledger(user_id=uid, amount=-cost, balance_after=current - cost, ...)
```
**Risk:** Two concurrent requests can both read the same balance, both pass the `>= cost` check, and both insert deductions — potentially driving the balance negative.  
**Fix:** Use `SELECT ... FOR UPDATE` on the balance row, or use a database-level atomic check constraint.

### W12: Error Messages Leak Internal Details
**Files:** `app.py:913`, `app.py:1048`, `app.py:4902`
```python
return JSONResponse({'error': {'message': f'upstream unavailable: {e}', ...}}, status_code=502)
```
**Risk:** Python exception messages can contain internal hostnames, connection strings, and stack details.  
**Fix:** Return a generic error message to the client; log the detailed error server-side.

---

## 🟢 Suggestions (Nice to Have)

### S1: Inconsistent Endpoint Naming
The API uses mixed naming conventions:
- `/content/features` vs `/admin/features` vs missing `/features`
- `/me/usage` vs `/wallet` (no `/me/wallet`)
- `/catalog/models` vs `/v1/models`

**Suggestion:** Adopt a consistent URL structure (e.g., `/api/v1/...` prefix for all, or `/me/...` for all user-scoped endpoints).

### S2: No Pagination on Several List Endpoints
Endpoints like `/api-keys`, `/notifications`, `/memories` have hardcoded `LIMIT` clauses but no cursor/page parameters.  
**Suggestion:** Add `skip`/`limit` query parameters with sensible defaults.

### S3: Monolithic File Architecture
`app.py` is 5140 lines with 50+ endpoints, ORM models, utility functions, middleware config, and business logic all in one file.  
**Suggestion:** Split into routers (`auth.py`, `chat.py`, `wallet.py`, `admin.py`, etc.) and separate model definitions into `models.py`.

### S4: Duplicate Billing Logic
`_track_usage` and `_bill_stream_usage` contain nearly identical pricing/billing code (~80 lines each).  
**Suggestion:** Extract a shared `_calculate_and_deduct_cost()` function.

### S5: Async Email Sending
`send_email` uses synchronous `smtplib.SMTP` which blocks the event loop during the TLS handshake and message send.  
**Suggestion:** Use `aiosmtplib` or run in an executor.

### S6: Rate Limiter Fail-Open vs Fail-Closed Inconsistency
The rate limiter in `security.py:49` fails closed (`return False, 0` when Redis is down), but the main app's quota check (`_check_quota_pre`, line 830) fails open (`pass` on exception).  
**Suggestion:** Standardize the failure mode strategy across all safety checks.

---

## Security Architecture Summary

### ✅ What's Done Well
1. **Session management:** Server-side sessions in Redis with httpOnly/secure/sameSite cookies
2. **CSRF protection:** Custom `X-Requested-With` header requirement for cookie-auth mutations
3. **Admin isolation:** Separate admin session namespace with CSRF tokens, audit logging
4. **Password security:** PBKDF2 with 100k iterations, per-user salt, constant-time comparison
5. **API key security:** SHA-256 with server-side pepper, keys shown only once
6. **Rate limiting:** Per-endpoint-class limits with Redis sliding window
7. **Security headers:** Full suite (HSTS, X-Frame-Options, CSP-like headers)
8. **SQL injection prevention:** All queries use parameterized ORM or parameterized raw SQL
9. **Input validation:** Pydantic models on most endpoints, email/password validation
10. **Audit logging:** All admin and auth state changes logged to `audit_log` table

### ❌ What Needs Improvement
1. Authentication bypass on Telegram link endpoint (C2)
2. Unprotected wallet topup (C3)
3. Missing audit log for API key creation (C4)
4. Race conditions in balance deduction (W11)
5. Performance risk in conversation search (W2)
6. Error message information leakage (W12)

---

## SQL Injection Risk Assessment

**Verdict: LOW RISK** ✅

All database queries use either:
- SQLAlchemy ORM (parameterized by design)
- `sqlalchemy.text()` with `:param` bind variables

The `ilike(f'%{q}%')` pattern (lines 2254, 2502, 2696-2699) uses ORM methods that parameterize the value. However, `%` and `_` wildcards in user input are NOT escaped, which could lead to broader matches than intended (not injection, but a logic issue).

The dynamic SQL in admin plan/package upserts (W7) uses string interpolation for column names but parameterized values — safe but fragile.

---

*End of audit. 5140 lines reviewed, 80+ endpoints cataloged.*
