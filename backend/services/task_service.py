"""Callable service core for creating a scheduled task.

`tasks.py`'s `POST /tasks` handler used to build the `ScheduledTask` row and
insert it directly, reading `uid` off the incoming `Request` the whole way
through. A later packet needs to create a task on a user's behalf from an
LLM tool-calling loop, which has no `Request` to read -- forging one would
be a classic identity-confusion bug, worse here than usual because this
project runs two parallel auth mechanisms (session cookie + hashed API
key). This module is the fix: the write core takes an explicit `uid`
parameter and never touches a `Request`, a session, or any other ambient
auth state. `tasks.create_task()` is now auth + parse + delegate, the same
shape `task_execution.py`'s `_execute_task()` established for `run_task()`.

This is a pure refactor -- `create_task()` here is the ONE place a
`ScheduledTask` row is ever inserted (see `tasks.py` for the read/update/
delete/run routes, none of which insert). Preserved byte-for-byte from the
handler this replaces:
  - the cron validation via `compute_next_run()` and its exact Persian/
    English error message
  - the response body shape and field set
  - the model sentinel `''` ("resolve at run time", never here) -- see
    `tasks.py`'s `_DEFAULT_MODEL_SENTINEL` docstring. This module does NOT
    call `_resolve_task_model`; that still happens exactly once, at run
    time, in `task_execution._execute_task`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from database import async_session
from models import ScheduledTask
from services.task_scheduler import compute_next_run


class TaskValidationError(Exception):
    """Invalid task-creation input (currently: a bad cron expression).

    Carries both localized messages so callers build whatever response
    shape they need (`err()` for the HTTP route today, an
    `{"ok": false, "error": ...}` tool result for the loop later) without
    this module importing FastAPI -- a service core has no business
    knowing about HTTP.
    """

    def __init__(self, message_fa: str, message_en: str):
        self.message_fa = message_fa
        self.message_en = message_en
        super().__init__(message_en)


@dataclass
class TaskSpec:
    """Mirrors `tasks.ScheduledTaskCreate` field-for-field."""

    title: str
    prompt: str
    description: str = ''
    model: str = ''
    cron_expression: str = '0 9 * * *'
    delivery_channel: str = 'dashboard'


async def create_task(uid: int, spec: TaskSpec, *, activate: bool = True) -> dict:
    """Insert a `ScheduledTask` row owned by `uid`.

    `uid` is an explicit parameter, never read from a `Request`/session --
    that is the entire point of this extraction (see module docstring).
    Raises `TaskValidationError` on an invalid cron expression, matching
    what the handler used to return inline as a 400.

    ``activate=False`` inserts the row already dormant: `is_active=False`
    and `next_run_at=NULL`, set BEFORE the insert rather than corrected
    after it.

    Why before, and why this parameter exists at all: a task created by the
    LLM tool-calling loop must never be live, because a live task is
    `services/task_scheduler.py` spending the user's money later with no
    human on the trigger -- which is why `app.py` keeps TASK_SCHEDULER_ENABLED
    off. The tool layer originally got this by issuing a corrective UPDATE
    straight after the insert, which leaves a window, however short, in which
    a model-authored task is armed and schedulable. A window with money on
    the other side of it is not a window worth keeping, and it stops being
    theoretical the day that flag flips. So the caller declares its intent
    and one transaction writes the truth.

    The cron expression is still validated when ``activate=False`` -- the
    caller gets the same loud error for a bad expression -- it is simply not
    stored. Validation and arming are separate concerns.
    """
    async with async_session() as session:
        task = ScheduledTask(
            user_id=uid, title=spec.title, description=spec.description,
            prompt=spec.prompt, model=spec.model,
            cron_expression=spec.cron_expression, delivery_channel=spec.delivery_channel,
        )
        # So next_run_at stops being decorative -- see
        # services/task_scheduler.py's module docstring. A task created
        # with an invalid cron expression fails loudly here rather than
        # silently sitting with next_run_at=NULL forever, never picked up
        # by the scheduler.
        try:
            next_run = compute_next_run(spec.cron_expression, datetime.now(timezone.utc))
        except ValueError as e:
            raise TaskValidationError(
                f'عبارت زمان‌بندی نامعتبر است: {e}', f'Invalid schedule expression: {e}',
            ) from e
        if activate:
            task.next_run_at = next_run
        else:
            task.is_active = False
            task.next_run_at = None
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return {
            'id': task.id, 'title': task.title, 'description': task.description,
            'prompt': task.prompt, 'model': task.model, 'cron_expression': task.cron_expression,
            'is_active': task.is_active, 'run_count': task.run_count,
            'delivery_channel': task.delivery_channel,
            'next_run_at': task.next_run_at.isoformat() if task.next_run_at else None,
            'created_at': task.created_at.isoformat() if task.created_at else None,
        }
