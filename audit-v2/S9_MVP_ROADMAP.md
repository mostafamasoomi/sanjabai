# S9 — MVP Roadmap & North Star Synthesis

**Role:** Senior 9 — CTO / VP Engineering
**Date:** 2026-07-16
**Project:** /root/multiai — Multiai AI Agent Platform
**Status:** THE NORTH STAR DOCUMENT (authoritative for S1–S8 remediation + roadmap)
**Source reports:** S1 (Model Reliability), S2 (Backend/Architecture), S3 (Frontend UX), S4 (Pricing Integrity), S6 (Streaming/Realtime), S7 (Security), S8 (UI Design Plan).
**Note on coverage:** The audit directory contains S1–S4, S6, S7, S8. **No S5 report was produced** (the file is absent). This synthesis treats S5 as "not delivered" and flags it as a gap in the audit board (see §0). All content below is derived strictly from the 7 reports that exist plus a live read of the code state (master @ `6a29182`).

---

## 0. Executive Summary (Read This First)

Multiai has **solid bones but a severely degraded runtime**. The product's differentiators are real and defensible: a multi-model aggregator (15+ models, 8+ providers in one UI), Persian-first RTL, Iran-accessible with local IRT pricing, and a unique Smart-Mode auto-router. But right now **only 4 of 91 tested models work (4.4%)**, the **billing path has a money-losing race + a free-generation exploit**, **streaming billing silently fails on disconnect**, and **the chat UI renders every AI response as raw unformatted text** — 5 years behind every competitor on two fundamentals (markdown + code highlighting).

This is not a "build new features" situation. It is a **stabilize → polish → differentiate** situation.

**The WOW MVP thesis:** *"The Persian ChatGPT — but better, because it has every model."* A user opens Multiai, sees a sleek dark RTL interface, picks a model from a beautiful card grid (or lets Smart Mode choose), types a question, and watches the response stream back with **rich markdown, syntax-highlighted code with copy buttons, a blinking cursor showing tok/s, and a live cost counter in Tomans.** Then they switch models mid-conversation to compare. They think: *"This is what ChatGPT would be if it spoke Farsi and had every model."*

**Three phases, six weeks:**

| Phase | Weeks | Theme | North-star outcome |
|-------|-------|-------|--------------------|
| **Phase 1 — Stabilize** | Week 1 | Stop the bleeding | Models work, billing is safe, streaming bills, security baseline |
| **Phase 2 — Polish** | Weeks 2–3 | Close the 5-year UX gap | Markdown, rich picker, streaming UX, sidebar, shortcuts, memory UI |
| **Phase 3 — Differentiate** | Weeks 4–6 | Build the moat | Model compare, auto-memory, realtime cost (Toman), prompt library, web search API, observability |

**Hard rule from the user:** No new feature enters production until the Phase-1 stability/security/migration/runtime blockers are resolved. Features are sequenced strictly behind that gate.

---

## 1. Current State Snapshot (grounded in audit evidence)

### 1.1 What works
- **Money math is sound:** `money.py` uses an immutable `Money(int IRT)` value object (no float). `metering.compute_charge()` does integer half-up rounding. Pricing pipeline is idempotent (S4 verdict: PASS on every data-quality check).
- **BillingService design is correct:** `reserve()/settle()/release()` with `FOR UPDATE` row locks and idempotency keys *already exist* in `services/billing.py` — the chat hot path just **doesn't use them** (S2-C1).
- **Security posture is mature for its size:** server-side sessions, CSRF defense-in-depth, fail-closed rate limiting on Redis outage, PBKDF2+salt passwords, peppered API-key hashing, SameSite=Lax cookies, no `localStorage`/XSS vectors (S7: no CRITICAL/HIGH vulns).
- **Streaming SSE framing is valid:** proxy routes correctly disable nginx buffering (`X-Accel-Buffering: no`, `Cache-Control: no-cache`). `AbortController` is correctly wired client-side. (S6 positive findings.)
- **Aurora v2 design system** is solid (2786-line `globals.css` with well-organized tokens). (S8.)
- **Smart Mode** auto-router exists and is unique to Multiai.

### 1.2 What is broken (the blockers)
| # | Area | Severity | Evidence |
|---|------|----------|----------|
| B1 | Only 4/91 models work; OpenRouter 100% blocked by WAF (Iran IP + dead tunnel); Bynara MiMo plan-restricted; free-tier smart-routing picks **non-existent** `qwen3-coder-free` → 400 | CRITICAL | S1 §2–§7 |
| B2 | **Billing race** (TOCTOU check-then-act + ignored `wallet` table + unused `reserve/settle`) → concurrent overspend / infinite free calls | CRITICAL (money loss) | S2-C1 |
| B3 | **Free generation exploit:** streaming billing only in `finally`, gated on `usage_data` which is `None` if client disconnects before final usage frame → user never charged | CRITICAL (revenue leak) | S6-F1 |
| B4 | No `request.is_disconnected()` / upstream cancellation → backend pays LiteLLM to completion after user hits "stop" | HIGH (operator cost) | S6-F4 |
| B5 | **~28 bare `except: pass`** swallow billing/auth/quota errors → quota bypass, silent undercharge (~100x), invisible incidents | CRITICAL | S2-C3 |
| B6 | Memory/Soul injection: 5x duplicated, **no char cap** (user can inject 2MB/request), **no prompt-injection sanitization** | CRITICAL (cost + security) | S2-C4 |
| B7 | No markdown / no syntax highlighting — every response is raw text | CRITICAL (UX) | S3 #1, S8 §1.3 |
| B8 | Flat `<select>` model picker; no pricing/context/capability display | HIGH | S3 #3 |
| B9 | Frontend ignores server `type:'billing'` and `type:'smart_info'` SSE events → real cost & chosen model never shown | HIGH | S6-F2/F3 |
| B10 | Model param not whitelisted against catalog → billing bypass to premium models at cheapest rate | MEDIUM | S7-M1 |
| B11 | Fixed-window rate limiter (2x burst at boundary) + XFF-spoofable IP id + no per-user/tiered limits | MEDIUM | S7-M2/M3/M4 |
| B12 | Catalog drift: 494 rows, only 10 "available" but only 4 actually work; 144 stale zenmux entries; `kimi-k2.7-code-free` works but disabled | HIGH | S1 §4, S4 §3 |

### 1.3 Code-quality scorecard (from S2)
| Axis | Score | Notes |
|------|-------|-------|
| Correctness (billing) | 2/10 | Race + dual-write + wallet ignored |
| Security | 5/10 | Good primitives, but XFF spoof + prompt injection + banned-session bypass |
| Reliability | 3/10 | No streaming timeout, bare excepts, no request IDs |
| Performance | 4/10 | Missing `provider_model_id` index, `SUM(ledger)` per request, N+1 memories |
| Maintainability | 4/10 | 5x duplicated injection, WET monolith |
| Observability | 2/10 | Prints, no structured logs, no metrics |
| Testing | 6/10 | `MemoryBillingRepo` exists; billing hot path uncovered |
| **Overall** | **~3.7/10** | **Stabilize before anything else** |

---

## 2. The WOW MVP Definition

### 2.1 First-visit experience (what the user sees)
1. **Sleek dark RTL landing** with animated Aurora gradient, Vazirmatn font, model-aware suggestion cards (not 4 static presets).
2. Topbar shows a **current model chip** (e.g. "tencent-hy3 · Bynara") and a **live wallet balance in Tomans**.
3. User types in Persian or English (`dir="auto"`). Hits Enter.
4. **Rich streaming response:** markdown rendered, code blocks syntax-highlighted with language badge + copy button, blinking cursor, **tok/s indicator**, and a **live cost counter** ticking up in Tomans.
5. When done: cost summary "۱,۲۳۴ توکن · ~۲,۵۰۰ تومان", and Copy / Regenerate / Edit buttons fade in.

### 2.2 The "amazing" moment (what makes them say wow)
> **Switch models mid-conversation and compare.** The user asks a hard coding question, gets a great answer from tencent-hy3, then clicks the model chip, picks mistral-large, and re-asks (or regenerates) — seeing the *same prompt* answered by a *different model* side-by-side. No other competitor (ChatGPT=GPT only, Claude=Claude only) can do this in one interface. **This is the moat.** (Built in Phase 3 as the killer feature; teased in Phase 2 via the rich picker + regenerate.)

### 2.3 Moats (must be preserved & amplified — from S8 §1.2)
1. **Multi-model aggregator** — 15+ models, 8+ providers, one UI.
2. **Persian-first RTL** — no global competitor serves Persian natively.
3. **Iran-accessible** — no VPN, local payment (Zarinpal), IRT pricing.
4. **Smart Mode** — server-side auto-router, unique to Multiai.
5. **Model Compare** (Phase 3) — the differentiator that compounds all four.

---

## 3. Model Strategy (5 hero models · capability organization · 4 pricing tiers)

### 3.1 The 5 Hero Models (anchor the catalog around these)
Selected from the **4 working-now + 1 near-term** set (S1 §7), chosen for breadth of capability and reliability today:

| Hero | Provider | Context | Role | IRT/M in (out) — current v2 (×1.20) |
|------|----------|---------|------|--------------------------------------|
| **tencent-hy3** | Bynara | 1M | Default / General / Coding | 43,200 (172,800) |
| **mistral-large** | Bynara | 252K | Advanced reasoning / creative | 432,000 (1,296,000) |
| **mistral-medium-3-5** | Bynara | 256K | Balanced / premium fallback | 324,000 (1,620,000) |
| **kimi-k2.7-code-free** | Bynara | — | Free coding (enable in catalog) | 0 (0) |
| **agnes-2.5-flash** | Bynara | — | Fast multimodal (fix 400, then promote) | 11,880 (59,832) |

> Until OpenRouter is unblocked (S1 P0), the hero set is Bynara-only. The Phase-1 model work is: (a) fix the smart-routing tuples to use **only working models** (S1 §5 fixed snippet already deployed & verified), (b) flip `kimi-k2.7-code-free` to `available`, (c) prune the 354-entry YAML to ~20 intended models, (d) unblock OpenRouter via a **non-IR exit VPS** (Hetzner/EU or Cloudflare Warp) + working tunnel, then expand to the 15–20 model full MVP.

### 3.2 Organization by Capability (frontend `ModelPicker` groups)
The picker (S8-F2) organizes by **capability**, not provider alphabetically:
- ⭐ **Recommended** (smart default per use-case)
- 💬 **General / Chat**
- 🔬 **Coding** (kimi, tencent, qwen-coder-free)
- 🧠 **Reasoning** (mistral-large, tencent)
- 🎨 **Creative** (mistral-large/medium)
- 👁 **Vision** (agnes, gemini — once fixed)
- 💰 **Free** (kimi-code-free, openrouter `:free` tier once unblocked)
- ⚡ **Fast / Budget**

Each card shows: name (LTR), provider badge, context-window badge, **price per 1M tokens (input/output, in Tomans)**, and capability tags.

### 3.3 Four Pricing Tiers (aligns with existing `plans` table that already supports `free`/`pro`/`enterprise`)
| Tier | Plan id | Rate limit (S7-M2 fix) | Monthly token quota | Positioning |
|------|---------|------------------------|---------------------|-------------|
| **Free** | `free` | 30 req/min | metered by balance (Tomans) | Entry; routed to free/cheap models (tencent-hy3, kimi-code-free) |
| **Pro** | `pro` | 120 req/min | generous monthly quota | Power users; all hero models; Smart Mode advanced |
| **Enterprise** | `enterprise` | 300 req/min | high / custom | Teams; priority routing; API access |
| **Unlimited** | `unlimited` | 300 req/min | uncapped (flat) | Heavy users; flat monthly |

> Pricing math is already correct (S4). The work is: (1) surface tier-aware rate limits (S7-M2), (2) ensure `refresh_pricing()` fixes the 482 v1 models still at 50% markup before any re-enable (S4 §2), (3) **product decision: enable a freemium free-model tier** (currently 27 zero-price models all disabled — S4 §3).

---

## 4. THE ROADMAP — Three Phases

> Sequencing rule enforced: **Phase 1 gates Phase 2 gates Phase 3.** Each phase's exit criteria must be met (verified by test, not assertion) before the next begins.

### PHASE 1 — STABILIZE (Week 1) — "Stop the bleeding"
**Goal:** A user can pick a working model, send a message, get billed correctly and safely, and not be able to abuse the system. No new UX features.

| ID | Work | Addresses | Effort | Exit criteria (verified) |
|----|------|-----------|--------|--------------------------|
| P1.1 | **Fix model crisis:** smart-routing tuples → working models only (S1 §5 snippet — *already deployed & verified*); enable `kimi-k2.7-code-free`; prune YAML to ~20; catalog sync so `/catalog/models` == actually-working set | B1, B12 | Done+verify | Live test: smart-chat for greeting/code/reasoning/creative all return 200 from working models; catalog shows only working |
| P1.2 | **Unblock OpenRouter:** move tunnel exit to non-IR VPS, fix ssh_key perms + remote auth, rotate key if needed; verify `curl` from container returns 200 not 403 | B1 | 1–2 d | ≥15 OpenRouter models return 200 in live test |
| P1.3 | **Billing race fix:** route chat path through `BillingService.reserve()` (pessimistic estimate) → LLM → `settle()` (actual); `release()` on cancel/timeout. Use `wallet` table as authoritative balance via `FOR UPDATE` | B2 (S2-C1) | 1 d | Concurrent load test (50 parallel req, $10 balance) → no overspend; ledger + wallet consistent |
| P1.4 | **Free-generation exploit fix:** bill in `finally` even when `usage_data is None` (reconstruct from streamed deltas or minimum charge); add `request.is_disconnected()` guard | B3 (S6-F1) | 0.5 d | `curl -N` abort before usage frame → user still charged; no new free rows |
| P1.5 | **Upstream cancellation:** forward `signal` to upstream `fetch` in all 3 proxy routes; `is_disconnected()` break in `event_stream` to stop paying LiteLLM on stop | B4 (S6-F4) | 0.5 d | User hits "توقف" → backend stops streaming from LiteLLM immediately |
| P1.6 | **Kill silent excepts:** replace ~28 `except: pass` with `logger.exception(...)` + safe defaults; add Sentry/structlog + `X-Request-Id` middleware | B5 (S2-C3) | 0.5 d | No bare excepts in billing/auth/quota; incidents logged with rid |
| P1.7 | **Memory/Soul hardening:** extract single `get_injection_messages()`; enforce `MAX_SOUL_CHARS=2000`, `MAX_MEM_CHAR=500`, `MAX_MEM_COUNT=5`; sanitize injection markers | B6 (S2-C4) | 0.5 d | Injecting 2MB memory → rejected/truncated; prompt-injection tags broken |
| P1.8 | **Security baseline:** whitelist `model` param vs catalog (S7-M1); trusted-proxy XFF handling (S7-M4); add `/v1/chat/` to CSRF prefixes (S7-L1); per-user/tiered rate limits (S7-M2); true sliding-window limiter (S7-M3) | B10, B11 | 1 d | Unknown model → 400; XFF spoof bypassed; tiered limits enforced |
| P1.9 | **DB/index hygiene:** `CREATE INDEX` on `model_catalog(provider_model_id)` (+ partial avail); add idempotency index on `wallet_reservations`; remove 144 zenmux rows | B12 (S2-Q1, C5) | 0.25 d | Pricing lookup no longer seq-scans; catalog clean |
| P1.10 | **Frontend: consume billing + smart_info SSE** (no UI redesign yet — just wire the events so cost/balance/model label update) | B9 (S6-F2/F3) | 0.5 d | After stream, real IRT cost + chosen model shown |

**Phase 1 Exit Gate:** models work end-to-end, billing is safe under load, no free-generation path, security baseline on, structured logs flowing. **Verify with a live chat + concurrent-billing test before any Phase-2 work.**

---

### PHASE 2 — POLISH (Weeks 2–3) — "Close the 5-year UX gap"
**Goal:** Multiai's chat UX matches ChatGPT/Claude/DeepSeek on the fundamentals. No new backend capabilities.

| ID | Work | Addresses | Effort | Exit criteria |
|----|------|-----------|--------|---------------|
| P2.1 | **Rich Markdown + Syntax Highlighting** (`react-markdown`+`remark-gfm`+`rehype-highlight`+`rehype-raw`, `MarkdownRenderer.tsx`, `CodeBlock.tsx` w/ copy + lang badge, RTL `dir="auto"`) | B7 (S3 #1/#2, S8-F1) | 2–3 d | Code blocks render highlighted w/ copy; tables/lists/bold correct in mixed FA/EN |
| P2.2 | **Rich Card Model Picker** (`ModelPicker.tsx`: search, capability groups, price/context badges, keyboard nav, persist selection) | B8 (S3 #3, S8-F2) | 1 d | Can search + filter + pick by capability; selection persists across refresh |
| P2.3 | **Streaming UX:** blinking cursor, tok/s indicator, smooth scroll, model-aware status ("connecting to X…") | S3 #8, S6-F7, S8-F3 | 0.5 d | Visible cursor + tok/s + status during stream |
| P2.4 | **Message Edit + Regenerate** (extract `useChat.ts`; inline edit user msg; regenerate assistant msg) | S3 #4, S8-F4 | 1 d | Edit re-sends from point; regenerate produces new reply |
| P2.5 | **Sidebar: search + date grouping + pin** (`ConversationSearch.tsx`, `ConversationList.tsx`) | S3 #7, S8-F5 | 1 d | 50+ convos searchable + grouped by date |
| P2.6 | **Keyboard Shortcuts** (global handler + help modal: Ctrl+N/K/↑/↓, Esc, Ctrl+/) | S3 #5, S8-F6 | 1 d | All shortcuts work; help modal accessible |
| P2.7 | **Memory / System-Prompt UI** (collapsible "System Instructions" + persona panel, wired to sanitized injection) | S3 #10, S8 (memory) | 1 d | User can set persistent persona; reflected in chat |
| P2.8 | **Live cost display (Toman)** using actual model pricing (replace hardcoded `totalTokens*0.000002`), balance warning when low | S3 #9, S6-F5, S8-F10 | 0.5 d | Pre-send + live cost in Tomans, correct per model |
| P2.9 | **Component decomposition:** break 1074-line `chat/page.tsx` into the S8 §4.2 component tree (<400 lines shell) | S3 structural, S8 §4 | ongoing | Page shell <400 lines; no logic lost |
| P2.10 | **Reconnect/retry** on stream drop (exp backoff, resend prompt) | S6-F6 | 0.5 d | Flaky connection recovers without lost message |

**Phase 2 Exit Gate:** Markdown + picker + streaming UX + sidebar + shortcuts + memory UI all live and tested in browser. UX score target ≥14/20 (from 6/20).

---

### PHASE 3 — DIFFERENTIATE (Weeks 4–6) — "Build the moat"
**Goal:** Features no competitor has. This is where Multiai becomes an *AI Agent Platform*, not a model gateway.

| ID | Work | Addresses | Effort | Exit criteria |
|----|------|-----------|--------|---------------|
| P3.1 | **🔥 Model Compare (KILLER FEATURE):** split-view / side-by-side same prompt across 2+ models, token-speed + cost comparison, vote best | S8 deferred→promote; moat | 3–4 d | Same prompt answered by 2 models; comparable metrics shown |
| P3.2 | **Auto-Memory Extraction:** post-conversation LLM extracts durable facts → user_memories (capped, sanitized); "learned about you" panel | S2-C4 evolution; retention | 2 d | Facts auto-saved with cap; user can review/delete |
| P3.3 | **Realtime Cost Tracker (Toman):** persistent mini-dashboard — session spend, daily cap, per-model burn, low-balance alert | S8-F10 evolution | 1 d | Live Toman spend vs cap; alerts fire |
| P3.4 | **Prompt Library:** save/label/share prompts + templates (backend CRUD + UI gallery) | S8-F (templates) | 2 d | Prompts save/recall/share; inserted into composer |
| P3.5 | **Web Search API:** production web search w/ citations (Perplexity-style `[1]` inline + source cards), replace fragile DDG regex scrape (S2-Q4) | S2-Q4, S8-F13 | 2 d | Search returns cited sources; injected sanitized |
| P3.6 | **Observability:** metrics (Prometheus/OTel) — token throughput, cost/min, model error rates, p95 latency; dashboards + billing-failure alert | S2-C3/Q3, S6-F8 | 2 d | Live dashboards; billing-failure alert fires on test |
| P3.7 | **Conversation Folders + Export fix** (backend `folder_id` + endpoints; fix 404 export route) | S8-F9/F12 | 1 d | Folders CRUD; export JSON/MD/TXT works |
| P3.8 | **Polish pass:** empty-state redesign (model-aware), micro-interactions (S8 §5), a11y baseline (S8-F15), voice input (S8-F8) | S8 Tier 3 | 2 d | Accessibility baseline met; empty state dynamic |

**Phase 3 Exit Gate:** Model Compare live (the wow), auto-memory + realtime cost + prompt library + web-search-citations + observability all shipped. Platform positioned as **AI Agent Platform**.

---

## 5. Seven Architecture Decision Records (ADRs)

> Format: **ADR-NN — Title — Status — Decision — Rationale — Consequences**

**ADR-01 — Billing uses reserve/settle with `wallet` as authoritative balance**
Status: **ACCEPTED** (S2-C1/C5). Chat path MUST call `BillingService.reserve()` (pessimistic estimate) before the upstream call and `settle()` (actual) after; `wallet` table is the source of truth, `ledger` is audit-only. `SUM(ledger)` per request is retired.
*Rationale:* eliminates TOCTOU overspend + dual-write inconsistency. *Consequence:* all chat entry points refactored; migrations may add `reserved` usage.

**ADR-02 — Streaming always bills, even on disconnect**
Status: **ACCEPTED** (S6-F1/F8). Billing in `finally` reconstructs cost from streamed deltas when `usage_data is None`; `request.is_disconnected()` triggers partial bill + upstream cancel.
*Rationale:* closes free-generation exploit + stops operator cost on cancel. *Consequence:* proxy routes forward `signal`; backend checks disconnect in loop.

**ADR-03 — Model param whitelisted against `model_catalog`**
Status: **ACCEPTED** (S7-M1). Every `model` from `ChatRequest` is validated against `provider_model_id WHERE availability='available'` before forwarding; unknown → 400.
*Rationale:* prevents billing bypass to premium models. *Consequence:* catalog is the single gatekeeper; catalog hygiene (P1.9) is mandatory.

**ADR-04 — Memory/Soul injection is capped, sanitized, single-sourced**
Status: **ACCEPTED** (S2-C4). One `get_injection_messages()` function; `MAX_SOUL_CHARS=2000`, `MAX_MEM_CHAR=500`, `MAX_MEM_COUNT=5`; injection markers broken.
*Rationale:* prevents 2MB context bloat + prompt injection. *Consequence:* auto-memory (P3.2) must respect the same caps.

**ADR-05 — No new state libraries; React hooks only**
Status: **ACCEPTED** (S8 §4.4). Chat decomposed into `useChat`, `useConversations`, `useModelPicker`, `useVoiceInput`. No Redux/Zustand/Jotai.
*Rationale:* scale doesn't yet warrant it; keeps bundle lean. *Consequence:* disciplined hook boundaries required.

**ADR-06 — Iranian accessibility is a first-class constraint, not an afterthought**
Status: **ACCEPTED** (S1, S8 §1.2). All upstream exits must be non-IR (Hetzner/EU or Cloudflare Warp); local payment (Zarinpal) + IRT pricing retained; RTL/Persian-native is the default, not a locale.
*Rationale:* this is the moat and the legal/reach requirement. *Consequence:* OpenRouter unblock requires infra change (P1.2), not a code change.

**ADR-07 — Feature gating: stability/security/migration/runtime blockers precede all new features**
Status: **ACCEPTED** (user directive). Phase 1 must exit-green (verified by live test) before Phase 2; Phase 2 before Phase 3. New feature work is rejected if it lands ahead of its gate.
*Rationale:* prevents the "features on a broken foundation" failure mode observed in current state. *Consequence:* roadmap is strictly sequential; no parallel phase-skipping.

---

## 6. Risk Assessment

| Risk | Prob | Impact | Phase | Mitigation |
|------|------|--------|-------|------------|
| OpenRouter stays blocked (IR WAF) | Med | High | P1 | Non-IR exit VPS (Hetzner) + key rotation; ship Bynara-only MVP meanwhile (hero set already Bynara) |
| Billing refactor introduces regressions | Med | High | P1 | Reserve/settle already designed & tested via `MemoryBillingRepo`; add integration test on chat path before merge |
| Breaking chat during 1074-line refactor | High | High | P2 | Extract incrementally per S8 §4.3; each feature independently shippable; browser test after each |
| RTL breaks in markdown tables/lists | High | Med | P2 | `dir="auto"` everywhere; test mixed FA/EN content |
| react-markdown bundle (~46KB gz) | Med | Low | P2 | Lazy-load via `next/dynamic`; tree-shake highlight.js to ~15KB |
| Web Speech API browser support | Med | Med | P3 | 94% global; hide mic button if unsupported |
| Model Compare UI complexity | Med | Med | P3 | Start with 2-model split; defer N-way |
| Scope creep into Phase 3 before P1/P2 green | High | High | All | ADR-07 gate enforced by review |
| S5 audit missing | Low | Low | — | Flagged; re-run a backend/perf audit if needed before launch |

---

## 7. Timeline (6 weeks, sequential gates)

```
Week 1  ▓▓▓▓▓▓▓▓  PHASE 1 STABILIZE  (P1.1–P1.10) ──► EXIT GATE: live chat + concurrent-billing test PASS
Week 2  ▓▓▓▓▓▓▓▓  PHASE 2 start: P2.1 Markdown, P2.2 Picker, P2.3 Streaming UX, P2.4 Edit/Regen
Week 3  ▓▓▓▓▓▓▓▓  PHASE 2 end:   P2.5 Sidebar, P2.6 Shortcuts, P2.7 Memory UI, P2.8 Cost, P2.9 Decomp, P2.10 Retry ──► EXIT GATE: UX ≥14/20, browser-tested
Week 4  ▓▓▓▓▓▓▓▓  PHASE 3 start: P3.1 Model Compare, P3.2 Auto-Memory
Week 5  ▓▓▓▓▓▓▓▓  PHASE 3 mid:   P3.3 Cost Tracker, P3.4 Prompt Library, P3.5 Web Search API
Week 6  ▓▓▓▓▓▓▓▓  PHASE 3 end:   P3.6 Observability, P3.7 Folders/Export, P3.8 Polish ──► EXIT GATE: Platform positioned as AI Agent Platform
```

**Critical-path dependencies:** P1.3 (billing) blocks safe launch; P1.2 (OpenRouter) gates the 15–20 model expansion (hero set works without it); P2.1 (markdown) is the single highest UX leverage and starts Day 1 of Week 2; P3.1 (Model Compare) is the headline differentiator and starts Week 4.

---

## 8. Success Metrics

### Phase 1 (Stabilize) — pass/fail, verified by test
- [ ] **Model availability:** ≥4 working now, ≥15 after OpenRouter unblock (live tested, not claimed)
- [ ] **Billing safety:** 50-parallel-request load test with low balance → **zero overspend**, ledger==wallet
- [ ] **No free generation:** 100 scripted mid-stream aborts → **100% billed**
- [ ] **Security baseline:** unknown model → 400; XFF spoof → rate-limit holds; tiered limits enforced
- [ ] **Observability seed:** structured logs with `X-Request-Id` on every request; zero bare `except: pass` in billing/auth

### Phase 2 (Polish) — UX scorecard
- [ ] Markdown rendering: **100%** of response types (code/tables/lists/bold) correct
- [ ] UX competitive score: **≥14/20** (from 6/20) on the S3 matrix
- [ ] Model picker: search + filter + persist working; selection survives refresh
- [ ] Chat page monolith: **<400 lines** shell

### Phase 3 (Differentiate) — moat metrics
- [ ] Model Compare: live, used in ≥20% of sessions (target)
- [ ] Auto-memory: ≥1 fact auto-saved per active user/week (target)
- [ ] Realtime cost: 100% of streams show correct Toman cost + balance update
- [ ] Web search: cited sources shown, zero undefined regex crashes
- [ ] Observability: dashboards live; billing-failure alert fires on injected test
- [ ] Positioning: marketed as **AI Agent Platform** (multi-model + memory + compare + agents)

### North-star KPI (6-week target)
> A first-time Persian user opens Multiai, sends one message, and within 30 seconds thinks *"This is what ChatGPT would be if it spoke Farsi and had every model."* — measured via activation (first message sent) + retention (returns within 7 days) + model-switch rate.

---

## 9. Appendix — Source Report Index
| Report | Author | Focus | Key verdict |
|--------|--------|-------|-------------|
| S1 | Model Engineer | 91-model live test | 4/91 work; OpenRouter WAF-blocked; smart-routing broken for free users |
| S2 | Backend Architect | chat.py / billing / streaming | Code quality 4.5/10; billing race + silent excepts are P0 |
| S3 | Frontend/UX | chat/page.tsx (1074 ln) | No markdown; UX 6/20 vs ChatGPT 19 |
| S4 | Pricing | catalog + billing pipeline | Integer Toman math sound; v1 50% markup drift dormant |
| **S5** | — | **NOT DELIVERED** | **Gap — flag for re-run if needed** |
| S6 | Streaming/Realtime | SSE + proxy routes | F1 free-gen exploit + F4 upstream-cancel are revenue leaks |
| S7 | Security | security/auth/deps | Mature posture; 4 MEDIUM (whitelist, rate-limit, XFF, sliding) |
| S8 | Product Designer | UI redesign + 15 features | WOW MVP = Persian ChatGPT w/ every model; 15-feature plan |

**This document is the North Star. All phase work references it. Deviations require ADR-07 gate review.**
