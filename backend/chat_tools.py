"""
Chat input-tool helpers: web-search grounding and file-text extraction.

Pulled out of chat.py (which was well past the project's 500-line ceiling).
``_web_search`` grounds chat answers in live search results (DuckDuckGo first,
Wikipedia fallback); ``_extract_file_text`` turns an uploaded file (txt/md/csv/
json/pdf) into plain text for the /v1/chat/with-file endpoint.
"""
from __future__ import annotations

import io
import logging
import re as _re

from fastapi import UploadFile

from dependencies import _to_fa
from chat_common import MAX_FILE_SIZE

logger = logging.getLogger(__name__)


async def _extract_file_text(upload: UploadFile) -> tuple[str, str]:
    """Return (text, error). Supports txt/md/csv/json/pdf."""
    name = (upload.filename or '').lower()
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            return '', f'file too large | فایل بیش از حد بزرگ است (حداکثر {_to_fa(MAX_FILE_SIZE // (1024*1024))} مگابایت)'
        chunks.append(chunk)
    data = b''.join(chunks)
    if name.endswith(('.txt', '.md', '.csv', '.json', '.log', '.text')):
        try:
            return data.decode('utf-8', errors='replace'), ''
        except Exception as e:
            logger.warning(f"_extract_file_text decode error {name}: {e}")
            return '', f'read error: {e}'
    if name.endswith('.pdf'):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if len(reader.pages) > 100:
                return '', 'PDF too many pages | تعداد صفحات PDF بیش از حد مجاز است (حداکثر ۱۰۰)'
            text = '\n'.join((p.extract_text() or '') for p in reader.pages[:100])
            return text[:200000], ''
        except Exception as e:
            logger.warning(f"_extract_file_text pdf error {name}: {e}")
            return '', f'pdf extract error: {e}'
    return '', f'unsupported file type: {name or "unknown"}'


async def _web_search(query: str, max_results: int = 5) -> str:
    """Web search used to ground chat answers.

    Strategy (most reliable first, with graceful fallback):
      1. DuckDuckGo HTML endpoint (works in most environments, no API key).
      2. Wikipedia open search API — always available, no bot challenges,
         used as a fallback when DDG returns its anomaly/202 challenge page.

    Returns a formatted bullet list of results, or '' on total failure.
    Proxies are only used when explicitly configured via env vars; the old
    hardcoded backhaul/SOCKS defaults are gone because they silently slow
    every request down when those hosts don't exist.
    """
    import os as _os
    import httpx
    from urllib.parse import unquote, quote

    # Only honor a proxy when the operator explicitly set one. The dead
    # hardcoded backhaul default is removed; we still try the env proxy
    # (HTTPS_PROXY/HTTP_PROXY) as a *fallback* but never as the only path.
    _env_proxy = _os.getenv('HTTPS_PROXY') or _os.getenv('HTTP_PROXY')
    _socks_proxy = None
    if _os.getenv('WEB_SEARCH_SOCKS'):
        try:
            import socksio  # noqa: F401
            _socks_proxy = _os.getenv('WEB_SEARCH_SOCKS')
        except ImportError:
            logger.debug('_web_search: socksio not installed, skipping SOCKS proxy')

    # Direct first (bypass any env proxy), then via the configured proxy.
    # Explicitly passing proxy=None disables httpx's automatic env-proxy
    # pickup, which would otherwise route everything through a dead host.
    _attempts: list[dict] = [{'proxy': None}]
    if _env_proxy:
        _attempts.append({'proxy': _env_proxy})
    if _socks_proxy:
        _attempts.append({'proxy': _socks_proxy})

    _headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://duckduckgo.com/',
        'Content-Type': 'application/x-www-form-urlencoded',
    }

    _q = ' '.join((query or '').split())  # collapse internal whitespace
    if not _q:
        return ''

    # ── 1) DuckDuckGo HTML ────────────────────────────────────────────────
    html = ''
    for cfg in _attempts:
        try:
            # Explicitly set proxy (None = bypass env proxy) so the direct
            # attempt never inherits a dead HTTPS_PROXY from the environment.
            kwargs = {'timeout': 15, 'follow_redirects': True, 'proxy': cfg['proxy']}
            async with httpx.AsyncClient(**kwargs) as _sc:
                r = await _sc.post(
                    'https://html.duckduckgo.com/html/',
                    data={'q': _q},
                    headers=_headers,
                )
            # DDG returns HTTP 202 with an "anomaly" bot-challenge page when it
            # blocks automation; only a real 200 with result markup counts.
            if r.status_code == 200 and 'result__a' in r.text:
                html = r.text
                break
        except Exception as e:
            logger.debug(f"_web_search DDG attempt proxy={cfg['proxy']} failed: {type(e).__name__}")
            continue

    if html:
        try:
            links = _re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.+?)</a>', html, _re.DOTALL)
            snippets = _re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, _re.DOTALL)
            if links:
                lines = []
                for i, (href, title) in enumerate(links[:max_results]):
                    title = _re.sub(r'<[^>]+>', '', title).strip()
                    snippet = _re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ''
                    actual_url = href
                    if 'uddg=' in href:
                        m = _re.search(r'uddg=([^&]+)', href)
                        if m:
                            actual_url = unquote(m.group(1))
                    if title:
                        lines.append(f'• {title}\n  {snippet}\n  {actual_url}')
                if lines:
                    return '\n'.join(lines)
        except Exception as e:
            logger.warning(f"_web_search DDG parse failed query={_q[:80]}: {e}")

    # ── 2) Wikipedia fallback (always reachable, no challenge) ────────────
    # Try direct (bypassing env proxy) first, then via the configured proxy.
    for _wp_proxy in ([None] + ([_env_proxy] if _env_proxy else [])):
        try:
            kwargs = {'timeout': 15, 'follow_redirects': True, 'proxy': _wp_proxy}
            async with httpx.AsyncClient(**kwargs) as _sc:
                r = await _sc.get(
                    'https://en.wikipedia.org/w/api.php',
                    params={
                        'action': 'query',
                        'list': 'search',
                        'srsearch': _q,
                        'srlimit': max_results,
                        'srprop': 'snippet',
                        'format': 'json',
                    },
                    headers={'User-Agent': 'Sanjabai/1.0 (web search fallback)'},
                )
            if r.status_code == 200:
                data = r.json()
                results = (data.get('query') or {}).get('search') or []
                lines = []
                for item in results[:max_results]:
                    title = item.get('title', '').strip()
                    snippet = _re.sub(r'<[^>]+>', '', item.get('snippet', '')).strip()
                    url = 'https://en.wikipedia.org/wiki/' + quote(title.replace(' ', '_'))
                    if title:
                        lines.append(f'• {title}\n  {snippet}\n  {url}')
                if lines:
                    logger.info(f"_web_search used Wikipedia fallback for query={_q[:80]}")
                    return '\n'.join(lines)
        except Exception as e:
            logger.warning(f"_web_search Wikipedia fallback failed query={_q[:80]}: {e}")

    logger.warning(f"_web_search all sources failed query={_q[:80]}")
    return ''
