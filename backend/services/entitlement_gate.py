"""Wiring layer between package entitlements (services/entitlements.py) and
the chat billing / reservation / payment-grant call sites.

services/entitlements.py is the source of truth for the entitlement rules
(NULL-ceiling fails closed, NULL remaining means "not metered", money is
integer Toman) and must not be modified here or reimplemented here. This
module only orchestrates *when* those functions get called from four
reservation sites, one consumption site, and one grant site, so that
reasoning lives in exactly one place instead of four-plus copies.

── Fail-safe direction (the one rule every function here must uphold) ─────
Every function in this module swallows its own exceptions and returns a
value that means "there is no entitlement here, fall back to the normal
wallet path" -- never raises past this module, never takes chat down, and
never makes a request free by accident. An entitlement lookup that throws
must look exactly like an entitlement lookup that legitimately found
nothing.
"""
from __future__ import annotations

import logging
from typing import Optional

from services.entitlements import (
    consume_entitlement,
    find_covering_entitlement,
    grant_entitlement,
)

logger = logging.getLogger('chat')  # shared with chat_*.py's billing logs


async def covering_entitlement(uid: int, est_cost_toman: int) -> Optional[dict]:
    """Best active entitlement covering a request estimated at
    ``est_cost_toman`` Toman, or None.

    Called at each of the four reserve sites (chat.py, chat_smart.py,
    chat_web.py, chat_compare.py) BEFORE opening a wallet reservation: when
    this returns non-None the caller must skip BillingService.reserve()
    entirely for that request (leave ``reservation = None``) so a user who
    bought a package but has an empty wallet is not rejected at reserve.

    This is a read-only pre-authorization, not a spend -- it does not
    decrement anything, so it is safe to call once per reservation (twice
    in one /v1/compare request, once per model) even against the same
    entitlement; the actual spend only happens later, atomically, in
    consume_for_usage() at the real charge point.

    Returns None both when nothing covers the request AND when the lookup
    itself raised -- the caller cannot and must not tell the difference,
    since both cases mean "proceed with the normal wallet reservation".
    """
    try:
        return await find_covering_entitlement(uid, int(est_cost_toman))
    except Exception as e:
        logger.warning(f"entitlement_gate.covering_entitlement failed uid={uid}: {e}")
        return None


async def consume_for_usage(uid: int, cost_toman: int, total_tokens: int) -> Optional[dict]:
    """Try to pay an ACTUAL usage cost (not the reserve-time estimate) from
    an entitlement, at the real charge point (chat_billing._record_usage,
    before the wallet lock).

    Re-runs find_covering_entitlement against the real ``cost_toman`` --
    which may exceed the estimate used at reserve time -- so the ceiling
    guard (max_cost_per_request_toman >= cost) is re-checked against what
    was actually served, keeping "no request may be loss-making" true even
    on an estimate overshoot. Only on a hit does it call
    consume_entitlement(), which is the single atomic spend.

    Returns the entitlement dict that was actually consumed on success (the
    caller logs/records its id), or None on every path that must fall back
    to the wallet unchanged:
      * no entitlement covers this exact cost
      * consume_entitlement() returned False -- its documented contract is
        that the caller must then bill the wallet; this can legitimately
        happen even right after find_covering_entitlement found a hit (a
        concurrent request raced it to zero, or it expired/was deactivated
        in between)
      * anything in this function raised

    Never charges an entitlement and lets the caller ALSO charge the
    wallet -- returning a truthy value here is the caller's sole signal
    that the request was paid by quota, full stop.
    """
    try:
        cost_toman = int(cost_toman)
        entitlement = await find_covering_entitlement(uid, cost_toman)
        if entitlement is None:
            return None
        ok = await consume_entitlement(entitlement['id'], requests=1, tokens=max(0, int(total_tokens)))
        if not ok:
            return None
        return entitlement
    except Exception as e:
        logger.warning(f"entitlement_gate.consume_for_usage failed uid={uid} cost={cost_toman}: {e}")
        return None


async def record_entitlement_usage(
    session,
    uid: int,
    model: str,
    entitlement_id: int,
    cost_toman: int,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    estimated: bool,
) -> None:
    """Record the usage_events row for a request paid by quota, not wallet.

    Mirrors chat_billing._record_usage's own wallet-path metering call
    (charge=Money(0), since the wallet did not move) but tags the event
    honestly as entitlement-covered. services/metering.py::record_usage does
    not expose a ``billing_source`` parameter today (usage_events.billing_source
    -- migration 0005 -- defaults to 'wallet' at the ORM level and nothing
    here overrides that column directly), so the fact that this request was
    quota-covered goes into ``meta`` instead, alongside the entitlement id
    and what the wallet charge would have been -- never silently dropped.

    Never raises: a failure to write the usage event must not turn an
    already-consumed entitlement into a failed request, the same best-effort
    behaviour the wallet path's own metering call already has.
    """
    import secrets as _secrets
    from services.billing import SqlBillingRepo
    from services.metering import record_usage
    from services.money import Money
    try:
        await record_usage(
            SqlBillingRepo(session),
            request_id=_secrets.token_hex(8),
            user_id=uid,
            model=model,
            charge=Money(0),
            upstream_status='success',
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            meta={
                'estimated': estimated,
                'source': 'local_estimate' if estimated else 'upstream',
                'billing_source': 'entitlement',
                'entitlement_id': entitlement_id,
                'wallet_cost_toman': cost_toman,
            },
        )
    except Exception as e:
        logger.warning(
            f"entitlement_gate.record_entitlement_usage failed uid={uid} "
            f"model={model!r} entitlement_id={entitlement_id}: {e}"
        )


async def grant_for_payment(uid: int, package_id: str, source_payment_id: str) -> Optional[dict]:
    """Grant a package's quota entitlement after a completed payment.

    Must be called AFTER the wallet has already been credited (this only
    ever adds a quota row; it never touches Wallet.balance) and must be
    non-fatal to the caller: payment_endpoints.py's callback has already
    told Zarinpal/the user the payment succeeded by the time this runs, so
    a failure here must never fail the callback or change the redirect --
    it is logged at ERROR (loud, with uid/package/payment so it can be
    reconciled by hand) and swallowed.

    ``source_payment_id`` must be stable across a replayed gateway
    callback -- grant_entitlement()'s ON CONFLICT DO NOTHING on
    (package_id, source_payment_id) is what makes a replay a no-op instead
    of a second free quota grant, but only if the same value is passed
    every time for the same payment.
    """
    try:
        return await grant_entitlement(uid, package_id, source_payment_id=source_payment_id)
    except Exception as e:
        logger.error(
            f"entitlement_gate.grant_for_payment FAILED uid={uid} package_id={package_id} "
            f"source_payment_id={source_payment_id}: {e} -- quota NOT granted, needs manual reconciliation"
        )
        return None
