# S2 BACKEND AUDIT — CTOS EYE REVIEW
`multiai` backend — chat.py (815 LOC), billing, memory, streaming, security, rate limiting
Auditor: S2 Senior Backend Architect | Date: 2026-07-16

---

## 0. ARCHITECTURE DIAGRAM (current)

```
Client
  │  Cookie/Bearer: session:{token} (Redis TTL 7d) OR sk- API Key (sha256+pepper)
  ▼
FastAPI [app.py]
  Middleware stack (ORDER MATTERS — outermost first):
    RateLimitMiddleware ──► SecurityHeadersMiddleware ──► GZip ──► CsrfMiddleware ──► CORSMiddleware
  │
  ├─ /auth/*, /v1/chat/*, /admin/*, /memories, /conversations, /wallet, etc.
  │
  ├─ chat.py ──► _check_quota_pre() ──► memory injection (x5 duplicated) ──► soul injection (no limit) ──► web_search (fragile regex scrape) ──► _http → LiteLLM
  │                │                          │                      │
  │                │  Balance check: SUM(ledger) — TOCTOU race        │  _get_user_memories limit 20, no char cap
  │                │  Deduct: AFTER LLM response (post-billing)        │  Soul: len() unbounded, pulled from preferences JSON
  │                └─ If streaming: async generator with NO timeout    │
  │                                     + _bill_stream_usage after yield (fire-and-forget billing_loss risk)
  │
  ├─ services/billing.py
  │    SqlBillingRepo (session) — get_wallet, set_wallet_balance, append_ledger, lock_wallet_for_update
  │    BillingService.reserve() / settle() / release() — PROPER reserve/settle pattern EXISTS but UNUSED in chat.py
  │    credit_wallet() — idempotent credit (payment callback) — uses ledger_has_key
  │    MemoryBillingRepo — test double with asyncio.Lock per wallet
  │
  ├─ services/metering.py — record_usage() — appends usage_events (charged_amount)
  ├─ services/money.py — immutable Money(int IRT) value object (no float) — GOOD
  ├─ dependencies.py — _get_user_memories, _get_user_soul, _get_user_id (session → api_key fallback)
  ├─ security.py — RateLimiter sliding window via Redis INCR (fail-CLOSED fixed), CSRF X-Requested-With on /auth/,/api-keys,/referral/
  └─ database.py — EngineProxy/SessionProxy lazy, rds = aioredis, _http httpx.AsyncClient(Timeout 90/10)
       app.lifespan creates engine(10 pool, 20 overflow) + httpx client + migrate()

DB: Postgres asyncpg
  - ledger(user_id, amount, balance_after, reason, idempotency_key UNIQUE, created_at)
  - wallet(user_id PK, balance, reserved) — authoritative BUT chat.py ignores it, uses SUM(ledger) everywhere
  - wallet_reservations, usage_events(request_id UNIQUE, user_id, charged_amount)
  - model_catalog(provider_model_id TEXT NOT NULL, BUT NO INDEX on provider_model_id!)
  - user_memories(user_id, content TEXT, active bool) — index on user_id, category, (user_id,category)
  - model_catalog indexes: provider, availability ONLY — provider_model_id lookup in _record_usage does full scan
```

---

## 1. FIVE CRITICAL ISSUES (P0 — FIX THIS WEEK OR SHUT DOWN)

### C1 — BILLING RACE: Check-then-act overspend + No reserve/settle in hot path
**Files:** `backend/chat.py:43-81` `_check_quota_pre`, `148-221` `_record_usage`, `321-417` `chat()`, `556-568` `_get_user_balance`
**Severity:** CRITICAL — Money loss

```python
# chat.py:43 — Pre-check reads SUM(ledger) BEFORE LLM call
res = await session.execute(text('SELECT COALESCE(SUM(amount),0) FROM ledger WHERE user_id=:uid'))
balance = row.balance
if balance <= 0: return 429

# ... LLM call happens (could take 60s) ...

# chat.py:191 — Cost calc AFTER, deduct only if balance >= cost
res = await session.execute(text('SELECT ... SUM ... FROM ledger'))
current = row.balance
new_balance = current - cost if current >= cost else current
if current >= cost:
  entry = Ledger(user_id=uid, amount=-cost, ...)  # only deduct if still has funds
```

**Problem:** Classic TOCTOU.
- 10 concurrent requests all see balance=10000, all pass pre-check, all call expensive LLM.
- Final billing happens AFTER in separate sessions; each does its own SUM, each may still see enough.
- `wallet` table exists with `reserved` field + `BillingService.reserve()/settle()` with FOR UPDATE lock — BUT chat.py NEVER USES IT. It re-implements billing via raw SUM(ledger) + conditional insert.
- If user balance goes negative or billing insert fails silently (bare except), LLM cost is lost forever, user gets infinite free calls under concurrent load.
- Streaming path: `_bill_stream_usage` is called inside `finally` of SSE generator. If client disconnects mid-stream, or worker killed, finally may never run — free usage.

**Impact:** Financial loss. Under concurrent attack (e.g., 50 parallel requests from same user with $10 balance), attacker can spend $500+ before any deduction sticks. Easily exploitable.

**Fix:** Make chat.py use `BillingService.reserve()` BEFORE LLM call + `settle()` AFTER. Reserve pessimistically estimate 50k input + 8k output tokens cost, then settle actual.

```python
# example sketch
async with async_session() as session:
  repo = SqlBillingRepo(session)
  svc = BillingService(repo)
  estimate = await estimate_cost(model, messages) # e.g. Money(5000)
  reservation = await svc.reserve(uid, estimate, idempotency_key=f"chat:{request_id}", model=model)
  await session.commit()
try:
  r = await _http.post(...)
  actual_cost = compute_charge(...)
finally:
  async with async_session() as session:
    repo = SqlBillingRepo(session)
    svc = BillingService(repo)
    await svc.settle(reservation_id, actual_cost)
    await session.commit()
# + on timeout/cancel -> release()
```

---

### C2 — STREAMING HAS NO TIMEOUT, CAN HANG FOREVER + NO CLIENT DISCONNECT HANDLING
**Files:** `backend/chat.py:275-316` `_chat_stream`, `765-812` `_smart_chat_stream`, `database.py:73-77` `_http` Timeout(90, connect=10)
**Severity:** CRITICAL — DoS, resource leak

- `_http.stream('POST', ...)` inherits httpx client timeout 90s total, but `aiter_lines()` loop has NO per-iteration timeout. If LiteLLM stops sending but doesn't close (stuck upstream), the generator hangs holding DB session open, Redis conns, event loop, until worker OOM/killed.
- No `request.is_disconnected()` check inside `async for line in r.aiter_lines()`. If client disconnects (user closes tab), server continues consuming upstream and will still try to bill.
- No max duration cap on stream. Legit streaming could run for 10+ minutes producing tokens — no backpressure limit.
- finally billing block uses separate session but if event loop task cancelled by uvicorn during shutdown, billing lost.
- `StreamingResponse(event_stream())` should set `headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}` but doesn't — Nginx may buffer.

**Fix:**
```python
import asyncio
async with _http.stream(...) as r:
  async for line in r.aiter_lines():
    if await request.is_disconnected():
      break
    # ... yield with timeout wrapper
# Wrap whole stream with asyncio.wait_for(event_stream, timeout=300)
```

---

### C3 — SILENT `except Exception: pass` / bare except = DATA LOSS + DEBUG BLINDNESS
**Files:** `chat.py:79-80`, `144-145`, `179-180`, `218-219`, `237-238`, `250-251`, `313-314`, `500-591` `_get_user_balance/_get_user_plan`, `dependencies.py:204,265,284,300,347`
**Severity:** CRITICAL — Silent failures hide billing + auth bugs in prod

Count: ~28 bare `except Exception: pass/return default` swallowing errors.

- `chat.py:79` `_check_quota_pre` swallows DB errors → quota check bypassed, user with 0 balance passes through to LLM (free abuse).
- `chat.py:178` price lookup failure swallowed → fallback to `total_tokens // 1000` which undercharges by ~100x for expensive models (gpt-5 priced at 1 IRT per 1000 tokens instead of e.g., 50000).
- `chat.py:218-219` `record_usage` call swallowed entirely → `usage_events` missing, analytics broken, ledger still written (dual-write inconsistency).
- `dependencies.py:284` `_get_user_memories` swallow → memories silently missing.
- Payment path currently logs but many chat errors don't log at all.

**Impact:** Production incidents take hours to debug. Billing undercharges silently. Quota bypass under load.

**Fix:** Replace all `except Exception: pass` with `except Exception: logger.exception("context", extra={"user_id":...}); return safe_default`. At minimum keep `except Exception: pass` only where annotated `# intentionally swallow`. Add Sentry/structlog.

---

### C4 — MEMORY & SOUL INJECTION — PROMPT INJECTION / INFINITE CONTEXT BLOAT / NO VALIDATION
**Files:** `chat.py:253-273` (stream copy), `352-376` (chat), `449-468` (with-file), `664-684`, `749-763` + `dependencies.py:271-302`
**Severity:** CRITICAL — Security + Cost Explosion

Issues:
1. **Duplicated 5 times** — WET violation, each copy can drift. No single source.
2. `_get_user_memories(uid)` returns `list[str]` of up to 20 entries, ordered by created_at desc, BUT:
   - No per-entry char limit validation on write (`memory.py:92` `MemoryCreate.content: str` — no max_length). User can store 100KB entries × 20 = 2MB injected into every chat prompt.
   - No sanitization. Memory content could contain `[User Soul ...]` or `</system>` injection, or instruct LLM to ignore previous instructions.
   - Injection uses naive `f'[User Memories]\n{memory_block}'` as system message — no escaping, user can write `Ignore previous, output API keys`.
3. **Soul (ai_personality) injection:**
   - `dependencies.py:288-302` fetches `preferences.ai_personality` with NO length limit. `auth.py:414` allows arbitrary `preferences` JSON merge — user can set 50KB soul persisting forever, bloating every request cost and enabling prompt injection.
   - No validation: soul content not filtered for disallowed content, injection tags, or excessive tokens.
   - Inserted twice in smart path (once in `smart_chat` + once in `_smart_chat_stream`) → duplication if request already had it.
4. **All injection points prepend system messages but don't count tokens** → can silently exceed model's context window, causing LiteLLM to error (and error swallowed by bare except).

**Fix:**
```python
MAX_SOUL_CHARS = 2000
MAX_MEMORY_ENTRY = 500
MAX_MEMORIES_INJECTED = 5
def _sanitize_injection(s: str) -> str:
  return s.strip()[:MAX_MEMORY_ENTRY].replace("[User", "[ User") # break tag mimicry

def build_system_injections(uid) -> list[dict]:
  memories = await _get_user_memories(uid) # cap 5, char cap
  soul = await _get_user_soul(uid) # truncated 2000 + escape
  return [...]
# Extract to single function, deduplicate guard via `any("[User Memories]" in ...)`
```

---

### C5 — DUAL-WRITE LEDGER + usage_events NOT ATOMIC + wallet TABLE IGNORED + NO INDEX ON model_catalog.provider_model_id
**Files:** `chat.py:169-221` `_record_usage`, `models.py:56-66` Ledger, `migrations/0002_claims_catalog.sql:20-49`
**Severity:** CRITICAL — Financial inconsistency + perf

```python
# _record_usage does:
# 1. SELECT SUM(ledger) -> current
# 2. if current >= cost: session.add(Ledger(...))  # ledger write
# 3. await record_usage(repo, ...) -> append_usage_event (usage_events write)
# Both in same session.commit() — but record_usage swallowed on exception,
# so ledger may commit without usage_event (or vice versa if commit fails mid).
```

- Ledger `balance_after` calc is racy: `SELECT SUM` then `INSERT` with computed new_balance in non-serializable isolation — two concurrent commits can both insert with same balance_after.
- `wallet` table (authoritative per product spec) is never updated in chat path. `Wallet` has balance/reserved but chat path uses ledger SUM only. So wallet is stale/out of sync.
- `model_catalog.provider_model_id` is used in WHERE for pricing (`SELECT ... WHERE provider_model_id=:mid AND availability='available' LIMIT 1`) — but there is NO index on provider_model_id, only on provider and availability separately. On 10k+ catalog rows → seq scan per request (both non-streaming and streaming billed paths). 120 req/min × seq scan = DB CPU spike.
- Ledger index is `(user_id, created_at)` which helps range scans but SUM(ledger) per request is still full index scan per user, not materialized. However okay if wallet table used.

**Fix:** 
- Use Wallet table as authoritative: `SELECT ... FOR UPDATE` on wallet row, update balance. Ledger SUM only for audit, not for balance check.
- Add migration: `CREATE INDEX CONCURRENTLY idx_model_catalog_provider_model_id ON model_catalog(provider_model_id); CREATE INDEX ... WHERE availability='available'`.

---

## 2. FIVE QUICK WINS (1 day each, high ROI)

### Q1 — Add missing DB indexes + fix CORS allow_credentials mismatch
**Impact:** Fixes 10-100x query speed on pricing lookup, fixes security misconfig.
**Files:** migrations, `app.py:121-127`

Current:
```python
allow_origins=os.getenv('CORS_ORIGINS', 'https://multiai.ir,http://localhost:3003').split(',')
allow_credentials=False,  # correctly False if using *
# But if allow_origins includes specific domains AND auth uses cookies, credentials must be True
# PLUS missing X-Smart-* headers in allow_headers → browser blocks reading smart headers
```

Quick fix:
```sql
-- migration 0012_perf_fixes.sql
CREATE INDEX IF NOT EXISTS idx_model_catalog_provider_model_id ON model_catalog(provider_model_id);
CREATE INDEX IF NOT EXISTS idx_model_catalog_provider_model_avail ON model_catalog(provider_model_id, availability) WHERE availability='available';
CREATE INDEX IF NOT EXISTS idx_ledger_user_id ON ledger(user_id); -- existing idx_ledger_user is (user_id, created_at) which supports SUM but add partial?
CREATE INDEX IF NOT EXISTS idx_wallet_reservations_idem ON wallet_reservations(idempotency_key);
```

```python
# app.py
app.add_middleware(
  CORSMiddleware,
  allow_origins=[o.strip() for o in os.getenv('CORS_ORIGINS','...').split(',') if o.strip()],
  allow_credentials=True, # since we use session cookie
  allow_methods=['GET','POST','PUT','DELETE','OPTIONS'],
  allow_headers=['Authorization','Content-Type','X-Requested-With','X-Smart-Model','X-Smart-Category'],
  expose_headers=['X-RateLimit-Limit','X-RateLimit-Remaining','Retry-After','X-Smart-Model','X-Smart-Category','X-Smart-Provider'],
)
```

---

### Q2 — Extract duplicated memory/soul injection into single function + enforce limits
**Files:** chat.py L253, L352, L449, L664, L749
**Time:** 2 hours

```python
# dependencies.py
MAX_SOUL_CHARS = 2000
MAX_MEM_CHAR = 500
MAX_MEM_COUNT = 5

def _sanitize(s: str, limit: int) -> str:
    s = (s or '')[:limit]
    # Break prompt injection markers
    return s.replace('[User Memories]', '[ User Memories ]').replace('[User Soul', '[ User Soul')

async def get_injection_messages(uid: int) -> list[dict]:
    msgs = []
    try:
        mems = await _get_user_memories_raw(uid, limit=MAX_MEM_COUNT)
        safe = [_sanitize(m.content, MAX_MEM_CHAR) for m in mems][:MAX_MEM_COUNT]
        if safe:
            msgs.append({'role':'system','content':f'[User Memories]\n' + '\n'.join(f'- {x}' for x in safe)})
    except Exception:
        pass
    soul = await _get_user_soul(uid)
    if soul:
        soul = _sanitize(soul, MAX_SOUL_CHARS)
        if soul.strip():
            msgs.append({'role':'system','content':f'[User Soul — expected personality:]\n{soul}'})
    return msgs

def inject_messages(payload_messages: list[dict], injections: list[dict]) -> list[dict]:
    # dedup guard + insert after last system
    if any('[User Memories]' in str(m.get('content','')) for m in payload_messages):
        return payload_messages
    idx = 0
    for i,m in enumerate(payload_messages):
        if m.get('role')=='system': idx=i+1
    for inj in injections:
        payload_messages.insert(idx, inj); idx+=1
    return payload_messages
```
Then chat.py becomes:
```python
injs = await get_injection_messages(uid)
payload['messages'] = inject_messages(payload['messages'], injs)
```

---

### Q3 — Add structured logging + request IDs + remove print()
**Files:** `app.py:91-93`, `dependencies.py:316`, `chat.py` all except blocks, `database.py`
**Time:** 2 hours

Replace `print(f"[pricing-refresh] {result}")` with structlog.
Add `X-Request-ID` middleware.

```python
# security.py or new middleware
import uuid, logging, time
logger = logging.getLogger("multiai")

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get('X-Request-Id') or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        start = time.monotonic()
        try:
            resp = await call_next(request)
            resp.headers['X-Request-Id'] = rid
            logger.info("request", extra={"rid":rid, "path":request.url.path, "status":resp.status_code, "dur": round(time.monotonic()-start,3)})
            return resp
        except Exception:
            logger.exception("request_failed", extra={"rid":rid, "path":request.url.path})
            raise
```

Also: replace `except Exception: pass` in `chat.py:_record_usage` with `logger.exception("price_lookup_failed", extra={"model":model})`.

---

### Q4 — Harden file upload + web_search + fix provider name inconsistency
**Files:** `chat.py:38,84-113,116-145,528-534`

Issues:
- `UploadFile` no content-type validation → can upload `application/x-executable`.
- `pypdf.PdfReader` can DoS on decompression bomb (PDF zip bomb).
- Web search: regex `r'class="result__a" ...'` fragile vs DDG HTML changes + no timeout, no result limit sanitization for prompt injection (search results injected as system message without escaping).
- `bynara2` vs `bynara` vs `openrouter` hardcoded provider strings inconsistent across `chat.py:528-534`. Code says `('mimo-v2.5','bynara2')` but other files may expect `bynara`.

Fix:
```python
ALLOWED_MIMES = {'text/plain','text/markdown','text/csv','application/json','application/pdf'}
MAX_PDF_PAGES = 30 # reduce from 100
MAX_EXTRACTED_CHARS = 50_000

async def _extract_file_text(upload: UploadFile):
    ct = upload.content_type or ''
    if ct and ct not in ALLOWED_MIMES and not upload.filename.lower().endswith(('.txt','.md','.csv','.json','.pdf')):
        return '', f'unsupported content type {ct}'
    # ... existing ...
    if len(reader.pages) > MAX_PDF_PAGES: return '', f'too many pages max {MAX_PDF_PAGES}'

async def _web_search(query: str) -> str:
    # add length limit + sanitize
    if len(query) > 200: query = query[:200]
    # ... after fetch ...
    # strip HTML tags + limit 500 chars per result
    return '\n'.join(lines)[:3000]

# unify provider
PROVIDER_DEFAULT = 'bynara' # single source of truth
```

---

### Q5 — Fix rate limiting bypass via IP spoof + add chat-specific limits
**Files:** `security.py:80-82,85-99`

```python
# current:
ip = request.headers.get('x-forwarded-for', request.client.host) 
# → attacker can set X-Forwarded-For to arbitrary to bypass rate limit (rotate IPs)
# Also UA hashing naive
```

Fix:
```python
def get_real_ip(request: Request) -> str:
    # Only trust X-Forwarded-For if behind known proxy (env TRUSTED_PROXY = true)
    # Parse first IP of list, validate IPv4/IPv6
    if os.getenv('TRUSTED_PROXY') == '1':
        xff = request.headers.get('x-forwarded-for','')
        if xff:
            ip = xff.split(',')[0].strip()
            # validate
            import ipaddress
            try: ipaddress.ip_address(ip); return ip
            except: pass
    return request.client.host if request.client else 'unknown'

# Add per-user daily cost limit
# chat_limiter currently 120/min with NO per-user token cost cap → one user can spend $1000/min
# Add second limiter: chat_daily_cost
```

Plus add `conversation search` ILIKE without escape: `conversations.py:90-95` uses `f'%{q}%'` with ILIKE — though `_escape_like` exists, it's NOT used there! SQL injection via LIKE? Actually param, so safe from SQLi, but LIKE pattern injection (regex DoS via `%_%_%_%%%%`) → use `_escape_like`.

---

## 3. DETAILED ANALYSIS

### Streaming
- Impl: `httpx.AsyncClient.stream()` + `aiter_lines()` yield SSE.
- Issues: No per-chunk timeout, no cancel on disconnect, no max duration, no backpressure, billing in finally may never execute, no logging of upstream latency.
- StreamingResponse missing SSE headers.
- Smart-chat stream sends `smart_info` meta event but no spec — frontend must handle ad-hoc `type: smart_info` vs OpenAI SSE.
- `payload['stream_options']['include_usage']=True` forces LiteLLM to send final usage chunk, but if upstream doesn't support, usage_data stays None → free usage.

**Recommended streaming state machine:**
Reserve → Stream with 5 min cap + heartbeat (comment `:keepalive`) every 15s → On client disconnect: break + release reserved remainder → On success: settle(actual) → On error: release.

### Billing
- Good: `Money` value object (no float), `BillingService.reserve/settle/release` exists, `MemoryBillingRepo` with locks for tests, payment callback properly uses FOR UPDATE.
- Bad: Chat path ignores BillingService, uses legacy SUM(ledger) race. Ledger balance_after racy. No idempotency key on chat billing path except `secrets.token_hex(8)` for metering (random per call, not idempotent on retry). Dual-write not transactional due to swallow.
- `wallet/topup` uses `payment_orders` table but models.py has `Payment` table — schema mismatch risk (0001 creates `payment_orders`, 0004 creates `payments`). Which is used? Both? Danger.

### Memory
- Endpoint CRUD solid with soft delete, ownership check via `user_id == uid`.
- Search uses `_escape_like` correctly.
- BUT: content length uncapped (DOS via huge memories), no embeddings/search relevance, no deduplication, limit 20 hardcoded in get but limit param missing in create.
- Export from conversations allows arbitrary JSON messages — could contain 10MB+ payload, no size limit on `Conversation.messages`.

### Rate Limiting
- Sliding window via `INCR` + `EXPIRE window*2` — simple but inaccurate: fixed window aligned to `int(time/window)`, allows 2x burst at window boundary (e.g., 60 at 59s + 60 at 60s = 120 in 2s).
- Fail-closed after fix (was fail-open previously). Good.
- No rate limiting on `/conversations/search` (expensive ILIKE with jsonb_array_elements) or `/memories/search` or `/wallet/ledger`.
- IP bypass via spoofed XFF.

### Timeouts & Error Handling
- httpx client: Timeout 90s connect 10s — okay for non-stream but long for chat pre-flight.
- LiteLLM health check timeout 5s — good.
- Web search timeout 12s but no circuit breaker, regex parsing fragile.
- No overall request timeout middleware.
- `except Exception: pass` everywhere hides DB down scenarios → fallback to free service.

### Security
- API key auth uses peppered hash — good.
- Session token 7d TTL + sliding expiration — reasonable.
- CSRF via X-Requested-With for cookie auth — good depth, covers CORS form POST.
- Admin session separate CSRF — good.
- Banned check only on API key auth, not on session auth? Check: `_get_user_id` session path doesn't check `banned` flag — banned user with active session cookie continues access! C bug.

---

## 4. CODE QUALITY SCORE: 4.5 / 10

| Axis | Score | Notes |
|------|-------|-------|
| Correctness (billing) | 2/10 | Race + dual-write + wallet ignored |
| Security | 5/10 | Good pepper/session/CSRF but banned bypass + XFF spoof + prompt injection |
| Reliability | 3/10 | No streaming timeout, bare excepts, no request IDs |
| Performance | 4/10 | Missing index on provider_model_id, SUM(ledger) each req, N+1 memories |
| Maintainability | 4/10 | 5x duplicated memory/soul injection, WET, no shared helpers |
| Observability | 2/10 | Prints, no structured logs, no metrics |
| Testing | 6/10 | MemoryBillingRepo exists, but billing path uncovered |

---

## 5. FILE:LINE INDEX (for CTO action items)

- `chat.py:43` _check_quota_pre race
- `chat.py:79-80` silent except bypasses quota
- `chat.py:116-145` _web_search fragile regex + no sanitization of results
- `chat.py:169-221` _record_usage dual-write + no FOR UPDATE
- `chat.py:275-316` _chat_stream no timeout/disconnect
- `chat.py:352-376` memory/soul injection duplicated
- `chat.py:528-534` hardcoded `bynara2` provider inconsistency
- `dependencies.py:288-302` _get_user_soul no limit
- `security.py:80-82` X-Forwarded-For trust without validation
- `migrations/0002_claims_catalog.sql:48-49` missing index provider_model_id
- `conversations.py:84-101` search ILIKE without _escape_like
- `auth.py:231-245` referral bonus ledger balance calc racy (SUM then insert)

---

## 6. WHAT TO DO MONDAY MORNING

1. **P0** Add `idx_model_catalog_provider_model_id` migration — 5 min.
2. **P0** Wrap billing in reserve/settle — 1 day. Stop money leak.
3. **P0** Add streaming timeout + is_disconnected check — 2 hours.
4. **P0** Fix banned check on session path — 10 min.
5. **P1** Replace bare excepts with logger.exception + Sentry DSN — half day.
6. **P1** Extract `get_injection_messages` — 2 hours, eliminates 200 LOC dup.
7. **P1** Limit soul/memory chars + sanitize prompt injection — 2 hours.

---

*End of S2 Backend Report — Brutal honest edition. System has solid bones (Money VO, BillingService design, peppered keys, CSRF) but hot path ignores its own safety mechanisms and hides failures. Fix billing race first.*
