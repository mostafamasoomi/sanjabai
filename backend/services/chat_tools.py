"""The tool registry for the LLM chat-tool-calling loop (Phase 8, packet B3).

Three tools only, in a module-level `frozenset` (`TOOL_NAMES`): `list_models`
(read-only), `create_task` and `create_assistant` (both write, both always
create an inert/private row -- see the two boundary comments below). This
module has ZERO integration with the chat path yet: nothing calls
`dispatch()` in production. A later packet wires the loop; this one builds
the registry and proves it with tests.

Four security boundaries, matched to the design doc (docs `design-phase8.md`
sections ب‑٥/ب‑٦):

1. Identity never comes from the model. No tool takes `user_id`/`uid`/
   `owner` as an argument -- `uid` is a parameter supplied by the caller
   (a closure over the authenticated session in the loop packet), and every
   write is scoped to it IN THE QUERY, never compared in Python afterwards,
   exactly as `smart_router.py`'s `_COMBO_SQL` comment (around lines
   311-322) argues for combo ownership.
2. No tool spends money and no tool activates anything. `create_task`
   always ends with `is_active=False, next_run_at=NULL`; `create_assistant`
   always ends with `is_public=False`. Neither is negotiable -- see
   `_exec_create_task` and `_exec_create_assistant` below.
3. Tool output is fixed-shape JSON, never free text, and never a raw
   exception. Every return path goes through `_cap_result`, which also
   enforces the 4,000-character serialized cap.
4. The action space is closed, not filtered: `TOOL_NAMES` is a frozenset
   compared with `in`, there is no `getattr`/`eval`/`exec` anywhere in this
   file (`tests/test_chat_tools.py::test_module_source_has_no_eval_exec_or_dynamic_getattr`
   asserts this over the AST, not by convention).

A tool-created task is inserted ALREADY DORMANT, in one transaction:
`create_task(uid, spec, activate=False)` sets `is_active=False` and
`next_run_at=NULL` before the insert. The default stays `activate=True` for
the `POST /tasks` handler, where a human just clicked "create" and an armed
task is what they asked for.

This module first shipped with a corrective `UPDATE` straight after the
insert instead, which left a window -- however short -- in which a
model-authored task was armed and schedulable. `TASK_SCHEDULER_ENABLED` is
off today so nothing polled it, but a window with the user's money on the
other side is not one to keep, and it stops being theoretical the day that
flag flips. The senior closed it at the source; see the `activate` parameter
in services/task_service.py for the full reasoning.

CONTRACT GAP found against `services.smart_router.Candidate`: it carries no
display-name field at all, only `public_id`. The design calls for
`"name_fa"` sourced from `candidate_pool()`; there is nothing to source it
from without a second query (explicitly forbidden by the packet). `_label`
below falls back to the `public_id` with the `sanjab/` namespace stripped --
not actually Persian text, but it never leaks the provider/upstream name,
which is the one non-negotiable part of that rule. Flagged for a follow-up
to `smart_router.py`'s SELECT, not fixed here.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any


from database import async_session
from services.task_scheduler import compute_next_run

# ── The closed action space (boundary 4) ──────────────────────────────────

_READ_ONLY_TOOLS = frozenset({'list_models'})
_WRITE_TOOLS = frozenset({'create_task', 'create_assistant'})
TOOL_NAMES = _READ_ONLY_TOOLS | _WRITE_TOOLS

# ── Validation bounds (defined before TOOL_SCHEMAS so the schema's
# maxLength values are the same constants the validators enforce, never a
# second hardcoded copy that could drift) ──────────────────────────────────

_TITLE_MAX = 100
_PROMPT_MAX = 10_000
_DESCRIPTION_MAX = 500
_NAME_MAX = 100
_SYSTEM_PROMPT_MAX = 8_000
_ICON_ALLOWED = frozenset({'chat', 'sparkles', 'code', 'palette', 'rocket', 'cpu', 'globe', 'chart'})
_LIST_MODELS_CAP = 20
_MAX_RESULT_CHARS = 4_000

# `services.task_service`'s own sentinel for "resolve at run time" -- see
# tasks.py's `_DEFAULT_MODEL_SENTINEL` docstring. `model` is never a tool
# argument (design rule); this is the only value ever passed.
_TASK_MODEL_SENTINEL = ''

_TIER_FA = {1: 'ارزان', 2: 'میانی', 3: 'بالا'}

# OpenAI-compatible function-calling schemas, keyed by tool name -- the loop
# packet builds the upstream `tools` array from `announced_tools()` plus
# this dict. Not otherwise consumed here.
TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    'list_models': {
        'type': 'function',
        'function': {
            'name': 'list_models',
            'description': 'مدل‌های در دسترس کاربر را با نام و رده قیمتی فهرست کن.',
            'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False},
        },
    },
    'create_task': {
        'type': 'function',
        'function': {
            'name': 'create_task',
            'description': (
                'یک وظیفهٔ زمان‌بندی‌شده پیش‌نویس کن. وظیفه غیرفعال ساخته می‌شود؛ '
                'کاربر خودش باید آن را فعال کند.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string', 'maxLength': _TITLE_MAX},
                    'prompt': {'type': 'string', 'maxLength': _PROMPT_MAX},
                    'cron_expression': {'type': 'string'},
                    'description': {'type': 'string', 'maxLength': _DESCRIPTION_MAX},
                },
                'required': ['title', 'prompt', 'cron_expression'],
                'additionalProperties': False,
            },
        },
    },
    'create_assistant': {
        'type': 'function',
        'function': {
            'name': 'create_assistant',
            'description': 'یک دستیار خصوصی (فقط برای همین کاربر) بساز.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'name': {'type': 'string', 'maxLength': _NAME_MAX},
                    'system_prompt': {'type': 'string', 'maxLength': _SYSTEM_PROMPT_MAX},
                    'description': {'type': 'string', 'maxLength': _DESCRIPTION_MAX},
                    'icon': {'type': 'string'},
                },
                'required': ['name', 'system_prompt'],
                'additionalProperties': False,
            },
        },
    },
}


def announced_tools(autonomy_level: str) -> frozenset[str]:
    """Which tool names the loop should put in the upstream `tools` array.

    `low` announces only `list_models` -- the creating tools aren't even
    offered, so the model isn't tempted to propose them; it falls back to
    telling the user in Persian where to go build one themselves. `medium`
    and anything unrecognized announce all three and rely on `dispatch()`
    to gate execution behind a confirmation. `high` also announces all
    three and lets them run.
    """
    if autonomy_level == 'low':
        return _READ_ONLY_TOOLS
    return TOOL_NAMES


def _valid_str(value: Any, min_len: int, max_len: int) -> bool:
    return isinstance(value, str) and min_len <= len(value) <= max_len


def _validate_task_args(arguments: dict) -> tuple[dict[str, str] | None, str | None]:
    """Only these four keys are ever read. Anything else in `arguments`
    (a stray `user_id`, `is_active`, `model`, ...) is silently ignored --
    that IS the identity/activation guard (boundaries 1 and 2), not a gap
    in it."""
    title = arguments.get('title')
    prompt = arguments.get('prompt')
    description = arguments.get('description', '')
    cron_expression = arguments.get('cron_expression')
    if not _valid_str(title, 1, _TITLE_MAX):
        return None, 'bad_title'
    if not _valid_str(prompt, 1, _PROMPT_MAX):
        return None, 'bad_prompt'
    if not isinstance(description, str) or len(description) > _DESCRIPTION_MAX:
        return None, 'bad_description'
    if not isinstance(cron_expression, str):
        return None, 'bad_cron'
    try:
        next_run = compute_next_run(cron_expression, datetime.now(timezone.utc))
    except ValueError:
        return None, 'bad_cron'
    if next_run is None:
        return None, 'bad_cron'
    return {
        'title': title, 'prompt': prompt, 'description': description,
        'cron_expression': cron_expression,
    }, None


def _validate_assistant_args(arguments: dict) -> tuple[dict[str, str] | None, str | None]:
    """Only these four keys are ever read -- `is_public` and `model_id` in
    particular are never looked at here, which is the whole enforcement of
    boundary 2 for this tool (see `_exec_create_assistant`)."""
    name = arguments.get('name')
    system_prompt = arguments.get('system_prompt')
    description = arguments.get('description', '')
    icon = arguments.get('icon', 'chat')
    if not _valid_str(name, 1, _NAME_MAX):
        return None, 'bad_name'
    if not _valid_str(system_prompt, 1, _SYSTEM_PROMPT_MAX):
        return None, 'bad_system_prompt'
    if not isinstance(description, str) or len(description) > _DESCRIPTION_MAX:
        return None, 'bad_description'
    if not isinstance(icon, str) or icon not in _ICON_ALLOWED:
        icon = 'chat'
    return {
        'name': name, 'system_prompt': system_prompt, 'description': description, 'icon': icon,
    }, None


# ── Result capping (boundary 3) ────────────────────────────────────────────

def _clip_strings(value: Any, max_len: int) -> Any:
    if isinstance(value, str):
        return value if len(value) <= max_len else value[:max_len] + '…'
    if isinstance(value, dict):
        return {k: _clip_strings(v, max_len) for k, v in value.items()}
    if isinstance(value, list):
        return [_clip_strings(v, max_len) for v in value]
    return value


def _cap_result(result: dict) -> dict:
    """Every `dispatch()` return path goes through here. Bounds the
    serialized size at `_MAX_RESULT_CHARS` -- a confirmation `preview` can
    echo back up to 10,000 characters of `prompt` (create_task) or 8,000 of
    `system_prompt` (create_assistant) straight into the model's context,
    and nothing about tool-result plumbing should be able to blow that up.
    Never raises: an unserializable value degrades to a fixed error shape
    rather than a stack trace ever reaching the model (boundary 3)."""
    try:
        encoded = json.dumps(result, ensure_ascii=False)
    except TypeError:
        return {'ok': False, 'error': 'unserializable_result'}
    if len(encoded) <= _MAX_RESULT_CHARS:
        return result
    clip_len = 2000
    while clip_len >= 50:
        clipped = _clip_strings(copy.deepcopy(result), clip_len)
        clipped['truncated'] = True
        if len(json.dumps(clipped, ensure_ascii=False)) <= _MAX_RESULT_CHARS:
            return clipped
        clip_len //= 2
    return {'ok': result.get('ok', False), 'truncated': True, 'error': 'result_too_large'}


# ── list_models ─────────────────────────────────────────────────────────

def _label(public_id: str) -> str:
    """See the CONTRACT GAP note in the module docstring: `Candidate` has
    no display-name field, so this is `public_id` with the `sanjab/`
    namespace stripped -- never the provider/upstream name."""
    return public_id.split('/', 1)[1] if '/' in public_id else public_id


async def _list_models() -> dict:
    # Imported lazily: `smart_router.py` does `import chat` at module
    # scope, and `chat.py` imports `services.token_budget` and
    # `middleware.compression` -- both being edited by other packets right
    # now. A module-level import here would make this file's collection
    # depend on the state of files this packet does not own.
    from services.smart_router import band_of, band_thresholds, candidate_pool

    pool = await candidate_pool()
    thresholds = band_thresholds(pool)
    models = [
        {'id': c.public_id, 'name_fa': _label(c.public_id), 'tier': _TIER_FA[band_of(c, thresholds)]}
        for c in pool[:_LIST_MODELS_CAP]
    ]
    return {'ok': True, 'models': models}


# ── create_task / create_assistant execution ───────────────────────────────

async def _exec_create_task(uid: int, normalized: dict[str, str]) -> dict:
    from services.task_service import TaskSpec, TaskValidationError
    from services.task_service import create_task as _create_task_core

    spec = TaskSpec(
        title=normalized['title'], prompt=normalized['prompt'],
        description=normalized['description'], model=_TASK_MODEL_SENTINEL,
        cron_expression=normalized['cron_expression'],
    )
    try:
        # activate=False is boundary 2, enforced in the insert itself rather
        # than corrected afterwards -- hardcoded here, never read from
        # `normalized`, so no model argument can arm a task.
        row = await _create_task_core(uid, spec, activate=False)
    except TaskValidationError:
        return {'ok': False, 'error': 'bad_cron'}
    return {'ok': True, 'id': row['id'], 'title': row['title'], 'needs_activation': True}


async def _exec_create_assistant(uid: int, normalized: dict[str, str]) -> dict:
    from services.assistant_service import AssistantSpec
    from services.assistant_service import create_assistant as _create_assistant_core

    spec = AssistantSpec(
        name=normalized['name'], description=normalized['description'],
        system_prompt=normalized['system_prompt'], icon=normalized['icon'],
        is_public=False,  # hardcoded, never from `normalized`/arguments -- boundary 2
    )
    row = await _create_assistant_core(uid, spec)
    if row is None:
        return {'ok': False, 'error': 'db_unavailable'}
    return {'ok': True, 'id': row['id'], 'name': spec.name}


# ── dispatch ────────────────────────────────────────────────────────────

async def dispatch(uid: int, autonomy_level: str, tool_name: str, arguments_json: str) -> dict:
    """The one entrypoint the (future) loop packet calls per `tool_calls`
    entry. `uid` is supplied by the caller's authenticated session, never
    read from `arguments_json` (boundary 1). Never raises: JSON decode
    failures and unknown names become tool results, not exceptions."""
    if tool_name not in TOOL_NAMES:
        return _cap_result({'ok': False, 'error': 'unknown_tool'})

    try:
        arguments = json.loads(arguments_json) if arguments_json else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return _cap_result({'ok': False, 'error': 'bad_arguments'})
    if not isinstance(arguments, dict):
        return _cap_result({'ok': False, 'error': 'bad_arguments'})

    if tool_name == 'list_models':
        return _cap_result(await _list_models())

    if tool_name == 'create_task':
        normalized, error = _validate_task_args(arguments)
    else:
        normalized, error = _validate_assistant_args(arguments)
    if error:
        return _cap_result({'ok': False, 'error': error})

    if autonomy_level != 'high':
        return _cap_result({'ok': False, 'needs_confirmation': True, 'preview': normalized})

    if tool_name == 'create_task':
        return _cap_result(await _exec_create_task(uid, normalized))
    return _cap_result(await _exec_create_assistant(uid, normalized))
