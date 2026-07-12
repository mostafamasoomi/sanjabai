"""Claim registry schema — typed, source-backed marketing/product copy.

Every user-facing claim (numbers, uptime, gifts, provider counts) must live here
with provenance metadata so it can be verified, expired, and feature-flag gated.
See docs/claims-policy.md for the governing policy.
"""
from __future__ import annotations

from enum import Enum

from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class ClaimType(str, Enum):
    FACT = "fact"
    ESTIMATE = "estimate"
    MARKETING = "marketing"
    ILLUSTRATIVE = "illustrative"


class Claim(Base):
    __tablename__ = "claims"

    key = Column(String, primary_key=True)
    copy_fa = Column(String)
    copy_en = Column(String)
    claim_type = Column(String)  # fact|estimate|marketing|illustrative
    source = Column(String)
    verified_at = Column(DateTime)
    expires_at = Column(DateTime)
    owner = Column(String)
    audience = Column(String)
    feature_flag = Column(String)
    fallback_copy = Column(String)
