# Compare: history + continued conversation (per-side or broadcast)

Date: 2026-08-30
Status: approved by owner, ready for implementation
Migration slot: `0054` (next free per docs/NEXT-SESSION.md)

## Problem

`/v1/compare` (`backend/chat_compare.py`) is fully stateless: one prompt in,
two model answers out, nothing persisted. `frontend/app/compare/page.tsx`
renders exactly one turn and throws it away on the next comparison. Owner
wants: (1) a history of past comparisons the user can reopen, (2) the
ability to continue a comparison — one message to both models at once, or a
message to only one side, without touching the other side's thread.

## Data model

New table `compare_sessions` (migration `0054`), same shape convention as
`Conversation` (models/_conversations.py) — a JSON blob per side, no
separate messages table, since neither `conversations` nor scheduled tasks
needed one and the same read/write pattern (one row per session, JSON
column of `{role, content}` dicts) applies here unchanged.

```sql
CREATE TABLE compare_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    model_a TEXT NOT NULL,             -- canonical provider_model_id
    model_b TEXT NOT NULL,
    model_a_requested TEXT NOT NULL,   -- what the user picked; echoed back,
    model_b_requested TEXT NOT NULL,   -- never the resolved provider id
    title TEXT NOT NULL DEFAULT '',
    thread_a JSONB NOT NULL DEFAULT '[]',
    thread_b JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_compare_sessions_user ON compare_sessions(user_id, updated_at DESC);
```

`thread_a`/`thread_b` are independent, undeduplicated arrays — after a
solo message to side A, A and B threads simply diverge from that point.
No shared-prefix pointer; the data volume is trivial (same as any chat
conversation) and a pointer scheme adds a failure mode for no real saving.

ORM model goes in `backend/models/_conversations.py` next to `Conversation`
(same file, same concern — conversation-shaped persistence).

## API (`backend/chat_compare.py`)

- `POST /v1/compare` — unchanged request/response shape, but now also
  creates a `compare_sessions` row (title auto-generated from the prompt,
  same `_auto_generate_title` truncation logic as `conversations.py`) and
  adds `session_id` to the JSON response. Non-breaking addition.

- `POST /v1/compare/sessions/{id}/continue` — body
  `{target: 'both'|'a'|'b', content: str, web_search?: bool}`.
  - 404 if the session doesn't belong to the caller (`WHERE user_id = :uid`,
    same ownership pattern as every `conversations.py` route — no separate
    ownership-check helper exists in this codebase, don't add one).
  - Appends `{role: 'user', content}` to the target thread(s).
  - Calls `_call_model_once` for the model(s) in scope only — `target='a'`
    must reserve/settle billing for model A alone, never touch B's
    reservation. `target='both'` reuses the existing dual-reserve /
    `asyncio.gather` / dual-release flow from `compare_models` verbatim.
  - Appends the assistant reply to each thread that was called, persists
    `thread_a`/`thread_b` + `updated_at`.
  - Response: `{model_a: result|null, model_b: result|null, faster, cheaper}`
    — `faster`/`cheaper` only computed when both ran this turn (same rule
    as today), `null` for the side not called this turn.

- `GET /v1/compare/sessions` — list, paginated exactly like
  `GET /conversations` (`page`/`limit` query params, `limit` capped at 100,
  `ORDER BY updated_at DESC`). Row shape: `id, title, model_a_requested,
  model_b_requested, created_at, updated_at`. Thread bodies excluded (same
  reason the conversations list excludes `messages`).

- `GET /v1/compare/sessions/{id}` — full row including both threads, for
  reopening in the UI.

- `DELETE /v1/compare/sessions/{id}` — mirrors
  `DELETE /conversations/{conv_id}`.

All five routes: `_get_user_id` auth check first, 401 if absent, same as
every existing route in this file — no new auth pattern.

## Frontend (`frontend/app/compare/`)

- Result panels change from single Q/A snapshot to a scrollable per-side
  turn list (each side renders its own `thread` array independently — they
  can have different lengths after a solo message).
- New history sidebar, modeled on `ConversationSidebar.tsx` /
  `useConversations.ts` (same list/open/delete affordances, own
  `useCompareSessions` hook hitting the endpoints above).
- Composer: the existing shared textarea + primary send button becomes
  "send to both" (`target: 'both'`) once a session exists. Add one small
  secondary send button under each result panel — pressing it sends the
  *same composer text* to only that side (`target: 'a'` or `'b'`) and
  clears the shared textarea after. No second textarea, no target selector
  — this was the owner's explicit choice over a segmented-control design.
- First message (no session yet) keeps calling `POST /v1/compare` as today;
  once `session_id` comes back, subsequent sends (both the primary button
  and the two per-side buttons) call the `continue` endpoint instead.
- Opening a history entry loads both threads via `GET
  .../sessions/{id}` and switches the page into "existing session" mode
  (same composer behavior as above, no `POST /v1/compare` call happens
  again for that session).

## Billing / correctness notes carried over from `compare_models`

- Free-tier and premium quota gates already batch both models in one call
  in the original endpoint specifically so a rejection on the second model
  never burns the first one's allowance — a solo-target continue call must
  gate on the *one* model actually being charged, not run the two-model
  batched gate for a single-model call.
- Web search injection happens once on the outbound `messages`, never
  per-model, same as today.
- `_call_model_once`'s comment about not mutating the shared `messages`
  list across concurrent `asyncio.gather` calls still applies to
  `target='both'`.

## Testing

- Backend: extend `tests/test_compare_web_search.py` /
  `tests/test_compare_stream_guard.py` siblings with a new
  `tests/test_compare_sessions.py` — session creation on first compare,
  continue-both persists both threads, continue-a/continue-b persists only
  the targeted thread and leaves the other untouched, ownership check (404
  on another user's session id), billing reserve/release scoped correctly
  per target.
- Frontend: no existing Playwright spec covers `/compare` yet — add one
  covering: first compare creates a session, continue-both grows both
  columns, solo-send to one side leaves the other column's turn count
  unchanged, reopening from history restores both threads.
- Wiring guard: per the project's standing rule (three past incidents of
  fully-tested-but-never-mounted code), the history sidebar and the two
  per-side send buttons need a test that fails if the senior forgets to
  actually mount/wire them into `page.tsx` — not just that the components
  compile in isolation.

## Out of scope

- No target selector UI (owner picked shared composer + per-side buttons).
- No dedup/shared-prefix storage for diverged threads.
- No change to the existing single-shot response shape's fields — only
  additive (`session_id`).
