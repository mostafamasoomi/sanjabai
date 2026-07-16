# Streaming Implementation Audit Report
## Multiai — S6: SSE, Billing Accuracy, Cancel, Reconnect, Typing Indicators

**Audit Date:** 2026-07-16  
**Auditor:** Senior Streaming & Real-time Infrastructure Engineer  
**Scope:** Backend `chat.py` (lines 254-316, 723-812), Frontend `page.tsx` streaming

---

## ۱. خلاصه فارسی (Persian Summary)

ارزیابی پیاده‌سازی استریمینگ چندای (Multiai) نشان می‌دهد که معماری کلی SSE (Server-Sent Events) به درستی کار می‌کند و توکن‌ها به صورت لحظه‌ای به کاربر نمایش داده می‌شوند. با این حال، چند مشکل جدی وجود دارد:

- **باگ بحرانی:** در صورت قطع شدن اتصال کاربر قبل از دریافت chunk usage، هزینه‌ای از کاربر کسر نمی‌شود (قابل سوءاستفاده)
- **باگ مهم:** فرانت‌اند رویداد `type: 'billing'` را پردازش نمی‌کند — اطلاعات هزینه واقعی هرگز به کاربر نمایش داده نمی‌شود
- **باگ مهم:** رویداد `type: 'smart_info'` در فرانت‌اند نادیده گرفته می‌شود
- **نبودن قابلیت اتصال مجدد (Reconnection):** در صورت قطع ارتباط، کاربر باید دوباره درخواست را ارسال کند
- **نبودن typing indicator پیشرفته:** فقط انیمیشن سه‌نقطه ساده وجود دارد

توصیه می‌شود این مشکلات قبل از release برطرف شوند.

---

## ۲. Streaming Architecture

### 2.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT (Browser)                              │
│                                                                      │
│  ┌──────────────┐    fetch() + AbortController                       │
│  │  page.tsx    │────────────────────────────────────────────┐       │
│  │              │   ReadableStream reader                    │       │
│  │  cancel()    │   TextDecoder → parse SSE lines            │       │
│  │  retry()     │   setMessages(acc) per chunk               │       │
│  └──────────────┘                                            │       │
│       ▲                                                      │       │
│       │ AbortController.abort()                              │       │
│       │ on "توقف" button click                               │       │
└───────┼──────────────────────────────────────────────────────┼───────┘
        │                                                      │
        │  HTTP POST /v1/chat/completions  (stream: true)      │
        │  HTTP POST /v1/smart-chat         (stream: true)     │
        │                                                      │
┌───────┴──────────────────────────────────────────────────────┴───────┐
│                     BACKEND (FastAPI)                                │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  chat.py                                                      │   │
│  │                                                                │   │
│  │  /v1/chat/completions ──► _chat_stream()                      │   │
│  │  /v1/smart-chat       ──► _smart_chat_stream()                │   │
│  │                                                                │   │
│  │  Both return: StreamingResponse(event_stream(),               │   │
│  │              media_type='text/event-stream')                   │   │
│  │                                                                │   │
│  │  event_stream() generator:                                     │   │
│  │    1. Set stream=True, include_usage=True                      │   │
│  │    2. POST to LiteLLM /v1/chat/completions                     │   │
│  │    3. async for line in r.aiter_lines():                       │   │
│  │         yield f"{line}\n\n"         ← proxy each SSE line      │   │
│  │         capture usage from final chunk                         │   │
│  │    4. finally:                                                 │   │
│  │         if usage_data:                                         │   │
│  │           _bill_stream_usage(uid, payload, usage_data)         │   │
│  │           yield billing event (type: 'billing')                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                       │
│                              │ HTTP POST (stream)                    │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  LiteLLM Proxy (127.0.0.1:4000)                               │   │
│  │  /v1/chat/completions → actual model provider                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Protocol: Server-Sent Events (SSE)

The backend uses **standard SSE** with `text/event-stream` content type. Each event is formatted as:

```
data: {json}\n\n
```

This is confirmed by the curl test output showing `data: {...}` lines followed by double newlines.

**Not EventSource:** The frontend does NOT use the browser's native `EventSource` API. Instead, it uses `fetch()` with response body streaming (`ReadableStream`), which gives more control (custom headers, POST method, abort signal).

### 2.3 Streaming Flow

1. **Backend receives request** with `stream: true`
2. **Pre-flight checks**: auth, quota, balance, memory injection, soul injection, web search
3. **Streaming path** (`_chat_stream` or `_smart_chat_stream`):
   - Creates a `StreamingResponse` with `text/event-stream`
   - The inner `event_stream()` generator:
     - Sets `stream: true` and `include_usage: true` in the payload
     - Opens an `httpx` stream to LiteLLM
     - Proxies each SSE line from LiteLLM to the client
     - Captures the `usage` field from the final chunk
     - In `finally`: bills the user and yields a billing event
4. **Frontend receives** the stream:
   - Reads chunks via `ReadableStream.getReader()`
   - Parses SSE lines (`data: {...}`)
   - Extracts `delta.content` from each chunk
   - Updates React state with accumulated content
   - Captures `usage` data for local stats

---

## ۳. Quality Assessment

### 3.1 What Works Well ✅

| Feature | Status | Details |
|---------|--------|---------|
| SSE proxying | ✅ Working | Backend correctly proxies LiteLLM SSE to clients |
| Token streaming | ✅ Working | Tokens arrive in real-time, frontend renders per-chunk |
| Partial message updates | ✅ Working | `setMessages(acc)` updates on every chunk |
| Stop button | ✅ Working | `AbortController.abort()` + `setStreaming(false)` |
| Cancel on AbortError | ✅ Working | Frontend shows "تولید متوقف شد." on abort |
| Billing in finally block | ✅ Working | Billing runs after stream completes |
| include_usage flag | ✅ Working | Backend requests usage data from LiteLLM |
| Smart-chat stream | ✅ Working | `smart_info` event emitted at start |
| Memory injection | ✅ Working | Memories injected before streaming |
| Soul injection | ✅ Working | Soul injected before streaming |

### 3.2 Quality Score: 6.5/10

Deducted for:
- No billing on disconnect (critical)
- Frontend ignores billing events (major)
- No reconnection (major)
- Frontend usage stats use hardcoded estimate (minor)
- No EventSource fallback (minor)

---

## ۴. Bugs Found

### 🐛 BUG-1: [CRITICAL] No billing on mid-stream disconnect

**Location:** `chat.py` lines 275-314, `_chat_stream.event_stream()`

**Description:** When the client disconnects before the final `usage` chunk arrives from LiteLLM, the `usage_data` variable remains `None`. The `finally` block only bills if `usage_data` is truthy:

```python
finally:
    if uid and usage_data and async_session is not None:  # ← usage_data is None
        ...
```

**Exploit:** A malicious user can:
1. Start a streaming request
2. Disconnect after receiving most of the response
3. Before the usage chunk arrives
4. Result: They get free tokens (no billing)

**Root cause:** The `usage_data` is only set when the final chunk containing `usage` arrives. If the client disconnects before that, the `finally` block runs but `usage_data` is still `None`.

**Reproduction:**
```bash
timeout 2 curl -N -X POST .../v1/chat/completions \
  -d '{"stream":true, "messages":[...]}' > /dev/null
# Ledger shows no debit entry
```

### 🐛 BUG-2: [MAJOR] Frontend ignores billing events from stream

**Location:** `page.tsx` lines 569-588

**Description:** The backend yields a `type: 'billing'` event at the end of the stream:
```json
{"type": "billing", "cost": 11, "input_tokens": 14, "output_tokens": 62, "balance_after": 99989, "currency": "IRT"}
```

The frontend parsing loop only handles:
- `obj.choices?.[0]?.delta?.content` → content update
- `obj.usage` → usage stats (using hardcoded estimate)
- `obj.x_smart_model` → smart model display

The `type: 'billing'` event is **completely ignored**. The frontend uses a hardcoded estimate `totalTokens * 0.000002` instead of the actual cost from the backend.

**Impact:** Users never see their actual balance after streaming. The usage stats displayed are inaccurate.

### 🐛 BUG-3: [MAJOR] Frontend ignores smart_info event

**Location:** `page.tsx` lines 569-588

**Description:** The backend yields a `type: 'smart_info'` event at the start of smart-chat streaming:
```json
{"type": "smart_info", "model": "qwen3-coder-free", "category": "simple"}
```

The frontend checks `obj.x_smart_model` (camelCase) but the backend sends `model` (lowercase) inside the `smart_info` event. The backend also sets `X-Smart-Model` header, but that's not accessible from response body streaming.

**Impact:** Smart model selection info is not displayed to the user during streaming.

### 🐛 BUG-4: [MINOR] Frontend usage estimate is hardcoded

**Location:** `page.tsx` line 602

```typescript
const estimatedCost = totalTokens * 0.000002 // rough estimate
```

This hardcoded rate doesn't match the actual pricing from `model_catalog`. The backend sends the real cost in the billing event, but it's ignored.

---

## ۵. Missing Features

### 5.1 Reconnection Logic ❌

**Status: Not implemented**

There is no automatic reconnection when the stream drops. If the connection is lost:
- The frontend stops receiving chunks
- The `while(true)` loop exits (or hangs)
- The user must manually retry

**Recommendation:** Implement exponential backoff reconnection with:
- Track last received chunk sequence number
- On reconnect, send `last_event_id` header
- Resume from last known position

### 5.2 Typing Indicator (Advanced) ⚠️

**Status: Partial — basic dots only**

The frontend shows a bouncing dots animation (`chat-typing`) when `streaming && isLast && !msg.content`. This is a simple CSS animation.

**Missing:**
- No "Typing..." text with model name (e.g., "GPT-4o is typing...")
- No estimated time remaining
- No token count as they arrive
- No stop button that's clearly visible during generation

**Note:** The footer does show "در حال تولید..." (Generating...) with a pulsing dot, which is a secondary indicator.

### 5.3 Cancel/Abort ✅ (partially)

**Status: Implemented but can be improved**

- `AbortController` is used correctly
- `cancel()` function calls `abort()` and sets `streaming=false`
- `AbortError` is caught and shows "تولید متوقف شد."
- **Missing:** The backend doesn't know the user cancelled. The LiteLLM request continues to completion (wasting upstream resources). The backend should detect client disconnect and cancel the upstream request.

### 5.4 Partial Message Updates ✅

**Status: Implemented**

Each chunk updates the message content via `setMessages(prev => ...)` with the accumulated text. This works correctly.

### 5.5 Token Counting During Streaming ❌

**Status: Not visible during streaming**

Token counts are only available at the end (from the final usage chunk). There's no real-time token counter during streaming. The frontend could:
- Count tokens from the accumulated text using a tokenizer
- Show tokens/second speed
- Estimate remaining time

---

## ۶. Recommendations

### 6.1 Immediate Fixes (Critical)

1. **Fix billing on disconnect (BUG-1):**
   ```python
   # In finally block, track partial usage
   finally:
       if uid and async_session is not None:
           # If we have usage_data (stream completed normally), bill full amount
           # If we don't have usage_data (client disconnected), estimate and bill
           if usage_data:
               await _bill_stream_usage(uid, payload, usage_data)
           else:
               # Estimate usage from accumulated tokens
               estimated_usage = {
                   'prompt_tokens': len(payload.get('messages', [])),
                   'completion_tokens': accumulated_tokens,
                   'total_tokens': accumulated_tokens + len(payload.get('messages', []))
               }
               await _bill_stream_usage(uid, payload, estimated_usage)
   ```

2. **Handle billing event in frontend (BUG-2):**
   ```typescript
   // In the parsing loop
   if (obj.type === 'billing') {
     setUsageStats(prev => ({
       ...prev,
       lastCost: obj.cost,
       lastBalance: obj.balance_after,
     }))
   }
   ```

3. **Handle smart_info event in frontend (BUG-3):**
   ```typescript
   if (obj.type === 'smart_info') {
     setSmartModel(obj.model)
     setSmartCategory(obj.category)
   }
   ```

### 6.2 Short-term Improvements

4. **Fix hardcoded estimate (BUG-4):** Use the actual cost from the billing event instead of `totalTokens * 0.000002`.

5. **Cancel upstream on disconnect:** Detect client disconnect in the event_stream generator and cancel the httpx stream:
   ```python
   async def event_stream():
       try:
           async with _http.stream(...) as r:
               async for line in r.aiter_lines():
                   try:
                       yield f"{line}\n\n"
                   except GeneratorExit:
                       # Client disconnected, cancel upstream
                       await r.aclose()
                       raise
   ```

6. **Add reconnection logic:** Use `EventSource` with `Last-Event-ID` header, or implement custom reconnection with the `fetch` API.

### 6.3 Long-term Enhancements

7. **Real-time token counter:** Use `tiktoken` or similar to count tokens as they arrive, show tokens/second.
8. **Server-Sent Events spec compliance:** Add `event:` and `id:` fields for better compatibility.
9. **Stream resumption:** Allow clients to resume interrupted streams.
10. **Rate limiting on streaming:** Prevent abuse of the mid-stream disconnect exploit.

---

## ۷. Appendix: Streaming Test Results

### Test 1: Basic streaming (curl)
```
$ curl -N -X POST http://127.0.0.1:8081/v1/chat/completions \
  -H 'Authorization: Bearer <token>' \
  -d '{"model":"tencent-hy3","messages":[{"role":"user","content":"count from 1 to 20"}],"stream":true}'

data: {"id":"chatcmpl-...","choices":[{"delta":{"content":"Here"}}]}
data: {"id":"chatcmpl-...","choices":[{"delta":{"content":" you"}}]}
data: {"id":"chatcmpl-...","choices":[{"delta":{"content":" go:\n\n1,"}}]}
...
data: {"id":"...","usage":{"completion_tokens":62,"prompt_tokens":14,"total_tokens":76}}
data: {"type":"billing","cost":11,"input_tokens":14,"output_tokens":62,"balance_after":99989,"currency":"IRT"}
```

✅ SSE works correctly  
✅ Tokens arrive in order  
✅ Usage data included  
✅ Billing event emitted at end  

### Test 2: Smart-chat streaming (curl)
```
$ curl -N -X POST http://127.0.0.1:8081/v1/smart-chat ...

data: {"type":"smart_info","model":"qwen3-coder-free","category":"simple"}
```

✅ smart_info event emitted  
⚠️ Model availability issue (qwen3-coder-free not available)  

### Test 3: Disconnect mid-stream
```
$ timeout 2 curl -N ... > /dev/null
# Ledger: NO billing entry created
```

❌ Confirmed: No billing on disconnect before usage chunk arrives  

---

## ۸. File Inventory

| File | Lines | Role |
|------|-------|------|
| `backend/chat.py` | 254-316 | `_chat_stream()` — main streaming function |
| `backend/chat.py` | 723-812 | `_smart_chat_stream()` — smart streaming function |
| `backend/chat.py` | 148-221 | `_record_usage()` — billing logic |
| `backend/chat.py` | 241-251 | `_bill_stream_usage()` — stream billing wrapper |
| `backend/chat.py` | 321-399 | `/v1/chat/completions` endpoint |
| `backend/chat.py` | 621-688 | `/v1/smart-chat` endpoint |
| `frontend/app/chat/page.tsx` | 470-474 | `cancel()` function |
| `frontend/app/chat/page.tsx` | 488-632 | `sendMessage()` — streaming loop |
| `frontend/app/chat/page.tsx` | 128-131 | Typing indicator (chat-typing) |
| `frontend/app/chat/page.tsx` | 830-835 | Stop button rendering |
| `frontend/app/chat/page.tsx` | 1050-1054 | Streaming status footer |
| `frontend/app/globals.css` | 1316-1335 | Typing animation CSS |
| `frontend/app/globals.css` | 1513-1527 | Streaming dot animation |

---

## ۹. Overall Verdict

The streaming architecture is **functional but incomplete**. The core SSE proxying works reliably, and the frontend renders tokens in real-time. However, the billing system has a critical gap that allows free token consumption via mid-stream disconnection, and the frontend ignores the backend's billing events entirely. These issues should be addressed before production deployment.

**Priority Order:**
1. Fix billing on disconnect (BUG-1) — **CRITICAL**
2. Handle billing events in frontend (BUG-2) — **MAJOR**
3. Handle smart_info events in frontend (BUG-3) — **MAJOR**
4. Cancel upstream on client disconnect — **MAJOR**
5. Add reconnection logic — **MEDIUM**
6. Fix hardcoded estimate (BUG-4) — **LOW**