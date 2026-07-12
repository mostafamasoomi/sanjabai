from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


_STABLE_ID = re.compile(r"^[a-z0-9]+(?:[._\-/][a-z0-9]+)*$")


class Availability(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"
    DISABLED = "disabled"


class CatalogPricing(BaseModel):
    currency: Literal["IRR", "IRT"]
    input_per_million: Decimal = Field(ge=0)
    output_per_million: Decimal = Field(ge=0)
    cached_input_per_million: Decimal | None = Field(default=None, ge=0)
    reasoning_per_million: Decimal | None = Field(default=None, ge=0)
    price_version: str = Field(min_length=1, max_length=100)
    effective_from: datetime


class ModelCatalogItem(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    provider_model_id: str = Field(min_length=1, max_length=300)
    provider: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    modalities: dict[str, list[str]]
    capabilities: list[str] = Field(default_factory=list)
    recommended_for: list[str] = Field(default_factory=list)
    context_window: int = Field(gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    pricing: CatalogPricing
    availability: Availability
    audience: list[Literal["consumer", "developer", "team"]]
    rate_limit: dict[str, int] | None = None
    deprecated_at: datetime | None = None
    last_verified_at: datetime
    provenance: Literal["provider", "admin-approved", "fallback"]

    @field_validator("modalities")
    @classmethod
    def validate_modalities(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if set(value) - {"input", "output"}:
            raise ValueError("modalities may only contain input and output")
        if not value.get("input") or not value.get("output"):
            raise ValueError("input and output modalities are required")
        return value

    @field_validator("rate_limit")
    @classmethod
    def validate_rate_limit(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value and any(number <= 0 for number in value.values()):
            raise ValueError("rate limits must be positive")
        return value

    @field_validator("id")
    @classmethod
    def validate_stable_id(cls, value: str) -> str:
        if not _STABLE_ID.match(value):
            raise ValueError(
                "id must be a stable slug (lowercase alphanumerics separated by . _ - /)"
            )
        return value

    @model_validator(mode="after")
    def validate_effective_dates(self) -> "ModelCatalogItem":
        if self.deprecated_at is not None and self.deprecated_at < self.pricing.effective_from:
            raise ValueError("deprecated_at cannot precede pricing.effective_from")
        return self


class CatalogResponse(BaseModel):
    data: list[ModelCatalogItem]
    generated_at: datetime
    source: Literal["approved-catalog"] = "approved-catalog"
