"""
Skills marketplace endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import async_session
from models import SkillTemplate, SkillTemplateRating
from dependencies import _get_user_id, _escape_like, admin_required

router = APIRouter()


class SkillTemplateCreate(BaseModel):
    title: str
    title_fa: str
    description: str = ''
    description_fa: str = ''
    category: str = 'general'
    prompt_template: str
    variables: list[dict[str, Any]] = []
    default_model: str = ''
    is_public: bool = False
    tags: list[str] = []


class SkillTemplateUpdate(BaseModel):
    title: str | None = None
    title_fa: str | None = None
    description: str | None = None
    description_fa: str | None = None
    category: str | None = None
    prompt_template: str | None = None
    variables: list[dict[str, Any]] | None = None
    default_model: str | None = None
    is_public: bool | None = None
    tags: list[str] | None = None


class SkillUseRequest(BaseModel):
    variables: dict[str, str] = {}
    model: str = ''


class SkillRatingRequest(BaseModel):
    rating: int


@router.get('/skills/my')
async def list_my_skill_templates(request: Request) -> JSONResponse:
    """List skill templates owned by the current user."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    try:
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(
                    SkillTemplate.user_id == uid,
                ).order_by(SkillTemplate.created_at.desc())
            )
            rows = [dict(r._mapping) for r in res.fetchall()]
        return JSONResponse(jsonable_encoder(rows))
    except Exception:
        return JSONResponse({'detail': 'خطای سرور'}, status_code=500)


@router.get('/skills')
async def list_skill_templates(
    request: Request,
    category: str | None = None,
    featured: bool | None = None,
    sort: str = 'popular',
    q: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> JSONResponse:
    """List public skill templates with optional filtering and sorting."""
    try:
        async with async_session() as session:
            stmt = SkillTemplate.__table__.select().where(SkillTemplate.is_public == True)
            if category:
                stmt = stmt.where(SkillTemplate.category == category)
            if featured is not None:
                stmt = stmt.where(SkillTemplate.is_featured == featured)
            if q:
                stmt = stmt.where(
                    SkillTemplate.title.ilike(f'%{_escape_like(q)}%') |
                    SkillTemplate.title_fa.ilike(f'%{_escape_like(q)}%') |
                    SkillTemplate.description.ilike(f'%{_escape_like(q)}%') |
                    SkillTemplate.description_fa.ilike(f'%{_escape_like(q)}%')
                )
            if sort == 'newest':
                stmt = stmt.order_by(SkillTemplate.created_at.desc())
            elif sort == 'top_rated':
                stmt = stmt.order_by(
                    SkillTemplate.rating_sum.desc().nullslast(),
                    SkillTemplate.rating_count.desc(),
                )
            else:
                stmt = stmt.order_by(SkillTemplate.usage_count.desc())
            stmt = stmt.offset(skip).limit(min(limit, 100))
            res = await session.execute(stmt)
            rows = [dict(r._mapping) for r in res.fetchall()]
        return JSONResponse(jsonable_encoder(rows))
    except Exception:
        return JSONResponse({'detail': 'خطای سرور'}, status_code=500)


@router.get('/skills/{template_id}')
async def get_skill_template(request: Request, template_id: int) -> JSONResponse:
    """Get a single skill template by ID."""
    try:
        if async_session is None:
            return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
            )
            row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        data = dict(row._mapping)
        if not data.get('is_public'):
            uid = await _get_user_id(request)
            if not uid or (data.get('user_id') != uid and not await admin_required(request)):
                return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
        return JSONResponse(jsonable_encoder(data))
    except Exception:
        return JSONResponse({'detail': 'خطای سرور'}, status_code=500)


@router.post('/skills')
async def create_skill_template(request: Request, payload: SkillTemplateCreate) -> JSONResponse:
    """Create a new skill template."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        tmpl = SkillTemplate(
            user_id=uid,
            title=payload.title,
            title_fa=payload.title_fa,
            description=payload.description,
            description_fa=payload.description_fa,
            category=payload.category,
            prompt_template=payload.prompt_template,
            variables=payload.variables,
            default_model=payload.default_model,
            is_public=payload.is_public,
            tags=payload.tags,
        )
        session.add(tmpl)
        await session.commit()
        await session.refresh(tmpl)
        return JSONResponse(jsonable_encoder({
            'id': tmpl.id, 'title': tmpl.title, 'title_fa': tmpl.title_fa,
            'description': tmpl.description, 'description_fa': tmpl.description_fa,
            'category': tmpl.category, 'prompt_template': tmpl.prompt_template,
            'variables': tmpl.variables, 'default_model': tmpl.default_model,
            'is_public': tmpl.is_public, 'is_featured': tmpl.is_featured,
            'usage_count': tmpl.usage_count, 'rating_sum': tmpl.rating_sum,
            'rating_count': tmpl.rating_count, 'tags': tmpl.tags,
            'created_at': tmpl.created_at, 'updated_at': tmpl.updated_at,
        }))


@router.put('/skills/{template_id}')
async def update_skill_template(request: Request, template_id: int, payload: SkillTemplateUpdate) -> JSONResponse:
    """Update a skill template (owner only)."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    try:
        if async_session is None:
            return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
            )
            row = res.fetchone()
            if not row:
                return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
            if row.user_id != uid:
                return JSONResponse({'detail': 'دسترسی غیرمجاز'}, status_code=403)
            update_data = {}
            for field in ['title', 'title_fa', 'description', 'description_fa', 'category',
                           'prompt_template', 'variables', 'default_model', 'is_public', 'tags']:
                val = getattr(payload, field, None)
                if val is not None:
                    update_data[field] = val
            if update_data:
                update_data['updated_at'] = datetime.now(timezone.utc).replace(tzinfo=None)
                await session.execute(
                    SkillTemplate.__table__.update().where(SkillTemplate.id == template_id),
                    update_data,
                )
                await session.commit()
        return JSONResponse({'status': 'ok'})
    except Exception:
        return JSONResponse({'detail': 'خطای سرور'}, status_code=500)


@router.delete('/skills/{template_id}')
async def delete_skill_template(request: Request, template_id: int) -> JSONResponse:
    """Delete a skill template (owner only)."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    try:
        if async_session is None:
            return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
            )
            row = res.fetchone()
            if not row:
                return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
            if row.user_id != uid:
                return JSONResponse({'detail': 'دسترسی غیرمجاز'}, status_code=403)
            await session.execute(
                SkillTemplate.__table__.delete().where(SkillTemplate.id == template_id)
            )
            await session.commit()
        return JSONResponse({'status': 'deleted'})
    except Exception:
        return JSONResponse({'detail': 'خطای سرور'}, status_code=500)


@router.post('/skills/{template_id}/rate')
async def rate_skill_template(request: Request, template_id: int, payload: SkillRatingRequest) -> JSONResponse:
    """Rate a skill template (1-5)."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if payload.rating < 1 or payload.rating > 5:
        return JSONResponse({'detail': 'امتیاز باید بین ۱ تا ۵ باشد'}, status_code=400)
    try:
        if async_session is None:
            return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
            )
            if not res.fetchone():
                return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
            existing = await session.execute(
                SkillTemplateRating.__table__.select().where(
                    SkillTemplateRating.template_id == template_id,
                    SkillTemplateRating.user_id == uid,
                )
            )
            old_rating = existing.fetchone()
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if old_rating:
                old_val = old_rating.rating
                await session.execute(
                    SkillTemplateRating.__table__.update().where(
                        SkillTemplateRating.template_id == template_id,
                        SkillTemplateRating.user_id == uid,
                    ),
                    {'rating': payload.rating, 'created_at': now},
                )
                await session.execute(
                    SkillTemplate.__table__.update().where(SkillTemplate.id == template_id),
                    {
                        'rating_sum': SkillTemplate.rating_sum - old_val + payload.rating,
                        'updated_at': now,
                    },
                )
            else:
                session.add(SkillTemplateRating(
                    template_id=template_id,
                    user_id=uid,
                    rating=payload.rating,
                ))
                await session.execute(
                    SkillTemplate.__table__.update().where(SkillTemplate.id == template_id),
                    {
                        'rating_sum': SkillTemplate.rating_sum + payload.rating,
                        'rating_count': SkillTemplate.rating_count + 1,
                        'updated_at': now,
                    },
                )
            await session.commit()
        return JSONResponse({'status': 'ok'})
    except Exception:
        return JSONResponse({'detail': 'خطای سرور'}, status_code=500)


@router.post('/skills/{template_id}/use')
async def use_skill_template(request: Request, template_id: int, payload: SkillUseRequest) -> JSONResponse:
    """Use a skill template: increment usage count and return rendered prompt."""
    try:
        if async_session is None:
            return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
            )
            row = res.fetchone()
            if not row:
                return JSONResponse({'detail': 'یافت نشد'}, status_code=404)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.execute(
                SkillTemplate.__table__.update().where(SkillTemplate.id == template_id),
                {'usage_count': SkillTemplate.usage_count + 1, 'updated_at': now},
            )
            await session.commit()
            rendered = row.prompt_template
            for var_name, var_value in payload.variables.items():
                rendered = rendered.replace('{' + var_name + '}', var_value)
            model = payload.model or row.default_model or ''
        return JSONResponse(jsonable_encoder({
            'rendered_prompt': rendered,
            'model': model,
        }))
    except Exception:
        return JSONResponse({'detail': 'خطای سرور'}, status_code=500)
