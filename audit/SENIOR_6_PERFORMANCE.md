# SENIOR 6 — Performance & Optimization Audit

**Auditor:** Senior Performance Engineer  
**Date:** 2026-07-14  
**Scope:** Backend, Frontend, Docker, Network performance  
**Status:** NO modifications made (read-only audit)

---

## Executive Summary

The multiai platform is functional and reasonably performant for its current scale. Health check responds in **14ms**, frontend in **26ms**. However, there are several performance anti-patterns that will bite as traffic grows. The most critical issues are: **synchronous Redis calls in an async FastAPI app**, **missing database indexes on heavily-queried columns**, **no response compression**, and **no response caching for catalog/content endpoints**.

| Severity | Count |
|----------|-------|
| 🔴 Critical | 3 |
| 🟠 High | 5 |
| 🟡 Medium | 6 |
| 🟢 Low | 4 |

---

## 1. Backend Performance

### 1.1 🔴 Synchronous Redis in Async Context (Critical)

**File:** `backend/app.py`, line 36  
**Issue:** `redis.Redis.from_url()` creates a **synchronous** Redis client. This client is used throughout the app (23+ call sites) inside `async def` handlers. Every `rds.get()`, `rds.setex()`, `rds.ping()`, `rds.delete()` call **blocks the event loop**.

**Impact:** Under concurrent load, one slow Redis call blocks ALL other requests. With ~135 async endpoints, this is a scalability bottleneck.

**Evidence:**
- Line 36: `rds = redis.Redis.from_url(REDIS_URL, decode_responses=True)` — synchronous client
- Lines 1705-1736: Session management uses `rds.get/setex/delete/expire/expire` — all synchronous
- Line 536: `rds.ping()` in `/health/ready` — blocks event loop
- Lines 2008-2026: `logout-all` iterates tokens with sync `rds.delete()` in a loop

**Fix:** Use `redis.asyncio.Redis.from_url()` or `aioredis`. Replace all `rds.get()` with `await rds.get()`.

---

### 1.2 🔴 Missing Database Indexes (Critical)

Several heavily-queried tables lack indexes on columns used in WHERE clauses:

| Table | Column | Used In | Index? |
|-------|--------|---------|--------|
| `conversations` | `user_id` | `/conversations`, `/conversations/search` | ❌ NO |
| `conversations` | `user_id, updated_at` | List + sort | ❌ NO |
| `quota` | `user_id` | Every chat request (`_check_quota_pre`) | ❌ NO |
| `pricing` | `model` | `_track_usage`, `_bill_stream_usage` | ❌ NO (UNIQUE on baseline but versioned table lacks it) |
| `model_catalog` | `provider_model_id` | `_track_usage` price lookup | ❌ NO |
| `api_keys` | `key_hash` | `_get_user_id` auth lookup | ❌ NO |

**Impact:** Sequential scans on `conversations` and `quota` tables under load. The `conversations` table is created by SQLAlchemy ORM (not in migrations), so it has no explicit indexes at all.

**Fix:** Add migration with:
```sql
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_quota_user ON quota(user_id);
CREATE INDEX IF NOT EXISTS idx_model_catalog_provider_model_id ON model_catalog(provider_model_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
```

---

### 1.3 🔴 Conversation Search: N+1 / Full-Table Scan Pattern (Critical)

**File:** `backend/app.py`, lines 2240-2286  
**Issue:** `search_conversations` executes **two queries**: one for title ILIKE, then fetches **200 rows** to iterate all messages in Python:

```python
res2 = await session.execute(
    Conversation.__table__.select()
    .where(Conversation.user_id == uid)
    .order_by(Conversation.updated_at.desc())
    .limit(200)  # Loads 200 full conversation objects with JSONB messages
)
all_rows = res2.fetchall()
for r in all_rows:
    msgs = r.messages or []  # Python-side filtering of JSONB
    for msg in msgs:
        if q.lower() in (msg.get('content', '') or '').lower():
```

**Impact:** Loads potentially megabytes of JSONB data into Python memory for every search. O(n*m) complexity.

**Fix:** Use PostgreSQL JSONB containment or `jsonb_to_recordset` + text search, or add a `tsvector` column on conversation messages.

---

### 1.4 🟠 No Connection Pool Configuration (High)

**File:** `backend/app.py`, line 433  
**Issue:** Engine created with defaults only:
```python
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
```

No `pool_size`, `max_overflow`, `pool_recycle`, or `pool_timeout` configured. SQLAlchemy defaults: pool_size=5, max_overflow=10.

**Impact:** Under load, only 5+10=15 concurrent DB connections allowed. Could cause "QueuePool limit" errors.

**Fix:** Add explicit pool config:
```python
engine = create_async_engine(
    DATABASE_URL, echo=False, pool_pre_ping=True,
    pool_size=10, max_overflow=20, pool_recycle=300, pool_timeout=30
)
```

---

### 1.5 🟠 No Response Caching (High)

**Issue:** No caching layer exists for frequently-read, rarely-changed endpoints:
- `/catalog/models` — hits DB on every request (line 663: `SELECT * FROM model_catalog`)
- `/catalog/pricing` — same pattern
- `/content/features` — DB query on every request
- `/content/discounts` — DB query on every request
- `/about` — DB query on every request
- `/org/default-model` — DB query on every request

**Impact:** Unnecessary DB load for data that changes rarely (admin-only mutations).

**Fix:** Cache in Redis with 60-300s TTL, invalidate on admin mutations. Example:
```python
cached = rds.get('cache:catalog:models')
if cached:
    return JSONResponse(json.loads(cached))
# ... fetch from DB ...
rds.setex('cache:catalog:models', 120, json.dumps(result))
```

---

### 1.6 🟠 No Response Compression (High)

**Issue:** No GZip/Brotli middleware configured on FastAPI. The `app.py` has no `GZipMiddleware` import or configuration.

**Impact:** JSON responses (catalog, conversations, analytics) are sent uncompressed. The `/catalog/models` endpoint returns ~5-15KB of JSON uncompressed.

**Fix:** Add `from fastapi.middleware.gzip import GZipMiddleware` and:
```python
app.add_middleware(GZipMiddleware, minimum_size=500)
```

---

### 1.7 🟠 SELECT * Queries (High)

**Issue:** Multiple `SELECT * FROM ...` raw SQL queries that fetch all columns:

- Line 663: `SELECT * FROM model_catalog ORDER BY provider, id`
- Line 3649: `SELECT * FROM plans WHERE id = :pid AND active = true`
- Line 3665: `SELECT * FROM credit_packages WHERE active = true`
- Lines 3703, 3771, 3784, 3837, 3967, 4047: Additional `SELECT *`

**Impact:** Fetches unnecessary columns (including large JSONB fields) when only specific fields are needed. Wastes memory and network.

**Fix:** Select only needed columns.

---

### 1.8 🟠 Streaming Implementation (High)

**File:** `backend/app.py`, lines 1073-1108  
**Assessment:** The streaming implementation is **correct** — uses `async for line in r.aiter_lines()` and yields lines. However:

1. **Line 1097:** `yield f"{line}\n\n"` — yields raw SSE line which is good.
2. **Lines 1102-1106:** Billing happens in `finally` block after stream ends — this is correct and non-blocking.
3. **Memory injection** (lines 1056-1071) does a DB query per stream start — acceptable.

**Minor issue:** Each SSE chunk is parsed with `json.loads()` to extract usage data (line 1091). This adds overhead per chunk during streaming.

---

### 1.9 🟡 Health Check Makes DB Connections (Medium)

**Files:** Lines 524-541 (`/health/ready`), 544-559 (`/health`)  
**Issue:** Each health check creates a new DB connection:
```python
async with engine.connect() as _:
    pass
```

And calls `rds.ping()` synchronously.

**Impact:** Health checks (called every 30s by Docker) create unnecessary connection overhead. Under high health-check frequency, this adds up.

---

### 1.10 🟡 Lazy Import of psutil (Medium)

**File:** Line 567: `import psutil` inside `health_detailed` handler.  
**Assessment:** This is actually **good** — lazy import avoids loading psutil at startup. However, the import happens on every admin health check call. Should be cached at module level after first import.

---

### 1.11 🟡 Duplicate Query Logic in _track_usage and _bill_stream_usage (Medium)

**Files:** Lines 1110-1188 (`_track_usage`) and 1190-1262 (`_bill_stream_usage`)  
**Issue:** These two functions contain nearly identical logic (quota update, price lookup, balance check, ledger deduction, metering). Code duplication increases maintenance risk and the chance of divergence.

---

### 1.12 🟡 get_user_id Makes DB Query for API Keys (Medium)

**File:** Lines 1849-1868  
**Issue:** Every API key auth triggers a SELECT + UPDATE on `api_keys` table (to update `last_used`). This adds latency to every authenticated request using API keys.

**Fix:** Update `last_used` asynchronously (fire-and-forget) or batch updates.

---

## 2. Frontend Performance

### 2.1 🟢 Bundle Size (Good)

**Measurement:**
```
.next/           = 5.7 MB (standalone)
.next/static/    = 1.8 MB
node_modules/    = 58.4 MB (not shipped in standalone)
```

**Assessment:** The standalone bundle is **5.7MB** which is reasonable. The frontend uses Next.js standalone output mode correctly. Node modules are not shipped in the container (standalone mode copies only needed files).

**Note:** The `.next/standalone/` directory doesn't exist in the container despite being referenced in Dockerfile — the container runs from `.next/` directly. This means the Dockerfile COPY fails silently and the container runs the dev-style build. **This is a bug but not a performance blocker.**

---

### 2.2 🟡 useCatalog Hook: No Deduplication (Medium)

**File:** `frontend/lib/useCatalog.ts`  
**Issue:** The `useCatalog()` hook fetches `/api/catalog/models` on every mount. If multiple components use `useCatalog()`, multiple identical API calls are made.

Currently used in: `Chat.tsx`, `app/chat/page.tsx`, and likely other pages.

**Fix:** Use a global cache (SWR, React Query, or a simple module-level cache):
```typescript
let cachedPromise: Promise<CatalogResponse> | null = null;
function fetchCatalog() {
  if (!cachedPromise) {
    cachedPromise = fetch('/api/catalog/models').then(r => r.json());
  }
  return cachedPromise;
}
```

---

### 2.3 🟡 Limited Use of React.memo (Medium)

**Assessment:** The codebase uses `useCallback` extensively (40+ instances across all files), which is good. However:
- Only 2 components use `dynamic()` for code splitting: `AdminPanel` and `Playground`
- No `React.memo` usage found on any component
- The `Chat.tsx` (basic) component re-renders all message rows on every state change

**Impact:** Moderate — React's reconciliation handles most cases fine for the current message count, but could matter with long conversations.

---

### 2.4 🟡 No Image Optimization (Medium)

**Issue:** The `public/` directory is minimal (116KB, fonts + manifest only). No `<Image>` from `next/image` usage detected — the app appears to be text-heavy with SVG icons, which is fine.

However, there's no `next/image` configuration for external images if any are added later.

---

### 2.5 🟢 Large Imports (Good)

**Assessment:** The frontend correctly uses:
- `dynamic()` for `AdminPanel` and `Playground` (lazy loading)
- Tree-shakeable icon imports via `@/components/ui/Icon`
- No obvious barrel-file anti-patterns

**Note:** The main `chat/page.tsx` is 1022 lines — this is a monolithic component that could benefit from splitting, but it's not a performance issue per se.

---

### 2.6 🟢 Next.js Configuration (Good)

**File:** `frontend/next.config.js`
- `reactStrictMode: true` ✓
- `poweredByHeader: false` ✓
- Security headers configured ✓
- Bundle analyzer available via `ANALYZE=true` ✓
- API rewrites configured for backend proxy ✓

---

## 3. Docker Performance

### 3.1 🟡 Backend Dockerfile: No Multi-Stage Build (Medium)

**File:** `backend/Dockerfile`
```dockerfile
FROM python:3.11-slim
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
```

**Issue:** Single-stage build. The final image contains pip cache, build tools, etc. No multi-stage to reduce image size.

**Frontend Dockerfile** is correctly multi-stage (builder → production).

**Fix:** Use multi-stage:
```dockerfile
FROM python:3.11-slim AS builder
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
COPY --from=builder /install /usr/local
COPY . .
```

---

### 3.2 🟢 Resource Limits (Good)

**From `docker-compose.multiai.yml`:**

| Service | Limit | Actual Usage | Headroom |
|---------|-------|-------------|----------|
| multiai_frontend | 512MiB | 52.8MiB (10.3%) | ✅ 90% free |
| multiai_api | 512MiB | 94.9MiB (18.5%) | ✅ 82% free |
| multiai_pg | 1GiB | 41.7MiB (4.1%) | ✅ 96% free |
| multiai_litellm | 2GiB | 1.0GiB (50.1%) | ⚠️ Half used |
| multiai_redis | 512MiB | 4.8MiB (0.9%) | ✅ 99% free |
| multiai_tunnel | 128MiB | 6.0MiB (4.7%) | ✅ 95% free |

**Assessment:** Resource limits are well-configured with healthy headroom. LiteLLM at 50% is the tightest — monitor under peak load.

---

### 3.3 🟢 Layer Caching (Good)

**Frontend Dockerfile:** Correctly separates `COPY package.json` from `COPY . .` to leverage Docker layer caching for npm install.

**Backend Dockerfile:** Same pattern — `COPY requirements.txt` before `COPY . .`. Good.

---

## 4. Network Performance

### 4.1 🔴 No Response Compression (Critical)

**Measurement:**
```
curl -sI http://localhost:8081/health/live
→ No Content-Encoding header
→ No Accept-Encoding in response
```

**Backend:** No GZip/Brotli middleware. All API responses sent uncompressed.

**Frontend:** Next.js standalone server handles compression internally for static assets. The `Vary: Accept-Encoding` header is present on frontend responses, and `x-nextjs-cache: HIT` confirms caching works.

---

### 4.2 🟡 Keep-Alive Configuration (Medium)

**Backend:** uvicorn default keep-alive (no explicit configuration).  
**Frontend:** `Connection: keep-alive` with `Keep-Alive: timeout=5` present. ✓

**httpx client** (line 435): Properly configured:
```python
_http = httpx.AsyncClient(
    timeout=httpx.Timeout(90, connect=10),
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
)
```

---

### 4.3 🟢 API Response Times (Good)

| Endpoint | Response Time |
|----------|--------------|
| `GET /health/live` | **14ms** |
| `GET /` (frontend) | **26ms** |

Both are well within acceptable thresholds.

---

## 5. Measured Resource Usage

```
CONTAINER                     CPU%    MEM USAGE/LIMIT         MEM%
multiai-multiai_frontend-1    0.00%   52.8MiB / 512MiB       10.31%
multiai-multiai_api-1         0.22%   94.88MiB / 512MiB      18.53%
multiai-multiai_pg-1          17.48%  41.65MiB / 1GiB         4.07%
multiai-multiai_litellm-1     0.21%   1.002GiB / 2GiB        50.10%
multiai-multiai_redis-1       1.01%   4.824MiB / 512MiB       0.94%
multiai-multiai_tunnel-1      0.00%   6.008MiB / 128MiB       4.69%
```

**Observations:**
- PostgreSQL CPU spike at 17.48% — likely due to recent queries or background work. Monitor.
- LiteLLM at 50% memory — needs monitoring under sustained load.
- All other services well within limits.

---

## 6. Prioritized Recommendations

### Immediate (P0 — Fix Before Scale)

1. **Replace synchronous Redis with async redis client** — blocks event loop on every request
2. **Add missing database indexes** — `conversations.user_id`, `quota.user_id`, `model_catalog.provider_model_id`
3. **Add GZip middleware** — free 60-80% bandwidth reduction on JSON responses

### Short-term (P1 — Next Sprint)

4. **Cache catalog/content endpoints in Redis** — reduce DB load for read-heavy public endpoints
5. **Configure SQLAlchemy connection pool** — prevent QueuePool exhaustion under load
6. **Fix conversation search** — replace Python-side JSONB iteration with PostgreSQL text search
7. **Backend Dockerfile multi-stage build** — reduce image size

### Medium-term (P2 — Technical Debt)

8. **Deduplicate _track_usage / _bill_stream_usage** — extract shared pricing logic
9. **Add React.memo to message list items** — prevent unnecessary re-renders in long conversations
10. **Use SWR/React Query for useCatalog** — deduplicate API calls across components
11. **Make last_used API key update async** — reduce auth latency
12. **Select specific columns instead of SELECT *** — reduce data transfer

---

## 7. Positive Findings

✅ Async SQLAlchemy with proper `asyncpg` driver  
✅ httpx connection pooling configured (20 max, 10 keepalive)  
✅ Streaming implementation uses proper `async for` with `aiter_lines`  
✅ Frontend uses Next.js standalone mode for minimal production bundle  
✅ Frontend Dockerfile is multi-stage  
✅ Resource limits well-configured with healthy headroom  
✅ `useCallback` used extensively (40+ instances) to prevent re-renders  
✅ Dynamic imports for heavy components (AdminPanel, Playground)  
✅ `pool_pre_ping=True` on SQLAlchemy engine (stale connection detection)  
✅ Rate limiting middleware with Redis-backed sliding window  
✅ Security headers middleware  
✅ Docker layer caching optimized in Dockerfiles  
✅ Frontend static assets properly cached (`Cache-Control: s-maxage=31536000`)  
✅ Health check responses in 14ms  

---

*End of Performance Audit — SENIOR 6*
