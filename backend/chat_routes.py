"""
Core chat endpoints: /v1/chat/completions and /v1/chat/with-file.

Pulled out of chat.py (which was well past the project's 500-line ceiling).
These are the two main completion endpoints with billing, assistant injection,
context/memory injection, web search grounding, and message compression.

Model-selection helpers that read ``chat.async_session`` (``_is_model_allowed``,
``is_working_model``, ``_resolve_provider``) are imported lazily from the chat
aggregator so test patches of ``chat.async_session`` keep reaching them.
"""
from __future__ import annotations

import json
import logging
import secrets
import time as _time

from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response

from database import async_session, _http
from models import Assistant
from dependencies import _get_user_id
from services.context_injection import get_injection_messages, inject_messages
from middleware.compression import compress_messages, estimate_savings
from services.billing import SqlBillingRepo, BillingService, InsufficientBalanceError
from services.money import Money

from chat_common import ChatRequest, MAX_FILE_SIZE, _fire_memory_extraction, _record_model_health
from chat_billing import _release_reservation, _check_quota_pre, _track_usage
from chat_tools import _web_search, _extract_file_text
from chat_stream import _chat_stream

logger = logging.getLogger(__name__)

router = APIRouter()


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
            from chat import is_working_model
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
    if model_to_check:
        from chat import _is_model_allowed
        if not await _is_model_allowed(model_to_check):
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
        from chat import _resolve_provider
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
            from chat import is_working_model
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
    from chat import _is_model_allowed
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
        from chat import _resolve_provider
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
