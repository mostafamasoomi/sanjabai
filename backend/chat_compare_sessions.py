"""`/v1/compare/sessions*` -- compare history + continue (migration 0054,
docs/superpowers/specs/2026-08-30-compare-history-continue-design.md).

Split out of chat_compare.py purely to keep THAT file under the house
500-line cap once this feature's routes were added -- same reason chat.py
itself is split into chat_web.py/chat_models.py/chat_search.py/
chat_billing.py/chat_stream.py/chat_compare.py/chat_smart.py. No behaviour
difference from living in chat_compare.py directly: `chat_compare.py`
imports the four route functions below at the bottom of its own module
body (after `_call_model_once`, `compare_models`, etc. are already defined
in its namespace) purely to register them on `chat.router` -- the same
side-effecting-import idiom chat.py uses for chat_web.py/chat_compare.py
itself. This file imports `_call_model_once` back FROM chat_compare.py
(one direction only, no cycle) so the reserve/gather/release + per-model
call/billing/error shape stays defined in exactly one place instead of
being duplicated.

MONKEYPATCH CONTRACT: same as chat_compare.py -- every attribute that tests
monkeypatch on the `chat` module (`_get_user_id`, `_resolve_provider`,
`check_and_consume`, `BillingService`, `async_session`, `_http`,
`_track_usage`, `_apply_web_search`, `_web_search`, ...) is resolved
through `chat.<name>` at call time below, never via `from chat import X`.
`chat` is imported plainly at module scope for the same circular-import
safety reason documented in chat_compare.py's docstring.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone

import sqlalchemy
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from models import CompareSession
from services.billing import SqlBillingRepo, InsufficientBalanceError
from services.money import Money
from services.entitlement_gate import covering_entitlement
from services.free_tier import covers_request
from i18n import err, err_openai

import chat
from chat_compare import _call_model_once, _check_quota_pre

logger = logging.getLogger('chat')  # keep all chat_*.py logs under the pre-split 'chat' logger name


class CompareContinueRequest(BaseModel):
    target: str  # 'both' | 'a' | 'b'
    content: str
    web_search: bool = False


def _insert_after_last_system(msgs: list, msg: dict) -> None:
    """Insert `msg` right after the last existing system message in `msgs`
    (index 0 if there is none) -- the exact positional rule
    chat_search._apply_web_search uses. Reused by the `target='both'` path
    below so a second thread can receive the identical grounding system
    message without a second web search call (see
    `_search_grounded_messages`)."""
    idx = 0
    for i, m in enumerate(msgs):
        if isinstance(m, dict) and m.get('role') == 'system':
            idx = i + 1
    msgs.insert(idx, dict(msg))


async def _search_grounded_messages(source: list, web_search: bool, *, handler: str) -> tuple[list, dict | None]:
    """Run `chat._apply_web_search` once against `source` and return the
    grounded copy plus the search-result system message it inserted (or
    None if search was off or found nothing) -- so a sibling thread can
    reuse that same message via `_insert_after_last_system` instead of
    triggering a second `chat._web_search` call for the identical query.
    `source` is copied, not mutated, matching `_call_model_once`'s
    no-shared-list-mutation rule."""
    _ws = {'messages': list(source), 'web_search': web_search}
    await chat._apply_web_search(_ws, handler=handler)
    grounded = _ws['messages']
    search_msg = None
    if len(grounded) > len(source):
        _source_ids = {id(m) for m in source}
        for m in grounded:
            if id(m) not in _source_ids:
                search_msg = m
                break
    return grounded, search_msg


@chat.router.post('/v1/compare/sessions/{session_id}/continue')
async def continue_compare_session(request: Request, session_id: int, payload: CompareContinueRequest) -> Response:
    """Send one message to both sides of an existing comparison, or to only
    one side -- see the module docstring / design spec for the contract.
    `target='a'`/`'b'` gates, reserves, calls and settles billing for ONLY
    that one model; the untouched side's thread and reservation are never
    touched, mirroring the reason `compare_models()` batches both models
    into one free-tier/premium gate call for `target='both'` (a rejection
    on one model must never burn the other's already-spent allowance).
    """
    uid = await chat._get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)

    if payload.target not in ('both', 'a', 'b'):
        return err_openai(
            'مقصد نامعتبر است',
            "target must be 'both', 'a', or 'b'.",
            400, code='invalid_target', err_type='invalid_request',
        )
    if chat.async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable.', 500)

    async with chat.async_session() as session:
        res = await session.execute(
            CompareSession.__table__.select().where(
                CompareSession.id == session_id, CompareSession.user_id == uid
            )
        )
        row = res.fetchone()
    if not row:
        return err('یافت نشد', 'Not found.', 404)

    new_msg = {'role': 'user', 'content': payload.content}
    # Same choke point every other chat entry point runs through first
    # (chat_enabled flag + content moderation + aggregate message quota) --
    # see chat_web._chat_preflight's docstring: this is a fifth call site
    # sending new content to a model, not exempt from it.
    _disabled = await chat._chat_preflight(uid, [new_msg])
    if _disabled is not None:
        return _disabled

    call_a = payload.target in ('both', 'a')
    call_b = payload.target in ('both', 'b')
    model_a, model_b = row.model_a, row.model_b
    models_in_scope = [m for m, use in ((model_a, call_a), (model_b, call_b)) if use]

    # Free-tier / premium gates -- scoped to ONLY the model(s) in scope this
    # turn (see this module's docstring and the design spec's billing notes):
    # a solo continue must never gate/consume against the untouched side.
    _ft_gate = await chat.check_and_consume(uid, models_in_scope)
    if _ft_gate is not None:
        return chat._free_tier_response(_ft_gate)
    _premium_gate = await chat.premium_check_and_consume(uid, models_in_scope)
    if _premium_gate is not None:
        return chat._premium_quota_response(_premium_gate)

    # Reserve billing -- one reservation per model IN SCOPE, same shape as
    # compare_models()'s dual-reserve but skipping the untouched side entirely.
    reservation_a = None
    reservation_b = None
    try:
        async with chat.async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = chat.BillingService(_repo)
            if call_a:
                if await covering_entitlement(uid, 1000) is not None or await covers_request(uid):
                    reservation_a = None
                else:
                    reservation_a = await _bill_svc.reserve(
                        uid, Money(1000), idempotency_key=f"cmpc:{secrets.token_hex(8)}", model=model_a,
                    )
            if call_b:
                if await covering_entitlement(uid, 1000) is not None or await covers_request(uid):
                    reservation_b = None
                else:
                    reservation_b = await _bill_svc.reserve(
                        uid, Money(1000), idempotency_key=f"cmpc:{secrets.token_hex(8)}", model=model_b,
                    )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return err_openai(
            'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.',
            'Your wallet balance is not enough. Please top up your account.',
            429, code='balance', err_type='quota_exceeded',
        )
    except Exception as e:
        logger.warning(f"Compare continue BillingService.reserve failed uid={uid}: {e}")
        quota_err = await _check_quota_pre(uid)
        if quota_err is not None:
            return quota_err

    # Web search, run at most once for this turn even when target='both'
    # (see _search_grounded_messages's docstring) -- never per-model.
    arr_a = (list(row.thread_a or []) + [new_msg]) if call_a else None
    arr_b = (list(row.thread_b or []) + [new_msg]) if call_b else None
    search_msg = None
    if call_a:
        arr_a, search_msg = await _search_grounded_messages(arr_a, payload.web_search, handler='compare.continue')
    if call_b:
        if search_msg is not None:
            _insert_after_last_system(arr_b, search_msg)
        else:
            arr_b, _ = await _search_grounded_messages(arr_b, payload.web_search, handler='compare.continue')

    result_a = None
    result_b = None
    if payload.target == 'both':
        result_a, result_b = await asyncio.gather(
            _call_model_once(model_a, arr_a, uid, request),
            _call_model_once(model_b, arr_b, uid, request),
        )
    elif call_a:
        result_a = await _call_model_once(model_a, arr_a, uid, request)
    elif call_b:
        result_b = await _call_model_once(model_b, arr_b, uid, request)

    # Echo back exactly what the caller originally requested, never the
    # resolved provider_model_id (same no-provider-leak rule as compare_models()).
    if result_a is not None:
        result_a['model'] = row.model_a_requested
    if result_b is not None:
        result_b['model'] = row.model_b_requested

    for res_ in (reservation_a, reservation_b):
        if res_:
            try:
                async with chat.async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = chat.BillingService(_rel_repo)
                    await _rel_svc.release(res_['reservation_id'])
                    await _rel_session.commit()
            except Exception as _rel_e:
                logger.warning(f"Compare continue BillingService.release failed uid={uid}: {_rel_e}")

    # faster/cheaper only meaningful when both ran THIS turn -- same rule as
    # compare_models(), null on a solo turn per the design spec.
    faster = None
    cheaper = None
    if payload.target == 'both' and not result_a.get('error') and not result_b.get('error'):
        if result_a['elapsed'] < result_b['elapsed']:
            faster = 'model_a'
        elif result_b['elapsed'] < result_a['elapsed']:
            faster = 'model_b'
        if result_a['cost'] < result_b['cost']:
            cheaper = 'model_a'
        elif result_b['cost'] < result_a['cost']:
            cheaper = 'model_b'

    update_data = {'updated_at': datetime.now(timezone.utc).replace(tzinfo=None)}
    if call_a:
        update_data['thread_a'] = arr_a + [{'role': 'assistant', 'content': result_a['content']}]
    if call_b:
        update_data['thread_b'] = arr_b + [{'role': 'assistant', 'content': result_b['content']}]
    async with chat.async_session() as _upd_session:
        await _upd_session.execute(
            CompareSession.__table__.update().where(CompareSession.id == session_id), update_data,
        )
        await _upd_session.commit()

    return JSONResponse(jsonable_encoder({
        'model_a': result_a,
        'model_b': result_b,
        'faster': faster,
        'cheaper': cheaper,
    }))


# ── Compare session history (list/get/delete) ──────────────────────────
# Paginated list mirrors conversations.py's list_conversations() exactly
# (same page/limit/OFFSET/LIMIT shape, capped at 100); get/delete mirror
# get_conversation()/delete_conversation()'s ownership-scoped
# `WHERE id = ... AND user_id = ...` pattern -- no separate ownership-check
# helper exists in this codebase, so none is added here either.

@chat.router.get('/v1/compare/sessions')
async def list_compare_sessions(request: Request) -> JSONResponse:
    uid = await chat._get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if chat.async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable.', 500)
    page = int(request.query_params.get('page', 1))
    limit = min(int(request.query_params.get('limit', 20)), 100)
    offset = (page - 1) * limit
    async with chat.async_session() as session:
        count_res = await session.execute(
            sqlalchemy.text('SELECT COUNT(*) as c FROM compare_sessions WHERE user_id = :uid'),
            {'uid': uid},
        )
        total = count_res.fetchone().c
        res = await session.execute(
            sqlalchemy.text(
                'SELECT id, title, model_a_requested, model_b_requested, created_at, updated_at '
                'FROM compare_sessions WHERE user_id = :uid ORDER BY updated_at DESC OFFSET :off LIMIT :lim'
            ),
            {'uid': uid, 'off': offset, 'lim': limit},
        )
        rows = [
            {
                'id': r.id, 'title': r.title,
                'model_a_requested': r.model_a_requested, 'model_b_requested': r.model_b_requested,
                'created_at': r.created_at, 'updated_at': r.updated_at,
            }
            for r in res.fetchall()
        ]
    return JSONResponse(jsonable_encoder({'items': rows, 'total': total, 'page': page, 'limit': limit}))


@chat.router.get('/v1/compare/sessions/{session_id}')
async def get_compare_session(request: Request, session_id: int) -> JSONResponse:
    uid = await chat._get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if chat.async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable.', 500)
    async with chat.async_session() as session:
        res = await session.execute(
            CompareSession.__table__.select().where(
                CompareSession.id == session_id, CompareSession.user_id == uid
            )
        )
        row = res.fetchone()
        if not row:
            return err('یافت نشد', 'Not found.', 404)
        return JSONResponse(jsonable_encoder({
            'id': row.id, 'title': row.title,
            'model_a_requested': row.model_a_requested, 'model_b_requested': row.model_b_requested,
            'thread_a': row.thread_a, 'thread_b': row.thread_b,
            'created_at': row.created_at, 'updated_at': row.updated_at,
        }))


@chat.router.delete('/v1/compare/sessions/{session_id}')
async def delete_compare_session(request: Request, session_id: int) -> JSONResponse:
    uid = await chat._get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if chat.async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable.', 500)
    async with chat.async_session() as session:
        res = await session.execute(
            CompareSession.__table__.select().where(
                CompareSession.id == session_id, CompareSession.user_id == uid
            )
        )
        row = res.fetchone()
        if not row:
            return err('یافت نشد', 'Not found.', 404)
        await session.execute(CompareSession.__table__.delete().where(CompareSession.id == session_id))
        await session.commit()
    return JSONResponse({'status': 'deleted'})
