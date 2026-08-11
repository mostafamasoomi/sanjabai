"""
Chat endpoints — aggregator.

The implementations live in one module per domain (this file used to hold all
of them inline, well past the project's 500-line ceiling):

  chat_common.py   – request/response models, file-size cap, shared helpers
  chat_billing.py  – usage tracking, wallet/quota charging, reservation release
  chat_stream.py   – SSE streaming for /v1/chat/completions
  chat_tools.py    – web search grounding and file-text extraction
  chat_smart.py    – smart-chat model selection + /v1/smart-chat endpoint
  chat_compare.py  – /v1/compare side-by-side model evaluation
  chat_routes.py   – /v1/chat/completions and /v1/chat/with-file

``router`` below aggregates all of them, so ``from chat import router`` keeps
mounting the exact same set of paths it always did.

The model-selection core (_resolve_provider, _get_model_upstream, the working
set, the caches) lives *here* rather than in a domain module: tests patch
``chat.async_session`` / ``chat._UPSTREAM_CACHE`` and expect
``chat._resolve_provider`` to observe those patches, so the code that reads
them must stay in this module (see tests/test_provider_routing.py). The domain
modules import these helpers lazily inside their functions (the same pattern
admin_catalog.py and security.py already use for ``chat._resolve_provider`` /
``chat._get_user_plan``).
"""
from __future__ import annotations

import logging

import sqlalchemy
from fastapi import APIRouter

from database import async_session, _http

# ── Re-exported helpers from domain modules ──────────────────────
# These names are importable from ``chat`` for backward compatibility with
# code and tests that do ``from chat import <name>``.
from chat_billing import (  # noqa: F401
    _record_usage,
    _track_usage,
    _bill_stream_usage,
    _release_reservation,
    _check_quota_pre,
)
from chat_common import (  # noqa: F401
    ChatRequest,
    CompareRequest,
    MAX_FILE_SIZE,
    _fire_memory_extraction,
    _record_model_health,
    _HEALTH_TASKS,
)
from chat_stream import _chat_stream  # noqa: F401
from chat_tools import _web_search, _extract_file_text  # noqa: F401
from chat_smart import (  # noqa: F401
    _smart_chat_stream,
    _analyze_message,
    _get_user_balance,
    _get_user_plan,
    _select_smart_model,
    _select_smart_model_safe,
)

logger = logging.getLogger(__name__)

# ── Model-routing core ──────────────────────────────────────────
# These are defined here (not in a domain module) because tests directly
# patch ``chat.async_session`` and ``chat._UPSTREAM_CACHE`` and expect
# ``chat._resolve_provider`` to see those patches at call time.

# Working model set — now DYNAMIC from the model_catalog DB table.
#
# The single source of truth is model_catalog (availability='available'). When the
# DB is unavailable we fall back to this verified hardcoded set so the service keeps
# working. See get_working_models() / is_working_model() below.
_HARDCODED_WORKING = frozenset({
    'tencent-hy3', 'mistral-large', 'mistral-medium-3-5',
    'deepseek-v4-pro', 'deepseek-v4-flash-bynara', 'deepseek-v4-pro-bynara',
    'mimo-v2.5-pro', 'mimo-v2.5-pro-ultraspeed',
})

# Cache of available model ids (refreshed on each call when DB is reachable).
_WORKING_SET_CACHE: set[str] | None = None

# Cache of model id -> upstream name ('litellm' / 'ninerouter' / ...), for
# models model_discovery.py tagged with a non-default upstream. Models an
# admin curated by hand (the whole pre-9Router catalog) have upstream=NULL
# and always fall through to providers.chat_provider() (litellm) below, so
# enabling 9Router for discovery never silently reroutes existing traffic —
# only models actually verified to exist behind it get sent there.
_UPSTREAM_CACHE: dict[str, str] = {}


async def _get_model_upstream(model_id: str) -> str | None:
    """Which named upstream (providers.Provider.name) serves this model, if any."""
    global _UPSTREAM_CACHE
    if async_session is None:
        return _UPSTREAM_CACHE.get(model_id)
    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                "SELECT id, provider_model_id, upstream FROM model_catalog WHERE upstream IS NOT NULL"
            ))
            cache: dict[str, str] = {}
            for row in res.fetchall():
                if row.upstream:
                    cache[str(row.id)] = row.upstream
                    cache[str(row.provider_model_id)] = row.upstream
            _UPSTREAM_CACHE = cache
    except Exception as e:
        logger.warning(f"_get_model_upstream DB read failed: {e}")
    return _UPSTREAM_CACHE.get(model_id)


async def _resolve_provider(model_id: str):
    """The providers.Provider that should serve a chat completion for this model."""
    from providers import get_provider, chat_provider
    upstream = await _get_model_upstream(model_id)
    if upstream:
        p = get_provider(upstream)
        if p:
            return p
    return chat_provider()


async def get_working_models() -> frozenset[str]:
    """Return the set of model ids considered 'working' (available in catalog).

    Reads from model_catalog (availability='available'). Falls back to the
    hardcoded verified set when the DB is unreachable so the service degrades
    gracefully instead of rejecting every request.
    """
    global _WORKING_SET_CACHE
    if async_session is None:
        return _HARDCODED_WORKING
    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                "SELECT provider_model_id, id FROM model_catalog WHERE availability = 'available'"
            ))
            ids: set[str] = set()
            for row in res.fetchall():
                ids.add(str(row.provider_model_id))
                ids.add(str(row.id))
            if ids:
                _WORKING_SET_CACHE = ids
                return frozenset(ids)
    except Exception as e:
        logger.warning(f"get_working_models DB read failed: {e}")
    return frozenset(_WORKING_SET_CACHE or _HARDCODED_WORKING)


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
    if async_session is None:
        return False
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text(
                    "SELECT 1 FROM model_catalog WHERE (provider_model_id = :mid OR id = :mid) AND availability='available' LIMIT 1"
                ),
                {'mid': model_id},
            )
            return res.fetchone() is not None
    except Exception as e:
        logger.warning(f"_is_model_allowed DB check failed model={model_id}: {e}")
        return False


# ── Router aggregation ──────────────────────────────────────────

import chat_routes   # noqa: E402
import chat_compare   # noqa: E402
import chat_smart     # noqa: E402

_DOMAIN_MODULES = (
    chat_routes,
    chat_compare,
    chat_smart,
)

router = APIRouter()
for _mod in _DOMAIN_MODULES:
    router.include_router(_mod.router)
del _mod
