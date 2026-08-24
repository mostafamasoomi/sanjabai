"""Document Generator endpoints.

POST /v1/documents/generate  — Generate PPTX/DOCX/MDX from AI prompt
GET  /v1/documents           — List user's generated documents
GET  /v1/documents/{id}/download — Download generated document
DELETE /v1/documents/{id}    — Delete generated document

── THE BUG THIS MODULE CLOSES (2026-08-24) ─────────────────────────────
POST /v1/documents/generate used to post straight to
`{LITELLM_HOST}/v1/chat/completions` with NONE of the gates every other
billed model call in this codebase runs: no `BillingService.reserve()`/
settle (grep `reserve(`/`settle`/`record_usage` was 0 -- charged NOTHING),
no free-tier gate, no package quota gate, no content moderation, and no
catalog/allow-list validation of the client-supplied `model` (straight off
`body.get('model', ...)`, unchanged, to the upstream) -- combined with the
file's `for attempt in range(2)` resilience retry, a failure could even
double the unbilled cost. Violated the two rules that never reopen: «هیچ
درخواستی نباید ضررده باشد» (no request may be loss-making) and «هیچ مدل
رایگانی نداریم» (there are no free models). Precedent: backend/
task_execution.py (commit 5f7b84f) closed the identical hole for scheduled
tasks; this fix mirrors that module's structure and gate order, not a new
billing pattern.

GATE ORDER, all BEFORE `BillingService.reserve()` (a pre-reserve rejection
means there is never a reservation to unwind), matching
chat_web._chat_preflight / task_execution.py exactly:

  1. Model validation (`_resolve_and_validate_model`) -- resolve the
     client-supplied model to a catalog `provider_model_id` and confirm
     it is probe-verified/available, same as chat_web.chat_with_file.
     Unknown/non-working -> Persian error, never forwarded upstream.
     Done FIRST: an unresolved id also misses `_record_usage`'s price
     lookup later and bills the fallback ceiling rate.
  2. `chat_enabled` kill switch (`site_settings.get_site_flag`) -- same
     flag/message as `chat_web._chat_disabled_response()`.
  3. Content moderation (`services.moderation.screen_request`) -- the
     same detector every chat route runs, called directly (not the
     JSONResponse-returning `moderation_preflight` wrapper) so the block
     message reads straight off `Verdict.message_fa`. Never raises; a
     broken detector ALLOWS (fail-safe contract) rather than locking out
     a paying user.
  4. Free-tier gate (`services.free_tier.check_and_consume`) -- hourly +
     lifetime + cheap-models-only; no-ops for a paid/package/balance user.
  5. Aggregate package quota (`services.user_quota.check_and_consume`) --
     caps a package holder; exempt for free tier / balance users.
  6. Premium sub-allowance (`services.premium_quota.check_and_consume`,
     migration 0046) -- of a package's window allowance, how many may be
     spent on an expensive model. Needs the resolved model (it prices it),
     which is why it sits here and not in the pre-model `_chat_preflight`.
  7. `BillingService.reserve()` -- pre-flight availability hold.
  8. The upstream call (`document_ai.generate_content` -- see that
     module's docstring for why its internal retry cannot double-bill).
  9. Bill the REAL cost directly to wallet.balance via
     `chat._bill_stream_usage` (same function task_execution.py uses) --
     this, not `BillingService.settle()`, is what actually charges the
     user; it has its own L1 missing-usage estimate fallback.
  9. Release the pre-flight hold from step 6 -- ALWAYS, failure or
     success (the real charge in step 8 is independent of the hold, so
     there is nothing to "settle" against it -- task_execution.py step 6).

MODULE SPLIT (house 500-line cap). One-directional (no circular import,
unlike the chat_*.py family) -- only this file needs the other two:
  document_ai.py        the one upstream call (`generate_content`) --
                        HTTP + retry + JSON-shape parsing/capping.
  document_builders.py  the three pure file builders + `_escape_mdx_text`.
  document_generator.py this file: `router` (app.py's only external
                        import of this module, grepped 2026-08-24),
                        storage/registry, all four endpoints + gates.

Known constraint, unchanged: the document registry (`_doc_registry`) is
in-memory only, does not survive a restart (documented gap). The
path-traversal defence in `download_document` is preserved exactly.
"""
from __future__ import annotations

import os
import re
import json
import secrets
import time
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse, Response

from database import async_session
from dependencies import _get_user_id
from services.billing import BillingService, InsufficientBalanceError, SqlBillingRepo
from services.free_tier import check_and_consume
from services.moderation import BLOCK_MESSAGE_FA, screen_request
from services.money import Money
from services.premium_quota import check_and_consume as _premium_quota_check
from services.user_quota import check_and_consume as _user_quota_check
from site_settings import get_site_flag

import document_ai
from document_ai import generate_content
from document_builders import _create_pptx, _create_docx, _create_mdx

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Storage ──────────────────────────────────────────────────────
DOC_STORAGE = Path('/tmp/sanjabai_docs')
DOC_STORAGE.mkdir(parents=True, exist_ok=True)

# In-memory doc registry (persists until container restart)
_doc_registry: dict[str, dict] = {}

# ── Safety constants ─────────────────────────────────────────────
MAX_PROMPT_LENGTH = 4000
DOC_ID_RE = re.compile(r'^[0-9a-f]{12}$')
EXT_MAP = {'pptx': '.pptx', 'docx': '.docx', 'mdx': '.md'}

# Reserve is a cheap pre-flight availability hold, not a prediction of the
# real cost -- same shape as chat_with_file's / task_execution.py's
# estimates. Sized higher than chat's (1000/5000) because document
# generation's max_tokens (3072-4096, see document_ai.py) is itself well
# above a typical chat reply -- the real charge (step 8 below) is whatever
# _bill_stream_usage/_record_usage computes from actual usage regardless
# of this number; this only has to not be exceeded on a routine request.
_RESERVE_ESTIMATE_WORKING = 4000
_RESERVE_ESTIMATE_UNKNOWN = 8000

# ── Persian error messages ────────────────────────────────────────
# _CHAT_DISABLED_MESSAGE is byte-for-byte chat_web._chat_disabled_response's
# text, and _FREE_TIER_MESSAGE/_QUOTA_MESSAGE/_INSUFFICIENT_BALANCE_MESSAGE/
# _GATEWAY_ERROR_MESSAGE are byte-for-byte task_execution.py's constants --
# reused deliberately (not reworded) per this fix's "mirror the reference,
# don't invent a new pattern" instruction.
_MODEL_NOT_ALLOWED_MESSAGE = 'مدل انتخابی پشتیبانی نمیشود'
_CHAT_DISABLED_MESSAGE = 'گفتگو موقتاً در دسترس نیست'
_FREE_TIER_MESSAGE = (
    'سقف پیام رایگان این مدل برای اکنون پر شده است؛ کمی بعد دوباره تلاش کنید '
    'یا با شارژ حساب این محدودیت را برای همیشه بردارید.'
)
_QUOTA_MESSAGE = (
    'سقف پیام بستهٔ شما برای این بازه پر شده است؛ کمی بعد دوباره تلاش کنید '
    'یا بستهٔ بزرگ‌تری تهیه کنید.'
)
_INSUFFICIENT_BALANCE_MESSAGE = 'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.'
_GATEWAY_ERROR_MESSAGE = 'سرویس موقتاً در دسترس نیست'


# ── Model resolution/validation ───────────────────────────────────
#
# Late-bound `import chat` inside each function (not at module scope, and
# never `from chat import X`) -- same reasoning as task_execution.py's
# module docstring: chat.py's model-resolution names
# (`_resolve_public_model`, `_safe_default_model`, `_is_model_allowed`) are
# what the test suite monkeypatches directly on the `chat` module, and a
# module-level import would both risk a chat.py <-> document_generator.py
# load-order issue and silently defeat that monkeypatching.

async def _resolve_and_validate_model(requested_model: str) -> str | None:
    """Resolve a user-supplied model string to a catalog `provider_model_id`
    and confirm it is currently probe-verified ('available'), the exact
    same two-step chat_web.chat_with_file uses for a chat request's model.

    Returns ``None`` when nothing usable is available -- never a
    hardcoded model literal (see chat_models._safe_default_model's
    docstring: an unresolved/rotted default silently bills the fallback
    ceiling rate instead of failing honestly).
    """
    import chat as chat_mod
    if requested_model:
        model = await chat_mod._resolve_public_model(requested_model)
    else:
        model = await chat_mod._safe_default_model()
    if not model:
        return None
    if not await chat_mod._is_model_allowed(model):
        return None
    return model


async def _resolve_fallback_model(primary_model: str) -> str | None:
    """Best-effort catalog-verified fallback for document_ai.generate_content's
    internal resilience retry. Returns ``None`` (disabling the model-switch
    on retry, not disabling the retry itself) rather than forwarding an
    unverified model name upstream -- see document_ai.py's `FALLBACK_MODEL`
    docstring for why this must never be the raw literal."""
    import chat as chat_mod
    if document_ai.FALLBACK_MODEL == primary_model:
        return None
    try:
        resolved = await chat_mod._resolve_public_model(document_ai.FALLBACK_MODEL)
        if resolved and resolved != primary_model and await chat_mod._is_model_allowed(resolved):
            return resolved
    except Exception as e:
        logger.warning(f"document_generator: fallback model resolution failed: {e}")
    return None


async def _release_reservation(reservation: dict | None, uid: int, label: str = '') -> None:
    """Release a billing reservation; fire-and-forget, logs on failure.
    Mirrors chat_web._release_reservation / task_execution._release."""
    if not reservation or async_session is None:
        return
    try:
        async with async_session() as s:
            repo = SqlBillingRepo(s)
            svc = BillingService(repo)
            await svc.release(reservation['reservation_id'])
            await s.commit()
    except Exception as e:
        logger.warning(f"document_generator._release_reservation failed uid={uid} {label}: {e}")


# ── Endpoints ────────────────────────────────────────────────────

@router.post('/v1/documents/generate')
async def generate_document(request: Request) -> JSONResponse:
    """Generate a document from a prompt. See module docstring for the
    mandatory gate order -- every gate below runs before `reserve()`, and
    `reserve()` always runs before the upstream call."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'error': {'message': 'لطفاً وارد حساب خود شوید'}}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({'error': {'message': 'درخواست نامعتبر'}}, status_code=400)

    prompt = (body.get('prompt') or '').strip()
    doc_type = (body.get('type') or 'pptx').lower()  # pptx, docx, mdx
    requested_model = (body.get('model') or '').strip()

    if not prompt:
        return JSONResponse({'error': {'message': 'متن درخواست الزامی است'}}, status_code=400)

    if len(prompt) > MAX_PROMPT_LENGTH:
        return JSONResponse(
            {'error': {'message': f'متن درخواست نباید بیشتر از {MAX_PROMPT_LENGTH} کاراکتر باشد'}},
            status_code=413,
        )

    if doc_type not in ('pptx', 'docx', 'mdx'):
        return JSONResponse({'error': {'message': 'نوع فایل نامعتبر. pptx, docx, یا mdx'}}, status_code=400)

    # ── Gate 1: model validation — BEFORE anything else, never forwarded
    # to the upstream unresolved/unverified. ──────────────────────────
    model = await _resolve_and_validate_model(requested_model)
    if model is None:
        return JSONResponse({'error': {'message': _MODEL_NOT_ALLOWED_MESSAGE}}, status_code=400)

    # ── Gate 2: chat_enabled kill switch. ──────────────────────────────
    if not await get_site_flag('chat_enabled'):
        return JSONResponse(
            {'error': {'message': _CHAT_DISABLED_MESSAGE,
                       'type': 'service_unavailable', 'code': 'chat_disabled'}},
            status_code=503,
        )

    # ── Gate 3: content moderation — BEFORE any reservation and BEFORE
    # the free-tier/quota gates. Never leaks the matched rule, model, or
    # provider name. ───────────────────────────────────────────────────
    verdict = await screen_request(uid, [{'role': 'user', 'content': prompt}])
    if verdict.decision == 'block':
        return JSONResponse(
            {'error': {'message': verdict.message_fa or BLOCK_MESSAGE_FA,
                       'type': 'content_policy', 'code': 'content_blocked'}},
            status_code=403,
        )

    # ── Gate 4: free-tier gate (per-model). ────────────────────────────
    ft_gate = await check_and_consume(uid, [model])
    if ft_gate is not None:
        return JSONResponse(
            {'error': {'message': ft_gate.get('message', _FREE_TIER_MESSAGE),
                       'type': 'rate_limited', 'code': ft_gate.get('code', 'free_tier')}},
            status_code=429,
        )

    # ── Gate 5: aggregate package quota gate. ──────────────────────────
    q_gate = await _user_quota_check(uid)
    if q_gate is not None:
        return JSONResponse(
            {'error': {'message': _QUOTA_MESSAGE,
                       'type': 'rate_limited', 'code': 'message_quota_exceeded'}},
            status_code=429,
        )

    # ── Gate 6: premium (expensive-model) sub-allowance. The same gate the
    # four chat routes run at their own post-model point, so generating a
    # document with an expensive model counts against the package's premium
    # sub-allowance rather than escaping it. ──────────────────────────
    p_gate = await _premium_quota_check(uid, [model])
    if p_gate is not None:
        return JSONResponse(
            {'error': {'message': p_gate.get('message', _FREE_TIER_MESSAGE),
                       'type': 'rate_limited', 'code': p_gate.get('code', 'premium_quota_exceeded')}},
            status_code=429,
        )

    # ── Gate 7: reserve. Every gate above has now passed; this is the
    # first point money is even provisionally touched. ────────────────
    import chat as chat_mod
    try:
        is_working = await chat_mod.is_working_model(model)
    except Exception as e:
        logger.warning(f"document_generator: is_working_model failed model={model}: {e}")
        is_working = False
    est_cost = _RESERVE_ESTIMATE_WORKING if is_working else _RESERVE_ESTIMATE_UNKNOWN

    reservation: dict | None = None
    try:
        async with async_session() as bill_session:
            repo = SqlBillingRepo(bill_session)
            svc = BillingService(repo)
            reservation = await svc.reserve(
                uid, Money(est_cost),
                idempotency_key=f"docgen:{secrets.token_hex(8)}",
                model=model,
            )
            await bill_session.commit()
    except InsufficientBalanceError:
        return JSONResponse(
            {'error': {'message': _INSUFFICIENT_BALANCE_MESSAGE,
                       'type': 'quota_exceeded', 'code': 'balance'}},
            status_code=429,
        )
    except Exception as e:
        logger.warning(f"document_generator: reserve failed uid={uid} model={model}: {e}")
        return JSONResponse({'error': {'message': _GATEWAY_ERROR_MESSAGE}}, status_code=502)

    doc_id = uuid.uuid4().hex[:12]
    output_path = DOC_STORAGE / f'{doc_id}{EXT_MAP[doc_type]}'

    # ── Gate 7: the upstream call. generate_content's internal retry
    # (see document_ai.py's module docstring) cannot double-bill: it
    # returns exactly once, and billing below runs exactly once, after
    # this single call returns successfully. `fallback_model` is resolved
    # here, not earlier, so a request rejected by an earlier gate never
    # pays for the extra catalog lookup. ──────────────────────────────
    fallback_model = await _resolve_fallback_model(model)
    try:
        start = time.time()
        data, usage, model_used = await generate_content(
            prompt, doc_type if doc_type != 'mdx' else 'pptx', model, fallback_model,
        )
        gen_time = time.time() - start
    except json.JSONDecodeError as e:
        logger.error(f'JSON parse error: {e}')
        await _release_reservation(reservation, uid, 'json_parse_error')
        return JSONResponse({'error': {'message': 'خطا در تولید محتوا. دوباره تلاش کنید.'}}, status_code=500)
    except Exception as e:
        logger.error(f'Document generation failed: {e}', exc_info=True)
        await _release_reservation(reservation, uid, 'generation_failed')
        return JSONResponse({'error': {'message': 'خطا در تولید سند. لطفاً دوباره تلاش کنید.'}}, status_code=500)

    try:
        if doc_type == 'pptx':
            _create_pptx(data, output_path)
        elif doc_type == 'docx':
            _create_docx(data, output_path)
        else:
            _create_mdx(data, output_path)
        file_size = output_path.stat().st_size
    except Exception as e:
        logger.error(f'Document file build failed: {e}', exc_info=True)
        await _release_reservation(reservation, uid, 'build_failed')
        return JSONResponse({'error': {'message': 'خطا در تولید سند. لطفاً دوباره تلاش کنید.'}}, status_code=500)

    # ── Gate 8: bill the REAL cost directly to wallet.balance. The
    # response was already generated at this point -- a settle failure
    # here is a reconciliation problem to log loudly, not a reason to
    # withhold a response already paid the compute cost for (same
    # reasoning as task_execution.py's step 5 comment). ────────────────
    cost_toman = 0
    try:
        bill_payload = {
            'model': model_used,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': False,
        }
        cost_info = await chat_mod._bill_stream_usage(
            uid, bill_payload, usage, response_text=json.dumps(data, ensure_ascii=False),
        )
        cost_toman = int((cost_info or {}).get('cost') or 0)
    except Exception as e:
        logger.error(
            f"document_generator: billing FAILED after a successful generation "
            f"uid={uid} model={model_used} doc_id={doc_id} "
            f"reservation={reservation.get('reservation_id') if reservation else None}: {e}"
        )

    # ── Gate 9: release the pre-flight hold — always, success or
    # failure. The real charge was already applied directly against
    # wallet.balance above; the hold is released, never settled, once the
    # real charge has landed (same pattern as task_execution.py step 6 /
    # chat.py's own non-streaming handler). ────────────────────────────
    await _release_reservation(reservation, uid, 'after_success')

    # Register document
    _doc_registry[doc_id] = {
        'id': doc_id,
        'user_id': uid,
        'prompt': prompt[:MAX_PROMPT_LENGTH],
        'type': doc_type,
        'model': model_used,
        'title': data.get('title', 'Untitled'),
        'filename': f'{doc_id}{EXT_MAP[doc_type]}',
        'file_size': file_size,
        'generation_time': round(gen_time, 1),
        'slides_count': len(data.get('slides', [])),
        'sections_count': len(data.get('sections', [])),
        'cost_toman': cost_toman,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }

    return JSONResponse({
        'id': doc_id,
        'type': doc_type,
        'title': data.get('title', 'Untitled'),
        'filename': f'{doc_id}{EXT_MAP[doc_type]}',
        'file_size': file_size,
        'generation_time': round(gen_time, 1),
        'slides_count': len(data.get('slides', [])),
        'sections_count': len(data.get('sections', [])),
        'download_url': f'/v1/documents/{doc_id}/download',
    })


@router.get('/v1/documents')
async def list_documents(request: Request) -> JSONResponse:
    """List user's generated documents."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'error': {'message': 'لطفاً وارد حساب خود شوید'}}, status_code=401)

    docs = [d for d in _doc_registry.values() if d['user_id'] == uid]
    docs.sort(key=lambda d: d['created_at'], reverse=True)
    return JSONResponse({'documents': docs})


@router.get('/v1/documents/{doc_id}/download')
async def download_document(doc_id: str, request: Request) -> Response:
    """Download a generated document."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'error': {'message': 'لطفاً وارد حساب خود شوید'}}, status_code=401)

    # Strict doc_id validation (defense-in-depth vs path traversal)
    if not DOC_ID_RE.match(doc_id or ''):
        return JSONResponse({'error': {'message': 'شناسه سند نامعتبر است'}}, status_code=400)

    doc = _doc_registry.get(doc_id)
    if not doc or doc['user_id'] != uid:
        return JSONResponse({'error': {'message': 'سند یافت نشد'}}, status_code=404)

    path = DOC_STORAGE / f'{doc_id}{EXT_MAP[doc["type"]]}'

    # Ensure resolved path stays inside DOC_STORAGE (defense-in-depth)
    if not str(path.resolve()).startswith(str(DOC_STORAGE.resolve()) + os.sep):
        return JSONResponse({'error': {'message': 'سند یافت نشد'}}, status_code=404)

    if not path.exists():
        return JSONResponse({'error': {'message': 'فایل یافت نشد'}}, status_code=404)

    mime_map = {
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'mdx': 'text/markdown',
    }

    # Sanitize download filename
    safe_title = re.sub(r'[^A-Za-z0-9_؀-ۿ\- ]', '', doc['title'])[:80] or 'document'

    return FileResponse(
        path=str(path),
        media_type=mime_map.get(doc['type'], 'application/octet-stream'),
        filename=f'{safe_title}{EXT_MAP[doc["type"]]}',
    )


@router.delete('/v1/documents/{doc_id}')
async def delete_document(doc_id: str, request: Request) -> JSONResponse:
    """Delete a generated document."""
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'error': {'message': 'لطفاً وارد حساب خود شوید'}}, status_code=401)

    if not DOC_ID_RE.match(doc_id or ''):
        return JSONResponse({'error': {'message': 'شناسه سند نامعتبر است'}}, status_code=400)

    doc = _doc_registry.get(doc_id)
    if not doc or doc['user_id'] != uid:
        return JSONResponse({'error': {'message': 'سند یافت نشد'}}, status_code=404)

    path = DOC_STORAGE / f'{doc_id}{EXT_MAP[doc["type"]]}'
    path.unlink(missing_ok=True)
    del _doc_registry[doc_id]

    return JSONResponse({'status': 'deleted'})
