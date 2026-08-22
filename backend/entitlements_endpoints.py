"""
User-facing read endpoint for package entitlements (request/token quotas
granted by a purchased package, tracked separately from the Toman wallet
balance).

GET /entitlements returns the caller's own active, non-expired entitlements.
Auth follows the exact pattern used by api_keys.py (`_get_user_id` from
`dependencies`) -- never accepts a user id from the request, so a user can
only ever see their own entitlements.

Degrades cleanly: `services/entitlements.py` (and the table it reads from)
is being built concurrently by another agent and may not exist yet, or the
migration that creates its table may not have been applied yet even once
the module lands. Either failure mode must return an empty list, not a 500
-- a wallet page that 500s because a not-yet-launched feature isn't wired
up is worse than one that quietly shows nothing.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from dependencies import _get_user_id

router = APIRouter()


@router.get('/entitlements')
async def list_my_entitlements(request: Request) -> JSONResponse:
    """List the caller's own active, non-expired package entitlements.

    Each item carries at least: id, package_id, requests_remaining,
    tokens_remaining, max_cost_per_request_toman, expires_at. A `None` in
    requests_remaining/tokens_remaining means that dimension is not metered
    at all for this entitlement -- it must survive serialisation as JSON
    `null`, never be coerced to 0.
    """
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    try:
        # Imported lazily, inside the function: services/entitlements.py is
        # being written concurrently by another agent. A top-level import
        # here would make this whole module (and anything that imports it,
        # e.g. app.py) fail to import until that module lands, which would
        # break collection for the entire test suite -- not just this file.
        from services.entitlements import list_entitlements
    except ImportError:
        # The service module doesn't exist yet on this deploy.
        return JSONResponse([])

    try:
        rows = await list_entitlements(uid)
    except Exception:
        # The migration that creates the entitlements table may not have
        # run yet even once the service module itself is deployed (e.g.
        # "relation does not exist"), or any other backing-store hiccup.
        # None of that is the user's problem -- show an empty list instead
        # of a 500 on a page that otherwise works fine.
        return JSONResponse([])

    return JSONResponse(jsonable_encoder(rows))
