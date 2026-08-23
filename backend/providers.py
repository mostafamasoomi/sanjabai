"""
Upstream provider adapters.

The gateway talks to one or more OpenAI-compatible upstreams. Historically that
was a single hard-coded LiteLLM host read straight out of `database.LITELLM_HOST`
at every call site. This module puts a thin, uniform surface in front of them so
that model discovery and health probing do not care which upstream they are
speaking to, and so a second upstream can be added by configuration rather than
by editing call sites.

Two providers ship today:

    litellm      the existing LiteLLM host (proxies Bynara)
    ninerouter   9Router, a self-hosted OpenAI-compatible gateway that defaults
                 to port 20128 and exposes an unauthenticated GET /api/health
                 *outside* the /v1 prefix (measured directly against the
                 upstream: /health, /healthz, /v1/health and /status all 404;
                 only /api/health answers, with {"ok":true})

Both speak the same three operations we need: list models, probe a model, and
report whether the upstream itself is reachable.

Chat traffic still flows through whichever provider `CHAT_PROVIDER` names
(default: litellm). Discovery and health probing always cover every enabled
provider, so 9Router can be observed in production before any user traffic is
pointed at it.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from database import _http, LITELLM_HOST

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


@dataclass(frozen=True)
class Provider:
    """A configured OpenAI-compatible upstream."""

    name: str
    #: Origin without a trailing slash, e.g. "http://9router:20128".
    base_url: str
    api_key: str
    #: Path of an unauthenticated liveness endpoint, relative to base_url.
    #: None when the upstream has no such endpoint and we must fall back to
    #: listing models to decide whether it is up.
    health_path: str | None = None

    @property
    def v1(self) -> str:
        return f'{self.base_url}/v1'

    def headers(self) -> dict[str, str]:
        h = {'Content-Type': 'application/json'}
        if self.api_key:
            h['Authorization'] = f'Bearer {self.api_key}'
        return h


# ── openrouter_enabled DB flag: sync/async bridge ────────────────────────
#
# configured_providers() below is a plain synchronous function called from
# both sync and async call sites throughout the codebase (see the comment
# at its OpenRouter branch). site_settings.get_site_flag() is async. Inside
# a running event loop there is no safe way to just `await` it from sync
# code, and blocking with asyncio.run()/run_until_complete() is worse than
# unsafe here -- configured_providers() is typically called FROM a
# coroutine already executing on the one running loop (a FastAPI request
# handler), so run_until_complete() would raise ("this event loop is
# already running") or, on a version that permitted nesting, would stall
# every other coroutine on that loop for the DB round-trip. Silently
# skipping the DB check instead would defeat the point of this feature.
#
# Instead: a tiny process-local cache with a short TTL, refreshed
# fire-and-forget by scheduling a background task on the running loop (if
# one exists) whenever it goes stale. Each call to
# _openrouter_db_flag_enabled() returns the CURRENT cached value
# immediately (never blocks) and may schedule a refresh for next time.
# Starts at False (fail-safe -- matches get_site_flag's own default for
# this flag) so a cold cache never enables OpenRouter on an unconfirmed
# read; a refresh failure leaves the last known-good value in place, i.e.
# falls back to whatever env-var-only behaviour already had it at.
_OPENROUTER_FLAG_CACHE_TTL_SECONDS = 5.0

_openrouter_flag_cache: dict[str, Any] = {
    'value': False,
    'checked_at': 0.0,
    'refreshing': False,
}


async def _refresh_openrouter_db_flag() -> None:
    """Populate ``_openrouter_flag_cache`` from the DB. Never raises."""
    try:
        from site_settings import get_site_flag
        value = await get_site_flag('openrouter_enabled')
        _openrouter_flag_cache['value'] = value
        _openrouter_flag_cache['checked_at'] = time.monotonic()
    except Exception as e:
        logger.warning(
            f"providers: openrouter_enabled DB flag refresh failed, "
            f"keeping last known value ({_openrouter_flag_cache['value']}): {e}"
        )
        # Still bump checked_at so a persistently-failing DB doesn't retry
        # on literally every single call to configured_providers().
        _openrouter_flag_cache['checked_at'] = time.monotonic()
    finally:
        _openrouter_flag_cache['refreshing'] = False


def _openrouter_db_flag_enabled() -> bool:
    """Non-blocking, best-effort read of the ``openrouter_enabled`` DB flag.

    Returns the last cached value immediately. If the cache is stale and a
    refresh isn't already in flight, schedules one on the currently running
    event loop (if any) for next time -- never awaits it here, never blocks.
    """
    now = time.monotonic()
    stale = (now - _openrouter_flag_cache['checked_at']) > _OPENROUTER_FLAG_CACHE_TTL_SECONDS
    if stale and not _openrouter_flag_cache['refreshing']:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            _openrouter_flag_cache['refreshing'] = True
            loop.create_task(_refresh_openrouter_db_flag())
        # else: no running loop (e.g. import time, a plain sync script) --
        # nothing safe to do; keep serving the last cached value.
    return bool(_openrouter_flag_cache['value'])


def configured_providers() -> list[Provider]:
    """Every upstream that is enabled in the environment.

    LiteLLM is always present because the chat path depends on it. 9Router is
    opt-in so that a deployment without one configured does not spend every
    probe cycle failing to connect to a host that was never meant to exist.
    """
    providers = [
        Provider(
            name='litellm',
            base_url=LITELLM_HOST.rstrip('/'),
            api_key=os.getenv('LITELLM_API_KEY', '') or os.getenv('LITELLM_MASTER_KEY', ''),
            # LiteLLM's /health requires the master key, so it is not usable as
            # an anonymous liveness check; fall back to listing models.
            health_path=None,
        ),
    ]


    omni_url = os.getenv('OMNIROUTER_URL', '').strip()
    if omni_url:
        providers.append(
            Provider(
                name='omniroute',
                base_url=omni_url.rstrip('/'),
                api_key=os.getenv('OMNIROUTER_API_KEY', ''),
                health_path=None,
            )
        )
    elif _env_flag('OMNIROUTER_ENABLED'):
        # OMNIROUTER_ENABLED was set but OMNIROUTER_URL was not. There used to
        # be a hard-coded Docker-bridge IP fallback here; this repo is public,
        # so that literal is gone. Skip registering the provider rather than
        # silently pointing at a host that may not exist on this deployment.
        logger.warning(
            "OMNIROUTER_ENABLED is set but OMNIROUTER_URL is empty; "
            "the omniroute provider will NOT be registered. Set OMNIROUTER_URL "
            "to enable it."
        )
    nine_url = os.getenv('NINEROUTER_URL', '').strip()
    if nine_url or _env_flag('NINEROUTER_ENABLED'):
        providers.append(
            Provider(
                name='ninerouter',
                base_url=(nine_url or 'http://9router:20128').rstrip('/'),
                api_key=os.getenv('NINEROUTER_API_KEY', ''),
                # 9Router serves GET /api/health unauthenticated, outside /v1.
                # (/health, /healthz, /v1/health and /status all 404 -- verified
                # against the live upstream; only /api/health answers 200.)
                health_path='/api/health',
            )
        )

    # OpenRouter: registered as a `provider` row (see migration
    # 0024_openrouter_provider.sql) with enabled=false by default.
    #
    # NOTE: OPENROUTER_API_KEY is already present in this deployment's .env
    # for an unrelated purpose (services/embeddings.py uses it as a fallback
    # embeddings backend, and content.py reads OpenRouter's public pricing
    # without needing a key at all). Gating solely on "is the key set" would
    # therefore silently turn OpenRouter into a live, probed, discoverable
    # chat upstream the moment this code ships — not what "disabled by
    # default" means. A second, explicit switch (OPENROUTER_ENABLED) is
    # required in addition to the key, mirroring the opt-in pattern already
    # used for 9Router/OmniRoute above. A key with the flag off — or the flag
    # on with no key — is skipped quietly rather than erroring.
    #
    # The switch itself is now env var OR the `openrouter_enabled` DB flag
    # (site_settings.py) -- see _openrouter_db_flag_enabled() below for why
    # that needs its own small cache rather than a plain `await`: this
    # function is synchronous and called from both sync and async call
    # sites (admin_monitoring.py, model_health_api.py, admin_catalog.py,
    # provider_catalog.py, model_discovery.py, model_health.py). Whatever
    # the DB read does, the API key requirement above is untouched -- the
    # flag only ever adds a second way to say "on", never a way to skip the
    # key check.
    if _env_flag('OPENROUTER_ENABLED') or _openrouter_db_flag_enabled():
        openrouter_key = os.getenv('OPENROUTER_API_KEY', '').strip()
        if openrouter_key:
            providers.append(
                Provider(
                    name='openrouter',
                    base_url=os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api').rstrip('/'),
                    api_key=openrouter_key,
                    health_path=None,
                )
            )
    return providers


def get_provider(name: str) -> Provider | None:
    for p in configured_providers():
        if p.name == name:
            return p
    return None


def chat_provider() -> Provider:
    """The upstream that user chat traffic is routed to.

    Defaults to litellm so that enabling 9Router for discovery and health does
    not silently move the billing path onto an unproven upstream.
    """
    name = os.getenv('CHAT_PROVIDER', 'litellm').strip().lower()
    return get_provider(name) or get_provider('litellm')  # type: ignore[return-value]


# ── Operations ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    latency_ms: int
    #: Short, log-safe reason. Never contains response bodies or keys.
    error: str | None = None
    status_code: int | None = None


async def upstream_alive(p: Provider, timeout: float = 5.0) -> ProbeResult:
    """Is the upstream process itself reachable?

    Distinct from per-model health: if this fails, every model behind it will
    fail too, and the status page should say the gateway is down rather than
    listing twenty-three individually broken models.
    """
    started = time.monotonic()
    try:
        if p.health_path:
            r = await _http.get(f'{p.base_url}{p.health_path}', timeout=timeout)
        else:
            r = await _http.get(f'{p.v1}/models', headers=p.headers(), timeout=timeout)
        elapsed = int((time.monotonic() - started) * 1000)
        if r.status_code >= 400:
            return ProbeResult(False, elapsed, f'http_{r.status_code}', r.status_code)
        return ProbeResult(True, elapsed, None, r.status_code)
    except Exception as e:
        elapsed = int((time.monotonic() - started) * 1000)
        return ProbeResult(False, elapsed, type(e).__name__)


async def list_models(p: Provider, timeout: float = 10.0) -> list[dict[str, Any]]:
    """GET /v1/models, normalised to a list of dicts with at least an `id`.

    Returns an empty list rather than raising: discovery runs on a schedule and
    one unreachable upstream must not abort the sync for the others.
    """
    try:
        r = await _http.get(f'{p.v1}/models', headers=p.headers(), timeout=timeout)
        if r.status_code >= 400:
            return []
        body = r.json()
    except Exception:
        return []

    data = body.get('data') if isinstance(body, dict) else body
    if not isinstance(data, list):
        return []

    out: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, str):
            out.append({'id': item})
        elif isinstance(item, dict) and item.get('id'):
            out.append(item)
    return out


async def probe_model(p: Provider, model_id: str, timeout: float = 20.0) -> ProbeResult:
    """Send the smallest possible completion to check a model actually answers.

    `max_tokens=1` keeps the cost of a probe to a single output token. A 4xx
    that is clearly about the request rather than the model (401/403) is
    reported as a provider-level failure by the caller, not as the model being
    broken.
    """
    payload = {
        'model': model_id,
        'messages': [{'role': 'user', 'content': 'ping'}],
        'max_tokens': 1,
        'temperature': 0,
        'stream': False,
    }
    started = time.monotonic()
    try:
        r = await _http.post(
            f'{p.v1}/chat/completions',
            json=payload,
            headers=p.headers(),
            timeout=timeout,
        )
        elapsed = int((time.monotonic() - started) * 1000)
        if r.status_code >= 400:
            return ProbeResult(False, elapsed, f'http_{r.status_code}', r.status_code)
        body = r.json()
        # A 200 with no choices is a broken upstream pretending to succeed.
        if not body.get('choices'):
            return ProbeResult(False, elapsed, 'empty_choices', r.status_code)
        return ProbeResult(True, elapsed, None, r.status_code)
    except asyncio.TimeoutError:
        return ProbeResult(False, int((time.monotonic() - started) * 1000), 'timeout')
    except Exception as e:
        return ProbeResult(False, int((time.monotonic() - started) * 1000), type(e).__name__)


# ── kr/ cost signal ─────────────────────────────────────────────────────
#
# `kr/` routes report a credit cost alongside the token counts. It is a
# COST signal in the upstream's own credit unit -- NOT Toman, never a
# charge, never anything the ledger sees -- recorded on usage_events.meta
# so cost analysis can compare what a request earned against what it cost.
#
# ⚠️ The wire shape is UNVERIFIED: a live probe of the upstream was blocked
# by this session's permission policy, so the real key and nesting were
# never observed. Hence several plausible spellings and one nested vendor
# block, and hence the one-shot shape log below: an unrecognised `kr/`
# usage block reports its KEYS once per model, which is how the real
# spelling gets discovered from production without a log line per request.
# A response without the field is ordinary -- silent, no warning, no
# billing effect whatsoever.
_KIRO_ROUTE_PREFIX = 'kr/'
_KIRO_CREDIT_KEYS = ('kiro_credits', 'kiroCredits', 'credits')
_KIRO_NESTED_KEYS = ('kiro', 'metadata', 'vendor', 'provider_metadata')

#: model ids whose unrecognised usage shape has already been logged once.
_kiro_shape_logged: set[str] = set()


def _as_credit_count(value: Any) -> float | int | None:
    """``value`` when it is a real numeric credit reading, else None.

    bool is excluded explicitly: it is an int subclass in Python, so
    ``True`` would otherwise be stored as 1 credit.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def extract_kiro_credits(usage: Any, *, model: str | None) -> float | int | None:
    """The `kiro_credits` cost reading from a `kr/` usage block, or None.

    Never raises and never bills: the caller records the result as an
    opaque diagnostic number on usage_events.meta. None means "not a `kr/`
    route" or "this response did not carry the signal", which are both
    normal.
    """
    if not str(model or '').startswith(_KIRO_ROUTE_PREFIX) or not isinstance(usage, dict) or not usage:
        return None

    for key in _KIRO_CREDIT_KEYS:
        found = _as_credit_count(usage.get(key))
        if found is not None:
            return found

    for block in _KIRO_NESTED_KEYS:
        nested = usage.get(block)
        if isinstance(nested, dict):
            for key in _KIRO_CREDIT_KEYS:
                found = _as_credit_count(nested.get(key))
                if found is not None:
                    return found

    if model not in _kiro_shape_logged:
        _kiro_shape_logged.add(model)
        # INFO, not WARNING: a kr/ response without the field is normal.
        # Keys only -- never values, which can carry upstream identifiers.
        logger.info(
            'kr/ usage block carried no recognised credit field for model=%s; keys=%s',
            model, sorted(usage.keys()),
        )
    return None
