# SENIOR 8 — API Documentation & Consistency Audit

**File:** `/root/multiai/backend/app.py` (5,140 lines, ~217KB)
**Framework:** FastAPI (title: "Persian AI Gateway", version 0.1.0)
**Date:** 2026-07-14

---

## 1. Complete API Endpoint Inventory

### 1.1 Root & System (4 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 1 | GET | `/` | None | — | `{"service": str, "docs": "/docs"}` |
| 2 | GET | `/health` | None | — | `HealthResponse` (status, uptime, db, redis) |
| 3 | GET | `/health/live` | None | — | `{"status": "ok"}` |
| 4 | GET | `/health/ready` | None | — | `{"status": "ok"/"unavailable", "db": str, "redis": str}` |
| 5 | GET | `/health/detailed` | Admin | — | System metrics (CPU, memory, disk, services) |

### 1.2 Authentication (12 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 6 | POST | `/auth/signup` | None | `AuthSignup` (email, password, ref?) | `{"token": str, "user": {id, email}}` + Set-Cookie |
| 7 | POST | `/auth/login` | None | `AuthLogin` (email, password) | `{"token": str, "user": {id, email}}` + Set-Cookie |
| 8 | POST | `/auth/logout` | Optional | — | `{"status": "ok"}` + Clear-Cookie |
| 9 | POST | `/auth/logout-all` | Session | — | `{"status": "ok", "revoked_sessions": int}` |
| 10 | GET | `/auth/me` | Session | — | `{id, email, created_at, referral_code}` |
| 11 | POST | `/auth/change-password` | Session | `ChangePasswordRequest` (current, new) | `{"status": "ok"}` + session rotation |
| 12 | PUT | `/auth/profile` | Session | `dict` (allowed: phone) | `{"status": "ok", "updated": [str]}` |
| 13 | POST | `/auth/forgot-password` | None | `ForgotPasswordRequest` (email) | `{"status": "ok", "message": str}` |
| 14 | POST | `/auth/reset-password` | None | `ResetPasswordRequest` (token, new_password) | `{"status": "ok", "message": str}` |
| 15 | POST | `/auth/telegram-link` | Session | `TelegramLink` (telegram_id) | `{"status": "ok", "telegram_id": int}` |
| 16 | GET | `/auth/telegram-link` | None | Query: `tg_id` | `{"token": str, "user": {id, email}}` |
| 17 | POST | `/auth/send-welcome` | Session | — | `{"status": "sent"/"queued"}` |

### 1.3 Admin Authentication (2 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 18 | POST | `/admin/login` | None | `AdminLogin` (token) | `{"status": "ok", "csrf": str}` + Set-Cookie |
| 19 | POST | `/admin/logout` | Admin Cookie | — | `{"status": "ok"}` + Clear-Cookie |

### 1.4 Chat & Completions (4 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 20 | POST | `/v1/chat/completions` | Session/API Key | OpenAI-compatible dict | OpenAI-compatible response (proxied) |
| 21 | POST | `/v1/chat/with-file` | Session/API Key | Multipart (file + model + messages + stream) | OpenAI-compatible response (proxied) |
| 22 | POST | `/v1/smart-chat` | Session/API Key | OpenAI-compatible dict + auto-model | OpenAI-compatible response + X-Smart-Model headers |
| 23 | GET | `/v1/models` | None | — | `{"object": "list", "data": [...]}` (OpenAI format) |

### 1.5 Catalog (2 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 24 | GET | `/catalog/models` | None | — | `{data: [...], generatedAt, source}` |
| 25 | GET | `/catalog/pricing` | None | — | `{data: [...], generatedAt, priceVersion}` |

### 1.6 Conversations (7 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 26 | GET | `/conversations` | Session | — | `[{id, title, model, created_at, updated_at}]` |
| 27 | POST | `/conversations` | Session | `ConvCreate` (title, model, messages) | `{id, title, model, messages, created_at}` |
| 28 | GET | `/conversations/search` | Session | Query: `q` | `[{...conversation...}]` |
| 29 | GET | `/conversations/analytics` | Session | — | Analytics summary object |
| 30 | GET | `/conversations/{conv_id}` | Session | — | `{id, title, model, messages, created_at}` |
| 31 | PUT | `/conversations/{conv_id}` | Session | `ConvUpdate` (title?, messages?) | `{"status": "ok"}` |
| 32 | DELETE | `/conversations/{conv_id}` | Session | — | `{"status": "deleted"}` |
| 33 | GET | `/conversations/{conv_id}/export` | Session | Query: `format` (json/markdown/text) | JSON / Markdown / Text file |

### 1.7 Memories (6 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 34 | GET | `/memories` | Session | Query: `category?` | `[Memory...]` |
| 35 | GET | `/memories/search` | Session | Query: `q` | `[Memory...]` |
| 36 | POST | `/memories` | Session | `MemoryCreate` (content, category, source, tags) | `{id, content, category, ...}` |
| 37 | PUT | `/memories/{memory_id}` | Session | `MemoryUpdate` | `{"status": "ok"}` |
| 38 | DELETE | `/memories/{memory_id}` | Session | — | `{"status": "deleted"}` (soft-delete) |

### 1.8 Skills Marketplace (8 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 39 | GET | `/skills` | None | Query: category, featured, sort, q, skip, limit | `[SkillTemplate...]` |
| 40 | GET | `/skills/my` | Session | — | `[SkillTemplate...]` |
| 41 | GET | `/skills/{template_id}` | Optional | — | `SkillTemplate` dict |
| 42 | POST | `/skills` | Session | `SkillTemplateCreate` | Full skill template object |
| 43 | PUT | `/skills/{template_id}` | Session (owner) | `SkillTemplateUpdate` | `{"status": "ok"}` |
| 44 | DELETE | `/skills/{template_id}` | Session (owner) | — | `{"status": "deleted"}` |
| 45 | POST | `/skills/{template_id}/rate` | Session | `SkillRatingRequest` (rating 1-5) | `{"status": "ok"}` |
| 46 | POST | `/skills/{template_id}/use` | None | `SkillUseRequest` (variables, model) | `{rendered_prompt, model}` |

### 1.9 Wallet & Billing (7 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 47 | GET | `/wallet` | Session | — | `{"balance": int}` |
| 48 | GET | `/wallet/ledger` | Session | — | `[{id, amount, balance_after, reason, created_at}]` |
| 49 | POST | `/wallet/topup` | Session | `TopupRequest` (amount) | `{"status": "ok", "balance_after": int}` |
| 50 | GET | `/billing/settings` | Session | — | `{user_id, payg_enabled, payg_hard_limit, notify_on_usage_pct}` |
| 51 | PUT | `/billing/settings` | Session | `BillingSettingsUpdate` | `{"status": "ok"}` |
| 52 | GET | `/me/billing` | Session | — | `{user_id, payg_enabled, payg_hard_limit, notify_on_usage_pct}` |
| 53 | PUT | `/me/billing` | Session | `BillingUpdate` | `{"status": "ok"}` |

### 1.10 Subscriptions & Plans (9 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 54 | GET | `/plans` | None | — | `{"plans": [...], "credit_packages": [...]}` |
| 55 | GET | `/plans/{plan_id}` | None | — | Plan dict |
| 56 | GET | `/credit-packages` | None | — | `[CreditPackage...]` |
| 57 | GET | `/credit-packages/{pkg_id}` | None | — | CreditPackage dict |
| 58 | POST | `/subscribe` | Session | `SubscribeRequest` (plan_id) | `{status, subscription: {...}}` |
| 59 | GET | `/subscription` | Session | — | `{subscription, plan}` |
| 60 | GET | `/me/subscription` | Session | — | `{subscription, payg_enabled, usage}` |
| 61 | POST | `/subscription/cancel` | Session | — | `{"status": "cancelled", "subscription_id": int}` |
| 62 | POST | `/subscription/renew` | Session | — | `{"status": "renewed", "ends_at": str}` |
| 63 | POST | `/subscription/checkout` | Session | `SubscriptionCheckout` (plan_id) | `{authority, url, amount, plan, plan_fa}` |
| 64 | POST | `/credit-package/checkout` | Session | `CreditPackageCheckout` (package_id) | `{authority, url, amount, package, total_credits}` |

### 1.11 Payment Gateway (3 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 65 | POST | `/payment/request` | Session | `PaymentRequest` (amount, description) | `{authority, url, amount}` |
| 66 | GET | `/payment/callback` | None | Query: Authority, Status | `{status, ref_id, amount, redirect}` |
| 67 | GET | `/payment/history` | Session | — | `[{id, amount, authority, ref_id, status, ...}]` |

### 1.12 Notifications (2 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 68 | GET | `/notifications` | Session | — | `[{id, type, title, body, read, created_at}]` |
| 69 | POST | `/notifications/{nid}/read` | Session | — | `{"status": "ok"}` |

### 1.13 API Keys (3 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 70 | POST | `/api-keys` | Session | `ApiKeyCreate` (name, scopes, expires_at) | `{id, name, key, prefix, masked, ...}` |
| 71 | GET | `/api-keys` | Session | — | `[{id, name, prefix, masked, scopes, ...}]` |
| 72 | DELETE | `/api-keys/{key_id}` | Session | — | `{"status": "revoked"}` |

### 1.14 Scheduled Tasks (7 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 73 | GET | `/tasks` | Session | — | `[Task...]` |
| 74 | POST | `/tasks` | Session | `ScheduledTaskCreate` | Task object |
| 75 | PUT | `/tasks/{task_id}` | Session | `ScheduledTaskUpdate` | Task object |
| 76 | DELETE | `/tasks/{task_id}` | Session | — | `{"status": "deleted"}` |
| 77 | POST | `/tasks/{task_id}/toggle` | Session | — | `{id, is_active}` |
| 78 | POST | `/tasks/{task_id}/run` | Session | — | `{execution_id, status, result, ...}` |
| 79 | GET | `/tasks/{task_id}/executions` | Session | — | `[Execution...]` |

### 1.15 Referral (1 endpoint)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 80 | GET | `/referral/stats` | Session | — | `{referral_code, referral_count, total_bonus, referral_url}` |

### 1.16 Public Content (2 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 81 | GET | `/content/features` | None | — | `[Feature...]` |
| 82 | GET | `/content/discounts` | None | — | `[{code, percent}]` |

### 1.17 About (1 endpoint)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 83 | GET | `/about` | None | — | `{title, body}` |

### 1.18 Organization (2 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 84 | GET | `/org/default-model` | None | — | `{"default_model": str}` |
| 85 | POST | `/admin/org-default-model` | Admin | `{default_model: str}` | `{"status": "ok", "default_model": str}` |

### 1.19 Admin — Content Management (14 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 86 | GET | `/admin/pricing` | Admin | — | `[PricingRow...]` |
| 87 | POST | `/admin/pricing` | Admin | dict (model, prices) | `{status, model, price_version}` |
| 88 | GET | `/admin/features` | Admin | — | `[Feature...]` |
| 89 | POST | `/admin/features` | Admin | dict (id?, title, ...) | `{status, id}` |
| 90 | DELETE | `/admin/features/{fid}` | Admin | — | `{"status": "deleted"}` |
| 91 | GET | `/admin/discounts` | Admin | — | `[Discount...]` |
| 92 | POST | `/admin/discounts` | Admin | dict (id?, code, ...) | `{status, id}` |
| 93 | DELETE | `/admin/discounts/{did}` | Admin | — | `{"status": "deleted"}` |
| 94 | POST | `/admin/about` | Admin | dict (title, body) | `{"status": "ok"}` |
| 95 | GET | `/admin/proxy` | Admin | — | Proxy config dict |
| 96 | POST | `/admin/proxy` | Admin | dict (proxy_url, ...) | `{status, proxy_url}` |
| 97 | GET | `/admin/plans` | Admin | — | `[Plan...]` |
| 98 | POST | `/admin/plans` | Admin | dict (id, fields...) | `{status, id}` |
| 99 | GET | `/admin/credit-packages` | Admin | — | `[CreditPackage...]` |
| 100 | POST | `/admin/credit-packages` | Admin | dict (id, fields...) | `{status, id}` |

### 1.20 Admin — User Management (5 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 101 | GET | `/admin/users` | Admin | Query: page, limit | `{users, total, page, limit}` |
| 102 | POST | `/admin/users/{uid}/ban` | Admin | — | `{status, banned}` |
| 103 | PUT | `/admin/users/{uid}` | Admin | dict (daily_limit, phone) | `{"status": "ok"}` |
| 104 | GET | `/admin/analytics` | Admin | — | Aggregate analytics |
| 105 | GET | `/admin/subscriptions` | Admin | Query: page, limit | `{subscriptions, total, page, limit}` |

### 1.21 Admin — Export (2 endpoints)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 106 | GET | `/admin/export/ledger` | Admin | — | CSV file (text/csv) |
| 107 | GET | `/admin/export/users` | Admin | — | CSV file (text/csv) |

### 1.22 WebSocket (1 endpoint)

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 108 | WS | `/ws` | Query: `token` | Client sends `ping` | `{type, message}` JSON frames |

### Usage/Metering

| # | Method | Path | Auth | Request Body | Response Schema |
|---|--------|------|------|-------------|-----------------|
| 109 | GET | `/me/usage` | Session | — | `{user_id, daily_limit, used_today, reset_at}` |

**Total: 109 endpoints** (108 HTTP + 1 WebSocket)

---

## 2. Consistency Check

### 2.1 Error Response Consistency — ⚠️ INCONSISTENT

**Expected pattern:** `{"detail": "message"}`

**Actual patterns found — THREE different error formats:**

| Pattern | Used In | Count |
|---------|---------|-------|
| `{"detail": "..."}` | Auth, admin, CRUD, most endpoints | ~240 occurrences |
| `{"error": {"message": "...", "type": "..."}}` | Chat completions, file upload (lines 800, 913, 1015, 1047, 4901) | 5 occurrences |
| `{"type": "error", "message": "..."}` | WebSocket (line 5103) | 1 occurrence |

**🔴 Severity: HIGH** — Clients must handle multiple error formats. The chat endpoints use OpenAI-style error format (`error.message`) while everything else uses `detail`.

**Recommendation:** Standardize on `{"detail": "message"}` for all non-OpenAI-compatible endpoints. For `/v1/chat/completions` and `/v1/smart-chat`, the OpenAI format `{"error": {"message": ..., "type": ...}}` is acceptable since it mirrors the upstream API contract. Document this distinction clearly.

### 2.2 Success Response Consistency — ⚠️ INCONSISTENT

Multiple success response shapes used:

| Pattern | Examples |
|---------|----------|
| `{"status": "ok"}` | Most admin mutation endpoints |
| `{"status": "deleted"}` | Delete endpoints |
| `{"status": "ok", "id": ...}` | Upsert endpoints (features, discounts, plans) |
| `{"status": "ok", "key": ..., "id": ...}` | API key creation |
| `{"status": "sent"/"queued"}` | Email sending |
| Raw data objects (no status) | GET endpoints returning lists/objects |
| `{"token": ..., "user": {...}}` | Auth endpoints |

**🟡 Severity: MEDIUM** — No consistent envelope. Some endpoints wrap in `{"status": ...}`, others return raw data. This is somewhat normal for REST APIs but should be documented.

### 2.3 HTTP Status Codes — ✅ MOSTLY CORRECT, ⚠️ MINOR ISSUES

| Code | Usage | Assessment |
|------|-------|------------|
| 200 | All successful responses | ✅ Correct |
| 400 | Validation errors | ✅ Correct |
| 401 | Missing/invalid auth | ✅ Correct |
| 403 | Forbidden (skill ownership) | ✅ Correct |
| 404 | Not found | ✅ Correct |
| 409 | Duplicate email signup | ✅ Correct |
| 429 | Quota exceeded / zero balance | ✅ Correct |
| 500 | DB not initialized | ⚠️ Should be 503 (service unavailable) |
| 502 | Upstream LiteLLM unavailable | ✅ Correct |

**🟡 Issue:** "db not initialized" returns 500 throughout (~50+ endpoints). This should be **503 Service Unavailable** since it's a transient infrastructure issue, not an application bug.

### 2.4 URL Path Consistency — 🔴 SIGNIFICANT ISSUES

**No consistent prefix strategy:**

| Pattern | Examples | Count |
|---------|----------|-------|
| `/v1/...` | `/v1/models`, `/v1/chat/completions`, `/v1/chat/with-file`, `/v1/smart-chat` | 4 |
| `/auth/...` | `/auth/login`, `/auth/signup`, etc. | 12 |
| `/admin/...` | `/admin/users`, `/admin/pricing`, etc. | ~25 |
| `/me/...` | `/me/usage`, `/me/subscription`, `/me/billing` | 4 |
| `/catalog/...` | `/catalog/models`, `/catalog/pricing` | 2 |
| Bare resource | `/conversations`, `/memories`, `/skills`, `/tasks`, `/wallet`, `/plans`, `/notifications`, `/api-keys`, `/about`, `/referral/stats`, `/subscribe`, `/subscription`, `/billing/settings`, `/payment/*`, `/content/*`, `/org/*`, `/credit-packages/*`, `/credit-package/*` | ~50 |

**Specific issues:**

1. **`/v1/` prefix is only used for OpenAI-compatible endpoints** — This is inconsistent. Either version all public API endpoints or none.

2. **Pluralization inconsistency:**
   - `/subscription` (singular) — GET/POST/cancel/renew
   - `/subscriptions` (plural) — only in admin (`/admin/subscriptions`)
   - `/subscribe` (verb) — POST
   - `/credit-packages` (plural, kebab) — GET list
   - `/credit-package/checkout` (singular, kebab) — POST

3. **Similar concepts, different URL structures:**
   - `/billing/settings` vs `/me/billing` — **both serve the same UserBillingSetting!**
   - `/subscription` vs `/me/subscription` — both return subscription data

4. **Hyphen vs no-hyphen:**
   - `/api-keys` (hyphen) — good
   - `/credit-packages` (hyphen) — good
   - `/default-model` — ok

5. **Mixed verbs and nouns:**
   - `/subscribe` (verb) — should be `POST /subscriptions`
   - `/subscription/cancel` (verb in path) — should be `DELETE /subscription`
   - `/subscription/renew` (verb in path)
   - `/subscription/checkout` — creates a payment, not a subscription

### 2.5 Auth Mechanism Consistency — ⚠️ MIXED

| Mechanism | Used For | Implementation |
|-----------|----------|----------------|
| **Session cookie** (primary) | User endpoints | `_get_user_id()` checks `session` cookie first |
| **Bearer token** (fallback) | User endpoints | `_get_user_id()` falls back to `Authorization: Bearer <token>` |
| **API key** (sk-...) | User endpoints | `_get_user_id()` falls back to `sk-*` key lookup in DB |
| **Admin session cookie** (primary) | Admin endpoints | `admin_required()` checks `admin_session` cookie + CSRF |
| **x-admin-token header** (fallback) | Admin endpoints | `admin_required()` falls back to header comparison |
| **Authorization: Bearer** (legacy) | Admin endpoints | `admin_required()` also checks Bearer for admin token |
| **WebSocket token query param** | WebSocket | Direct `token` query parameter |

**🟡 Issues:**
- Admin auth allows 3 different methods (cookie+CSRF, x-admin-token header, Bearer header)
- WebSocket uses query param token (leaks in logs/URLs) — should use first message auth
- No rate limiting differentiation between auth types (API keys should have higher limits)

---

## 3. Missing Endpoints & Security Issues

### 3.1 `/docs` Exposure — 🔴 SECURITY RISK

```python
@app.get('/')
async def root() -> dict[str, str]:
    return {'service': 'Persian AI Gateway', 'docs': '/docs'}
```

**The `/docs` endpoint (Swagger UI) and `/openapi.json` are enabled by default in FastAPI.** The root endpoint even advertises them!

**🔴 Recommendation:**
```python
# In production:
app = FastAPI(title='Persian AI Gateway', version='0.1.0', 
              lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
```

Or gate behind admin auth. OpenAPI schemas expose the full API surface to attackers.

### 3.2 Dead/Unreachable Endpoints

**None found.** All registered endpoints appear reachable.

### 3.3 Duplicate/Overlapping Endpoints — 🔴 REAL PROBLEM

| Overlap | Endpoint A | Endpoint B | Issue |
|---------|-----------|------------|-------|
| Billing settings | `GET /billing/settings` | `GET /me/billing` | Both return same `UserBillingSetting` data |
| Billing settings | `PUT /billing/settings` | `PUT /me/billing` | Both update same `UserBillingSetting` |
| Subscription data | `GET /subscription` | `GET /me/subscription` | Both return current subscription |
| Plan listing | `GET /plans` | `GET /admin/plans` | Admin version includes inactive plans (intentional?) |

**🟡 Recommendation:** Deprecate one of each pair. Prefer the `/me/` prefix for user-scoped endpoints.

### 3.4 Additional Security Concerns

1. **Payment callback (`GET /payment/callback`) is unauthenticated** — This is correct for Zarinpal redirects, but the endpoint must validate the `Authority` parameter strictly. It does go through `handle_payment_callback()`.

2. **`/auth/telegram-link` GET is unauthenticated** — Anyone who knows a `tg_id` can get a session token. This is a **potential account takeover vector** if telegram IDs are guessable/leaked.

3. **Admin `POST /admin/users/{uid}` reads raw `await request.json()`** instead of using a Pydantic model — no input validation (lines 3060, 3980, 4060).

4. **CORS `allow_credentials=False`** but auth uses cookies — this means cookie-based auth from cross-origin requests won't work. The frontend must use Bearer tokens for cross-origin requests.

---

## 4. API Versioning Analysis

### 4.1 Current State — 🔴 NO CONSISTENT STRATEGY

Only 4 of 109 endpoints use `/v1/` prefix:
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/chat/with-file`
- `POST /v1/smart-chat`

These are the OpenAI-compatible endpoints — the `/v1/` prefix mimics the OpenAI API surface. The remaining ~105 endpoints have **no version prefix**.

### 4.2 Is This a Problem?

**🟡 Yes, but low priority currently.** The non-versioned endpoints are all application-specific and can evolve freely since the frontend is tightly coupled. However:

- If external developers use the API (e.g., API key holders hitting `/v1/chat/completions`), breaking changes to other endpoints (`/wallet`, `/conversations`, etc.) will break them without warning.
- There is no `Accept-Version` header or query param versioning either.

### 4.3 Recommendations

1. **Short term:** Document that only `/v1/*` endpoints are part of the "public API" and may be used by external developers. All other endpoints are "application API" subject to change.

2. **Long term:** If opening up more endpoints to external consumers, add `/v1/` prefix to all public-facing endpoints:
   - `/v1/auth/*`
   - `/v1/conversations/*`
   - `/v1/memories/*`
   - `/v1/wallet/*`
   - etc.

---

## 5. Summary of Findings

| Category | Severity | Count | Description |
|----------|----------|-------|-------------|
| Error format inconsistency | 🔴 HIGH | 2 | `{"detail"}` vs `{"error": {"message"}}` |
| Duplicate endpoints | 🔴 HIGH | 3 pairs | `/billing/settings` vs `/me/billing`, `/subscription` vs `/me/subscription` |
| `/docs` exposed | 🔴 HIGH | 1 | Swagger UI + OpenAPI schema exposed in production |
| DB error as 500 not 503 | 🟡 MEDIUM | ~50 | "db not initialized" should be 503 |
| No API versioning strategy | 🟡 MEDIUM | 1 | Only OpenAI-compat endpoints versioned |
| Telegram link auth bypass | 🟡 MEDIUM | 1 | GET `/auth/telegram-link` gives session tokens based on tg_id alone |
| Raw `request.json()` in admin | 🟡 MEDIUM | 3 | No Pydantic validation on admin plan/package/user edit |
| URL path inconsistency | 🟡 MEDIUM | ~10 | Mixed singular/plural, verbs/nouns, prefix patterns |
| CORS vs cookies | 🟡 LOW | 1 | `allow_credentials=False` blocks cross-origin cookie auth |
| WebSocket token in URL | 🟢 LOW | 1 | Token in query param (minor log exposure risk) |
| Total endpoints | — | 109 | 108 HTTP + 1 WebSocket |

---

## 6. Endpoint Count by Category

| Category | Count | Auth Model |
|----------|-------|------------|
| Health & System | 5 | None (except /health/detailed = Admin) |
| Auth | 12 | None → Session |
| Admin Auth | 2 | Token → Admin Cookie |
| Chat | 4 | Session/API Key |
| Catalog | 2 | None |
| Conversations | 8 | Session |
| Memories | 5 | Session |
| Skills | 8 | Mixed (None/Session/Owner) |
| Wallet | 3 | Session |
| Billing | 4 | Session |
| Subscriptions & Plans | 11 | Mixed (None/Session) |
| Payment | 3 | Mixed (Session/None) |
| Notifications | 2 | Session |
| API Keys | 3 | Session |
| Tasks | 7 | Session |
| Referral | 1 | Session |
| Public Content | 3 | None |
| Admin Content Mgmt | 15 | Admin |
| Admin User Mgmt | 5 | Admin |
| Admin Export | 2 | Admin |
| WebSocket | 1 | Token query param |
| **Total** | **109** | |
