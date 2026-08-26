"""Admin surface for the upstream prompt-overhead discount
(services/upstream_overhead.py, migration 0041, chat_billing.py's discount
block).

Two routes:

  * ``GET /admin/upstream-overhead`` -- the currently stored map plus, for
    context, a 7-day per-provider count of discounted requests and total
    tokens discounted, read straight from ``usage_events``.
  * ``POST /admin/upstream-overhead/measure`` -- re-measures LIVE and
    overwrites the stored map.

── Why a two-point measurement, not "raw prompt_tokens minus a clean
baseline" ─────────────────────────────────────────────────────────────
The first cut of this feature assumed litellm was a uniformly clean
baseline and computed overhead as ``prompt_tokens - 14`` (14 being
litellm's reading for a 2-token control message). That was wrong and was
withdrawn before ever being seeded (see migration 0041's header): a
same-day follow-up measurement found the SAME model (mimo-v2.5-free)
reporting 248 prompt_tokens through litellm and 433 through ninerouter for
the identical short message -- litellm is not preamble-free, it simply has
a smaller, MODEL-specific baseline cost that has nothing to do with any
router. Subtracting a single global "clean" number would have folded that
model's own real cost into "9router overhead" and discounted it away,
undercharging the user below what the request genuinely cost.

The fix is to measure the INTERCEPT per (provider, prefix) using two points
on the exact same model/route, never comparing across routes or models:

    P1 = a short, fixed control message (a couple of tokens)
    P2 = a long, fixed, deterministic message (the same short Persian
         sentence repeated a fixed number of times)

Read real prompt_tokens p1/p2 from the upstream for both. Let c1/c2 be OUR
OWN local estimates of those two message bodies
(chat_billing._estimate_input_tokens -- the exact same estimator the
billing floor uses, so the two are measuring on a consistent yardstick).
Then

    slope    = (p2 - p1) / (c2 - c1)   # how the upstream counts our text
    overhead = round(p1 - slope * c1)  # tokens present at zero user content

is the number of tokens present when the user wrote nothing -- whoever
injected them, model or router -- clamped to ``max(0, overhead)``. The
slope term cancels out any constant disagreement between our tokenizer
heuristic and the upstream's real one, which a one-point measurement would
silently fold into "overhead" too. A non-finite or negative slope, or
``c2 == c1`` (should not happen with the fixed prompts below, but is
guarded regardless), records overhead 0 for that entry -- 0 is always the
safe direction, since it means "apply no discount, charge in full".

── 9router replies as SSE even for a non-streaming request ────────────
Confirmed live by the coordinator, 2026-08-23: 9router's response
Content-Type is ``text/event-stream`` and its body is ``data: {...}``
lines EVEN WHEN the request did not ask for ``stream``. ``_parse_prompt_tokens``
below therefore never assumes a single JSON body -- it scans for SSE
``data:`` lines first (taking the LAST chunk that carries a non-empty
``usage`` block, matching chat_stream.py's own streaming parser) and only
falls back to parsing the whole body as one JSON object when no such line
is found (litellm's shape).

── Auth ─────────────────────────────────────────────────────────────────
Every handler below calls ``admin_required`` as its very first real
action. tests/test_admin_routes_require_auth.py walks the AST of every
backend module and fails any ``/admin`` handler that does not -- not
optional, and the POST route here fires real (tiny, max_tokens=3) upstream
calls, so leaving it open would let an anonymous caller spend upstream
money in a loop, exactly the class of incident that test file exists to
prevent.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from database import _http, async_session
from dependencies import admin_required
from i18n import err
from providers import get_provider

logger = logging.getLogger(__name__)

router = APIRouter()

_SETTING_KEY = 'upstream_prompt_overhead'

# Never below ~15s -- 9router has been measured taking up to ~11s to
# respond. connect=10 gives the TCP handshake its own budget; read=25
# leaves headroom above the observed worst case.
_PROBE_TIMEOUT = httpx.Timeout(25.0, connect=10.0, read=25.0)

# Fixed, deterministic control messages -- reproducible across runs so a
# re-measurement is comparable to the last one. The long prompt is the
# short sentence below repeated a fixed number of times, never generated
# from anything request-specific.
_SHORT_PROMPT = 'سلام'
_LONG_SENTENCE = (
    'این یک جمله ثابت فارسی است که برای اندازه‌گیری دقیق سربار پرامپت بارها تکرار می‌شود. '
)
_LONG_REPEAT_COUNT = 40
_LONG_PROMPT = _LONG_SENTENCE * _LONG_REPEAT_COUNT


def _prefix(provider_model_id: str) -> str:
    return (provider_model_id or '').split('/', 1)[0]


def _parse_prompt_tokens(body_text: str) -> int | None:
    """Extract `usage.prompt_tokens` from a chat/completions response body
    that may be a single JSON object (litellm) or SSE `data: {...}` lines
    (9router, even for a non-streamed request -- see module docstring).

    Returns None if no usable usage block was found anywhere in the body.
    """
    text = (body_text or '').strip()
    if not text:
        return None

    last_usage: dict[str, Any] | None = None
    saw_sse_data_line = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith('data:'):
            continue
        saw_sse_data_line = True
        data_str = line[len('data:'):].strip()
        if data_str == '[DONE]':
            continue
        try:
            chunk = json.loads(data_str)
        except (json.JSONDecodeError, ValueError):
            continue
        usage = chunk.get('usage') if isinstance(chunk, dict) else None
        if isinstance(usage, dict) and usage:
            last_usage = usage

    if not saw_sse_data_line:
        try:
            body = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None
        usage = body.get('usage') if isinstance(body, dict) else None
        if isinstance(usage, dict) and usage:
            last_usage = usage

    if not last_usage:
        return None
    try:
        return int(last_usage.get('prompt_tokens'))
    except (TypeError, ValueError):
        return None


async def _probe_prompt_tokens(provider, model_id: str, content: str) -> int | None:
    """One live chat/completions call; returns real prompt_tokens or None
    on any failure (bad status, timeout, unparseable body). Never raises."""
    payload = {
        'model': model_id,
        'messages': [{'role': 'user', 'content': content}],
        'max_tokens': 3,
        'temperature': 0,
        'stream': False,
    }
    try:
        r = await _http.post(
            f'{provider.v1}/chat/completions',
            json=payload,
            headers={**provider.headers(), 'Accept': 'application/json'},
            timeout=_PROBE_TIMEOUT,
        )
    except Exception as e:
        logger.warning('upstream-overhead probe request failed model=%s: %s', model_id, e)
        return None
    if r.status_code >= 400:
        logger.warning('upstream-overhead probe http_%s model=%s', r.status_code, model_id)
        return None
    return _parse_prompt_tokens(r.text)


async def _representative_models() -> list[tuple[str, str]]:
    """One (upstream, provider_model_id) pair per currently-available
    (upstream, prefix) combination in model_catalog. `upstream` is the
    providers.Provider.name this model routes through (litellm/ninerouter/
    ...); the prefix is the first path segment of provider_model_id, the
    same key component services/upstream_overhead.py looks entries up by.
    """
    if async_session is None:
        return []
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            """
            SELECT DISTINCT ON (upstream, split_part(provider_model_id, '/', 1))
                   upstream, provider_model_id
              FROM model_catalog
             WHERE availability = 'available'
               AND upstream IS NOT NULL AND upstream <> ''
             ORDER BY upstream, split_part(provider_model_id, '/', 1), provider_model_id
            """
        ))
        return [(row.upstream, row.provider_model_id) for row in res.fetchall()]


@router.post('/admin/upstream-overhead/measure')
async def measure_upstream_overhead(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'The database is unavailable.', 500)

    from chat_billing import _estimate_input_tokens

    c1 = _estimate_input_tokens([{'role': 'user', 'content': _SHORT_PROMPT}])
    c2 = _estimate_input_tokens([{'role': 'user', 'content': _LONG_PROMPT}])

    try:
        candidates = await _representative_models()
    except Exception as e:
        logger.warning('upstream-overhead measure: candidate lookup failed: %s', e)
        return err(
            'خطا در خواندن فهرست مدل‌ها از پایگاه داده',
            'Failed to read the model list from the database.', 500,
        )

    entries: dict[str, int] = {}
    measurements: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, str]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for upstream, model_id in candidates:
        provider = get_provider(upstream)
        if provider is None:
            skipped.append({'upstream': upstream, 'model': model_id, 'reason': 'provider_not_configured'})
            continue

        p1 = await _probe_prompt_tokens(provider, model_id, _SHORT_PROMPT)
        p2 = await _probe_prompt_tokens(provider, model_id, _LONG_PROMPT)
        if p1 is None or p2 is None:
            skipped.append({'upstream': upstream, 'model': model_id, 'reason': 'probe_failed'})
            continue

        key = f'{upstream}:{_prefix(model_id)}'
        if c2 == c1:
            # Cannot happen with the fixed prompts above, but the whole
            # point of measuring live is that "cannot happen" is not a
            # promise -- guard it exactly as specified rather than divide
            # by zero. 0 = no discount = the safe direction.
            logger.warning('upstream-overhead measure: c1 == c2 for %s, recording overhead 0', key)
            slope = None
            overhead = 0
        else:
            slope = (p2 - p1) / (c2 - c1)
            if not (slope == slope) or slope in (float('inf'), float('-inf')) or slope < 0:
                # slope != slope catches NaN without importing math.
                logger.warning(
                    'upstream-overhead measure: non-finite/negative slope=%s for %s '
                    '(p1=%s p2=%s c1=%s c2=%s), recording overhead 0',
                    slope, key, p1, p2, c1, c2,
                )
                overhead = 0
            else:
                overhead = max(0, round(p1 - slope * c1))

        entries[key] = overhead
        measurements[key] = {
            'overhead': overhead, 'p1': p1, 'p2': p2, 'c1': c1, 'c2': c2,
            'slope': slope, 'sample_model': model_id, 'measured_at': now_iso,
        }
        logger.info(
            'upstream-overhead measured %s sample_model=%s p1=%s p2=%s c1=%s c2=%s -> overhead=%s',
            key, model_id, p1, p2, c1, c2, overhead,
        )

    # provider_default[upstream] = the SMALLEST overhead measured for that
    # upstream this run -- so a prefix that was not (or could not be)
    # measured this round is never assumed to carry MORE overhead than any
    # prefix we actually proved, which is the direction that risks
    # undercharging. A provider with zero successful measurements this run
    # gets no provider_default entry at all (falls through to 0 at lookup
    # time via get_prompt_overhead, i.e. no discount).
    provider_default: dict[str, int] = {}
    for key, overhead in entries.items():
        upstream = key.split(':', 1)[0]
        if upstream not in provider_default or overhead < provider_default[upstream]:
            provider_default[upstream] = overhead

    new_value = {
        'version': 1,
        'measured_at': now_iso,
        'entries': entries,
        'provider_default': provider_default,
        'measurements': measurements,
    }

    try:
        async with async_session() as session:
            await session.execute(
                sqlalchemy.text(
                    "INSERT INTO app_setting (key, value, updated_at) "
                    "VALUES (:k, :v, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now()"
                ),
                {'k': _SETTING_KEY, 'v': json.dumps(new_value)},
            )
            await session.commit()
    except Exception as e:
        logger.warning('upstream-overhead measure: write failed: %s', e)
        return err(
            'خطا در ذخیره‌سازی نتیجه اندازه‌گیری',
            'Failed to save the measurement result.', 500,
        )

    try:
        from services.upstream_overhead import invalidate_cache
        await invalidate_cache()
    except Exception as e:
        logger.warning('upstream-overhead measure: cache invalidation failed: %s', e)

    return JSONResponse({
        'status': 'ok',
        'measured': len(entries),
        'skipped': skipped,
        'value': new_value,
    })


@router.get('/admin/upstream-overhead')
async def get_upstream_overhead(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'The database is unavailable.', 500)

    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text('SELECT value, updated_at FROM app_setting WHERE key = :k'),
                {'k': _SETTING_KEY},
            )
            row = res.fetchone()
    except Exception as e:
        logger.warning('GET /admin/upstream-overhead: DB read failed: %s', e)
        return err(
            'خطا در خواندن تنظیمات از پایگاه داده',
            'Failed to read settings from the database.', 500,
        )

    stored = row.value if row is not None else {'version': 1, 'measured_at': None, 'entries': {}, 'provider_default': {}}
    updated_at = row.updated_at.isoformat() if row is not None and row.updated_at else None

    stats: list[dict[str, Any]] = []
    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                """
                SELECT provider,
                       COUNT(*) AS requests,
                       COALESCE(SUM((meta->>'prompt_overhead_discounted')::bigint), 0) AS total_discounted
                  FROM usage_events
                 WHERE created_at > now() - interval '7 days'
                   AND meta ? 'prompt_overhead_discounted'
                 GROUP BY provider
                 ORDER BY provider
                """
            ))
            # int() on both columns is load-bearing, not cosmetic. Postgres
            # widens SUM(bigint) to numeric, which asyncpg hands back as a
            # decimal.Decimal, and JSONResponse's json.dumps has no encoder
            # for Decimal -- so the moment any usage_event carried a
            # prompt_overhead_discounted value this endpoint answered 500.
            # The try/except above only covers the query, not the response
            # construction below, so the TypeError escaped as a bare 500.
            stats = [
                {
                    'provider': r.provider,
                    'requests7d': int(r.requests or 0),
                    'totalTokensDiscounted7d': int(r.total_discounted or 0),
                }
                for r in res.fetchall()
            ]
    except Exception as e:
        logger.warning('GET /admin/upstream-overhead: usage_events read failed: %s', e)
        stats = []

    return JSONResponse({
        'stored': stored,
        'storedUpdatedAt': updated_at,
        'perProviderStats7d': stats,
    })
