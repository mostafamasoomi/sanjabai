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
                 to port 20128 and exposes an unauthenticated GET /health
                 *outside* the /v1 prefix

Both speak the same three operations we need: list models, probe a model, and
report whether the upstream itself is reachable.

Chat traffic still flows through whichever provider `CHAT_PROVIDER` names
(default: litellm). Discovery and health probing always cover every enabled
provider, so 9Router can be observed in production before any user traffic is
pointed at it.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

from database import _http, LITELLM_HOST


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

    nine_url = os.getenv('NINEROUTER_URL', '').strip()
    if nine_url or _env_flag('NINEROUTER_ENABLED'):
        providers.append(
            Provider(
                name='ninerouter',
                base_url=(nine_url or 'http://9router:20128').rstrip('/'),
                api_key=os.getenv('NINEROUTER_API_KEY', ''),
                # 9Router serves GET /health unauthenticated, outside /v1.
                health_path='/health',
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
