"""
Assistant management endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import async_session
from models import Assistant
import sqlalchemy
from dependencies import _get_user_id
from i18n import err
from services.assistant_service import AssistantSpec, create_assistant as _create_assistant_core

router = APIRouter()


class AssistantCreate(BaseModel):
    name: str = 'New Assistant'
    description: str = ''
    system_prompt: str = ''
    model_id: str = ''
    icon: str = 'chat'
    is_public: bool = False


@router.get('/assistants')
async def list_assistants(request: Request) -> JSONResponse:
    """List user's assistants + public ones."""
    uid = await _get_user_id(request)
    if async_session is None:
        return JSONResponse([])
    async with async_session() as session:
        if uid:
            res = await session.execute(
                Assistant.__table__.select().where(
                    (Assistant.user_id == uid) | (Assistant.is_public == True)
                ).order_by(Assistant.updated_at.desc())
            )
        else:
            res = await session.execute(
                Assistant.__table__.select().where(Assistant.is_public == True)
                .order_by(Assistant.updated_at.desc())
            )
        rows = res.fetchall()
        return JSONResponse(jsonable_encoder([dict(r._mapping) for r in rows]))


@router.post('/assistants')
async def create_assistant(request: Request, payload: AssistantCreate) -> JSONResponse:
    """Auth + parse, then delegate to services.assistant_service.create_assistant
    -- the ONE place an Assistant row is ever inserted. Same split as
    tasks.py's create_task (see services/assistant_service.py's docstring):
    lets an LLM tool-calling loop create an assistant on a user's behalf
    with an explicit uid, without forging a Request.
    """
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    spec = AssistantSpec(
        name=payload.name, description=payload.description,
        system_prompt=payload.system_prompt, model_id=payload.model_id,
        icon=payload.icon, is_public=payload.is_public,
    )
    result = await _create_assistant_core(uid, spec)
    if result is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    return JSONResponse(result)


@router.get('/assistants/{assistant_id}')
async def get_assistant(assistant_id: int, request: Request) -> JSONResponse:
    # Ownership gate: an assistant is readable only by its owner or, if
    # is_public, by anyone. Without the owner/public filter this endpoint was
    # an IDOR -- ids are sequential ints, so any visitor could walk them and
    # read another user's private system_prompt (session 11 audit A4). PUT and
    # DELETE on the same resource already filter on user_id; GET must match.
    uid = await _get_user_id(request)
    if async_session is None:
        return err('یافت نشد', 'Not found.', 404)
    async with async_session() as session:
        res = await session.execute(
            Assistant.__table__.select().where(
                Assistant.id == assistant_id,
                sqlalchemy.or_(Assistant.is_public == True, Assistant.user_id == uid),  # noqa: E712
            )
        )
        row = res.fetchone()
        if not row:
            return err('یافت نشد', 'Not found.', 404)
        return JSONResponse(jsonable_encoder(dict(row._mapping)))


@router.put('/assistants/{assistant_id}')
async def update_assistant(assistant_id: int, request: Request, payload: dict[str, Any]) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(
            Assistant.__table__.select().where(Assistant.id == assistant_id, Assistant.user_id == uid)
        )
        row = res.fetchone()
        if not row:
            # NOT CONVERTED -- see handoff report. `detail` here is a mixed
            # EN|FA literal, not a clean Persian string, so byte-identical
            # conversion isn't well-defined; flagged for the senior instead
            # of guessing at a split.
            # Was a single string with both languages jammed together either
            # side of a pipe -- the hand-rolled version of what err() does
            # properly. Split at the pipe; the Persian half is unchanged.
            return err(
                'یافت نشد یا متعلق به شما نیست',
                'Not found, or not owned by you.',
                404,
            )
        obj = await session.get(Assistant, assistant_id)
        for field in ('name', 'description', 'system_prompt', 'model_id', 'icon', 'is_public'):
            if field in payload:
                setattr(obj, field, payload[field])
        obj.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await session.commit()
    return JSONResponse({'status': 'ok'})


@router.delete('/assistants/{assistant_id}')
async def delete_assistant(assistant_id: int, request: Request) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(
            Assistant.__table__.select().where(Assistant.id == assistant_id, Assistant.user_id == uid)
        )
        if not res.fetchone():
            return err('یافت نشد', 'Not found.', 404)
        await session.execute(Assistant.__table__.delete().where(Assistant.id == assistant_id))
        await session.commit()
    return JSONResponse({'status': 'ok'})
