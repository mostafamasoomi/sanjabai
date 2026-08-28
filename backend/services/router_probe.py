"""The acceptance probe for "being the router" -- a second role a model can
hold besides "being sellable to a user".

``services/probe_gate.py`` enforces the house rule "a model is offered only
after a successful live probe" for *selling a model*
(``admin_catalog.bulk_set_availability``, ``admin_pricing.toggle_model``).
That is a different question from "is this model any good AT ROUTING", and
today ``services/smart_router_llm._router_model`` answers it with "whatever
is cheapest in the pool" -- which measurement on 2026-08-28 proved is
`ag/gpt-oss-120b-medium`, a model that dumps its whole token budget into
`reasoning_content` and returns `content=''`, and 7 of the pool's 11
cheapest members turned out to be similarly unable to answer a bare menu
number at all. "Cheapest pool member" is not fail-open, it is fail-RANDOM.

── THE DESIGN PROPERTY THAT MUST SURVIVE ───────────────────────────────────
If this probe is itself broken and rejects everything, every model's stored
`ok` is false (or missing), `_router_model` returns None for all of them,
`llm_route` returns None, and Smart Mode falls back to the rule-based path
(services/smart_router.select_by_rules). THE WORST FAILURE MODE OF THIS
PROBE IS THE STATUS QUO -- the same behaviour as if the LLM router feature
did not exist at all. There is no failure mode of this module that is worse
than not having it.

── TWO STAGES, NOT ONE ──────────────────────────────────────────────────────
Stage 1, SHAPE (necessary): one call with a synthetic 8-item numbered menu
and one fixed message; the reply must survive `smart_router_llm._parse_choice`
(a bare in-range integer, nothing else). Run once per model.

Stage 2, DISCRIMINATION (sufficient, and the part 2026-08-26's fix did not
have): three fixed reference messages (greeting / code / reasoning) against
a menu whose bands are known to US (derived from `services.smart_router
.band_of`, never from the model's own judgement). Pass iff
`band(answer(greeting)) == 1` AND `band(answer(reasoning)) >= 2`.

That bar is deliberately loose: we are not asking the router to say "8", we
are asking it not to say "5" for "hello". Live measurement on 2026-08-28
found this bar produces a clean, model-independent split: three different
router-model candidates, on two different upstream providers, all answered
band 1 for the greeting and code/reasoning strictly above it once the menu
carried band labels -- and all three were noise (no pattern at all,
`greeting` landing in the MIDDLE band) on the bare, unlabelled menu
production sent that day. Both stages here render their menu through
`services.router_prompt.build_prompt` -- the SAME function
`smart_router_llm.llm_route` calls for the real chat path, so this probe can
never again certify a prompt production does not actually send (that gap is
exactly what made the 2026-08-28 measurement necessary in the first place;
see build_prompt's module docstring for the full story and
`tests/test_router_prompt.py` for the test that pins the two paths identical).

The band labels are OUR fixed text, derived from `band_of()` over the real
candidate pool -- never from the user's message. The security boundary is
unchanged from `smart_router_llm.py`: the only accepted reply is a bare
in-range menu integer, checked with the same `_parse_choice` `fullmatch`
regex that already defeats prompt injection there.

── THREE OUTCOMES, THREE DIFFERENT FATES -- do not collapse them ───────────
  * wrong shape / no discrimination (a well-formed 200 whose CONTENT fails
    stage 1 or stage 2) -- a PERMANENT defect. `ok=false`, the row is
    overwritten, and the model is out of the router candidate list until
    the next measurement proves otherwise.
  * any HTTP-level failure -- non-200 status (429, 5xx, and also other 4xx:
    the 2026-08-28 measurement recorded a bare 403 from `omniroute` in the
    same run and same breath as a 429 from `gemini-2.5-flash-lite`, both
    cited as the SAME class of transient router flakiness, not a verdict on
    the model) -- OR a timeout, OR a transport exception. TRANSIENT.
    `ok=false, reason='transient_*'`, `retry_after` = now + 6h, and if the
    STORED entry already had `ok=true` from a previous successful
    measurement, that entry is preserved untouched apart from the
    transient stamp -- an accidental 429 must never permanently evict a
    model that has already proven itself.
  * the model is no longer present in `candidate_pool()` at all (withdrawn,
    unpriced, quarantined, whatever) -- it left the catalog. Its row is
    removed from the stored map outright, whether or not it was rescanned
    this run.

`httpx.TimeoutException` does NOT subclass the builtin `TimeoutError` --
both are checked explicitly below (see smart_router_llm.py's identical note
for the live `ReadTimeout.__mro__` trace this is pinned against).

── SCAN SCOPE AND COST ──────────────────────────────────────────────────────
Only the `SCAN_LIMIT` (12) cheapest pool members, from
`services.smart_router.candidate_pool()` -- its existing 60s cache is
reused, this module adds no new query on that hot path. A router more
expensive than that is pointless to measure. Each scanned model costs at
most 4 live calls (1 shape + 3 discrimination) at `_MAX_TOKENS` tokens each,
imported from `smart_router_llm` so the two modules can never quietly drift
apart on call shape.

Minimum probe timeout: 15 seconds. One upstream router (ninerouter/9router)
regularly takes up to ~11s to answer; anything tighter reports a healthy
dependency as dead. `_PROBE_TIMEOUT` below gives it a comfortable margin,
mirroring `admin_overhead.py`'s identical timeout for the identical reason.

── PERSISTENCE -- NO MIGRATION ──────────────────────────────────────────────
One `app_setting` row, key `SETTING_KEY` ("smart_router_probe"). Mirrors
`admin_overhead.py`'s `upstream_prompt_overhead` idiom exactly: JSONB value,
plain `INSERT ... ON CONFLICT (key) DO UPDATE`, no new table, and -- unlike
`upstream_prompt_overhead` -- no seeding migration at all. The row simply
does not exist until an admin runs `POST /admin/smart-router/probe`
(admin_smart_router.py); reading a missing row degrades to "never
measured", which is `not_probed` for every model, which is the same
status-quo-safe fallback as everything else in this module.

── NEVER ON THE CHAT PATH -- the red line of this module ───────────────────
`run_probe_scan()` (this module's only entry point that makes live calls)
is imported and awaited from exactly one place in this codebase:
`admin_smart_router.py`'s POST handler, run by an admin on demand. Nothing
in `smart_router_llm.llm_route` (the hot chat path) references
`run_probe_scan` -- it only reads the STORED result, via `router_eligibility`
below, inside `_router_model`, and does so with a deferred (function-local)
import specifically so this module never has to be imported at chat-request
time just to answer "is X a router". `tests/test_router_probe.py` pins this
with an AST/source-text check, not a comment nobody enforces.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import sqlalchemy

from database import _http, async_session
from providers import get_provider
from services.router_prompt import build_prompt
from services.smart_router import Candidate, band_of, band_thresholds, candidate_pool
from services.smart_router_llm import _MAX_TOKENS, _SYSTEM_PROMPT, _TEMPERATURE, _menu, _parse_choice

logger = logging.getLogger('chat')  # same logger name as the rest of the smart-mode path

SETTING_KEY = 'smart_router_probe'

# Never below ~15s -- see module docstring. connect=10 gives the TCP
# handshake its own budget; read=25 leaves headroom above the observed
# worst case, same numbers as admin_overhead.py's identical timeout.
_PROBE_TIMEOUT = httpx.Timeout(25.0, connect=10.0, read=25.0)

# Only the 12 cheapest pool members are ever measured -- see module docstring.
SCAN_LIMIT = 12

# A synthetic (non-catalog) menu used ONLY for the shape check -- it must
# not name any real model, so a shape pass can never be misread as "this
# candidate model routes to itself".
_SHAPE_MENU_SIZE = 8

# A stored ok=true result older than this is still ACCEPTED (never
# re-probed from the chat path -- see module docstring's red line), just
# logged loudly so staleness is visible without ever blocking the feature.
STALE_AFTER = timedelta(days=7)

# How long a transient failure keeps a model out before the NEXT scheduled
# scan should reconsider it. Purely informational today (scans are
# admin-triggered, not on a timer) -- recorded so a future scheduler has a
# number to read instead of inventing one.
RETRY_AFTER_TRANSIENT = timedelta(hours=6)

# Fixed, deterministic reference messages -- OUR text, reproducible across
# runs. Order is greeting, code, reasoning; iteration order is preserved
# (Python dicts, 3.7+) and the module never reorders it, so `samples` in the
# stored result always reflects the same call order.
_REFERENCE_MESSAGES = {
    'greeting': 'سلام، خوبی؟',
    'code': 'یک تابع پایتون بنویس که بررسی کند یک عدد اول است یا نه.',
    'reasoning': (
        'قطار الف با سرعت ۶۰ کیلومتر بر ساعت از تهران و قطار ب با سرعت ۸۰ '
        'کیلومتر بر ساعت از اصفهان، هم‌زمان به سمت هم حرکت می‌کنند. فاصله '
        'دو شهر ۴۲۰ کیلومتر است. چند ساعت بعد به هم می‌رسند؟ مرحله به '
        'مرحله استدلال کن.'
    ),
}

_PROBE_SETTING_SQL = sqlalchemy.text('SELECT value FROM app_setting WHERE key = :key')


def _empty_stored() -> dict[str, Any]:
    return {'version': 1, 'measured_at': None, 'results': {}}


async def _load_stored(session) -> dict[str, Any]:
    """Read the stored probe map through an ALREADY-OPEN session -- lets
    `_router_model` reuse its own session instead of opening a second one
    per chat-adjacent read. Never raises; a bad/foreign shape in `value`
    degrades to "never measured", same as a missing row."""
    res = await session.execute(_PROBE_SETTING_SQL, {'key': SETTING_KEY})
    row = res.fetchone()
    if row is None or not row.value or not isinstance(row.value, dict):
        return _empty_stored()
    return row.value


async def _read_stored() -> dict[str, Any]:
    """Same as `_load_stored`, but opens (and closes) its own session --
    used by `run_probe_scan`, which is not already inside one."""
    if async_session is None:
        return _empty_stored()
    try:
        async with async_session() as session:
            return await _load_stored(session)
    except Exception as e:
        logger.warning(f'{SETTING_KEY} read failed, treating as never measured: {e}')
        return _empty_stored()


async def _persist(value: dict[str, Any]) -> None:
    if async_session is None:
        return
    import json
    async with async_session() as session:
        await session.execute(
            sqlalchemy.text(
                "INSERT INTO app_setting (key, value, updated_at) "
                "VALUES (:k, :v, now()) "
                "ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now()"
            ),
            {'k': SETTING_KEY, 'v': json.dumps(value)},
        )
        await session.commit()


def _is_stale(measured_at: str | None) -> bool:
    """True when `measured_at` is missing, unparsable, or older than
    STALE_AFTER. Unparsable/missing counts as stale (not an error) -- the
    caller's response to "stale" is to accept-and-warn, never to refuse, so
    treating an unreadable timestamp as "definitely old" is the safe
    direction here, unlike everywhere else in this module where the safe
    direction is to refuse."""
    if not measured_at:
        return True
    try:
        dt = datetime.fromisoformat(measured_at)
    except ValueError:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - dt > STALE_AFTER


async def router_eligibility(session, model_key: str) -> tuple[bool, str]:
    """(ok, reason) for one model, read through an ALREADY-OPEN session.

    `model_key` is a Candidate.public_id -- the same key `run_probe_scan`
    stores results under.

    reason is one of:
      'ok'          -- ok=true, measurement fresh (<= 7 days)
      'stale'       -- ok=true, measurement older than 7 days (still
                       eligible -- the caller logs a warning, does not
                       refuse; see STALE_AFTER)
      'not_probed'  -- no stored result for this model at all (never
                       measured, or the app_setting row itself is missing)
      <a stored 'reason' string> -- e.g. 'bad_shape', 'no_discrimination',
                       or a transient_* label left over from the most
                       recent measurement attempt on a model that has never
                       had a successful one

    Never raises: any read failure inside `_load_stored` already degrades
    to "never measured" (`not_probed`), which is the fail-closed answer.
    """
    stored = await _load_stored(session)
    results = stored.get('results') or {}
    entry = results.get(model_key)
    if not entry:
        return False, 'not_probed'
    if not entry.get('ok'):
        return False, entry.get('reason') or 'not_ok'
    if _is_stale(stored.get('measured_at')):
        return True, 'stale'
    return True, 'ok'


def _synthetic_shape_menu() -> list[Candidate]:
    """8 placeholder entries that name no real model -- see module
    docstring. `public_id` values deliberately look nothing like a real
    provider route (`prefix/model-name`) so a pass can never be confused
    with routing to an actual catalog entry."""
    return [
        Candidate(
            provider_model_id=f'probe-shape-{i}',
            public_id=f'probe-shape-{i}',
            input_per_million=1,
            output_per_million=1,
            context_window=1,
            upstream=None,
            blended=i,
        )
        for i in range(1, _SHAPE_MENU_SIZE + 1)
    ]


async def _call(provider, model_id: str, user_prompt: str) -> tuple[str | None, str | None]:
    """One live chat/completions call. Returns `(reply_content, None)` on a
    200 response, or `(None, transient_reason)` on ANY HTTP-level problem --
    a non-200 status (429, 5xx, and other 4xx alike -- see module
    docstring), a timeout, or a transport exception. Never raises.

    `httpx.TimeoutException` is NOT a subclass of the builtin `TimeoutError`
    -- both are checked, same as `smart_router_llm.llm_route`'s identical
    guard and for the identical reason (measured live in this same file
    earlier the same day: `ReadTimeout.__mro__` does not include
    `TimeoutError`)."""
    payload = {
        'model': model_id,
        'messages': [
            {'role': 'system', 'content': _SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt},
        ],
        'max_tokens': _MAX_TOKENS,
        'temperature': _TEMPERATURE,
    }
    try:
        r = await _http.post(
            f'{provider.v1}/chat/completions',
            json=payload,
            headers={**provider.headers(), 'Accept': 'application/json'},
            timeout=_PROBE_TIMEOUT,
        )
    except (TimeoutError, httpx.TimeoutException) as e:
        logger.info(f'router_probe timeout model={model_id}: {e}')
        return None, 'transient_timeout'
    except Exception as e:
        logger.info(f'router_probe request failed model={model_id}: {e}')
        return None, 'transient_exception'
    if r.status_code != 200:
        return None, f'transient_http_{r.status_code}'
    try:
        data = r.json()
    except Exception:
        return None, 'transient_exception'
    reply = ((data.get('choices') or [{}])[0].get('message') or {}).get('content')
    return reply, None


def _merge_transient(prev_entry: dict | None, reason: str, now_iso: str) -> dict[str, Any]:
    """A transient failure NEVER erases a previous ok=true -- see module
    docstring's outcome table. When there is no previous good result, the
    model simply stays unconfirmed (ok=false) with the transient reason
    attached, so a permanently-broken model and a never-yet-probed model
    both start from the same honest "not eligible" state."""
    retry_after = (datetime.now(timezone.utc) + RETRY_AFTER_TRANSIENT).isoformat()
    if prev_entry and prev_entry.get('ok'):
        merged = dict(prev_entry)
        merged['reason'] = reason
        merged['retry_after'] = retry_after
        merged['transient_at'] = now_iso
        return merged
    return {'ok': False, 'reason': reason, 'at': now_iso, 'retry_after': retry_after}


def _band_of_sample(position: int | None, menu: list[Candidate], thresholds: tuple[int, int]) -> int | None:
    if position is None or not (1 <= position <= len(menu)):
        return None
    return band_of(menu[position - 1], thresholds)


async def _probe_one(
    candidate: Candidate,
    shape_menu: list[Candidate],
    disc_menu: list[Candidate],
    thresholds: tuple[int, int],
    prev_entry: dict | None,
    now_iso: str,
) -> dict[str, Any]:
    """Stage 1 then stage 2 for one candidate. See module docstring for the
    three-outcome table this implements."""
    provider = get_provider(candidate.upstream) if candidate.upstream else None
    if provider is None:
        return {'ok': False, 'reason': 'provider_not_configured', 'at': now_iso}

    # Stage 1 -- shape, once, against the synthetic menu. Rendered through
    # the SAME build_prompt() production calls (see module docstring) --
    # `thresholds` here is the real pool's, applied to the synthetic menu;
    # the actual band numbers this stage's prompt shows are irrelevant to a
    # shape check, only that the call shape matches production exactly.
    shape_prompt = build_prompt(_REFERENCE_MESSAGES['greeting'], shape_menu, thresholds)
    reply, transient = await _call(provider, candidate.provider_model_id, shape_prompt)
    if transient:
        return _merge_transient(prev_entry, transient, now_iso)
    if _parse_choice(reply, len(shape_menu)) is None:
        return {
            'ok': False, 'shape_ok': False, 'reason': 'bad_shape',
            'at': now_iso, 'sample_reply': reply,
        }

    # Stage 2 -- discrimination, three fixed reference messages against the
    # ANNOTATED real-pool menu.
    samples: dict[str, int | None] = {}
    for label, message in _REFERENCE_MESSAGES.items():
        prompt_text = build_prompt(message, disc_menu, thresholds)
        reply, transient = await _call(provider, candidate.provider_model_id, prompt_text)
        if transient:
            return _merge_transient(prev_entry, transient, now_iso)
        idx = _parse_choice(reply, len(disc_menu))
        samples[label] = (idx + 1) if idx is not None else None

    greeting_band = _band_of_sample(samples.get('greeting'), disc_menu, thresholds)
    reasoning_band = _band_of_sample(samples.get('reasoning'), disc_menu, thresholds)
    discriminates = greeting_band == 1 and reasoning_band is not None and reasoning_band >= 2
    if not discriminates:
        return {
            'ok': False, 'shape_ok': True, 'discriminates': False,
            'reason': 'no_discrimination', 'at': now_iso, 'samples': samples,
        }
    return {
        'ok': True, 'shape_ok': True, 'discriminates': True,
        'at': now_iso, 'samples': samples,
    }


async def run_probe_scan() -> dict[str, Any]:
    """Measure the `SCAN_LIMIT` cheapest pool members and persist the
    result. The ONLY function in this module that makes a live upstream
    call OR opens a write transaction -- called from exactly one place,
    `admin_smart_router.py`'s POST handler, on an admin's explicit request.
    NEVER call this from the chat path (see module docstring's red line).

    Never raises: any per-model failure is captured in that model's stored
    result (see `_probe_one`), and a DB read/write failure degrades to
    "start from empty"/"drop the write" with a warning, exactly the same
    fail-closed posture as the rest of this module.
    """
    pool = await candidate_pool()
    scan_targets = pool[:SCAN_LIMIT]
    previous = await _read_stored()
    prev_results = previous.get('results') or {}
    full_pool_keys = {c.public_id for c in pool}
    scan_keys = {c.public_id for c in scan_targets}

    # Models still in the full pool but not re-scanned this round (ranked
    # 13th+) keep their last known result untouched. Models no longer in
    # the full pool at all are dropped here -- "left the catalog" (see
    # module docstring's outcome table) -- and never reappear even if
    # `scan_targets` below fails to produce a fresh entry for them.
    new_results: dict[str, Any] = {
        key: entry for key, entry in prev_results.items()
        if key in full_pool_keys and key not in scan_keys
    }

    shape_menu = _synthetic_shape_menu()
    disc_menu = _menu(pool)
    thresholds = band_thresholds(pool)
    now_iso = datetime.now(timezone.utc).isoformat()

    for c in scan_targets:
        try:
            new_results[c.public_id] = await _probe_one(
                c, shape_menu, disc_menu, thresholds, prev_results.get(c.public_id), now_iso,
            )
        except Exception as e:
            logger.warning(f'router_probe: measuring {c.public_id!r} raised, recording as transient: {e}')
            new_results[c.public_id] = _merge_transient(
                prev_results.get(c.public_id), 'transient_exception', now_iso,
            )

    value = {'version': 1, 'measured_at': now_iso, 'results': new_results}
    try:
        await _persist(value)
    except Exception as e:
        logger.warning(f'{SETTING_KEY} write failed, measurement was not saved: {e}')
    return value
