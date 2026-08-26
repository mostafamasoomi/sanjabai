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
from i18n import err
from dependencies import admin_required, _write_audit_log

router = APIRouter()

_AVAILABILITY_VALUES = ('available', 'degraded', 'maintenance', 'disabled')
_ROUTING_POLICY_VALUES = ('cheapest_healthy', 'priority', 'pinned')
_CANDIDATE_STATE_VALUES = ('proposed', 'approved', 'rejected')

def _unauthorized() -> JSONResponse:
    """A FRESH 401 per call -- never one shared module-level Response.

    These two used to be module-level `JSONResponse` singletons. A Response is
    mutated in place as it goes back out through the middleware stack, so the
    same object accumulated state across requests: GZipMiddleware stamped
    `content-encoding: gzip` on it on the first unauthenticated hit and then
    handed the *uncompressed* body to every later one, and `vary` grew an
    extra `Accept-Encoding` each time. Reproduced live on the running API --
    four unauthenticated GETs of /admin/logical-models returned one clean 401
    followed by three `httpx.DecodingError`s, i.e. the client cannot read the
    401 at all. It was live, not latent: this router is registered in app.py
    (line 355), not in admin.py, so grepping admin.py for it finds nothing.

    Same defect and same fix as admin_moderation.py::_denied().
    """
    return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)


def _no_db() -> JSONResponse:
    """A fresh 500 per call -- see :func:`_unauthorized`."""
    return err('پایگاه داده در دسترس نیست', 'The database is unavailable.', 500)


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
        return _unauthorized()
    if async_session is None:
        return _no_db()

    qp = request.query_params
    q = (qp.get('q') or '').strip()
    availability = qp.get('availability') or ''
    if availability and availability not in _AVAILABILITY_VALUES:
        return err('مقدار availability نامعتبر است', 'Invalid availability value.', 400)
    pending_only = (qp.get('pending_only') or '').lower() in ('1', 'true', 'yes')
    page = max(1, int(qp.get('page', 1)))
    limit = min(max(1, int(qp.get('limit', 50))), 200)
    offset = (page - 1) * limit

    params = {'q': q, 'qlike': f'%{q}%', 'availability': availability}

    # WHERE, not HAVING: the GROUP BY lives inside the subquery, so the outer
    # query is ungrouped — HAVING here made Postgres treat the whole result as
    # one aggregate group and reject the bare `proposed_count` column
    # (GroupingError, endpoint returned 500 on every call; caught by the live
    # smoke of session 11 — the mocked-session tests can't see SQL errors).
    having = "WHERE (:pending_only = false OR proposed_count > 0)"
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
        return _unauthorized()
    if async_session is None:
        return _no_db()

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT * FROM logical_model WHERE key = :key'), {'key': key}
        )
        model_row = res.fetchone()
        if not model_row:
            return err('مدل منطقی یافت نشد', 'Logical model not found.', 404)
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


# ── Write endpoints (admin_logical_write.py) ──────────────────────────
# update_candidate / update_routing / update_availability physically live
# in admin_logical_write.py now, purely to stay under the house 500-line
# cap -- imported here (after every name it needs by late-binding through
# `admin_logical.<name>` -- router, admin_required, _write_audit_log,
# _unauthorized, _no_db, _AVAILABILITY_VALUES, _ROUTING_POLICY_VALUES,
# _CANDIDATE_STATE_VALUES -- is already defined above) so the routes
# register on THIS module's `router` object and the names stay importable
# from `admin_logical` for anything that still expects them here. See
# admin_logical_write.py's IMPORT CONTRACT before moving anything again.
from admin_logical_write import (  # noqa: F401,E402
    _validate_candidate_payload,
    update_candidate,
    update_routing,
    update_availability,
)
