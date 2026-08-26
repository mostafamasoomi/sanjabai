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
import re
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session, rds
from dependencies import admin_required, _write_audit_log
from i18n import err
from services import margin, probe_gate

router = APIRouter()

# MONKEYPATCH CONTRACT: the margin guard is reached as
# `margin.refuse_if_loss_making`, never imported by name, so
# tests/test_margin_guard_wiring.py can patch the one symbol on services.margin
# and have every call site here follow it. Same contract for the probe
# guard, reached as `probe_gate.refuse_if_unprobed`.


async def _refuse_loss_making(session, model_ids, request, **kwargs) -> JSONResponse | None:
    """400 + audit when the resulting price would be loss-making, else None.

    «هیچ درخواستی نباید ضررده باشد» -- refused outright, never silently
    auto-corrected to a safe number: an admin who typed the wrong price
    has to see the numbers and decide.
    """
    refusal = await margin.refuse_if_loss_making(session, model_ids, **kwargs)
    if refusal is None:
        return None
    await _write_audit_log('admin.margin.refused', target_type='model_catalog',
                           target_id=refusal.model_id, details=refusal.audit, request=request)
    # `detail_en or detail` -- a refusal built before the English side existed
    # shows its Persian rather than an empty string.
    return err(refusal.detail, refusal.detail_en or refusal.detail, 400)


async def _refuse_unprobed(session, model_ids, request) -> JSONResponse | None:
    """400 + audit when any id lacks a confirmed live probe, else None.

    «مدل فقط بعد از پروب زنده موفق به کاربر ارائه می‌شود» -- see
    services/probe_gate.py for why this is not the same thing as
    model_catalog.last_verified_at. Same audit-then-400 shape as
    `_refuse_loss_making` above, distinct event name so the two refusal
    reasons (margin vs. honest-labelling) are distinguishable in
    audit_log.
    """
    refusal = await probe_gate.refuse_if_unprobed(session, model_ids)
    if refusal is None:
        return None
    await _write_audit_log('admin.model.probe_refused', target_type='model_catalog',
                           target_id=None, details=refusal.audit, request=request)
    # `detail_en or detail` -- a refusal built before the English side existed
    # shows its Persian rather than an empty string.
    return err(refusal.detail, refusal.detail_en or refusal.detail, 400)


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

    `last_ok_at` and `health_status` are joined in from model_health_state
    because `last_verified_at` cannot answer the one question that decides
    whether a row can be enabled at all. That column is NOT NULL DEFAULT
    now() and is touched by every rollup pass, so all ~1,200 rows carry a
    recent date whether or not the model has ever answered — the admin table
    was showing "آخرین تأیید زنده: امروز" for models that had never been
    probed once. services/probe_gate.py gates on `last_ok_at`, so that is
    what the table has to show.

    `public_id` and `audience` come along for the same reason: a healthy,
    priced row with no public_id is invisible to users no matter what its
    availability says, and nothing in the panel used to reveal that.
    """
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            "SELECT c.id, c.provider_model_id, c.provider, c.upstream, c.display_name, "
            "c.availability, c.provenance, c.context_window, c.currency, "
            "c.input_per_million, c.output_per_million, "
            "c.usd_input_per_million, c.usd_output_per_million, c.last_verified_at, "
            "c.markup_pct, c.public_id, c.audience, "
            "s.last_ok_at, s.status AS health_status, s.last_error AS health_last_error "
            "FROM model_catalog c "
            # Either key: the background sweep records under provider_model_id,
            # the admin's «تست زنده» under the catalog id (same string for all
            # but one row today, but the join must not depend on that).
            "LEFT JOIN model_health_state s "
            "  ON s.model_id = c.id OR s.model_id = c.provider_model_id "
            "ORDER BY c.display_name, c.id"
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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    upstream = str(payload.get('upstream') or '').strip()
    if not upstream:
        return err('مقدار upstream الزامی است', 'upstream is required.', 400)

    from providers import configured_providers
    valid = {p.name for p in configured_providers()}
    if upstream not in valid:
        return err(
            f'upstream نامعتبر است (مجاز: {", ".join(sorted(valid))})',
            f'Invalid upstream. Valid options: {", ".join(sorted(valid))}',
            400,
        )

    async with async_session() as session:
        # The row's price does not change here, but its upstream COST can:
        # moving off the owner's own infrastructure onto a paid router turns
        # a zero cost into a real one, so the existing price has to be
        # re-judged against the upstream being moved TO.
        refused = await _refuse_loss_making(session, [model_id], request, upstream=upstream)
        if refused is not None:
            return refused
        res = await session.execute(sqlalchemy.text(
            'UPDATE model_catalog SET upstream = :u, updated_at = now() WHERE id = :id'
        ), {'u': upstream, 'id': model_id})
        if res.rowcount == 0:
            return err('مدل در کاتالوگ یافت نشد', 'Model not found in catalog.', 404)
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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    ids = payload.get('ids')
    availability = payload.get('availability')
    if not isinstance(ids, list) or not ids:
        return err('فهرست مدلها الزامی است', 'A list of model ids is required.', 400)
    if len(ids) > _BULK_MAX_IDS:
        return err('تعداد مدلها بیش از حد مجاز است', 'Too many model ids.', 400)
    if availability not in _VALID_AVAILABILITY:
        return err('وضعیت نامعتبر است', 'Invalid availability status.', 400)

    str_ids = [str(i) for i in ids]
    async with async_session() as session:
        # Only the transition that puts models ON SALE is a margin decision
        # / an honest-labelling decision; withdrawing them (disabled/
        # maintenance/degraded) never is either. The whole batch is refused
        # rather than partially applied, so the admin never has to work out
        # which half of a bulk enable actually landed.
        if availability == 'available':
            refused = await _refuse_unprobed(session, str_ids, request)
            if refused is not None:
                return refused
            refused = await _refuse_loss_making(session, str_ids, request)
            if refused is not None:
                return refused
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
#
# There is also an upper cap. Nothing enforced one before this: an admin
# who fat-fingers 700 instead of 7 silently multiplies every listed price
# on that model by ~8x -- no CHECK constraint, no loss-making guard catches
# it (a too-HIGH price is never loss-making). 1000 (i.e. 10x, +1000%) is
# chosen as the ceiling: it is comfortably above any markup this product
# has ever actually charged (single/low-double-digit percentages), so it
# never blocks a legitimate business decision, but it still catches the
# fat-finger case (a stray extra digit, a % sign typed as a raw multiplier,
# etc.) before it reaches a live price.
# The two field parsers and their English error tables live in a sibling
# module; this file is the endpoints. See admin_catalog_parsing.py for why
# they return a 2-tuple and not a language triple.
from admin_catalog_parsing import (  # noqa: E402
    _IMAGE_PRICE_ERR_EN, _MARKUP_PCT_ERR_EN, _MARKUP_PCT_MAX,
    _parse_image_price, _parse_markup_pct,
)


@router.get('/admin/markup/global')
async def get_global_markup(request: Request) -> JSONResponse:
    """Current global markup percentage (models with no override use this)."""
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    from content import get_global_markup_pct
    pct = await get_global_markup_pct()
    return JSONResponse({'markup_pct': pct})


@router.post('/admin/markup/global')
async def set_global_markup(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Set the global markup percentage applied to every model with no override."""
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    pct, fa_err = _parse_markup_pct(payload.get('markup_pct'), allow_null=False)
    if fa_err:
        return err(fa_err, _MARKUP_PCT_ERR_EN.get(fa_err, fa_err), 400)

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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    ids = payload.get('ids')
    if not isinstance(ids, list) or not ids:
        return err('فهرست مدلها الزامی است', 'A list of model ids is required.', 400)
    if len(ids) > _BULK_MAX_IDS:
        return err('تعداد مدلها بیش از حد مجاز است', 'Too many model ids.', 400)

    pct, fa_err = _parse_markup_pct(payload.get('markup_pct'), allow_null=True)
    if fa_err:
        return err(fa_err, _MARKUP_PCT_ERR_EN.get(fa_err, fa_err), 400)

    str_ids = [str(i) for i in ids]
    async with async_session() as session:
        refused = await _refuse_loss_making(session, str_ids, request,
                                            markup_pct=pct, markup_pct_provided=True)
        if refused is not None:
            return refused
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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    pct, fa_err = _parse_markup_pct(payload.get('markup_pct'), allow_null=True)
    if fa_err:
        return err(fa_err, _MARKUP_PCT_ERR_EN.get(fa_err, fa_err), 400)

    async with async_session() as session:
        refused = await _refuse_loss_making(session, [model_id], request,
                                            markup_pct=pct, markup_pct_provided=True)
        if refused is not None:
            return refused
        res = await session.execute(sqlalchemy.text(
            'UPDATE model_catalog SET markup_pct = :p, updated_at = now() WHERE id = :id'
        ), {'p': pct, 'id': model_id})
        if res.rowcount == 0:
            return err('مدل در کاتالوگ یافت نشد', 'Model not found in catalog.', 404)
        await session.commit()

    await _write_audit_log('admin.markup.set_model', target_type='model_catalog', target_id=model_id,
                            details={'markup_pct': pct}, request=request)
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'ok', 'model': model_id, 'markup_pct': pct})


# ── Image (media) pricing ────────────────────────────────────────
#
# Migration 0032 added model_catalog.image_price_per_unit (numeric, NULL for
# every row). backend/images.py's POST /v1/images/generations hard-refuses
# any request for a model whose image_price_per_unit is NULL (its gate 2,
# "no request may ever be loss-making") -- so until an admin sets a price
# here, image generation cannot serve anything. Unlike markup_pct (a
# percentage, float is fine), image_price_per_unit is a base Toman amount:
# the DB column is `numeric` with no scale constraint, so THIS endpoint is
# the only thing standing between an admin typing "10.5" and a fractional
# Toman quietly entering the pricing pipeline -- floats are rejected here,
# not just non-negative values.

@router.get('/admin/catalog/media-models')
async def list_media_models(request: Request) -> JSONResponse:
    """Media (image-output) rows from model_catalog with their current
    image_price_per_unit, for the admin image-pricing table.

    Identifies media rows the same way migration 0031 populated them: a
    model whose `modalities.output` array contains "image" (JSONB
    containment, `@>`), regardless of whether it also handles other output
    modalities alongside images (see migrations/0031_model_modalities.sql).
    """
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            "SELECT id, provider_model_id, display_name, availability, "
            "image_price_per_unit, markup_pct "
            "FROM model_catalog WHERE modalities->'output' @> '\"image\"'::jsonb "
            "ORDER BY display_name, id"
        ))
        rows = [dict(r._mapping) for r in res.fetchall()]
    return JSONResponse(jsonable_encoder(rows))


@router.post('/admin/catalog/models/{model_id:path}/image-price')
async def set_model_image_price(request: Request, model_id: str, payload: dict[str, Any]) -> JSONResponse:
    """Set (or clear, with image_price_per_unit: null) one model's base
    per-image Toman price.

    Uses a `:path` converter for the same reason as set_model_upstream and
    set_model_markup above -- most model_catalog ids contain a `/`. Must
    stay registered after any literal (non-`:path`) sibling route under
    `/admin/catalog/models/...` for the same reason bulk_set_model_markup
    must precede set_model_markup: a bare `{model_id:path}` converter
    greedily matches any remaining path segment, including a literal one
    that looks like it should be its own route.
    """
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    price, fa_err = _parse_image_price(payload.get('image_price_per_unit'))
    if fa_err:
        return err(fa_err, _IMAGE_PRICE_ERR_EN.get(fa_err, fa_err), 400)

    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            'UPDATE model_catalog SET image_price_per_unit = :p, updated_at = now() WHERE id = :id'
        ), {'p': price, 'id': model_id})
        if res.rowcount == 0:
            return err('مدل در کاتالوگ یافت نشد', 'Model not found in catalog.', 404)
        await session.commit()

    await _write_audit_log('admin.catalog.set_image_price', target_type='model_catalog', target_id=model_id,
                            details={'image_price_per_unit': price}, request=request)
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'ok', 'model': model_id, 'image_price_per_unit': price})
