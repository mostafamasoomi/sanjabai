# SENIOR 2 — Chat Page Deep Audit

**File:** `frontend/app/chat/page.tsx` (1022 lines)  
**Date:** 2026-07-14  
**Status:** READ-ONLY AUDIT  

---

## 1. Model Selector

**Rating: ✅ GOOD (with minor issues)**

- **Loading:** Uses `useCatalog()` hook which fetches from `/api/catalog/models`. Loading state shows skeleton, error shows error message, empty shows empty state. ✅
- **Selection persistence:** Model selection does NOT persist across page reloads. On mount, it tries (in order): URL `?model=` param → favorite models from localStorage → org default model from `/api/org/default-model` → `models[0]`. No explicit save of user's manual selection to localStorage. ⚠️ **BUG: Manual model selection is lost on page refresh.**
- **Correct model name sent:** Uses `model.providerModelId || model.id` when sending. ✅
- **UI:** Native `<select>` element with `displayName`. Functional but not premium UX. The `data-testid="model-select"` is present for testing. ✅

**Issues:**
1. **Model selection not persisted** — When user manually picks a model, it should be saved to localStorage and restored on reload.
2. **Race condition on model default:** The `/api/org/default-model` fetch and the favorites check can race. If org fetch resolves after favorites already set a model, the `if (!model)` guard prevents overwrite, which is correct. But the `return` inside the `.then()` callback doesn't actually stop execution of the `useEffect` — it just exits the `.then()` callback, so `setModel(models[0])` in the `.catch()` won't run. This is fine.

---

## 2. Message Input

**Rating: ✅ GOOD**

- **Textarea:** Yes, `<textarea>` with `rows={1}` and `fieldSizing: 'content'` for auto-grow. ✅
- **Shift+Enter for newline:** `handleKeyDown` checks `e.key === 'Enter' && !e.shiftKey` to submit; Shift+Enter passes through to the textarea. ✅
- **Enter to send:** Yes, calls `handleSubmit`. ✅
- **Disabled when empty:** Submit button has `disabled={(!input.trim() && !attachedFile) || streaming || !model}`. ✅
- **Placeholder:** Shows keyboard hint. ✅
- **Character count:** Shows at bottom when input has content. ✅

**Issues:**
1. No input length limit/validation visible. Could send extremely long messages.

---

## 3. Send Flow

**Rating: ✅ GOOD (with issues)**

- **Endpoint:** Routes to `/api/chat` (normal) or `/api/v1/smart-chat` (smart mode) or `/api/chat/with-file` (file upload). ✅
- **Streaming:** Full SSE streaming implementation with `ReadableStream` reader, `TextDecoder`, and `data:` line parsing. Accumulates delta content and updates messages reactively. ✅
- **Error handling:** 
  - Catches `AbortError` for cancelled requests — shows "تولید متوقف شد." ✅
  - Detects balance errors (`code === 'balance'` or 429) — shows special balance UI with links to pricing/wallet. ✅
  - General errors show inline error message. ✅
- **Auto-save:** Saves messages to conversation after streaming completes, and also on error (partial progress). ✅
- **Usage stats:** Parses `usage` from stream and tracks token counts + estimated cost. ✅

**Issues:**
1. **`/api/v1/smart-chat` route does NOT exist** in the frontend API routes. The page sends to this path but there's no Next.js route handler at `frontend/app/api/v1/smart-chat/route.ts`. This means smart mode will 404 unless the backend is directly proxied. ⚠️ **BUG: Smart mode chat endpoint missing.**
2. **`web_search` param not sent in file upload mode** — when `attachedFile` is set, `webSearch` is ignored. Minor but worth noting.
3. **`assistant_id` not sent in file upload mode** — same issue.
4. **Cost estimate is rough:** `totalTokens * 0.000002` is a flat rate regardless of model pricing. The `ModelCatalogItem` has per-model pricing (`inputPerMillion`, `outputPerMillion`) that could be used instead.

---

## 4. Conversation Sidebar

**Rating: ✅ GOOD**

- **Load conversations:** Fetches from `/api/conversations` on mount with auth headers. Shows skeleton while loading. ✅
- **Switch between them:** `loadConversation(id)` fetches `/api/conversations/${id}`, loads messages, sets model from conversation, closes mobile drawer. ✅
- **Delete:** Two-click confirm pattern (first click shows check icon, second click deletes). 3-second timeout to reset confirm. Shows spinner while deleting. ✅
- **Create new:** `startNewChat()` resets state. Auto-creates conversation on first user message via `createConversation()`. ✅
- **Date formatting:** Relative time (minutes ago, hours ago, days ago) with Persian locale. ✅
- **Model badge:** Shows model name on each conversation item. ✅

**Issues:**
1. **No search/filter** for conversations. Large lists will be hard to navigate.
2. **No pagination** — loads all conversations at once.
3. **Conversation title** is first 50 chars of first user message. No way to rename.
4. **Backend proxy is thin** — `conversations/route.ts` GET silently returns `[]` on error (line 21), masking real failures.

---

## 5. Web Search Toggle

**Rating: ✅ GOOD**

- **Toggle:** Button with globe icon, toggles `webSearch` state. Visual feedback with accent color when active. ✅
- **Persists:** Saves to `localStorage` key `multiai_web_search`. ✅
- **Sends param:** `...(webSearch ? { web_search: true } : {})` in request body. ✅
- **Shows results:** No — web search results are not displayed separately. They're presumably included in the LLM's response text. ⚠️

**Issues:**
1. No visual indication of whether web search actually returned results.
2. Not sent during file upload mode.

---

## 6. File Upload

**Rating: ⚠️ PARTIAL**

- **Accept files:** Yes, `<input type="file" accept=".txt,.md,.csv,.json,.pdf,.text,.log">`. ✅
- **Show preview:** Shows filename with paperclip icon and remove button. No file content preview. ⚠️
- **Send correctly:** Uses `FormData` with file, model, messages, stream. Sent to `/api/chat/with-file` which proxies to backend `/v1/chat/with-file`. ✅
- **Auth:** Sends `Authorization` header with FormData (no Content-Type — browser sets multipart boundary). ✅

**Issues:**
1. **No file size limit** enforced client-side. Large files could cause issues.
2. **No file content preview** — user can't verify file contents before sending.
3. **No upload progress indicator.**
4. **No image support** — accepted types are text-based only. No `.png`, `.jpg`, etc.
5. **File is cleared after send** (`setAttachedFile(null)`) — correct behavior.

---

## 7. Smart Mode Toggle

**Rating: ⚠️ PARTIAL (broken endpoint)**

- **Toggle:** Checkbox styled as switch. Visual feedback with knob animation. ✅
- **Persists:** Saves to `localStorage` key `multiai_smart_mode`. ✅
- **Sends model header:** `X-Smart-Model: {model.providerModelId}` when smart mode is on. ✅
- **Shows smart model:** After streaming, if `obj.x_smart_model` is in the response, displays it as a badge. ✅
- **Endpoint:** Routes to `/api/v1/smart-chat` — **this route does not exist** in the frontend. ⚠️ **BUG**

**Issues:**
1. **Critical: `/api/v1/smart-chat` route is missing.** Smart mode will fail with 404.
2. Smart mode is disabled when file is attached (falls back to normal `/api/chat`). This is intentional but not communicated to the user.

---

## 8. Quick Actions (Presets)

**Rating: ✅ GOOD**

- **4 presets:** Code, Translation, Summarization, Analysis — with Persian labels. ✅
- **Populate input:** No — they directly call `sendMessage(prompt)` rather than populating the input field. This means clicking a preset immediately sends the message. ✅ (but different from "populate input" pattern)
- **Conditional display:** Only shown when `showPresets && messages.length <= 1`. Hidden after first message. ✅

**Issues:**
1. Presets send immediately rather than populating the textarea for user editing. This is a design choice but may surprise users.
2. Presets are hardcoded — not configurable.

---

## 9. Loading States

**Rating: ✅ GOOD**

- **Streaming indicator:** "در حال تولید..." with animated dot in composer footer. ✅
- **Typing indicator:** Three-dot animation in assistant bubble while waiting for first token. ✅
- **Cancel button:** Appears in model bar during streaming. ✅
- **Disabled button:** Send button disabled during streaming. ✅
- **Error messages:** Inline error display with special handling for balance errors. ✅
- **Skeleton loaders:** Model selector shows skeleton while catalog loads. Conversation list shows skeletons. ✅

**Issues:**
1. No global loading overlay — user can interact with other elements during streaming.
2. No retry button on general errors (only on assistant messages via the retry action).

---

## 10. Auth Handling

**Rating: ✅ GOOD**

- **Auth headers:** `authHeaders()` returns `{ Authorization: 'Bearer ${token}', Content-Type: 'application/json' }`. Used consistently for all API calls. ✅
- **Token source:** From `useAuth()` context which reads from `localStorage.getItem('auth_token')`. ✅
- **401 handling:** The auth provider handles 401/403 by clearing token and user state. The chat page itself doesn't handle 401 specifically — it relies on the auth context. ⚠️
- **No-token behavior:** Many functions have `if (!token) return` guards. Chat still works without token (just no conversation persistence). ✅

**Issues:**
1. **No 401 interception during chat** — if token expires mid-conversation, the streaming request will fail with a generic error rather than redirecting to login.
2. **File upload with no token** — the `fh` object for file upload only includes auth if token exists, which is correct, but the backend may reject unauthenticated file uploads.

---

## 11. Assistant Integration

**Rating: ✅ GOOD**

- **URL param:** Reads `?assistant=` from search params. ✅
- **Fetch assistant:** Loads from `/api/assistants/${assistantParam}` with auth. ✅
- **Banner:** Shows assistant name, description, icon, and settings link. ✅
- **Model override:** If assistant has `model_id`, sets model from catalog. ✅
- **Send with assistant:** `...(activeAssistant ? { assistant_id: activeAssistant.id } : {})` in request body. ✅
- **Loading state:** Shows skeleton while assistant loads. ✅

**Issues:**
1. **`assistant_id` not sent in file upload mode.**
2. **No system prompt injection visible** — the assistant has `system_prompt` field but it's not used client-side (presumably the backend handles it).
3. **Race condition:** If `models` array changes (re-fetch), the `useEffect` that loads the assistant re-runs because `models` is in the dependency array, potentially re-fetching the assistant unnecessarily.

---

## 12. Export

**Rating: ❌ BROKEN**

- **UI:** Export dropdown with JSON/Markdown/Text options. Only visible when `activeConversationId` exists. ✅
- **Endpoint:** Calls `/api/conversations/${id}/export?format=${format}`. ❌ **This route does NOT exist.** There is no `frontend/app/api/conversations/[id]/export/route.ts` file.
- **Download:** Uses `blob()` + `URL.createObjectURL` + hidden `<a>` click. Pattern is correct. ✅

**Issues:**
1. **Critical: Export endpoint is missing.** The export feature will always fail with 404.
2. The toast shows "خطا در خروجی گرفتن" (export error) every time.

---

## 13. Responsive / Mobile

**Rating: ✅ GOOD**

- **Mobile detection:** `window.innerWidth < 768` with resize listener. ✅
- **Mobile drawer:** Conversation sidebar becomes a slide-out drawer with overlay. ✅
- **Hamburger menu:** Shows menu icon on mobile to open drawer. ✅
- **Desktop sidebar:** Can be collapsed/expanded. ✅
- **Close on navigate:** Drawer closes when conversation is loaded. ✅

**Issues:**
1. No bottom safe area handling for the chat composer on mobile (the AppShell has `safe-bottom` class on bottom nav, but the chat page's composer doesn't).
2. The model bar could overflow on small screens with many elements (model select + smart mode + export + provider badge + cancel button).

---

## Related Files Audit

### `frontend/app/api/chat/route.ts`
- Proxies to backend `${upstream}/v1/chat/completions`. ✅
- Passes through streaming SSE. ✅
- Forwards auth headers. ✅
- Default upstream: `http://multiai-multiai_api-1:8000`. ✅

### `frontend/app/api/chat/with-file/route.ts`
- Proxies to backend `${upstream}/v1/chat/with-file`. ✅
- Passes through streaming SSE. ✅
- Forwards auth headers. ✅
- Uses `nodejs` runtime (required for FormData streaming). ✅

### `frontend/app/api/conversations/route.ts`
- GET: proxies to `/conversations`, returns `[]` on error. ⚠️ Silently masks errors.
- POST: proxies to `/conversations` with body. ✅

### `frontend/app/api/conversations/[id]/route.ts`
- GET/PUT/DELETE all proxy to backend. ✅
- PUT returns `{ status: 'ok' }` instead of the actual response data. Minor.

### `frontend/components/AppShell.tsx`
- Global sidebar with navigation. ✅
- Mobile bottom nav with main items. ✅
- Mobile overlay drawer for full nav. ✅
- First-visit onboarding redirect. ✅
- Command palette (⌘K). ✅
- User menu with profile/dashboard/logout. ✅

---

## Summary of Critical Issues

| # | Severity | Issue |
|---|----------|-------|
| 1 | 🔴 Critical | `/api/v1/smart-chat` route does not exist — Smart Mode is broken |
| 2 | 🔴 Critical | `/api/conversations/[id]/export` route does not exist — Export is broken |
| 3 | 🟡 Medium | Model selection not persisted across page reloads |
| 4 | 🟡 Medium | `assistant_id` and `web_search` not sent in file upload mode |
| 5 | 🟡 Medium | No 401 interception during active chat session |
| 6 | 🟡 Medium | Cost estimate uses flat rate instead of per-model pricing |
| 7 | 🟢 Low | No file size limit or content preview for uploads |
| 8 | 🟢 Low | No conversation search/filter or pagination |
| 9 | 🟢 Low | Presets send immediately instead of populating input |
| 10 | 🟢 Low | Model bar can overflow on small mobile screens |

## Summary of Strengths

- Well-structured component with clear separation of concerns
- Robust streaming implementation with proper abort handling
- Good error differentiation (balance vs general errors)
- Two-click delete confirmation pattern
- Auto-save of conversation messages
- Persian/RTL UI throughout
- Proper mobile responsive layout with drawer pattern
- Usage stats tracking with token counts
