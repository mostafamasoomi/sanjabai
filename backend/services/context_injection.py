"""
Context injection helper — centralizes memory & soul injection for chat.

Fixes S4: duplicated 5x memory injection with no limits, no sanitization.
Limits: MAX_SOUL_CHARS=2000, MAX_MEMORY_ENTRY=500, MAX_MEMORIES_INJECTED=5
Sanitization: breaks "[User" -> "[ User" to prevent prompt injection via memories.
Dedup guard: checks if "[User Memories]" already in messages to avoid double inject.

Phase E3: the whole block is gated to one turn in N (see the ``messages``
argument of get_injection_messages and services/token_budget.py).
"""
from __future__ import annotations

import logging
from typing import Any

from services.token_budget import should_inject_context

logger = logging.getLogger(__name__)

MAX_SOUL_CHARS = 2000
MAX_MEMORY_ENTRY = 500
MAX_MEMORIES_INJECTED = 5
# The pinned context is a single user-authored note or pasted .md file
# (profile 'پرونده دائمی' / persistent document), not one of the 5
# auto-selected memory facts, so it gets its own, larger budget.
MAX_PINNED_CONTEXT_CHARS = 6000

def _sanitize_injection(s: str, limit: int) -> str:
    """Strip, truncate, and break injection patterns."""
    if not s:
        return ""
    s = s.strip()[:limit]
    # Break patterns that could be used to inject roles or system tags
    s = s.replace("[User", "[ User")
    s = s.replace("[System", "[ System")
    s = s.replace("<|", "< |")
    s = s.replace("[Assistant", "[ Assistant")
    s = s.replace("###", "# # #")
    return s


async def get_injection_messages(
    uid: int,
    skill_ids: list[int] | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """
    Fetch memories (limit 5) + soul (truncated) + pinned context + the
    user's activated skills -> list of system messages.
    Returns list of dicts to be injected via inject_messages().

    ``skill_ids`` is optional and defaults to None so all existing call
    sites (chat.py, chat_smart.py, chat_web.py, chat_stream.py x2,
    chat_compare.py) keep working untouched, picking up the user's
    activated skills automatically.

    ``messages`` is the outbound payload; when given, a block at or over
    INJECT_ALWAYS_UNDER_CHARS is gated to one turn in
    INJECT_CONTEXT_EVERY_N_TURNS (Phase E3, see
    services/token_budget.py::should_inject_context). A smaller block, and
    omitting ``messages`` entirely, injects unconditionally as before.
    """
    injections: list[dict[str, str]] = []
    if not uid:
        return injections

    # --- Memories ---
    try:
        from dependencies import _get_user_memories as dep_mem
        raw_mems = await dep_mem(uid)
    except Exception as e:
        logger.warning(f"get_injection_messages: _get_user_memories failed uid={uid}: {e}")
        raw_mems = []

    if raw_mems:
        seen = set()
        cleaned = []
        for m in raw_mems:
            if not m or not isinstance(m, str):
                continue
            s = _sanitize_injection(m, MAX_MEMORY_ENTRY)
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            cleaned.append(s)
            if len(cleaned) >= MAX_MEMORIES_INJECTED:
                break
        if cleaned:
            block = "\n".join(f"- {x}" for x in cleaned)
            injections.append(
                {"role": "system", "content": f"[User Memories]\n{block}"}
            )

    # --- Soul / ai_personality ---
    try:
        from dependencies import _get_user_soul as dep_soul
        raw_soul = await dep_soul(uid)
    except Exception as e:
        logger.warning(f"get_injection_messages: _get_user_soul failed uid={uid}: {e}")
        raw_soul = ""

    if raw_soul:
        soul_clean = _sanitize_injection(raw_soul, MAX_SOUL_CHARS)
        if soul_clean:
            injections.append(
                {
                    "role": "system",
                    "content": f"[User Soul — این شخصیت و لحن مورد انتظار کاربر است. طبق این رفتار کن:]\n{soul_clean}",
                }
            )

    # --- Pinned context (persistent note / uploaded .md, profile-level) ---
    try:
        from dependencies import _get_user_pinned_context as dep_pinned
        raw_pinned = await dep_pinned(uid)
    except Exception as e:
        logger.warning(f"get_injection_messages: _get_user_pinned_context failed uid={uid}: {e}")
        raw_pinned = ""

    if raw_pinned:
        pinned_clean = _sanitize_injection(raw_pinned, MAX_PINNED_CONTEXT_CHARS)
        if pinned_clean:
            injections.append(
                {
                    "role": "system",
                    "content": f"[User Pinned Context — یادداشت دائمی کاربر که در تمام چت‌ها باید در نظر گرفته شود:]\n{pinned_clean}",
                }
            )

    # --- Activated skills (user-activated only, see services/skill_injection.py) ---
    try:
        from services.skill_injection import get_active_skill_messages
        skill_msgs = await get_active_skill_messages(uid, skill_ids)
    except Exception as e:
        logger.warning(f"get_injection_messages: get_active_skill_messages failed uid={uid}: {e}")
        skill_msgs = []
    if skill_msgs:
        injections.extend(skill_msgs)

    # E3 gate -- runs on the BUILT block because the decision is size-aware
    # (services/token_budget.py::should_inject_context) and only the built
    # block knows its size. The four reads above cost ~7ms against an
    # upstream that takes up to 11s, and they already ran on every request
    # before Phase E, so deciding after them adds no load; a proxy would
    # need the same reads and be less accurate. `messages` is optional so a
    # caller that does not pass the outbound payload stays ungated.
    if messages is not None and not should_inject_context(
        messages, sum(len(i.get('content') or '') for i in injections)
    ):
        return []

    return injections


def inject_messages(
    payload_messages: list[dict[str, Any]], injections: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """
    Insert injection messages after last system message, with dedup guard.
    If "[User Memories]" already present in payload_messages, skip memory injection.
    If "[User Soul" already present, skip soul injection.
    """
    if not injections:
        return payload_messages
    msgs = payload_messages or []
    # Build presence map
    has_mem = any(
        isinstance(m, dict) and "[User Memories]" in (m.get("content") or "")
        for m in msgs
    )
    has_soul = any(
        isinstance(m, dict) and "[User Soul" in (m.get("content") or "")
        for m in msgs
    )
    has_pinned = any(
        isinstance(m, dict) and "[User Pinned Context" in (m.get("content") or "")
        for m in msgs
    )
    has_skills = any(
        isinstance(m, dict) and "[User Skills" in (m.get("content") or "")
        for m in msgs
    )

    to_inject: list[dict[str, str]] = []
    for inj in injections:
        c = inj.get("content", "")
        if "[User Memories]" in c and has_mem:
            continue
        if "[User Soul" in c and has_soul:
            continue
        if "[User Pinned Context" in c and has_pinned:
            continue
        if "[User Skills" in c and has_skills:
            continue
        to_inject.append(inj)

    if not to_inject:
        return msgs

    # Insert after last system message
    insert_idx = 0
    for i, m in enumerate(msgs):
        if isinstance(m, dict) and m.get("role") == "system":
            insert_idx = i + 1
    # Insert in order
    for offset, inj in enumerate(to_inject):
        msgs.insert(insert_idx + offset, inj)
    return msgs
