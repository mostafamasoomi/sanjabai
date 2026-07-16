# S5 Memory & Personalization Report — Multiai

**Date:** 2026-07-16
**Tester:** S5 Senior AI/Memory Engineer
**Project:** /root/multiai — Multiai Chat Platform
**Scope:** backend/memory.py (168 lines), dependencies._get_user_memories / _get_user_soul, chat.py memory+soul injection (multiple locations), UserMemory model, users.preferences.ai_personality
**Auth used:** cookie/token session for demo@multiai.com (uid=35), backend at http://localhost:8081
**Grade: D+ (functional CRUD, non-existent intelligence)**

---

## 0. Executive Summary

The memory subsystem is a **manual CRUD store bolted onto every chat request**. All 5 endpoints work. But there is **zero intelligence**: no auto-extraction, no relevance filtering, no token budget, no semantic retrieval, no deduplication, no consolidation. Every active memory (up to 20) is stuffed into every single chat turn regardless of relevance. It behaves like a sticky-notes table, not a memory system.

It is production-*stable* (won't crash — helpers swallow exceptions) but production-*wrong* for a platform positioning itself as an "AI Agent Platform." Compared to the Hermes memory model (curated, char-budgeted, declarative, deduped), Multiai is 2–3 generations behind.

---

## 1. What Exists — Verified Live

All endpoints mounted at **root** (no `/api` prefix; frontend proxies `/api/*`). Auth is **cookie/session-based** — Bearer token is rejected by these routes (`_get_user_id` reads the session cookie).

| Endpoint | Method | Result (live, uid=35) | Notes |
|---|---|---|---|
| `/memories` | GET | 200 — returned 8 active rows | filter by `?category=` supported |
| `/memories/search?q=` | GET | 200 — ILIKE match on "Persian" → 2 rows | `_escape_like` prevents wildcard injection ✓ |
| `/memories` | POST | 200 — created id=9 | source hardcoded default 'manual' |
| `/memories/{id}` | PUT | 200 `{"status":"ok"}` | partial update, ownership-checked ✓ |
| `/memories/{id}` | DELETE | 200 `{"status":"deleted"}` | **soft** delete (active=False) ✓ |

**Model (user_memories):** id, user_id (FK→users, ON DELETE CASCADE), content (text), category (default 'general'), source (default 'manual'), tags (text[]), active (bool), created_at, updated_at.
**Indexes:** pkey, user_id, category, (user_id,category) — adequate for the current filter/list queries.
**Data:** only uid=35 has rows (8), **every row has source='manual'** — proof that auto-extraction has never populated a single row.

**Injection path (chat.py):** `_get_user_memories(uid)` → `ORDER BY created_at DESC LIMIT 20`, formatted as a `[User Memories]` system message and inserted after the first system message. `_get_user_soul(uid)` → reads `users.preferences.ai_personality` and injects a `[User Soul]` system message. Both helpers `try/except → return []/''` so they never break chat.

---

## 2. The Four Critical Gaps

### 2.1 Auto-memory extraction — **DOES NOT EXIST**
Confirmed by code search (no `extract`, `remember`, `save_memory`, embedding logic anywhere) and by DB (`SELECT DISTINCT source` → only `manual`). The user must manually POST every memory. The model never learns anything from conversations. This is the single biggest gap — it means "memory" is really just a user-maintained notes table.

### 2.2 Relevance filtering — **DOES NOT EXIST**
`_get_user_memories` fetches the **20 most recent active memories and injects ALL of them into EVERY chat**, regardless of whether the current question relates to them. A user asking "what's 2+2" gets their cat's name, job, favorite food, and color shoved into context. This wastes tokens, adds noise, can bias/derail answers, and does not scale past a handful of memories.

### 2.3 Token budget — **DOES NOT EXIST**
The only bound is `LIMIT 20`. A single memory `content` is unbounded text. 20 long memories can blow past thousands of tokens with no accounting, no truncation, no cost cap. On billed models this silently inflates every request's input cost. Hermes caps memory at a hard char budget (~2.2k) and rejects overflow; Multiai has nothing.

### 2.4 Semantic search — **DOES NOT EXIST (ILIKE only)**
`/memories/search` and any retrieval is substring `ILIKE '%q%'`. Searching "pet" will NOT find "I have a cat named Simba." No embeddings, no pgvector, no ranking by similarity. Retrieval is lexical and brittle.

---

## 3. Secondary Gaps

- **Massive code duplication.** The memory-injection block (build `[User Memories]`, find system idx, insert) is **copy-pasted at 3+ call sites** in chat.py (~lines 262, 353, 449) plus the soul block twice (~366, 460). Any fix (budget, relevance) must be made in every copy → drift risk. Should be one shared `inject_context(payload, uid)` helper.
- **No deduplication / consolidation.** Nothing prevents "I like blue" being stored 5 times. No merge, no supersede. Hermes does dedup + replace; Multiai grows unbounded.
- **Soul is a raw string.** `ai_personality` is injected verbatim with no length cap and no sanitization — a user can inject arbitrary instructions (prompt-injection surface) and unbounded tokens into every request's system prompt.
- **Dedup guard only on one path.** The first injection site checks `not any(... startswith('[User Memories]'))`; the other sites don't — a payload can end up with **duplicate** memory blocks depending on route.
- **No `updated_at` on create response** and inconsistent field sets returned across endpoints.
- **No pagination on list** (returns all active; search has LIMIT 50, list has none).
- **category/source are free-text**, no enum/validation — "test", "general", "preferences", "personal", "professional" coexist arbitrarily.
- **No importance/decay/last_used** columns — cannot rank or age out memories even if retrieval were added.

---

## 4. Comparison to Hermes Memory System

| Dimension | Hermes | Multiai | Gap |
|---|---|---|---|
| Population | Agent auto-saves durable facts proactively | Manual POST only | ✗✗✗ |
| Relevance | Curated, high-signal, injected as compact block | ALL 20 recent injected every turn | ✗✗✗ |
| Budget | Hard char cap (~2.2k), overflow rejected → forces consolidation | None (LIMIT 20, unbounded content) | ✗✗✗ |
| Retrieval | Whole curated set (small by design) | ILIKE substring for /search; LIMIT 20 for chat | ✗✗ |
| Dedup/consolidate | Batch replace/remove, atomic, dedup | None | ✗✗ |
| Structure | user vs memory targets, declarative facts | flat table, free-text category | ✗ |
| Guidance | "declarative facts, not instructions; skip trivia" | none | ✗ |

Multiai stores *more* (unbounded) but *understands* nothing. Hermes stores *less* but *curates*. Curation is the whole point.

---

## 5. Production Memory Plan (prioritized)

**P0 — Stop the bleeding (1–2 days)**
1. **Consolidate injection into one helper** `build_memory_context(uid) -> list[msg]` used by all chat paths. Kills duplication + drift. (Cross-ref S2/S6.)
2. **Add a token/char budget.** Cap injected memory block to e.g. 1500 chars; truncate lowest-priority first. Cap `ai_personality` to ~500 chars on write.
3. **Cap + sanitize soul** injection; strip obvious instruction-injection markers, enforce length on PUT of preferences.

**P1 — Make retrieval smart (3–5 days)**
4. **Add pgvector** (`content_embedding vector(N)`), compute embedding on POST/PUT (cheap embed model via existing LiteLLM). Retrieval = cosine top-k over the *current user query*, not "last 20." Fallback to ILIKE if embeddings unavailable.
5. **Relevance-gated injection:** only inject memories with similarity ≥ threshold to the latest user message; hard cap k (e.g. 6) + budget.
6. Add columns: `importance smallint`, `last_used_at`, `use_count` for ranking/decay.

**P2 — Auto-extraction (5–8 days)**
7. **Post-turn extraction job:** after an assistant reply, run a cheap model to extract durable facts ("declarative, skip trivia" per Hermes guidance), write with `source='auto'`, dedup against existing (embedding similarity > 0.9 → merge/skip). Make it async (background task/Celery — see tasks_router) so it never blocks streaming.
8. **Dedup/consolidate pass:** nightly or on-write merge near-duplicate memories, supersede stale ones.

**P3 — Polish**
9. Category enum + validation; pagination on list; importance decay; per-user memory count cap; UI to review/approve auto-extracted memories before they go active (`active=False` until user confirms).

---

## 6. Verdict

**Grade: D+.** CRUD is correct, secure enough (ownership checks, LIKE escaping, soft delete), and stable. But it is a manual notes table masquerading as memory: no auto-extraction (0 auto rows in DB), no relevance filtering (all injected every turn), no token budget (LIMIT 20 only), no semantic search (ILIKE only). For an "AI Agent Platform" positioning against AvalAI/GapGPT, this is a competitive liability. P0+P1 (budget + pgvector relevance + dedup) are the minimum to call this a real memory system; P2 auto-extraction is what would make it a differentiator.

**Files to change:** backend/chat.py (dedup injection → 1 helper), backend/dependencies.py (_get_user_memories → relevance+budget), backend/memory.py (embeddings on write, validation), backend/models.py (pgvector column + importance/last_used), new backend migration, optional backend/tasks.py (async extraction).
