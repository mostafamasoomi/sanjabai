"""
Skill injection — turns a user's *activated* skills into system messages
appended by ``services/context_injection.py``.

Why this exists. Until migrations/0040_user_skill_activations.sql and
models.UserSkillActivation, a "skill" was a template library only:
``POST /skills/{id}/use`` rendered ``prompt_template`` and handed the
string back to the frontend -- nothing in any chat module ever read it,
so a skill never reached the model. The owner's instruction ("even if
the user added a memory or a skill from the panel, it must be applied
to the request, exactly like the Hermes and Claude structure") plus
"we must not induce extra tokens of our own on the user's request"
together fix the design: user-activated skills only, no auto-discovery,
no model-chosen invocation. A user with zero activations gets a
byte-for-byte unchanged request.

Contract: this module never raises. Every DB access is wrapped in
try/except and logs a warning + returns ``[]`` on failure -- a broken
skill must never break a chat (same house rule as context_injection.py).
"""
from __future__ import annotations

import logging

from database import async_session
from models import SkillTemplate, UserSkillActivation
from services.context_injection import _sanitize_injection

logger = logging.getLogger(__name__)

MAX_SKILLS_INJECTED = 3
MAX_SKILL_CHARS = 4000
# Hard ceiling across all injected skill bodies combined, regardless of how
# many individual skills are under MAX_SKILLS_INJECTED -- a user could
# activate 3 skills each near MAX_SKILL_CHARS and blow the token budget.
MAX_SKILLS_TOTAL_CHARS = 8000

_HEADER = "[User Skills — این مهارت‌ها را کاربر خودش فعال کرده است. طبق آن‌ها عمل کن:]"


def _allowed(row, uid: int) -> bool:
    """A user may only ever see their own skills or public ones.

    Applied in Python (not only in SQL) so this check holds even if a
    query is later simplified/changed -- never leak another user's
    private skill template body into a chat.
    """
    return bool(row is not None and (row.user_id == uid or row.is_public))


async def _load_active_templates(uid: int) -> list:
    """Templates the user activated (enabled=True), ordered by
    position/id, capped at MAX_SKILLS_INJECTED at the SQL level."""
    async with async_session() as session:
        stmt = (
            SkillTemplate.__table__.select()
            .select_from(
                SkillTemplate.__table__.join(
                    UserSkillActivation.__table__,
                    UserSkillActivation.template_id == SkillTemplate.id,
                )
            )
            .where(
                UserSkillActivation.user_id == uid,
                UserSkillActivation.enabled == True,  # noqa: E712
            )
            .order_by(UserSkillActivation.position, SkillTemplate.id)
            .limit(MAX_SKILLS_INJECTED)
        )
        res = await session.execute(stmt)
        rows = res.fetchall()
    return [r for r in rows if _allowed(r, uid)]


async def _load_explicit_templates(uid: int, skill_ids: list[int]) -> list:
    """Exactly the requested templates, filtered to ones the user may
    use (own or public), in the order the caller specified them."""
    async with async_session() as session:
        stmt = SkillTemplate.__table__.select().where(SkillTemplate.id.in_(skill_ids))
        res = await session.execute(stmt)
        rows = res.fetchall()
    by_id = {r.id: r for r in rows}
    ordered = [by_id[i] for i in skill_ids if i in by_id]
    return [r for r in ordered if _allowed(r, uid)]


def _render_skill_block(rows) -> list[dict[str, str]]:
    """Sanitize + budget the selected rows into a single system message."""
    if not rows:
        return []
    parts: list[str] = []
    total = 0
    for row in rows:
        if len(parts) >= MAX_SKILLS_INJECTED:
            break
        title = (getattr(row, "title_fa", None) or getattr(row, "title", None) or "").strip()
        body = _sanitize_injection(getattr(row, "prompt_template", "") or "", MAX_SKILL_CHARS)
        if not body:
            continue
        section = f"## {title}\n{body}"
        # +2 accounts for the blank-line separator before this section
        # (none for the first one).
        added = len(section) + (2 if parts else 0)
        if total + added > MAX_SKILLS_TOTAL_CHARS:
            break
        parts.append(section)
        total += added

    if not parts:
        return []
    content = _HEADER + "\n" + "\n\n".join(parts)
    return [{"role": "system", "content": content}]


async def get_active_skill_messages(
    uid: int, skill_ids: list[int] | None = None
) -> list[dict[str, str]]:
    """Fetch the user's activated (or explicitly selected) skills as a
    list containing zero or one system message.

    ``uid`` falsy -> [] immediately, no DB hit. Never raises.
    """
    if not uid:
        return []
    try:
        if async_session is None:
            return []
        if skill_ids:
            rows = await _load_explicit_templates(uid, skill_ids)
        else:
            rows = await _load_active_templates(uid)
    except Exception as e:
        logger.warning(f"get_active_skill_messages: DB load failed uid={uid}: {e}")
        return []

    try:
        return _render_skill_block(rows)
    except Exception as e:
        logger.warning(f"get_active_skill_messages: render failed uid={uid}: {e}")
        return []
