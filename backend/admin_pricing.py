"""Admin pricing endpoints: live model prices, model toggle, live-probe test.

Split out of admin.py (house 500-line cap) -- see admin.py's module
docstring for the full split map. Pure move: no behaviour change.

MONKEYPATCH CONTRACT: routes here gate on `admin.admin_required(request)`
(via a plain `import admin`, never `from admin import admin_required`) so
that `patch('admin.admin_required', ...)` in tests/test_admin_model_control.py
still works -- see admin.py's own module docstring for why.
"""
from __future__ import annotations

import os
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select

from database import async_session, rds
from models import Pricing
import admin
from dependencies import _write_audit_log
from services import margin, probe_gate

router = APIRouter()

#: Total wall-clock budget for the admin panel's «تست زنده», retry included.
#: Sized against the Next.js rewrite's hard 30s cap, not against the probe --
#: see the call site in test_model.
_ADMIN_PROBE_BUDGET_S = float(os.getenv('ADMIN_PROBE_BUDGET_S', '26'))

# MONKEYPATCH CONTRACT (second one, see the module docstring for the first):
# the guard is reached as `margin.refuse_if_loss_making`, never imported by
# name, so tests/test_margin_guard.py can patch the one symbol on
# services.margin and have every call site here follow it. Same contract
# for the probe guard, reached as `probe_gate.refuse_if_unprobed`.

# Money law: the internal unit is ALWAYS integer Toman, everywhere; a Rial
# conversion happens only inside the payment-gateway adapter (payment.py).
# model_catalog.currency's own CHECK constraint still permits 'IRR' (a
# schema leftover), but this admin surface must never be the place an
# admin mislabels a Toman price as something else, so it is pinned to the
# one value this product actually uses.
_ALLOWED_CURRENCY = 'IRT'


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
    return JSONResponse({'detail': refusal.detail}, status_code=400)


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
    return JSONResponse({'detail': refusal.detail}, status_code=400)


# ── Pricing admin ───────────────────────────────────────────────

@router.get('/admin/pricing')
async def list_pricing(request: Request) -> JSONResponse:
    """List live model prices. Source of truth = model_catalog (used by chat billing)."""
    if not await admin.admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            "SELECT id AS model, display_name, input_per_million, output_per_million, currency, "
            "usd_input_per_million, usd_output_per_million, availability "
            "FROM model_catalog ORDER BY display_name"
        ))
        rows = []
        for r in res.fetchall():
            rows.append({
                'model': r.model,
                'display_name': r.display_name,
                'input_per_million': int(r.input_per_million or 0),
                'output_per_million': int(r.output_per_million or 0),
                'currency': r.currency,
                'usd_input_per_million': r.usd_input_per_million,
                'usd_output_per_million': r.usd_output_per_million,
                'availability': r.availability,
            })
    return JSONResponse(jsonable_encoder(rows))


async def get_active_price(session, model_id: str) -> "Pricing | None":
    """Return the currently-active pricing version for *model_id*."""
    res = await session.execute(
        select(Pricing)
        .where(Pricing.model == model_id, Pricing.effective_to.is_(None))
        .order_by(Pricing.effective_from.desc(), Pricing.price_version.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


@router.post('/admin/pricing')
async def set_pricing(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Update live prices on model_catalog (the table chat billing actually reads)."""
    if not await admin.admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    model = payload.get('model')
    if not model:
        return JSONResponse({'detail': 'مدل الزامی است'}, status_code=400)
    try:
        input_pm = int(payload.get('input_per_million', 0))
        output_pm = int(payload.get('output_per_million', 0))
    except (TypeError, ValueError):
        return JSONResponse({'detail': 'قیمتها باید عدد صحیح باشند'}, status_code=400)
    currency = payload.get('currency', _ALLOWED_CURRENCY)
    if currency != _ALLOWED_CURRENCY:
        return JSONResponse(
            {'detail': f'واحد پول باید «{_ALLOWED_CURRENCY}» (تومان) باشد؛ این سامانه فقط تومان می‌فروشد.'},
            status_code=400,
        )
    async with async_session() as session:
        refused = await _refuse_loss_making(
            session, [model], request,
            input_per_million=input_pm, output_per_million=output_pm,
        )
        if refused is not None:
            return refused
        res = await session.execute(sqlalchemy.text(
            "UPDATE model_catalog SET input_per_million=:inp, output_per_million=:out, "
            "currency=:cur, updated_at=now() WHERE id=:m"
        ), {'inp': input_pm, 'out': output_pm, 'cur': currency, 'm': model})
        if res.rowcount == 0:
            return JSONResponse({'detail': 'مدل در کاتالوگ یافت نشد'}, status_code=404)
        await session.commit()
    await _write_audit_log('admin.pricing.set', target_type='model_catalog', target_id=model,
                           details={'input_per_million': input_pm, 'output_per_million': output_pm})
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'updated', 'model': model})


# `/toggle` is a quick single-click kill-switch between 'available' and
# 'disabled' only -- see its own docstring below. model_catalog.availability
# also has 'maintenance' (the vast majority of rows -- discovered but never
# promoted) and 'degraded' (probe partially failing), both owned by the
# background health mirror (model_health_policy.py._target_catalog_state),
# which only ever promotes a row to 'available' after a live probe *and* a
# price are both present ("مدل فقط بعد از پروب زنده موفق ارائه می‌شود"). A
# binary flip that treats "anything that isn't 'available'" as "should
# become 'available'" would let one misclick push an unprobed/parked model
# straight onto customers -- admin_catalog.py's bulk_set_availability
# already had to special-case this ("a bulk 'disable' must also correctly
# cover rows that start out maintenance or degraded"); this single-row
# endpoint never got the matching fix until now. `/admin/models/bulk-
# availability` (تب «عملیات کاتالوگ») is the correct tool for a
# maintenance/degraded row.
_TOGGLE_STATES = {'available', 'disabled'}
# Same Persian labels as the frontend's ModelsTab.tsx / PricingSection.tsx
# AVAILABILITY_FA -- one wording for this status across the whole panel.
_AVAILABILITY_FA = {'maintenance': 'تعمیرات', 'degraded': 'کاهش‌یافته'}


@router.post('/admin/models/{model_id:path}/toggle')
async def toggle_model(request: Request, model_id: str) -> JSONResponse:
    """Admin: flip a model between 'available' and 'disabled'.

    Same effect as the legacy admin/app.py toggle endpoints, exposed here so
    the React admin panel (the one actually in front of admins day-to-day)
    doesn't need the separate Jinja admin app just to kill a broken model.

    Uses the `:path` converter — the same fix as
    admin_catalog.py's set-upstream route — because most catalog ids
    (~96%) contain a literal `/` (e.g. "freellmapi/agnes-1.5-flash"), which
    a plain `{model_id}` segment never matches.
    """
    if not await admin.admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            'SELECT availability FROM model_catalog WHERE id = :id'
        ), {'id': model_id})
        row = res.fetchone()
        if row is None:
            return JSONResponse({'detail': 'مدل در کاتالوگ یافت نشد'}, status_code=404)
        if row.availability not in _TOGGLE_STATES:
            state_fa = _AVAILABILITY_FA.get(row.availability, row.availability)
            await _write_audit_log('admin.model.toggle_refused', target_type='model_catalog',
                                   target_id=model_id, details={'availability': row.availability}, request=request)
            return JSONResponse({'detail': (
                f'مدل «{model_id}» در وضعیت «{state_fa}» است. این کلید سریع فقط بین «فعال» و «غیرفعال» '
                'جابه‌جا می‌کند و برای این وضعیت معنا ندارد؛ فعال‌سازی مدلی که پروب زنده آن را تأیید '
                'نکرده ممنوع است -- برای تغییر وضعیت از تب «عملیات کاتالوگ» استفاده کنید.'
            )}, status_code=400)
        new_avail = 'disabled' if row.availability == 'available' else 'available'
        # Withdrawing a model can never be loss-making or dishonest; only
        # the flip that puts it back on sale is a margin decision AND an
        # honest-labelling decision (it must already have a confirmed live
        # probe -- see services/probe_gate.py).
        if new_avail == 'available':
            refused = await _refuse_unprobed(session, [model_id], request)
            if refused is not None:
                return refused
            refused = await _refuse_loss_making(session, [model_id], request)
            if refused is not None:
                return refused
        await session.execute(sqlalchemy.text(
            'UPDATE model_catalog SET availability = :a, updated_at = now() WHERE id = :id'
        ), {'a': new_avail, 'id': model_id})
        await session.commit()
    await _write_audit_log('admin.model.toggle', target_type='model_catalog', target_id=model_id,
                           details={'availability': new_avail})
    if rds:
        await rds.delete('cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing')
    return JSONResponse({'status': 'ok', 'model': model_id, 'availability': new_avail})


@router.post('/admin/models/{model_id:path}/test')
async def test_model(request: Request, model_id: str) -> JSONResponse:
    """Admin: send a minimal live probe to a model and report the result.

    Reuses providers.probe_model (the same probe model_health.py runs on a
    schedule) so "test now" in the admin panel and the status page's
    background health checks agree on what "working" means.

    The result is RECORDED, not just displayed. It used to be displayed only,
    which made this button the front half of a deadlock: services/probe_gate.py
    will not let a model be made `available` until `model_health_state.last_ok_at`
    is non-NULL, the panel told the admin to press this button first, and
    pressing it wrote nothing. See model_health.record_probe_sample.

    Retries a transient failure (a router cooldown quotes ~40s and then
    answers) before believing it — a button an admin presses by hand must not
    condemn a model on one unlucky moment. `:path` converter — see
    toggle_model above.
    """
    if not await admin.admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    from chat import _resolve_provider
    from model_health import record_probe_sample
    from providers import probe_model_resilient
    provider = await _resolve_provider(model_id)
    # budget_s: the browser reaches this through a Next.js rewrite that
    # hard-caps at 30s. 26 leaves the retry room to run after a fast 429
    # (~23s worst case end to end) and skips it after a slow failure, rather
    # than handing the admin a bare 500 for a probe that actually completed.
    result = await probe_model_resilient(provider, model_id, budget_s=_ADMIN_PROBE_BUDGET_S)
    await record_probe_sample(model_id, ok=result.ok, latency_ms=result.latency_ms,
                              error=result.error, provider=provider.name)
    await _write_audit_log('admin.model.test', target_type='model_catalog', target_id=model_id,
                           details={'ok': result.ok, 'latency_ms': result.latency_ms, 'error': result.error})
    return JSONResponse({
        'model': model_id,
        'upstream': provider.name,
        'ok': result.ok,
        'latency_ms': result.latency_ms,
        'error': result.error,
        'status_code': result.status_code,
    })


