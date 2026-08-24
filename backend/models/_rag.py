"""RAG ORM models: uploaded documents, their chunks + embeddings, and
embedding-usage billing records.
"""
from __future__ import annotations

from datetime import datetime

import sqlalchemy
from sqlalchemy.orm import Mapped, mapped_column

from ._base import Base, Vector, _HAS_PGVECTOR, _utcnow


class RagDocument(Base):
    __tablename__ = 'rag_documents'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    title: Mapped[str]
    file_name: Mapped[str | None] = mapped_column(nullable=True)
    file_type: Mapped[str | None] = mapped_column(nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(default='upload')
    source_url: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default='pending')
    error_message: Mapped[str | None] = mapped_column(nullable=True)
    chunk_count: Mapped[int] = mapped_column(default=0)
    total_chars: Mapped[int] = mapped_column(default=0)
    content_hash: Mapped[str | None] = mapped_column(nullable=True)
    meta: Mapped[dict | None] = mapped_column('metadata', sqlalchemy.JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)


class RagChunk(Base):
    __tablename__ = 'rag_chunks'
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('rag_documents.id'))
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'))
    chunk_index: Mapped[int]
    content: Mapped[str]
    token_count: Mapped[int] = mapped_column(default=0)
    embedding = mapped_column(Vector(1536) if _HAS_PGVECTOR else sqlalchemy.JSON, nullable=True)
    embedding_model: Mapped[str] = mapped_column(default='text-embedding-3-small')
    doc_metadata: Mapped[dict | None] = mapped_column('metadata', sqlalchemy.JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class RagEmbeddingUsage(Base):
    __tablename__ = 'rag_embedding_usage'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'))
    document_id: Mapped[int | None] = mapped_column(nullable=True)
    operation: Mapped[str]
    tokens_used: Mapped[int] = mapped_column(default=0)
    charged_amount: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(default='IRT')
    request_id: Mapped[str] = mapped_column(unique=True)
    model: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
