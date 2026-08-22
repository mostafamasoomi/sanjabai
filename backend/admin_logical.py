"""
Admin endpoints for `logical_model` / `logical_model_candidate`
(migration 0025_logical_models.sql).

Phase C, part 3: the clusterer (a separate offline job) already populated
these two tables in production -- 449 logical models, 1154 candidates. It
auto-approved only the 100 singleton clusters (one physical model = one
obvious candidate); the other 1054 rows are `state='proposed'` and
deliberately held for a human, because 137 of the underlying clusters
tripped a price or context-window inconsistency warning during clustering.
Before this file there was no screen to work through that queue -- this
router is that screen's backend half (``LogicalModelsSection.tsx`` is the
frontend half, owned by the same change).

── What a "logical model" is, for anyone new to this schema ───────────────
`logical_model` is the thing a *user* eventually sees ("GPT-4o", "Claude
Opus") -- one row, one price, one availability. `logical_model_candidate`
is the N *physical* upstream models (`model_catalog` rows, each a specific
provider's specific model id) that a logical model is allowed to route a
request to. Nothing here is user-visible yet: every logical_model row seeded
so far has `availability='maintenance'`, and per the module comment in the
migration itself, "Nothing reads these tables until LOGICAL_ROUTING_ENABLED
=true." This router only lets an admin get the *data* into a shippable
state (approved candidates, a sane routing policy, availability flipped on)
-- it does not flip that separate feature flag.

── Route prefix ────────────────────────────────────────────────────────
Registered bare as ``/admin/logical-models...`` (no leading ``/api``), same
as every other admin router in this codebase (``admin_packages.py``,
``site_settings.py``) -- the Next.js proxy strips a leading ``/api`` before
forwarding.

── The guard rails, and why they are not optional ─────────────────────────
1. Pinning: `logical_model.pinned_candidate_id` is a foreign key straight
   into `model_catalog(id)` -- i.e. it stores a *catalog_id* (the physical
   model), not a `logical_model_candidate.id`. A pin is only meaningful if
   some `logical_model_candidate` row for this `logical_key` with that
   `catalog_id` is both `state='approved'` and `enabled=true`; pinning
   anything else (rejected, disabled, or a catalog_id that was never even
   proposed for this logical model) is a trap that only surfaces when a
   real user's request tries to route through it and finds nothing there.
   Refused with a Persian 400, both when setting `pinned_candidate_id`
   directly and, symmetrically, when a candidate-state edit would yank the
   rug out from under a pin already in place (rejecting/disabling the
   candidate a logical model currently has pinned).
2. Availability: setting `availability='available'` requires at least one
   `approved` + `enabled` candidate for that logical_key. Without one, the
   logical model would be published with nowhere to route -- the "model
   only ever shown after a live probe succeeded" rule this product runs on
   applies here one level up: no eligible candidate, no publish.
3. Every enum field (`availability`, `routing_policy`, candidate `state`)
   is checked against the exact CHECK-constraint value lists from migration
   0025 before any SQL runs, so a typo returns a Persian 400 instead of an
   unhandled asyncpg CheckViolation turning into a 500.

── Decimal serialisation ───────────────────────────────────────────────
`est_cost_usd_input`/`est_cost_usd_output` (candidate) and
`usd_input_per_million`/`usd_output_per_million` (model_catalog, joined in)
are NUMERIC -- asyncpg/SQLAlchemy hand these back as `Decimal`, which the
stdlib `json` module cannot serialise. Every response here goes through
`jsonable_encoder`, exactly like `admin_packages.py`'s `list_packages`,
which converts `Decimal` the same way FastAPI's own response encoding does.
These are USD cost *estimates* for admin comparison only -- never confuse
them with the Toman fields (`input_per_million`/`output_per_million`),
which are this product's real money and must never be multiplied or
divided by 10 anywhere.
"""
from __future__ import annotations

from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session
from dependencies import admin_required, _write_audit_log

router = APIRouter()

_AVAILABILITY_VALUES = ('available', 'degraded', 'maintenance', 'disabled')
_ROUTING_POLICY_VALUES = ('cheapest_healthy', 'priority', 'pinned')
_CANDIDATE_STATE_VALUES = ('proposed', 'approved', 'rejected')

_UNAUTHORIZED = JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
_NO_DB = JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)


def _candidate_counts_cte() -> str:
    """Shared SELECT used by both the list query and its COUNT(*) sibling,
    so the pagination total is computed against exactly the same filtered
    set the page itself was drawn from."""
    return """
        SELECT lm.key, lm.display_name, lm.vendor, lm.context_window,
               lm.max_output_tokens, lm.availability, lm.routing_policy,
               lm.pinned_candidate_id, lm.updated_at,
               COUNT(lmc.id) AS candidate_count,
               COUNT(*) FILTER (WHERE lmc.state = 'proposed') AS proposed_count,
               COUNT(*) FILTER (WHERE lmc.state = 'approved') AS approved_count,
               COUNT(*) FILTER (WHERE lmc.state = 'rejected') AS rejected_count
        FROM logical_model lm
        LEFT JOIN logical_model_candidate lmc ON lmc.logical_key = lm.key
        WHERE (:q = '' OR lm.key ILIKE :qlike OR lm.display_name ILIKE :qlike)
          AND (:availability = '' OR lm.availability = :availability)
        GROUP BY lm.key
    """


@router.get('/admin/logical-models')
async def list_logical_models(request: Request) -> JSONResponse:
    """Paginated, filterable list -- 449 rows is far too many to dump at
    once, and the admin's real working queue is "models with undecided
    (proposed) candidates", so that filter and a text search are both
    first-class query params, and the default sort surfaces the queue
    (most `proposed` candidates first) rather than an arbitrary key order.
    """
    if not await admin_required(request):
        return _UNAUTHORIZED
    if async_session is None:
        return _NO_DB

    qp = request.query_params
    q = (qp.get('q') or '').strip()
    availability = qp.get('availability') or ''
    if availability and availability not in _AVAILABILITY_VALUES:
        return JSONResponse({'detail': 'مقدار availability نامعتبر است'}, status_code=400)
    pending_only = (qp.get('pending_only') or '').lower() in ('1', 'true', 'yes')
    page = max(1, int(qp.get('page', 1)))
    limit = min(max(1, int(qp.get('limit', 50))), 200)
    offset = (page - 1) * limit

    params = {'q': q, 'qlike': f'%{q}%', 'availability': availability}

    having = "HAVING (:pending_only = false OR proposed_count > 0)"
    async with async_session() as session:
        count_res = await session.execute(
            sqlalchemy.text(
                f"SELECT COUNT(*) AS c FROM ({_candidate_counts_cte()}) counts {having}"
            ),
            {**params, 'pending_only': pending_only},
        )
        total = count_res.fetchone().c

        res = await session.execute(
            sqlalchemy.text(
                f"""
                SELECT * FROM ({_candidate_counts_cte()}) counts
                {having}
                ORDER BY proposed_count DESC, key
                LIMIT :limit OFFSET :offset
                """
            ),
            {**params, 'pending_only': pending_only, 'limit': limit, 'offset': offset},
        )
        rows = [dict(r._mapping) for r in res.fetchall()]

    items = [
        {
            'key': r['key'], 'display_name': r['display_name'], 'vendor': r['vendor'],
            'context_window': r['context_window'], 'max_output_tokens': r['max_output_tokens'],
            'availability': r['availability'], 'routing_policy': r['routing_policy'],
            'pinned_candidate_id': r['pinned_candidate_id'], 'updated_at': r['updated_at'],
            'candidate_counts': {
                'total': r['candidate_count'], 'proposed': r['proposed_count'],
                'approved': r['approved_count'], 'rejected': r['rejected_count'],
            },
        }
        for r in rows
    ]
    return JSONResponse(jsonable_encoder({'items': items, 'total': total, 'page': page, 'limit': limit}))


@router.get('/admin/logical-models/{key}')
async def get_logical_model(request: Request, key: str) -> JSONResponse:
    """One logical model plus every candidate, each joined to its
    `model_catalog` row -- an admin approving a candidate needs to see the
    real physical id, its live availability, and its real price in the same
    view, not open a second screen to look it up. Approving blind is the
    failure mode this endpoint's shape exists to prevent.
    """
    if not await admin_required(request):
        return _UNAUTHORIZED
    if async_session is None:
        return _NO_DB

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM logical_model WHERE key = :key'), {'key': key}
        )
        model_row = res.fetchone()
        if not model_row:
            return JSONResponse({'detail': 'مدل منطقی یافت نشد'}, status_code=404)
        model = dict(model_row._mapping)

        cand_res = await session.execute(
            sqlalchemy.text(
                """
                SELECT lmc.id AS candidate_id, lmc.catalog_id, lmc.priority, lmc.enabled,
                       lmc.state, lmc.est_cost_usd_input, lmc.est_cost_usd_output,
                       lmc.added_by, lmc.created_at, lmc.updated_at,
                       mc.provider AS catalog_provider,
                       mc.provider_model_id AS catalog_provider_model_id,
                       mc.display_name AS catalog_display_name,
                       mc.availability AS catalog_availability,
                       mc.currency AS catalog_currency,
                       mc.input_per_million AS catalog_input_per_million,
                       mc.output_per_million AS catalog_output_per_million,
                       mc.usd_input_per_million AS catalog_usd_input_per_million,
                       mc.usd_output_per_million AS catalog_usd_output_per_million
                FROM logical_model_candidate lmc
                JOIN model_catalog mc ON mc.id = lmc.catalog_id
                WHERE lmc.logical_key = :key
                ORDER BY lmc.priority, lmc.id
                """
            ),
            {'key': key},
        )
        cand_rows = [dict(r._mapping) for r in cand_res.fetchall()]

    candidates = []
    for r in cand_rows:
        candidates.append({
            'id': r['candidate_id'], 'catalog_id': r['catalog_id'], 'priority': r['priority'],
            'enabled': r['enabled'], 'state': r['state'],
            'est_cost_usd_input': r['est_cost_usd_input'], 'est_cost_usd_output': r['est_cost_usd_output'],
            'added_by': r['added_by'], 'created_at': r['created_at'], 'updated_at': r['updated_at'],
            'catalog': {
                'id': r['catalog_id'], 'provider': r['catalog_provider'],
                'provider_model_id': r['catalog_provider_model_id'],
                'display_name': r['catalog_display_name'], 'availability': r['catalog_availability'],
                'currency': r['catalog_currency'],
                'input_per_million': r['catalog_input_per_million'],
                'output_per_million': r['catalog_output_per_million'],
                'usd_input_per_million': r['catalog_usd_input_per_million'],
                'usd_output_per_million': r['catalog_usd_output_per_million'],
            },
        })

    return JSONResponse(jsonable_encoder({**model, 'candidates': candidates}))


def _validate_candidate_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    cleaned: dict[str, Any] = {}
    if 'state' in payload:
        v = payload['state']
        if v not in _CANDIDATE_STATE_VALUES:
            return {}, f"وضعیت گزینه باید یکی از این مقادیر باشد: {', '.join(_CANDIDATE_STATE_VALUES)}"
        cleaned['state'] = v
    if 'enabled' in payload:
        v = payload['enabled']
        if not isinstance(v, bool):
            return {}, 'فعال/غیرفعال بودن گزینه باید true/false باشد'
        cleaned['enabled'] = v
    if 'priority' in payload:
        v = payload['priority']
        if isinstance(v, bool) or not isinstance(v, int):
            return {}, 'اولویت باید عدد صحیح باشد'
        cleaned['priority'] = v
    return cleaned, None


@router.post('/admin/logical-models/{key}/candidates/{candidate_id}')
async def update_candidate(request: Request, key: str, candidate_id: int, payload: dict[str, Any]) -> JSONResponse:
    """Approve/reject a candidate (`state`), enable/disable it, and/or set
    its `priority` -- three fields on the same row, so one endpoint rather
    than three, but every change is still audit-logged with exactly what
    changed.
    """
    if not await admin_required(request):
        return _UNAUTHORIZED
    if async_session is None:
        return _NO_DB

    unknown = set(payload) - {'state', 'enabled', 'priority'}
    if unknown:
        return JSONResponse({'detail': f'فیلد ناشناخته: {", ".join(sorted(unknown))}'}, status_code=400)

    cleaned, err = _validate_candidate_payload(payload)
    if err:
        return JSONResponse({'detail': err}, status_code=400)
    if not cleaned:
        return JSONResponse({'detail': 'هیچ فیلدی برای بروزرسانی ارسال نشده است'}, status_code=400)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                """
                SELECT lmc.id, lmc.catalog_id, lmc.state, lmc.enabled,
                       lm.pinned_candidate_id
                FROM logical_model_candidate lmc
                JOIN logical_model lm ON lm.key = lmc.logical_key
                WHERE lmc.logical_key = :key AND lmc.id = :cid
                """
            ),
            {'key': key, 'cid': candidate_id},
        )
        row = res.fetchone()
        if not row:
            return JSONResponse({'detail': 'گزینه یافت نشد'}, status_code=404)
        row_map = dict(row._mapping)

        # Guard: this candidate is the logical model's current pin (matched
        # by catalog_id -- see module docstring on what pinned_candidate_id
        # actually points to), and this edit would make it ineligible
        # (rejected/proposed, or disabled). Refuse rather than silently
        # breaking the live pin.
        is_current_pin = (
            row_map['pinned_candidate_id'] is not None
            and row_map['pinned_candidate_id'] == row_map['catalog_id']
        )
        about_to_break = is_current_pin and (
            cleaned.get('state', row_map['state']) != 'approved'
            or cleaned.get('enabled', row_map['enabled']) is False
        )
        if about_to_break:
            return JSONResponse(
                {'detail': 'این گزینه هم‌اکنون به‌عنوان مسیر پین‌شدهٔ این مدل منطقی انتخاب شده است؛ '
                           'ابتدا سیاست مسیریابی را تغییر دهید یا گزینهٔ دیگری را پین کنید.'},
                status_code=400,
            )

        set_parts = [f'{f} = :{f}' for f in cleaned]
        set_parts.append('updated_at = now()')
        await session.execute(
            sqlalchemy.text(
                f"UPDATE logical_model_candidate SET {', '.join(set_parts)} WHERE id = :cid"
            ),
            {**cleaned, 'cid': candidate_id},
        )
        await session.commit()

    await _write_audit_log(
        'admin.logical_candidate.update', target_type='logical_model_candidate',
        target_id=candidate_id, details={'logical_key': key, **cleaned}, request=request,
    )
    return JSONResponse({'status': 'ok', 'id': candidate_id, 'updated': cleaned})


@router.post('/admin/logical-models/{key}/routing')
async def update_routing(request: Request, key: str, payload: dict[str, Any]) -> JSONResponse:
    """Set `routing_policy` and/or `pinned_candidate_id`.

    `pinned_candidate_id` is a `model_catalog.id` (see module docstring),
    not a `logical_model_candidate.id` -- validated here against a live
    approved+enabled candidate for this exact `logical_key` before it is
    ever written, and a `routing_policy='pinned'` with no pin is rejected
    as meaningless rather than silently accepted.
    """
    if not await admin_required(request):
        return _UNAUTHORIZED
    if async_session is None:
        return _NO_DB

    unknown = set(payload) - {'routing_policy', 'pinned_candidate_id'}
    if unknown:
        return JSONResponse({'detail': f'فیلد ناشناخته: {", ".join(sorted(unknown))}'}, status_code=400)

    cleaned: dict[str, Any] = {}
    if 'routing_policy' in payload:
        v = payload['routing_policy']
        if v not in _ROUTING_POLICY_VALUES:
            return JSONResponse(
                {'detail': f"سیاست مسیریابی باید یکی از این مقادیر باشد: {', '.join(_ROUTING_POLICY_VALUES)}"},
                status_code=400,
            )
        cleaned['routing_policy'] = v
    if 'pinned_candidate_id' in payload:
        v = payload['pinned_candidate_id']
        if v is not None and not isinstance(v, str):
            return JSONResponse({'detail': 'شناسهٔ گزینهٔ پین‌شده باید رشته یا null باشد'}, status_code=400)
        cleaned['pinned_candidate_id'] = v
    if not cleaned:
        return JSONResponse({'detail': 'هیچ فیلدی برای بروزرسانی ارسال نشده است'}, status_code=400)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM logical_model WHERE key = :key'), {'key': key}
        )
        current = res.fetchone()
        if not current:
            return JSONResponse({'detail': 'مدل منطقی یافت نشد'}, status_code=404)
        current_map = dict(current._mapping)
        effective = {**current_map, **cleaned}

        if effective.get('pinned_candidate_id') is not None:
            chk = await session.execute(
                sqlalchemy.text(
                    """
                    SELECT 1 FROM logical_model_candidate
                    WHERE logical_key = :key AND catalog_id = :cid
                      AND state = 'approved' AND enabled = true
                    """
                ),
                {'key': key, 'cid': effective['pinned_candidate_id']},
            )
            if not chk.fetchone():
                return JSONResponse(
                    {'detail': 'گزینهٔ انتخاب‌شده برای پین باید برای همین مدل منطقی، تأییدشده (approved) '
                               'و فعال (enabled) باشد. پین‌کردن گزینهٔ رد‌شده یا غیرفعال تله‌ای است که فقط '
                               'وقتی کاربر واقعی به آن برسد آشکار می‌شود.'},
                    status_code=400,
                )

        if effective.get('routing_policy') == 'pinned' and effective.get('pinned_candidate_id') is None:
            return JSONResponse(
                {'detail': 'سیاست مسیریابی «پین‌شده» بدون انتخاب یک گزینهٔ پین معنا ندارد'},
                status_code=400,
            )

        set_parts = [f'{f} = :{f}' for f in cleaned]
        set_parts.append('updated_at = now()')
        await session.execute(
            sqlalchemy.text(f"UPDATE logical_model SET {', '.join(set_parts)} WHERE key = :key"),
            {**cleaned, 'key': key},
        )
        await session.commit()

    await _write_audit_log(
        'admin.logical_model.routing_update', target_type='logical_model',
        target_id=key, details=cleaned, request=request,
    )
    return JSONResponse({'status': 'ok', 'key': key, 'updated': cleaned})


@router.post('/admin/logical-models/{key}/availability')
async def update_availability(request: Request, key: str, payload: dict[str, Any]) -> JSONResponse:
    """Set a logical model's `availability`. Publishing it (`available`)
    requires at least one eligible (`approved` + `enabled`) candidate --
    otherwise the model would go live with nowhere to route, which only a
    real user's failed request would ever reveal.
    """
    if not await admin_required(request):
        return _UNAUTHORIZED
    if async_session is None:
        return _NO_DB

    unknown = set(payload) - {'availability'}
    if unknown:
        return JSONResponse({'detail': f'فیلد ناشناخته: {", ".join(sorted(unknown))}'}, status_code=400)
    if 'availability' not in payload:
        return JSONResponse({'detail': 'فیلد availability الزامی است'}, status_code=400)
    availability = payload['availability']
    if availability not in _AVAILABILITY_VALUES:
        return JSONResponse(
            {'detail': f"availability باید یکی از این مقادیر باشد: {', '.join(_AVAILABILITY_VALUES)}"},
            status_code=400,
        )

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT key FROM logical_model WHERE key = :key'), {'key': key}
        )
        if not res.fetchone():
            return JSONResponse({'detail': 'مدل منطقی یافت نشد'}, status_code=404)

        if availability == 'available':
            chk = await session.execute(
                sqlalchemy.text(
                    """
                    SELECT COUNT(*) AS c FROM logical_model_candidate
                    WHERE logical_key = :key AND state = 'approved' AND enabled = true
                    """
                ),
                {'key': key},
            )
            if chk.fetchone().c == 0:
                return JSONResponse(
                    {'detail': 'این مدل منطقی هیچ گزینهٔ تأییدشده و فعالی ندارد؛ نمی‌توان آن را در دسترس قرار داد '
                               '(هیچ مسیری برای پاسخ‌دادن به کاربر وجود نخواهد داشت).'},
                    status_code=400,
                )

        await session.execute(
            sqlalchemy.text(
                'UPDATE logical_model SET availability = :availability, updated_at = now() WHERE key = :key'
            ),
            {'availability': availability, 'key': key},
        )
        await session.commit()

    await _write_audit_log(
        'admin.logical_model.availability_update', target_type='logical_model',
        target_id=key, details={'availability': availability}, request=request,
    )
    return JSONResponse({'status': 'ok', 'key': key, 'availability': availability})
