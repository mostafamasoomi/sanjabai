# Multiai Backend API Review Report

**Generated:** 2026-07-15  
**Base URL:** http://127.0.0.1:8081  
**Backend:** FastAPI (Uvicorn) with PostgreSQL, Redis, LiteLLM proxy  
**Total Endpoints Tested:** 98 unique endpoints across 17 groups  

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total endpoint groups | 17 |
| Total unique endpoints | ~98 |
| Critical bugs (500 errors) | 2 |
| Auth bypass issues | 1 (design-level) |
| Internal error leaks | 1 |
| Minor issues | 3 |
| Overall health | Good — core flows work correctly |

---

## 🐛 Critical Bugs

### 1. `GET /conversations/analytics` — 500 Internal Server Error
- **Status:** ❌ BROKEN
- **HTTP Status:** 500
- **Response:** `{"detail": "analytics error: Object of type Decimal is not JSON serializable"}`
- **Root Cause:** PostgreSQL `SUM(charged_amount)` returns `Decimal` type. The `JSONResponse` serializer cannot handle Python `Decimal` objects.
- **Fix:** Convert Decimal values to `float` before returning, or use a custom JSON encoder:
  ```python
  total_cost = float(usage_row.total_cost) if usage_row else 0
  # And similarly for all Decimal fields in models_used and daily_usage
  ```

### 2. `GET /me/billing` — 500 Internal Server Error
- **Status:** ❌ BROKEN
- **HTTP Status:** 500
- **Response:** `Internal Server Error` (plain text, not JSON)
- **Root Cause:** The endpoint uses `select(UserBillingSetting)` (ORM-style) which returns SQLAlchemy `Row` objects. Attribute access (`billing.user_id`) fails because ORM `select()` rows wrap the entity differently than `Model.__table__.select()`.
- **Comparison:** `GET /billing/settings` works correctly — it uses `UserBillingSetting.__table__.select()` (table-level select).
- **Fix:** Change line 4395 from `select(UserBillingSetting).where(...)` to `UserBillingSetting.__table__.select().where(...)`, or access the entity via `billing[0].user_id`.

---

## ⚠️ Security & Design Issues

### 3. `GET /assistants` — No Auth Required (By Design)
- **Status:** ⚠️ BY DESIGN
- **HTTP Status:** 200 (returns public assistants for unauthenticated users)
- **Analysis:** The endpoint intentionally allows unauthenticated access to view public assistants. Authenticated users see their own + public. Not a bug, but worth documenting that this is a public endpoint.

### 4. `GET /skills` — No Auth Required (By Design)
- **Status:** ⚠️ BY DESIGN
- **HTTP Status:** 200 (returns public skill templates)
- **Analysis:** Same pattern as assistants — public listing endpoint. `GET /skills/my` correctly requires auth (returns 401).

### 5. `POST /v1/smart-chat` — Internal Error Leak
- **Status:** ⚠️ BUG
- **HTTP Status:** 401
- **Response:** `{"error": {"message": "litellm.AuthenticationError: AuthenticationError: OpenrouterException - {\"error\":{\"message\":..."}}`
- **Issue:** Exposes internal LiteLLM and OpenRouter error details including stack traces and provider-specific error messages.
- **Fix:** Catch authentication errors from LiteLLM and return a generic message like "LLM provider authentication failed. Please try again later."

### 6. `PUT /auth/profile` — Very Limited Field Support
- **Status:** ⚠️ DESIGN LIMITATION
- **HTTP Status:** 400 (when sending `name` field)
- **Response:** `{"detail": "فیلد معتبری برای بروزرسانی وجود ندارد"}`
- **Analysis:** Only the `phone` field is accepted for updates (line 2166: `allowed = {'phone'}`). The `name`, `email`, and other profile fields cannot be updated via this endpoint.
- **Recommendation:** Expand allowed fields or document the limitation clearly.

---

## ✅ Endpoint Group Results

### Health Endpoints
| Endpoint | Method | Status | Auth Required | Notes |
|----------|--------|--------|---------------|-------|
| `/health/live` | GET | ✅ 200 | No | Returns `{"status":"ok"}` |
| `/health/ready` | GET | ✅ 200 | No | Returns `{"status":"ok"}` |
| `/health` | GET | ✅ 200 | No | Returns uptime, db, redis status |
| `/health/detailed` | GET | ⚠️ 401 | **Admin** | Requires admin auth — inconsistent with other health endpoints |
| `/` | GET | ✅ 200 | No | Service info |

### Auth Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/auth/signup` | POST | ✅ 200/409 | Returns token+user on success, 409 on duplicate email |
| `/auth/login` | POST | ✅ 200/401 | Returns token+user on success |
| `/auth/me` | GET | ✅ 200/401 | Returns user profile |
| `/auth/change-password` | POST | ✅ 200/422 | Uses `current_password` field (not `old_password`) |
| `/auth/forgot-password` | POST | ✅ 200 | Always returns 200 (prevents email enumeration) |
| `/auth/reset-password` | POST | ✅ 400 | Returns 400 for invalid token |
| `/auth/profile` | PUT | ⚠️ 400 | Only accepts `phone` field |
| `/auth/logout` | POST | ✅ 200 | Invalidates current session |
| `/auth/logout-all` | POST | ✅ 200 | Revokes all sessions |
| `/auth/telegram-link` | POST | ✅ 200 | Links Telegram ID |
| `/auth/telegram-token` | POST | ✅ 401 | Requires telegram auth (correct) |
| `/auth/send-welcome` | POST | ✅ 200 | Queues welcome email |

### Wallet Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/wallet` | GET | ✅ 200 | Returns balance |
| `/wallet/ledger` | GET | ✅ 200 | Returns transaction history |
| `/wallet/topup` | POST | ✅ 422 | Requires `payment_order_id` field |

### API Keys Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/api-keys` | POST | ✅ 200 | Creates key, returns full key (shown once) |
| `/api-keys` | GET | ✅ 200 | Lists keys with masked values |
| `/api-keys/{id}` | DELETE | ✅ 200 | Revokes key |

### Conversations Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/conversations` | POST | ✅ 200 | Creates conversation |
| `/conversations` | GET | ✅ 200 | Lists with pagination |
| `/conversations/search` | GET | ✅ 200 | Full-text search works |
| `/conversations/analytics` | GET | ❌ 500 | **Decimal serialization bug** |
| `/conversations/{id}` | GET | ✅ 200/404 | Get single conversation |
| `/conversations/{id}` | PUT | ✅ 200 | Update title etc. |
| `/conversations/{id}` | DELETE | ✅ 200 | Delete conversation |
| `/conversations/{id}/export` | GET | ✅ 200 | Export with messages |

### Assistants Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/assistants` | POST | ✅ 200 | Creates assistant |
| `/assistants` | GET | ✅ 200 | Lists user's + public (no auth = public only) |
| `/assistants/{id}` | GET | ✅ 200/404 | Get single |
| `/assistants/{id}` | PUT | ✅ 200 | Update |
| `/assistants/{id}` | DELETE | ✅ 200 | Delete |

### Skills Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/skills` | GET | ✅ 200 | Public skill templates (no auth required) |
| `/skills/my` | GET | ✅ 200/401 | User's skills (auth required) |
| `/skills` | POST | ✅ 200/422 | Create skill (requires `title`) |
| `/skills/{id}` | GET | ✅ 200/404 | Get single |
| `/skills/{id}` | PUT | ✅ 200 | Update |
| `/skills/{id}` | DELETE | ✅ 200 | Delete |
| `/skills/{id}/rate` | POST | ✅ 200 | Rate skill |
| `/skills/{id}/use` | POST | ✅ 200 | Record usage |

### Catalog & Models
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/catalog/models` | GET | ✅ 200 | Returns model catalog with providers |
| `/catalog/pricing` | GET | ✅ 200 | Returns pricing data |
| `/v1/models` | GET | ✅ 200 | OpenAI-compatible model list |
| `/content/features` | GET | ✅ 200 | Content features |
| `/content/discounts` | GET | ✅ 200 | Available discount codes |

### V1 Chat Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/v1/chat/completions` | POST | ✅ 400 | Validates model name, returns clear error for invalid |
| `/v1/chat/with-file` | POST | ✅ 422 | Requires `file` field |
| `/v1/smart-chat` | POST | ⚠️ 401 | **Leaks internal LiteLLM errors** |

### Memory Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/memories` | POST | ✅ 200 | Create memory entry |
| `/memories` | GET | ✅ 200/401 | List memories |
| `/memories/search` | GET | ✅ 200 | Search memories |
| `/memories/{id}` | PUT | ✅ 200 | Update |
| `/memories/{id}` | DELETE | ✅ 200 | Delete |

### Tasks Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/tasks` | POST | ✅ 200/422 | Create task (requires `prompt`) |
| `/tasks` | GET | ✅ 200/401 | List tasks |
| `/tasks/{id}` | PUT | ✅ 200/422 | Update |
| `/tasks/{id}` | DELETE | ✅ 200 | Delete |
| `/tasks/{id}/toggle` | POST | ✅ 200 | Toggle active state |
| `/tasks/{id}/run` | POST | ✅ 200 | Manual trigger |
| `/tasks/{id}/executions` | GET | ✅ 200 | Execution history |

### Subscription & Billing
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/plans` | GET | ✅ 200 | List all plans |
| `/plans/{id}` | GET | ✅ 200/404 | Get plan details |
| `/credit-packages` | GET | ✅ 200 | List packages |
| `/credit-packages/{id}` | GET | ✅ 200/404 | Get package details |
| `/subscribe` | POST | ✅ 200 | Subscribe to plan |
| `/subscription` | GET | ✅ 200 | Get current subscription |
| `/subscription/cancel` | POST | ✅ 200 | Cancel subscription |
| `/subscription/renew` | POST | ✅ 200 | Renew subscription |
| `/subscription/checkout` | POST | ✅ 200 | Create checkout session |
| `/credit-package/checkout` | POST | ✅ 200 | Package checkout |
| `/billing/settings` | GET | ✅ 200 | Get billing settings (auto-creates defaults) |
| `/billing/settings` | PUT | ✅ 200 | Update billing settings |
| `/me/subscription` | GET | ✅ 200 | User's subscription status |
| `/me/billing` | GET | ❌ 500 | **SQLAlchemy ORM bug** |
| `/me/billing` | PUT | ✅ 200 | Update billing |
| `/me/usage` | GET | ✅ 200 | Daily usage stats |

### Payment Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/payment/request` | POST | ✅ 200 | Initiate payment |
| `/payment/callback` | GET | ✅ 200 | Payment callback handler |
| `/payment/history` | GET | ✅ 200 | Payment history |

### Notification Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/notifications` | GET | ✅ 200/401 | List notifications |
| `/notifications/{id}/read` | POST | ✅ 200/422 | Mark as read |

### Referral Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/referral/stats` | GET | ✅ 200/401 | Referral code, count, URL |

### Organization Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/org/default-model` | GET | ✅ 200 | Returns default model |

### About Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/about` | GET | ✅ 200 | About page content |
| `/admin/about` | POST | ✅ 200 | Update about (admin) |

### Admin Endpoints
| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/admin/login` | POST | ✅ 200 | Admin token auth |
| `/admin/logout` | POST | ✅ 200 | Admin logout |
| `/admin/users` | GET | ✅ 200 | List all users |
| `/admin/users/{id}/ban` | POST | ✅ 200 | Ban user |
| `/admin/users/{id}` | PUT | ✅ 200 | Update user |
| `/admin/pricing` | GET | ✅ 200 | Get pricing rules |
| `/admin/pricing` | POST | ✅ 200 | Set pricing rule |
| `/admin/features` | GET | ✅ 200 | List features |
| `/admin/features` | POST | ✅ 200 | Create feature |
| `/admin/features/{id}` | DELETE | ✅ 200 | Delete feature |
| `/admin/discounts` | GET | ✅ 200 | List discounts |
| `/admin/discounts` | POST | ✅ 200 | Create discount |
| `/admin/discounts/{id}` | DELETE | ✅ 200 | Delete discount |
| `/admin/proxy` | GET | ✅ 200 | Get proxy config |
| `/admin/proxy` | POST | ✅ 200 | Set proxy config |
| `/admin/org-default-model` | POST | ✅ 200 | Set default model |
| `/admin/analytics` | GET | ✅ 200 | Dashboard analytics |
| `/admin/export/ledger` | GET | ✅ 200 | Export ledger CSV |
| `/admin/export/users` | GET | ✅ 200 | Export users CSV |
| `/admin/plans` | GET | ✅ 200 | List plans |
| `/admin/plans` | POST | ✅ 200 | Create plan |
| `/admin/credit-packages` | GET | ✅ 200 | List packages |
| `/admin/credit-packages` | POST | ✅ 200 | Create package |
| `/admin/subscriptions` | GET | ✅ 200 | List subscriptions |

---

## Auth Enforcement Summary

| Endpoint | No-Auth Result | Expected | Status |
|----------|---------------|----------|--------|
| `/auth/me` | 401 | 401 | ✅ |
| `/wallet` | 401 | 401 | ✅ |
| `/wallet/ledger` | 401 | 401 | ✅ |
| `/api-keys` | 401 | 401 | ✅ |
| `/conversations` | 401 | 401 | ✅ |
| `/assistants` | 200 | Public | ✅ (by design) |
| `/skills/my` | 401 | 401 | ✅ |
| `/skills` | 200 | Public | ✅ (by design) |
| `/memories` | 401 | 401 | ✅ |
| `/tasks` | 401 | 401 | ✅ |
| `/notifications` | 401 | 401 | ✅ |
| `/me/usage` | 401 | 401 | ✅ |
| `/referral/stats` | 401 | 401 | ✅ |
| `/admin/users` (user token) | 401 | 401/403 | ✅ |
| `/admin/users` (no auth) | 401 | 401 | ✅ |

**Auth enforcement is solid.** All user-specific endpoints correctly require authentication. Admin endpoints reject regular user tokens. Two endpoints (`/assistants`, `/skills`) are intentionally public.

---

## Response Format Consistency

### Success Responses
Most endpoints return consistent JSON. Common patterns:
- `{"status": "ok"}` for mutations (create/update/delete)
- Direct object for reads: `{"id": ..., "name": ...}`
- Lists for collections: `[{...}, {...}]`
- Some use `{"items": [...]}` for paginated results

### Error Responses
- Most use `{"detail": "..."}` with localized (Persian) messages
- Validation errors: `{"detail": [{"type": "...", "loc": [...], "msg": "..."}]}`
- **Inconsistency:** `/me/billing` 500 returns plain text, not JSON
- **Inconsistency:** `/v1/chat/*` endpoints use OpenAI-style `{"error": {"message": "..."}}` format

---

## Rate Limiting

- **Limit:** 60 requests/minute per IP (visible in `X-Ratelimit-Limit: 60` header)
- **Remaining:** Tracked via `X-Ratelimit-Remaining` header
- **Response:** 429 Too Many Requests
- **Note:** Rate limiting hit during testing — some endpoints that appeared as 429 in initial test run were actually working correctly when tested with proper delays.

---

## Recommendations

### P0 — Fix Immediately
1. **Fix `/conversations/analytics` 500:** Convert all `Decimal` values to `float` before JSON serialization
2. **Fix `/me/billing` 500:** Use `Model.__table__.select()` instead of ORM `select()` for consistent row access, or add error handling

### P1 — Fix Soon
3. **Sanitize `/v1/smart-chat` errors:** Don't expose internal LiteLLM/OpenRouter error details
4. **Expand `PUT /auth/profile`:** Allow updating at least `name` and potentially `email`

### P2 — Improve
5. **Standardize error response format:** All endpoints should return JSON with consistent `{"detail": "..."}` or `{"error": {"message": "..."}}`
6. **Add pagination to list endpoints:** `/api-keys`, `/assistants`, `/skills`, `/notifications` return full arrays without pagination
7. **Document public vs. protected endpoints** in API docs (Swagger/OpenAPI)
8. **`/health/detailed` auth:** Consider making this public or at least available to any authenticated user (not just admin)

### P3 — Nice to Have
9. Add API versioning (e.g., `/v1/auth/login`)
10. Add request ID tracking in responses
11. Consider English error messages alongside Persian for API consumers
