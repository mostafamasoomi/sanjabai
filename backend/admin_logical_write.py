"""Write endpoints for `logical_model` / `logical_model_candidate` -- split
out of admin_logical.py purely to stay under the house 500-line cap. See
admin_logical.py's module docstring for the schema/product context (what a
"logical model" is, the guard rails on pinning/availability, and why every
enum field is checked against migration 0025's CHECK-constraint lists
before any SQL runs). Nothing about behaviour changed in this move: same
routes, same validation, same SQL, same Persian strings.

IMPORT CONTRACT -- read before moving anything again. `tests/test_admin_logical.py`
does `import admin_logical` and then `patch.object(admin_logical, 'admin_required', ...)`
and `patch.object(admin_logical, '_write_audit_log', ...)` around calls into
the endpoints defined in THIS file (update_candidate/update_routing/
update_availability). Python resolves a bare global name against the
*defining* module's namespace, not the importing one -- a plain
`from admin_logical import admin_required` here would bind the pre-patch
function object at import time and silently stop observing those patches
(this is documented as a live prior incident in chat_web.py's and
chat_search.py's own IMPORT CONTRACT sections). So `admin_logical` is
imported plainly at module scope here, and every one of
`admin_required`, `_write_audit_log`, `_unauthorized`, `_no_db`,
`_AVAILABILITY_VALUES`, `_ROUTING_POLICY_VALUES`, `_CANDIDATE_STATE_VALUES`
is read through `admin_logical.<name>` at CALL time below, never via
`from admin_logical import X`. Routes are registered on the same shared
router object the same way, via `@admin_logical.router.post(...)` (the
`admin_logical.router` APIRouter instance -- app.py:317 does
`from admin_logical import router as admin_logical_router` and only ever
sees that one object, so routes registered here show up on it exactly as
if they were still defined in admin_logical.py). This is safe against the
admin_logical.py <-> admin_logical_write.py circular import: nothing here
touches an `admin_logical` attribute until a function actually runs (route
registration itself is just decorating `admin_logical.router`, which
already exists by the time admin_logical.py imports this module at the
very bottom of its own file, after every name above is already defined).

Also carries forward admin_logical.py's per-call-Response discipline (see
its module docstring's "KNOWN TRAP" section on `_unauthorized`/`_no_db`
having previously been module-level singletons that GZipMiddleware mutated
in place): every response here is built fresh inside the function that
returns it, and `_unauthorized()`/`_no_db()` are called (never stored) for
the same reason.
"""
from __future__ import annotations

from typing import Any

import sqlalchemy
from fastapi import Request
from fastapi.responses import JSONResponse

from database import async_session
from i18n import err

import admin_logical


def _validate_candidate_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str | None, str | None]:
    cleaned: dict[str, Any] = {}
    if 'state' in payload:
        v = payload['state']
        if v not in admin_logical._CANDIDATE_STATE_VALUES:
            values = ', '.join(admin_logical._CANDIDATE_STATE_VALUES)
            return ({}, f"وضعیت گزینه باید یکی از این مقادیر باشد: {values}",
                    f"Candidate state must be one of: {values}")
        cleaned['state'] = v
    if 'enabled' in payload:
        v = payload['enabled']
        if not isinstance(v, bool):
            return {}, 'فعال/غیرفعال بودن گزینه باید true/false باشد', "The candidate's enabled flag must be true or false."
        cleaned['enabled'] = v
    if 'priority' in payload:
        v = payload['priority']
        if isinstance(v, bool) or not isinstance(v, int):
            return {}, 'اولویت باید عدد صحیح باشد', 'Priority must be an integer.'
        cleaned['priority'] = v
    return cleaned, None, None


@admin_logical.router.post('/admin/logical-models/{key}/candidates/{candidate_id}')
async def update_candidate(request: Request, key: str, candidate_id: int, payload: dict[str, Any]) -> JSONResponse:
    """Approve/reject a candidate (`state`), enable/disable it, and/or set
    its `priority` -- three fields on the same row, so one endpoint rather
    than three, but every change is still audit-logged with exactly what
    changed.
    """
    if not await admin_logical.admin_required(request):
        return admin_logical._unauthorized()
    if async_session is None:
        return admin_logical._no_db()

    unknown = set(payload) - {'state', 'enabled', 'priority'}
    if unknown:
        fields = ", ".join(sorted(unknown))
        return err(f'فیلد ناشناخته: {fields}', f'Unknown field: {fields}', 400)

    cleaned, fa_err, en_err = _validate_candidate_payload(payload)
    if fa_err:
        return err(fa_err, en_err, 400)
    if not cleaned:
        return err('هیچ فیلدی برای بروزرسانی ارسال نشده است', 'No fields were sent to update.', 400)

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
            return err('گزینه یافت نشد', 'Candidate not found.', 404)
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
            return err(
                'این گزینه هم‌اکنون به‌عنوان مسیر پین‌شدهٔ این مدل منطقی انتخاب شده است؛ '
                'ابتدا سیاست مسیریابی را تغییر دهید یا گزینهٔ دیگری را پین کنید.',
                "This candidate is currently pinned as this logical model's route; "
                'change the routing policy first, or pin a different candidate.',
                400,
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

    await admin_logical._write_audit_log(
        'admin.logical_candidate.update', target_type='logical_model_candidate',
        target_id=candidate_id, details={'logical_key': key, **cleaned}, request=request,
    )
    return JSONResponse({'status': 'ok', 'id': candidate_id, 'updated': cleaned})


@admin_logical.router.post('/admin/logical-models/{key}/routing')
async def update_routing(request: Request, key: str, payload: dict[str, Any]) -> JSONResponse:
    """Set `routing_policy` and/or `pinned_candidate_id`.

    `pinned_candidate_id` is a `model_catalog.id` (see module docstring),
    not a `logical_model_candidate.id` -- validated here against a live
    approved+enabled candidate for this exact `logical_key` before it is
    ever written, and a `routing_policy='pinned'` with no pin is rejected
    as meaningless rather than silently accepted.
    """
    if not await admin_logical.admin_required(request):
        return admin_logical._unauthorized()
    if async_session is None:
        return admin_logical._no_db()

    unknown = set(payload) - {'routing_policy', 'pinned_candidate_id'}
    if unknown:
        fields = ", ".join(sorted(unknown))
        return err(f'فیلد ناشناخته: {fields}', f'Unknown field: {fields}', 400)

    cleaned: dict[str, Any] = {}
    if 'routing_policy' in payload:
        v = payload['routing_policy']
        if v not in admin_logical._ROUTING_POLICY_VALUES:
            values = ', '.join(admin_logical._ROUTING_POLICY_VALUES)
            return err(
                f"سیاست مسیریابی باید یکی از این مقادیر باشد: {values}",
                f"Routing policy must be one of: {values}",
                400,
            )
        cleaned['routing_policy'] = v
    if 'pinned_candidate_id' in payload:
        v = payload['pinned_candidate_id']
        if v is not None and not isinstance(v, str):
            return err('شناسهٔ گزینهٔ پین‌شده باید رشته یا null باشد',
                       'The pinned candidate id must be a string or null.', 400)
        cleaned['pinned_candidate_id'] = v
    if not cleaned:
        return err('هیچ فیلدی برای بروزرسانی ارسال نشده است', 'No fields were sent to update.', 400)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM logical_model WHERE key = :key'), {'key': key}
        )
        current = res.fetchone()
        if not current:
            return err('مدل منطقی یافت نشد', 'Logical model not found.', 404)
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
                return err(
                    'گزینهٔ انتخاب‌شده برای پین باید برای همین مدل منطقی، تأییدشده (approved) '
                    'و فعال (enabled) باشد. پین‌کردن گزینهٔ رد‌شده یا غیرفعال تله‌ای است که فقط '
                    'وقتی کاربر واقعی به آن برسد آشکار می‌شود.',
                    'The candidate selected for pinning must be approved and enabled for this '
                    'exact logical model. Pinning a rejected or disabled candidate is a trap '
                    'that only surfaces once a real user hits it.',
                    400,
                )

        if effective.get('routing_policy') == 'pinned' and effective.get('pinned_candidate_id') is None:
            return err(
                'سیاست مسیریابی «پین‌شده» بدون انتخاب یک گزینهٔ پین معنا ندارد',
                "Routing policy 'pinned' has no meaning without selecting a pinned candidate.",
                400,
            )

        set_parts = [f'{f} = :{f}' for f in cleaned]
        set_parts.append('updated_at = now()')
        await session.execute(
            sqlalchemy.text(f"UPDATE logical_model SET {', '.join(set_parts)} WHERE key = :key"),
            {**cleaned, 'key': key},
        )
        await session.commit()

    await admin_logical._write_audit_log(
        'admin.logical_model.routing_update', target_type='logical_model',
        target_id=key, details=cleaned, request=request,
    )
    return JSONResponse({'status': 'ok', 'key': key, 'updated': cleaned})


@admin_logical.router.post('/admin/logical-models/{key}/availability')
async def update_availability(request: Request, key: str, payload: dict[str, Any]) -> JSONResponse:
    """Set a logical model's `availability`. Publishing it (`available`)
    requires at least one eligible (`approved` + `enabled`) candidate --
    otherwise the model would go live with nowhere to route, which only a
    real user's failed request would ever reveal.
    """
    if not await admin_logical.admin_required(request):
        return admin_logical._unauthorized()
    if async_session is None:
        return admin_logical._no_db()

    unknown = set(payload) - {'availability'}
    if unknown:
        fields = ", ".join(sorted(unknown))
        return err(f'فیلد ناشناخته: {fields}', f'Unknown field: {fields}', 400)
    if 'availability' not in payload:
        return err('فیلد availability الزامی است', 'The availability field is required.', 400)
    availability = payload['availability']
    if availability not in admin_logical._AVAILABILITY_VALUES:
        values = ', '.join(admin_logical._AVAILABILITY_VALUES)
        return err(
            f"availability باید یکی از این مقادیر باشد: {values}",
            f"availability must be one of: {values}",
            400,
        )

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT key FROM logical_model WHERE key = :key'), {'key': key}
        )
        if not res.fetchone():
            return err('مدل منطقی یافت نشد', 'Logical model not found.', 404)

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
                return err(
                    'این مدل منطقی هیچ گزینهٔ تأییدشده و فعالی ندارد؛ نمی‌توان آن را در دسترس قرار داد '
                    '(هیچ مسیری برای پاسخ‌دادن به کاربر وجود نخواهد داشت).',
                    'This logical model has no approved and enabled candidate; it cannot be made '
                    'available (there would be no route to answer a user).',
                    400,
                )

        await session.execute(
            sqlalchemy.text(
                'UPDATE logical_model SET availability = :availability, updated_at = now() WHERE key = :key'
            ),
            {'availability': availability, 'key': key},
        )
        await session.commit()

    await admin_logical._write_audit_log(
        'admin.logical_model.availability_update', target_type='logical_model',
        target_id=key, details={'availability': availability}, request=request,
    )
    return JSONResponse({'status': 'ok', 'key': key, 'availability': availability})
