"""Public read of admin-authored landing page overrides.

Architecture set by the senior for B-LAND phase 6: this module NEVER holds
the landing page's actual content. That stays exactly where it is today --
thirteen static TypeScript modules under
``frontend/components/landing/content/*.ts`` (api, capabilities, catalog,
comparison, constants, faq, features, footer, hero, nav, pricing, stats,
steps). This table (migration 0052, ``landing_content``) holds ONLY
per-module overrides. An empty table means "render every module exactly as
its static file says" -- the intended default, not a degraded state.

Companion to ``admin_landing.py`` (the ``/admin/landing/content`` write/
delete API, which imports ``ALLOWED_KEYS``, ``FROZEN_PATHS``,
``MAX_VALUE_BYTES``, ``frozen_conflicts`` and ``invalidate_cache`` from
here rather than duplicating them) and migration ``0052_landing_content.sql``.

Read semantics deliberately mirror ``content_catalog.py``'s
``/catalog/models``: a short Redis cache under ``cache:landing:content``
(same key-naming family as ``cache:catalog:models`` / ``cache:content:
features``, see ``i18n.py``'s module docstring), and -- unlike the admin
read side, which is a direct, un-cached DB read like
``admin_free_tier.py`` -- this endpoint FAILS OPEN. Any DB or Redis fault
answers ``{"data": {}, "updated_at": null}`` with a logged error rather
than a 500: a broken override store must degrade the landing page to
today's static content, never break it. It is reached from an
unauthenticated public route, so it must never surface a stack trace or a
5xx for a store that is allowed to be empty by design.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session, rds

logger = logging.getLogger(__name__)

router = APIRouter()

# The thirteen frontend/components/landing/content/*.ts module names. This
# is the ONLY thing standing between `landing_content` and becoming an
# unstructured key/value dump -- admin_landing.py refuses any other key on
# write with a 400. Not enforced by a DB CHECK constraint (see migration
# 0052's rationale) so a fourteenth landing module later is a one-line
# change here, not a new migration.
ALLOWED_KEYS = frozenset({
    'api', 'capabilities', 'catalog', 'comparison', 'constants', 'faq',
    'features', 'footer', 'hero', 'nav', 'pricing', 'stats', 'steps',
})

# ── Honest-labelling freeze ──────────────────────────────────────────────
#
# House rule: a numeric claim that comes from a live count (model counts,
# in particular -- docs/product-contract.md sec 4) must never become
# hand-editable, or the landing page could simply be told to lie. Reading
# every one of the thirteen content modules for a field fed by
# `useCatalog()`/`modelCount()` found FOUR such fields, in FOUR files (the
# packet named only stats.ts and constants.ts; comparison.ts, pricing.ts
# and faq.ts also carry one each and are included here for the same
# reason -- leaving them writable while stats.ts is frozen would still let
# the page contradict itself). ``constants.ts`` itself was checked and
# holds none (see below) -- it contains only two static business constants
# (a base URL and the minimum top-up label), neither one a live count.
#
# frozen_paths.ts:line -- reasoning:
#   frontend/components/landing/content/stats.ts:18 -- FA `items[0].value`
#     is `(count) => count != null ? faNum(count) : '-'` -- the live
#     "active models" number itself.
#   frontend/components/landing/content/comparison.ts:33 -- FA
#     `rows[0].sanjabai` is `(count) => ... ${faNum(count)} model...` --
#     restates the same live count in the comparison table's first row
#     (the file's own comment: "used to hardcode a fixed model count").
#   frontend/components/landing/content/pricing.ts:56 -- FA
#     `columns[1].features[3]` is `(count) => ... ${faNum(count)} model` --
#     the pay-as-you-go plan's "access to every N models" bullet.
#   frontend/components/landing/content/faq.ts:25-28 -- FA `items[0].a` is
#     a function of `count`, embedding the live number into the first FAQ
#     answer (the file's own comment: "used to hardcode a fixed model
#     count").
#
# What is intentionally NOT frozen, and why:
#   - stats.ts items[2].value, the literal string '0' for "monthly
#     subscription fee": a fixed product invariant (there is no
#     subscription), not a number derived from a live count. Freezing
#     every business-invariant number here would be a much larger
#     (and different) guard than "honest live-count labelling"; out of
#     scope for this packet.
#   - constants.ts (MIN_TOPUP_LABEL_FA/EN, API_BASE_URL): both are fixed
#     business constants, not live-counted claims -- no frozen path for
#     the "constants" key.
#   - Every other landing module (capabilities, catalog, footer, hero,
#     nav, steps, api, features): grepped for `faNum(`, `useCatalog`,
#     `modelCount` -- none reference the live catalog at all.
#
# NOTE: today's four source files export FUNCTIONS closed over the live
# count, not plain JSON -- there is no existing static export an override
# could slot into yet. The paths below describe the plausible future JSON
# shape (mirroring each module's existing array-of-objects literal) so
# this guard exists before the frontend consumes overrides at all, rather
# than being bolted on after the fact. Whichever later phase defines the
# exact wire contract must keep the live-computed value out of whatever a
# stored override can supply, however that contract ends up shaped -- this
# dict is a floor, not a promise that the eventual JSON matches it byte
# for byte.
FROZEN_PATHS: dict[str, tuple[str, ...]] = {
    'stats': ('items.0.value',),
    'comparison': ('rows.0.sanjabai',),
    'pricing': ('columns.1.features.3',),
    'faq': ('items.0.a',),
}

_CACHE_KEY = 'cache:landing:content'
_CACHE_TTL = 60  # seconds, deliberately short -- see admin_landing.py's
                 # explicit invalidate_cache() call on every accepted write.

# 64KB per override value. Generous for a JSON blob describing one landing
# section, small enough that nothing can turn this table into a document
# store by accident.
MAX_VALUE_BYTES = 64 * 1024


def path_value(value: Any, path: str) -> tuple[bool, Any]:
    """Walk a dot-separated path into a JSON-shaped Python value.

    A purely numeric segment indexes a list; any other segment indexes a
    dict key. Never raises -- any shape mismatch (missing key,
    out-of-range index, indexing into a scalar) is reported as simply "not
    found", which is the right answer for a freeze check: if the submitted
    JSON does not happen to carry that path at all, there is nothing to
    reject.
    """
    cur = value
    for part in path.split('.'):
        if isinstance(cur, list):
            if not part.lstrip('-').isdigit():
                return False, None
            idx = int(part)
            if idx < 0 or idx >= len(cur):
                return False, None
            cur = cur[idx]
        elif isinstance(cur, dict):
            if part not in cur:
                return False, None
            cur = cur[part]
        else:
            return False, None
    return True, cur


def frozen_conflicts(key: str, value: Any) -> list[str]:
    """Which of `key`'s frozen paths does the submitted `value` populate.

    Empty list means the write is clear to proceed as far as the
    honest-labelling rule is concerned.
    """
    return [p for p in FROZEN_PATHS.get(key, ()) if path_value(value, p)[0]]


async def invalidate_cache() -> None:
    """Drop the public GET cache. Called by admin_landing.py after every
    accepted write or delete so an admin's change is visible at once,
    instead of waiting out the 60s TTL."""
    try:
        await rds.delete(_CACHE_KEY)
    except Exception as e:
        logger.error('landing content cache invalidate failed: %s', e)


@router.get('/landing/content')
async def get_landing_content(request: Request) -> JSONResponse:
    """All current overrides, keyed by module name. Public, unauthenticated,
    no side effects. Only keys that have a stored override are present in
    `data` -- everything else, the caller renders from its own static
    fallback. Fails open to `{"data": {}, "updated_at": null}` on any DB or
    Redis fault (logged as an error, never raised) -- see module docstring.
    """
    try:
        cached = await rds.get(_CACHE_KEY)
        if cached:
            return JSONResponse(json.loads(cached))
    except Exception as e:
        logger.error('GET /landing/content cache read failed: %s', e)
        # Fall through to the DB read below rather than giving up here --
        # a Redis fault alone should not blank out working overrides.

    data: dict[str, Any] = {}
    updated_at = None
    try:
        if async_session is None:
            return JSONResponse({'data': {}, 'updated_at': None})
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                'SELECT key, value, updated_at FROM landing_content'
            ))
            for row in res.fetchall():
                m = row._mapping
                data[m['key']] = m['value']
                ts = m['updated_at']
                if ts is not None and (updated_at is None or ts > updated_at):
                    updated_at = ts
    except Exception as e:
        logger.error('GET /landing/content DB read failed: %s', e)
        return JSONResponse({'data': {}, 'updated_at': None})

    result = jsonable_encoder({'data': data, 'updated_at': updated_at})
    try:
        await rds.setex(_CACHE_KEY, _CACHE_TTL, json.dumps(result))
    except Exception as e:
        logger.error('GET /landing/content cache write failed: %s', e)
    return JSONResponse(result)
