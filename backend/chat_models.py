"""Model resolution and availability -- split out of chat.py (see chat.py's
module docstring for why).

Holds: upstream resolution (_get_model_upstream / _resolve_provider),
public_id canonicalization (_resolve_public_model), the safe default-model
lookup (_safe_default_model), and the "working model" allow-list
(get_working_models / is_working_model / _is_model_allowed / WORKING_MODELS
/ _HARDCODED_WORKING).

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

logger = logging.getLogger('chat')  # keep all chat_*.py logs under the pre-split 'chat' logger name

# Working model set — now DYNAMIC from the model_catalog DB table.
#
# The single source of truth is model_catalog (availability='available'). When the
# DB is unavailable we fall back to this verified hardcoded set so the service keeps
# working. See get_working_models() / is_working_model() below.
_HARDCODED_WORKING: frozenset[str] = frozenset({
    'tencent-hy3', 'mistral-large', 'mistral-medium-3-5',
    'deepseek-v4-pro', 'deepseek-v4-flash-bynara', 'deepseek-v4-pro-bynara',
    'mimo-v2.5-pro', 'mimo-v2.5-pro-ultraspeed',
})

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
_UPSTREAM_ALIASES = {
    '9router': 'ninerouter',
    'nine_router': 'ninerouter',
    'omni': 'omniroute',
    'omni_route': 'omniroute',
}


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
    """
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
    hardcoded verified set when the DB is unreachable so the service degrades
    gracefully instead of rejecting every request.
    """
    if chat.async_session is None:
        return _HARDCODED_WORKING
    try:
        async with chat.async_session() as session:
            res = await session.execute(sqlalchemy.text(
                "SELECT provider_model_id, id, public_id FROM model_catalog WHERE availability = 'available'"
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
    return frozenset(chat._WORKING_SET_CACHE or _HARDCODED_WORKING)


async def is_working_model(model_id: str) -> bool:
    """True if the model is available in the live catalog (or the fallback set)."""
    if not model_id:
        return False
    bare = model_id.split('/')[-1] if '/' in model_id else model_id
    working = await get_working_models()
    return bare in working or model_id in working


# Backwards-compatible alias (deprecated — prefer is_working_model()).
WORKING_MODELS = _HARDCODED_WORKING


async def _is_model_allowed(model_id: str) -> bool:
    """Check if model is in the available catalog (dynamic from model_catalog).

    The working set is now sourced from model_catalog (availability='available').
    A model is allowed if it is present and available in the catalog, or if it
    falls back to the verified hardcoded set when the DB is unreachable.
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
                    "SELECT 1 FROM model_catalog WHERE (provider_model_id = :mid OR id = :mid OR public_id = :mid) AND availability='available' LIMIT 1"
                ),
                {'mid': model_id},
            )
            return res.fetchone() is not None
    except Exception as e:
        logger.warning(f"_is_model_allowed DB check failed model={model_id}: {e}")
        return False
