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
import secrets

from fastapi import Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response

from i18n import err, err_openai
from dependencies import _to_fa
from services.context_injection import inject_messages
from services.token_budget import apply_outbound_budget
from services.billing import SqlBillingRepo, BillingService, InsufficientBalanceError
from services.money import Money
from services.entitlement_gate import covering_entitlement
from services.moderation import moderation_preflight
from services.user_quota import check_and_consume as _user_quota_check
from services.premium_quota import check_and_consume as _premium_quota_check
from model_output import clean_response_dict

import chat
from providers import COMPLETION_TIMEOUT_SECONDS
from site_settings import get_site_flag

logger = logging.getLogger('chat')  # keep all chat_*.py logs under the pre-split 'chat' logger name

# Re-exported so chat.py line 276's `from chat_web import _apply_web_search,
# _web_search, ...` keeps working after the search code moved to chat_search.py
# (that move was forced by the 500-line cap, not by any behaviour change).
# Tests monkeypatch `chat._web_search`; chat_search._apply_web_search reads it
# off the `chat` module at call time, so patching still reaches it -- see
# chat_search.py's IMPORT CONTRACT before touching this.
from chat_search import _web_search, _apply_web_search  # noqa: F401,E402

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB hard cap


async def _chat_disabled_response() -> JSONResponse | None:
    """503 while the ``chat_enabled`` site flag is off; None otherwise.

    The single implementation behind all FOUR chat entry points --
    /v1/chat/completions, /v1/chat/with-file, /v1/smart-chat and
    /v1/compare -- which now reach it through ``_chat_preflight`` below,
    itself reached as ``chat._chat_preflight``; ``_chat_preflight`` still
    calls this one as ``chat._chat_disabled_response`` so the existing
    monkeypatches keep gating every route. Gating only one route would make
    the admin's switch a lie, since the other three would keep serving.

    Lives here rather than in chat.py for the same reason
    _release_reservation below does: to keep chat.py under the house
    500-line cap.
    """
    if await get_site_flag('chat_enabled'):
        return None
    return err_openai(
            'گفتگو موقتاً در دسترس نیست',
            'Chat is temporarily unavailable.',
            503, code='chat_disabled', err_type='service_unavailable',
        )


async def _chat_preflight(uid: int, messages) -> JSONResponse | None:
    """THE pre-flight gate. Every chat entry point's first act after
    resolving the user; a non-None return is the response to send.

    ONE CHOKE POINT, NOT SIX. There are four chat HTTP routes --
    /v1/chat/completions (chat.py), /v1/chat/with-file (this file),
    /v1/smart-chat (chat_smart.py), /v1/compare (chat_compare.py).
    chat_stream.py registers no route of its own: `_chat_stream` /
    `_smart_chat_stream` are helpers those routes call *after* their own
    gates, so gating the four routes gates streaming too. All four already
    awaited `_chat_disabled_response()` as their first gate; this function
    is that same gate plus content screening, so the screen is called from
    exactly ONE place in the codebase.

    WHY NOT get_injection_messages(). That helper is the one thing all six
    chat call sites share, and it is where Session 9's skill injection went
    -- but all six of its call sites run AFTER that route's
    `BillingService.reserve()`. Screening there would open a wallet
    reservation on a request we are about to refuse, i.e. spend to protect
    nothing. This gate runs BEFORE the free-tier gate and BEFORE reserve(),
    so a blocked request touches neither the wallet nor an upstream.

    `_chat_disabled_response` is reached as `chat._chat_disabled_response`
    (late-bound through the `chat` facade) rather than as the bare
    same-module global, so `patch.object(chat_mod, '_chat_disabled_response')`
    still gates every route -- see this module's MONKEYPATCH CONTRACT.

    `messages` is passed through untouched to services/moderation.py, which
    accepts both call-site shapes: the list of message dicts the JSON routes
    carry and the JSON *string* /v1/chat/with-file receives as a Form field.
    Screening never mutates it -- a clean payload goes upstream byte for
    byte -- and it never raises: a broken detector allows the request (see
    services/moderation.py's fail-safe contract).

    THE AGGREGATE MESSAGE QUOTA (services/user_quota.py) is charged here,
    last, and this is its ONLY call site in the codebase. Here because it is
    the one function all four routes share, it is per-user rather than
    per-model (so unlike the per-model free-tier gate it does not need to
    wait for model resolution), and it already sits after user resolution
    and far before every BillingService.reserve() -- a request rejected on
    quota never opens a wallet reservation, so there is never one to unwind.
    Charged AFTER the screen so a message blocked for content costs the user
    nothing, and it charges ONE message per HTTP request -- including
    /v1/compare, which fans out to two models on that single message. It
    never raises: services/user_quota.py fails open on any Redis/DB error.
    """
    disabled = await chat._chat_disabled_response()
    if disabled is not None:
        return disabled
    screened = await moderation_preflight(uid, messages)
    if screened is not None:
        return screened
    gate = await _user_quota_check(uid)
    if gate is not None:
        return _user_quota_response(gate)
    return None


def _user_quota_response(gate: dict) -> JSONResponse:
    """The 429 for an aggregate message-quota rejection.

    Deliberately the same shape as chat.py::_free_tier_response (429,
    ``error.type='rate_limited'``, a Persian message and a numeric
    ``retry_after_seconds``) so the frontend's existing error handling needs
    no change -- only ``error.code`` differs, so the two caps stay
    distinguishable in logs and in support. Numerals go through
    dependencies._to_fa via chat._persian_duration, per the Persian-first
    rule; the limit itself is rendered with _to_fa for the same reason.
    """
    retry = int(gate.get('retry_after_seconds', 0))
    limit = int(gate.get('limit', 0))
    if gate.get('source') == 'package':
        tail = 'برای سقف بالاتر، بستهٔ بزرگ‌تری تهیه کنید.'
    else:
        tail = 'با تهیهٔ بسته یا شارژ حساب، سقف شما افزایش می‌یابد.'
    message = (
        f'سقف {_to_fa(limit)} پیام در هر ۵ ساعت پر شده است. '
        f'حدود {chat._persian_duration(retry)} دیگر دوباره فعال می‌شود. {tail}'
    )
    return JSONResponse(
        {'error': {
            'message': message,
            'type': 'rate_limited',
            'code': 'message_quota_exceeded',
            'limit': limit,
            'used': int(gate.get('used', 0)),
            'source': gate.get('source', ''),
            'retry_after_seconds': retry,
        }},
        status_code=429,
    )


def _premium_quota_response(gate: dict) -> JSONResponse:
    """The 429 for a premium/expensive-model sub-allowance rejection
    (services/premium_quota.py) -- a different ``error.code`` from both
    ``message_quota_exceeded`` (this file's own aggregate gate) and
    ``free_tier_throttle`` (chat.py's), so the three stay distinguishable in
    logs and support.

    Unlike :func:`_user_quota_response`, the Persian message is built
    entirely inside premium_quota.py's gate dict (the same split
    chat.py::_free_tier_response uses for services/free_tier.py) since the
    message needs no piece of information this function has that the gate
    dict does not already carry -- this only shapes the HTTP envelope.
    """
    return JSONResponse(
        {'error': {
            'message': gate.get('message', 'سهم مدل‌های پیشرفته حساب شما پر شده است.'),
            # The gate builds a reason-specific pair (services/free_tier.py,
            # services/premium_quota.py); these defaults only cover a gate
            # shape that predates them.
            'message_en': gate.get('message_en', 'Your premium-model allowance is used up.'),
            'type': 'rate_limited',
            'code': gate.get('code', 'premium_quota_exceeded'),
            'retry_after_seconds': int(gate.get('retry_after_seconds', 0)),
        }},
        status_code=429,
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
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)
    _disabled = await chat._chat_preflight(uid, messages)
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

    # Premium (expensive-model) sub-allowance gate (services/premium_quota.py,
    # migration 0046) — runs after the free-tier gate above and strictly
    # before BillingService.reserve() below, exactly like it: a rejected
    # request must open no reservation and reach no upstream. Needs `model`
    # resolved (it looks up the model's base price), which is why it cannot
    # live in chat._chat_preflight (pre-model, shared by all four routes) and
    # instead sits here at the same post-model point the free-tier gate does.
    _premium_gate = await _premium_quota_check(uid, [model]) if model else None
    if _premium_gate is not None:
        return _premium_quota_response(_premium_gate)

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
        return err_openai(
            'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.',
            'Your wallet balance is not enough. Please top up your account.',
            429, code='balance', err_type='quota_exceeded',
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
    # NOT named `err`: this function also calls the i18n helper `err()`, and
    # Python binds a name assigned anywhere in a body as local for the WHOLE
    # body -- so that call would raise UnboundLocalError before ever reaching
    # this line. Reproduced, not theorised.
    text, extract_err = await _extract_file_text(file)
    if extract_err:
        await _release_reservation(reservation, uid, 'file_error')
        return JSONResponse(
            {'error': {'message': extract_err, 'type': 'file_error'}}, status_code=400,
        )
    if text.strip():
        file_block = f'[Attached file: {file.filename}]\n\n{text[:50000]}'
        msgs.append({'role': 'user', 'content': file_block})
    selected_model = model
    # Whitelist validation
    if not selected_model:
        # _safe_default_model() couldn't find anything in the catalog
        # either -- see the identical check/comment in chat().
        await _release_reservation(reservation, uid, 'no_model_available')
        return err_openai(
            'در حال حاضر مدلی برای انتخاب پیش‌فرض در دسترس نیست. لطفاً یک مدل را به‌صورت دستی انتخاب کنید.',
            'No model is available to pick by default right now. Please choose one manually.',
            400, code='model_not_available', err_type='invalid_request',
        )
    if not await chat._is_model_allowed(selected_model):
        logger.info(f"chat_with_file blocked model={selected_model} uid={uid}")
        await _release_reservation(reservation, uid, 'model_reject')
        return err_openai(
            f'مدل {selected_model} در دسترس نیست',
            f'Model {selected_model} is not available',
            400, code='model_not_available', err_type='invalid_request',
        )
    payload = {'model': selected_model, 'messages': msgs, 'stream': stream}
    # Use helper for injection (S2)
    try:
        injs = await chat.get_injection_messages(uid, messages=msgs)
        if injs:
            payload['messages'] = inject_messages(msgs, injs)
            msgs = payload['messages']
    except Exception as e:
        logger.warning(f"chat_with_file injection failed uid={uid}: {e}")

    # Phase E ceiling -- see services/token_budget.py.
    await apply_outbound_budget(payload)
    msgs = payload['messages']
    if stream:
        await _release_reservation(reservation, uid, 'before_stream')
        return await chat._chat_stream(payload, request)
    try:
        _provider = await chat._resolve_provider(selected_model)
        r = await chat._http.post(
            f'{_provider.v1}/chat/completions', json=payload,
            headers={**_provider.headers(), 'Accept': 'application/json'},
            timeout=COMPLETION_TIMEOUT_SECONDS,
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
        return err('سرویس موقتاً در دسترس نیست', 'The service is temporarily unavailable.', 502)
