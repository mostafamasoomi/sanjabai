"""
RAG (Document Search) API endpoints.

POST /v1/rag/upload   — Upload document for indexing
POST /v1/rag/query    — Query documents with RAG
GET  /v1/rag/documents — List user's documents
DELETE /v1/rag/documents/{id} — Soft-delete document
GET  /v1/rag/documents/{id}/status — Poll indexing status
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from i18n import err
from database import async_session
from models import RagDocument
from dependencies import _get_user_id
from services.doc_processor import process_document, DocProcessorError, SUPPORTED_TYPES, MAX_FILE_SIZE
from services.rag import query_documents

logger = logging.getLogger(__name__)

# Characters that could enable path traversal or null-byte tricks in a stored filename.
_UNSAFE_FILENAME_CHARS = re.compile(r'[\x00-\x1f/\\:*?"<>|]')


def sanitize_filename(filename: str) -> str:
    """Strip path components and control chars so a filename can never traverse.

    We never use the client-supplied name to build a filesystem path (content is
    kept in memory / DB), but the name is reflected back to the user and stored,
    so we normalize it to a safe basename with no directory components.
    """
    if not filename:
        return 'unknown'
    # Take only the final path component (defeats ../, C:\..., etc.)
    base = os.path.basename(filename.strip())
    # Remove null bytes and path/control/dangerous characters
    base = _UNSAFE_FILENAME_CHARS.sub('_', base)
    # Collapse leading dots (defeats hidden-file / traversal tricks)
    base = base.lstrip('.')
    if not base:
        return 'unknown'
    # Bound length to avoid oversized metadata
    return base[:255]

router = APIRouter()

# ── Pydantic models ───────────────────────────────────────────────────────────


class RagQueryRequest(BaseModel):
    question: str
    document_id: int | None = None
    model: str = 'mimo-v2.5'
    top_k: int = 5  # number of source chunks to send to the LLM


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post('/v1/rag/upload')
async def rag_upload(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    """Upload a document for RAG indexing."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)

    # CSRF defense-in-depth for cookie-authenticated mutations: require a custom
    # header that cross-origin form submissions cannot set. API-key (Bearer) auth
    # is exempt because it is not vulnerable to browser CSRF.
    if request.cookies.get('session') and not request.headers.get('x-requested-with'):
        return err(
            'هدر X-Requested-With ارسال نشده (محافظت CSRF)',
            'Missing X-Requested-With header (CSRF protection).',
            403,
        )

    # Validate file type (operate on a sanitized basename — never a path)
    raw_filename = file.filename or 'unknown'
    filename = sanitize_filename(raw_filename)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in SUPPORTED_TYPES:
        return err(
            f'فرمت فایل پشتیبانی نمی‌شود. فرمت‌های مجاز: {", ".join(SUPPORTED_TYPES)}',
            f'Unsupported file format. Allowed formats: {", ".join(SUPPORTED_TYPES)}',
            400,
        )

    # Read content
    try:
        content = await file.read()
    except Exception:
        logger.warning(f'RAG upload file read failed uid={uid}')
        return err('خطا در خواندن فایل', 'Error reading the file.', 400)

    if len(content) > MAX_FILE_SIZE:
        return err(
            f'حجم فایل از {MAX_FILE_SIZE // (1024*1024)} مگابایت بیشتر است',
            f'File size exceeds {MAX_FILE_SIZE // (1024*1024)} MB.',
            400,
        )

    if len(content) == 0:
        return err('فایل خالی است', 'The file is empty.', 400)

    # Process document
    try:
        result = await process_document(
            user_id=uid,
            file_content=content,
            filename=filename,
        )
    except DocProcessorError as e:
        return err(e.fa, e.en, 400)
    except Exception as e:
        logger.error(f'RAG upload failed uid={uid}: {e}')
        return err('خطا در پردازش سند', 'Error processing the document.', 500)

    return JSONResponse({
        'document_id': result['document_id'],
        'filename': filename,
        'chunks': result.get('chunk_count', 0),
        'status': result['status'],
        'message': result.get('message', ''),
    })


@router.post('/v1/rag/query')
async def rag_query(request: Request, payload: RagQueryRequest) -> JSONResponse:
    """Query documents using RAG."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)

    if not payload.question or not payload.question.strip():
        return err('لطفاً سوال خود را وارد کنید', 'Please enter your question.', 400)

    if len(payload.question) > 2000:
        return err('سوال نباید بیشتر از ۲۰۰۰ کاراکتر باشد', 'The question must not exceed 2000 characters.', 400)

    try:
        result = await query_documents(
            user_id=uid,
            question=payload.question,
            document_id=payload.document_id,
            top_k=payload.top_k,
            model=payload.model,
        )
    except Exception as e:
        logger.error(f'RAG query failed uid={uid}: {e}')
        return err('خطا در جستجوی اسناد', 'Error searching the documents.', 500)

    return JSONResponse(result)


@router.get('/v1/rag/documents')
async def rag_list_documents(request: Request) -> JSONResponse:
    """List user's RAG documents."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)

    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text("""
                SELECT id, title, file_name, file_type, file_size, status,
                       chunk_count, total_chars, error_message, created_at
                FROM rag_documents
                WHERE user_id = :uid AND status != 'deleted'
                ORDER BY created_at DESC
            """),
            {'uid': uid},
        )
        rows = res.fetchall()

    documents = []
    for r in rows:
        documents.append({
            'id': r._mapping['id'],
            'title': r._mapping['title'],
            'file_name': r._mapping['file_name'],
            'file_type': r._mapping['file_type'],
            'file_size': r._mapping['file_size'],
            'status': r._mapping['status'],
            'chunk_count': r._mapping['chunk_count'],
            'total_chars': r._mapping['total_chars'],
            'error_message': r._mapping['error_message'],
            'created_at': r._mapping['created_at'].isoformat() if r._mapping['created_at'] else None,
        })

    return JSONResponse({'documents': documents})


@router.delete('/v1/rag/documents/{document_id}')
async def rag_delete_document(request: Request, document_id: int) -> JSONResponse:
    """Soft-delete a RAG document."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)

    # CSRF defense-in-depth for cookie-authenticated mutations (see upload handler)
    if request.cookies.get('session') and not request.headers.get('x-requested-with'):
        return err(
            'هدر X-Requested-With ارسال نشده (محافظت CSRF)',
            'Missing X-Requested-With header (CSRF protection).',
            403,
        )

    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text("""
                UPDATE rag_documents
                SET status = 'deleted', updated_at = now()
                WHERE id = :did AND user_id = :uid AND status != 'deleted'
                RETURNING id
            """),
            {'did': document_id, 'uid': uid},
        )
        row = res.fetchone()
        await session.commit()

    if not row:
        return err('سند پیدا نشد', 'Document not found.', 404)

    return JSONResponse({'deleted': True})


@router.get('/v1/rag/documents/{document_id}/status')
async def rag_document_status(request: Request, document_id: int) -> JSONResponse:
    """Poll document indexing status."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)

    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database is unavailable.', 500)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text("""
                SELECT status, chunk_count, error_message
                FROM rag_documents
                WHERE id = :did AND user_id = :uid
            """),
            {'did': document_id, 'uid': uid},
        )
        row = res.fetchone()

    if not row:
        return err('سند پیدا نشد', 'Document not found.', 404)

    return JSONResponse({
        'status': row._mapping['status'],
        'chunk_count': row._mapping['chunk_count'],
        'error_message': row._mapping['error_message'],
    })
