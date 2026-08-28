"""Admin surface for the smart-router acceptance probe
(services/router_probe.py -- read that module's docstring first, it carries
the full design rationale: two stages, three outcomes, why the worst
failure mode of the probe is the pre-feature status quo).

Two routes, mirroring admin_overhead.py's `upstream_prompt_overhead` idiom
exactly -- same shape, same auth gate, same "measure re-runs and overwrites
the stored map, get reads it back" split:

  * ``POST /admin/smart-router/probe`` -- runs `router_probe.run_probe_scan()`
    LIVE (up to 12 models x 4 calls each, ~15-25s timeout per call -- this
    can take a while) and overwrites the stored `app_setting` row.
  * ``GET /admin/smart-router/probe`` -- the currently stored result, or the
    empty/never-measured shape if it has never been run.

── Auth ─────────────────────────────────────────────────────────────────
Every handler below calls ``admin_required`` as its very first real action.
tests/test_admin_routes_require_auth.py walks the AST of every backend
module and fails any ``/admin`` handler that does not -- not optional, and
the POST route here fires real live upstream calls (small, but real, and up
to 48 of them per run), so leaving it open would let an anonymous caller
spend upstream money in a loop, exactly the class of incident that test
file exists to prevent.
"""
from __future__ import annotations

import logging

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from database import async_session
from dependencies import admin_required
from i18n import err
from services.router_probe import SETTING_KEY, _load_stored, run_probe_scan

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post('/admin/smart-router/probe')
async def measure_smart_router_probe(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)

    try:
        value = await run_probe_scan()
    except Exception as e:
        logger.warning(f'smart-router probe measure failed: {e}')
        return err(
            'اندازه‌گیری پروب روتر ممکن نشد',
            'Failed to run the router acceptance probe.', 500,
        )

    results = value.get('results') or {}
    ok_count = sum(1 for entry in results.values() if entry.get('ok'))
    return JSONResponse({
        'status': 'ok',
        'measured': len(results),
        'eligible': ok_count,
        'value': value,
    })


@router.get('/admin/smart-router/probe')
async def get_smart_router_probe(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'The database is unavailable.', 500)

    try:
        async with async_session() as session:
            stored = await _load_stored(session)
            res = await session.execute(
                sqlalchemy.text('SELECT updated_at FROM app_setting WHERE key = :k'),
                {'k': SETTING_KEY},
            )
            row = res.fetchone()
    except Exception as e:
        logger.warning(f'GET /admin/smart-router/probe: DB read failed: {e}')
        return err(
            'خطا در خواندن تنظیمات از پایگاه داده',
            'Failed to read settings from the database.', 500,
        )

    updated_at = row.updated_at.isoformat() if row is not None and row.updated_at else None
    return JSONResponse({'stored': stored, 'storedUpdatedAt': updated_at})
