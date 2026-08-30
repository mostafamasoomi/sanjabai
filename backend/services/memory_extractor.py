"""
Auto-Memory Extraction from conversations.

Uses LiteLLM to extract key facts about the user from conversations,
then saves them to user_memories with deduplication and sanitization.

Lightweight: runs as background task via asyncio.create_task, never blocks chat.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from services.context_injection import _sanitize_injection

logger = logging.getLogger(__name__)

MAX_MEM_CHAR = 500        # Truncate each extracted memory to 500 chars
MAX_MEM_EXTRACT = 3       # Max 3 memories extracted per conversation
MIN_MSG_COUNT = 3         # Only extract if conversation has >3 messages

# ── Runtime stats for /memories/auto-status ─────────────────────
_stats: dict[str, Any] = {
    "enabled": True,
    "last_extraction": None,       # datetime or None
    "total_extracted": 0,          # lifetime count of memories saved
    "last_error": None,            # str or None — last failure seen, if any
    "error_count": 0,              # lifetime count of failed extraction calls
}


def get_auto_status() -> dict[str, Any]:
    """Return current auto-extraction status for the status endpoint."""
    return {
        "enabled": _stats["enabled"],
        "last_extraction": _stats["last_extraction"].isoformat() if _stats["last_extraction"] else None,
        "total_extracted": _stats["total_extracted"],
        "last_error": _stats["last_error"],
        "error_count": _stats["error_count"],
    }


async def extract_memories(
    uid: int,
    conversation_messages: list[dict[str, Any]],
) -> int:
    """
    Extract 1-3 key facts about the user from a conversation using LiteLLM,
    then save them to user_memories with deduplication and sanitization.

    Returns the number of new memories saved (0-3).
    """
    if not uid or not conversation_messages:
        return 0

    # Only extract if enough messages
    if len(conversation_messages) <= MIN_MSG_COUNT:
        return 0

    # ── Build a compact representation of the conversation ──────
    lines: list[str] = []
    for msg in conversation_messages[-20:]:  # last 20 messages max
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Multimodal content — extract text parts only
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
            content = " ".join(parts)
        if not isinstance(content, str):
            continue
        # Truncate per message
        content = content[:500]
        lines.append(f"{role}: {content}")

    if not lines:
        return 0

    conversation_text = "\n".join(lines)

    # ── Call LiteLLM to extract facts ───────────────────────────
    facts: list[str] = []
    from database import _http, LITELLM_HOST

    prompt = (
        "Extract 1-3 key facts about the user from this conversation. "
        "Return as a JSON array of strings. Be concise. "
        "Only extract factual, persistent information (e.g. name, preferences, "
        "skills, interests, background, goals). "
        "Do NOT extract transient chat content or questions. "
        "If there is nothing worth remembering, return an empty array [].\n\n"
        f"Conversation:\n{conversation_text}"
    )

    # The primary model is fast but occasionally ReadTimeouts on a flaky
    # upstream; the fallback is slower but steadier. Extraction is a background
    # task, so a longer timeout + one fallback attempt costs the user nothing
    # and stops a transient blip from silently dropping a memory. A 200 with an
    # empty [] is a valid "nothing to remember" -- do not treat it as a failure.
    _models = [m for m in (
        os.getenv("MEMORY_EXTRACT_MODEL", "deepseek-v4-flash"),
        os.getenv("MEMORY_EXTRACT_FALLBACK", "stepfun-3.7-flash"),
    ) if m]
    _got_response = False
    _last_err: str | None = None
    for _model in _models:
        try:
            r = await _http.post(
                f"{LITELLM_HOST}/v1/chat/completions",
                json={
                    "model": _model,
                    "messages": [
                        {"role": "system", "content": "You are a memory extraction assistant. Return ONLY a JSON array of strings, nothing else."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 300,
                },
                headers={"Accept": "application/json"},
                timeout=45,
            )
        except Exception as e:
            _last_err = f"{type(e).__name__}: {str(e)[:150]}"
            logger.warning(f"extract_memories: LiteLLM call failed uid={uid} model={_model}: {_last_err}")
            continue
        if r.status_code != 200:
            _last_err = f"litellm {r.status_code} ({_model})"
            logger.warning(f"extract_memories: LiteLLM returned {r.status_code} for uid={uid} model={_model}")
            continue

        _got_response = True
        data = r.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Parse the JSON array
        content = content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[-1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                facts = [str(f).strip()[:MAX_MEM_CHAR] for f in parsed if f]
            elif isinstance(parsed, str):
                facts = [parsed.strip()[:MAX_MEM_CHAR]] if parsed.strip() else []
        except (json.JSONDecodeError, ValueError):
            # Try to extract array from text
            import re as _re
            arr_match = _re.search(r'\[.*?\]', content, _re.DOTALL)
            if arr_match:
                try:
                    parsed = json.loads(arr_match.group(0))
                    if isinstance(parsed, list):
                        facts = [str(f).strip()[:MAX_MEM_CHAR] for f in parsed if f]
                except (json.JSONDecodeError, ValueError):
                    pass
        break

    if not _got_response:
        _stats["last_error"] = _last_err or "extraction failed"
        _stats["error_count"] += 1
        return 0

    if not facts:
        return 0

    # Limit to max entries
    facts = facts[:MAX_MEM_EXTRACT]

    # ── Sanitize each fact ──────────────────────────────────────
    facts = [_sanitize_injection(f, MAX_MEM_CHAR) for f in facts]
    facts = [f for f in facts if f]  # Drop empty after sanitization

    if not facts:
        return 0

    # ── Deduplicate against existing memories & save ────────────
    saved_count = 0
    try:
        from database import async_session
        from models import UserMemory
        from dependencies import _escape_like

        if async_session is None:
            return 0

        async with async_session() as session:
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            for fact in facts:
                # Check if a similar memory already exists (ILIKE match)
                escaped = _escape_like(fact[:100])  # Use first 100 chars for match
                res = await session.execute(
                    UserMemory.__table__.select().where(
                        UserMemory.user_id == uid,
                        UserMemory.active == True,
                        UserMemory.content.ilike(f"%{escaped}%"),
                    ).limit(1)
                )
                existing = res.fetchone()
                if existing:
                    continue  # Duplicate — skip

                # Save new memory
                mem = UserMemory(
                    user_id=uid,
                    content=fact,
                    category="auto",
                    source="auto_extraction",
                    tags=[],
                    created_at=now,
                    updated_at=now,
                )
                session.add(mem)
                saved_count += 1

            if saved_count > 0:
                await session.commit()
                _stats["total_extracted"] += saved_count
                _stats["last_extraction"] = now
                logger.info(f"extract_memories: saved {saved_count} new memories for uid={uid}")

    except Exception as e:
        logger.warning(f"extract_memories: save failed uid={uid}: {e}")

    return saved_count