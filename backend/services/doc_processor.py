"""
Document processor for RAG — extracts text, chunks, generates embeddings.

Handles: PDF (pymupdf), plain text (.txt, .md), CSV.
Background processing with status tracking.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any

import sqlalchemy
from sqlalchemy import select

from database import async_session
from models import RagDocument, RagChunk
from services.chunking import chunk_text, estimate_tokens
from services.embeddings import embed_texts

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
MAX_DOCUMENTS_PER_USER = 50
MAX_CHUNKS_PER_USER = 1000
SUPPORTED_TYPES = {'pdf', 'txt', 'md', 'csv', 'json'}


def _extract_text(content: bytes, filename: str) -> str:
    """Extract text from file content."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    if ext == 'pdf':
        return _extract_pdf(content)
    elif ext in ('txt', 'md', 'csv', 'json'):
        return content.decode('utf-8', errors='replace')
    else:
        raise ValueError(f'Unsupported file type: {ext}')


def _extract_pdf(content: bytes) -> str:
    """Extract text from PDF using pymupdf."""
    try:
        import pymupdf  # fitz
        doc = pymupdf.open(stream=content, filetype='pdf')
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return '\n\n'.join(text_parts)
    except ImportError:
        # Fallback: try pypdf (already in requirements)
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(content))
            text_parts = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
            return '\n\n'.join(text_parts)
        except Exception as e:
            raise RuntimeError(f'PDF extraction failed (install pymupdf): {e}')


async def _check_dedup(user_id: int, content_hash: str) -> str | None:
    """Check if user already has a document with same content hash."""
    if async_session is None:
        return None
    async with async_session() as session:
        res = await session.execute(
            select(RagDocument.id).where(
                RagDocument.user_id == user_id,
                RagDocument.content_hash == content_hash,
                RagDocument.status != 'deleted',
            ).limit(1)
        )
        row = res.fetchone()
        return str(row[0]) if row else None


async def _check_limits(user_id: int) -> None:
    """Check user hasn't exceeded document/chunk limits."""
    if async_session is None:
        return
    async with async_session() as session:
        # Document count
        res = await session.execute(
            sqlalchemy.text(
                "SELECT COUNT(*) FROM rag_documents WHERE user_id = :uid AND status != 'deleted'"
            ),
            {'uid': user_id},
        )
        doc_count = res.scalar()
        if doc_count and doc_count >= MAX_DOCUMENTS_PER_USER:
            raise ValueError(f'حداکثر {MAX_DOCUMENTS_PER_USER} سند مجاز است')

        # Chunk count
        res = await session.execute(
            sqlalchemy.text(
                "SELECT COALESCE(SUM(chunk_count), 0) FROM rag_documents WHERE user_id = :uid AND status = 'indexed'"
            ),
            {'uid': user_id},
        )
        chunk_count = res.scalar()
        if chunk_count and chunk_count >= MAX_CHUNKS_PER_USER:
            raise ValueError(f'حداکثر {MAX_CHUNKS_PER_USER} بخش مجاز است')


async def process_document(
    user_id: int,
    file_content: bytes,
    filename: str,
    idempotency_key: str | None = None,
) -> dict:
    """Process a document: extract text, chunk, embed, store.

    Returns dict with document_id, status, chunk_count.
    """
    # Validate size
    if len(file_content) > MAX_FILE_SIZE:
        raise ValueError(f'حجم فایل از {MAX_FILE_SIZE // (1024*1024)} مگابایت بیشتر است')

    # Check limits
    await _check_limits(user_id)

    # Extract text
    try:
        text = _extract_text(file_content, filename)
    except Exception as e:
        raise ValueError(f'خطا در استخراج متن: {e}')

    if not text or len(text.strip()) < 10:
        raise ValueError('فایل خالی است یا متن قابل استخراج نیست')

    content_hash = hashlib.sha256(text.encode()).hexdigest()

    # Check dedup
    existing_id = await _check_dedup(user_id, content_hash)
    if existing_id:
        return {'document_id': existing_id, 'status': 'duplicate', 'message': 'این سند قبلاً بارگذاری شده'}

    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    idempotency_key = idempotency_key or f'rag-{user_id}-{content_hash[:16]}-{secrets.token_hex(4)}'

    # Create document record
    if async_session is None:
        raise RuntimeError('Database not available')

    async with async_session() as session:
        doc = RagDocument(
            user_id=user_id,
            title=filename,
            file_name=filename,
            file_type=ext,
            file_size=len(file_content),
            source='upload',
            status='processing',
            content_hash=content_hash,
            idempotency_key=idempotency_key,
        )
        session.add(doc)
        await session.flush()
        doc_id = doc.id
        await session.commit()

    # Process in background (but for simplicity, do inline with status tracking)
    try:
        # Chunk
        chunks = chunk_text(text)
        if not chunks:
            await _update_status(doc_id, 'error', 'متن قابل تقسیم نیست')
            return {'document_id': doc_id, 'status': 'error', 'message': 'متن قابل تقسیم نیست'}

        # Generate embeddings
        texts = [c['content'] for c in chunks]
        embeddings = await embed_texts(texts, user_id, doc_id)

        # Store chunks
        async with async_session() as session:
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                rag_chunk = RagChunk(
                    document_id=doc_id,
                    user_id=user_id,
                    chunk_index=i,
                    content=chunk['content'],
                    token_count=chunk['token_estimate'],
                    embedding=embedding,
                    embedding_model='text-embedding-3-small',
                )
                session.add(rag_chunk)

            # Update document status
            await session.execute(
                sqlalchemy.text("""
                    UPDATE rag_documents
                    SET status = 'indexed', chunk_count = :cc, total_chars = :tc, updated_at = now()
                    WHERE id = :did
                """),
                {'cc': len(chunks), 'tc': len(text), 'did': doc_id},
            )
            await session.commit()

        return {
            'document_id': doc_id,
            'status': 'indexed',
            'chunk_count': len(chunks),
            'total_chars': len(text),
        }

    except Exception as e:
        logger.error(f'Document processing failed doc_id={doc_id}: {e}')
        await _update_status(doc_id, 'error', str(e)[:500])
        return {'document_id': doc_id, 'status': 'error', 'message': str(e)[:200]}


async def _update_status(doc_id: int, status: str, error: str | None = None) -> None:
    """Update document status."""
    if async_session is None:
        return
    try:
        async with async_session() as session:
            await session.execute(
                sqlalchemy.text("""
                    UPDATE rag_documents
                    SET status = :status, error_message = :err, updated_at = now()
                    WHERE id = :did
                """),
                {'status': status, 'err': error, 'did': doc_id},
            )
            await session.commit()
    except Exception as e:
        logger.warning(f'Failed to update doc status: {e}')
