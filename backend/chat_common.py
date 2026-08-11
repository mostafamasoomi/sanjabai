"""
Shared chat helpers: request models, the file-size cap, and the background
health-sample / auto-memory tasks fired by both the chat routes and the
streaming helpers.

Pulled out of chat.py (which was well past the project's 500-line ceiling)
so the request schemas and fire-and-forget helpers are importable without
dragging in the endpoint modules. This module has no dependency on the chat
aggregator, so the route/stream modules can import it at module load time.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from services.memory_extractor import extract_memories, MIN_MSG_COUNT

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    model: str = ''
    messages: list = []
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    web_search: bool = False
    assistant_id: int | None = None


class CompareRequest(BaseModel):
    model_a: str
    model_b: str
    messages: list = []
    stream: bool = False


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB hard cap


def _record_model_health(
    model_id: str, *, ok: bool, latency_ms: int | None = None, error: str | None = None
) -> None:
    """Record a passive health sample for a real request, off the response path.

    Fire-and-forget on purpose: the user's completion has already succeeded or
    failed by this point, and a health-table write must never add latency to it
    or turn a good response into an error. Imported lazily so chat.py does not
    depend on model_health at import time.
    """
    if not model_id:
        return
    try:
        from model_health import record_traffic

        task = asyncio.create_task(
            record_traffic(model_id, ok, latency_ms=latency_ms, error=error)
        )
        # Hold a reference so the task is not garbage-collected mid-flight.
        _HEALTH_TASKS.add(task)
        task.add_done_callback(_HEALTH_TASKS.discard)
    except Exception:
        pass


_HEALTH_TASKS: set[asyncio.Task] = set()


def _fire_memory_extraction(uid: int, messages: list[dict[str, Any]]) -> None:
    """Schedule background auto-memory extraction if conversation has enough messages."""
    if uid and messages and len(messages) > MIN_MSG_COUNT:
        # Capture a copy of messages to avoid mutation issues
        msgs_snapshot = [dict(m) for m in messages[-40:]]  # Keep last 40 max
        asyncio.create_task(extract_memories(uid, msgs_snapshot))
