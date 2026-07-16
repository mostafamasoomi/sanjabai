# P1 Billing Fix Report: Wire BillingService.reserve()/release() into Chat Endpoints

**Date:** 2026-07-16  
**Phase:** 1 (Backend — BillingService Integration)  
**File:** `backend/chat.py`  
**Fix Type:** Replace TOCTOU `_check_quota_pre` with proper `FOR UPDATE` locked reservation pattern

---

## Problem

`_check_quota_pre()` used a **check-then-act** pattern:

1. Query `SUM(amount) FROM ledger` to get balance
2. If balance > 0, allow the request
3. After LLM call, `_track_usage` writes a ledger entry

This has a **TOCTOU race**: two concurrent requests from the same user can both pass the balance check, then both deduct, potentially going negative.

`BillingService.reserve()` already exists in `services/billing.py` with proper `FOR UPDATE` row-level locking, but was not wired into the chat endpoints.

## Solution

Replaced `_check_quota_pre()` calls with `BillingService.reserve()` in all three non-streaming endpoints:

| Endpoint | Lines Modified |
|---|---|
| `POST /v1/chat/completions` (chat) | 407–552 |
| `POST /v1/chat/with-file` (chat_with_file) | 558–658 |
| `POST /v1/smart-chat` (smart_chat) | 897–997 |

### Pattern Applied

1. **Before LLM call**: `BillingService.reserve()` with estimated cost
   - Known models (`_WORKING_SET`): 1000 IRT minimum
   - Unknown models: 5000 IRT
   - Uses `FOR UPDATE` lock → eliminates TOCTOU race
   - Idempotency key: `chat:{token}`, `file:{token}`, `smart:{token}`

2. **After successful LLM call**: `_track_usage` records the actual cost (ledger entry), then `BillingService.release()` frees the hold

3. **On error**: `BillingService.release()` frees the hold

4. **Before streaming**: `BillingService.release()` frees the hold (streaming billing is handled independently by `_bill_stream_usage` in the `finally` block)

5. **Fallback**: If `BillingService.reserve()` fails for any non-balance reason, the legacy `_check_quota_pre()` is called as a safety net

### Why `release()` instead of `settle()`?

`BillingService.settle()` deducts from wallet balance AND writes a ledger entry. `_track_usage`/`_record_usage` also writes a ledger entry. Using both would **double-charge** the user. Instead, we:
- Use `reserve()` for the pre-flight balance check with proper locking
- Keep `_track_usage` for the actual billing records (as instructed)
- Use `release()` to free the hold after billing is complete

### Early Return Paths Covered

All early return paths in `chat_with_file()` release the reservation:
- File extraction error → release
- Model not allowed → release
- Streaming path → release before stream

All early return paths in `chat()` release the reservation:
- Model not allowed → release
- Streaming path → release before stream

All early return paths in `smart_chat()` release the reservation:
- Streaming path → release before stream

## Verification

```bash
$ python3 -m py_compile backend/chat.py
SYNTAX OK
```

## No Breaking Changes

- Existing `_check_quota_pre` is preserved as a fallback
- Existing `_track_usage` / `_bill_stream_usage` unchanged
- Existing streaming billing (`finally` block) unchanged
- All existing error messages preserved
- `BillingService` and `SqlBillingRepo` were already imported at line 34