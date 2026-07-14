# SENIOR 7 — Docker & Infrastructure Deep Audit

**Auditor:** Hermes Agent (DevOps)  
**Date:** 2026-07-14  
**Scope:** `/root/multiai/` — all Docker infrastructure

---

## 1. Service Inventory

| Service | Image/Build | Status | Restart | Mem Limit | Health Check |
|---|---|---|---|---|---|
| multiai_pg | postgres:16-alpine | Up 8h (healthy) | unless-stopped | 1 GB | ✅ pg_isready |
| multiai_redis | redis:7-alpine | Up 8h | unless-stopped | 512 MB | ❌ None |
| multiai_litellm | ./backend/Dockerfile.litellm | Up 8h | unless-stopped | 2 GB | ❌ None |
| multiai_tunnel | ./infra/Dockerfile.tunnel | Up 8h | unless-stopped | 128 MB | ❌ None |
| multiai_api | ./backend/Dockerfile | Up 3h (healthy) | unless-stopped | 512 MB | ✅ urllib health/live |
| multiai_frontend | ./frontend/Dockerfile | Up 3h (healthy) | unless-stopped | 512 MB | ✅ fetch localhost:3000 |
| multiai_bot | ./bot/Dockerfile | exited (0) | on-failure:3 | 256 MB | ⚠️ PID1 check only |

---

## 2. Network Analysis

### ✅ All services on same network
All 7 services join `multiai_net` (bridge driver). DNS resolution works:
- `multiai_api`, `multiai_pg`, `multiai_redis`, `multiai_litellm`, `multiai_tunnel` — all resolvable by service name.

### Connectivity Tests — PASSED
```
frontend → multiai_api:8000/health/live  → {"status":"ok"} ✅
api → redis://multiai_redis:6379/0       → True ✅
```

### ⚠️ Ports exposed to 0.0.0.0
- `multiai_api` binds `0.0.0.0:8081` — accessible from all network interfaces
- `multiai_frontend` binds `0.0.0.0:3003` — accessible from all network interfaces
- **Risk:** If this host has a public IP, the API and frontend are exposed to the internet without a reverse proxy or firewall.
- **Recommendation:** Bind to `127.0.0.1` unless intentionally public, or use a reverse proxy (nginx/caddy) with TLS.

---

## 3. Volume Persistence

| Volume | Purpose | Persistent? |
|---|---|---|
| multiai_pg_data | PostgreSQL data | ✅ Named volume |
| multiai_redis_data | Redis AOF + RDB | ✅ Named volume, `--appendonly yes`, save 60 1 |

**Assessment:** Data volumes are properly configured. Redis has both AOF and periodic RDB snapshots.

---

## 4. Resource Limits

| Service | Limit | Assessment |
|---|---|---|
| multiai_pg | 1 GB | ✅ Reasonable for small workload |
| multiai_redis | 512 MB | ✅ Sufficient |
| multiai_litellm | 2 GB | ✅ Generous for proxy |
| multiai_tunnel | 128 MB | ✅ Minimal SSH tunnel |
| multiai_api | 512 MB | ⚠️ May be tight under load; no swap configured |
| multiai_frontend | 512 MB | ✅ Adequate for Next.js standalone |
| multiai_bot | 256 MB | ✅ Sufficient |

**Note:** No CPU limits set on any container. Under heavy load, containers could starve each other.

---

## 5. Dockerfile Audit

### backend/Dockerfile — GOOD
- ✅ Build stage: `requirements.txt` installed first for layer caching
- ✅ Non-root user: `appuser` created and used
- ✅ Health check: `urllib.request.urlopen('http://localhost:8000/health/live')`
- ✅ `--no-cache-dir` on pip install
- ⚠️ No multi-stage build (single stage is fine for Python, but final image includes build tools)
- ⚠️ `COPY . .` after pip install is correct ordering, but includes tests/docs in image

### frontend/Dockerfile — GOOD
- ✅ Multi-stage build (builder → production)
- ✅ Standalone output mode (`.next/standalone`)
- ✅ Non-root user: `node`
- ✅ Health check using `fetch('http://localhost:3000')`
- ⚠️ `npm install` without `npm ci` — may get non-deterministic builds
- ⚠️ No `.dockerignore` check — `COPY . .` may include `node_modules`, `.git`, etc.

### bot/Dockerfile — ISSUES
- ✅ Health check present
- ✅ `--no-cache-dir` on pip
- ❌ **Runs as root** — no `USER` directive
- ⚠️ Health check only checks PID 1 alive (`os.kill(1,0)`), doesn't verify bot is functional
- ⚠️ `COPY bot.py .` — no requirements layer caching optimization (requirements installed before copy, which is correct)

### infra/Dockerfile.tunnel — ISSUES
- ❌ **SSH key baked into image** — `COPY ssh_key /root/.ssh/id_ed25519`
- ❌ **SSH key file permissions 644** (world-readable) — should be 600
- ❌ **StrictHostKeyChecking=no** — vulnerable to MITM attacks
- ❌ **Hardcoded IP:** `89.169.55.129:22022`
- ⚠️ Runs as root
- ⚠️ Infinite retry loop with 5s sleep — no exponential backoff

---

## 6. Environment & Secrets Audit

### .env file
- ❌ **Permissions: 644** (world-readable) — should be `chmod 600`
- Secrets present: `POSTGRES_PASSWORD`, `ADMIN_PASS`, `ADMIN_TOKEN`, `BYNARA_API_KEY`, `BYNARA_API_KEY_2`, `TELEGRAM_BOT_TOKEN`
- All mounted read-only into API container: `./.env:/app/.env:ro` ✅

### Hardcoded values in docker-compose
- ❌ **`HTTP_PROXY` / `HTTPS_PROXY`:** `http://10.10.11.2:8888` — hardcoded private IP, set on `multiai_litellm` and `multiai_bot`
- ❌ **Tunnel endpoint:** `89.169.55.129` hardcoded in Dockerfile.tunnel
- ⚠️ Default passwords in `.env.example`: `CHANGE_ME_STRONG_PASSWORD` — acceptable for example, but ensure `.env` has real values

### Secrets in container environment
- `BYNARA_API_KEY` and `BYNARA_API_KEY_2` are passed via environment to litellm container — visible in `docker inspect`
- `ADMIN_PASS` and `ADMIN_TOKEN` visible in API container environment
- **Recommendation:** Use Docker secrets or a vault for production

---

## 7. Critical Bug: Frontend Client-Side API Calls

### ❌ NEXT_PUBLIC_API_URL = http://multiai_api:8000 breaks client-side fetch

**Location:** `frontend/components/Chat.tsx` line 33:
```javascript
const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
const res = await fetch(`${base}/v1/chat/completions`, { ... })
```

**Problem:** `NEXT_PUBLIC_*` vars are embedded at **build time** into the client-side JavaScript bundle. The value `http://multiai_api:8000` is a Docker-internal hostname that **does not resolve in the user's browser**.

**Impact:** The main chat feature (`Chat.tsx`) makes direct client-side fetch calls to `http://multiai_api:8000/v1/chat/completions` — this will fail for all browser users with a DNS resolution error.

**Workaround present but not used:** `next.config.js` defines rewrites that proxy `/v1/*` and `/api/*` to the backend. Server-side API routes (`app/api/chat/route.ts`) correctly use the internal URL. But `Chat.tsx` bypasses the proxy by using the full URL.

**Fix:** `Chat.tsx` should use a relative path (`/v1/chat/completions`) instead of `${base}/v1/chat/completions`, letting the Next.js rewrite proxy handle routing.

---

## 8. LiteLLM Configuration

### ✅ Correctly configured
- Config mounted as read-only volume: `./backend/litellm_config.yaml:/app/config.yaml:ro`
- API keys use `os.environ/BYNARA_API_KEY` pattern — correctly references env vars
- Two API key tiers: `BYNARA_API_KEY` (OpenRouter free models) and `BYNARA_API_KEY_2` (Bynara router paid models)
- `drop_params: true` — drops unsupported params instead of erroring
- `request_timeout: 90` — reasonable for LLM calls

### ⚠️ No health check on LiteLLM
- `depends_on: condition: service_started` — API starts even if LiteLLM isn't ready
- **Recommendation:** Add health check to LiteLLM and use `condition: service_healthy`

---

## 9. Bot Graceful Degradation

### ✅ Graceful exit when no token
```python
if not BOT_TOKEN or BOT_TOKEN == 'your-bot-token':
    print('⚠️  TELEGRAM_BOT_TOKEN not set or placeholder. Exiting gracefully.')
    sys.exit(0)
```

### ⚠️ Problem: exit(0) + on-failure:3
- Bot exits with code 0 (success) when token is missing
- Restart policy is `on-failure:3` — Docker won't restart on exit code 0
- **Result:** Bot silently stops and never restarts, even after token is configured
- **Current state:** Bot is `exited (0)` — confirms this behavior
- **Fix:** Either exit with non-zero code, or use `unless-stopped` restart policy

---

## 10. Dependency Audit (backend/requirements.txt)

### ❌ No pinned versions — all use minimum version constraints only
```
fastapi>=0.111        # unpinned
uvicorn[standard]     # unpinned
sqlalchemy[asyncio]   # unpinned
asyncpg               # unpinned
redis>=5              # unpinned
httpx                 # unpinned
pydantic>=2           # unpinned
pypdf>=4.0.0          # unpinned
python-multipart>=0.0.9  # unpinned
psutil>=5.9           # unpinned
```

**Risks:**
- Non-reproducible builds — different installs get different versions
- No `pip freeze` output or lock file found
- No pinned versions = no vulnerability baseline to audit against

**Recommendation:** Generate `requirements.lock` with exact versions via `pip freeze > requirements.lock` and use that for production builds.

---

## 11. Summary of Findings

### 🔴 Critical (2)
1. **Frontend Chat.tsx broken:** Client-side `fetch` uses Docker-internal hostname `http://multiai_api:8000` — browsers cannot resolve this. Chat feature is non-functional from the browser.
2. **SSH key in image with 644 perms:** `infra/ssh_key` baked into tunnel image, world-readable, `StrictHostKeyChecking=no`.

### 🟠 High (4)
3. **.env file permissions 644:** Secrets readable by all local users — should be 600.
4. **No pinned dependency versions:** Non-reproducible builds, no vulnerability baseline.
5. **Ports bound to 0.0.0.0:** API (8081) and frontend (3003) exposed to all interfaces.
6. **Bot restart policy mismatch:** Exit 0 + `on-failure:3` = bot never restarts after graceful exit.

### 🟡 Medium (5)
7. **No health check on Redis:** Dependent services can't wait for Redis readiness.
8. **No health check on LiteLLM:** API starts before LiteLLM is ready.
9. **Hardcoded IPs:** `10.10.11.2:8888` (proxy) and `89.169.55.129` (tunnel) in compose/Dockerfile.
10. **Bot runs as root:** No `USER` directive in bot Dockerfile.
11. **Secrets in environment:** API keys/passwords visible via `docker inspect`.

### 🟢 Low (3)
12. **No CPU limits:** Containers can starve each other under load.
13. **Frontend uses `npm install` instead of `npm ci`:** Non-deterministic builds.
14. **Tunnel retry loop:** No exponential backoff on SSH reconnect.

---

## 12. Recommendations (Priority Order)

1. **Fix Chat.tsx:** Change `fetch(\`${base}/v1/chat/completions\`)` → `fetch('/v1/chat/completions')` to use Next.js rewrite proxy.
2. **chmod 600 .env** and `chmod 600 infra/ssh_key`.
3. **Pin all dependencies** in requirements.txt or use a lock file.
4. **Add health checks** to Redis and LiteLLM services.
5. **Fix bot restart policy** — use `unless-stopped` or exit with non-zero code.
6. **Bind ports to 127.0.0.1** if behind a reverse proxy.
7. **Add USER directive** to bot Dockerfile.
8. **Move hardcoded IPs** to `.env` variables.
9. **Use Docker secrets** or a vault for production secrets.
10. **Add `.dockerignore`** to frontend build context.
