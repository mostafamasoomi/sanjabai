"""Usage estimation and billing -- split out of chat.py (see chat.py's
module docstring for why).

Holds the loss-path hardening (L1-L4, documented inline below),
``_record_usage`` (the actual ledger/wallet-writing billing path),
``_track_usage`` (non-streaming) and ``_bill_stream_usage`` (streaming).

MONKEYPATCH CONTRACT: tests patch `chat_mod._get_user_id`,
`chat_mod.async_session`, and directly call `chat_mod._record_usage`,
`chat_mod._track_usage` (see test_billing_loss_paths.py,
test_wallet_balance_charge.py, test_markup_billing_wire.py,
test_with_file_web_search.py). `_track_usage`/`_bill_stream_usage` resolve
`_get_user_id` and `async_session` through `chat.<name>` at call time
(never a bare name) so those patches are observed regardless of the fact
that these functions no longer live in chat.py itself. `_record_usage`
takes an already-open `session` as a parameter (not `async_session`
itself), but still calls chat.py-owned `_as_naive_utc` through `chat.`
for the same reason. `chat` is imported plainly at module scope, which is
safe against the chat.py <-> chat_billing.py circular import: nothing here
touches a `chat` attribute until a function actually runs, by which point
chat.py has finished executing.

SPLIT NOTE (2026-08-24): the L1/L2 loss-path estimation constants and pure
helper functions (`ESTIMATE_CHARS_PER_TOKEN`, `FALLBACK_PRICE_PER_MILLION_IN`,
`FALLBACK_PRICE_PER_MILLION_OUT`, `_estimate_tokens_from_chars`,
`_estimate_message_text_chars`, `_estimate_input_tokens`,
`_estimate_output_tokens`, `_extract_reasoning_tokens`,
`_usage_idempotency_key`, `_extract_response_text`) now physically live in
chat_billing_estimate.py, purely to stay under the house 500-line cap --
nothing about their behaviour changed. They are re-exported below
(`# noqa: F401` where unused directly in this file) so every existing
`from chat_billing import ...` (chat.py, admin_overhead.py,
tests/test_upstream_overhead.py) and `chat_billing.<name>` reference
(tests/test_entitlement_wiring.py) keeps resolving exactly as before. These
are pure functions with no `chat` module dependency, so -- unlike
`_record_usage`/`_track_usage`/`_bill_stream_usage` above -- nothing here
needed the late-binding `chat.<name>` treatment.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from models import Quota, Ledger
from providers import extract_kiro_credits

import chat

from chat_billing_estimate import (  # noqa: F401
    ESTIMATE_CHARS_PER_TOKEN,
    FALLBACK_PRICE_PER_MILLION_IN,
    FALLBACK_PRICE_PER_MILLION_OUT,
    _estimate_tokens_from_chars,
    _estimate_message_text_chars,
    _estimate_input_tokens,
    _estimate_output_tokens,
    _extract_reasoning_tokens,
    _usage_idempotency_key,
    _extract_response_text,
)

logger = logging.getLogger('chat')  # keep all chat_*.py logs under the pre-split 'chat' logger name


async def _record_usage(session: AsyncSession, uid: int, payload: dict[str, Any], usage: dict[str, Any], idempotency_key: str | None = None, response_text: str = '') -> dict[str, Any]:
    """Shared billing logic for tracking and billing usage. Returns cost info dict.

    Implements the loss-path fixes documented above (L1 missing/partial
    usage -> local estimate, L2 price-lookup-miss floor, L3 reasoning
    tokens, L4 shortfall still charges + records).
    """
    result = {'input_tokens': 0, 'output_tokens': 0, 'cost': 0, 'balance_after': 0}
    usage = usage or {}
    model = payload.get('model', '')

    input_tokens = int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0)
    output_tokens = int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)
    reasoning_tokens = _extract_reasoning_tokens(usage)

    # L1: local estimate for whichever side the upstream omitted. Handles
    # both a fully-missing usage block (the common case: some 9router
    # backend ignores stream_options.include_usage entirely) and a partial
    # one (real prompt_tokens but a botched/absent completion_tokens, or
    # vice versa) -- either way a served response must never be billed as
    # if it cost zero tokens.
    estimated = False
    # Tracked separately from `estimated` (which also goes True when only
    # the OUTPUT side was estimated): the upstream-overhead discount below
    # must only ever touch a REAL upstream-reported input_tokens value, so
    # it needs to know specifically whether the INPUT side came from our
    # own _estimate_input_tokens() rather than the upstream.
    input_estimated = False
    if input_tokens <= 0 and output_tokens <= 0 and reasoning_tokens <= 0:
        input_tokens = _estimate_input_tokens(payload.get('messages'))
        output_tokens = _estimate_output_tokens(response_text)
        estimated = True
        input_estimated = True
    else:
        if input_tokens <= 0:
            input_tokens = _estimate_input_tokens(payload.get('messages'))
            estimated = True
            input_estimated = True
        if output_tokens <= 0 and reasoning_tokens <= 0:
            output_tokens = _estimate_output_tokens(response_text)
            estimated = True

    # L3: fold reasoning tokens into output_tokens (billed at the output
    # rate -- model_catalog.reasoning_per_million is not populated for any
    # row today, so a separate reasoning rate would just be an unbilled
    # column; folding into output is simple, conservative, and correct
    # either way). The OpenAI spec says completion_tokens already includes
    # reasoning tokens, but not every gateway honours that, and nothing in
    # the response tells us which case we're in -- we bill as though it
    # does NOT (the conservative side of "never lose money"): in the
    # spec-compliant case this slightly over-bills by reasoning_tokens
    # rather than risk under-billing a thinking model that forgot to fold
    # them in.
    if reasoning_tokens > 0:
        output_tokens = output_tokens + reasoning_tokens

    if input_tokens <= 0 and output_tokens <= 0:
        # Nothing real and nothing estimable (e.g. empty messages and an
        # empty response) -- nothing was actually served, so there is
        # nothing to bill. Do not fabricate a charge.
        return result

    if estimated:
        # KNOWN LOWER BOUND, not a best-effort match to real usage: every
        # upstream route has been observed to inject a large preamble
        # server-side, AFTER our outgoing payload leaves us (a system
        # prompt / template the upstream adds before calling the actual
        # model) -- our messages-based estimate has no way to see it and
        # cannot be corrected for it here (the size is upstream/route-
        # specific and not reliably knowable from this side). Measured
        # prompt_tokens for the SAME 2-character message: ~2784 on the
        # gemini routes, ~5756 on kr/glm-5 -- thousands of tokens this
        # estimate will never include. So a real conversation can show
        # wildly different input_tokens between a request where usage came
        # back (large, real, includes the preamble) and one where it did
        # not (small, estimated, preamble-blind). Logged at WARNING with
        # the literal numbers so this gap is loud, not silently absorbed
        # into "billing succeeded."
        logger.warning(
            f"_record_usage: BILLING ESTIMATE (LOCAL ESTIMATE, not real usage) for "
            f"model={model!r} uid={uid} -- input_tokens={input_tokens} "
            f"output_tokens={output_tokens} (chars_per_token={ESTIMATE_CHARS_PER_TOKEN}). "
            f"KNOWN LOWER BOUND: excludes any upstream-side hidden preamble not present "
            f"in our outgoing payload -- real prompt_tokens for this model/route may be "
            f"thousands of tokens higher (observed ~2784-5756 on other routes for a "
            f"2-character message) -- do not treat this number as authoritative."
        )

    # ── Upstream prompt-overhead discount (owner decision 2026-08-23) ─────
    # Some upstream routes (measured: ninerouter's cc/ and ag/ prefixes
    # worst of all) inject a preamble into the prompt server-side, AFTER
    # our outgoing payload leaves us, and report the inflated total back as
    # prompt_tokens -- the user never wrote that text and must not pay for
    # it. services/upstream_overhead.py holds the measured map (app_setting
    # key upstream_prompt_overhead, seeded empty/inert by migration 0041
    # until an admin runs POST /admin/upstream-overhead/measure).
    #
    # Only applies when input_tokens is a REAL upstream-reported number:
    # input_estimated means input_tokens came from our own
    # _estimate_input_tokens(payload['messages']), which by construction
    # already excludes anything the upstream might have injected --
    # discounting an already-preamble-free estimate would undercharge, not
    # correct anything.
    #
    # The floor is mandatory and non-negotiable: our own local estimate of
    # what the user's messages actually contain. Without it a stale or
    # over-large overhead entry (a bad measurement, or a route that changed
    # its preamble size) could let a user send a huge prompt and be billed
    # for almost nothing -- discounted_input_tokens() enforces
    # max(raw - overhead, floor, 1) so the billed number can never fall
    # below what we can independently verify was sent.
    #
    # This entire block must never be able to raise past _record_usage's
    # hard "never raises" contract -- any failure here falls back to
    # billing the untouched raw upstream number, which is the safe
    # (never-undercharge) direction.
    #
    # Provider is resolved ONCE here (the same chat._resolve_provider(model)
    # every other module-level call site uses -- see chat.py's
    # _apply_persian_style_guard_for_model / the non-streaming health-check
    # call -- never a second resolution path) and reused below both for the
    # overhead lookup and for the usage_events.provider column, which this
    # metering call has never actually populated (services/metering.py's
    # record_usage() has always accepted a `provider` kwarg; nothing calling
    # it from this function passed one, so every usage_events row has
    # provider = NULL). Threading it through here is what makes
    # admin_overhead.py's "per-provider requests / tokens discounted" report
    # mean anything at all.
    provider_name = ''
    try:
        _provider_obj = await chat._resolve_provider(model)
        provider_name = getattr(_provider_obj, 'name', '') or ''
    except Exception as e:
        logger.warning(
            f"_record_usage: provider resolution failed model={model!r} uid={uid}: {e}"
        )

    prompt_tokens_raw = input_tokens
    prompt_overhead_discounted = 0
    if not input_estimated and provider_name:
        try:
            from services.upstream_overhead import discounted_input_tokens, get_prompt_overhead
            overhead = await get_prompt_overhead(provider_name, model)
            if overhead > 0:
                floor = _estimate_input_tokens(payload.get('messages'))
                billed = discounted_input_tokens(input_tokens, overhead, floor)
                if billed < input_tokens:
                    prompt_overhead_discounted = input_tokens - billed
                    logger.info(
                        f"_record_usage: prompt overhead discount applied "
                        f"provider={provider_name} model={model!r} uid={uid} "
                        f"raw={input_tokens} overhead={overhead} billed={billed}"
                    )
                    input_tokens = billed
        except Exception as e:
            logger.warning(
                f"_record_usage: prompt overhead discount failed model={model!r} uid={uid}: {e}"
            )

    total_tokens = input_tokens + output_tokens
    result['input_tokens'] = input_tokens
    result['output_tokens'] = output_tokens

    # Quota tracking (self-healing upsert -- see loss-path audit follow-up).
    # auth.py only creates a Quota row for users who signed up AFTER that
    # code existed; any earlier account (this deployment's only real user
    # included) has none. This used to be a bare UPDATE, which matches zero
    # rows and silently does nothing when no row exists -- used_today was
    # therefore never recorded for such users, at all, ever. Upsert instead
    # of "create at signup only": it self-heals every existing gap (past and
    # future) in one place rather than requiring a backfill migration, and
    # this table has no unique constraint on user_id to build a real
    # ON CONFLICT upsert on, so a plain select-then-insert/update is used.
    # NOTE: this has a narrow race window under truly concurrent first
    # requests from the same never-before-seen user (both could see no row
    # and both INSERT) -- acceptable for a soft usage counter, not a money
    # invariant like Ledger; worth a `UNIQUE(user_id)` constraint migration
    # if that ever matters.
    _now = datetime.now(timezone.utc).replace(tzinfo=None)
    res = await session.execute(Quota.__table__.select().where(Quota.user_id == uid))
    quota = res.fetchone()
    if quota:
        _quota_reset_at = chat._as_naive_utc(quota.reset_at)
        if _quota_reset_at and _now >= _quota_reset_at:
            # Roll the daily counter over. Previously only _check_quota_pre
            # did this rollover, and that function is a fallback that only
            # runs when BillingService.reserve() raises an unexpected
            # exception -- it is not on the normal per-request path (see
            # chat()/chat_with_file()/compare_models()/smart_chat()), so
            # relying on it alone meant used_today could also just never
            # roll over in practice.
            new_used = total_tokens
            new_reset_at = _now + timedelta(days=1)
        else:
            new_used = quota.used_today + total_tokens
            new_reset_at = _quota_reset_at
        await session.execute(
            Quota.__table__.update().where(Quota.user_id == uid),
            {'used_today': new_used, 'reset_at': new_reset_at, 'updated_at': _now},
        )
    else:
        session.add(Quota(
            user_id=uid, daily_limit=200000, used_today=total_tokens,
            reset_at=_now + timedelta(days=1), updated_at=_now,
        ))

    price_row = None
    try:
        price_res = await session.execute(
            sqlalchemy.text(
                'SELECT input_per_million, output_per_million, markup_pct '
                'FROM model_catalog '
                'WHERE provider_model_id = :mid AND availability = :avail LIMIT 1'
            ),
            {'mid': model, 'avail': 'available'},
        )
        price_row = price_res.fetchone()
    except Exception as e:
        logger.warning(f"_record_usage price lookup failed model={model} uid={uid}: {e}")

    if price_row and (price_row.input_per_million or price_row.output_per_million):
        # The profit percentage is applied HERE, at read time, through the
        # same apply_markup() the catalog endpoints use -- not baked into the
        # stored price. That identity is the whole point: if billing computed
        # the markup its own way, we would show the user one number and
        # charge another. model_catalog stores the BASE Toman price; the
        # effective percentage is the model's own markup_pct override, or the
        # global setting when that column is NULL.
        from content import apply_markup, get_effective_markup_pct

        # getattr, not attribute access: `markup_pct` arrives from migration
        # 0030, and a price row produced by an older code path or a test
        # double may not carry it. Missing => None => inherit the global.
        effective_pct = await get_effective_markup_pct(
            getattr(price_row, 'markup_pct', None)
        )
        inp_rate = apply_markup(price_row.input_per_million, effective_pct)
        out_rate = apply_markup(price_row.output_per_million, effective_pct)
    else:
        # L2: no price row for a model we just served -- a catalog data bug,
        # not a billing decision. Bill at the configurable ceiling rate
        # (FALLBACK_PRICE_PER_MILLION_* above) instead of the old
        # `total_tokens // 1000` guess, which undercharged real rates
        # (e.g. Gemini 2.5 Pro at ~238/1000 tokens) by roughly two orders
        # of magnitude. Logged as an ERROR (not a warning) because it means
        # the catalog needs fixing, not just "this one request was odd".
        inp_rate = FALLBACK_PRICE_PER_MILLION_IN
        out_rate = FALLBACK_PRICE_PER_MILLION_OUT
        logger.error(
            f"_record_usage: no price row for served model={model!r} uid={uid} "
            f"-- billing at fallback ceiling rate in={inp_rate}/M out={out_rate}/M; "
            f"this model_catalog entry needs fixing"
        )
    cost = max(1, int((input_tokens * inp_rate + output_tokens * out_rate + 500_000) // 1_000_000))

    # Entitlement gate: real (not estimated) cost may be covered by a
    # package quota, consumed atomically before the wallet is touched --
    # fail-safe fallback to the wallet path lives in entitlement_gate.py.
    from services.entitlement_gate import consume_for_usage, record_entitlement_usage
    entitlement = await consume_for_usage(uid, cost, total_tokens)
    if entitlement is not None:
        # Paid by quota: no Wallet.balance change, no Ledger row (would
        # muddy balance == ledger_sum); balance_after is the real balance.
        from services.billing import SqlBillingRepo
        wallet = await SqlBillingRepo(session).ensure_wallet(uid)
        result['cost'] = 0
        result['balance_after'] = wallet['balance']
        await record_entitlement_usage(
            session, uid, model, entitlement['id'], cost,
            input_tokens, output_tokens, reasoning_tokens, estimated,
        )
        return result

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
            charged = cost
            new_balance = current - cost
        else:
            # L4: actual usage cost exceeds the current balance. reserve()
            # gates the common case pre-flight; this is the residual where
            # real usage ran over the reserved estimate. Charge whatever is
            # left rather than silently charging (and recording) nothing.
            # Do NOT let the wallet go negative and do NOT change the
            # overdraft policy -- going into debt is a product decision the
            # owner has not made -- just stop the silent zero and make the
            # shortfall visible for reconciliation.
            charged = current
            new_balance = 0
            logger.warning(
                f"_record_usage: L4 shortfall uid={uid} model={model!r} "
                f"cost={cost} balance_before={current} charged={charged} "
                f"shortfall={cost - charged}"
            )
        await _repo.set_wallet_balance(uid, new_balance)
        reason = f'مصرف {model}'
        if charged < cost:
            reason += ' (کسری موجودی)'
        entry = Ledger(user_id=uid, txn_type='usage', amount=-charged, balance_after=new_balance, reason=reason, idempotency_key=idempotency_key)
        session.add(entry)
    result['cost'] = charged
    result['balance_after'] = new_balance

    try:
        from services.metering import record_usage
        from services.money import Money
        meta: dict[str, Any] = {'estimated': estimated, 'source': 'local_estimate' if estimated else 'upstream'}
        # Always recorded (merged into `meta`, never overwriting the keys
        # above or set below) -- prompt_tokens_raw is what the upstream
        # actually reported before any discount; prompt_overhead_discounted
        # is 0 when no discount applied (estimated input, no matching
        # overhead entry, or overhead computed to 0). Together these make
        # every billed input_tokens value auditable against what the
        # upstream said, not just a number that looks smaller than before.
        meta['prompt_tokens_raw'] = prompt_tokens_raw
        meta['prompt_overhead_discounted'] = prompt_overhead_discounted
        # F2: the `kr/` routes' credit cost signal, in the UPSTREAM's credit
        # unit -- not Toman, not a charge, never read back by billing. Kept
        # only so cost analysis can compare what a request earned against
        # what it cost us. Absent on every other route, and absent (rather
        # than null) when a kr/ response did not carry it.
        kiro_credits = extract_kiro_credits(usage, model=model)
        if kiro_credits is not None:
            meta['kiro_credits'] = kiro_credits
        if charged < cost:
            meta['listed_cost'] = cost
            meta['shortfall'] = cost - charged
        await record_usage(
            _repo,
            request_id=secrets.token_hex(8),
            user_id=uid,
            model=model,
            provider=provider_name or None,
            charge=Money(charged),
            upstream_status='success',
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            meta=meta,
        )
    except Exception as e:
        logger.warning(f"_record_usage metering failed model={model} uid={uid}: {e}")

    return result


async def _track_usage(request: Request, payload: dict[str, Any], response_data: dict[str, Any]) -> dict[str, Any]:
    """Record token usage for non-streaming requests. Returns cost info.

    L1: does NOT early-return when usage is missing/zero -- that early
    return was exactly the bug (a served response billed nothing because
    the upstream omitted `usage`). _record_usage now falls back to a local
    estimate in that case, so it must always be given the chance to run.
    """
    uid = await chat._get_user_id(request)
    if not uid or chat.async_session is None:
        return {}
    usage = response_data.get('usage') or {}
    if not usage:
        # Diagnose WHY, not just paper over it with the estimate fallback:
        # log the SHAPE of what actually came back (keys only, never
        # content) so a future occurrence of this is diagnosable instead of
        # silently invisible like the incident this fix responds to.
        logger.warning(
            f"_track_usage: no usable usage block model={payload.get('model')!r} "
            f"response_keys={sorted(response_data.keys()) if isinstance(response_data, dict) else type(response_data).__name__} "
            f"usage_field_type={type(response_data.get('usage')).__name__ if isinstance(response_data, dict) else 'n/a'}"
        )
    idempotency_key = _usage_idempotency_key(response_data.get('id'))
    response_text = _extract_response_text(response_data)
    try:
        async with chat.async_session() as session:
            cost_info = await _record_usage(session, uid, payload, usage, idempotency_key=idempotency_key, response_text=response_text)
            await session.commit()
            return cost_info
    except Exception as e:
        logger.warning(f"_track_usage failed uid={uid} model={payload.get('model')}: {e}")
        return {}


async def _bill_stream_usage(uid: int, payload: dict[str, Any], usage: dict[str, Any], response_text: str = '') -> dict[str, Any]:
    """Bill the user after a streaming chat completes. Returns cost info.

    L1: no early return on missing/zero usage -- see _track_usage docstring.
    ``response_text`` is the accumulated assistant text from the SSE deltas,
    used as the L1 output-token estimate when the upstream never sent a
    usage chunk at all.
    """
    try:
        async with chat.async_session() as session:
            cost_info = await _record_usage(session, uid, payload, usage or {}, response_text=response_text)
            await session.commit()
            return cost_info
    except Exception as e:
        logger.warning(f"_bill_stream_usage failed uid={uid} model={payload.get('model')}: {e}")
        return {}
