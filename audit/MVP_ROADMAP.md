# 🗺️ Multiai MVP Roadmap — The North Star Document

**Author:** Senior CTO/VP Engineering (S9 Synthesis)  
**Date:** 2026-07-16  
**Sources:** S1 (Model Audit), S2 (Backend Audit), S3 (Frontend UX Audit), S4 (Pricing Audit), S5 (Memory Audit), S6 (Streaming Audit)  
**Status:** FINAL — Ready for Executive Review

---

## 📊 Executive Summary

Multiai is a **multi-model Persian AI chat platform** with a solid foundation but significant gaps. After a comprehensive 6-audit review, the platform scores **3.8/10** overall and is **not production-ready**. The good news: the path to an exceptional MVP is clear, well-defined, and achievable in 4-6 weeks.

### The Platform Today

| Dimension | Score | Assessment |
|-----------|-------|------------|
| **Model Availability** | 2.0% working | Only 7/354 models functional. OpenRouter dead. |
| **Backend Quality** | 4/10 | Functional but race conditions, silent errors, no observability |
| **Frontend UX** | 4.5/10 | No markdown rendering, primitive model picker, missing fundamentals |
| **Pricing Accuracy** | ✅ PASS | v2 pricing correct. 98% models disabled. |
| **Memory System** | 45/100 | Basic CRUD. No auto-extraction, no relevance. |
| **Streaming** | 6.5/10 | Works but no billing on disconnect, frontend ignores billing events |
| **Security** | NOT AUDITED | High risk. No S7 audit exists. |

### The Critical Path

**Three things must happen before anyone sees the panel:**

1. **Fix the model crisis** — Only 7 models work. Smart-chat defaults to broken models. OpenRouter is completely dead.
2. **Add Markdown rendering** — AI responses are raw text. This alone makes the product feel like a prototype.
3. **Fix the billing race condition** — Users can overspend. Revenue leaks on every concurrent request.

**Everything else can be phased.**

### The WOW MVP Vision

A user opens Multiai for the first time. They see a beautiful, dark-themed Persian RTL interface. They type a question in Farsi. The response streams back with **rich markdown, syntax-highlighted code blocks, and a blinking cursor**. They see the model they're using, its cost in Tomans, and their wallet balance updating in real-time. They can switch between 15+ working models with a beautiful card-based picker. They think: "This is the Persian ChatGPT — and it has MORE models."

---

## 🎯 The WOW MVP Definition

### What the User Sees on First Visit

1. **Beautiful empty state** — Animated gradient background, model-specific suggestions, capability showcase
2. **Rich model picker** — Not a `<select>`, but a card-based searchable grid with descriptions, pricing, and capability tags
3. **Smart Mode toggle** — Prominently visible, clearly explained
4. **Persian welcome** — Full RTL, culturally relevant presets, Persian-optimized models highlighted

### What Makes Them Say "This is Amazing"

1. **Rich Markdown with syntax highlighting** — Code blocks have copy buttons, language detection, and dark theme
2. **Real-time cost tracking in Tomans** — Not just tokens, actual IRT cost updating live
3. **Multi-model compare** — Split-view comparing 2-3 models on the same prompt
4. **Auto-generated conversation titles** — AI names conversations with emoji (e.g., "🐍 Python decorator deep dive")
5. **Memory that works** — The AI remembers preferences across sessions without manual input

### MUST-HAVE vs NICE-TO-HAVE

| Category | MUST-HAVE (Phase 1-2) | NICE-TO-HAVE (Phase 3+) |
|----------|----------------------|------------------------|
| **Models** | 15+ working models, fixed routing | 50+ models, OpenRouter restored |
| **Chat UX** | Markdown, syntax highlighting, rich picker, streaming cursor | Model compare, prompt library, canvas |
| **Billing** | Race condition fix, real-time cost, billing events | Per-token cost estimate, spending limits |
| **Memory** | Auto-extraction, relevance filtering, token budget | Semantic search, memory types, RAG |
| **Streaming** | Billing on disconnect, reconnect, cancel upstream | Real-time token counter, stream resume |
| **Infrastructure** | Indexes, logging, request IDs | Circuit breaker, metrics, A/B testing |

---

## 🏗️ Phase 1: IMMEDIATE FIXES — This Week (Days 1-7)

**Goal:** Make the platform functional and safe. Fix everything that would embarrass us or cost us money.

### P1.1 — Fix the Model Crisis 🔴

**Critical Path. Must be done first.**

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Fix OpenRouter API key | `.env` / litellm config | 1h | DevOps | All 342 OpenRouter models return 200 |
| Replace smart-chat defaults | `backend/chat.py:528-534` | 30m | Backend | `_DEFAULT_MODEL` = `('gemini-3.5-flash', 'bynara')` |
| Remove broken catalog entries | `model_catalog` table | 15m | Backend | mimo-v2.5*, grok-4.5 marked `disabled` |
| Add kimi-k2.7-code-free to catalog | `model_catalog` table | 15m | Backend | kimi model appears in catalog API |
| Fix provider mapping | `backend/chat.py:528-534` | 15m | Backend | All references use `bynara` not `bynara2` |
| Enable key OpenRouter models | `model_catalog` table | 2h | Backend | 20+ popular OR models available |
| Set model health check endpoint | `backend/` new file | 3h | Backend | GET /health/models returns live status |

**Deliverable:** 15+ working models, smart-chat routes to actually-working models, catalog reflects reality.

### P1.2 — Fix Billing Integrity 🔴

**Revenue protection. Do NOT skip.**

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Wire BillingService into chat flow | `backend/chat.py` + `services/billing.py` | 3d | Backend | `reserve()` before LLM call, `settle()` after |
| Fix streaming disconnect billing (BUG-1) | `backend/chat.py:275-314` | 2h | Backend | Disconnect after tokens = still billed |
| Add `model_catalog.provider_model_id` index | `database/migrations/` | 30m | Backend | `EXPLAIN` shows index scan, not seq scan |
| Replace `except Exception: pass` with logging | `backend/chat.py` (10+ locations) | 2h | Backend | All silent failures now log warnings |
| Add `conversations(user_id, updated_at)` index | `database/migrations/` | 15m | Backend | List query uses index-only scan |
| Add `usage_events(user_id, model)` index | `database/migrations/` | 15m | Backend | Analytics GROUP BY uses index |

**Deliverable:** No revenue leakage. Every token consumed is billed. Billing failures are logged.

### P1.3 — Fix Streaming Critical Bugs 🔴

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Handle billing event in frontend (BUG-2) | `frontend/app/chat/page.tsx:569-588` | 1h | Frontend | Real cost from backend displayed |
| Handle smart_info event in frontend (BUG-3) | `frontend/app/chat/page.tsx:569-588` | 30m | Frontend | Smart model name shown during stream |
| Cancel upstream on client disconnect | `backend/chat.py:275-314` | 1h | Backend | LiteLLM request cancelled when client disconnects |
| Fix hardcoded cost estimate (BUG-4) | `frontend/app/chat/page.tsx:602` | 30m | Frontend | Uses actual billing event cost |

**Deliverable:** Streaming billing is correct. Frontend shows real costs. Smart mode info visible.

### P1.4 — Security Baseline (If S7 not done) 🟡

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Add input validation on memory content | `backend/memory.py` | 1h | Backend | Max 2000 chars, XSS sanitized |
| Add rate limiting on memory endpoints | `backend/memory.py` | 30m | Backend | 30 req/min per user |
| Enable CORS credentials if needed | `backend/app.py:121-127` | 15m | Backend | Cookie auth works cross-origin |
| Add content-length limits on soul | `backend/dependencies.py` | 15m | Backend | Max 1000 chars for ai_personality |

**Deliverable:** Basic security hardening. No open abuse vectors.

### Phase 1 Success Criteria

- [ ] 15+ working models in catalog
- [ ] Smart-chat routes to working models 100% of time
- [ ] No revenue leakage from concurrent requests
- [ ] Streaming disconnect doesn't give free tokens
- [ ] Frontend shows real cost from backend
- [ ] All critical bugs from S1, S2, S6 fixed
- [ ] All 4 missing indexes created

---

## 🎨 Phase 2: UX OVERHAUL — Next 2 Weeks (Days 8-21)

**Goal:** Go from prototype to world-class. Make the product feel like a premium AI platform.

### P2.1 — Markdown & Code Rendering 🔴 (THE single biggest impact)

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Install react-markdown + remark-gfm | `frontend/package.json` | 15m | Frontend | Dependencies installed |
| Install rehype-highlight + dark theme | `frontend/package.json` | 15m | Frontend | Syntax highlighting works |
| Create MarkdownRenderer component | `frontend/components/chat/MarkdownRenderer.tsx` | 3h | Frontend | All markdown features render |
| Add per-code-block copy button | `frontend/components/chat/CodeBlock.tsx` | 1h | Frontend | Every code block has copy button |
| Update ChatMessageItem to use MarkdownRenderer | `frontend/app/chat/page.tsx:133` | 1h | Frontend | `<div>{msg.content}</div>` → `<MarkdownRenderer content={msg.content} />` |
| Add RTL-aware markdown styling | `frontend/app/globals.css` | 2h | Frontend | Lists, blockquotes, tables render RTL-correct |

**Deliverable:** AI responses render beautiful rich markdown with syntax-highlighted code blocks, copy buttons, and proper RTL handling.

### P2.2 — Rich Model Picker 🔴

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Build ModelPicker component | `frontend/components/chat/ModelPicker.tsx` | 4h | Frontend | Searchable, card-based, grouped |
| Add model search/filter | `frontend/components/chat/ModelPicker.tsx` | 2h | Frontend | Type to filter by name/capability |
| Add provider badges and icons | `frontend/components/chat/ModelPicker.tsx` | 1h | Frontend | Visual provider differentiation |
| Show pricing per model | `frontend/components/chat/ModelPicker.tsx` | 1h | Frontend | IRT/1M tokens displayed |
| Add capability tags | `frontend/components/chat/ModelPicker.tsx` | 1h | Frontend | "code", "vision", "fast" tags |
| Add "Recommended" and "Persian-optimized" badges | `frontend/components/chat/ModelPicker.tsx` | 30m | Frontend | Hero models highlighted |
| Replace `<select>` with ModelPicker | `frontend/app/chat/page.tsx:769-780` | 1h | Frontend | Native select replaced |
| Add favorites/pinning | `frontend/components/chat/ModelPicker.tsx` | 2h | Frontend | Users can pin favorite models |

**Deliverable:** World-class model picker that makes the multi-model advantage visible and usable.

### P2.3 — Streaming UX Enhancement 🟠

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Add blinking cursor during streaming | `frontend/app/chat/page.tsx` + CSS | 1h | Frontend | Cursor blinks at end of streaming text |
| Add smooth fade-in for new tokens | `frontend/app/globals.css` | 30m | Frontend | CSS animation on new content |
| Add "Stop generating" button improvement | `frontend/app/chat/page.tsx:830-835` | 30m | Frontend | More visible, animated stop button |
| Add tokens/sec display | `frontend/app/chat/page.tsx` | 1h | Frontend | Live speed counter during generation |
| Add reconnection logic | `frontend/app/chat/page.tsx` | 3h | Frontend | Auto-reconnect with exponential backoff |

**Deliverable:** Streaming feels alive — cursor blinks, tokens fade in, speed is visible, and reconnection works.

### P2.4 — Conversation Sidebar Enhancement 🟠

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Add search bar in sidebar | `frontend/app/chat/page.tsx:651-713` | 2h | Frontend | Filter conversations by title |
| Add date grouping headers | `frontend/app/chat/page.tsx:651-713` | 1h | Frontend | "Today", "Yesterday", "This Week" |
| Add AI-generated titles | `backend/chat.py` + `frontend/` | 3h | Fullstack | After first response, title auto-generated |
| Add pin-to-top | `frontend/app/chat/page.tsx` | 1h | Frontend | Pinned conversations stay at top |
| Add conversation title editing | `frontend/app/chat/page.tsx` | 1h | Frontend | Double-click to rename |

**Deliverable:** Sidebar is usable at scale (100+ conversations). Search, date grouping, AI titles.

### P2.5 — Keyboard Shortcuts & Accessibility 🟠

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Implement keyboard shortcut system | `frontend/app/chat/page.tsx` | 2h | Frontend | Ctrl+N new chat, Ctrl+K model picker, Ctrl+/ help |
| Add shortcut help modal | `frontend/app/chat/page.tsx` | 1h | Frontend | `?` key shows all shortcuts |
| Add aria-live regions | `frontend/app/chat/page.tsx` | 1h | Frontend | Screen reader announces new messages |
| Add focus trap in mobile drawer | `frontend/app/chat/page.tsx` | 30m | Frontend | Tab stays within drawer |
| Fix RTL CSS logical properties | `frontend/app/globals.css` | 2h | Frontend | All `left`/`right` → `inset-inline-*` |

**Deliverable:** Power users fly with keyboard. Screen readers work. RTL is pixel-perfect.

### P2.6 — Memory UI Integration 🟡

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Add memory indicator in model bar | `frontend/app/chat/page.tsx:746` | 1h | Frontend | Shows active memory count |
| Add memory toggle | `frontend/app/chat/page.tsx` | 1h | Frontend | Enable/disable memory injection |
| Add memory preview flyout | `frontend/app/chat/page.tsx` | 2h | Frontend | Click indicator → see memory snippets |

**Deliverable:** Memory is visible in chat. Users know what the AI remembers.

### Phase 2 Success Criteria

- [ ] All AI responses render rich markdown with syntax highlighting
- [ ] Model picker is card-based, searchable, with pricing
- [ ] Streaming has cursor animation and speed display
- [ ] Sidebar has search, date grouping, AI titles
- [ ] All keyboard shortcuts work
- [ ] UX score improves from 4.5 → 8.0/10

---

## 🚀 Phase 3: ADVANCED FEATURES — Next Month (Days 22-42)

**Goal:** Add competitive differentiators. Make Multiai the best Persian AI platform.

### P3.1 — Model Compare (Killer Feature) 🟠

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Build split-view compare layout | `frontend/app/compare/` | 5d | Frontend | 2-3 models side-by-side |
| Simultaneous streaming from multiple models | `backend/` new endpoint | 3d | Backend | `/v1/compare` streams all models |
| Add compare mode toggle in chat | `frontend/app/chat/page.tsx` | 2d | Frontend | "Compare" button splits view |

**Deliverable:** The feature no competitor has — compare GPT, Claude, and Persian models on the same prompt.

### P3.2 — Auto-Memory Extraction 🟠

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Build memory extraction prompt | `backend/services/memory_extractor.py` | 2d | Backend | LLM call extracts facts from conversation |
| Add post-chat extraction hook | `backend/chat.py` | 1d | Backend | After each response, analyze for memories |
| Add duplicate detection | `backend/services/memory_extractor.py` | 1d | Backend | ILIKE + embedding similarity check |
| Add memory approval UI | `frontend/app/chat/` | 2d | Frontend | "Should I remember this?" cards |
| Add relevance-based memory selection | `backend/dependencies.py` | 2d | Backend | Only inject relevant memories |
| Add token budget management | `backend/dependencies.py` | 1d | Backend | Cap memory tokens at 20% of context window |

**Deliverable:** The AI remembers. Users don't need to manually create memories. Smart relevance filtering.

### P3.3 — Real-Time Cost Tracker 🟡

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Live cost counter in composer footer | `frontend/app/chat/page.tsx:1048-1068` | 2d | Frontend | Cost updates as tokens stream |
| Pre-send cost estimate | `frontend/app/chat/page.tsx` | 1d | Frontend | "This will cost ~X Tomans" |
| Wallet balance warning | `frontend/app/chat/page.tsx` | 1d | Frontend | Yellow/red when balance low |
| Per-model cost comparison | `frontend/components/chat/ModelPicker.tsx` | 1d | Frontend | Sort by cost in picker |

**Deliverable:** Complete cost transparency. Users trust the platform because they always know what they're spending.

### P3.4 — Prompt Library 🟡

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Build prompt library page | `frontend/app/prompts/` | 3d | Frontend | Searchable, categorized library |
| Add curated Persian prompts | `database/seed_prompts.sql` | 1d | Content | 50+ Persian prompt templates |
| Add "use this prompt" in chat | `frontend/app/chat/page.tsx` | 1d | Frontend | One-click to use template |
| Add user prompt saving | `backend/` new endpoint | 2d | Backend | Save/load personal prompts |

**Deliverable:** Prompt templates drive engagement. Persian-specific prompts are a unique advantage.

### P3.5 — Web Search Enhancement 🟡

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Replace DDG scraping with API | `backend/chat.py:116-145` | 2d | Backend | Use proper search API |
| Add search result caching | `backend/chat.py` | 1d | Backend | Redis cache, 5min TTL |
| Add search source citations | `frontend/app/chat/page.tsx` | 1d | Frontend | Clickable source links in responses |

**Deliverable:** Reliable web search with citations. No fragile regex scraping.

### P3.6 — Observability & Production Readiness 🟡

| Task | File(s) | Effort | Owner | Success Criteria |
|------|---------|--------|-------|-----------------|
| Add structured logging | `backend/` all files | 2d | Backend | JSON logs with request IDs |
| Add Prometheus metrics | `backend/middleware/metrics.py` | 2d | Backend | Request count, latency, error rate, model usage |
| Add idempotency keys | `backend/chat.py` | 1d | Backend | `Idempotency-Key` header prevents double-charge |
| Add circuit breaker | `backend/chat.py` | 1d | Backend | Upstream failures isolate, don't cascade |
| Refactor chat.py into modules | `backend/chat/` | 3d | Backend | Separate files for routing, billing, streaming, smart |

**Deliverable:** Platform is observable, debuggable, and resilient. Ready for production traffic.

### Phase 3 Success Criteria

- [ ] Model compare works with 2-3 simultaneous streams
- [ ] Auto-memory extraction creates memories from conversations
- [ ] Real-time cost tracker updates during streaming
- [ ] Prompt library has 50+ Persian templates
- [ ] Web search uses API, shows citations
- [ ] Structured logging and metrics are operational
- [ ] Backend code is modularized (no 815-line single file)

---

## 🧠 Model Strategy

### Hero Models (Featured Prominently)

These are the models that get the "Recommended" badge and prime placement in the picker:

| Hero Model | Provider | Why | Pricing (IRT/1M) |
|-----------|----------|-----|-----------------|
| **Gemini 3.5 Flash** | Bynara/Google | Best all-around for Persian. Fast, capable. | 324K / 1,944K |
| **Mistral Large** | Bynara/Mistral | Strong general purpose, good Persian. | 432K / 1,296K |
| **Agnes 2.5 Flash** | Bynara | Fastest model, great for simple queries. | 12K / 60K |
| **Tencent Hy3** | Bynara | Best reasoning model available. | 43K / 173K |
| **Kimi K2.7 Code** | Bynara | Free coding model. Zero cost. | 0 / 0 |

### Model Organization by Capability

| Category | Models | When to Use |
|----------|--------|-------------|
| **⚡ Fast & Cheap** | Agnes 2.0 Flash, Agnes 2.5 Flash, Kimi K2.7 Code | Greetings, simple queries, quick translations |
| **🧠 General Purpose** | Gemini 3.5 Flash, Mistral Large, Mistral Medium 3.5 | Daily conversations, writing, analysis |
| **💻 Coding** | Kimi K2.7 Code, Mistral Large | Code generation, debugging, review |
| **🔬 Reasoning** | Tencent Hy3, Mistral Large | Complex analysis, math, logic |
| **🌐 If OpenRouter Fixed** | GPT-4o, Claude Sonnet 5, DeepSeek V4, Qwen 3.7 Max | Premium tier, best-in-class capabilities |

### Pricing Tiers Aligned with Models

| Tier | Models | Monthly Price | Target |
|------|--------|---------------|--------|
| **Free** | Agnes 2.0 Flash, Kimi K2.7 Code | 0 IRT | Trial, light use |
| **Basic** | All Bynara models | 49K-99K IRT/month | Regular users |
| **Pro** | + OpenRouter premium models (GPT, Claude) | 199K-299K IRT/month | Power users, developers |
| **Enterprise** | Everything + custom models + API | Custom | Businesses, teams |

### Model Strategy Principles

1. **Bynara-first for MVP** — OpenRouter is dead. Ship with what works.
2. **Highlight the free model** — Kimi K2.7 Code is free. This is a massive acquisition channel.
3. **Persian-optimized badge** — Models that excel at Persian get a special badge.
4. **Transparent pricing** — Every model shows IRT/1M tokens. No surprises.
5. **Smart Mode as default** — Auto-selects the best model for the task. Reduces decision fatigue.

---

## 🏛️ Architecture Decision Record (ADR)

### ADR-1: Use BillingService Reserve/Settle Pattern

**Decision:** Replace direct ledger writes in `chat.py` with the existing `BillingService.reserve()` / `settle()` pattern from `services/billing.py`.

**Rationale:** The current "check balance, call LLM, deduct" flow has a race condition. The `BillingService` already implements proper `FOR UPDATE` locking and `wallet.reserved` tracking. It exists but is unused.

**Impact:** Prevents revenue leakage. Adds ~2 DB queries per request (reserve + settle). Backward-compatible — ledger entries remain the same.

### ADR-2: Extract Context Injection into Shared Helper

**Decision:** Create `backend/services/context_injection.py` with a single `inject_context(payload, uid)` function.

**Rationale:** Memory/soul injection is duplicated 5 times across `chat.py`. Changes to injection logic currently require editing 5 locations. A shared helper reduces duplication and prevents drift.

**Impact:** ~200 lines of duplicated code eliminated. Single source of truth for injection order and format.

### ADR-3: Refactor chat.py into Modules

**Decision:** Split `backend/chat.py` (815 lines) into:
- `backend/chat/router.py` — Route handlers
- `backend/chat/streaming.py` — SSE streaming logic
- `backend/chat/billing.py` — Usage tracking and billing
- `backend/chat/smart.py` — Smart mode selection
- `backend/chat/context.py` — Memory, soul, web search injection

**Rationale:** Single-responsibility principle. Currently a "god file" that handles HTTP, auth, billing, metering, web search, file handling, and smart routing.

**Impact:** Better maintainability. Easier to test. Parallel development possible.

### ADR-4: Frontend — Markdown-First Rendering

**Decision:** Replace raw text display with `react-markdown` + `rehype-highlight` + `remark-gfm`.

**Rationale:** The #1 competitive gap. Every competitor renders markdown. Raw text makes the product feel like a prototype.

**Impact:** 2-3 hours of work. Transforms the entire user experience.

### ADR-5: Model Picker — Card-Based, Not Select

**Decision:** Replace native `<select>` with a custom card-based model picker component.

**Rationale:** The multi-model advantage is invisible with a flat select. Users can't differentiate models, see pricing, or discover capabilities.

**Impact:** 4-6 hours of work. Makes the core differentiator visible.

### ADR-6: Memory — Relevance-Based, Not All-Injected

**Decision:** Implement relevance-based memory selection instead of injecting all memories into every chat.

**Rationale:** Currently injects ALL memories into ALL chats. This wastes tokens, pollutes context, and can produce irrelevant responses. A simple keyword overlap or embedding similarity check would filter to relevant memories only.

**Impact:** Better chat quality. Lower token costs. Required for auto-memory extraction to be useful at scale.

### ADR-7: Streaming — Billing on Disconnect

**Decision:** Track partial token counts during streaming and bill on disconnect.

**Rationale:** Currently, if a user disconnects before the usage chunk arrives, they get free tokens. This is exploitable. The fix tracks accumulated tokens from stream chunks and bills estimated usage on disconnect.

**Impact:** Prevents revenue leakage from streaming. May slightly overcharge on disconnect (acceptable trade-off vs. undercharging).

---

## ⚠️ Risk Assessment

### Critical Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| **OpenRouter never comes back** | Medium | High | Bynara-only MVP. Don't wait for OR. |
| **Bynara plan restrictions block more models** | Medium | High | Monitor health. Have fallback providers. |
| **Billing race condition exploited at scale** | High | High | **Fix in Phase 1.** Non-negotiable. |
| **No S7 security audit exists** | High | Critical | Run security audit BEFORE launch. |
| **Silent error swallowing hides system failures** | High | High | **Fix in Phase 1.** Add logging everywhere. |

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| **DuckDuckGo blocks scraping** | Medium | Medium | Phase 3: Switch to proper search API |
| **Redis outage takes down platform** | Low | High | Rate limiter fails closed. Add graceful degradation. |
| **No streaming timeout** | Medium | Medium | Phase 1: Add 120s streaming timeout |
| **Single-file chat.py becomes unmaintainable** | High | Medium | Phase 3: Refactor into modules |

### Business Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| **Users don't understand multi-model value** | Medium | High | Rich model picker + Smart Mode default |
| **Persian market prefers ChatGPT** | Medium | High | Compete on: no VPN, IRT pricing, Persian optimization |
| **Pricing too expensive for Iranian market** | Medium | High | Highlight free model. Offer basic tier at 49K IRT. |
| **No mobile app** | Low | Medium | PWA as stopgap. Native app in Q3. |

---

## 📅 Timeline Estimate

| Phase | Duration | Calendar | Key Deliverable |
|-------|----------|----------|-----------------|
| **Phase 1** | 5-7 days | Week 1 | Platform functional, safe, 15+ models |
| **Phase 2** | 10-14 days | Weeks 2-3 | World-class UX, markdown, rich picker |
| **Phase 3** | 15-20 days | Weeks 4-6 | Differentiators: compare, memory, cost tracker |
| **Total** | **30-41 days** | **4-6 weeks** | Production-ready MVP |

### Parallel Workstreams

| Week | Backend Team | Frontend Team | DevOps |
|------|-------------|---------------|--------|
| 1 | Billing fix, model fix, indexes | Markdown, streaming bugs | OpenRouter key, model health |
| 2 | Memory extraction, context refactor | Model picker, sidebar, shortcuts | Monitoring setup |
| 3 | Compare endpoint, web search API | Compare UI, cost tracker, prompt library | CI/CD, staging env |
| 4 | Circuit breaker, idempotency, refactor | Polish, accessibility, testing | Production deployment |

---

## 📏 Success Metrics

### Launch Metrics (End of Phase 2)

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| Working models | 7 | 15+ | `/v1/models` endpoint |
| UX score | 4.5/10 | 8.0/10 | UX audit re-run |
| Markdown rendering | ❌ | ✅ | Visual check |
| Billing accuracy | ❌ Race condition | ✅ Atomic | Load test: 100 concurrent requests |
| Streaming billing on disconnect | ❌ | ✅ | Test: disconnect mid-stream |
| Frontend billing display | ❌ Hardcoded | ✅ Real | Check billing event handling |

### Growth Metrics (End of Phase 3)

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Daily active users | 100+ | Analytics |
| Average session length | 10+ minutes | Analytics |
| Conversation completion rate | >80% | Analytics (no abort) |
| Memory creation rate | 5+/user/week | DB query |
| Model compare usage | 10% of sessions | Feature flag analytics |
| User satisfaction | >4.5/5 | In-app survey |

---

## 📝 خلاصه فارسی (Persian Summary)

### نقشه راه MVP — سند نور شمالی

پس از ۶ ممیزی جامع، پلتفرم Multiai نمره کلی **۳.۸ از ۱۰** را کسب کرده و **برای عرضه آماده نیست**. اما مسیر رسیدن به یک MVP استثنایی کاملاً مشخص است.

### سه فاز اصلی:

**فاز ۱ — اصلاحات فوری (هفته اول):**
- رفع بحران مدلها: فقط ۷ مدل از ۳۵۴ مدل کار میکنند. OpenRouter کاملاً قطع است.
- رفع مشکل billing: کاربران میتوانند با درخواستهای همزمان بیشتر از موجودی خود مصرف کنند.
- رفع باگهای استریمینگ: قطع اتصال = مصرف رایگان. فرانتاند هزینه واقعی را نمایش نمیدهد.
- اضافه کردن ایندکسهای ضروری دیتابیس.

**فاز ۲ — بازطراحی UX (هفته ۲-۳):**
- اضافه کردن رندر Markdown و Syntax Highlighting (بزرگترین شکاف رقابتی)
- جایگزینی سلکتور مدل با یک کامپوننت کارتی غنی
- انیمیشن استریمینگ (چشمکزن نشانگر، نمایش سرعت)
- جستجو در سایدبار، عناوین خودکار، کلیدهای میانبر

**فاز ۳ — ویژگیهای پیشرفته (هفته ۴-۶):**
- مقایسه همزمان مدلها (ویژگی منحصربهفرد)
- استخراج خودکار حافظه از مکالمات
- ردیاب هزینه لحظهای به تومان
- کتابخانه پرامپتهای فارسی
- آمادهسازی برای تولید (مانیتورینگ، لاگ، refactor)

### WOW MVP:
کاربر برای اولین بار وارد میشود. یک تم تاریک زیبا با رابط کاملاً فارسی میبیند. سوال میپرسد. پاسخ با **مارکداون غنی، کدهای رنگی، و نشانگر چشمکزن** نمایش داده میشود. هزینه به تومان به صورت لحظهای بهروزرسانی میشود. مدلها را در یک پیکر کارتی زیبا میبیند. فکر میکند: "این همان ChatGPT فارسی است — با کلی مدل بیشتر!"

### استراتژی مدل:
- مدلهای اصلی: Gemini 3.5 Flash, Mistral Large, Agnes 2.5 Flash, Tencent Hy3
- مدل رایگان: Kimi K2.7 Code (کانال جذب کاربر)
- در اولویت: مدلهای Bynara (چون OpenRouter قطع است)

### زمانبندی: ۴-۶ هفته تا MVP آماده عرضه

---

*This document is the authoritative source for all MVP decisions. All teams should align their work to this roadmap. Updates require CTO approval.*