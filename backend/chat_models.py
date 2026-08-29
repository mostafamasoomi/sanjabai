"""Model resolution and availability -- split out of chat.py (see chat.py's
module docstring for why).

Holds: upstream resolution (_get_model_upstream / _resolve_provider),
public_id canonicalization (_resolve_public_model), the safe default-model
lookup (_safe_default_model), and the "working model" allow-list
(get_working_models / is_working_model / _is_model_allowed).

MONKEYPATCH / SHARED-STATE CONTRACT -- read before touching this file:
tests reach into chat.py's namespace directly, not this module's, for both
patched functions (`chat_mod._resolve_provider = ...`,
`chat_mod._is_model_allowed = ...`, `chat_mod.async_session = ...`, etc. --
see test_provider_routing.py / test_chat_output_hygiene.py / etc.) AND raw
mutable cache state (`chat_mod._UPSTREAM_CACHE = {}`,
`chat_mod._WORKING_SET_CACHE = None`, `chat_mod._MODEL_RESOLVE_CACHE = {}` --
see test_provider_routing.py / test_public_model_ids.py). A function moved
here that read/wrote a plain module-level `global` would silently stop
seeing those resets/patches: the `global` would bind to *this* module's
namespace, not chat.py's, and the test's `chat_mod.X = ...` would only ever
touch a copy nobody reads. Every reference below to `async_session`, the
upstream/model-resolve caches, or another chat.py-owned name is therefore
resolved through `chat.<name>` at call time (never a bare name, never a
`from chat import X`), and `chat` itself is imported plainly at module
scope -- safe against the chat.py <-> chat_models.py circular import because
nothing here touches a `chat` attribute until a function actually runs, by
which point chat.py has finished executing.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time

import sqlalchemy

import chat

from providers import COMPLETION_TIMEOUT_SECONDS  # re-export: chat.py is at
# the 500-line house cap and takes this on its existing chat_models import
# line rather than adding one. Owned by providers.py.

logger = logging.getLogger('chat')  # keep all chat_*.py logs under the pre-split 'chat' logger name

# Working model set — DYNAMIC from the model_catalog DB table.
#
# The single source of truth is model_catalog (availability='available'). There
# is deliberately NO hardcoded fallback set here anymore (removed — see
# get_working_models() below for why). During a genuine DB outage, billing,
# reservations and session lookup are all down too, so a chat request cannot
# complete anyway; a hardcoded set bought no real resilience, it only widened
# the window in which a model an admin had withdrawn (availability != 'available')
# could still reach a user. Fail closed instead.

# Cache of model id -> upstream name ('litellm' / 'ninerouter' / ...), for
# models model_discovery.py tagged with a non-default upstream. Models an
# admin curated by hand (the whole pre-9Router catalog) have upstream=NULL
# and always fall through to providers.chat_provider() (litellm) below, so
# enabling 9Router for discovery never silently reroutes existing traffic --
# only models actually verified to exist behind it get sent there.
#
# The cache dict and its loaded-at timestamp (`chat._UPSTREAM_CACHE` /
# `chat._UPSTREAM_CACHE_LOADED_AT`) live on the `chat` module -- see this
# module's docstring for why.
_UPSTREAM_CACHE_TTL_SECONDS = 60
# Set while a refresh is already in flight, so concurrent requests that all
# see a stale cache at once don't all fire the same full-table query
# (thundering herd on cache expiry).
_UPSTREAM_CACHE_REFRESH_LOCK = asyncio.Lock()

# Known aliases for upstream names that predate/deviate from the registered
# providers.Provider names (e.g. a hand-run DB fix that used '9router'
# instead of the registered 'ninerouter'). Normalizing here means a stray
# non-canonical value in model_catalog.upstream degrades gracefully instead
# of silently falling back to litellm.
# Single source of truth: services/margin.py, beside FREE_UPSTREAMS -- the
# two are one decision, since a name the map does not normalise is a name
# FREE_UPSTREAMS will not match. Re-exported under the original private name
# so nothing that referenced it here has to change.
from services.margin import UPSTREAM_ALIASES as _UPSTREAM_ALIASES


async def _get_model_upstream(model_id: str) -> str | None:
    """Which named upstream (providers.Provider.name) serves this model, if any.

    Cached for _UPSTREAM_CACHE_TTL_SECONDS to avoid a full-table scan of
    model_catalog on every chat request. On a DB read failure, or while a
    refresh is already in flight, the previous cache is kept rather than
    cleared -- serving slightly-stale routing beats failing every request.
    """
    if chat.async_session is None:
        return chat._UPSTREAM_CACHE.get(model_id)

    now = _time.monotonic()
    if now - chat._UPSTREAM_CACHE_LOADED_AT < _UPSTREAM_CACHE_TTL_SECONDS:
        return chat._UPSTREAM_CACHE.get(model_id)

    if _UPSTREAM_CACHE_REFRESH_LOCK.locked():
        # Someone else is already refreshing; use what we have rather than
        # queuing up behind them.
        return chat._UPSTREAM_CACHE.get(model_id)

    async with _UPSTREAM_CACHE_REFRESH_LOCK:
        # Re-check: another request may have refreshed while we waited for
        # the lock.
        now = _time.monotonic()
        if now - chat._UPSTREAM_CACHE_LOADED_AT < _UPSTREAM_CACHE_TTL_SECONDS:
            return chat._UPSTREAM_CACHE.get(model_id)
        try:
            async with chat.async_session() as session:
                res = await session.execute(sqlalchemy.text(
                    "SELECT id, provider_model_id, upstream FROM model_catalog WHERE upstream IS NOT NULL"
                ))
                cache: dict[str, str] = {}
                for row in res.fetchall():
                    if row.upstream:
                        cache[str(row.id)] = row.upstream
                        cache[str(row.provider_model_id)] = row.upstream
                chat._UPSTREAM_CACHE = cache
                chat._UPSTREAM_CACHE_LOADED_AT = _time.monotonic()
        except Exception as e:
            logger.warning(f"_get_model_upstream DB read failed, keeping previous cache: {e}")
    return chat._UPSTREAM_CACHE.get(model_id)


# ── Public model id resolution ──────────────────────────────────
#
# migrations/0028_public_model_ids.sql adds model_catalog.public_id: a route
# -free public id (e.g. "sanjab/mistral-large") that never leaks the upstream
# prefix (bynara/, kr/, cc/, cx/, ag/, gemini-api/models/, nvidia/...) or the
# word "free". model_catalog.id and provider_model_id are UNCHANGED and must
# keep resolving indefinitely -- there is no deprecation window.
#
# THE HAZARD this exists to close: the incoming `model` string is forwarded
# verbatim to the upstream (LiteLLM/9router have never heard of `sanjab/*`,
# so an unresolved new id 502s) AND used verbatim as the price-lookup key in
# _record_usage (`WHERE provider_model_id = :mid`) -- an unresolved
# `sanjab/*` string MISSES that lookup and silently bills at the fallback
# CEILING rate. _resolve_public_model() must therefore run exactly once, as
# early as possible, at every chat/compare/smart-chat call site -- before the
# free-tier gate, before the wallet reservation, before validation, before
# the upstream call -- so everything downstream (routing, health, billing,
# free-tier bucketing, reservations, usage) stays keyed on the SAME
# provider_model_id it always was.
#
# Cached with the identical TTL/refresh-lock pattern as _UPSTREAM_CACHE
# above: invalidated purely by TTL expiry (no explicit invalidation call
# exists for _UPSTREAM_CACHE either), so a public_id an admin assigns takes
# effect within _MODEL_RESOLVE_CACHE_TTL_SECONDS without a restart.
_MODEL_RESOLVE_CACHE_TTL_SECONDS = 60
_MODEL_RESOLVE_REFRESH_LOCK = asyncio.Lock()

# One query, explicit ORDER BY: rnk=0 (public_id) beats rnk=1
# (provider_model_id) beats rnk=2 (id) whenever the same string could match
# more than one row/column (e.g. a stale bare id that happens to collide
# with someone else's public_id). The cache-build loop below keeps only the
# FIRST occurrence of each key, and rows arrive in rnk order, so precedence
# is enforced by this ORDER BY, not by accident of iteration/dict order.
_MODEL_RESOLVE_SQL = sqlalchemy.text(
    """
    SELECT key, provider_model_id FROM (
        SELECT public_id AS key, provider_model_id, 0 AS rnk
            FROM model_catalog WHERE public_id IS NOT NULL
        UNION ALL
        SELECT provider_model_id AS key, provider_model_id, 1 AS rnk
            FROM model_catalog WHERE provider_model_id IS NOT NULL
        UNION ALL
        SELECT id AS key, provider_model_id, 2 AS rnk
            FROM model_catalog WHERE id IS NOT NULL
    ) precedence
    ORDER BY rnk
    """
)


async def _resolve_public_model(model: str) -> str:
    """Canonicalize any model string (public_id, provider_model_id, or the
    legacy `id`) to model_catalog.provider_model_id -- the id routing,
    health, and billing have always been keyed on.

    Returns ``model`` unchanged when it matches nothing (an unknown model
    string must still fall through to the existing "not available" path
    instead of crashing) and when the DB is unreachable (fails open onto
    whatever was last cached, same as _get_model_upstream).

    Thin wrapper over :func:`_resolve_public_model_catalog` so that EVERY
    one of that function's five return paths -- not just the one after a
    cache refresh -- gets the logical-model fallback. Splitting it this way
    rather than editing each return in place is deliberate: the earlier
    shape had four early returns and it would have been easy to wire three
    of them and ship a flag that worked only on a cold cache.
    """
    return await _apply_logical_routing(model, await _resolve_public_model_catalog(model))


async def _resolve_public_model_catalog(model: str) -> str:
    """The catalog-only half of :func:`_resolve_public_model`, unchanged in
    behaviour from before the logical layer existed."""
    if not model:
        return model
    if chat.async_session is None:
        return chat._MODEL_RESOLVE_CACHE.get(model, model)

    now = _time.monotonic()
    if now - chat._MODEL_RESOLVE_CACHE_LOADED_AT < _MODEL_RESOLVE_CACHE_TTL_SECONDS:
        return chat._MODEL_RESOLVE_CACHE.get(model, model)

    if _MODEL_RESOLVE_REFRESH_LOCK.locked():
        # Someone else is already refreshing; use what we have rather than
        # queuing up behind them.
        return chat._MODEL_RESOLVE_CACHE.get(model, model)

    async with _MODEL_RESOLVE_REFRESH_LOCK:
        # Re-check: another request may have refreshed while we waited for
        # the lock.
        now = _time.monotonic()
        if now - chat._MODEL_RESOLVE_CACHE_LOADED_AT < _MODEL_RESOLVE_CACHE_TTL_SECONDS:
            return chat._MODEL_RESOLVE_CACHE.get(model, model)
        try:
            async with chat.async_session() as session:
                res = await session.execute(_MODEL_RESOLVE_SQL)
                cache: dict[str, str] = {}
                for row in res.fetchall():
                    if row.key and row.key not in cache:
                        cache[str(row.key)] = str(row.provider_model_id)
                chat._MODEL_RESOLVE_CACHE = cache
                chat._MODEL_RESOLVE_CACHE_LOADED_AT = _time.monotonic()
        except Exception as e:
            logger.warning(f"_resolve_public_model cache refresh failed, keeping previous cache: {e}")
    return chat._MODEL_RESOLVE_CACHE.get(model, model)


# ── Phase C P4: the logical model layer, behind a flag ──────────────────
#
# services/model_resolver.py has been complete and tested since the sixth
# session but was called from NOWHERE in production (re-verified by grep
# 2026-08-23). This is its one and only call site.
#
# It hangs off _resolve_public_model deliberately, because that function is
# already the single early canonicalization point every chat/compare/
# smart-chat path funnels through BEFORE the free-tier gate, the wallet
# reservation, validation and the upstream call. Resolving here means
# routing, health, free-tier bucketing, reservations and -- the financially
# load-bearing one -- _record_usage's price lookup all stay keyed on the
# same provider_model_id they always were. Resolving anywhere later would
# reintroduce exactly the unresolved-id-bills-the-ceiling-rate hazard the
# block above this function exists to document.
#
# SAFETY, in the order it matters:
#   1. Only consulted when the catalog matched NOTHING (resolved is model
#      unchanged). No model that routes today can be rerouted by this.
#   2. Flag defaults OFF (migration 0042). OFF is byte-for-byte the old
#      behaviour -- the phase's acceptance criterion.
#   3. resolve_logical_model() never raises and its None means "fall back",
#      so the worst case with the flag ON is the behaviour with it OFF.
#   4. It returns a model_catalog.id, NOT a provider_model_id, so the
#      result is run back through the same cache to canonicalize it. A
#      logical row pointing at a catalog id that is not in the cache is
#      discarded rather than forwarded upstream half-resolved.
async def _apply_logical_routing(model: str, resolved: str) -> str:
    """Try the logical layer for a model string the catalog did not know.

    Returns ``resolved`` untouched in every other case, including any
    failure -- this function never raises and never changes a model that
    already resolves.

    The "catalog did not know it" test is MEMBERSHIP in the resolve cache,
    not ``resolved != model``. Those are not the same thing: a caller that
    passes an already-canonical provider_model_id (``cc/claude-sonnet-5``)
    gets that same string back, so an equality test would classify a
    perfectly well-known model as unknown and send it through the logical
    layer on every request.
    """
    if not model or model in chat._MODEL_RESOLVE_CACHE:
        return resolved
    try:
        from site_settings import get_site_flag
        if not await get_site_flag('logical_routing_enabled'):
            return resolved
        from services.model_resolver import resolve_logical_model
        catalog_id = await resolve_logical_model(model)
        if not catalog_id:
            return resolved
        physical = chat._MODEL_RESOLVE_CACHE.get(str(catalog_id))
        if not physical:
            logger.warning(
                '_apply_logical_routing: logical key %r resolved to catalog id %r '
                'which is not in the resolve cache, falling back',
                model, catalog_id,
            )
            return resolved
        logger.info('_apply_logical_routing: %r -> %r -> %r', model, catalog_id, physical)
        return physical
    except Exception as e:
        logger.warning('_apply_logical_routing failed for %r, falling back: %s', model, e)
        return resolved


# FIX 3: the empty-model default used to be a hardcoded literal
# ('tencent-hy3'), which is not a real model_catalog row (the real ones are
# 'tencent-hy3-free'/'sanjab/tencent-hy3') -- a request with no `model`
# field was rejected by the exact default the code had just picked, with an
# error message suggesting the same broken literal. tasks.py's
# _default_model() (added this session for the identical class of bug in
# scheduled tasks) fixes it the right way: ask the catalog for the cheapest
# currently-available model with a public_id, never bake in a name that can
# rot. Reused here via a LAZY import (inside the function body, not at
# module load time) rather than duplicating the query, because tasks.py
# does `import chat as chat_mod` at its own module load time -- importing
# tasks.py back at chat.py's module load time would be circular. A lazy
# import has no such problem: by the time a request handler actually runs,
# both modules are already fully loaded.
async def _safe_default_model() -> str:
    """Resolve a real default model id when the client sends none at all.

    Returns '' (never a hardcoded literal) when the catalog is empty or
    unreachable -- callers must treat that as "no usable default" and
    reject the request rather than send an empty/garbage model string
    upstream (see the FINANCIAL RULE on _resolve_public_model above: an
    unresolved id misses the billing price lookup and bills the fallback
    ceiling rate).
    """
    try:
        from tasks import _default_model as _catalog_default_model
        return await _catalog_default_model()
    except Exception as e:
        logger.warning(f"_safe_default_model: catalog lookup failed: {e}")
        return ''


async def _resolve_provider(model_id: str):
    """The providers.Provider that should serve a chat completion for this model."""
    from providers import get_provider, chat_provider
    upstream = await _get_model_upstream(model_id)
    if upstream:
        p = get_provider(upstream)
        if p is None:
            alias = _UPSTREAM_ALIASES.get(upstream)
            if alias:
                p = get_provider(alias)
        if p:
            return p
        logger.warning(
            f"_resolve_provider: upstream={upstream!r} for model={model_id!r} did not "
            "resolve to a configured Provider; falling back to chat_provider() (litellm)"
        )
    return chat_provider()


async def get_working_models() -> frozenset[str]:
    """Return the set of model ids considered 'working' (available in catalog).

    Reads from model_catalog (availability='available'). Falls back to the
    last successful read (`chat._WORKING_SET_CACHE`) when the DB is
    unreachable, so a brief blip keeps serving whatever was last known good.

    There is NO hardcoded fallback set. On a cold cache (nothing has ever
    succeeded — e.g. right after startup, before the first catalog read) this
    returns an empty set, and every model is then rejected by
    is_working_model()/_is_model_allowed(). That is intentional: during a
    genuine DB outage, billing/reservations/session lookup are all down too,
    so a chat request can't complete anyway, and a hardcoded set only bought
    the risk of silently serving a model an admin had deliberately disabled.
    """
    if chat.async_session is None:
        fallback = frozenset(chat._WORKING_SET_CACHE or ())
        if not fallback:
            logger.error("get_working_models: async_session is None and cache is cold -- returning EMPTY working set, every model will be rejected")
        return fallback
    try:
        async with chat.async_session() as session:
            res = await session.execute(sqlalchemy.text(
                "SELECT provider_model_id, id, public_id FROM model_catalog "
                "WHERE availability = 'available' "
                # Honest labelling, defense-in-depth: `availability` alone
                # says nothing about whether this row has ever actually
                # answered a live probe (see content_catalog.py's identical
                # gate on the public catalog queries). last_ok_at IS NOT NULL
                # is ever-probed-OK, not a freshness window -- a freshness
                # gate here would mass-reject every chat request during a
                # prober outage, not just hide a listing.
                "AND EXISTS (SELECT 1 FROM model_health_state s "
                "WHERE (s.model_id = model_catalog.id OR s.model_id = model_catalog.provider_model_id) "
                "AND s.last_ok_at IS NOT NULL)"
            ))
            ids: set[str] = set()
            for row in res.fetchall():
                ids.add(str(row.provider_model_id))
                ids.add(str(row.id))
                if row.public_id:
                    ids.add(str(row.public_id))
            if ids:
                chat._WORKING_SET_CACHE = ids
                return frozenset(ids)
    except Exception as e:
        logger.warning(f"get_working_models DB read failed: {e}")
    fallback = frozenset(chat._WORKING_SET_CACHE or ())
    if not fallback:
        logger.error("get_working_models: DB read failed/empty and cache is cold -- returning EMPTY working set, every model will be rejected")
    return fallback


async def is_working_model(model_id: str) -> bool:
    """True if the model is available in the live catalog (or the fallback set)."""
    if not model_id:
        return False
    bare = model_id.split('/')[-1] if '/' in model_id else model_id
    working = await get_working_models()
    return bare in working or model_id in working


async def _is_model_allowed(model_id: str) -> bool:
    """Check if model is in the available catalog (dynamic from model_catalog).

    The working set is now sourced from model_catalog (availability='available').
    A model is allowed if it is present and available in the catalog, or if it
    falls back to the last-known-good cached set when the DB is unreachable
    (empty on a cold cache -- see get_working_models()).
    """
    if not model_id:
        return False
    # Strip provider prefix if present (e.g. bynara/tencent-hy3 -> tencent-hy3)
    bare = model_id.split('/')[-1] if '/' in model_id else model_id
    # Fast-path against the dynamic working set (DB-backed, hardcoded fallback)
    fast_path = await get_working_models()
    if bare in fast_path or model_id in fast_path:
        return True  # ponytail: skip redundant 2nd DB query; add when live-kill switch needed
    # Not in working set -> must be in DB available
    if chat.async_session is None:
        return False
    try:
        async with chat.async_session() as session:
            res = await session.execute(
                sqlalchemy.text(
                    "SELECT 1 FROM model_catalog WHERE (provider_model_id = :mid OR id = :mid OR public_id = :mid) "
                    "AND availability='available' "
                    # Same probe-history gate as get_working_models() above --
                    # required here too, not just there: this query is the
                    # DB fallback _is_model_allowed() falls through to on a
                    # working-set cache miss, and every chat/compare/smart-
                    # chat/document-generator call site gates on
                    # _is_model_allowed(), not get_working_models() directly.
                    # Gating only the cache and leaving this raw check
                    # ungated would make the working-set gate above a no-op
                    # in practice -- any never-probed-OK model would simply
                    # fall through to this query and still pass.
                    "AND EXISTS (SELECT 1 FROM model_health_state s "
                    "WHERE (s.model_id = model_catalog.id OR s.model_id = model_catalog.provider_model_id) "
                    "AND s.last_ok_at IS NOT NULL) "
                    "LIMIT 1"
                ),
                {'mid': model_id},
            )
            return res.fetchone() is not None
    except Exception as e:
        logger.warning(f"_is_model_allowed DB check failed model={model_id}: {e}")
        return False
