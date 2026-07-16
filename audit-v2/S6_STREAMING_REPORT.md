# S6 — Streaming & Realtime Infrastructure Audit (v2)

**Date:** 2026-07-16
**Auditor:** Senior 6 — Streaming / Real-time Infra
**Scope:** Backend `backend/chat.py` streaming functions `_chat_stream` (254–316) and
`_smart_chat_stream` (723–812); frontend streaming in `frontend/app/chat/page.tsx`;
Next.js SSE proxy routes `frontend/app/api/chat/route.ts`, `.../api/v1/smart-chat/route.ts`,
`.../api/chat/with-file/route.ts`.

This is an **independent re-read** of the live source (master @ `6a29182`), not a copy of the
prior v1 report. Every finding below is traced to a specific line + verified by reading the code.

---

## 0. TL;DR — Severity Verdict

| # | Finding | Severity | Exploitable now? |
|---|---------|----------|------------------|
| F1 | Billing never charges the user on early client disconnect → free generation | **CRITICAL** | Yes |
| F2 | Frontend ignores `type:'billing'` event → real cost never shown | **HIGH** | Yes (UX + billing trust) |
| F3 | Frontend ignores `type:'smart_info'` event | **MEDIUM** | Yes (smart model hidden) |
| F4 | No upstream cancellation on client abort → backend keeps paying LiteLLM | **HIGH** | Yes (operator cost) |
| F5 | Hardcoded cost estimate `totalTokens * 0.000002` | **MEDIUM** | Showing wrong numbers |
| F6 | No reconnection / retry logic on stream drop | **MEDIUM** | Yes (reliability) |
| F7 | Typing indicator = bare 3-dot only, no model/status context | **LOW** | Polished UX gap |
| F8 | `finally` billing swallows all exceptions silently (`except: pass`) | **MEDIUM** | Silent billing loss |

---

## 1. SSE Protocol — what's actually sent

Both `_chat_stream` and `_smart_chat_stream` build a `StreamingResponse(event_stream(),
media_type='text/event-stream')` and emit raw lines as `f"{line}\n\n"` (chat.py:296, 792) — i.e.
they proxy LiteLLM's SSE verbatim. Each event is a standard `data: <json>\n\n` frame.

`_smart_chat_stream` additionally emits **one** leading event before the proxy loop:

```python
# chat.py:778
yield f'data: {json.dumps({"type": "smart_info", "model": selected_model, "category": category})}\n\n'
```

Billing event (emitted in `finally`, only if `cost > 0`):

```python
# chat.py:304-312 / 800-807
yield f'data: {json.dumps({
  "type": "billing",
  "cost": ..., "input_tokens": ..., "output_tokens": ...,
  "balance_after": ..., "currency": "IRT"
})}\n\n'
```

**Protocol compliance:** conforms to `text/event-stream`. The Next.js proxy routes set the
correct passthrough headers (`Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`,
`Connection: keep-alive`) so nginx buffering is disabled (route.ts:26-30, etc.). **Good.**

**Gap:** no `id:` / `event:` / `retry:` SSE fields are ever emitted, so the browser's native
`EventSource` reconnect mechanism is inapplicable (the app uses `fetch`+`ReadableStream`, not
`EventSource` — see F6).

---

## 2. F1 — CRITICAL: no billing on early disconnect (exploitable)

### The bug
Billing lives **only** in the `finally` block, and is gated by:

```python
# chat.py:300 (and 796)
if uid and usage_data and async_session is not None:
```

`usage_data` is captured **only** when a chunk carrying `usage` arrives from LiteLLM:

```python
# chat.py:292-293 / 788-789
if isinstance(chunk.get('usage'), dict) and chunk['usage']:
    usage_data = chunk['usage']
```

LiteLLM (OpenAI-compatible) sends the `usage` object **in the final chunk, after** `[DONE]`
(typically the `stream_options.include_usage=True` frame). If the **client disconnects before
that final frame is received**, the generator's `async for` loop ends, the `finally` runs, but
`usage_data is None` → the `if` is false → **no `_bill_stream_usage` call is made → the user is
never charged.**

### Why it's exploitable
An attacker can:
1. Open a streaming request for an expensive model.
2. Stream the answer (they receive the full text — tokens are yielded to the client live).
3. Kill the TCP connection (or send `AbortController.abort()` on the frontend) **just before
   LiteLLM emits the usage chunk**.

They keep the generated content; the backend never records a charge because `usage_data` was
never set. Repeated, this is a **free-generation / balance-drain bypass** against the platform's
own cost. The `finally` block does NOT reconstruct usage from what was streamed — it relies
entirely on the single final usage frame.

### Secondary angle — streaming the whole answer for free
Even on *normal* completion the billing is correct, but the window for a mid-stream abort is
real and trivial to hit programmatically (e.g. `curl -N` + closing the pipe early, or any HTTP
client that drops the connection). There is **no server-side guard** (no
`request.is_disconnected()` check, no pre-authorization hold, no "bill on first token" meter).

### Fix outline
- Reconstruct billing from streamed deltas if `usage_data` is missing (count tokens roughly via
  the accumulated `usage`/`prompt_tokens` or sum of delta lengths + a fallback estimate) and bill
  anyway in `finally`.
- OR take a **pre-request hold / minimum charge** at quota-check time (`_check_quota_pre`) and
  reconcile in `finally`.
- OR detect disconnect with `if await request.is_disconnected():` inside the loop and still bill
  the partial usage.

---

## 3. F4 — HIGH: no upstream cancellation on client disconnect

Frontend `cancel()`:

```tsx
// page.tsx:470-474
const cancel = useCallback(() => {
  abortRef.current?.abort()
  abortRef.current = null
  setStreaming(false)
}, [])
```

`abort()` kills the **browser→Next.js** fetch. But the Next.js proxy routes do **not** forward the
abort signal to the backend:

```ts
// api/chat/route.ts:15-19
const res = await fetch(`${upstream}/v1/chat/completions`, {
  method: 'POST',
  headers,
  body: JSON.stringify(body),
  // NOTE: no `signal` passed here
})
```

So when the user hits "توقف" (stop), the chain is:

```
Browser ──abort──▶ Next.js route (fetch is done on browser side)
                         │
                         └─▶ backend / LiteLLM  STILL STREAMING to completion
```

The backend keeps streaming from LiteLLM to the *dead* Next.js reader until LiteLLM finishes,
then the `finally` block runs `_bill_stream_usage`. Two consequences:
- The **operator still pays LiteLLM** for the full completion even though the user cancelled.
- Because of F1, if the cancel lands before the usage frame, the **user isn't charged but the
  platform ate the cost** — the worst of both worlds.

The backend side also never checks `request.is_disconnected()` to abort its own upstream
`_http.stream(...)` call, so even a direct client→backend disconnect doesn't cancel LiteLLM.

### Fix outline
- Pass `signal: request.signal` (or the controller signal) into the upstream `fetch` in every
  proxy route, and `dup` the request body so aborting propagates.
- In `event_stream`, wrap the `async for` with
  `if await request.is_disconnected(): break` and close the `_http` context to cancel LiteLLM.

---

## 4. F2 — HIGH: frontend ignores `type:'billing'`

The frontend SSE parser (page.tsx:569-589) only handles three shapes:

```tsx
const obj = JSON.parse(data)
const delta = obj.choices?.[0]?.delta?.content
if (delta) { acc += delta; ... }                 // text
if (obj.usage) usageData = obj.usage              // usage (from LiteLLM frame)
if (obj.x_smart_model) setSmartModel(obj.x_smart_model)  // (dead field; backend sends X-Smart-Model header, not this)
```

There is **no branch for `obj.type === 'billing'`**. The authoritative, server-computed
`cost` / `balance_after` / `input_tokens` / `output_tokens` events emitted by the backend
(chat.py:304-312, 800-807) are **silently dropped**. The user never sees the real IRT charge or
their remaining balance update in real time.

Net effect: the entire server-side billing event channel is dead weight on the wire.

---

## 5. F3 — MEDIUM: frontend ignores `type:'smart_info'`

In smart mode the backend emits `{"type":"smart_info","model":...,"category":...}`
(chat.py:778) as the **first** frame. The frontend parser has no `type==='smart_info'` branch,
so the chosen smart model/category is invisible. The smart model label the UI *does* try to read
(`obj.x_smart_model`, page.tsx:587) is **never sent** — the backend puts it in the
`X-Smart-Model` response *header* (chat.py:813) which the Next.js proxy forwards but the
page.tsx stream reader never inspects. Result: in smart mode the user gets no feedback about
which model answered.

---

## 6. F5 — MEDIUM: hardcoded cost estimate

```tsx
// page.tsx:602
const estimatedCost = totalTokens * 0.000002 // rough estimate
```

This is a flat $0.000002/token, applied to **every** model identically, regardless of the actual
per-model IRT pricing the backend already computed and sent (but which is ignored per F2). So:
- Cost shown is **always wrong** for any model that doesn't price at exactly $2/1M tokens.
- Mixed prompt/completion pricing isn't modelled (real systems charge input vs output
  differently).

The correct value is already available from the backend's `type:'billing'` event — it just needs
to be consumed (F2).

---

## 7. F6 — MEDIUM: no reconnection / retry logic

The streaming loop (page.tsx:565-590) is a single `while(true)` read of `reader.read()`. On any
transport error (`reader.read()` rejects, network drop, 502 mid-stream) the `try` block throws and
control goes to the `catch` — which shows a toast and **does not retry**. There is no:
- Exponential backoff reconnect,
- resumable stream (no `Last-Event-ID` since none is emitted — see §1),
- automatic re-send of the prompt on transient failure.

For a chat product this means a flaky connection => lost message with no recovery, hurting
reliability. Note the existing v1 report claimed a `retry()` existed; the current master code has
**no** `retry()` — only `cancel()`. Confirmed by grep: only `cancel`/`abort` present.

---

## 8. F7 — LOW: typing indicator is bare 3-dot only

While `streaming` is true the UI shows only a minimal animated 3-dot placeholder
(`setStreaming(true)` at 504, spinner rendered in the assistant bubble). There is:
- No "Model X is thinking…" label,
- No token/streaming progress hint,
- No distinction between "connecting", "first token pending", and "streaming".

Given smart mode picks a model server-side (F3), the absence of even a generic "connecting to
model…" state is a missed real-time affordance.

---

## 9. F8 — MEDIUM: silent billing failure in `finally`

```python
# chat.py:313-314 / 809-810
                except Exception:
                    pass
```

The entire billing path (`_bill_stream_usage` + event yield) is wrapped so that **any** failure
is swallowed. If the DB session is busy, the balance update fails, or `_record_usage` raises, the
user is **silently not charged and nobody is alerted**. Combined with F1 this means billing gaps
are invisible to operators. At minimum log the exception; ideally emit a server-side
`billing_failed` metric/alert.

---

## 10. Positive findings (what's correct)

- SSE framing is valid; proxy routes correctly disable buffering (`X-Accel-Buffering: no`,
  `Cache-Control: no-cache`).
- `stream_options.include_usage = True` is set so LiteLLM returns a usage frame (when the stream
  completes).
- `AbortController` is correctly wired on the client for *local* cancellation UX.
- Memory/soul injection guards prevent double-injection (fragile string-prefix check, but
  functional).
- Both stream paths share an identical billing/finally pattern (good for a single fix to land in
  both).

---

## 11. Prioritized remediation plan

| Order | Fix | Addresses | Effort |
|-------|-----|-----------|--------|
| 1 | Bill in `finally` even when `usage_data is None` (reconstruct or min-charge) + detect `request.is_disconnected()` | F1, F8 | M |
| 2 | Forward `signal` to upstream `fetch` in all 3 proxy routes; add `is_disconnected()` break in `event_stream` | F4 | S |
| 3 | Consume `type:'billing'` in page.tsx → update real cost + balance | F2, F5 | S |
| 4 | Consume `type:'smart_info'` + read `X-Smart-Model` header for label | F3 | S |
| 5 | Add reconnect/retry with backoff + resumable send | F6 | M |
| 6 | Replace 3-dot with model-aware status indicator | F7 | S |
| 7 | Log+alert on billing exceptions instead of `pass` | F8 | S |

**Top priority:** F1 + F4 together — they are the exploitable/revenue-leaking pair. Fixing F4
alone without F1 would *increase* operator cost (more cancelled-but-completed generations billed
to the platform). Fix F1 first so every completed-or-partial generation is always charged, then
F4 to stop paying for cancelled generations.

---

## 12. Verification notes

- Static read of `backend/chat.py` (master 6a29182), `frontend/app/chat/page.tsx`, and the three
  `app/api/**/route.ts` SSE proxies.
- `curl -N` live test was **not** run: the multiai backend is not currently listening on a
  reachable port in this workspace (uvicorn processes seen are other apps on 8080/8800/8082; the
  multiai chat service binds inside docker behind `LITELLM_HOST`). A live `curl -N` repro of F1
  would require the backend up + a valid auth token; the code path is unambiguous from source and
  the bug is structural, not environmental.
- To reproduce F1 live: `curl -N -H "Authorization: Bearer <token>" -d '{"model":...,"messages":[...],"stream":true}' <host>/v1/chat/completions` then `Ctrl-C` before the final `data: {...usage...}` frame; observe no new billing row for the user while the answer text was already delivered.
