# Phase 1 Frontend Fix Report — Streaming UX

**Date:** 2026-07-16  
**Engineer:** Senior Frontend (Inspector Phase 1)  
**File:** `frontend/app/chat/page.tsx`

---

## Summary

Fixed 4 bugs in the streaming SSE loop and footer display:

1. **Hardcoded USD cost → Real IRT billing events**  
2. **Missing `billing` SSE event handler**  
3. **Missing `smart_info` SSE event handler**  
4. **No tokens/sec display in UI**

---

## Changes Made

### 1. Billing event handler (line ~598–606)

Added parsing of `type: "billing"` SSE events from the backend. The backend sends:

```json
{"type":"billing", "cost":..., "input_tokens":..., "output_tokens":..., "balance_after":..., "currency":"IRT"}
```

**Code added:**

```tsx
if (obj.type === 'billing') {
  setUsageStats(prev => ({
    promptTokens: obj.input_tokens ?? prev.promptTokens,
    completionTokens: obj.output_tokens ?? prev.completionTokens,
    totalTokens: (obj.input_tokens ?? 0) + (obj.output_tokens ?? 0),
    estimatedCost: obj.cost ?? prev.estimatedCost
  }))
}
```

### 2. Smart info event handler (line ~607–610)

Added parsing of `type: "smart_info"` SSE events:

```tsx
if (obj.type === 'smart_info') {
  setSmartModel(obj.model)
}
```

### 3. Removed hardcoded cost estimate (line ~628–638)

**Before:** `const estimatedCost = totalTokens * 0.000002` (fake USD estimate)  
**After:** Token counts still updated from `usageData`, but `estimatedCost` comes exclusively from billing events. The usage fallback preserves the previous cost value.

### 4. Tokens/sec tracking (lines ~513–514, ~611–618)

- Set `streamStartTimeRef.current = Date.now()` when streaming starts
- Reset `tokensPerSec` to 0 on new stream
- Calculate tokens/sec in SSE loop: `elapsed = (Date.now() - startTime) / 1000`, `tps = Math.round(totalTokens / elapsed)`
- Update `tokensPerSec` state on each chunk

### 5. Footer display update (line ~1083–1086)

**Before:** `~${usageStats.estimatedCost.toFixed(4)}` (USD, 4 decimals)  
**After:** `~{usageStats.estimatedCost.toLocaleString('fa-IR')} تومان` (Persian-formatted IRT)

Added tokens/sec display when streaming:

```tsx
{streaming && tokensPerSec > 0 && (
  <span className="usage-tps" dir="ltr">{tokensPerSec} tok/s</span>
)}
```

---

## State Used

All state variables already existed in the component:

| Variable | Type | Line | Role |
|---|---|---|---|
| `usageStats` | `useState<UsageStats>` | 215 | Holds prompt/completion/total tokens + estimatedCost |
| `tokensPerSec` | `useState<number>` | 216 | Tokens/second display (was unused) |
| `streamStartTimeRef` | `useRef<number>` | 217 | Stream start timestamp (was unused) |
| `smartModel` | `useState<string \| null>` | 213 | Smart model display (was only set from `x_smart_model`) |

---

## Verification

- `npm run build` — chat page compiles successfully (`✓ Compiled successfully in 15.7s`)
- Pre-existing type error in `AdminCharts.tsx:277` (unrelated) blocks full build
- SSE parsing loop structure preserved — `AbortController` logic untouched
- `continue` not used in billing/smart_info handlers (both `if` blocks are leaf branches, no fallthrough risk)

---

## Risks / Edge Cases

- **Billing event arrives before usageData**: The billing handler sets tokens directly from `input_tokens`/`output_tokens` fields, so it's independent of the final `usageData` block.
- **Billing event never arrives**: Cost stays at 0 IRT (previous behavior was a fake USD number). The token counts still update from `usageData` at stream end.
- **Tokens/sec during streaming**: Uses `usageData` from the stream (may update mid-stream), avoids flickering by only showing when `tps > 0`.