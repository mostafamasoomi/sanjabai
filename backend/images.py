"""POST /v1/images/generations -- OpenAI-compatible image generation.

Why this is a separate router instead of a branch inside chat.py: both
upstreams (omniroute, 9router) hard-reject an image model on
/v1/chat/completions --

    400 -> "Model '...' is an image-generation model and cannot be used on
            /v1/chat/completions. Use POST /v1/images/generations instead."

-- and expose their own POST /v1/images/generations instead, with the
confirmed request shape ``{"model": "<provider>/<model>", "prompt": "...",
"n": 1}``. ``model`` must already be ``provider/model``; omniroute rejects
anything else with "Invalid image model ... Use format: provider/model".

FINANCIAL RULE (see module docstring of chat.py's _resolve_public_model for
the full incident writeup): the incoming ``model`` string must be
canonicalized to ``model_catalog.provider_model_id`` via
``chat._resolve_public_model`` exactly ONCE, at the very start of the
handler -- before the availability gate, the price gate, and the wallet
reservation -- because everything downstream (the upstream call AND the
billing price lookup) is keyed on that canonical id. An unresolved
``sanjab/*`` string would both fail upstream and miss the price lookup.

NO SUCCESSFUL GENERATION HAS EVER BEEN OBSERVED (2026-08-22): every image
provider either upstream registers is uncredentialed or out of credit (see
scripts/probe_media.py). The response parser below therefore handles BOTH
documented OpenAI shapes defensively --

    {"created": <int>, "data": [{"url": "https://..."}]}
    {"created": <int>, "data": [{"b64_json": "...."}]}

-- and treats a missing/empty ``data`` as a failure that bills nothing,
rather than assuming either shape is the one that will actually show up.

VIDEO IS EXPLICITLY OUT OF SCOPE. The owner deferred it ("به یک نقطه استیبل
رسیدیم برمی‌گردیم سروقت تولید ویدئو") and no upstream has a credentialed
video route today. Nothing here handles /v1/videos/*.
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Any

import httpx
import sqlalchemy
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import async_session, _http
from dependencies import _get_user_id
from chat import _resolve_public_model, _resolve_provider, _release_reservation
from content import apply_markup, get_effective_markup_pct
from services.billing import SqlBillingRepo, BillingService, InsufficientBalanceError
from services.money import Money
from site_settings import get_site_flag

logger = logging.getLogger(__name__)

router = APIRouter()


class ImageGenerationRequest(BaseModel):
    model: str = ''
    prompt: str = ''
    n: int | None = 1
    size: str | None = None


# A real image generation took 103 seconds on the one route that reached a
# provider (omniroute -> antigravity, before it 403'd). Nothing below 15s is
# safe per this codebase's operational rule; 300s leaves real headroom over
# the single observed data point instead of cutting it close.
IMAGE_READ_TIMEOUT_SECONDS = 300
IMAGE_UPSTREAM_TIMEOUT = httpx.Timeout(
    IMAGE_READ_TIMEOUT_SECONDS, connect=15, read=IMAGE_READ_TIMEOUT_SECONDS,
)

# Sane per-request cap so a single request cannot open an unbounded
# reservation or an unbounded number of upstream-billed units. Not derived
# from any observed upstream limit (none has ever answered) -- just a
# product-level guard.
MAX_N_IMAGES = 4

_IMAGE_MODEL_SQL = sqlalchemy.text(
    "SELECT provider_model_id, availability, image_price_per_unit, markup_pct "
    "FROM model_catalog WHERE provider_model_id = :mid LIMIT 1"
)


async def _load_image_model(provider_model_id: str):
    """Fetch the one row this endpoint needs, keyed on the CANONICAL id
    (provider_model_id) -- the same key chat.py's price lookup uses, and for
    the same reason: an unresolved public_id would miss here too."""
    if async_session is None:
        return None
    try:
        async with async_session() as session:
            res = await session.execute(_IMAGE_MODEL_SQL, {'mid': provider_model_id})
            return res.fetchone()
    except Exception as e:
        logger.warning(f"images: model_catalog lookup failed model={provider_model_id}: {e}")
        return None


def _extract_images(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only the entries that actually carry an image (``url`` or
    ``b64_json``), from either documented OpenAI images response shape.

    Anything else -- a missing ``data`` key, a non-list ``data``, an entry
    with neither field (e.g. a bare job-id/polling shape this endpoint does
    not support) -- is dropped rather than crashing, and an empty result
    here is what makes the caller treat the whole request as a failure that
    bills nothing.
    """
    if not isinstance(data, dict):
        return []
    items = data.get('data')
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if isinstance(item, dict) and (item.get('url') or item.get('b64_json')):
            out.append(item)
    return out


def _error(message: str, *, code: str, status: int, err_type: str = 'invalid_request') -> JSONResponse:
    return JSONResponse(
        {'error': {'message': message, 'type': err_type, 'code': code}},
        status_code=status,
    )


@router.post('/v1/images/generations')
async def images_generations(request: Request, payload: ImageGenerationRequest) -> Response:
    uid = await _get_user_id(request)
    if not uid:
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if not await get_site_flag('image_generation_enabled'):
        return _error(
            'تولید تصویر موقتاً در دسترس نیست', code='image_generation_disabled',
            status=503, err_type='service_unavailable',
        )

    model_in = (payload.model or '').strip()
    if not model_in:
        return _error('مدل مشخص نشده است', code='model_required', status=400)

    # Gate 0 (financial rule): canonicalize BEFORE every other gate and
    # before the reservation -- see module docstring.
    resolved_model = await _resolve_public_model(model_in)

    n_requested = payload.n or 1
    if n_requested < 1:
        n_requested = 1
    n_requested = min(n_requested, MAX_N_IMAGES)

    row = await _load_image_model(resolved_model)

    # Gate 1: availability. Every image model is 'maintenance' today (no
    # upstream credential works yet -- see scripts/probe_media.py), so in
    # practice this refuses every request until the owner adds a key. That
    # is correct and intended, not a bug to work around.
    if row is None or row.availability != 'available':
        return _error(
            f'مدل {resolved_model} برای تولید تصویر در دسترس نیست',
            code='model_not_available', status=400,
        )

    # Gate 2: price. NULL means "no price, cannot be served" -- a hard
    # refusal, never a guessed/fallback rate. Unlike chat.py's L2 ceiling
    # fallback (which exists to avoid under-billing tokens that were
    # ALREADY served), an image request that has not been sent yet must
    # simply be refused so no request can ever be loss-making.
    if row.image_price_per_unit is None:
        return _error(
            f'قیمتی برای مدل {resolved_model} ثبت نشده است؛ این مدل قابل ارائه نیست',
            code='price_not_set', status=400,
        )

    effective_pct = await get_effective_markup_pct(getattr(row, 'markup_pct', None))
    # apply_markup is content.py's single source of truth for turning a base
    # price into a served number -- the same function the catalog/pricing
    # endpoints use, so the shown price (once a catalog UI exists for media)
    # and the billed price can never disagree. Reused verbatim, not
    # reimplemented, even though its docstring talks about per-million rates
    # -- the arithmetic (base * (1 + pct/100), rounded) is identical for a
    # flat per-image base price.
    price_per_image = apply_markup(row.image_price_per_unit, effective_pct)
    if price_per_image <= 0:
        return _error(
            f'قیمت مدل {resolved_model} نامعتبر است', code='price_not_set', status=400,
        )

    reserve_amount = price_per_image * n_requested

    reservation = None
    try:
        async with async_session() as _bill_session:
            _repo = SqlBillingRepo(_bill_session)
            _bill_svc = BillingService(_repo)
            reservation = await _bill_svc.reserve(
                uid, Money(reserve_amount),
                idempotency_key=f"img:{secrets.token_hex(8)}",
                model=resolved_model,
            )
            await _bill_session.commit()
    except InsufficientBalanceError:
        return JSONResponse(
            {'error': {
                'message': 'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.',
                'type': 'quota_exceeded', 'code': 'balance',
            }},
            status_code=429,
        )
    except Exception as e:
        logger.warning(f"images.generations reserve failed uid={uid} model={resolved_model}: {e}")
        return JSONResponse({'detail': 'سرویس موقتاً در دسترس نیست', 'code': 'gateway_error'}, status_code=502)

    upstream_payload: dict[str, Any] = {'model': resolved_model, 'prompt': payload.prompt, 'n': n_requested}
    if payload.size:
        upstream_payload['size'] = payload.size

    try:
        provider = await _resolve_provider(resolved_model)
        r = await _http.post(
            f'{provider.v1}/images/generations',
            json=upstream_payload,
            headers={**provider.headers(), 'Accept': 'application/json'},
            timeout=IMAGE_UPSTREAM_TIMEOUT,
        )
    except Exception as e:
        logger.warning(f"images.generations upstream error uid={uid} model={resolved_model}: {e}")
        await _release_reservation(reservation, uid, 'on_error')
        return JSONResponse({'detail': 'سرویس موقتاً در دسترس نیست', 'code': 'gateway_error'}, status_code=502)

    if r.status_code != 200:
        # Covers the observed failure modes directly (401 dead key, 402 no
        # credits, 403 unverified account) as well as anything else the
        # upstream returns -- never bill, always release the hold.
        await _release_reservation(reservation, uid, 'upstream_error')
        return Response(content=r.content, status_code=r.status_code, media_type='application/json')

    try:
        resp_data = r.json()
    except Exception as e:
        logger.warning(f"images.generations: unparseable upstream body uid={uid} model={resolved_model}: {e}")
        resp_data = {}

    images = _extract_images(resp_data)
    n_returned = len(images)

    if n_returned == 0:
        logger.warning(
            f"images.generations: upstream HTTP 200 but no usable image data "
            f"uid={uid} model={resolved_model} n_requested={n_requested} -- billing nothing"
        )
        await _release_reservation(reservation, uid, 'empty_result')
        return _error(
            'تولید تصویر ناموفق بود؛ هیچ تصویری از سرویس دریافت نشد',
            code='no_images', status=502, err_type='upstream_error',
        )

    # Bill for exactly what came back. Clamped to n_requested defensively --
    # the upstream is not trusted to honor the requested `n` -- so a
    # (never-observed, but not impossible) over-return can never charge more
    # than the reservation's hold, which would raise inside settle().
    billable_n = min(n_returned, n_requested)
    charge_amount = price_per_image * billable_n

    try:
        async with async_session() as _settle_session:
            _repo = SqlBillingRepo(_settle_session)
            _bill_svc = BillingService(_repo)
            await _bill_svc.settle(reservation['reservation_id'], Money(charge_amount))
            await _settle_session.commit()
    except Exception as e:
        # The images were already generated and are about to be returned to
        # the user -- a settle failure here is a reconciliation problem, not
        # a reason to withhold a response that was already paid for (the
        # reservation still holds the funds until whatever cleans up stale
        # reservations runs). Logged loudly so it's never silently invisible.
        logger.error(
            f"images.generations: settle FAILED after successful generation "
            f"uid={uid} model={resolved_model} reservation={reservation.get('reservation_id')} "
            f"charge={charge_amount}: {e}"
        )

    resp_data['billing'] = {
        'cost': charge_amount,
        'images': n_returned,
        'currency': 'IRT',
    }
    return Response(content=json.dumps(resp_data), status_code=200, media_type='application/json')
