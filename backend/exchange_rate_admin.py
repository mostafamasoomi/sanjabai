"""
Admin visibility into, and control over, the USD->IRT exchange rate that
every displayed price depends on: current rate, which resolver tier
produced it (source), when it was last refreshed, the list of additional
sources tried alongside tgju.org (Bonbast.com plus any admin-added site --
migrations/0047_exchange_sources.sql), and the flat Toman markup added to
the rate (owner's ask, 2026-08-25: make the ~2000 Toman margin editable
from the panel instead of only via env var + rebuild).

Mirrors admin_catalog.py's pattern exactly (same `admin_required` dependency,
same JSONResponse-with-401 style, same "refuse outright on a bad number,
never silently auto-correct" style for the flat-markup write) -- see that
file for the house style this follows.

── Trust boundary for POST /admin/exchange-rate/sources ─────────────────
A source an admin adds here is a URL plus a DECLARATIVE regex extraction
rule -- never code (see services/exchange_sources.py's module docstring for
the full reasoning). validate_source_url()/validate_custom_regex_pattern()
below reject the write outright on anything that looks unsafe; nothing here
ever evals or execs admin input.
"""
from __future__ import annotations

import json
import re
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session, rds
from dependencies import admin_required, _write_audit_log
from services.exchange_sources import (
    FLAT_MARKUP_SETTING_KEY,
    FLAT_MARKUP_CACHE_KEY,
    validate_custom_regex_pattern,
    validate_source_url,
)

router = APIRouter()

# A custom source_key may never shadow a built-in tier's own `source` string
# -- content.py's ladder already uses these as provenance labels, and
# get_exchange_rate_meta()'s `source` field would become ambiguous.
_RESERVED_SOURCE_KEYS = {'db_override', 'tgju', 'bonbast', 'er_api', 'hardcoded_fallback'}
_SOURCE_KEY_RE = re.compile(r'^[a-z][a-z0-9_]{1,31}$')
_FLAT_MARKUP_MAX_TOMAN = 500_000  # generous fat-finger guard: today's real rate is ~200k Toman/USD, so a markup above this is almost certainly a typo, not a business decision -- raise it if that ever changes


async def _invalidate_exchange_rate_caches() -> None:
    """Every cache key a change to the rate, its sources, or the flat markup
    can make stale. Deleted together on every write below so the panel and
    every priced page reflect the change immediately instead of waiting out
    a TTL (up to 10 minutes for the catalog keys -- see CLAUDE.md's
    Redis-invalidation rule)."""
    if not rds:
        return
    import content
    try:
        await rds.delete(
            content.EXCHANGE_RATE_CACHE_KEY,
            'exchange_rate:usd_irt',  # legacy key written by content.py's /exchange-rate, /api/exchange-rate
            FLAT_MARKUP_CACHE_KEY,
            'cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing',
        )
    except Exception:
        pass


@router.get('/admin/exchange-rate')
async def get_exchange_rate_admin(request: Request) -> JSONResponse:
    """Current USD->IRT rate, its source, and when it was last fetched."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    from content import get_exchange_rate_meta
    meta = await get_exchange_rate_meta()
    return JSONResponse(jsonable_encoder(meta))


@router.post('/admin/exchange-rate/refresh')
async def refresh_exchange_rate_admin(request: Request) -> JSONResponse:
    """Bust the cached rate and re-resolve it immediately.

    Deletes the same Redis key `_get_exchange_rate()` reads/writes
    (`content.EXCHANGE_RATE_CACHE_KEY`), so the very next read (this
    request's own call to `get_exchange_rate_meta()`) is a forced cache
    miss and re-runs the full resolver (db_override -> tgju -> configured
    sources -> er_api -> hardcoded_fallback).
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    import content
    if rds:
        try:
            await rds.delete(content.EXCHANGE_RATE_CACHE_KEY)
        except Exception:
            pass

    meta = await content.get_exchange_rate_meta()
    await _write_audit_log('admin.exchange_rate.refresh', target_type='exchange_rate', target_id=None,
                            details={'source': meta.get('source')}, request=request)
    return JSONResponse(jsonable_encoder(meta))


# ── Flat Toman markup ──────────────────────────────────────────────────

def _parse_flat_markup_toman(raw: Any) -> tuple[float | None, str | None]:
    if raw is None:
        return None, 'مقدار مارک‌آپ الزامی است'
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None, 'مقدار مارک‌آپ نامعتبر است'
    if v < 0:
        return None, 'مارک‌آپ نمی‌تواند منفی باشد (باعث فروش زیر نرخ بازار می‌شود)'
    if v > _FLAT_MARKUP_MAX_TOMAN:
        return None, f'مارک‌آپ بیش از حد بزرگ است (سقف {_FLAT_MARKUP_MAX_TOMAN:,} تومان) -- احتمالاً اشتباه تایپی است'
    return v, None


@router.get('/admin/exchange-rate/flat-markup')
async def get_flat_markup_admin(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    from services.exchange_sources import get_flat_markup_toman
    import content
    value = await get_flat_markup_toman()
    return JSONResponse({'flat_markup_toman': value, 'default_toman': content.USD_IRT_FLAT_MARKUP})


@router.post('/admin/exchange-rate/flat-markup')
async def set_flat_markup_admin(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Set the flat Toman markup added to the USD->IRT rate. 0 is allowed
    (the owner may deliberately want no flat margin for a while); negative
    and absurdly large values are refused outright, never auto-corrected --
    same house style as admin_catalog.py's global-markup-percent write."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    value, err = _parse_flat_markup_toman(payload.get('flat_markup_toman'))
    if err:
        return JSONResponse({'detail': err}, status_code=400)

    async with async_session() as session:
        await session.execute(sqlalchemy.text(
            "INSERT INTO app_setting (key, value, updated_at) "
            "VALUES (:key, :v, now()) "
            "ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now()"
        ), {'key': FLAT_MARKUP_SETTING_KEY, 'v': json.dumps(value)})
        await session.commit()

    await _write_audit_log('admin.exchange_rate.set_flat_markup', target_type='app_setting',
                            target_id=FLAT_MARKUP_SETTING_KEY, details={'flat_markup_toman': value}, request=request)
    await _invalidate_exchange_rate_caches()
    return JSONResponse({'status': 'ok', 'flat_markup_toman': value})


# ── Configured sources (Bonbast.com + admin-added custom sources) ────────

_BUILTIN_INFO = [
    {'source_key': 'tgju', 'display_name': 'tgju.org', 'kind': 'code', 'editable': False,
     'note': 'همیشه اولین تلاش پس از override دستی؛ کد ثابت، از این جدول مدیریت نمی‌شود.'},
    {'source_key': 'er_api', 'display_name': 'open.er-api.com', 'kind': 'code', 'editable': False,
     'note': 'پشتیبان؛ وقتی tgju و منابع فعال زیر شکست بخورند امتحان می‌شود.'},
    {'source_key': 'hardcoded_fallback', 'display_name': 'مقدار ثابت در کد', 'kind': 'code', 'editable': False,
     'note': 'آخرین راه‌حل؛ همیشه فعال است و از طریق پنل غیرفعال نمی‌شود.'},
]


@router.get('/admin/exchange-rate/sources')
async def list_exchange_rate_sources(request: Request) -> JSONResponse:
    """The full picture: the two code-only tiers (tgju, er_api,
    hardcoded_fallback -- read-only, `editable: false`) plus every row in
    exchange_rate_sources (Bonbast.com, is_builtin, and any admin-added
    custom_regex source), which the panel can create/edit/delete below."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                'SELECT source_key, display_name, kind, url, unit, extract_regex, enabled, '
                'priority, timeout_s, is_builtin, updated_at FROM exchange_rate_sources '
                'ORDER BY priority ASC, id ASC'
            ))
            rows = [dict(r._mapping) for r in res.fetchall()]
    except Exception as e:
        return JSONResponse({'detail': f'خطا در خواندن منابع نرخ ارز: {e}'}, status_code=500)

    for r in rows:
        r['editable'] = True  # every DB row (bonbast included) supports enabled/priority/timeout_s edits
        r['deletable'] = not r['is_builtin']

    return JSONResponse(jsonable_encoder({'builtin': _BUILTIN_INFO, 'configured': rows}))


@router.post('/admin/exchange-rate/sources')
async def create_exchange_rate_source(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Add a new custom_regex source -- the extensibility the owner asked
    for ("اگر مرجع دیگری خواست"). Always kind='custom_regex'; a second
    'bonbast' row, or any code-only kind, cannot be created from here."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    source_key = str(payload.get('source_key') or '').strip().lower()
    display_name = str(payload.get('display_name') or '').strip()
    url = str(payload.get('url') or '').strip()
    unit = str(payload.get('unit') or '').strip().lower()
    extract_regex = str(payload.get('extract_regex') or '').strip()
    priority = payload.get('priority', 100)
    timeout_s = payload.get('timeout_s', 5)

    if not _SOURCE_KEY_RE.match(source_key):
        return JSONResponse({'detail': 'کلید منبع باید با حرف کوچک شروع شود و فقط شامل حروف کوچک، عدد و _ باشد (۲ تا ۳۲ نویسه)'}, status_code=400)
    if source_key in _RESERVED_SOURCE_KEYS:
        return JSONResponse({'detail': 'این کلید برای یک منبع پایه رزرو شده است'}, status_code=400)
    if not display_name:
        return JSONResponse({'detail': 'نام نمایشی الزامی است'}, status_code=400)
    if unit not in ('toman', 'rial'):
        return JSONResponse({'detail': "واحد باید toman یا rial باشد"}, status_code=400)
    url_err = validate_source_url(url)
    if url_err:
        return JSONResponse({'detail': url_err}, status_code=400)
    regex_err = validate_custom_regex_pattern(extract_regex)
    if regex_err:
        return JSONResponse({'detail': regex_err}, status_code=400)
    try:
        priority = int(priority)
        timeout_s = float(timeout_s)
    except (TypeError, ValueError):
        return JSONResponse({'detail': 'اولویت و مهلت زمانی باید عددی باشند'}, status_code=400)
    if priority <= 0:
        return JSONResponse({'detail': 'اولویت باید عددی مثبت باشد (کوچک‌تر یعنی زودتر امتحان می‌شود)'}, status_code=400)
    if not (0 < timeout_s <= 10):
        return JSONResponse({'detail': 'مهلت زمانی باید بین ۰ تا ۱۰ ثانیه باشد'}, status_code=400)

    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                "INSERT INTO exchange_rate_sources "
                "(source_key, display_name, kind, url, unit, extract_regex, enabled, priority, timeout_s, is_builtin) "
                "VALUES (:source_key, :display_name, 'custom_regex', :url, :unit, :extract_regex, true, :priority, :timeout_s, false) "
                "RETURNING id"
            ), {
                'source_key': source_key, 'display_name': display_name, 'url': url,
                'unit': unit, 'extract_regex': extract_regex, 'priority': priority, 'timeout_s': timeout_s,
            })
            new_id = res.scalar_one()
            await session.commit()
    except sqlalchemy.exc.IntegrityError:
        return JSONResponse({'detail': 'کلید منبع تکراری است'}, status_code=409)
    except Exception as e:
        return JSONResponse({'detail': f'خطا در ایجاد منبع: {e}'}, status_code=500)

    await _write_audit_log('admin.exchange_rate.source_create', target_type='exchange_rate_sources',
                            target_id=source_key, details={'url': url, 'unit': unit, 'priority': priority},
                            request=request)
    await _invalidate_exchange_rate_caches()
    return JSONResponse({'status': 'ok', 'id': new_id, 'source_key': source_key}, status_code=201)


@router.patch('/admin/exchange-rate/sources/{source_key}')
async def update_exchange_rate_source(source_key: str, request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Edit enabled/priority/timeout_s on any row (Bonbast included). A
    custom_regex row also accepts url/extract_regex/unit edits; Bonbast's
    fetch is fixed Python code, so those three fields are ignored for it
    even if sent."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    sets, params = [], {'source_key': source_key}

    if 'enabled' in payload:
        sets.append('enabled = :enabled')
        params['enabled'] = bool(payload['enabled'])
    if 'priority' in payload:
        try:
            p = int(payload['priority'])
        except (TypeError, ValueError):
            return JSONResponse({'detail': 'اولویت باید عددی باشد'}, status_code=400)
        if p <= 0:
            return JSONResponse({'detail': 'اولویت باید عددی مثبت باشد'}, status_code=400)
        sets.append('priority = :priority')
        params['priority'] = p
    if 'timeout_s' in payload:
        try:
            t = float(payload['timeout_s'])
        except (TypeError, ValueError):
            return JSONResponse({'detail': 'مهلت زمانی باید عددی باشد'}, status_code=400)
        if not (0 < t <= 10):
            return JSONResponse({'detail': 'مهلت زمانی باید بین ۰ تا ۱۰ ثانیه باشد'}, status_code=400)
        sets.append('timeout_s = :timeout_s')
        params['timeout_s'] = t
    if 'url' in payload or 'extract_regex' in payload or 'unit' in payload:
        if 'url' in payload:
            url_err = validate_source_url(str(payload['url'] or ''))
            if url_err:
                return JSONResponse({'detail': url_err}, status_code=400)
            sets.append('url = :url')
            params['url'] = str(payload['url']).strip()
        if 'extract_regex' in payload:
            regex_err = validate_custom_regex_pattern(str(payload['extract_regex'] or ''))
            if regex_err:
                return JSONResponse({'detail': regex_err}, status_code=400)
            sets.append('extract_regex = :extract_regex')
            params['extract_regex'] = str(payload['extract_regex']).strip()
        if 'unit' in payload:
            unit = str(payload['unit']).strip().lower()
            if unit not in ('toman', 'rial'):
                return JSONResponse({'detail': "واحد باید toman یا rial باشد"}, status_code=400)
            sets.append('unit = :unit')
            params['unit'] = unit
        # A builtin row (bonbast) ignores these three fields even if sent --
        # its fetch is fixed Python code, not database-driven; the WHERE
        # clause below intentionally does not exclude is_builtin rows so
        # enabled/priority/timeout_s edits on Bonbast still succeed even
        # when the request also (harmlessly) tried to set url/regex/unit --
        # those columns simply get written but are never read by the fetch.

    if not sets:
        return JSONResponse({'detail': 'هیچ فیلدی برای به‌روزرسانی ارسال نشده است'}, status_code=400)

    sets.append('updated_at = now()')
    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                f"UPDATE exchange_rate_sources SET {', '.join(sets)} WHERE source_key = :source_key RETURNING id"
            ), params)
            row = res.fetchone()
            if row is None:
                return JSONResponse({'detail': 'منبع یافت نشد'}, status_code=404)
            await session.commit()
    except Exception as e:
        return JSONResponse({'detail': f'خطا در به‌روزرسانی منبع: {e}'}, status_code=500)

    await _write_audit_log('admin.exchange_rate.source_update', target_type='exchange_rate_sources',
                            target_id=source_key, details={k: v for k, v in payload.items()}, request=request)
    await _invalidate_exchange_rate_caches()
    return JSONResponse({'status': 'ok', 'source_key': source_key})


@router.delete('/admin/exchange-rate/sources/{source_key}')
async def delete_exchange_rate_source(source_key: str, request: Request) -> JSONResponse:
    """Only a non-builtin (admin-added custom_regex) row can be deleted --
    Bonbast can be disabled (PATCH enabled=false) but not removed, so the
    seeded row migrations/0047_exchange_sources.sql relies on always exists."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                "DELETE FROM exchange_rate_sources WHERE source_key = :source_key AND is_builtin = FALSE RETURNING id"
            ), {'source_key': source_key})
            row = res.fetchone()
            if row is None:
                return JSONResponse({'detail': 'منبع یافت نشد یا منبع پایه است و قابل حذف نیست'}, status_code=404)
            await session.commit()
    except Exception as e:
        return JSONResponse({'detail': f'خطا در حذف منبع: {e}'}, status_code=500)

    await _write_audit_log('admin.exchange_rate.source_delete', target_type='exchange_rate_sources',
                            target_id=source_key, details={}, request=request)
    await _invalidate_exchange_rate_caches()
    return JSONResponse({'status': 'ok'})
