"""Skill-marketplace ORM models: templates, ratings, and per-user activation."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, _utcnow


class SkillTemplate(Base):
    """Skill template for the marketplace."""
    __tablename__ = 'skill_templates'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(sqlalchemy.ForeignKey('users.id'), nullable=True)
    title: Mapped[str]
    title_fa: Mapped[str]
    description: Mapped[str] = mapped_column(default='')
    description_fa: Mapped[str] = mapped_column(default='')
    category: Mapped[str] = mapped_column(default='general')
    prompt_template: Mapped[str]
    variables: Mapped[dict[str, Any] | None] = mapped_column(sqlalchemy.JSON, default=list)
    default_model: Mapped[str] = mapped_column(default='')
    is_public: Mapped[bool] = mapped_column(default=False)
    is_featured: Mapped[bool] = mapped_column(default=False)
    usage_count: Mapped[int] = mapped_column(default=0)
    rating_sum: Mapped[int] = mapped_column(default=0)
    rating_count: Mapped[int] = mapped_column(default=0)
    tags: Mapped[list | None] = mapped_column(sqlalchemy.JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class SkillTemplateRating(Base):
    """Rating for a skill template."""
    __tablename__ = 'skill_template_ratings'
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('skill_templates.id'))
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'))
    rating: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class UserSkillActivation(Base):
    """One user's decision to switch a skill on for their own chats.

    Until this table existed a skill was a *template library* -- POST
    /skills/{id}/use rendered ``prompt_template`` and handed the string back
    to the frontend, and nothing in any of the seven chat modules ever read
    the word ``skill``. A row here is what makes a skill actually reach the
    model, via services/skill_injection.py, on exactly the same footing as a
    memory (see services/context_injection.py).

    The row is the user's explicit act, so injecting it is not us inducing
    tokens the user did not ask for -- it is us honouring a request the user
    made in the panel. Nothing is injected for a user with no rows here.
    """
    __tablename__ = 'user_skill_activations'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    template_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('skill_templates.id'), index=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)
