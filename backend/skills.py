"""
Skills marketplace endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import async_session
from i18n import err
from models import SkillTemplate, SkillTemplateRating, UserSkillActivation
from dependencies import _get_user_id, _escape_like, admin_required
from services.skill_injection import MAX_SKILLS_INJECTED

router = APIRouter()


def _render_skill_prompt(template: str, variables: dict[str, str]) -> str:
    """Substitute skill-template variables into `template`.

    UI-documented form is {{var}} (frontend/app/skills/page.tsx); {var} is a
    legacy single-brace form some existing templates still use. Must
    substitute {{var}} FIRST: since "{{name}}" contains "{name}" as a
    substring, doing the single-brace pass first would leave the outer
    braces stranded (-> "{Bob}" instead of "Bob"). str.replace() is a single
    non-recursive scan, so running the double-brace pass first and then the
    single-brace pass is safe -- text just substituted in (e.g. a value that
    itself contains "{other}") is never rescanned. A variable with no entry
    in `variables` is left as literal text, unchanged (existing behavior).
    """
    rendered = template
    for var_name, var_value in variables.items():
        rendered = rendered.replace('{{' + var_name + '}}', var_value)
    for var_name, var_value in variables.items():
        rendered = rendered.replace('{' + var_name + '}', var_value)
    return rendered


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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
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
        return err('خطای سرور', 'Server error', 500)


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
        return err('خطای سرور', 'Server error', 500)


@router.get('/skills/active')
async def list_active_skills(request: Request) -> JSONResponse:
    """List the current user's skill activations (enabled and disabled),
    ordered by position, for the panel to render toggle state."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.select(
                    SkillTemplate.id,
                    SkillTemplate.title,
                    SkillTemplate.title_fa,
                    UserSkillActivation.position,
                    UserSkillActivation.enabled,
                )
                .select_from(
                    UserSkillActivation.__table__.join(
                        SkillTemplate.__table__,
                        UserSkillActivation.template_id == SkillTemplate.id,
                    )
                )
                .where(UserSkillActivation.user_id == uid)
                .order_by(UserSkillActivation.position, SkillTemplate.id)
            )
            rows = [dict(r._mapping) for r in res.fetchall()]
        return JSONResponse(jsonable_encoder(rows))
    except Exception:
        return err('خطای سرور', 'Server error', 500)


@router.get('/skills/{template_id}')
async def get_skill_template(request: Request, template_id: int) -> JSONResponse:
    """Get a single skill template by ID."""
    try:
        if async_session is None:
            return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
            )
            row = res.fetchone()
        if not row:
            return err('یافت نشد', 'Not found', 404)
        data = dict(row._mapping)
        if not data.get('is_public'):
            uid = await _get_user_id(request)
            if not uid or (data.get('user_id') != uid and not await admin_required(request)):
                return err('یافت نشد', 'Not found', 404)
        return JSONResponse(jsonable_encoder(data))
    except Exception:
        return err('خطای سرور', 'Server error', 500)


@router.post('/skills')
async def create_skill_template(request: Request, payload: SkillTemplateCreate) -> JSONResponse:
    """Create a new skill template."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    try:
        if async_session is None:
            return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
            )
            row = res.fetchone()
            if not row:
                return err('یافت نشد', 'Not found', 404)
            if row.user_id != uid:
                return err('دسترسی غیرمجاز', 'Access denied', 403)
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
        return err('خطای سرور', 'Server error', 500)


@router.delete('/skills/{template_id}')
async def delete_skill_template(request: Request, template_id: int) -> JSONResponse:
    """Delete a skill template (owner only)."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    try:
        if async_session is None:
            return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
            )
            row = res.fetchone()
            if not row:
                return err('یافت نشد', 'Not found', 404)
            if row.user_id != uid:
                return err('دسترسی غیرمجاز', 'Access denied', 403)
            await session.execute(
                SkillTemplate.__table__.delete().where(SkillTemplate.id == template_id)
            )
            await session.commit()
        return JSONResponse({'status': 'deleted'})
    except Exception:
        return err('خطای سرور', 'Server error', 500)
@router.post('/skills/{template_id}/activate')
async def activate_skill(request: Request, template_id: int) -> JSONResponse:
    """Switch a skill on for the current user's own chats (idempotent).

    404 if the template does not exist or is neither owned by the user
    nor public. Enforces the MAX_SKILLS_INJECTED cap: at most that many
    skills may be enabled for a user at once.
    """
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
    try:
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
            )
            tmpl = res.fetchone()
            if not tmpl or (tmpl.user_id != uid and not tmpl.is_public):
                return err('یافت نشد', 'Not found', 404)

            count_res = await session.execute(
                sqlalchemy.select(sqlalchemy.func.count()).select_from(
                    UserSkillActivation.__table__
                ).where(
                    UserSkillActivation.user_id == uid,
                    UserSkillActivation.enabled == True,  # noqa: E712
                    UserSkillActivation.template_id != template_id,
                )
            )
            enabled_count = count_res.scalar_one()
            if enabled_count >= MAX_SKILLS_INJECTED:
                return err(
                    f'حداکثر {MAX_SKILLS_INJECTED} مهارت را می‌توان همزمان فعال کرد',
                    f'At most {MAX_SKILLS_INJECTED} skills can be active at the same time',
                    400,
                )

            await session.execute(
                sqlalchemy.text(
                    """
                    INSERT INTO user_skill_activations
                        (user_id, template_id, enabled, position, created_at, updated_at)
                    VALUES (
                        :uid, :tid, TRUE,
                        COALESCE(
                            (SELECT MAX(position) + 1 FROM user_skill_activations WHERE user_id = :uid),
                            0
                        ),
                        now(), now()
                    )
                    ON CONFLICT (user_id, template_id) DO UPDATE SET
                        enabled = TRUE, updated_at = now()
                    """
                ),
                {'uid': uid, 'tid': template_id},
            )
            await session.commit()
        return JSONResponse({'status': 'ok'})
    except Exception:
        return err('خطای سرور', 'Server error', 500)


@router.delete('/skills/{template_id}/activate')
async def deactivate_skill(request: Request, template_id: int) -> JSONResponse:
    """Switch a skill off for the current user. The row is kept (enabled
    set to FALSE) so its position survives a toggle round-trip."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
    try:
        async with async_session() as session:
            res = await session.execute(
                UserSkillActivation.__table__.select().where(
                    UserSkillActivation.user_id == uid,
                    UserSkillActivation.template_id == template_id,
                )
            )
            row = res.fetchone()
            if not row:
                return err('این مهارت برای شما فعال نشده است', 'This skill is not enabled for you', 404)
            await session.execute(
                UserSkillActivation.__table__.update().where(
                    UserSkillActivation.user_id == uid,
                    UserSkillActivation.template_id == template_id,
                ),
                {'enabled': False, 'updated_at': datetime.now(timezone.utc).replace(tzinfo=None)},
            )
            await session.commit()
        return JSONResponse({'status': 'ok'})
    except Exception:
        return err('خطای سرور', 'Server error', 500)


@router.post('/skills/{template_id}/rate')
async def rate_skill_template(request: Request, template_id: int, payload: SkillRatingRequest) -> JSONResponse:
    """Rate a skill template (1-5)."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account', 401)
    if payload.rating < 1 or payload.rating > 5:
        return err('امتیاز باید بین ۱ تا ۵ باشد', 'Rating must be between 1 and 5', 400)
    try:
        if async_session is None:
            return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
            )
            if not res.fetchone():
                return err('یافت نشد', 'Not found', 404)
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
        return err('خطای سرور', 'Server error', 500)


@router.post('/skills/{template_id}/use')
async def use_skill_template(request: Request, template_id: int, payload: SkillUseRequest) -> JSONResponse:
    """Use a skill template: increment usage count and return rendered prompt."""
    try:
        if async_session is None:
            return err('پایگاه داده در دسترس نیست', 'Database is unavailable', 500)
        async with async_session() as session:
            res = await session.execute(
                SkillTemplate.__table__.select().where(SkillTemplate.id == template_id)
            )
            row = res.fetchone()
            if not row:
                return err('یافت نشد', 'Not found', 404)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.execute(
                SkillTemplate.__table__.update().where(SkillTemplate.id == template_id),
                {'usage_count': SkillTemplate.usage_count + 1, 'updated_at': now},
            )
            await session.commit()
            rendered = _render_skill_prompt(row.prompt_template, payload.variables)
            model = payload.model or row.default_model or ''
        return JSONResponse(jsonable_encoder({
            'rendered_prompt': rendered,
            'model': model,
        }))
    except Exception:
        return err('خطای سرور', 'Server error', 500)
