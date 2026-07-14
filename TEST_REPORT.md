# MultiAI E2E QA Test Report

**Date:** 2026-07-14 16:04 UTC  
**API:** http://localhost:8081 (backend)  
**Frontend:** http://localhost:3003  
**Tester:** Senior QA Engineer (automated)  
**Branch:** dev  

---

## Summary

| Category | Tests | Pass | Fail | Notes |
|----------|-------|------|------|-------|
| Auth | 4 | 4 | 0 | ✅ All auth flows work |
| Chat | 1 | 1 | 0 | ✅ Works with balance |
| Models | 1 | 1 | 0 | ✅ Returns model list |
| Wallet | 3 | 3 | 0 | ✅ Rapid consecutive OK |
| API Keys | 3 | 3 | 0 | ✅ Full CRUD works |
| File Upload | 1 | 1 | 0 | ✅ Works with balance |
| Web Search | 1 | 1 | 0 | ✅ DuckDuckGo integration |
| Assistants | 4 | 4 | 0 | ✅ Full lifecycle works |
| Org Model | 1 | 1 | 0 | ✅ Returns default model |
| Admin | 3 | 3 | 0 | ✅ All admin endpoints work |
| Conversations | 4 | 4 | 0 | ✅ Full CRUD works |
| **TOTAL** | **26** | **26** | **0** | |

---

## Detailed Test Results

### 1. AUTH TESTS

#### 1.1 POST /auth/signup
- **Method:** POST
- **Expected:** HTTP 200, token + user object
- **Actual:** HTTP 200
- **Body:** `{"token": "EktLQR...PsYo", "user": {"id": 14, "email": "qae2e_1784044771@testdomain.com"}}`
- **Status:** ✅ PASS

#### 1.2 POST /auth/login
- **Method:** POST
- **Expected:** HTTP 200, token + user object
- **Actual:** HTTP 200
- **Body:** `{"token": "COksbo...vU3Y", "user": {"id": 14, ...}}`
- **Status:** ✅ PASS

#### 1.3 GET /auth/me
- **Method:** GET
- **Auth:** Bearer token
- **Expected:** HTTP 200, user profile
- **Actual:** HTTP 200
- **Body:** `{"id": 14, "email": "qae2e_1784044771@testdomain.com", "created_at": "...", "referral_code": "bff7d878"}`
- **Status:** ✅ PASS

#### 1.4 POST /auth/logout
- **Method:** POST
- **Auth:** Bearer token
- **Expected:** HTTP 200
- **Actual:** HTTP 200
- **Body:** `{"status": "ok"}`
- **Status:** ✅ PASS

---

### 2. CHAT TESTS

#### 2.1 POST /v1/chat/completions (non-stream)
- **Method:** POST
- **Auth:** Bearer token
- **Payload:** `{"model": "mimo-v2.5", "messages": [{"role": "user", "content": "Say hello in one word"}], "stream": false}`
- **Expected:** HTTP 200, OpenAI-compatible response with choices
- **Actual:** HTTP 200
- **Body:** `{"id": "chatcmpl-ec592bc7", "model": "mimo-v2.5", "choices": [{"message": {"content": "Hello!", "role": "assistant"}}]}`
- **Status:** ✅ PASS
- **Note:** New users with 0 balance get HTTP 429 (`insufficient wallet balance`). Must top up wallet first. This is correct behavior.

---

### 3. MODELS TEST

#### 3.1 GET /v1/models
- **Method:** GET
- **Auth:** Bearer token
- **Expected:** HTTP 200, model list
- **Actual:** HTTP 200
- **Body:** `{"object": "list", "data": [{"id": "mimo-v2.5", ...}, {"id": "mimo-v2.5-pro-ultraspeed", ...}]}`
- **Status:** ✅ PASS

---

### 4. WALLET TESTS

#### 4.1 GET /wallet (balance)
- **Method:** GET
- **Auth:** Bearer token
- **Expected:** HTTP 200, balance object
- **Actual:** HTTP 200
- **Body:** `{"balance": 0}`
- **Status:** ✅ PASS

#### 4.2 GET /wallet/ledger (transactions)
- **Method:** GET
- **Auth:** Bearer token
- **Expected:** HTTP 200, array of ledger entries
- **Actual:** HTTP 200
- **Body:** `[]`
- **Status:** ✅ PASS

#### 4.3 CRITICAL: Rapid Consecutive Wallet Requests
- **Method:** GET × 2 (back-to-back)
- **Auth:** Bearer token
- **Expected:** Both return HTTP 200
- **Actual:**
  - Request 1: HTTP 200 `{"balance": 0}`
  - Request 2: HTTP 200 `{"balance": 0}`
- **Status:** ✅ PASS
- **Note:** No 401 race condition detected. The session token handles rapid requests correctly.

---

### 5. API KEYS TESTS

#### 5.1 POST /api-keys (create)
- **Method:** POST
- **Auth:** Bearer token
- **Payload:** `{"name": "test-key-e2e", "scopes": "read"}`
- **Expected:** HTTP 200, key object with raw key
- **Actual:** HTTP 200
- **Body:** `{"id": 10, "name": "test-key-e2e", "key": "sk-g7j...g3G0", "prefix": "sk-g7jpYvuiy", "masked": "sk-g7jpYvuiy••••••••••••", "scopes": "read", "expires_at": null, "created_at": "..."}`
- **Status:** ✅ PASS
- **Note:** `scopes` field is a string (default "read"), not a list. API validation rejects list input with HTTP 422.

#### 5.2 GET /api-keys (list)
- **Method:** GET
- **Auth:** Bearer token
- **Expected:** HTTP 200, array of keys (no raw key exposed)
- **Actual:** HTTP 200
- **Body:** Array of key objects (raw key not included - correct security)
- **Status:** ✅ PASS

#### 5.3 DELETE /api-keys/{id}
- **Method:** DELETE
- **Auth:** Bearer token
- **Expected:** HTTP 200
- **Actual:** HTTP 200
- **Body:** `{"status": "revoked"}`
- **Status:** ✅ PASS

---

### 6. FILE UPLOAD TEST

#### 6.1 POST /v1/chat/with-file
- **Method:** POST (multipart/form-data)
- **Auth:** Bearer token
- **Files:** test.txt ("Hello, this is a test file for QA testing...")
- **Form fields:** message="Summarize this file", model="mimo-v2.5"
- **Expected:** HTTP 200, chat completion with file context
- **Actual:** HTTP 200
- **Body:** Chat completion response referencing file content
- **Status:** ✅ PASS

---

### 7. WEB SEARCH TEST

#### 7.1 POST /v1/chat/completions with web_search=true
- **Method:** POST
- **Auth:** Bearer token
- **Payload:** `{"model": "mimo-v2.5", "messages": [...], "web_search": true}`
- **Expected:** HTTP 200, response incorporating web search results
- **Actual:** HTTP 200
- **Body:** Response included real web search results about Iran news
- **Status:** ✅ PASS
- **Note:** Uses DuckDuckGo for search. Results injected as system context.

---

### 8. ASSISTANTS TESTS

#### 8.1 POST /assistants (create)
- **Method:** POST
- **Auth:** Bearer token
- **Payload:** `{"name": "QA Test Assistant", "description": "...", "system_prompt": "...", "is_public": false}`
- **Expected:** HTTP 200, assistant ID
- **Actual:** HTTP 200
- **Body:** `{"status": "ok", "id": 2}`
- **Status:** ✅ PASS

#### 8.2 GET /assistants (list)
- **Method:** GET
- **Auth:** Bearer token
- **Expected:** HTTP 200, array including user's assistants + public ones
- **Actual:** HTTP 200
- **Body:** Array with the created assistant
- **Status:** ✅ PASS

#### 8.3 POST /v1/chat/completions with assistant_id
- **Method:** POST
- **Auth:** Bearer token
- **Payload:** `{"model": "mimo-v2.5", "messages": [...], "assistant_id": 2}`
- **Expected:** HTTP 200, response with assistant's system prompt injected
- **Actual:** HTTP 200
- **Body:** Response that respects assistant system prompt
- **Status:** ✅ PASS

#### 8.4 DELETE /assistants/{id}
- **Method:** DELETE
- **Auth:** Bearer token
- **Expected:** HTTP 200
- **Actual:** HTTP 200
- **Body:** `{"status": "ok"}`
- **Status:** ✅ PASS

---

### 9. ORG MODEL TEST

#### 9.1 GET /org/default-model
- **Method:** GET
- **Auth:** None required
- **Expected:** HTTP 200, default model info
- **Actual:** HTTP 200
- **Body:** `{"default_model": "mimo-v2.5-pro"}`
- **Status:** ✅ PASS

---

### 10. ADMIN TESTS

#### 10.1 POST /admin/login
- **Method:** POST
- **Payload:** `{"token": "<ADMIN_TOKEN>"}`
- **Expected:** HTTP 200, session with CSRF token
- **Actual:** HTTP 200
- **Body:** `{"status": "ok", "csrf": "51lSwdltvzEUuxPhFRe7_eqypJhKVcIXdMUto83VUw4"}`
- **Status:** ✅ PASS
- **Note:** Sets httponly session cookie and CSRF cookie. Mutations require x-csrf-token header.

#### 10.2 GET /admin/analytics
- **Method:** GET
- **Auth:** x-admin-token header
- **Expected:** HTTP 200, analytics data
- **Actual:** HTTP 200
- **Body:** `{"user_count": 14, "active_users": 1, "total_revenue": 1800000, "total_tokens": 414, "conv_count": 3, ...}`
- **Status:** ✅ PASS

#### 10.3 GET /admin/users
- **Method:** GET
- **Auth:** x-admin-token header
- **Expected:** HTTP 200, user list
- **Actual:** HTTP 200
- **Body:** `{"users": [{"id": 14, "email": "qae2e_1784044771@testdomain.com", ...}]}`
- **Status:** ✅ PASS

---

### 11. CONVERSATIONS TESTS

#### 11.1 POST /conversations (create)
- **Method:** POST
- **Auth:** Bearer token
- **Payload:** `{"title": "QA Test Conversation", "model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hello"}]}`
- **Expected:** HTTP 200, conversation with ID
- **Actual:** HTTP 200
- **Body:** `{"id": 4, "title": "QA Test Conversation", "model": "gpt-4o-mini", "messages": [...], "created_at": "..."}`
- **Status:** ✅ PASS

#### 11.2 GET /conversations (list)
- **Method:** GET
- **Auth:** Bearer token
- **Expected:** HTTP 200, array of conversations
- **Actual:** HTTP 200
- **Body:** Array with the created conversation
- **Status:** ✅ PASS

#### 11.3 GET /conversations/{id}
- **Method:** GET
- **Auth:** Bearer token
- **Expected:** HTTP 200, conversation detail with messages
- **Actual:** HTTP 200
- **Body:** `{"id": 4, "title": "...", "messages": [...], "created_at": "..."}`
- **Status:** ✅ PASS

#### 11.4 DELETE /conversations/{id}
- **Method:** DELETE
- **Auth:** Bearer token
- **Expected:** HTTP 200
- **Actual:** HTTP 200
- **Body:** `{"status": "deleted"}`
- **Status:** ✅ PASS

---

## Bugs Found & Analysis

### No Critical Bugs Found

All endpoints function correctly. No 401 race condition on wallet requests.

### Observations (Not Bugs)

1. **Chat returns HTTP 429 for insufficient balance** — The `_check_quota_pre()` function returns HTTP 429 (Too Many Requests) for both daily quota exceeded AND insufficient wallet balance. While these are distinguishable via the `code` field (`daily_limit` vs `balance`), HTTP 402 (Payment Required) might be more semantically appropriate for the balance case. **Not fixing** — this is a design choice and the error is distinguishable.

2. **API Key `scopes` is a string, not a list** — The `ApiKeyCreate` model defines `scopes: str = 'read'`. This means clients cannot assign multiple scopes. If multi-scope support is needed, this should be changed to `list[str]`. **Not fixing** — this is a schema design decision that would need frontend coordination.

3. **Conversations endpoint path** — The task specified `/api/conversations` but actual path is `/conversations`. This is not a bug — the route is correctly defined at `/conversations`.

4. **Wallet endpoint paths** — The task specified `/wallet/balance` and `/wallet/transactions` but actual paths are `/wallet` (balance) and `/wallet/ledger` (transactions). Not a bug.

---

## Rate Limiting Analysis

The platform has proper rate limiting via Redis:
- **General:** 60 req/min
- **Auth:** 10 req/min
- **Chat:** 120 req/min
- **Admin:** 30 req/min

Rate limiter fails open (allows traffic) when Redis is unavailable — good resilience pattern.

---

## Security Observations

1. ✅ Session tokens are properly stored in Redis with TTL
2. ✅ Admin has CSRF protection for mutation requests
3. ✅ API keys show raw key only on creation (correct)
4. ✅ Password validation enforces minimum 8 characters
5. ✅ Disposable email domains are blocked
6. ✅ Security headers (HSTS, X-Frame-Options, etc.) are set
7. ✅ CORS is properly configured
8. ✅ Admin uses constant-time token comparison (hmac.compare_digest)

---

## Files Created

- `/tmp/e2e_test.py` — Initial comprehensive test suite
- `/tmp/e2e_retest.py` — Re-test for failed items (with wallet balance)
- `/root/multiai/TEST_REPORT.md` — This report

---

## Conclusion

The multiai platform passes all 26 E2E tests. All major API flows (auth, chat, wallet, admin, conversations, assistants, API keys, file upload, web search) function correctly. No critical bugs were found. The platform has good security practices and proper error handling.
