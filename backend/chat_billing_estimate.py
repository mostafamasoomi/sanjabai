"""Loss-path estimation helpers for chat_billing.py -- split out purely to
keep chat_billing.py under the house 500-line cap. See chat_billing.py's
module docstring for the split's origin and chat.py's module docstring for
why chat.py is split into chat_*.py files at all.

Holds the L1 (local token estimate) and L2 (fallback price ceiling)
loss-path constants/helpers that ``chat_billing._record_usage`` calls.
Nothing here changed in the move -- see git history for the substantive
loss-path-hardening commits that introduced this logic in the first place.

IMPORT CONTRACT: these are pure functions (no dependency on the `chat`
module, no DB/session access) and nothing in the test suite monkeypatches
any name here directly -- `tests/test_upstream_overhead.py` and
`admin_overhead.py` both do `from chat_billing import _estimate_input_tokens`
(the re-export chat_billing.py keeps below), not
`from chat_billing_estimate import ...`, so callers should keep going
through `chat_billing` rather than importing this module directly, but
either form resolves to the exact same function object.
"""
from __future__ import annotations

import math
import os
import secrets
from typing import Any

# ── Billing fallbacks (loss-path hardening) ──────────────────────
#
# Owner's hard requirement: "we must be profitable on the price we offer
# the user, and must never lose money on any request, in the ratio of the
# user's usage of each model against what we pay per token." The constants
# and helpers below back the loss paths _record_usage otherwise has.

# L1: chars-per-token used to estimate tokens locally when an upstream
# omits `usage` (or returns a malformed/all-zero usage block). 9router fans
# out to dozens of heterogeneous backends and any one of them may ignore
# stream_options.include_usage or just not send a usage object -- serving
# the response and billing zero for that request is a 100% loss.
#
# No tokenizer dependency (tiktoken/transformers) exists in requirements.txt
# and we were told not to add a heavyweight one just for this, so this is a
# documented chars-per-token heuristic, not an exact count. The product UI
# is Persian, which runs far denser than English (~1.5-3 chars/token vs
# ~4 for English/code). We use the LOW end of the Persian range: fewer
# chars assumed per token means the same text produces a HIGHER estimated
# token count, which is the conservative direction for a "never bill less
# than what was served" policy -- it trades a possible over-estimate on
# English/code-heavy messages for the guarantee that a Persian message is
# never under-counted.
ESTIMATE_CHARS_PER_TOKEN = 1.5

# L2: floor price used only when a served model has no price row in
# model_catalog (a data bug -- every available model should have one).
# Defaults are the CEILING of the catalog's current price band -- the max
# input_per_million / output_per_million among availability='available'
# rows as of 2026-08-21 (kr/claude-sonnet-4.5-thinking: 571,800 in /
# 2,859,000 out, IRT per million) -- so a lookup miss can never under-bill
# relative to what any real available model actually costs at our prices.
# Configurable because the catalog's price ceiling moves as models are
# added/repriced.
FALLBACK_PRICE_PER_MILLION_IN = int(os.getenv('FALLBACK_PRICE_PER_MILLION_IN', '571800'))
FALLBACK_PRICE_PER_MILLION_OUT = int(os.getenv('FALLBACK_PRICE_PER_MILLION_OUT', '2859000'))


def _estimate_tokens_from_chars(n_chars: int) -> int:
    """Conservative local token estimate from a raw character count."""
    if n_chars <= 0:
        return 0
    return max(1, math.ceil(n_chars / ESTIMATE_CHARS_PER_TOKEN))


def _estimate_message_text_chars(messages: list | None) -> int:
    """Sum of visible text characters across an outgoing chat payload's
    messages, plus a small fixed overhead per message for role/formatting
    tokens (every real tokenizer charges something for these)."""
    total = 0
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        content = m.get('content', '')
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = part.get('text')
                    if isinstance(text, str):
                        total += len(text)
        total += 8  # per-message role/formatting overhead
    return total


def _estimate_input_tokens(messages: list | None) -> int:
    """L1: local input-token estimate from the outgoing payload['messages']
    -- the text we actually sent upstream."""
    return _estimate_tokens_from_chars(_estimate_message_text_chars(messages))


def _estimate_output_tokens(text: str) -> int:
    """L1: local output-token estimate from response text (non-streaming)
    or accumulated streamed deltas (streaming)."""
    return _estimate_tokens_from_chars(len(text or ''))


def _extract_reasoning_tokens(usage: dict) -> int:
    """L3: reasoning/thinking tokens the upstream produced, from whichever
    field it happens to expose. Thinking models are live in production
    (kr/claude-sonnet-4.5-thinking, availability='available') and reasoning
    tokens are real generated tokens that must be billed -- nothing reads
    model_catalog.reasoning_per_million today so they were simply dropped.

    Only ONE field is read (never summed across fields) so a gateway that
    exposes reasoning tokens both nested (OpenAI-style
    usage.completion_tokens_details.reasoning_tokens) and top-level (seen
    from some non-OpenAI-shaped gateways as usage.reasoning_tokens /
    usage.thinking_tokens) is never counted twice.
    """
    if not isinstance(usage, dict):
        return 0
    details = usage.get('completion_tokens_details')
    if isinstance(details, dict):
        v = details.get('reasoning_tokens')
        if v:
            try:
                return max(0, int(v))
            except (TypeError, ValueError):
                pass
    for key in ('reasoning_tokens', 'thinking_tokens'):
        v = usage.get(key)
        if v:
            try:
                return max(0, int(v))
            except (TypeError, ValueError):
                continue
    return 0


def _usage_idempotency_key(resp_id: str | None) -> str:
    """Idempotency key for a non-streaming usage-charge ledger row.

    Found live (2026-08-21): this used to be `f"usage:{resp_id}"` alone, on
    the assumption that the upstream's completion `id` is unique per
    request. Confirmed empirically FALSE for at least two models
    (tencent-hy3-free and mimo-v2.5-free both returned the IDENTICAL id
    across genuinely distinct, differently-worded requests) -- every
    billing attempt after the first for that model then collided with the
    ledger's UNIQUE(idempotency_key) constraint, raising IntegrityError and
    rolling back the ENTIRE transaction (ledger + wallet + quota) for a
    fully served response. There is no retry wrapper around _track_usage,
    so genuine double-submission protection was never actually
    load-bearing here; _bill_stream_usage (the streaming path) has never
    passed an idempotency_key at all and has not needed one. Generate a
    guaranteed-unique key instead of trusting an upstream implementation
    detail we do not control; resp_id is kept in the value purely as a
    human debugging breadcrumb, not for its uniqueness.
    """
    return f"usage:{resp_id or 'noid'}:{secrets.token_hex(8)}"


def _extract_response_text(response_data: dict) -> str:
    """Concatenate visible assistant text across all choices, for the L1
    output-token estimate fallback on the non-streaming path."""
    parts = []
    for choice in (response_data or {}).get('choices') or []:
        if not isinstance(choice, dict):
            continue
        content = (choice.get('message') or {}).get('content')
        if isinstance(content, str):
            parts.append(content)
    return ''.join(parts)


def _reconcile_usage(response_data: Any, cost_info: dict[str, Any]) -> None:
    """Overwrite the raw upstream `usage` block echoed to the client with
    what was actually billed. Upstreams can inject phantom preamble tokens
    (e.g. prompt_tokens=2206) that _record_usage correctly discounts before
    charging (e.g. input_tokens=316) -- billing was never wrong, only the
    echoed usage was stale. Mutates response_data in place; never raises.
    """
    try:
        usage = response_data.get('usage') if isinstance(response_data, dict) else None
        in_t, out_t = cost_info.get('input_tokens'), cost_info.get('output_tokens')
        if not isinstance(usage, dict) or not isinstance(in_t, int) or not isinstance(out_t, int):
            return
        usage['prompt_tokens'], usage['completion_tokens'], usage['total_tokens'] = in_t, out_t, in_t + out_t
    except Exception:
        pass
