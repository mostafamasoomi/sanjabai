"""Keyed web-search providers (Brave / Tavily / Serper).

Why this exists
---------------
``chat_search._web_search`` grounds chat answers from two *keyless* sources:
the DuckDuckGo Instant Answer API and Wikipedia intro extracts. Both were
measured reachable from this server and both return real prose, but neither
is a general web index -- they answer "what is X" well and "what happened
this week" not at all. Anything time-sensitive, local, or not encyclopedic
falls through to ''.

This module adds the missing layer: a real search index, behind an API key.
All three vendors below were probed from this server on 2026-08-23 and are
reachable (they answered the unauthenticated request with an auth error,
which is proof the TCP/TLS path works, not a network block)::

    422  api.search.brave.com/res/v1/web/search   (missing subscription header)
    401  api.tavily.com/search                    (missing key)
    403  google.serper.dev/search                 (missing key)

Contract
--------
:func:`search` NEVER raises and never blocks on a provider that is not
configured -- with no key present it returns ``[]`` without making a network
call at all, so the keyless path in ``_web_search`` is reached at full speed.
That matters because this runs inline on a user's chat request.

Adding a provider: write a ``_search_<name>`` coroutine with the same
signature and shape as the three below, then add it to ``_PROVIDERS``. The
normalized result shape is a list of ``SearchHit``; the caller does all
formatting, so a provider adapter never emits user-facing text.
"""
from __future__ import annotations

import html as _html
import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger('chat')  # same logger as the rest of the chat path

#: Per-provider HTTP timeout. Floor is the house rule "no probe/health
#: timeout below ~15s" (9router alone can take 11s); these are commercial
#: search APIs and answer in well under a second, but a slow one must
#: degrade to the keyless fallback rather than stall a chat request.
SEARCH_TIMEOUT_S = 15.0


@dataclass(frozen=True)
class SearchHit:
    """One normalized result. ``url`` is what the model cites as its source."""

    title: str
    snippet: str
    url: str


def _clean(value: object) -> str:
    """Collapse whitespace and unescape HTML entities from a provider field.

    Providers return `&quot;`/`&amp;` literals in titles and snippets (the
    keyless sources did too -- same reason ``_web_search`` unescapes). Not
    doing this puts raw entities into the model's context and, from there,
    into the user's answer.
    """
    if not isinstance(value, str):
        return ''
    return ' '.join(_html.unescape(value).split())


def _hits_from(rows: object, title_key: str, snippet_key: str, url_key: str, limit: int) -> list[SearchHit]:
    """Build hits from a provider's result array, skipping malformed rows.

    Defensive on every element: a provider that changes shape, or a proxy
    that returns an error document with a 200, must degrade to fewer/zero
    hits rather than raise past :func:`search`'s never-raises contract.
    """
    out: list[SearchHit] = []
    for row in (rows if isinstance(rows, list) else []):
        if len(out) >= limit:
            break
        if not isinstance(row, dict):
            continue
        title, url = _clean(row.get(title_key)), _clean(row.get(url_key))
        if not title or not url:
            continue
        out.append(SearchHit(title=title, snippet=_clean(row.get(snippet_key)), url=url))
    return out


async def _search_brave(query: str, key: str, limit: int) -> list[SearchHit]:
    """Brave Search API. Results live under ``web.results[]``."""
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_S, proxy=None) as cli:
        r = await cli.get(
            'https://api.search.brave.com/res/v1/web/search',
            params={'q': query, 'count': limit},
            headers={'Accept': 'application/json', 'X-Subscription-Token': key},
        )
    if r.status_code != 200:
        logger.warning('search_providers brave returned http_%s', r.status_code)
        return []
    body = r.json()
    web = body.get('web') if isinstance(body, dict) else None
    rows = web.get('results') if isinstance(web, dict) else None
    # Brave calls the snippet field "description".
    return _hits_from(rows, 'title', 'description', 'url', limit)


async def _search_tavily(query: str, key: str, limit: int) -> list[SearchHit]:
    """Tavily. POST with the key in the body; results under ``results[]``."""
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_S, proxy=None) as cli:
        r = await cli.post(
            'https://api.tavily.com/search',
            json={'api_key': key, 'query': query, 'max_results': limit,
                  'search_depth': 'basic'},
        )
    if r.status_code != 200:
        logger.warning('search_providers tavily returned http_%s', r.status_code)
        return []
    body = r.json()
    rows = body.get('results') if isinstance(body, dict) else None
    return _hits_from(rows, 'title', 'content', 'url', limit)


async def _search_serper(query: str, key: str, limit: int) -> list[SearchHit]:
    """Serper (Google SERP proxy). Results under ``organic[]``."""
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_S, proxy=None) as cli:
        r = await cli.post(
            'https://google.serper.dev/search',
            json={'q': query, 'num': limit},
            headers={'X-API-KEY': key, 'Content-Type': 'application/json'},
        )
    if r.status_code != 200:
        logger.warning('search_providers serper returned http_%s', r.status_code)
        return []
    body = r.json()
    rows = body.get('organic') if isinstance(body, dict) else None
    return _hits_from(rows, 'title', 'snippet', 'link', limit)


#: name -> (env var holding the key, adapter). Order is the auto-detect
#: preference when WEB_SEARCH_PROVIDER is unset: Brave first because its
#: free tier is the one that does not expire.
_PROVIDERS: dict[str, tuple[str, object]] = {
    'brave': ('BRAVE_SEARCH_API_KEY', _search_brave),
    'tavily': ('TAVILY_API_KEY', _search_tavily),
    'serper': ('SERPER_API_KEY', _search_serper),
}


def configured_provider() -> tuple[str, str] | None:
    """The (name, key) that :func:`search` would use, or None.

    ``WEB_SEARCH_PROVIDER`` pins a specific one; unset means "use whichever
    has a key", in ``_PROVIDERS`` order. An explicitly pinned provider whose
    key is missing resolves to None rather than silently falling through to
    a different vendor than the operator named -- a silent substitution is
    exactly the kind of thing that makes a bill impossible to explain.
    """
    pinned = (os.getenv('WEB_SEARCH_PROVIDER') or '').strip().lower()
    if pinned:
        entry = _PROVIDERS.get(pinned)
        if entry is None:
            logger.warning('WEB_SEARCH_PROVIDER=%r is not a known provider', pinned)
            return None
        key = (os.getenv(entry[0]) or '').strip()
        if not key:
            logger.warning('WEB_SEARCH_PROVIDER=%r set but %s is empty', pinned, entry[0])
            return None
        return pinned, key
    for name, (env_var, _fn) in _PROVIDERS.items():
        key = (os.getenv(env_var) or '').strip()
        if key:
            return name, key
    return None


async def search(query: str, max_results: int = 5) -> list[SearchHit]:
    """Search via the configured provider. Returns [] when none is configured.

    Never raises -- a dead or misbehaving provider degrades to [] so the
    caller falls through to the keyless sources, exactly as if no key had
    been set. Returning [] and returning "search is off" are deliberately
    the same thing here: the caller's next step is identical either way.
    """
    q = ' '.join((query or '').split())
    if not q:
        return []
    chosen = configured_provider()
    if chosen is None:
        return []
    name, key = chosen
    _env_var, fn = _PROVIDERS[name]
    try:
        hits = await fn(q, key, max(1, max_results))  # type: ignore[operator]
    except Exception as e:
        logger.warning('search_providers %s failed query=%r: %s', name, q[:80], type(e).__name__)
        return []
    if hits:
        logger.info('search_providers %s returned %d hit(s) for query=%r', name, len(hits), q[:80])
    else:
        logger.info('search_providers %s returned no hits for query=%r', name, q[:80])
    return hits
