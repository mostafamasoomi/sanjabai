"""
Chat endpoints: /v1/chat/completions, /v1/chat/with-file, /v1/smart-chat.
Includes streaming, usage tracking, web search, and smart model selection.
"""
from __future__ import annotations

import io
import json
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

from database import async_session, _http, LITELLM_HOST
from models import Quota, Assistant, Ledger, Subscription, UserMemory
from dependencies import _get_user_id, _get_user_memories, _to_fa

router = APIRouter()


class ChatRequest(BaseModel):
    model: str = ''
    messages: list = []
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    web_search: bool = False
    assistant_id: int | None = None


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB hard cap


# ── Shared helpers ──────────────────────────────────────────────

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
    except Exception:
        pass
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
            return '', f'pdf extract error: {e}'
    return '', f'unsupported file type: {name or "unknown"}'


async def _web_search(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo via httpx. Returns formatted results."""
    try:
        from urllib.parse import unquote
        r = await _http.post(
            'https://html.duckduckgo.com/html/',
            data={'q': query, 'b': ''},
            headers={'User-Agent': 'Mozilla/5.0 (compatible; Multiai/1.0)'},
            timeout=12, follow_redirects=True,
        )
        if r.status_code != 200:
            return ''
        html = r.text
        links = _re.findall(r'class="result__a"\s+href="([^"]+)"[^>]*>(.+?)</a>', html)
        snippets = _re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, _re.DOTALL)
        if not links:
            return ''
        lines = []
        for i, (href, title) in enumerate(links[:max_results]):
            title = _re.sub(r'<[^>]+>', '', title).strip()
            snippet = _re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ''
            actual_url = href
            if 'uddg=' in href:
                m = _re.search(r'uddg=([^&]+)', href)
                if m:
                    actual_url = unquote(m.group(1))
            lines.append(f'• {title}\n  {snippet}\n  {actual_url}')
        return '\n'.join(lines)
    except Exception:
        return ''


async def _record_usage(session: AsyncSession, uid: int, payload: dict[str, Any], usage: dict[str, Any]) -> None:
    """Shared billing logic for tracking and billing usage."""
    total_tokens = usage.get('total_tokens', 0)
    if total_tokens <= 0:
        return
    model = payload.get('model', '')
    input_tokens = int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0)
    output_tokens = int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)

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
    except Exception:
        pass

    if price_row:
        inp_rate = float(price_row.input_per_million or 0)
        out_rate = float(price_row.output_per_million or 0)
        cost = max(1, int((input_tokens * inp_rate + output_tokens * out_rate + 500_000) // 1_000_000))
    else:
        cost = max(1, total_tokens // 1000)

    res = await session.execute(
        sqlalchemy.text('SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid FOR UPDATE'),
        {'uid': uid},
    )
    row = res.fetchone()
    current = row.balance if row else 0
    if current >= cost:
        entry = Ledger(user_id=uid, amount=-cost, balance_after=current - cost, reason=f'مصرف {model}')
        session.add(entry)

    try:
        from services.billing import SqlBillingRepo
        from services.metering import record_usage
        from services.money import Money
        _repo = SqlBillingRepo(session)
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
    except Exception:
        pass


async def _track_usage(request: Request, payload: dict[str, Any], response_data: dict[str, Any]):
    """Record token usage for non-streaming requests."""
    uid = await _get_user_id(request)
    if not uid or async_session is None:
        return
    usage = response_data.get('usage', {})
    if usage.get('total_tokens', 0) <= 0:
        return
    try:
        async with async_session() as session:
            await _record_usage(session, uid, payload, usage)
            await session.commit()
    except Exception:
        pass


async def _bill_stream_usage(uid: int, payload: dict[str, Any], usage: dict[str, Any]):
    """Bill the user after a streaming chat completes."""
    if usage.get('total_tokens', 0) <= 0:
        return
    try:
        async with async_session() as session:
            await _record_usage(session, uid, payload, usage)
            await session.commit()
    except Exception:
        pass


async def _chat_stream(payload: dict[str, Any], request: Request):
    """Stream chat completion via SSE, collecting usage for billing."""
    uid = await _get_user_id(request)

    if uid and not any(
        isinstance(m, dict) and m.get('content', '').startswith('[User Memories]')
        for m in payload.get('messages', [])
    ):
        memories = await _get_user_memories(uid)
        if memories:
            memory_block = '\n'.join(f'- {m}' for m in memories)
            memory_msg = {'role': 'system', 'content': f'[User Memories]\n{memory_block}'}
            messages = payload.get('messages', [])
            insert_idx = 0
            for i, msg in enumerate(messages):
                if isinstance(msg, dict) and msg.get('role') == 'system':
                    insert_idx = i + 1
                    break
            messages.insert(insert_idx, memory_msg)
            payload['messages'] = messages

    async def event_stream():
        usage_data = None
        try:
            payload['stream'] = True
            payload.setdefault('stream_options', {})
            if isinstance(payload['stream_options'], dict):
                payload['stream_options']['include_usage'] = True
            async with _http.stream('POST', f"{LITELLM_HOST}/v1/chat/completions", json=payload, headers={'Accept': 'text/event-stream'}) as r:
                async for line in r.aiter_lines():
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
            yield f'data: {{"error": "سرویس موقتاً در دسترس نیست", "code": "gateway_error"}}\n\n'
        finally:
            if uid and usage_data and async_session is not None:
                try:
                    await _bill_stream_usage(uid, payload, usage_data)
                except Exception:
                    pass

    return StreamingResponse(event_stream(), media_type='text/event-stream')


# ── Routes ──────────────────────────────────────────────────────

@router.post('/v1/chat/completions')
async def chat(request: Request, payload: ChatRequest) -> Response:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    payload = payload.model_dump(exclude_none=True)

    quota_err = await _check_quota_pre(uid)
    if quota_err is not None:
        return quota_err

    # Assistant injection
    _assistant_id = payload.pop('assistant_id', None)
    if _assistant_id and async_session is not None:
        try:
            async with async_session() as _asession:
                _ares = await _asession.execute(
                    Assistant.__table__.select().where(Assistant.id == int(_assistant_id))
                )
                _arow = _ares.fetchone()
                if _arow and _arow.system_prompt:
                    _sys_msg = {'role': 'system', 'content': _arow.system_prompt}
                    _msgs = payload.get('messages', [])
                    _msgs.insert(0, _sys_msg)
                    payload['messages'] = _msgs
                    if _arow.model_id and not payload.get('model'):
                        payload['model'] = _arow.model_id
        except Exception:
            pass

    # Memory injection
    memories = await _get_user_memories(uid)
    if memories:
        memory_block = '\n'.join(f'- {m}' for m in memories)
        memory_msg = {'role': 'system', 'content': f'[User Memories]\n{memory_block}'}
        messages = payload.get('messages', [])
        insert_idx = 0
        for i, msg in enumerate(messages):
            if isinstance(msg, dict) and msg.get('role') == 'system':
                insert_idx = i + 1
                break
        messages.insert(insert_idx, memory_msg)
        payload['messages'] = messages

    # Web search injection
    if payload.pop('web_search', False):
        _msgs = payload.get('messages', [])
        _query = ''
        for _m in reversed(_msgs):
            if isinstance(_m, dict) and _m.get('role') == 'user':
                _query = _m.get('content', '')
                break
        if _query:
            _results = await _web_search(_query)
            if _results:
                _search_msg = {'role': 'system', 'content': f'[Web Search Results for: {_query[:100]}]\n{_results}'}
                _idx = 0
                for _i, _m in enumerate(_msgs):
                    if isinstance(_m, dict) and _m.get('role') == 'system':
                        _idx = _i + 1
                _msgs.insert(_idx, _search_msg)
                payload['messages'] = _msgs

    stream = payload.get('stream', False)
    if stream:
        return await _chat_stream(payload, request)
    try:
        r = await _http.post(f"{LITELLM_HOST}/v1/chat/completions", json=payload, headers={'Accept': 'application/json'})
        if r.status_code == 200:
            await _track_usage(request, payload, r.json())
            return Response(content=r.content, status_code=200, media_type='application/json')
        return Response(content=r.content, status_code=r.status_code, media_type='application/json')
    except Exception as e:
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
    quota_err = await _check_quota_pre(uid)
    if quota_err is not None:
        return quota_err
    try:
        msgs = json.loads(messages) if messages else []
    except Exception:
        msgs = []
    if not isinstance(msgs, list):
        msgs = []
    text, err = await _extract_file_text(file)
    if err:
        return JSONResponse({'error': {'message': err, 'type': 'file_error'}}, status_code=400)
    if text.strip():
        file_block = f'[Attached file: {file.filename}]\n\n{text[:50000]}'
        msgs.append({'role': 'user', 'content': file_block})
    selected_model = model or 'mimo-v2.5'
    payload = {'model': selected_model, 'messages': msgs, 'stream': stream}
    memories = await _get_user_memories(uid)
    if memories:
        memory_block = '\n'.join(f'- {m}' for m in memories)
        memory_msg = {'role': 'system', 'content': f'[User Memories]\n{memory_block}'}
        insert_idx = 0
        for i, msg in enumerate(msgs):
            if isinstance(msg, dict) and msg.get('role') == 'system':
                insert_idx = i + 1
                break
        msgs.insert(insert_idx, memory_msg)
        payload['messages'] = msgs
    if stream:
        return await _chat_stream(payload, request)
    try:
        r = await _http.post(
            f'{LITELLM_HOST}/v1/chat/completions', json=payload,
            headers={'Accept': 'application/json'},
        )
        if r.status_code == 200:
            await _track_usage(request, payload, r.json())
            return Response(content=r.content, status_code=200, media_type='application/json')
        return Response(content=r.content, status_code=r.status_code, media_type='application/json')
    except Exception as e:
        return JSONResponse(
            {'detail': 'سرویس موقتاً در دسترس نیست', 'code': 'gateway_error'},
            status_code=502,
        )


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

_FREE_MODELS = [('qwen3-coder-free', 'openrouter'), ('hermes-3-405b-free', 'openrouter')]
_CODING_MODELS = [('qwen3-coder-free', 'openrouter'), ('mimo-v2.5', 'bynara2')]
_REASONING_MODELS = [('mimo-v2.5', 'bynara2'), ('mimo-v2.5-pro', 'bynara2')]
_CREATIVE_MODELS = [('mimo-v2.5', 'bynara2'), ('mimo-v2.5-pro', 'bynara2')]
_DEFAULT_MODEL = ('mimo-v2.5', 'bynara2')
_ADVANCED_MODEL = ('mimo-v2.5-pro', 'bynara2')
_PREMIUM_MODEL = ('gpt-5.6-luna', 'bynara2')


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
    except Exception:
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
    except Exception:
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


@router.post('/v1/smart-chat')
async def smart_chat(request: Request, payload: ChatRequest) -> Response:
    """Smart Mode: auto-selects the cheapest model capable of handling the request."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    payload = payload.model_dump(exclude_none=True)

    quota_err = await _check_quota_pre(uid)
    if quota_err is not None:
        return quota_err

    messages = payload.get('messages', [])
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

    original_model = payload.get('model', '')
    force_model = request.headers.get('X-Smart-Model', '').strip()
    if force_model and force_model.lower() != 'auto':
        if '/' in force_model:
            selected_provider, selected_model = force_model.split('/', 1)
        else:
            selected_model = force_model
            selected_provider = 'bynara2'
    else:
        selected_model, selected_provider = _select_smart_model(category, balance, plan)

    payload['model'] = selected_model

    memories = await _get_user_memories(uid)
    if memories:
        memory_block = '\n'.join(f'- {m}' for m in memories)
        memory_msg = {'role': 'system', 'content': f'[User Memories]\n{memory_block}'}
        insert_idx = 0
        for i, msg in enumerate(messages):
            if isinstance(msg, dict) and msg.get('role') == 'system':
                insert_idx = i + 1
                break
        messages.insert(insert_idx, memory_msg)
        payload['messages'] = messages

    stream = payload.get('stream', False)
    if stream:
        return await _smart_chat_stream(payload, request, selected_model, category)

    try:
        r = await _http.post(
            f'{LITELLM_HOST}/v1/chat/completions',
            json=payload,
            headers={'Accept': 'application/json'},
        )
        if r.status_code == 200:
            await _track_usage(request, payload, r.json())
            resp = Response(content=r.content, status_code=200, media_type='application/json')
        else:
            resp = Response(content=r.content, status_code=r.status_code, media_type='application/json')
            resp.headers['X-Smart-Model'] = selected_model
            resp.headers['X-Smart-Category'] = category
            resp.headers['X-Smart-Provider'] = selected_provider
            if original_model and original_model != selected_model:
                resp.headers['X-Smart-Original-Model'] = original_model
            return resp
    except Exception as e:
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

    if uid and not any(
        isinstance(m, dict) and m.get('content', '').startswith('[User Memories]')
        for m in payload.get('messages', [])
    ):
        memories = await _get_user_memories(uid)
        if memories:
            memory_block = '\n'.join(f'- {m}' for m in memories)
            memory_msg = {'role': 'system', 'content': f'[User Memories]\n{memory_block}'}
            messages = payload.get('messages', [])
            insert_idx = 0
            for i, msg in enumerate(messages):
                if isinstance(msg, dict) and msg.get('role') == 'system':
                    insert_idx = i + 1
                    break
            messages.insert(insert_idx, memory_msg)
            payload['messages'] = messages

    async def event_stream():
        usage_data = None
        try:
            payload['stream'] = True
            payload.setdefault('stream_options', {})
            if isinstance(payload['stream_options'], dict):
                payload['stream_options']['include_usage'] = True
            async with _http.stream(
                'POST',
                f'{LITELLM_HOST}/v1/chat/completions',
                json=payload,
                headers={'Accept': 'text/event-stream'},
            ) as r:
                yield f'data: {json.dumps({"type": "smart_info", "model": selected_model, "category": category})}\n\n'
                async for line in r.aiter_lines():
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
            yield f'data: {{"error": "upstream unavailable: {e}"}}\n\n'
        finally:
            if uid and usage_data and async_session is not None:
                try:
                    await _bill_stream_usage(uid, payload, usage_data)
                except Exception:
                    pass

    response = StreamingResponse(event_stream(), media_type='text/event-stream')
    response.headers['X-Smart-Model'] = selected_model
    response.headers['X-Smart-Category'] = category
    return response
