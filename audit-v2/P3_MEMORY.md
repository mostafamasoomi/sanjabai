# P3: Auto-Memory Extraction — Phase 3 Memory

**Date:** 2026-07-16  
**Engineer:** Senior AI Engineer  
**Status:** ✅ Complete

---

## Overview

Phase 3 adds automatic memory extraction from conversations. After each chat response completes, a background task uses LiteLLM to extract key facts about the user, deduplicates them against existing memories, and stores them in `user_memories`. This replaces the need for manual memory creation.

## Delivery

### 1. `backend/services/memory_extractor.py` (NEW)

Core auto-extraction module with:

- **`extract_memories(uid, conversation_messages)`** — Main extraction function
  - Builds a compact representation of the last 20 messages (truncated to 500 chars each)
  - Calls LiteLLM (`tencent-hy3`) with a structured prompt to extract 1-3 key facts
  - Parses JSON array response with fallback regex extraction
  - Sanitizes each fact using `_sanitize_injection()` from `context_injection.py`
  - Deduplicates via ILIKE check against existing memories before saving
  - Saves to `user_memories` with `category='auto'`, `source='auto_extraction'`
  - Returns count of saved memories (0-3)

- **`get_auto_status()`** — Returns current stats for the status endpoint

- **Runtime stats** (`_stats` dict):
  - `enabled: True` (always on; future toggle point)
  - `last_extraction: datetime | None` — last successful extraction timestamp
  - `total_extracted: int` — lifetime count of memories saved

- **Caps enforced:**
  - `MAX_MEM_CHAR = 500` — each memory truncated to 500 chars
  - `MAX_MEM_EXTRACT = 3` — max 3 memories per extraction
  - `MIN_MSG_COUNT = 3` — only extract if conversation has >3 messages

### 2. Integration into `chat.py` (MODIFIED)

Added `_fire_memory_extraction(uid, messages)` helper that schedules background extraction via `asyncio.create_task`. Integrated at 5 points:

| Endpoint | Integration Point | Type |
|---|---|---|
| `POST /v1/chat/completions` | After successful non-streaming response | `_fire_memory_extraction()` |
| `POST /v1/chat/with-file` | After successful non-streaming response | `_fire_memory_extraction()` |
| `POST /v1/smart-chat` | After successful non-streaming response | `_fire_memory_extraction()` |
| `_chat_stream` (internal) | In finally block after billing | `_fire_memory_extraction()` |
| `_smart_chat_stream` (internal) | In finally block after billing | `_fire_memory_extraction()` |

All calls are fire-and-forget — they never block the chat response. Messages are snapshotted (last 40) to avoid mutation issues.

### 3. `GET /memories/auto-status` endpoint (ADDED to `memory.py`)

Returns:
```json
{
  "enabled": true,
  "last_extraction": "2026-07-16T12:00:00" or null,
  "total_extracted": 42
}
```

## Design Decisions

- **Lightweight:** Uses `asyncio.create_task` for background execution — zero impact on response latency
- **Cheapest model:** Uses `tencent-hy3` for extraction to minimize cost
- **Deduplication:** ILIKE check prevents duplicate memories from being stored
- **Sanitization:** Reuses `_sanitize_injection()` to prevent prompt injection via extracted memories
- **No DB schema changes:** Reuses existing `user_memories` table with `category='auto'` and `source='auto_extraction'`
- **Message snapshot:** Takes a copy of messages before firing the bg task to avoid mutation races

## Verification

```bash
$ python3 -m py_compile backend/services/memory_extractor.py && echo PASS
PASS

$ python3 -m py_compile backend/chat.py && echo PASS
PASS

$ python3 -m py_compile backend/memory.py && echo PASS
PASS
```

All three files compile cleanly with no syntax errors.

## Files Changed

| File | Action | Description |
|---|---|---|
| `backend/services/memory_extractor.py` | **NEW** | Core auto-extraction module |
| `backend/chat.py` | MODIFIED | Import + `_fire_memory_extraction` helper + 5 integration points |
| `backend/memory.py` | MODIFIED | Added `GET /memories/auto-status` endpoint |

## Lines of Code

- `memory_extractor.py`: ~170 lines
- `chat.py` changes: +12 lines (helper) + 12 lines (5 integration spots)
- `memory.py` changes: +7 lines