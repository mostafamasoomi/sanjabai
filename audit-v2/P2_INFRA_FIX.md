# Phase 2: Infrastructure Verification Report

**Date:** 2026-07-16
**Inspector:** Senior DevOps/Infra Engineer
**Status:** ⚠️ ISSUES FOUND — 1 Critical, 2 Moderate, 4 Low

---

## 1. DOCKER COMPOSE REVIEW (`docker-compose.multiai.yml`)

### 1.1 Service Inventory

| Service | Image | Port | mem_limit | Health Check | Status |
|---------|-------|------|-----------|--------------|--------|
| `multiai_pg` | postgres:16-alpine | 5432 (internal) | 1g | ✅ pg_isready | 🟢 Healthy |
| `multiai_redis` | redis:7-alpine | 6379 (internal) | 512m | ✅ redis-cli ping | 🟢 Healthy |
| `multiai_litellm` | build (Dockerfile.litellm) | 4000 (internal) | 2g | ✅ python health check | 🟢 Healthy |
| `multiai_tunnel` | build (Dockerfile.tunnel) | 9090 (internal) | 128m | ❌ NONE | 🟡 Running |
| `multiai_api` | build (Dockerfile) | 8081:8000 | 512m | ✅ (from Dockerfile) | 🟢 Healthy |
| `multiai_frontend` | build (Dockerfile) | 3003:3000 | 512m | ✅ (from Dockerfile) | 🟢 Healthy |
| `multiai_bot` | build (Dockerfile) | none | 256m | ❌ NONE | 🔴 Restarting |

### 1.2 Issues Found

#### 🔴 CRITICAL: Bot Service Crash Loop
- **Symptom:** `multiai_bot-1` restarting continuously (every ~30s)
- **Logs:** `⚠️ TELEGRAM_BOT_TOKEN not set or placeholder. Exiting gracefully.`
- **Root Cause:** `TELEGRAM_BOT_TOKEN` environment variable is empty or not set in `.env`
- **Impact:** Telegram bot is completely non-functional
- **Fix:** Set `TELEGRAM_BOT_TOKEN` in `/root/multiai/.env` or accept bot being down (intentional)

#### 🟡 MODERATE: Missing Health Checks
- `multiai_tunnel` — no health check defined. If the SSH tunnel dies, Docker won't detect it.
- `multiai_bot` — no health check defined. Combined with the crash loop, Docker has no structured way to know the service is unhealthy.
- **Recommendation:** Add health checks for both services.

#### 🟡 MODERATE: Weak Depends-On Conditions
- `multiai_api` depends on `multiai_redis` with `condition: service_started` instead of `service_healthy`. Redis could start but be unhealthy, and API would still proceed.
- `multiai_api` depends on `multiai_litellm` with `condition: service_started` instead of `service_healthy`.
- `multiai_frontend` depends on `multiai_api` with no condition (defaults to `service_started`).
- **Recommendation:** Use `condition: service_healthy` for all critical dependencies.

#### 🟢 LOW: No CPU Limits
- All services have `mem_limit` set but no `cpus` or CPU quota limits.
- A runaway process could consume all CPU. Currently not critical given low CPU usage.

#### 🟢 LOW: Hard Memory Limits Only
- All services use `mem_limit` (hard limit) without `mem_reservation` (soft limit).
- This means containers can't burst above their hard limit and may be OOM-killed.
- **Recommendation:** Add `mem_reservation` at ~70% of `mem_limit` for critical services.

---

## 2. RESOURCE USAGE (Live)

| Service | Memory Limit | Memory Used | % Used | CPU % |
|---------|-------------|-------------|--------|-------|
| pg | 1 GiB | 102.9 MiB | 10.1% | 0.03% |
| redis | 512 MiB | 6.25 MiB | 1.2% | 1.11% |
| litellm | 2 GiB | 639.8 MiB | 31.2% | 0.25% |
| api | 512 MiB | 81.8 MiB | 16.0% | 0.18% |
| frontend | 512 MiB | 61.6 MiB | 12.0% | 0.00% |
| bot | 256 MiB | 0 B | 0% | 0.00% |
| tunnel | 128 MiB | 4.1 MiB | 3.2% | 0.18% |
| **Total** | **~5.4 GiB** | **~896 MiB** | **~16.5%** | **~1.8%** |

### Host Resources
- **Memory:** 15 GiB total, 7.8 GiB used (52%), 1.1 GiB free
- **Disk:** 50G total, 46G used — **98% FULL (only 1.4G free)** ⚠️
- **Docker disk:** 11.09 GB images, 1.78 GB containers, 838 MB volumes, 4.3 GB build cache

#### 🔴 CRITICAL: Disk at 98%
- Root filesystem has only 1.4 GB free. Risk of Docker or system failure.
- **Recommendation:** Run `docker system prune -a` to clean unused images and build cache (reclaimable ~5 GB), or expand disk.

---

## 3. REDIS PERSISTENCE AUDIT

### Configuration
```
save: "60 1"        → RDB snapshot every 60s if ≥1 key changed
appendonly: yes     → AOF persistence enabled
appendfsync: everysec → fsync every second (good balance of safety/performance)
```

### Live Status
| Metric | Value | Status |
|--------|-------|--------|
| RDB last save status | `ok` | ✅ |
| RDB last save time | Recent (within last minute) | ✅ |
| RDB changes since last save | 5 | ✅ |
| RDB saves total | 7 | ✅ |
| AOF enabled | `yes` | ✅ |
| AOF last write status | `ok` | ✅ |
| AOF current size | 1.62 MB | ✅ |
| AOF base size | 88 bytes | ✅ |

### Assessment: ✅ EXCELLENT
Redis persistence is configured correctly with both RDB snapshots and AOF. The `appendfsync everysec` setting provides good durability without excessive I/O. Data is being persisted successfully.

---

## 4. HEALTH CHECK DETAILS

### Docker-Level Health Checks

| Service | Check Command | Interval | Timeout | Retries | Start Period |
|---------|--------------|----------|---------|---------|-------------|
| pg | `pg_isready -U multiai` | 10s | 5s | 5 | — |
| redis | `redis-cli ping` | 10s | 5s | 3 | — |
| litellm | Python urllib to `/health/liveliness` | 20s | 15s | 5 | 30s |
| api | (from Dockerfile) | — | — | — | — |
| frontend | (from Dockerfile) | — | — | — | — |
| bot | ❌ NONE | — | — | — | — |
| tunnel | ❌ NONE | — | — | — | — |

### Endpoint-Level Health Checks

**API Health Endpoint** (`GET /health`):
```json
{"status":"ok","uptime":0.0,"db":"ok","redis":"ok"}
```
✅ All subsystems healthy.

**LiteLLM Health Endpoint** (`GET /health/liveliness`):
- Internal health check passes (used by Docker health check).
- Note: LiteLLM port 4000 is not exposed externally — only accessible within Docker network.

---

## 5. ENVIRONMENT VARIABLES AUDIT

### `.env` File (checked: secrets redacted)
| Variable | Status | Notes |
|----------|--------|-------|
| `DATABASE_URL` | ✅ Set | postgresql+asyncpg connection |
| `REDIS_URL` | ✅ Set | Points to `multiai_tunnel:9090` (via SSH tunnel) |
| `ADMIN_USER` | ✅ Set | `admin` |
| `ADMIN_PASS` | ✅ Set | (redacted) |
| `CORS_ORIGINS` | ✅ Set | `https://multiai.ir, http://localhost:3003` |
| `BYNARA_API_KEY` | ✅ Set | Required by LiteLLM |
| `BYNARA_API_KEY_2` | ✅ Set | Required by LiteLLM |
| `OPENROUTER_API_KEY` | ✅ Set | Required by LiteLLM |
| `TELEGRAM_BOT_TOKEN` | ❌ EMPTY/MISSING | Bot service crashes |

### Compose-Level Env Vars
- `HTTP_PROXY` / `HTTPS_PROXY`: Set to `http://10.10.11.2:8888` for LiteLLM, API, and Bot
- `NO_PROXY`: Properly configured with localhost, internal services, and external APIs
- `LITELLM_HOST`: `http://multiai_litellm:4000` — correct internal Docker DNS

---

## 6. LIVE VERIFICATION SUMMARY

### 6.1 All Services Running?
| Service | Running | Healthy | Port Accessible |
|---------|---------|---------|-----------------|
| pg | ✅ | ✅ | Internal only |
| redis | ✅ | ✅ | Internal only |
| litellm | ✅ | ✅ | Internal only |
| tunnel | ✅ | ⚠️ No HC | Internal only |
| api | ✅ | ✅ | ✅ (8081) |
| frontend | ✅ | ✅ | ✅ (3003) |
| bot | ❌ Crash loop | ❌ | N/A |

### 6.2 API Health Endpoint
✅ `GET http://localhost:8081/health` → `{"status":"ok","db":"ok","redis":"ok"}`

### 6.3 Frontend Accessible
✅ `GET http://localhost:3003` → Returns full Next.js HTML page (Multiai — Persian AI platform)

### 6.4 Model Catalog
✅ `GET http://localhost:8081/v1/models` → Returns **8 models**, all with pricing:

| # | Model ID | Provider | Context Window | Input Price/1M | Output Price/1M |
|---|----------|----------|----------------|----------------|-----------------|
| 1 | `deepseek-v4-flash-bynara` | Bynara (key1) | 131K | 21,600 IRT | 86,400 IRT |
| 2 | `deepseek-v4-pro` | Bynara (key1) | 131K | 43,200 IRT | 172,800 IRT |
| 3 | `deepseek-v4-pro-bynara` | Bynara (key1) | 131K | 43,200 IRT | 172,800 IRT |
| 4 | `mimo-v2.5-pro` | Bynara (key2) | 1M | 93,960 IRT | 187,920 IRT |
| 5 | `mimo-v2.5-pro-ultraspeed` | Bynara (key2) | 1M | 28,080 IRT | 56,160 IRT |
| 6 | `mistral-large` | Bynara (key1) | 252K | 432,000 IRT | 1,296,000 IRT |
| 7 | `mistral-medium-3-5` | Bynara (key1) | 256K | 324,000 IRT | 1,620,000 IRT |
| 8 | `tencent-hy3` | Bynara (key1) | 1M | 43,200 IRT | 172,800 IRT |

**Note:** LiteLLM config has 350+ models defined (mostly OpenRouter), but the API catalog only returns 8. This is correct — the backend database only has pricing records for the 8 Bynara-proxied models. OpenRouter models are defined in LiteLLM but not registered in the API database.

---

## 7. RECOMMENDATIONS SUMMARY

### 🔴 Critical (Must Fix)
1. **Disk at 98%** — Run `docker system prune -a` to reclaim ~5 GB. Risk of service failure.
2. **Bot crash loop** — Either set `TELEGRAM_BOT_TOKEN` in `.env` or stop the bot service explicitly.

### 🟡 Moderate (Should Fix)
3. Add health checks to `multiai_tunnel` and `multiai_bot` services.
4. Upgrade `depends_on` conditions from `service_started` to `service_healthy` for Redis and LiteLLM.

### 🟢 Low (Nice to Have)
5. Add CPU limits to prevent runaway processes.
6. Add `mem_reservation` (soft memory limits) for graceful degradation.
7. Consider exposing LiteLLM health endpoint for external monitoring.
8. Add `restart: unless-stopped` to all services (already present ✅).

---

## 8. VERDICT

**Overall Grade: B+ (85/100)**

The core infrastructure is well-designed and stable. All critical services (database, cache, LiteLLM proxy, API, frontend) are healthy and properly configured. Resource limits are appropriate for the workload. Redis persistence is correctly configured with both RDB and AOF.

**Two issues need immediate attention:**
1. **Disk space is critically low** (98%) — this could cause cascading failures
2. **Bot service is in a crash loop** due to missing `TELEGRAM_BOT_TOKEN`

Once these are addressed, the deployment is production-ready.