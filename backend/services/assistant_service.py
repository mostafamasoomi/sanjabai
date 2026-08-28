"""Callable service core for creating an assistant.

Same extraction as `services/task_service.py` -- see that module's
docstring for the full rationale (a later LLM tool-calling loop needs to
create rows on a user's behalf without forging a `Request`, and this
project's two parallel auth mechanisms make that especially unsafe here).
`assistants.create_assistant()` is now auth + parse + delegate; this
module is the ONE place an `Assistant` row is ever inserted.

Preserved byte-for-byte from the handler this replaces: the response body
shape (`{'status': 'ok', 'id': ...}`), the database-unavailable guard, and
the field set written. `uid` is an explicit parameter, never read from a
`Request`/session.
"""
from __future__ import annotations

from dataclasses import dataclass

from database import async_session
from models import Assistant


@dataclass
class AssistantSpec:
    """Mirrors `assistants.AssistantCreate` field-for-field."""

    name: str = 'New Assistant'
    description: str = ''
    system_prompt: str = ''
    model_id: str = ''
    icon: str = 'chat'
    is_public: bool = False


async def create_assistant(uid: int, spec: AssistantSpec) -> dict | None:
    """Insert an `Assistant` row owned by `uid`.

    Returns `None` if the database is unavailable (`async_session is
    None`), matching the handler's pre-existing 500 guard -- the caller is
    responsible for turning that into whatever response shape it needs.
    """
    if async_session is None:
        return None
    async with async_session() as session:
        obj = Assistant(
            user_id=uid, name=spec.name, description=spec.description,
            system_prompt=spec.system_prompt, model_id=spec.model_id,
            icon=spec.icon, is_public=spec.is_public,
        )
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
    return {'status': 'ok', 'id': obj.id}
