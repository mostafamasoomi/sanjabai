"""File text extraction, web search, and the /v1/chat/with-file route --
split out of chat.py (see chat.py's module docstring for why).

MONKEYPATCH CONTRACT: tests patch several of these names directly on the
`chat` module (`chat_mod._web_search = ...`, `chat_mod._get_user_id = ...`,
`chat_mod.BillingService = ...`, `chat_mod.check_and_consume = ...`,
`chat_mod._resolve_provider = ...`, `chat_mod._is_model_allowed = ...`,
`chat_mod.is_working_model = ...`, `chat_mod.get_injection_messages = ...`,
`chat_mod._track_usage = ...`, `chat_mod.async_session = ...` -- see
test_web_search.py / test_with_file_web_search.py). Notably `_web_search` is
patched and expected to affect `_apply_web_search`'s behavior even though
both live in this same file -- a plain intra-module call would NOT observe
that patch, since Python resolves a bare global name against the *defining*
module's namespace, not chat.py's. Every one of those names is therefore
read through `chat.<name>` at call time everywhere below (including the
`_apply_web_search` -> `_web_search` call), never via `from chat import X`
and never via a bare intra-module reference. `chat` is imported plainly at
module scope, which is safe against the chat.py <-> chat_web.py circular
import: nothing here touches a `chat` attribute until a function actually
runs, by which point chat.py has finished executing.
"""
from __future__ import annotations

import io
import json
import logging
import re as _re
import secrets

from fastapi import Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response

from dependencies import _to_fa
from services.context_injection import inject_messages
from services.billing import SqlBillingRepo, BillingService, InsufficientBalanceError
from services.money import Money
from services.entitlement_gate import covering_entitlement
from model_output import clean_response_dict

import chat
from site_settings import get_site_flag

logger = logging.getLogger('chat')  # keep all chat_*.py logs under the pre-split 'chat' logger name

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB hard cap


async def _chat_disabled_response() -> JSONResponse | None:
    """503 while the ``chat_enabled`` site flag is off; None otherwise.

    The single implementation behind all FOUR chat entry points --
    /v1/chat/completions, /v1/chat/with-file, /v1/smart-chat and
    /v1/compare -- which reach it as ``chat._chat_disabled_response``
    (chat.py re-exports it). Gating only one route would make the admin's
    switch a lie, since the other three would keep serving.

    Lives here rather than in chat.py for the same reason
    _release_reservation below does: to keep chat.py under the house
    500-line cap.
    """
    if await get_site_flag('chat_enabled'):
        return None
    return JSONResponse(
        {'error': {'message': 'گفتگو موقتاً در دسترس نیست',
                   'type': 'service_unavailable', 'code': 'chat_disabled'}},
        status_code=503,
    )


async def _release_reservation(reservation: dict | None, uid: int, label: str = '') -> None:
    """Release a billing reservation; fire-and-forget, logs on failure.

    Lives here (not chat.py) purely to keep chat.py under the house
    500-line cap -- chat_with_file() below is its heaviest caller. Every
    other module reaches it as `chat._release_reservation` (re-exported by
    chat.py).
    """
    if not reservation or chat.async_session is None:
        return
    try:
        async with chat.async_session() as s:
            _rel_repo = SqlBillingRepo(s)
            _rel_svc = BillingService(_rel_repo)
            await _rel_svc.release(reservation['reservation_id'])
            await s.commit()
    except Exception as e:
        logger.warning(f"release_reservation failed uid={uid} {label}: {e}")


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


async def _apply_web_search(payload_dict: dict, *, handler: str) -> None:
    """Pop ``web_search`` off ``payload_dict`` and, if truthy, inject search
    results as a system message ahead of the last user question.

    Shared by ``/v1/chat/completions`` and ``/v1/smart-chat`` so the two
    handlers cannot drift apart again -- this exact bug (smart-chat silently
    dropping ``web_search`` and forwarding the stray key upstream unread) is
    what this helper was extracted to fix. Mutates ``payload_dict`` in place.
    ``handler`` is a short label ('chat.completions' / 'smart-chat') used only
    for logging, so an incident like the one that motivated this fix is
    diagnosable from logs instead of silently invisible.
    """
    if not payload_dict.pop('web_search', False):
        return
    _msgs = payload_dict.get('messages', [])
    _query = ''
    for _m in reversed(_msgs):
        if isinstance(_m, dict) and _m.get('role') == 'user':
            _query = _m.get('content', '')
            break
    _query_log = _query if isinstance(_query, str) else str(_query)
    if not _query:
        logger.info(f"web_search requested handler={handler} but no user message found; skipping")
        return
    logger.info(f"web_search requested handler={handler} query={_query_log[:80]!r}")
    _results = await chat._web_search(_query)
    if _results:
        logger.info(f"web_search succeeded handler={handler} query={_query_log[:80]!r}")
        _search_msg = {'role': 'system', 'content': f'[نتایج جستجوی وب برای: {_query_log[:100]}]\n{_results}\n\nمهم: این نتایج جستجوی لحظه‌ای از اینترنت هستند. از آنها مستقیماً برای پاسخ استفاده کن. هرگز نگو "به اینترنت دسترسی ندارم" یا "اطلاعات من قدیمی است" — چون نتایج جستجوی زنده بالا در دسترس تو هستند. پاسخ را بر اساس این نتایج بنویس و منبع خبر را ذکر کن.'}
        _idx = 0
        for _i, _m in enumerate(_msgs):
            if isinstance(_m, dict) and _m.get('role') == 'system':
                _idx = _i + 1
        _msgs.insert(_idx, _search_msg)
        payload_dict['messages'] = _msgs
    else:
        logger.info(f"web_search failed/no-results handler={handler} query={_query_log[:80]!r}")


@chat.router.post('/v1/chat/with-file')
async def chat_with_file(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form(''),
    messages: str = Form('[]'),
    stream: bool = Form(False),
    web_search: bool = Form(False),
):
    """Chat with an attached file."""
    uid = await chat._get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    _disabled = await chat._chat_disabled_response()
    if _disabled is not None:
        return _disabled

    # Canonicalize a public_id (or any legacy id) to provider_model_id, or
    # resolve a live catalog default when the client sent none -- see
    # _resolve_public_model's and _safe_default_model's docstrings (FIX 3:
    # previously the empty case fell through to a hardcoded 'tencent-hy3'
    # literal that is not a real catalog row).
    if model:
        model = await chat._resolve_public_model(model)
    else:
        model = await chat._safe_default_model()

    # Free-tier throttle gate — before any reservation is opened.
    _ft_gate = await chat.check_and_consume(uid, [model]) if model else None
    if _ft_gate is not None:
        return chat._free_tier_response(_ft_gate)

    # P1: BillingService reserve (replaces _check_quota_pre with proper FOR UPDATE locking)
    # Fall back to legacy _check_quota_pre if BillingService fails
    reservation = None
    try:
        async with chat.async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = chat.BillingService(_repo)
            _est_cost = 1000 if (model and await chat.is_working_model(model)) else 5000
            # Package quota covers this request -> skip the wallet reservation
            # (reservation stays None; the release/settle code below already
            # treats None as a no-op). See services/entitlement_gate.py.
            if await covering_entitlement(uid, _est_cost) is not None:
                reservation = None
            else:
                reservation = await _bill_svc.reserve(
                    uid, Money(_est_cost),
                    idempotency_key=f"file:{secrets.token_hex(8)}",
                    model=model,
                )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return JSONResponse(
            {'error': {'message': 'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.', 'type': 'quota_exceeded', 'code': 'balance'}},
            status_code=429,
        )
    except Exception as e:
        import traceback
        logger.warning(f"BillingService.reserve failed uid={uid}, falling back to legacy _check_quota_pre: {e}\n{traceback.format_exc()}")
        quota_err = await chat._check_quota_pre(uid)
        if quota_err is not None:
            return quota_err
    try:
        msgs = json.loads(messages) if messages else []
    except Exception as e:
        logger.warning(f"chat_with_file messages parse failed uid={uid}: {e}")
        msgs = []
    if not isinstance(msgs, list):
        msgs = []
    # Web search injection (shared helper -- see _apply_web_search), run
    # BEFORE the file's extracted text is appended below so the search query
    # is the user's actual question, not the file content. Applied the same
    # way /v1/chat/completions and /v1/smart-chat do so all three chat entry
    # points behave identically instead of silently drifting.
    # FIX 2: counteract the injected caveman-style system prompt -- see
    # chat()'s comment / _REASONING_INJECTING_PROVIDERS docstring. Applied
    # to the client's original messages, before web search adds its own
    # system message, via the same "_ws_payload" container so both share
    # the house pattern (_apply_web_search) of mutate-then-reread.
    _ws_payload = {'messages': msgs, 'web_search': web_search}
    await chat._apply_persian_style_guard_for_model(_ws_payload, model)
    await _apply_web_search(_ws_payload, handler='chat.with-file')
    msgs = _ws_payload['messages']
    text, err = await _extract_file_text(file)
    if err:
        await _release_reservation(reservation, uid, 'file_error')
        return JSONResponse({'error': {'message': err, 'type': 'file_error'}}, status_code=400)
    if text.strip():
        file_block = f'[Attached file: {file.filename}]\n\n{text[:50000]}'
        msgs.append({'role': 'user', 'content': file_block})
    selected_model = model
    # Whitelist validation
    if not selected_model:
        # _safe_default_model() couldn't find anything in the catalog
        # either -- see the identical check/comment in chat().
        await _release_reservation(reservation, uid, 'no_model_available')
        return JSONResponse(
            {'error': {'message': 'در حال حاضر مدلی برای انتخاب پیش‌فرض در دسترس نیست. لطفاً یک مدل را به‌صورت دستی انتخاب کنید.', 'type': 'invalid_request', 'code': 'model_not_available'}},
            status_code=400,
        )
    if not await chat._is_model_allowed(selected_model):
        logger.info(f"chat_with_file blocked model={selected_model} uid={uid}")
        await _release_reservation(reservation, uid, 'model_reject')
        return JSONResponse(
            {'error': {'message': f'مدل {selected_model} در دسترس نیست', 'type': 'invalid_request', 'code': 'model_not_available'}},
            status_code=400,
        )
    payload = {'model': selected_model, 'messages': msgs, 'stream': stream}
    # Use helper for injection (S2)
    try:
        injs = await chat.get_injection_messages(uid)
        if injs:
            payload['messages'] = inject_messages(msgs, injs)
            msgs = payload['messages']
    except Exception as e:
        logger.warning(f"chat_with_file injection failed uid={uid}: {e}")
    if stream:
        await _release_reservation(reservation, uid, 'before_stream')
        return await chat._chat_stream(payload, request)
    try:
        _provider = await chat._resolve_provider(selected_model)
        r = await chat._http.post(
            f'{_provider.v1}/chat/completions', json=payload,
            headers={**_provider.headers(), 'Accept': 'application/json'},
        )
        if r.status_code == 200:
            resp_data = r.json()
            # Bill on the RAW upstream response -- see the identical
            # comment in chat() above.
            cost_info = await chat._track_usage(request, payload, resp_data)
            resp_data = clean_response_dict(resp_data)
            if cost_info and cost_info.get('cost', 0) > 0:
                resp_data['billing'] = {
                    'cost': cost_info.get('cost', 0),
                    'input_tokens': cost_info.get('input_tokens', 0),
                    'output_tokens': cost_info.get('output_tokens', 0),
                    'balance_after': cost_info.get('balance_after', 0),
                    'currency': 'IRT',
                }
            # P1: Release reservation after successful billing
            await _release_reservation(reservation, uid, 'after_success')
            # P3: Fire background auto-memory extraction
            chat._fire_memory_extraction(uid, msgs)
            return Response(content=json.dumps(resp_data), status_code=200, media_type='application/json')
        await _release_reservation(reservation, uid, 'upstream_error')
        return Response(content=r.content, status_code=r.status_code, media_type='application/json')
    except Exception as e:
        logger.warning(f"chat_with_file gateway error uid={uid} model={selected_model}: {e}")
        # P1: Release reservation on error
        if reservation:
            try:
                async with chat.async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = chat.BillingService(_rel_repo)
                    await _rel_svc.release(reservation['reservation_id'])
                    await _rel_session.commit()
            except Exception as _rel_e:
                logger.warning(f"BillingService.release on error failed uid={uid}: {_rel_e}")
        return JSONResponse(
            {'detail': 'سرویس موقتاً در دسترس نیست', 'code': 'gateway_error'},
            status_code=502,
        )
