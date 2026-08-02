"""
Chat endpoints: /v1/chat/completions, /v1/chat/with-file, /v1/smart-chat.
Includes streaming, usage tracking, web search, and smart model selection.

S2 fixes:
- Extract memory/soul injection to services/context_injection.py with limits & sanitization
- Replace silent except: pass with logger.warning
- Add model whitelist validation (DB + hardcoded working set)
- Add streaming timeout & client disconnect handling
- Fix default model for file chat (mimo disabled -> tencent-hy3)
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import traceback
import re as _re
import secrets
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session, _http
from models import Quota, Assistant, Ledger, Subscription
from dependencies import _get_user_id, _to_fa
from services.context_injection import get_injection_messages, inject_messages
from services.billing import SqlBillingRepo, BillingService, InsufficientBalanceError
from services.money import Money
from services.memory_extractor import extract_memories, MIN_MSG_COUNT
from middleware.compression import compress_messages, estimate_savings

logger = logging.getLogger(__name__)

import time as _time


def _record_model_health(
    model_id: str, *, ok: bool, latency_ms: int | None = None, error: str | None = None
) -> None:
    """Record a passive health sample for a real request, off the response path.

    Fire-and-forget on purpose: the user's completion has already succeeded or
    failed by this point, and a health-table write must never add latency to it
    or turn a good response into an error. Imported lazily so chat.py does not
    depend on model_health at import time.
    """
    if not model_id:
        return
    try:
        from model_health import record_traffic

        task = asyncio.create_task(
            record_traffic(model_id, ok, latency_ms=latency_ms, error=error)
        )
        # Hold a reference so the task is not garbage-collected mid-flight.
        _HEALTH_TASKS.add(task)
        task.add_done_callback(_HEALTH_TASKS.discard)
    except Exception:
        pass


_HEALTH_TASKS: set[asyncio.Task] = set()

router = APIRouter()


def _fire_memory_extraction(uid: int, messages: list[dict[str, Any]]) -> None:
    """Schedule background auto-memory extraction if conversation has enough messages."""
    if uid and messages and len(messages) > MIN_MSG_COUNT:
        # Capture a copy of messages to avoid mutation issues
        msgs_snapshot = [dict(m) for m in messages[-40:]]  # Keep last 40 max
        asyncio.create_task(extract_memories(uid, msgs_snapshot))


class ChatRequest(BaseModel):
    model: str = ''
    messages: list = []
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    web_search: bool = False
    assistant_id: int | None = None


class CompareRequest(BaseModel):
    model_a: str
    model_b: str
    messages: list = []
    stream: bool = False


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB hard cap

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


# ── Shared helpers ──────────────────────────────────────────────

async def _release_reservation(reservation: dict | None, uid: int, label: str = '') -> None:
    """Release a billing reservation; fire-and-forget, logs on failure."""
    if not reservation or async_session is None:
        return
    try:
        async with async_session() as s:
            _rel_repo = SqlBillingRepo(s)
            _rel_svc = BillingService(_rel_repo)
            await _rel_svc.release(reservation['reservation_id'])
            await s.commit()
    except Exception as e:
        logger.warning(f"release_reservation failed uid={uid} {label}: {e}")

async def _check_quota_pre(uid: int) -> JSONResponse | None:
    """Pre-flight quota and balance check before calling LiteLLM."""
    if async_session is None:
        return None
    try:
        async with async_session() as session:
            res = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
            quota = res.fetchone()
            if quota:
                limit = quota.daily_limit
                used = quota.used_today
                reset_at = quota.reset_at
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if reset_at and now >= reset_at:
                    await session.execute(
                        Quota.__table__.update().where(Quota.user_id == uid),
                        {'used_today': 0, 'updated_at': now},
                    )
                    await session.commit()
                    used = 0
                if limit > 0 and used >= limit:
                    return JSONResponse(
                        {'error': {'message': 'daily token quota exceeded', 'type': 'quota_exceeded', 'code': 'daily_limit'}},
                        status_code=429,
                    )
            res = await session.execute(
                sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
                {'uid': uid},
            )
            row = res.fetchone()
            balance = row.balance if row else 0
            if balance <= 0:
                return JSONResponse(
                    {'error': {'message': 'insufficient wallet balance | موجودی کیف پول کافی نیست', 'type': 'quota_exceeded', 'code': 'balance'}},
                    status_code=429,
                )
    except Exception as e:
        logger.warning(f"_check_quota_pre failed uid={uid}: {e}")
    return None


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
                    headers={'User-Agent': 'Sanjhubai/1.0 (web search fallback)'},
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


async def _record_usage(session: AsyncSession, uid: int, payload: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    """Shared billing logic for tracking and billing usage. Returns cost info dict."""
    result = {'input_tokens': 0, 'output_tokens': 0, 'cost': 0, 'balance_after': 0}
    total_tokens = usage.get('total_tokens', 0)
    if total_tokens <= 0:
        return result
    model = payload.get('model', '')
    input_tokens = int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0)
    output_tokens = int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)

    result['input_tokens'] = input_tokens
    result['output_tokens'] = output_tokens

    res = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
    quota = res.fetchone()
    if quota:
        await session.execute(
            Quota.__table__.update().where(Quota.user_id == uid),
            {'used_today': quota.used_today + total_tokens, 'updated_at': datetime.now(timezone.utc).replace(tzinfo=None)},
        )

    price_row = None
    try:
        price_res = await session.execute(
            sqlalchemy.text(
                'SELECT input_per_million, output_per_million FROM model_catalog '
                'WHERE provider_model_id = :mid AND availability = :avail LIMIT 1'
            ),
            {'mid': model, 'avail': 'available'},
        )
        price_row = price_res.fetchone()
    except Exception as e:
        logger.warning(f"_record_usage price lookup failed model={model} uid={uid}: {e}")

    if price_row:
        inp_rate = int(price_row.input_per_million or 0)
        out_rate = int(price_row.output_per_million or 0)
        cost = max(1, int((input_tokens * inp_rate + output_tokens * out_rate + 500_000) // 1_000_000))
    else:
        cost = max(1, total_tokens // 1000)

    result['cost'] = cost

    # Charge against Wallet.balance itself (the source of truth that
    # BillingService.reserve() gates future requests against), not just the
    # ledger's running SUM. Previously this only ever appended a Ledger row
    # and Wallet.balance was left untouched by real usage — it only moved on
    # top-ups — so the pre-flight reserve() check against `balance - reserved`
    # never reflected actual spend and users could keep chatting for free
    # indefinitely once their true (ledger) balance ran out. Locked via
    # lock_wallet_for_update to avoid a concurrent-request race on the same
    # wallet row.
    from services.billing import SqlBillingRepo
    _repo = SqlBillingRepo(session)
    async with _repo.lock_wallet_for_update(uid):
        wallet = await _repo.ensure_wallet(uid)
        current = wallet['balance']
        if current >= cost:
            new_balance = current - cost
            await _repo.set_wallet_balance(uid, new_balance)
            entry = Ledger(user_id=uid, amount=-cost, balance_after=new_balance, reason=f'مصرف {model}')
            session.add(entry)
        else:
            new_balance = current
    result['balance_after'] = new_balance

    try:
        from services.metering import record_usage
        from services.money import Money
        await record_usage(
            _repo,
            request_id=secrets.token_hex(8),
            user_id=uid,
            model=model,
            charge=Money(cost),
            upstream_status='success',
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except Exception as e:
        logger.warning(f"_record_usage metering failed model={model} uid={uid}: {e}")

    return result


async def _track_usage(request: Request, payload: dict[str, Any], response_data: dict[str, Any]) -> dict[str, Any]:
    """Record token usage for non-streaming requests. Returns cost info."""
    uid = await _get_user_id(request)
    if not uid or async_session is None:
        return {}
    usage = response_data.get('usage', {})
    if usage.get('total_tokens', 0) <= 0:
        return {}
    try:
        async with async_session() as session:
            cost_info = await _record_usage(session, uid, payload, usage)
            await session.commit()
            return cost_info
    except Exception as e:
        logger.warning(f"_track_usage failed uid={uid} model={payload.get('model')}: {e}")
        return {}


async def _bill_stream_usage(uid: int, payload: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    """Bill the user after a streaming chat completes. Returns cost info."""
    if usage.get('total_tokens', 0) <= 0:
        return {}
    try:
        async with async_session() as session:
            cost_info = await _record_usage(session, uid, payload, usage)
            await session.commit()
            return cost_info
    except Exception as e:
        logger.warning(f"_bill_stream_usage failed uid={uid} model={payload.get('model')}: {e}")
        return {}


async def _chat_stream(payload: dict[str, Any], request: Request):
    """Stream chat completion via SSE, collecting usage for billing."""
    uid = await _get_user_id(request)

    if uid:
        try:
            injs = await get_injection_messages(uid)
            if injs:
                payload['messages'] = inject_messages(payload.get('messages', []), injs)
        except Exception as e:
            logger.warning(f"_chat_stream injection failed uid={uid}: {e}")

    # Compress old messages to reduce token usage
    try:
        _orig = [m.copy() for m in payload.get("messages", [])]
        payload["messages"] = compress_messages(payload.get("messages", []), preserve_last=2)
        _sav = estimate_savings(_orig, payload["messages"])
        if _sav["savings_pct"] > 0:
            logger.info(f"Headroom stream: {_sav['savings_pct']}% saved ({_sav['saved_chars']} chars)")
    except Exception as e:
        logger.debug(f"Compression skipped: {e}")

    async def event_stream():
        usage_data = None
        try:
            payload['stream'] = True
            payload.setdefault('stream_options', {})
            if isinstance(payload['stream_options'], dict):
                payload['stream_options']['include_usage'] = True
            import httpx
            _provider = await _resolve_provider(payload.get('model', ''))
            # Streaming timeout: 90s total, 10s connect
            async with _http.stream(
                'POST',
                f'{_provider.v1}/chat/completions',
                json=payload,
                headers={**_provider.headers(), 'Accept': 'text/event-stream'},
                timeout=httpx.Timeout(90, connect=10, read=90),
            ) as r:
                async for line in r.aiter_lines():
                    # Disconnect handling
                    if await request.is_disconnected():
                        logger.info(f"_chat_stream client disconnected uid={uid} model={payload.get('model')}")
                        break
                    if line:
                        stripped = line.strip()
                        if stripped.startswith('data:'):
                            data_str = stripped[5:].strip()
                            if data_str == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data_str)
                                if isinstance(chunk.get('usage'), dict) and chunk['usage']:
                                    usage_data = chunk['usage']
                            except (json.JSONDecodeError, ValueError):
                                pass
                        yield f"{line}\n\n"
        except Exception as e:
            logger.warning(f"_chat_stream error uid={uid} model={payload.get('model')}: {e}")
            yield f'data: {json.dumps({"error": "سرویس موقتاً در دسترس نیست", "code": "gateway_error"})}\n\n'
        finally:
            if uid and usage_data and async_session is not None:
                try:
                    cost_info = await _bill_stream_usage(uid, payload, usage_data)
                    if cost_info and cost_info.get('cost', 0) > 0:
                        billing_event = json.dumps({
                            'type': 'billing',
                            'cost': cost_info.get('cost', 0),
                            'input_tokens': cost_info.get('input_tokens', 0),
                            'output_tokens': cost_info.get('output_tokens', 0),
                            'balance_after': cost_info.get('balance_after', 0),
                            'currency': 'IRT',
                        })
                        yield f'data: {billing_event}\n\n'
                except Exception as e:
                    logger.warning(f"_chat_stream billing emit failed uid={uid}: {e}")
            # P3: Fire background auto-memory extraction (streaming)
            if uid:
                _fire_memory_extraction(uid, payload.get('messages', []))

    return StreamingResponse(event_stream(), media_type='text/event-stream')


# ── Routes ──────────────────────────────────────────────────────

@router.post('/v1/chat/completions')
async def chat(request: Request, payload: ChatRequest) -> Response:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    payload_dict = payload.model_dump(exclude_none=True)

    # P1: BillingService reserve (replaces _check_quota_pre with proper FOR UPDATE locking)
    # Fall back to legacy _check_quota_pre if BillingService fails
    reservation = None
    try:
        async with async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = BillingService(_repo)
            _model = payload_dict.get('model', '') or 'tencent-hy3'
            _est_cost = 1000 if await is_working_model(_model) else 5000
            reservation = await _bill_svc.reserve(
                uid, Money(_est_cost),
                idempotency_key=f"chat:{secrets.token_hex(8)}",
                model=_model,
            )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return JSONResponse(
            {'error': {'message': 'insufficient wallet balance | موجودی کیف پول کافی نیست', 'type': 'quota_exceeded', 'code': 'balance'}},
            status_code=429,
        )
    except Exception as e:
        import traceback
        logger.warning(f"BillingService.reserve failed uid={uid}, falling back to legacy _check_quota_pre: {e}\n{traceback.format_exc()}")
        quota_err = await _check_quota_pre(uid)
        if quota_err is not None:
            return quota_err

    # Default model if empty (S2: mimo disabled, use tencent-hy3)
    if not payload_dict.get('model'):
        payload_dict['model'] = 'tencent-hy3'

    # --- Model whitelist validation ---
    model_to_check = payload_dict.get('model', '')
    if model_to_check and not await _is_model_allowed(model_to_check):
        logger.info(f"chat blocked: model={model_to_check} uid={uid} not allowed")
        await _release_reservation(reservation, uid, 'model_reject')
        return JSONResponse(
            {'error': {'message': f'مدل {model_to_check} در دسترس نیست | مدل پیشفرض tencent-hy3 را انتخاب کنید', 'type': 'invalid_request', 'code': 'model_not_available'}},
            status_code=400,
        )

    # Assistant injection
    _assistant_id = payload_dict.pop('assistant_id', None)
    if _assistant_id and async_session is not None:
        try:
            async with async_session() as _asession:
                _ares = await _asession.execute(
                    Assistant.__table__.select().where(Assistant.id == int(_assistant_id))
                )
                _arow = _ares.fetchone()
                if _arow and _arow.system_prompt:
                    _sys_msg = {'role': 'system', 'content': _arow.system_prompt}
                    _msgs = payload_dict.get('messages', [])
                    _msgs.insert(0, _sys_msg)
                    payload_dict['messages'] = _msgs
                    if _arow.model_id and not payload_dict.get('model'):
                        payload_dict['model'] = _arow.model_id
        except Exception as e:
            logger.warning(f"chat assistant injection failed aid={_assistant_id} uid={uid}: {e}")

    # Memory + soul injection via helper (S2 fix duplication + limits + sanitization)
    try:
        injs = await get_injection_messages(uid)
        if injs:
            payload_dict['messages'] = inject_messages(payload_dict.get('messages', []), injs)
    except Exception as e:
        logger.warning(f"chat injection failed uid={uid}: {e}")

    # Web search injection
    if payload_dict.pop('web_search', False):
        _msgs = payload_dict.get('messages', [])
        _query = ''
        for _m in reversed(_msgs):
            if isinstance(_m, dict) and _m.get('role') == 'user':
                _query = _m.get('content', '')
                break
        if _query:
            _results = await _web_search(_query)
            if _results:
                _search_msg = {'role': 'system', 'content': f'[نتایج جستجوی وب برای: {_query[:100]}]\n{_results}\n\nمهم: این نتایج جستجوی لحظه‌ای از اینترنت هستند. از آنها مستقیماً برای پاسخ استفاده کن. هرگز نگو "به اینترنت دسترسی ندارم" یا "اطلاعات من قدیمی است" — چون نتایج جستجوی زنده بالا در دسترس تو هستند. پاسخ را بر اساس این نتایج بنویس و منبع خبر را ذکر کن.'}
                _idx = 0
                for _i, _m in enumerate(_msgs):
                    if isinstance(_m, dict) and _m.get('role') == 'system':
                        _idx = _i + 1
                _msgs.insert(_idx, _search_msg)
                payload_dict['messages'] = _msgs

    # Compress old messages to reduce token usage
    try:
        _orig = [m.copy() for m in payload_dict.get('messages', [])]
        payload_dict['messages'] = compress_messages(payload_dict.get('messages', []), preserve_last=2)
        _sav = estimate_savings(_orig, payload_dict['messages'])
        if _sav['savings_pct'] > 0:
            logger.info(f"Headroom: {_sav['savings_pct']}%% saved ({_sav['saved_chars']} chars)")
    except Exception as e:
        logger.debug(f"Compression skipped: {e}")

    stream = payload_dict.get('stream', False)
    if stream:
        await _release_reservation(reservation, uid, 'before_stream')
        return await _chat_stream(payload_dict, request)
    _hc_model = str(payload_dict.get('model') or '')
    _hc_started = _time.monotonic()
    try:
        _provider = await _resolve_provider(_hc_model)
        r = await _http.post(f'{_provider.v1}/chat/completions', json=payload_dict, headers={**_provider.headers(), 'Accept': 'application/json'})
        # Passive health sample. Real traffic is the best signal we have about
        # whether a model works, and it costs nothing extra to record.
        _record_model_health(
            _hc_model,
            ok=r.status_code == 200,
            latency_ms=int((_time.monotonic() - _hc_started) * 1000),
            error=None if r.status_code == 200 else f'http_{r.status_code}',
        )
        if r.status_code == 200:
            cost_info = await _track_usage(request, payload_dict, r.json())
            resp_data = r.json()
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
            _fire_memory_extraction(uid, payload_dict.get('messages', []))
            return Response(content=json.dumps(resp_data), status_code=200, media_type='application/json')
        await _release_reservation(reservation, uid, 'upstream_error')
        return Response(content=r.content, status_code=r.status_code, media_type='application/json')
    except Exception as e:
        logger.warning(f"chat gateway error uid={uid} model={payload_dict.get('model')}: {e}")
        _record_model_health(
            _hc_model,
            ok=False,
            latency_ms=int((_time.monotonic() - _hc_started) * 1000),
            error=type(e).__name__,
        )
        await _release_reservation(reservation, uid, 'on_error')
        return JSONResponse({'detail': 'سرویس موقتاً در دسترس نیست', 'code': 'gateway_error'}, status_code=502)


@router.post('/v1/chat/with-file')
async def chat_with_file(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form(''),
    messages: str = Form('[]'),
    stream: bool = Form(False),
):
    """Chat with an attached file."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    # P1: BillingService reserve (replaces _check_quota_pre with proper FOR UPDATE locking)
    # Fall back to legacy _check_quota_pre if BillingService fails
    reservation = None
    try:
        async with async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = BillingService(_repo)
            _est_cost = 1000 if await is_working_model(model or 'tencent-hy3') else 5000
            reservation = await _bill_svc.reserve(
                uid, Money(_est_cost),
                idempotency_key=f"file:{secrets.token_hex(8)}",
                model=model or 'tencent-hy3',
            )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return JSONResponse(
            {'error': {'message': 'insufficient wallet balance | موجودی کیف پول کافی نیست', 'type': 'quota_exceeded', 'code': 'balance'}},
            status_code=429,
        )
    except Exception as e:
        import traceback
        logger.warning(f"BillingService.reserve failed uid={uid}, falling back to legacy _check_quota_pre: {e}\n{traceback.format_exc()}")
        quota_err = await _check_quota_pre(uid)
        if quota_err is not None:
            return quota_err
    try:
        msgs = json.loads(messages) if messages else []
    except Exception as e:
        logger.warning(f"chat_with_file messages parse failed uid={uid}: {e}")
        msgs = []
    if not isinstance(msgs, list):
        msgs = []
    text, err = await _extract_file_text(file)
    if err:
        await _release_reservation(reservation, uid, 'file_error')
        return JSONResponse({'error': {'message': err, 'type': 'file_error'}}, status_code=400)
    if text.strip():
        file_block = f'[Attached file: {file.filename}]\n\n{text[:50000]}'
        msgs.append({'role': 'user', 'content': file_block})
    # S2 fix: mimo-v2.5 disabled, use tencent-hy3 as default
    selected_model = model or 'tencent-hy3'
    # Whitelist validation
    if not await _is_model_allowed(selected_model):
        logger.info(f"chat_with_file blocked model={selected_model} uid={uid}")
        await _release_reservation(reservation, uid, 'model_reject')
        return JSONResponse(
            {'error': {'message': f'مدل {selected_model} در دسترس نیست | مدل tencent-hy3', 'type': 'invalid_request', 'code': 'model_not_available'}},
            status_code=400,
        )
    payload = {'model': selected_model, 'messages': msgs, 'stream': stream}
    # Use helper for injection (S2)
    try:
        injs = await get_injection_messages(uid)
        if injs:
            payload['messages'] = inject_messages(msgs, injs)
            msgs = payload['messages']
    except Exception as e:
        logger.warning(f"chat_with_file injection failed uid={uid}: {e}")
    if stream:
        await _release_reservation(reservation, uid, 'before_stream')
        return await _chat_stream(payload, request)
    try:
        _provider = await _resolve_provider(selected_model)
        r = await _http.post(
            f'{_provider.v1}/chat/completions', json=payload,
            headers={**_provider.headers(), 'Accept': 'application/json'},
        )
        if r.status_code == 200:
            cost_info = await _track_usage(request, payload, r.json())
            resp_data = r.json()
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
            _fire_memory_extraction(uid, msgs)
            return Response(content=json.dumps(resp_data), status_code=200, media_type='application/json')
        await _release_reservation(reservation, uid, 'upstream_error')
        return Response(content=r.content, status_code=r.status_code, media_type='application/json')
    except Exception as e:
        logger.warning(f"chat_with_file gateway error uid={uid} model={selected_model}: {e}")
        # P1: Release reservation on error
        if reservation:
            try:
                async with async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = BillingService(_rel_repo)
                    await _rel_svc.release(reservation['reservation_id'])
                    await _rel_session.commit()
            except Exception as _rel_e:
                logger.warning(f"BillingService.release on error failed uid={uid}: {_rel_e}")
        return JSONResponse(
            {'detail': 'سرویس موقتاً در دسترس نیست', 'code': 'gateway_error'},
            status_code=502,
        )


# ── Compare ──────────────────────────────────────────────────────

async def _call_model_once(
    model: str,
    messages: list,
    uid: int,
    request: Request,
) -> dict[str, Any]:
    """Call a single model and return response + timing + usage + cost."""
    import time
    start = time.monotonic()
    payload = {'model': model, 'messages': messages, 'stream': False}

    # Memory + soul injection
    try:
        injs = await get_injection_messages(uid)
        if injs:
            payload['messages'] = inject_messages(payload.get('messages', []), injs)
    except Exception as e:
        logger.warning(f"_call_model_once injection failed uid={uid} model={model}: {e}")

    # Compress
    try:
        _orig = [m.copy() for m in payload.get('messages', [])]
        payload['messages'] = compress_messages(payload.get('messages', []), preserve_last=2)
    except Exception as e:
        logger.debug(f"Compression skipped in compare: {e}")

    try:
        _provider = await _resolve_provider(model)
        r = await _http.post(
            f'{_provider.v1}/chat/completions',
            json=payload,
            headers={**_provider.headers(), 'Accept': 'application/json'},
        )
        elapsed = round(time.monotonic() - start, 3)
        if r.status_code == 200:
            resp_data = r.json()
            cost_info = await _track_usage(request, payload, resp_data)
            usage = resp_data.get('usage', {})
            content = ''
            choices = resp_data.get('choices', [])
            if choices:
                content = choices[0].get('message', {}).get('content', '')
            return {
                'model': model,
                'content': content,
                'elapsed': elapsed,
                'input_tokens': usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0) or 0,
                'output_tokens': usage.get('completion_tokens', 0) or usage.get('output_tokens', 0) or 0,
                'cost': cost_info.get('cost', 0) if cost_info else 0,
                'error': None,
            }
        else:
            return {
                'model': model,
                'content': '',
                'elapsed': elapsed,
                'input_tokens': 0,
                'output_tokens': 0,
                'cost': 0,
                'error': f'upstream error {r.status_code}',
            }
    except Exception as e:
        elapsed = round(time.monotonic() - start, 3)
        logger.warning(f"_call_model_once failed uid={uid} model={model}: {e}")
        return {
            'model': model,
            'content': '',
            'elapsed': elapsed,
            'input_tokens': 0,
            'output_tokens': 0,
            'cost': 0,
            'error': str(e),
        }


@router.post('/v1/compare')
async def compare_models(request: Request, payload: CompareRequest) -> Response:
    """Compare two models side-by-side. Non-streaming first."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    model_a = payload.model_a
    model_b = payload.model_b
    messages = payload.messages

    if not model_a or not model_b:
        return JSONResponse(
            {'error': {'message': 'هر دو مدل باید مشخص شوند', 'type': 'invalid_request', 'code': 'missing_models'}},
            status_code=400,
        )

    # Validate both models
    if not await _is_model_allowed(model_a):
        return JSONResponse(
            {'error': {'message': f'مدل {model_a} در دسترس نیست', 'type': 'invalid_request', 'code': 'model_not_available'}},
            status_code=400,
        )
    if not await _is_model_allowed(model_b):
        return JSONResponse(
            {'error': {'message': f'مدل {model_b} در دسترس نیست', 'type': 'invalid_request', 'code': 'model_not_available'}},
            status_code=400,
        )

    # P1: Reserve billing for both models (estimate worst-case)
    reservation_a = None
    reservation_b = None
    try:
        async with async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = BillingService(_repo)
            reservation_a = await _bill_svc.reserve(
                uid, Money(1000),
                idempotency_key=f"cmp:{secrets.token_hex(8)}",
                model=model_a,
            )
            reservation_b = await _bill_svc.reserve(
                uid, Money(1000),
                idempotency_key=f"cmp:{secrets.token_hex(8)}",
                model=model_b,
            )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return JSONResponse(
            {'error': {'message': 'insufficient wallet balance | موجودی کیف پول کافی نیست', 'type': 'quota_exceeded', 'code': 'balance'}},
            status_code=429,
        )
    except Exception as e:
        logger.warning(f"Compare BillingService.reserve failed uid={uid}: {e}")
        quota_err = await _check_quota_pre(uid)
        if quota_err is not None:
            return quota_err

    # Run both models in parallel
    results = await asyncio.gather(
        _call_model_once(model_a, messages, uid, request),
        _call_model_once(model_b, messages, uid, request),
    )

    result_a, result_b = results

    # Release reservations
    for res in (reservation_a, reservation_b):
        if res:
            try:
                async with async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = BillingService(_rel_repo)
                    await _rel_svc.release(res['reservation_id'])
                    await _rel_session.commit()
            except Exception as _rel_e:
                logger.warning(f"Compare BillingService.release failed uid={uid}: {_rel_e}")

    # Determine winner stats
    faster = None
    cheaper = None
    if not result_a.get('error') and not result_b.get('error'):
        if result_a['elapsed'] < result_b['elapsed']:
            faster = 'model_a'
        elif result_b['elapsed'] < result_a['elapsed']:
            faster = 'model_b'
        if result_a['cost'] < result_b['cost']:
            cheaper = 'model_a'
        elif result_b['cost'] < result_a['cost']:
            cheaper = 'model_b'

    return JSONResponse({
        'model_a': result_a,
        'model_b': result_b,
        'faster': faster,
        'cheaper': cheaper,
        'messages': messages,
    })


# ── Smart Chat ──────────────────────────────────────────────────

_GREETING_PATTERNS = _re.compile(
    r'^[\s]*(hi|hello|hey|salam|سلام|سلامت|สวัสดี|hallo|ciao|bonjour|hola|'
    r'good\s*(morning|afternoon|evening|night)|สวัสดี|merhaba|selam|hej|'
    r'howdy|yo|how\s*are\s*you|what\'?\s*up|sup|khubi|chetori|khobi)',
    _re.IGNORECASE,
)

_CODE_KEYWORDS = _re.compile(
    r'(```|def\s|class\s|function\s|import\s|from\s+\w+\s+import|'
    r'async\s+def|const\s|let\s|var\s|=>|return\s|if\s*\(|for\s*\(|'
    r'while\s*\(|try\s*{|except\s|raise\s|throw\s|new\s+\w+|'
    r'print\(|console\.log|SELECT\s|INSERT\s|UPDATE\s|DELETE\s)',
    _re.IGNORECASE,
)

_REASONING_KEYWORDS = _re.compile(
    r'(analyze|analyse|explain|compare|contrast|evaluate|reason|prove|'
    r'derive|derive|optimize|strategy|trade-?off|pros?\s*and\s*cons?|'
    r'logic|argument|hypothesis|theorem|algorithm|proof|'
    r'چرا|چگونه|تحلیل|مقایسه|ارزیابی|استراتژی)',
    _re.IGNORECASE,
)

_Creative_KEYWORDS = _re.compile(
    r'(write\s+a\s+(story|poem|essay|song|novel|article)|'
    r'creative|imagine|fiction|creative\s+writing|'
    r'داستان|شعر|خلاقیت)',
    _re.IGNORECASE,
)

# S1 verified live test 2026-07-16 (354 models, 3 working):
#   WORKING: mistral-large, mistral-medium-3-5, tencent-hy3 (all bynara)
#   kimi-k2.7-code-free -> 429 free daily quota (UNRELIABLE; do not route as primary)
# S1 Fix 2026-07-16: Only WORKING models (8 total: 3 mistral, 1 tencent, 2 deepseek, 2 mimo)
# See audit-v2/S1_MODEL_REPORT.md for live test results
_FREE_MODELS = [('tencent-hy3', 'bynara'), ('deepseek-v4-flash-bynara', 'bynara')]
_CODING_MODELS = [('deepseek-v4-pro', 'bynara'), ('mistral-large', 'bynara')]
_REASONING_MODELS = [('deepseek-v4-pro', 'bynara'), ('mimo-v2.5-pro', 'bynara')]
_CREATIVE_MODELS = [('mistral-large', 'bynara'), ('mistral-medium-3-5', 'bynara')]
_DEFAULT_MODEL = ('tencent-hy3', 'bynara')            # cheapest, 1M ctx, reliable
_ADVANCED_MODEL = ('deepseek-v4-pro', 'bynara')        # best reasoning
_PREMIUM_MODEL = ('mimo-v2.5-pro', 'bynara')           # premium coding


def _analyze_message(text: str) -> str:
    if not text or not text.strip():
        return 'simple'
    if _GREETING_PATTERNS.search(text):
        return 'greeting'
    if _CODE_KEYWORDS.search(text):
        return 'code'
    if _REASONING_KEYWORDS.search(text):
        return 'reasoning'
    if _Creative_KEYWORDS.search(text):
        return 'creative'
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    if len(text) > 500 or len(sentences) > 4:
        return 'complex'
    if len(text) > 200:
        return 'medium'
    return 'simple'


async def _get_user_balance(uid: int) -> int:
    if async_session is None:
        return 0
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid'),
                {'uid': uid},
            )
            row = res.fetchone()
            return int(row.balance) if row else 0
    except Exception as e:
        logger.warning(f"_get_user_balance failed uid={uid}: {e}")
        return 0


async def _get_user_plan(uid: int) -> str:
    if async_session is None:
        return 'free'
    try:
        async with async_session() as session:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            res = await session.execute(
                select(Subscription)
                .where(
                    Subscription.user_id == uid,
                    Subscription.status == 'active',
                    (Subscription.ends_at.is_(None)) | (Subscription.ends_at > now),
                )
                .order_by(Subscription.created_at.desc())
                .limit(1)
            )
            sub = res.scalar_one_or_none()
            return sub.plan if sub else 'free'
    except Exception as e:
        logger.warning(f"_get_user_plan failed uid={uid}: {e}")
        return 'free'


def _select_smart_model(category: str, balance: int, plan: str) -> tuple[str, str]:
    if balance < 10000:
        return _FREE_MODELS[0]
    if category in ('greeting', 'simple'):
        return _FREE_MODELS[0]
    if plan in ('pro', 'enterprise', 'unlimited'):
        if category == 'complex':
            return _ADVANCED_MODEL
        if category == 'reasoning':
            return _REASONING_MODELS[1]
        if category == 'code':
            return _CODING_MODELS[0]
        if category == 'creative':
            return _CREATIVE_MODELS[1]
        return _DEFAULT_MODEL
    if category == 'complex':
        return _REASONING_MODELS[0]
    if category == 'reasoning':
        return _REASONING_MODELS[0]
    if category == 'code':
        return _CODING_MODELS[0]
    if category == 'creative':
        return _CREATIVE_MODELS[0]
    if category == 'medium':
        return _DEFAULT_MODEL
    return _DEFAULT_MODEL



async def _select_smart_model_safe(category: str, balance: int, plan: str) -> tuple[str, str]:
    model, provider = _select_smart_model(category, balance, plan)
    if not await is_working_model(model):
        return _DEFAULT_MODEL
    return model, provider

# Working model set (confirmed via live test 2026-07-16)
# _WORKING_SET moved to top of file (near WORKING_MODELS)

@router.post('/v1/smart-chat')
async def smart_chat(request: Request, payload: ChatRequest) -> Response:
    """Smart Mode: auto-selects the cheapest model capable of handling the request."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    payload_dict = payload.model_dump(exclude_none=True)

    messages = payload_dict.get('messages', [])
    last_user_msg = ''
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get('role') == 'user':
            last_user_msg = msg.get('content', '')
            if isinstance(last_user_msg, list):
                parts = []
                for part in last_user_msg:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        parts.append(part.get('text', ''))
                last_user_msg = ' '.join(parts)
            break

    category = _analyze_message(last_user_msg)
    balance = await _get_user_balance(uid)
    plan = await _get_user_plan(uid)

    original_model = payload_dict.get('model', '')
    force_model = request.headers.get('X-Smart-Model', '').strip()
    if force_model and force_model.lower() != 'auto':
        # Whitelist validation for forced model
        if not await _is_model_allowed(force_model if '/' not in force_model else force_model.split('/', 1)[1]):
            logger.info(f"smart_chat blocked forced model={force_model} uid={uid}")
            return JSONResponse(
                {'error': {'message': f'مدل {force_model} در دسترس نیست', 'type': 'invalid_request', 'code': 'model_not_available'}},
                status_code=400,
            )
        if '/' in force_model:
            selected_provider, selected_model = force_model.split('/', 1)
        else:
            selected_model = force_model
            selected_provider = 'bynara2'
    else:
        selected_model, selected_provider = await _select_smart_model_safe(category, balance, plan)

    # P1: BillingService reserve (replaces _check_quota_pre with proper FOR UPDATE locking)
    # Fall back to legacy _check_quota_pre if BillingService fails
    reservation = None
    try:
        async with async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = BillingService(_repo)
            _est_cost = 1000 if await is_working_model(selected_model) else 5000
            reservation = await _bill_svc.reserve(
                uid, Money(_est_cost),
                idempotency_key=f"smart:{secrets.token_hex(8)}",
                model=selected_model,
            )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return JSONResponse(
            {'error': {'message': 'insufficient wallet balance | موجودی کیف پول کافی نیست', 'type': 'quota_exceeded', 'code': 'balance'}},
            status_code=429,
        )
    except Exception as e:
        import traceback
        logger.warning(f"BillingService.reserve failed uid={uid}, falling back to legacy _check_quota_pre: {e}\n{traceback.format_exc()}")
        quota_err = await _check_quota_pre(uid)
        if quota_err is not None:
            return quota_err

    payload_dict['model'] = selected_model

    # Use helper for injection (S2 deduplication)
    try:
        injs = await get_injection_messages(uid)
        if injs:
            messages = inject_messages(messages, injs)
            payload_dict['messages'] = messages
    except Exception as e:
        logger.warning(f"smart_chat injection failed uid={uid}: {e}")

    # Compress old messages to reduce token usage (smart_chat)
    try:
        _orig = [m.copy() for m in payload_dict.get('messages', [])]
        payload_dict['messages'] = compress_messages(payload_dict.get('messages', []), preserve_last=2)
        _sav = estimate_savings(_orig, payload_dict['messages'])
        if _sav['savings_pct'] > 0:
            logger.info(f"Headroom smart: {_sav['savings_pct']}%% saved ({_sav['saved_chars']} chars)")
    except Exception as e:
        logger.debug(f"Compression skipped: {e}")

    stream = payload_dict.get('stream', False)
    if stream:
        # P1: Release reservation before streaming (stream billing handles actual cost in finally)
        if reservation:
            try:
                async with async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = BillingService(_rel_repo)
                    await _rel_svc.release(reservation['reservation_id'])
                    await _rel_session.commit()
            except Exception as _rel_e:
                logger.warning(f"BillingService.release before stream failed uid={uid}: {_rel_e}")
        return await _smart_chat_stream(payload_dict, request, selected_model, category)

    try:
        _provider = await _resolve_provider(selected_model)
        r = await _http.post(
            f'{_provider.v1}/chat/completions',
            json=payload_dict,
            headers={**_provider.headers(), 'Accept': 'application/json'},
        )
        if r.status_code == 200:
            cost_info = await _track_usage(request, payload_dict, r.json())
            resp_data = r.json()
            if cost_info and cost_info.get('cost', 0) > 0:
                resp_data['billing'] = {
                    'cost': cost_info.get('cost', 0),
                    'input_tokens': cost_info.get('input_tokens', 0),
                    'output_tokens': cost_info.get('output_tokens', 0),
                    'balance_after': cost_info.get('balance_after', 0),
                    'currency': 'IRT',
                }
            # P1: Release reservation after successful billing (track_usage already wrote ledger)
            if reservation:
                try:
                    async with async_session() as _rel_session:
                        _rel_repo = SqlBillingRepo(_rel_session)
                        _rel_svc = BillingService(_rel_repo)
                        await _rel_svc.release(reservation['reservation_id'])
                        await _rel_session.commit()
                except Exception as _rel_e:
                    logger.warning(f"BillingService.release after success failed uid={uid}: {_rel_e}")
            resp = Response(content=json.dumps(resp_data), status_code=200, media_type='application/json')
        else:
            if reservation:
                try:
                    async with async_session() as _rel_session:
                        _rel_repo = SqlBillingRepo(_rel_session)
                        _rel_svc = BillingService(_rel_repo)
                        await _rel_svc.release(reservation['reservation_id'])
                        await _rel_session.commit()
                except Exception as _rel_e:
                    logger.warning(f"BillingService.release on upstream error failed uid={uid}: {_rel_e}")
            resp = Response(content=r.content, status_code=r.status_code, media_type='application/json')
        # P3: Fire background auto-memory extraction
        _fire_memory_extraction(uid, payload_dict.get('messages', []))
        resp.headers['X-Smart-Model'] = selected_model
        resp.headers['X-Smart-Category'] = category
        resp.headers['X-Smart-Provider'] = selected_provider
        if original_model and original_model != selected_model:
            resp.headers['X-Smart-Original-Model'] = original_model
        return resp
    except Exception as e:
        logger.warning(f"smart_chat gateway error uid={uid} model={selected_model}: {e}")
        # P1: Release reservation on error
        if reservation:
            try:
                async with async_session() as _rel_session:
                    _rel_repo = SqlBillingRepo(_rel_session)
                    _rel_svc = BillingService(_rel_repo)
                    await _rel_svc.release(reservation['reservation_id'])
                    await _rel_session.commit()
            except Exception as _rel_e:
                logger.warning(f"BillingService.release on error failed uid={uid}: {_rel_e}")
        return JSONResponse(
            {'detail': 'سرویس موقتاً در دسترس نیست', 'code': 'gateway_error'},
            status_code=502,
        )


async def _smart_chat_stream(
    payload: dict[str, Any],
    request: Request,
    selected_model: str,
    category: str,
):
    """Stream smart chat completion via SSE."""
    uid = await _get_user_id(request)

    # Dedup guard + helper (previously duplicated)
    if uid:
        try:
            injs = await get_injection_messages(uid)
            if injs:
                payload['messages'] = inject_messages(payload.get('messages', []), injs)
        except Exception as e:
            logger.warning(f"_smart_chat_stream injection failed uid={uid}: {e}")

    async def event_stream():
        usage_data = None
        try:
            payload['stream'] = True
            payload.setdefault('stream_options', {})
            if isinstance(payload['stream_options'], dict):
                payload['stream_options']['include_usage'] = True
            import httpx
            _provider = await _resolve_provider(selected_model)
            async with _http.stream(
                'POST',
                f'{_provider.v1}/chat/completions',
                json=payload,
                headers={**_provider.headers(), 'Accept': 'text/event-stream'},
                timeout=httpx.Timeout(90, connect=10, read=90),
            ) as r:
                yield f'data: {json.dumps({"type": "smart_info", "model": selected_model, "category": category})}\n\n'
                async for line in r.aiter_lines():
                    if await request.is_disconnected():
                        logger.info(f"_smart_chat_stream disconnected uid={uid} model={selected_model}")
                        break
                    if line:
                        stripped = line.strip()
                        if stripped.startswith('data:'):
                            data_str = stripped[5:].strip()
                            if data_str == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data_str)
                                if isinstance(chunk.get('usage'), dict) and chunk['usage']:
                                    usage_data = chunk['usage']
                            except (json.JSONDecodeError, ValueError):
                                pass
                        yield f'{line}\n\n'
        except Exception as e:
            logger.warning(f"_smart_chat_stream error uid={uid} model={selected_model}: {e}")
            yield f'data: {json.dumps({"error": f"upstream unavailable: {e}"})}\n\n'
        finally:
            if uid and usage_data and async_session is not None:
                try:
                    cost_info = await _bill_stream_usage(uid, payload, usage_data)
                    if cost_info and cost_info.get('cost', 0) > 0:
                        billing_event = json.dumps({
                            'type': 'billing',
                            'cost': cost_info.get('cost', 0),
                            'input_tokens': cost_info.get('input_tokens', 0),
                            'output_tokens': cost_info.get('output_tokens', 0),
                            'balance_after': cost_info.get('balance_after', 0),
                            'currency': 'IRT',
                        })
                        yield f'data: {billing_event}\n\n'
                except Exception as e:
                    logger.warning(f"_smart_chat_stream billing emit failed uid={uid}: {e}")
            # P3: Fire background auto-memory extraction (streaming)
            if uid:
                _fire_memory_extraction(uid, payload.get('messages', []))

    response = StreamingResponse(event_stream(), media_type='text/event-stream')
    response.headers['X-Smart-Model'] = selected_model
    response.headers['X-Smart-Category'] = category
    return response
