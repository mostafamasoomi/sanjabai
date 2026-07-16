# Phase 3: Model Compare — Implementation Report

**Date:** 2026-07-16
**Status:** COMPLETE

---

## Overview

Built the Model Compare feature — a split-view comparison of two AI models side-by-side, with backend `/v1/compare` endpoint running both models in parallel and a frontend compare page showing results with timing, token usage, and cost.

---

## Backend: `/v1/compare` Endpoint

### File: `backend/chat.py`

**New model:**
```python
class CompareRequest(BaseModel):
    model_a: str
    model_b: str
    messages: list = []
    stream: bool = False
```

**New helper: `_call_model_once()`**
- Calls a single model through LiteLLM
- Injects memory/soul context via `get_injection_messages()` + `inject_messages()`
- Applies message compression
- Tracks timing with `time.monotonic()` for high-precision elapsed measurement
- Records usage + billing via `_track_usage()`
- Returns structured result: `{model, content, elapsed, input_tokens, output_tokens, cost, error}`

**New route: `POST /v1/compare`**
- Authenticates user via `_get_user_id()`
- Validates both models via `_is_model_allowed()`
- Reserves billing for both models via `BillingService.reserve()` — falls back to legacy `_check_quota_pre()` if BillingService fails
- Runs both models in parallel using `asyncio.gather()` — both calls fire simultaneously, not sequentially
- Releases reservations after both complete
- Determines winner stats: `faster` (which model had lower elapsed time) and `cheaper` (which model had lower cost)
- Returns JSON response:
```json
{
  "model_a": { "model": "...", "content": "...", "elapsed": 1.23, "input_tokens": 100, "output_tokens": 200, "cost": 300, "error": null },
  "model_b": { ... },
  "faster": "model_a",
  "cheaper": "model_b",
  "messages": [...]
}
```

### Design decisions:
- **Non-streaming first** — keeps it simple, both models complete before returning
- **Parallel execution** — `asyncio.gather` ensures both models run concurrently, not one after the other
- **Separate billing reservations** — each model gets its own reservation, both released after completion
- **Error resilience** — if one model fails, the other's result is still returned; errors are captured per-model

---

## Frontend: Compare Page

### API Proxy: `frontend/app/api/v1/compare/route.ts`
- Standard Next.js API route proxy pattern (matching existing `/api/chat` and `/api/v1/smart-chat`)
- Forwards requests to backend at `${NEXT_PUBLIC_API_URL}/v1/compare`
- Passes through auth headers

### Page: `frontend/app/compare/page.tsx`
**Split view layout:**
- **Top controls card:** Two model pickers (A and B) with a "VS" divider, prompt input, and submit button
- **Results area:** Two side-by-side panels (grid: 1fr 1fr), responsive stack on mobile

**Each result panel shows:**
- Model name + provider badge
- Winner badges: ⚡ سریعتر (faster) and 💰 ارزانتر (cheaper)
- Stats bar: زمان (elapsed), توکن ورودی (input tokens), توکن خروجی (output tokens), هزینه (cost in IRT)
- Content area with Markdown rendering (reuses MarkdownRenderer from chat)
- Loading spinner, error state, and empty placeholder states

**Key features:**
- Model pickers filter out each other's selection to prevent duplicate picks
- Ctrl+Enter keyboard shortcut to submit
- Real cost display in IRT (tomans)
- Winner highlighting: green text for faster/cheaper stats
- Mobile responsive: stacks vertically on small screens

### Chat Page Integration: `frontend/app/chat/page.tsx`
- Added `Link` import from `next/link`
- Added a **Compare button** (⚖️ icon) in the model bar, between Smart Mode and Export
- Links to `/compare` — opens the compare page in the same tab

### Styles: `frontend/app/globals.css`
- ~300 lines of CSS added at the end of the file
- Uses existing design tokens (`--bg-surface`, `--border`, `--accent`, etc.)
- Color-coded badges: indigo for Model A, pink for Model B
- Green for winner stats (faster/cheaper)
- Full responsive breakpoint at 768px

---

## Verification

| Check | Result |
|-------|--------|
| `python3 -m py_compile backend/chat.py` | ✅ PASS |
| `npm run build` (frontend) | ✅ PASS |
| `/compare` page built | ✅ 2.82 kB, static |
| `/api/v1/compare` route built | ✅ Dynamic |

---

## Files Created/Modified

| File | Action |
|------|--------|
| `backend/chat.py` | MODIFIED — Added `CompareRequest` model, `_call_model_once()` helper, `POST /v1/compare` route |
| `frontend/app/api/v1/compare/route.ts` | CREATED — API proxy for `/v1/compare` |
| `frontend/app/compare/page.tsx` | REWRITTEN — Split-view compare page |
| `frontend/app/chat/page.tsx` | MODIFIED — Added `Link` import + compare button |
| `frontend/app/globals.css` | MODIFIED — Added ~300 lines of compare page styles |

---

## Next Steps (Phase 4+)

1. **Streaming compare** — SSE with events for model_a and model_b, streaming both responses simultaneously
2. **Multi-model compare** — Support 3-4 models in the compare view
3. **Persist compare sessions** — Save compare results to conversation history
4. **Share compare results** — Generate shareable links
5. **Prompt library integration** — Quick access to test prompts from the compare page