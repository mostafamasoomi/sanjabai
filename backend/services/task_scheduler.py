"""5-field cron evaluator + background scheduling loop for scheduled tasks.

Before this module existed, `scheduled_tasks.cron_expression` and
`next_run_at` were stored on the row but nothing ever evaluated them -- a
task only ever fired when someone clicked "run" (see backend/tasks.py's
POST /tasks/{id}/run). This module is what turns those columns from
decorative into load-bearing:

* :func:`compute_next_run` is a minimal 5-field cron evaluator (numbers,
  ``*``, ``*/n``, ranges, lists) used by tasks.py's create_task/update_task
  to populate `next_run_at`, and by this module's own loop to recompute it
  after every run. It is written from scratch on purpose: `croniter` is not
  in requirements.txt, and the prebuilt `sanjabai-test:local` image the CI
  verification step runs against does not have it either -- a new top-level
  import of it would fail the entire test suite at collection time, not just
  this feature.

* :func:`scheduler_loop` is a 60-second-tick background loop (see app.py's
  lifespan for the `asyncio.create_task(...)` hook this is meant to be
  wired into -- NOT edited here, the coordinator owns app.py) that claims
  every due task with a single atomic ``UPDATE ... WHERE is_active AND
  next_run_at <= now() RETURNING ...`` (see :func:`claim_due_tasks`) so two
  overlapping ticks can never hand the same task to two concurrent
  executions, then runs each claimed task through
  ``task_execution._execute_task`` (the billed execution core) and
  recomputes its `next_run_at`.

Timestamps follow this codebase's naive-UTC convention throughout (see
models.py::_utcnow() -- `datetime.now(timezone.utc).replace(tzinfo=None)`).
A tz-aware/naive comparison mismatch has already caused one production
incident here (commit 3437409, in chat.py's quota.reset_at handling); every
datetime this module touches is normalized via :func:`_as_naive_utc` before
any comparison, and both :func:`cron_matches` and :func:`compute_next_run`
are tested against both naive and tz-aware input.

🔴 The loop is gated behind ``TASK_SCHEDULER_ENABLED`` (env var), DEFAULTING
TO OFF. This is the first code path in the product that spends a user's
money with no human on the trigger -- it must not run in production until
the coordinator has verified billing end-to-end on a manual run.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from database import async_session

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: str = 'false') -> bool:
    return os.getenv(name, default).strip().lower() in ('1', 'true', 'yes', 'on')


TASK_SCHEDULER_ENABLED = _env_flag('TASK_SCHEDULER_ENABLED')
TASK_SCHEDULER_TICK_SECONDS = int(os.getenv('TASK_SCHEDULER_TICK_SECONDS', '60') or '60')

# Hard cap on how far into the future compute_next_run will search before
# giving up -- protects against a cron expression that can never match
# (e.g. "0 0 30 2 *", February 30th never exists in any year) turning into
# an infinite loop. Two years of minutes is comfortably beyond any
# realistic schedule this product would ever configure.
_MAX_SEARCH_MINUTES = 2 * 366 * 24 * 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive_utc(dt: datetime) -> datetime:
    """Normalize a possibly tz-aware datetime to this codebase's naive-UTC
    convention (see models.py::_utcnow()). See module docstring for why
    this matters -- a tz-aware/naive mismatch here has already caused a
    production incident (commit 3437409) in the equivalent chat.py code."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ── 5-field cron evaluator ──────────────────────────────────────────────

def _parse_cron_field(field: str, lo: int, hi: int) -> set[int]:
    """Parse one of the 5 cron fields into the set of values it matches.

    Supports a literal number, ``*``, ``*/n`` (step), ``a-b`` (range),
    ``a-b/n`` (stepped range), and comma-separated lists of any of the
    above. Deliberately NOT a full cron grammar (no named months/days, no
    ``?``/``L``/``W``/``#``) -- this product's scheduled tasks only ever
    need the common cases, and a hand-rolled minimal evaluator was an
    explicit requirement (no new dependency).
    """
    field = field.strip()
    if not field:
        raise ValueError('empty cron field')
    values: set[int] = set()
    for part in field.split(','):
        part = part.strip()
        if not part:
            continue
        step = 1
        base = part
        if '/' in part:
            base, step_s = part.split('/', 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError(f'invalid step in cron field: {part!r}')
        if base == '*':
            start, end = lo, hi
        elif '-' in base:
            a, b = base.split('-', 1)
            start, end = int(a), int(b)
        else:
            start = end = int(base)
        if start > end or start < lo or end > hi:
            raise ValueError(f'cron field value out of range: {part!r} (expected {lo}-{hi})')
        v = start
        while v <= end:
            values.add(v)
            v += step
    return values


def _compile_cron(cron_expression: str) -> dict[str, Any]:
    """Parse a 5-field cron expression once into matcher state, so a caller
    that needs to test many candidate datetimes (compute_next_run) does not
    re-parse the string on every candidate."""
    fields = cron_expression.split()
    if len(fields) != 5:
        raise ValueError(f'cron expression must have 5 fields, got {len(fields)}: {cron_expression!r}')
    minute_f, hour_f, dom_f, month_f, dow_f = fields
    dows_raw = _parse_cron_field(dow_f, 0, 7)
    return {
        'minutes': _parse_cron_field(minute_f, 0, 59),
        'hours': _parse_cron_field(hour_f, 0, 23),
        'doms': _parse_cron_field(dom_f, 1, 31),
        'months': _parse_cron_field(month_f, 1, 12),
        'dows': {v % 7 for v in dows_raw},  # cron uses 0 AND 7 for Sunday
        'dom_restricted': dom_f.strip() != '*',
        'dow_restricted': dow_f.strip() != '*',
    }


def _matches_compiled(compiled: dict[str, Any], when: datetime) -> bool:
    when = _as_naive_utc(when)
    if when.minute not in compiled['minutes']:
        return False
    if when.hour not in compiled['hours']:
        return False
    if when.month not in compiled['months']:
        return False
    dom_restricted = compiled['dom_restricted']
    dow_restricted = compiled['dow_restricted']
    if not dom_restricted and not dow_restricted:
        return True
    # Standard cron OR-quirk: when BOTH day-of-month and day-of-week are
    # restricted (neither is '*'), the day matches if EITHER matches; when
    # only one is restricted, only that one applies. ANDing the two
    # unconditionally would silently turn e.g. "0 9 1 * 1" (9am on the 1st
    # OR every Monday) into "the 1st, but only if it's a Monday".
    cron_dow = (when.weekday() + 1) % 7  # Python Monday=0 -> cron Sunday=0
    if dom_restricted and dow_restricted:
        return when.day in compiled['doms'] or cron_dow in compiled['dows']
    if dom_restricted:
        return when.day in compiled['doms']
    return cron_dow in compiled['dows']


def cron_matches(cron_expression: str, when: datetime) -> bool:
    """Return True iff `when` (naive or tz-aware -- normalized to naive UTC
    first) matches the 5-field cron expression ``minute hour dom month dow``.
    """
    return _matches_compiled(_compile_cron(cron_expression), when)


def compute_next_run(cron_expression: str, after: datetime) -> datetime | None:
    """The first minute-aligned datetime strictly after `after` (naive or
    tz-aware) that matches `cron_expression`. Returns naive UTC. Returns
    None if nothing matches within `_MAX_SEARCH_MINUTES` (an impossible
    expression, e.g. February 30th)."""
    compiled = _compile_cron(cron_expression)
    after = _as_naive_utc(after)
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(_MAX_SEARCH_MINUTES):
        if _matches_compiled(compiled, candidate):
            return candidate
        candidate += timedelta(minutes=1)
    logger.error(f"task_scheduler: cron expression never matches within search window: {cron_expression!r}")
    return None


# ── Atomic claim + execution loop ───────────────────────────────────────

_CLAIM_SQL = text(
    "UPDATE scheduled_tasks SET next_run_at = NULL "
    "WHERE is_active = true AND next_run_at IS NOT NULL AND next_run_at <= :now "
    "RETURNING id, user_id, model, prompt, cron_expression"
)

_SET_NEXT_RUN_SQL = text("UPDATE scheduled_tasks SET next_run_at = :next_run_at WHERE id = :task_id")


async def claim_due_tasks(session, now: datetime) -> list:
    """Atomically claim every active task whose next_run_at is due, in a
    single UPDATE ... RETURNING. This is what makes two overlapping ticks
    unable to double-run the same task: the WHERE clause requires
    next_run_at IS NOT NULL, and this same statement sets it to NULL as
    part of the claim -- a second concurrent UPDATE (a real overlapping
    tick, in production, on the same Postgres row) blocks on the row lock
    and, once the first commits, sees next_run_at already NULL and matches
    nothing."""
    res = await session.execute(_CLAIM_SQL, {'now': now})
    return res.fetchall()


async def _recompute_next_run(task_id: int, cron_expression: str, base_time: datetime) -> None:
    if async_session is None:
        return
    next_run = compute_next_run(cron_expression, base_time)
    try:
        async with async_session() as session:
            await session.execute(_SET_NEXT_RUN_SQL, {'next_run_at': next_run, 'task_id': task_id})
            await session.commit()
    except Exception as e:
        logger.error(f"task_scheduler: failed to recompute next_run_at task_id={task_id}: {e}")


async def _run_claimed_task(row: Any) -> None:
    """Execute one claimed task and ALWAYS recompute its next_run_at
    afterward, even if _execute_task raises -- otherwise a claimed task
    (whose next_run_at was just set to NULL by the claim query) would never
    be scheduled again."""
    import task_execution

    base_time = _utcnow()
    try:
        await task_execution._execute_task(row, row.user_id)
    except Exception as e:
        logger.error(f"task_scheduler: _execute_task raised for task_id={row.id}: {e}")
    finally:
        await _recompute_next_run(row.id, row.cron_expression, base_time)


async def scheduler_tick() -> int:
    """Claim and run every currently-due task once. Returns how many were claimed."""
    if async_session is None:
        return 0
    try:
        async with async_session() as session:
            rows = await claim_due_tasks(session, _utcnow())
            await session.commit()
    except Exception as e:
        logger.error(f"task_scheduler: claim query failed: {e}")
        return 0
    for row in rows:
        await _run_claimed_task(row)
    return len(rows)


async def _db_scheduler_flag() -> bool:
    """Best-effort read of the ``task_scheduler_enabled`` DB flag.

    ``site_settings.get_site_flag`` already fails open to its registered
    default (``False`` for this flag) on any Redis/DB error and never
    raises -- but this wrapper still catches everything around the call
    (e.g. the import itself failing) so a problem here can never do
    anything worse than "behave as if the DB flag were off", i.e. fall
    back to env-var-only behaviour, per the brief.
    """
    try:
        from site_settings import get_site_flag
        return await get_site_flag('task_scheduler_enabled')
    except Exception as e:
        logger.warning(f"task_scheduler: DB flag read failed, falling back to env-only: {e}")
        return False


async def _effective_scheduler_enabled() -> bool:
    """Env var OR DB flag -- either one being on turns the scheduler on.

    Short-circuits on the env var so the common "env already on" case never
    needs a DB round-trip, and so an env-off deployment can still be turned
    on purely from the admin panel.
    """
    if TASK_SCHEDULER_ENABLED:
        return True
    return await _db_scheduler_flag()


async def scheduler_loop() -> None:
    """Background loop -- see app.py's lifespan for the
    `asyncio.create_task(scheduler_loop())` hook (added by the coordinator,
    not this module).

    Gated behind ``TASK_SCHEDULER_ENABLED`` (env var) OR the
    ``task_scheduler_enabled`` DB flag (see :func:`_effective_scheduler_enabled`),
    defaulting to OFF: see the 🔴 note in the module docstring.

    This loop is long-lived (one instance for the life of the process), so
    the effective enabled state is re-evaluated on *every* tick rather than
    once at entry -- a one-shot check at startup would mean an admin
    flipping the DB flag in the panel only takes effect after a container
    restart, which is exactly the problem these flags exist to solve. When
    disabled, the loop still ticks (sleeping the same interval) purely to
    re-check the flag -- it does not claim or run any tasks. A single log
    line is emitted only when the effective state actually *changes*
    (on/off or off/on), not on every tick, to avoid spamming the log with a
    line every `TASK_SCHEDULER_TICK_SECONDS` forever.
    """
    logger.info(f"task_scheduler: loop starting, tick={TASK_SCHEDULER_TICK_SECONDS}s")
    last_state: bool | None = None
    while True:
        try:
            enabled = await _effective_scheduler_enabled()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Should be unreachable (_effective_scheduler_enabled already
            # catches everything internally), but per the same fail-open
            # contract as the rest of this module: never let a flag-read
            # problem crash the loop or silently spend money -- treat it as
            # "off" for this tick and try again next tick.
            logger.error(f"task_scheduler: effective-enabled check failed unexpectedly: {e}")
            enabled = False

        if enabled != last_state:
            logger.info(
                f"task_scheduler: effective enabled state changed -> "
                f"{'ON' if enabled else 'OFF'} (env={TASK_SCHEDULER_ENABLED})"
            )
            last_state = enabled

        if enabled:
            try:
                claimed = await scheduler_tick()
                if claimed:
                    logger.info(f"task_scheduler: executed {claimed} due task(s)")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"task_scheduler: tick failed: {e}")

        await asyncio.sleep(TASK_SCHEDULER_TICK_SECONDS)
