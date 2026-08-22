"""
Scheduled tasks endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, text

from database import async_session, _http, LITELLM_HOST
from models import ScheduledTask, TaskExecution
from dependencies import _get_user_id
import chat as chat_mod

router = APIRouter()

# Empty string is a sentinel meaning "pick whatever the catalog currently
# has available" -- see _default_model() below. Do NOT hardcode a literal
# model id here: a previous version defaulted to 'mimo-v2.5', which the
# catalog can (and did) mark `maintenance`, silently breaking every task
# that didn't pick its own model. See tests/test_small_items.py for the
# regression this guards against.
_DEFAULT_MODEL_SENTINEL = ''

# Short in-process cache for _default_model() so a burst of task
# creations/runs doesn't hit Postgres once per task; refreshed independently
# of chat.py's own resolution caches.
_DEFAULT_MODEL_CACHE: str | None = None
_DEFAULT_MODEL_CACHE_LOADED_AT: float = 0.0
_DEFAULT_MODEL_CACHE_TTL_SECONDS = 60


async def _default_model() -> str:
    """Resolve a model to use when a task doesn't specify one.

    Deliberately does not hardcode a name: picks the cheapest currently
    `available` catalog entry that has a public id (i.e. one real users can
    already see and use through /v1/models), so a catalog change can't
    silently strand tasks the way the old 'mimo-v2.5' literal did. Returns
    '' if the catalog is empty/unreachable -- callers must treat that as
    "no usable model right now" rather than sending an empty string upstream.
    """
    import time as _time

    global _DEFAULT_MODEL_CACHE, _DEFAULT_MODEL_CACHE_LOADED_AT
    now = _time.monotonic()
    if _DEFAULT_MODEL_CACHE is not None and now - _DEFAULT_MODEL_CACHE_LOADED_AT < _DEFAULT_MODEL_CACHE_TTL_SECONDS:
        return _DEFAULT_MODEL_CACHE
    if async_session is None:
        return _DEFAULT_MODEL_CACHE or ''
    try:
        async with async_session() as session:
            res = await session.execute(text(
                "SELECT provider_model_id FROM model_catalog "
                "WHERE availability = 'available' AND public_id IS NOT NULL "
                "ORDER BY (input_per_million + output_per_million) ASC, provider_model_id ASC "
                "LIMIT 1"
            ))
            row = res.fetchone()
            if row and row.provider_model_id:
                _DEFAULT_MODEL_CACHE = str(row.provider_model_id)
                _DEFAULT_MODEL_CACHE_LOADED_AT = now
                return _DEFAULT_MODEL_CACHE
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"_default_model catalog lookup failed: {e}")
    return _DEFAULT_MODEL_CACHE or ''


async def _resolve_task_model(task_model: str) -> str:
    """Canonicalize a scheduled task's model to a real provider_model_id
    before anything is sent upstream -- exactly once, as early as possible.

    Covers both the empty-model sentinel (pick a fresh default, never a
    stale hardcoded one) and an explicit sanjab/* or legacy id a user
    picked (canonicalize it the same way chat.py's /v1/chat/completions
    does, via _resolve_public_model). See _resolve_public_model's docstring
    in chat.py for why this must happen before any upstream call.

    Returns '' when no usable model can be found at all -- callers must
    treat that as "nothing to run", not send an empty string upstream.
    """
    model_to_call = task_model or await _default_model()
    if model_to_call:
        model_to_call = await chat_mod._resolve_public_model(model_to_call)
    return model_to_call


class ScheduledTaskCreate(BaseModel):
    title: str
    description: str = ''
    prompt: str
    model: str = _DEFAULT_MODEL_SENTINEL
    cron_expression: str = '0 9 * * *'
    delivery_channel: str = 'dashboard'


class ScheduledTaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    prompt: str | None = None
    model: str | None = None
    cron_expression: str | None = None
    is_active: bool | None = None
    delivery_channel: str | None = None


@router.get('/tasks')
async def list_tasks(request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.user_id == uid).order_by(ScheduledTask.created_at.desc())
        )
        tasks = res.scalars().all()
        return JSONResponse([{
            'id': t.id, 'title': t.title, 'description': t.description,
            'prompt': t.prompt, 'model': t.model, 'cron_expression': t.cron_expression,
            'is_active': t.is_active, 'last_run_at': t.last_run_at.isoformat() if t.last_run_at else None,
            'next_run_at': t.next_run_at.isoformat() if t.next_run_at else None,
            'run_count': t.run_count, 'last_result': t.last_result,
            'delivery_channel': t.delivery_channel,
            'created_at': t.created_at.isoformat() if t.created_at else None,
            'updated_at': t.updated_at.isoformat() if t.updated_at else None,
        } for t in tasks])


@router.post('/tasks')
async def create_task(request: Request, payload: ScheduledTaskCreate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        task = ScheduledTask(
            user_id=uid, title=payload.title, description=payload.description,
            prompt=payload.prompt, model=payload.model,
            cron_expression=payload.cron_expression, delivery_channel=payload.delivery_channel,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return JSONResponse({
            'id': task.id, 'title': task.title, 'description': task.description,
            'prompt': task.prompt, 'model': task.model, 'cron_expression': task.cron_expression,
            'is_active': task.is_active, 'run_count': task.run_count,
            'delivery_channel': task.delivery_channel,
            'created_at': task.created_at.isoformat() if task.created_at else None,
        })


@router.put('/tasks/{task_id}')
async def update_task(request: Request, task_id: int, payload: ScheduledTaskUpdate) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.user_id == uid)
        )
        task = res.scalar_one_or_none()
        if not task:
            return JSONResponse({'detail': 'task not found | وظیفه یافت نشد'}, status_code=404)
        update_data = payload.model_dump(exclude_unset=True)
        for key, val in update_data.items():
            setattr(task, key, val)
        task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
        await session.refresh(task)
        return JSONResponse({
            'id': task.id, 'title': task.title, 'description': task.description,
            'prompt': task.prompt, 'model': task.model, 'cron_expression': task.cron_expression,
            'is_active': task.is_active, 'run_count': task.run_count,
            'delivery_channel': task.delivery_channel,
        })


@router.delete('/tasks/{task_id}')
async def delete_task(request: Request, task_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.user_id == uid)
        )
        task = res.scalar_one_or_none()
        if not task:
            return JSONResponse({'detail': 'task not found | وظیفه یافت نشد'}, status_code=404)
        await session.delete(task)
        await session.commit()
        return JSONResponse({'status': 'deleted'})


@router.post('/tasks/{task_id}/toggle')
async def toggle_task(request: Request, task_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.user_id == uid)
        )
        task = res.scalar_one_or_none()
        if not task:
            return JSONResponse({'detail': 'task not found | وظیفه یافت نشد'}, status_code=404)
        task.is_active = not task.is_active
        task.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
        return JSONResponse({'id': task.id, 'is_active': task.is_active})


@router.post('/tasks/{task_id}/run')
async def run_task(request: Request, task_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.user_id == uid)
        )
        task = res.scalar_one_or_none()
        if not task:
            return JSONResponse({'detail': 'task not found | وظیفه یافت نشد'}, status_code=404)

        execution = TaskExecution(
            task_id=task.id, user_id=uid, status='running',
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)

    result_text = None
    error_text = None
    tokens_used = 0
    status = 'completed'
    try:
        model_to_call = await _resolve_task_model(task.model)
        if not model_to_call:
            raise RuntimeError('no available model in catalog')
        chat_payload = {
            'model': model_to_call,
            'messages': [{'role': 'user', 'content': task.prompt}],
            'stream': False,
        }
        r = await _http.post(f"{LITELLM_HOST}/v1/chat/completions", json=chat_payload, headers={'Accept': 'application/json'})
        if r.status_code == 200:
            data = r.json()
            result_text = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            tokens_used = data.get('usage', {}).get('total_tokens', 0)
        else:
            status = 'failed'
            error_text = f"HTTP {r.status_code}: {r.text[:500]}"
    except Exception as e:
        status = 'failed'
        error_text = str(e)[:500]

    completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as session:
        res = await session.execute(select(TaskExecution).where(TaskExecution.id == execution.id))
        exec_rec = res.scalar_one()
        exec_rec.status = status
        exec_rec.result = result_text
        exec_rec.error = error_text
        exec_rec.tokens_used = tokens_used
        exec_rec.completed_at = completed_at
        await session.commit()

        res2 = await session.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
        task_rec = res2.scalar_one()
        task_rec.last_run_at = completed_at
        task_rec.run_count += 1
        task_rec.last_result = result_text
        task_rec.updated_at = completed_at
        await session.commit()

    return JSONResponse({
        'execution_id': execution.id, 'status': status, 'result': result_text,
        'error': error_text, 'tokens_used': tokens_used,
    })


@router.get('/tasks/{task_id}/executions')
async def list_task_executions(request: Request, task_id: int) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    async with async_session() as session:
        res = await session.execute(
            select(ScheduledTask).where(ScheduledTask.id == task_id, ScheduledTask.user_id == uid)
        )
        task = res.scalar_one_or_none()
        if not task:
            return JSONResponse({'detail': 'task not found | وظیفه یافت نشد'}, status_code=404)
        res2 = await session.execute(
            select(TaskExecution).where(TaskExecution.task_id == task_id).order_by(TaskExecution.created_at.desc())
        )
        execs = res2.scalars().all()
        return JSONResponse([{
            'id': e.id, 'task_id': e.task_id, 'status': e.status,
            'result': e.result, 'tokens_used': e.tokens_used, 'error': e.error,
            'started_at': e.started_at.isoformat() if e.started_at else None,
            'completed_at': e.completed_at.isoformat() if e.completed_at else None,
            'created_at': e.created_at.isoformat() if e.created_at else None,
        } for e in execs])
