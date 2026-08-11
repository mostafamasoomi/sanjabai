"""


Admin panel content: features, discounts, about, proxy config, org default model.
from fastapi.responses import HTMLResponse
"""
from __future__ import annotations

from fastapi.responses import HTMLResponse
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request

from admin_config import (
    templates, UI, async_session, _redirect_or_html, _require_api_session,
    _json_response, _fetch_all, _fetch_one, _execute
)

router = APIRouter()


# ===== Server-rendered pages ===============================================

@router.get('/admin/discounts', response_class=HTMLResponse)
async def discounts_page(request: Request):
    return _redirect_or_html(request, 'discounts.html', {})


@router.get('/admin/features', response_class=HTMLResponse)
async def features_page(request: Request):
    return _redirect_or_html(request, 'features.html', {})


@router.get('/admin/settings', response_class=HTMLResponse)
async def settings_page(request: Request):
    return _redirect_or_html(request, 'settings.html', {})


@router.get('/admin/about', response_class=HTMLResponse)
async def about_page(request: Request):
    return _redirect_or_html(request, 'about.html', {})


# ===== API endpoints (JSON) ================================================

# --- Features ---

@router.get('/admin/api/features')
async def api_features(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, title, description, icon, active, order_idx, updated_at FROM features ORDER BY order_idx')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.post('/admin/api/features')
async def api_features_create(request: Request):
    _require_api_session(request)
    body = await request.json()
    fid = body.get('id')
    title = body.get('title', '')
    description = body.get('description', '')
    icon = body.get('icon', '')
    active = body.get('active', True)
    order_idx = body.get('order_idx', 0)

    if not title:
        return _json_response({'error': 'title is required'}, 400)

    try:
        async with async_session() as session:
            async with session.begin():
                if fid:
                    await _execute(session,
                        'UPDATE features SET title = :t, description = :d, icon = :i, active = :a, order_idx = :o, updated_at = :c WHERE id = :id',
                        {'t': title, 'd': description, 'i': icon, 'a': active, 'o': order_idx, 'c': datetime.utcnow(), 'id': fid})
                else:
                    await _execute(session,
                        'INSERT INTO features (title, description, icon, active, order_idx, updated_at) VALUES (:t, :d, :i, :a, :o, :c)',
                        {'t': title, 'd': description, 'i': icon, 'a': active, 'o': order_idx, 'c': datetime.utcnow()})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.delete('/admin/api/features/{feature_id}')
async def api_features_delete(request: Request, feature_id: int):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                await _execute(session, 'DELETE FROM features WHERE id = :id', {'id': feature_id})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- Discounts ---

@router.get('/admin/api/discounts')
async def api_discounts(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, code, percent, active, expires_at, updated_at '
                    'FROM discounts ORDER BY id')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.post('/admin/api/discounts')
async def api_discounts_create(request: Request):
    _require_api_session(request)
    body = await request.json()
    did = body.get('id')
    code = body.get('code', '')
    percent = body.get('percent', 0)
    expires_at = body.get('expires_at')
    active = body.get('active', True)

    if not code:
        return _json_response({'error': 'code is required'}, 400)

    try:
        async with async_session() as session:
            async with session.begin():
                if did:
                    await _execute(session,
                        'UPDATE discounts SET code = :c, percent = :p, expires_at = :e, active = :a, updated_at = :u WHERE id = :id',
                        {'c': code, 'p': percent, 'e': expires_at, 'a': active, 'u': datetime.utcnow(), 'id': did})
                else:
                    await _execute(session,
                        'INSERT INTO discounts (code, percent, active, expires_at, updated_at) '
                        'VALUES (:c, :p, :a, :e, :u)',
                        {'c': code, 'p': percent, 'a': active, 'e': expires_at, 'u': datetime.utcnow()})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.delete('/admin/api/discounts/{discount_id}')
async def api_discounts_delete(request: Request, discount_id: int):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                await _execute(session, 'DELETE FROM discounts WHERE id = :id', {'id': discount_id})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- About ---

@router.get('/admin/api/about')
async def api_about(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, section, content, updated_at FROM about_content ORDER BY section')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.post('/admin/api/about')
async def api_about_update(request: Request):
    _require_api_session(request)
    body = await request.json()
    section = body.get('section', '')
    content = body.get('content', '')

    if not section:
        return _json_response({'error': 'section is required'}, 400)

    try:
        async with async_session() as session:
            async with session.begin():
                existing = await _fetch_one(session,
                    'SELECT id FROM about_content WHERE section = :s', {'s': section})
                if existing:
                    await _execute(session,
                        'UPDATE about_content SET content = :c, updated_at = :u WHERE id = :id',
                        {'c': content, 'u': datetime.utcnow(), 'id': existing['id']})
                else:
                    await _execute(session,
                        'INSERT INTO about_content (section, content, updated_at) VALUES (:s, :c, :u)',
                        {'s': section, 'c': content, 'u': datetime.utcnow()})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


# --- Proxy Config ---

@router.get('/admin/api/proxy')
async def api_proxy(request: Request):
    _require_api_session(request)
    try:
        async with async_session() as session:
            async with session.begin():
                rows = await _fetch_all(session,
                    'SELECT id, key, value, updated_at FROM proxy_config ORDER BY key')
                return _json_response(rows)
    except Exception as e:
        return _json_response({'error': str(e)}, 500)


@router.post('/admin/api/proxy')
async def api_proxy_update(request: Request):
    _require_api_session(request)
    body = await request.json()
    key = body.get('key', '')
    value = body.get('value', '')

    if not key:
        return _json_response({'error': 'key is required'}, 400)

    try:
        async with async_session() as session:
            async with session.begin():
                existing = await _fetch_one(session,
                    'SELECT id FROM proxy_config WHERE key = :k', {'k': key})
                if existing:
                    await _execute(session,
                        'UPDATE proxy_config SET value = :v, updated_at = :u WHERE id = :id',
                        {'v': value, 'u': datetime.utcnow(), 'id': existing['id']})
                else:
                    await _execute(session,
                        'INSERT INTO proxy_config (key, value, updated_at) VALUES (:k, :v, :u)',
                        {'k': key, 'v': value, 'u': datetime.utcnow()})
                return _json_response({'ok': True})
    except Exception as e:
        return _json_response({'error': str(e)}, 500)