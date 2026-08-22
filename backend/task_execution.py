"""Billed execution core for scheduled tasks.

`tasks.py`'s POST /tasks/{id}/run endpoint and `services/task_scheduler.py`'s
background loop both call :func:`_execute_task` -- the ONE place a scheduled
task's prompt is ever sent upstream. Before this module existed, `run_task`
in tasks.py posted straight to LiteLLM with no reservation, no settle, and
no usage record: a straight revenue-loss path (a user could run scheduled
tasks for free forever, and once the scheduler ships, entirely without a
human clicking anything). This module closes that hole by wrapping the
upstream call in the same reserve -> call -> settle -> release bracket every
other billed entry point in this codebase uses (modeled on backend/images.py
lines 136-291 and backend/chat.py's non-streaming POST /v1/chat/completions
handler, ~lines 1479-1608).

Order is NON-NEGOTIABLE (see the FINANCIAL RULE in chat._resolve_public_model's
and images.py's module docstrings for the incident writeups this mirrors):

  1. Resolve the model EXACTLY ONCE, first (tasks._resolve_task_model) --
     an unresolved/unconverted model id makes _record_usage's price lookup
     MISS, and a fallback CEILING rate applies, overcharging the user.
  2. The free-tier gate (services.free_tier.check_and_consume) -- the same
     one chat.py's handler runs, so a scheduled task can't be used to bypass
     the 5-message free-tier throttle. Must run before any reservation is
     opened: a pre-reserve rejection means there is never a reservation to
     unwind.
  3. BillingService.reserve() -- pre-flight availability check + hold.
  4. The upstream call.
  5. Settle via chat._bill_stream_usage(uid, payload, usage, response_text=...)
     -- it opens its own session and already handles a missing/partial usage
     block with the L1 local estimate, which is exactly this path's
     situation (scheduled tasks always call with stream=False, but the
     upstream is not guaranteed to return a `usage` block any more here than
     anywhere else). Like chat.py's own non-streaming handler, this charges
     wallet.balance DIRECTLY -- the pre-flight reservation from step 3 is
     never itself "settled", only released (see step 6).
  6. Release the reservation. ALWAYS -- upstream exception, non-200, empty
     content, or a settle that raises all release the hold (see `_release`).

LATE BINDING IS MANDATORY. `chat.py` is being restructured by another agent
concurrently while this module is being written, and the test suite
monkeypatches names ON THE CHAT MODULE (and on the `tasks` module, for
`_resolve_task_model`). Neither module is ever imported at module scope
here -- always `import chat` / `import tasks` inside the function that needs
them, then call `chat.<name>(...)` / `tasks.<name>(...)` at call time. A
module-level `from chat import X` would both break if chat.py's module
layout changes under the split, and silently defeat monkeypatching (a patch
would land on a name this module never re-reads).

Money is an integer number of Toman throughout -- see services/money.py.
Never multiply or divide by 10 anywhere in this file.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from database import _http, async_session
from models import ScheduledTask, TaskExecution
from services.billing import BillingService, InsufficientBalanceError, SqlBillingRepo
from services.free_tier import check_and_consume
from services.money import Money

logger = logging.getLogger(__name__)

# Same shape as chat.py's non-streaming reserve estimate (chat.py's chat()
# handler, ~line 1495): a cheap pre-flight hold, not a prediction of the
# real cost -- the real charge is whatever chat._bill_stream_usage/
# _record_usage computes from actual (or L1-estimated) tokens after the
# fact. A catalog-verified "working" model gets the tighter estimate;
# anything else gets the wider one, same reasoning as chat.py's.
_RESERVE_ESTIMATE_WORKING = 1000
_RESERVE_ESTIMATE_UNKNOWN = 5000

_INSUFFICIENT_BALANCE_MESSAGE = 'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.'
_FREE_TIER_MESSAGE = (
    'سقف پیام رایگان این مدل برای اکنون پر شده است؛ کمی بعد دوباره تلاش کنید '
    'یا با شارژ حساب این محدودیت را برای همیشه بردارید.'
)
_NO_MODEL_MESSAGE = 'در حال حاضر مدلی برای اجرای این وظیفه در دسترس نیست'
_EMPTY_RESPONSE_MESSAGE = 'پاسخ خالی از سرویس دریافت شد'
_GATEWAY_ERROR_MESSAGE = 'سرویس موقتاً در دسترس نیست'


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _release(reservation: dict | None, uid: int, label: str = '') -> None:
    """Release a billing reservation; fire-and-forget, logs on failure.

    Deliberately a local, self-contained ~10 lines (mirroring
    chat._release_reservation) rather than a late-bound call into chat.py:
    this file's only intentional dependencies on chat.py are the symbols the
    coordinator named (is_working_model, _resolve_provider,
    _bill_stream_usage) -- keeping the release path self-contained means a
    rename inside chat.py's ongoing restructuring can't silently break
    reservation cleanup here.
    """
    if not reservation or async_session is None:
        return
    try:
        async with async_session() as s:
            repo = SqlBillingRepo(s)
            svc = BillingService(repo)
            await svc.release(reservation['reservation_id'])
            await s.commit()
    except Exception as e:
        logger.warning(f"task_execution._release failed uid={uid} {label}: {e}")


async def _finalize(
    execution_id: int | None,
    task_id: int,
    status: str,
    result_text: str | None,
    error_text: str | None,
    tokens_used: int,
    cost_toman: int,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Write the final TaskExecution + ScheduledTask rows. Always runs,
    success or failure, mirroring the original run_task's unconditional
    bookkeeping: every attempt counts toward run_count and updates
    last_run_at/last_result, whether or not it was billable."""
    completed_at = _utcnow()
    if async_session is not None:
        try:
            async with async_session() as session:
                if execution_id is not None:
                    res = await session.execute(
                        select(TaskExecution).where(TaskExecution.id == execution_id)
                    )
                    exec_row = res.scalar_one_or_none()
                    if exec_row is not None:
                        exec_row.status = status
                        exec_row.result = result_text
                        exec_row.error = error_text
                        exec_row.tokens_used = tokens_used
                        exec_row.cost_toman = cost_toman
                        exec_row.completed_at = completed_at
                await session.commit()

                res2 = await session.execute(
                    select(ScheduledTask).where(ScheduledTask.id == task_id)
                )
                task_row = res2.scalar_one_or_none()
                if task_row is not None:
                    task_row.last_run_at = completed_at
                    task_row.run_count = (task_row.run_count or 0) + 1
                    task_row.last_result = result_text
                    task_row.updated_at = completed_at
                await session.commit()
        except Exception as e:
            logger.warning(
                f"task_execution._finalize failed task_id={task_id} "
                f"execution_id={execution_id}: {e}"
            )

    return {
        'execution_id': execution_id,
        'status': status,
        'result': result_text,
        'error': error_text,
        'error_code': error_code,
        'tokens_used': tokens_used,
        'cost_toman': cost_toman,
    }


async def _execute_task(task: Any, uid: int) -> dict[str, Any]:
    """Execute one scheduled task's prompt, billed. See module docstring for
    the mandatory reserve -> call -> settle -> release order.

    Called from two places: tasks.py's POST /tasks/{id}/run (a ScheduledTask
    ORM row the router already fetched for this uid) and
    services/task_scheduler.py's background loop (a plain Row claimed off
    the due-tasks queue). Either way `task` only needs `.id`, `.model`, and
    `.prompt` -- `uid` is passed separately (the scheduler claims tasks for
    potentially many different users per tick, so it is never assumed to
    equal `task.user_id` implicitly here).
    """
    execution_id: int | None = None
    if async_session is not None:
        try:
            async with async_session() as session:
                execution = TaskExecution(
                    task_id=task.id, user_id=uid, status='running', started_at=_utcnow(),
                )
                session.add(execution)
                await session.commit()
                await session.refresh(execution)
                execution_id = execution.id
        except Exception as e:
            logger.warning(f"task_execution: failed to create TaskExecution row task_id={task.id}: {e}")

    # 1. Resolve the model exactly once, first.
    import tasks as tasks_mod
    model_to_call = await tasks_mod._resolve_task_model(task.model)
    if not model_to_call:
        return await _finalize(execution_id, task.id, 'failed', None, _NO_MODEL_MESSAGE, 0, 0)

    chat_payload: dict[str, Any] = {
        'model': model_to_call,
        'messages': [{'role': 'user', 'content': task.prompt}],
        'stream': False,
    }

    # 2. Free-tier gate -- before any reservation is opened.
    ft_gate = await check_and_consume(uid, [model_to_call])
    if ft_gate is not None:
        return await _finalize(execution_id, task.id, 'failed', None, _FREE_TIER_MESSAGE, 0, 0)

    # 3. Reserve.
    import chat as chat_mod
    try:
        is_working = await chat_mod.is_working_model(model_to_call)
    except Exception as e:
        logger.warning(f"task_execution: is_working_model failed model={model_to_call}: {e}")
        is_working = False
    est_cost = _RESERVE_ESTIMATE_WORKING if is_working else _RESERVE_ESTIMATE_UNKNOWN

    reservation: dict | None = None
    try:
        async with async_session() as bill_session:
            repo = SqlBillingRepo(bill_session)
            svc = BillingService(repo)
            reservation = await svc.reserve(
                uid, Money(est_cost),
                idempotency_key=f"task:{secrets.token_hex(8)}",
                model=model_to_call,
            )
            await bill_session.commit()
    except InsufficientBalanceError:
        return await _finalize(
            execution_id, task.id, 'failed', None, _INSUFFICIENT_BALANCE_MESSAGE, 0, 0,
            error_code='insufficient_balance',
        )
    except Exception as e:
        logger.warning(f"task_execution: reserve failed uid={uid} model={model_to_call}: {e}")
        return await _finalize(execution_id, task.id, 'failed', None, _GATEWAY_ERROR_MESSAGE, 0, 0)

    # 4. Upstream call.
    try:
        provider = await chat_mod._resolve_provider(model_to_call)
        r = await _http.post(
            f"{provider.v1}/chat/completions", json=chat_payload,
            headers={**provider.headers(), 'Accept': 'application/json'},
        )
    except Exception as e:
        await _release(reservation, uid, 'upstream_exception')
        return await _finalize(execution_id, task.id, 'failed', None, str(e)[:500], 0, 0)

    if r.status_code != 200:
        await _release(reservation, uid, 'upstream_non200')
        return await _finalize(
            execution_id, task.id, 'failed', None,
            f"HTTP {r.status_code}: {r.text[:500]}", 0, 0,
        )

    try:
        data = r.json()
    except Exception as e:
        logger.warning(f"task_execution: unparseable upstream body uid={uid} model={model_to_call}: {e}")
        data = {}

    choices = data.get('choices') or []
    result_text = ''
    if choices and isinstance(choices[0], dict):
        result_text = (choices[0].get('message') or {}).get('content') or ''
    usage = data.get('usage') or {}
    tokens_used = int(usage.get('total_tokens') or 0)

    if not result_text:
        logger.warning(
            f"task_execution: upstream HTTP 200 but no content uid={uid} "
            f"model={model_to_call} task_id={task.id} -- billing nothing"
        )
        await _release(reservation, uid, 'empty_result')
        return await _finalize(execution_id, task.id, 'failed', None, _EMPTY_RESPONSE_MESSAGE, 0, 0)

    # 5. Settle -- late-bound, bare uid, opens its own session, already
    # handles a missing/partial usage block via the L1 local estimate.
    cost_toman = 0
    try:
        cost_info = await chat_mod._bill_stream_usage(uid, chat_payload, usage, response_text=result_text)
        cost_toman = int((cost_info or {}).get('cost') or 0)
    except Exception as e:
        # The response was already generated and is about to be returned to
        # the user -- a settle failure here is a reconciliation problem, not
        # a reason to withhold a response already paid for (same reasoning
        # as images.py's settle-failure comment). Logged loudly so it is
        # never silently invisible.
        logger.error(
            f"task_execution: settle FAILED after a successful upstream response "
            f"uid={uid} model={model_to_call} task_id={task.id} "
            f"reservation={reservation.get('reservation_id') if reservation else None}: {e}"
        )

    # 6. Release the pre-flight hold. The real charge was already applied
    # directly against wallet.balance inside _bill_stream_usage/_record_usage
    # (same pattern chat.py's own non-streaming handler uses -- reserve()
    # exists to gate availability up front; it is released, never settled,
    # once the real charge has been applied).
    await _release(reservation, uid, 'after_success')

    return await _finalize(execution_id, task.id, 'completed', result_text, None, tokens_used, cost_toman)
