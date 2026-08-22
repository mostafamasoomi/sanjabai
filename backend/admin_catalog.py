"""
Admin catalog endpoints for the models management tab.

`admin.py` already owns `/admin/pricing` and the per-model `/toggle` and
`/test` routes (used by the pricing tab). This module is the server side of
the *models* tab specifically: a full model_catalog listing that includes
provider/upstream (admin-only — never reuse this payload shape for a
user-facing route), an endpoint to change which configured upstream router
serves a row, and a bulk availability endpoint so the admin isn't stuck
toggling 1,100+ rows one at a time.
"""
from __future__ import annotations

import json
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session, rds
from dependencies import admin_required, _write_audit_log

router = APIRouter()

_VALID_AVAILABILITY = {'available', 'degraded', 'maintenance', 'disabled'}

# Sanity cap for bulk operations — comfortably above the current catalog size
# (~1,123 rows) so it never blocks a legitimate "select all", but still
# guards against a malformed payload trying to update an unbounded list.
_BULK_MAX_IDS = 5000


@router.get('/admin/catalog/models')
async def list_catalog_models(request: Request) -> JSONResponse:
    """Full model_catalog listing for the admin models table.

    Includes `provider` and `upstream`, which the user-facing catalog
    endpoints (`/v1/models`, `/catalog/models` in content.py) must not
    expose. This route is admin-only; keep it that way.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            "SELECT id, provider_model_id, provider, upstream, display_name, "
            "availability, provenance, context_window, currency, "
            "input_per_million, output_per_million, "
            "usd_input_per_million, usd_output_per_million, last_verified_at, markup_pct "
            "FROM model_catalog ORDER BY display_name, id"
        ))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/models/{model_id:path}/set-upstream')
async def set_model_upstream(request: Request, model_id: str, payload: dict[str, Any]) -> JSONResponse:
    """Change which configured upstream router serves this catalog row.

    Uses a `:path` converter (not the plain `{model_id}` the existing
    `/toggle` and `/test` routes in admin.py use) because ~96% of
    model_catalog ids contain a `/` (e.g. `freellmapi/agnes-1.5-flash`).
    A URL-encoded `%2F` never reaches Starlette's router as an encoded
    character for a plain segment param — the ASGI layer decodes it to a
    literal `/` first, so a single `{model_id}` segment never matches
    and every slash-containing id 404s. The caller must send the raw
    (unencoded) slash for this route to match.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    upstream = str(payload.get('upstream') or '').strip()
    if not upstream:
        return JSONResponse({'detail': 'مقدار upstream الزامی است'}, status_code=400)

    from providers import configured_providers
    valid = {p.name for p in configured_providers()}
    if upstream not in valid:
        return JSONResponse(
            {'detail': f'upstream نامعتبر است (مجاز: {", ".join(sorted(valid))})'},
            status_code=400,
        )

    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            'UPDATE model_catalog SET upstream = :u, updated_at = now() WHERE id = :id'
        ), {'u': upstream, 'id': model_id})
        if res.rowcount == 0:
            return JSONResponse({'detail': 'مدل در کاتالوگ یافت نشد'}, status_code=404)
        await session.commit()

    await _write_audit_log('admin.model.set_upstream', target_type='model_catalog', target_id=model_id,
                            details={'upstream': upstream}, request=request)
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'ok', 'model': model_id, 'upstream': upstream})


@router.post('/admin/models/bulk-availability')
async def bulk_set_availability(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Set availability on many models at once (bulk enable/disable/etc).

    Sets availability explicitly rather than reusing the single-model
    `/toggle` endpoint's flip semantics, since a bulk "disable" must also
    correctly cover rows that start out `maintenance` or `degraded`, not
    just `available`.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    ids = payload.get('ids')
    availability = payload.get('availability')
    if not isinstance(ids, list) or not ids:
        return JSONResponse({'detail': 'فهرست مدلها الزامی است'}, status_code=400)
    if len(ids) > _BULK_MAX_IDS:
        return JSONResponse({'detail': 'تعداد مدلها بیش از حد مجاز است'}, status_code=400)
    if availability not in _VALID_AVAILABILITY:
        return JSONResponse({'detail': 'وضعیت نامعتبر است'}, status_code=400)

    str_ids = [str(i) for i in ids]
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            'UPDATE model_catalog SET availability = :a, updated_at = now() WHERE id = ANY(:ids)'
        ), {'a': availability, 'ids': str_ids})
        updated = res.rowcount
        await session.commit()

    await _write_audit_log('admin.model.bulk_availability', target_type='model_catalog', target_id=None,
                            details={'availability': availability, 'count': updated, 'ids': str_ids[:50]},
                            request=request)
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'ok', 'updated': updated, 'availability': availability})


# ── Markup (profit percentage) ──────────────────────────────────
#
# Two levels, mirroring content.py's resolver (get_global_markup_pct /
# resolve_markup_pct / apply_markup, which is what actually prices every
# response -- these endpoints only read/write the underlying settings):
# a global percentage (app_setting row, migrations/0030_markup_pct.sql)
# applied to every model, and a per-model override on model_catalog.markup_pct
# that wins when set (NULL = inherit the global). A negative percentage is
# rejected everywhere -- the product rule is that no request may ever be
# loss-making, and the DB CHECK constraint backs this up as a second line
# of defense.

def _parse_markup_pct(raw: Any, *, allow_null: bool) -> tuple[float | None, str | None]:
    """Validate a markup_pct payload value. Returns (value, error_detail)."""
    if raw is None:
        if allow_null:
            return None, None
        return None, 'درصد سود الزامی است'
    try:
        pct = float(raw)
    except (TypeError, ValueError):
        return None, 'درصد نامعتبر است'
    if pct < 0:
        return None, 'درصد سود نمی‌تواند منفی باشد (هیچ درخواستی نباید ضررده باشد)'
    return pct, None


@router.get('/admin/markup/global')
async def get_global_markup(request: Request) -> JSONResponse:
    """Current global markup percentage (models with no override use this)."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    from content import get_global_markup_pct
    pct = await get_global_markup_pct()
    return JSONResponse({'markup_pct': pct})


@router.post('/admin/markup/global')
async def set_global_markup(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Set the global markup percentage applied to every model with no override."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    pct, err = _parse_markup_pct(payload.get('markup_pct'), allow_null=False)
    if err:
        return JSONResponse({'detail': err}, status_code=400)

    async with async_session() as session:
        await session.execute(sqlalchemy.text(
            "INSERT INTO app_setting (key, value, updated_at) "
            "VALUES ('global_markup_pct', :v, now()) "
            "ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now()"
        ), {'v': json.dumps(pct)})
        await session.commit()

    await _write_audit_log('admin.markup.set_global', target_type='app_setting', target_id='global_markup_pct',
                            details={'markup_pct': pct}, request=request)
    if rds:
        await rds.delete('cache:markup:global_pct', 'cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'ok', 'markup_pct': pct})


@router.get('/admin/markup/models')
async def list_model_markups(request: Request) -> JSONResponse:
    """Per-model markup overrides (markup_pct: null means "inherit the global")."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            "SELECT id, display_name, input_per_million, output_per_million, markup_pct "
            "FROM model_catalog ORDER BY display_name, id"
        ))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/markup/models/bulk')
async def bulk_set_model_markup(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Set (or clear, with markup_pct: null) a markup override on many models at once.

    Registered BEFORE set_model_markup's `/admin/markup/models/{model_id:path}`
    below: Starlette matches routes in registration order, and a `:path`
    converter with no trailing segment greedily matches ANY remaining path
    -- including the literal segment "bulk" -- so if that route were
    registered first, POST /admin/markup/models/bulk would be swallowed by
    it (model_id="bulk") and this endpoint would be unreachable.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    ids = payload.get('ids')
    if not isinstance(ids, list) or not ids:
        return JSONResponse({'detail': 'فهرست مدلها الزامی است'}, status_code=400)
    if len(ids) > _BULK_MAX_IDS:
        return JSONResponse({'detail': 'تعداد مدلها بیش از حد مجاز است'}, status_code=400)

    pct, err = _parse_markup_pct(payload.get('markup_pct'), allow_null=True)
    if err:
        return JSONResponse({'detail': err}, status_code=400)

    str_ids = [str(i) for i in ids]
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            'UPDATE model_catalog SET markup_pct = :p, updated_at = now() WHERE id = ANY(:ids)'
        ), {'p': pct, 'ids': str_ids})
        updated = res.rowcount
        await session.commit()

    await _write_audit_log('admin.markup.bulk_set_model', target_type='model_catalog', target_id=None,
                            details={'markup_pct': pct, 'count': updated, 'ids': str_ids[:50]},
                            request=request)
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'ok', 'updated': updated, 'markup_pct': pct})


@router.post('/admin/markup/models/{model_id:path}')
async def set_model_markup(request: Request, model_id: str, payload: dict[str, Any]) -> JSONResponse:
    """Set (or clear, with markup_pct: null) one model's markup override.

    Uses a `:path` converter for the same reason as set_model_upstream above
    -- most model_catalog ids contain a `/`. Must stay registered AFTER
    bulk_set_model_markup above -- see that function's docstring.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    pct, err = _parse_markup_pct(payload.get('markup_pct'), allow_null=True)
    if err:
        return JSONResponse({'detail': err}, status_code=400)

    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            'UPDATE model_catalog SET markup_pct = :p, updated_at = now() WHERE id = :id'
        ), {'p': pct, 'id': model_id})
        if res.rowcount == 0:
            return JSONResponse({'detail': 'مدل در کاتالوگ یافت نشد'}, status_code=404)
        await session.commit()

    await _write_audit_log('admin.markup.set_model', target_type='model_catalog', target_id=model_id,
                            details={'markup_pct': pct}, request=request)
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'ok', 'model': model_id, 'markup_pct': pct})
