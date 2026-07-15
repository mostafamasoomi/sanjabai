"""
User memory endpoints: CRUD for persistent memory entries.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import async_session
from models import UserMemory
from dependencies import _get_user_id, _escape_like

router = APIRouter()


class MemoryCreate(BaseModel):
    content: str
    category: str = 'general'
    source: str = 'manual'
    tags: list[str] = []


class MemoryUpdate(BaseModel):
    content: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    active: bool | None = None


@router.get('/memories')
async def list_memories(request: Request, category: str | None = None) -> JSONResponse:
    """List active memories for the current user, optionally filtered by category."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        stmt = UserMemory.__table__.select().where(
            UserMemory.user_id == uid,
            UserMemory.active == True,
        )
        if category:
            stmt = stmt.where(UserMemory.category == category)
        stmt = stmt.order_by(UserMemory.created_at.desc())
        res = await session.execute(stmt)
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.get('/memories/search')
async def search_memories(request: Request, q: str = '') -> JSONResponse:
    """Full-text search across memory content for the current user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        if q:
            res = await session.execute(
                UserMemory.__table__.select().where(
                    UserMemory.user_id == uid,
                    UserMemory.active == True,
                    UserMemory.content.ilike(f'%{_escape_like(q)}%'),
                ).order_by(UserMemory.created_at.desc()).limit(50)
            )
        else:
            res = await session.execute(
                UserMemory.__table__.select().where(
                    UserMemory.user_id == uid,
                    UserMemory.active == True,
                ).order_by(UserMemory.created_at.desc()).limit(50)
            )
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/memories')
async def create_memory(request: Request, payload: MemoryCreate) -> JSONResponse:
    """Create a new memory entry for the current user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        mem = UserMemory(
            user_id=uid,
            content=payload.content,
            category=payload.category,
            source=payload.source,
            tags=payload.tags,
        )
        session.add(mem)
        await session.commit()
        await session.refresh(mem)
        return JSONResponse(jsonable_encoder({
            'id': mem.id, 'content': mem.content, 'category': mem.category,
            'source': mem.source, 'tags': mem.tags, 'active': mem.active,
            'created_at': mem.created_at,
        }))


@router.put('/memories/{memory_id}')
async def update_memory(request: Request, memory_id: int, payload: MemoryUpdate) -> JSONResponse:
    """Update an existing memory entry."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            UserMemory.__table__.select().where(
                UserMemory.id == memory_id, UserMemory.user_id == uid
            )
        )
        mem = res.fetchone()
        if not mem:
            return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        update_data = {}
        if payload.content is not None:
            update_data['content'] = payload.content
        if payload.category is not None:
            update_data['category'] = payload.category
        if payload.tags is not None:
            update_data['tags'] = payload.tags
        if payload.active is not None:
            update_data['active'] = payload.active
        if update_data:
            update_data['updated_at'] = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.execute(
                UserMemory.__table__.update().where(UserMemory.id == memory_id),
                update_data,
            )
            await session.commit()
    return JSONResponse({'status': 'ok'})


@router.delete('/memories/{memory_id}')
async def delete_memory(request: Request, memory_id: int) -> JSONResponse:
    """Soft-delete a memory entry (set active=False)."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(
            UserMemory.__table__.select().where(
                UserMemory.id == memory_id, UserMemory.user_id == uid
            )
        )
        mem = res.fetchone()
        if not mem:
            return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        await session.execute(
            UserMemory.__table__.update().where(UserMemory.id == memory_id),
            {'active': False, 'updated_at': datetime.now(timezone.utc).replace(tzinfo=None)},
        )
        await session.commit()
    return JSONResponse({'status': 'deleted'})
