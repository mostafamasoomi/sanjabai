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
from dependencies import _get_user_id

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
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        obj = Assistant(
            user_id=uid, name=payload.name, description=payload.description,
            system_prompt=payload.system_prompt, model_id=payload.model_id,
            icon=payload.icon, is_public=payload.is_public,
        )
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
    return JSONResponse({'status': 'ok', 'id': obj.id})


@router.get('/assistants/{assistant_id}')
async def get_assistant(assistant_id: int, request: Request) -> JSONResponse:
    if async_session is None:
        return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
    async with async_session() as session:
        res = await session.execute(
            Assistant.__table__.select().where(Assistant.id == assistant_id)
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        return JSONResponse(jsonable_encoder(dict(row._mapping)))


@router.put('/assistants/{assistant_id}')
async def update_assistant(assistant_id: int, request: Request, payload: dict[str, Any]) -> JSONResponse:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            Assistant.__table__.select().where(Assistant.id == assistant_id, Assistant.user_id == uid)
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'not found or not owned | یافت نشد یا متعلق به شما نیست'}, status_code=404)
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
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            Assistant.__table__.select().where(Assistant.id == assistant_id, Assistant.user_id == uid)
        )
        if not res.fetchone():
            return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        await session.execute(Assistant.__table__.delete().where(Assistant.id == assistant_id))
        await session.commit()
    return JSONResponse({'status': 'ok'})
