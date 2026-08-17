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
    _model = payload_dict.get('model', '') or 'tencent-hy3'
    payload_dict['model'] = _model
    try:
        async with async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = BillingService(_repo)

            # Token-aware estimate: use max_tokens if provided, else a reasonable upper bound.
            # We settle the actual usage later, so overestimating here is safe and prevents under-reservation.
            _max_tokens = int(payload_dict.get('max_tokens') or 4000)
            _prompt_tokens = sum(len(m.get('content', '')) // 4 for m in payload_dict.get('messages', []) if isinstance(m, dict))
            _est_tokens = _prompt_tokens + _max_tokens

            # Approximate cost: fetch price from model_catalog if possible, otherwise use a safe default
            _price_row = None
            try:
                import sqlalchemy
                _price_res = await _bill_session.execute(
                    sqlalchemy.text(
                        'SELECT input_per_million, output_per_million FROM model_catalog '
                        'WHERE provider_model_id = :mid AND availability = :avail LIMIT 1'
                    ),
                    {'mid': _model, 'avail': 'available'},
                )
                _price_row = _price_res.fetchone()
            except Exception:
                pass

            if _price_row:
                inp_rate = int(_price_row.input_per_million or 0)
                out_rate = int(_price_row.output_per_million or 0)
                _est_cost = max(1, int((_prompt_tokens * inp_rate + _max_tokens * out_rate + 500_000) // 1_000_000))
            else:
                # Fallback to a safe estimate based on tokens
                _est_cost = max(10, _est_tokens // 100)

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
        # Do NOT release before streaming. The stream handler will settle or release in its finally block.
        return await _chat_stream(payload_dict, request, reservation=reservation)
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
            resp_data = r.json()
            cost_info = await _track_usage(request, payload_dict, resp_data)
            actual_cost = cost_info.get('cost', 0) if cost_info else 0

            if cost_info and actual_cost > 0:
                resp_data['billing'] = {
                    'cost': actual_cost,
                    'input_tokens': cost_info.get('input_tokens', 0),
                    'output_tokens': cost_info.get('output_tokens', 0),
                    'balance_after': cost_info.get('balance_after', 0),
                    'currency': 'IRT',
                }

            # P1: Settle reservation with actual cost, releasing remainder
            if reservation:
                try:
                    async with async_session() as _settle_session:
                        _settle_repo = SqlBillingRepo(_settle_session)
                        _settle_svc = BillingService(_settle_repo)
                        if actual_cost > 0:
                            await _settle_svc.settle(reservation['reservation_id'], Money(actual_cost))
                        else:
                            await _settle_svc.release(reservation['reservation_id'])
                        await _settle_session.commit()
                except Exception as e:
                    logger.warning(f"BillingService.settle failed uid={uid} res={reservation['reservation_id']}: {e}")

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
    selected_model = model or 'tencent-hy3'
    try:
        async with async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = BillingService(_repo)

            # Token-aware estimate
            _max_tokens = 4000
            try:
                _msgs_tmp = json.loads(messages) if messages else []
                _prompt_tokens = sum(len(m.get('content', '')) // 4 for m in _msgs_tmp if isinstance(m, dict))
            except Exception:
                _prompt_tokens = 1000
            _est_tokens = _prompt_tokens + _max_tokens

            _price_row = None
            try:
                import sqlalchemy
                _price_res = await _bill_session.execute(
                    sqlalchemy.text(
                        'SELECT input_per_million, output_per_million FROM model_catalog '
                        'WHERE provider_model_id = :mid AND availability = :avail LIMIT 1'
                    ),
                    {'mid': selected_model, 'avail': 'available'},
                )
                _price_row = _price_res.fetchone()
            except Exception:
                pass

            if _price_row:
                inp_rate = int(_price_row.input_per_million or 0)
                out_rate = int(_price_row.output_per_million or 0)
                _est_cost = max(1, int((_prompt_tokens * inp_rate + _max_tokens * out_rate + 500_000) // 1_000_000))
            else:
                _est_cost = max(10, _est_tokens // 100)

            reservation = await _bill_svc.reserve(
                uid, Money(_est_cost),
                idempotency_key=f"file:{secrets.token_hex(8)}",
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
        # Pass reservation to stream handler
        return await _chat_stream(payload, request, reservation=reservation)
    try:
        from chat import _resolve_provider
        _provider = await _resolve_provider(selected_model)
        r = await _http.post(
            f'{_provider.v1}/chat/completions', json=payload,
            headers={**_provider.headers(), 'Accept': 'application/json'},
        )
        if r.status_code == 200:
            resp_data = r.json()
            cost_info = await _track_usage(request, payload, resp_data)
            actual_cost = cost_info.get('cost', 0) if cost_info else 0

            if cost_info and actual_cost > 0:
                resp_data['billing'] = {
                    'cost': actual_cost,
                    'input_tokens': cost_info.get('input_tokens', 0),
                    'output_tokens': cost_info.get('output_tokens', 0),
                    'balance_after': cost_info.get('balance_after', 0),
                    'currency': 'IRT',
                }

            # P1: Settle reservation with actual cost
            if reservation:
                try:
                    async with async_session() as _settle_session:
                        _settle_repo = SqlBillingRepo(_settle_session)
                        _settle_svc = BillingService(_settle_repo)
                        if actual_cost > 0:
                            await _settle_svc.settle(reservation['reservation_id'], Money(actual_cost))
                        else:
                            await _settle_svc.release(reservation['reservation_id'])
                        await _settle_session.commit()
                except Exception as e:
                    logger.warning(f"BillingService.settle failed uid={uid} res={reservation['reservation_id']}: {e}")

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
