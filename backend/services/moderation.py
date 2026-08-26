"""Phase J — content safety. The ONE pre-flight screen every chat path runs.

Before this module the product inspected nothing: a user could ask for
anything and no rule, log, event or alert existed anywhere in the backend.

ONE CHOKE POINT, NOT SIX. There are exactly four chat HTTP entry points
(grepped 2026-08-23): /v1/chat/completions (chat.py), /v1/smart-chat
(chat_smart.py), /v1/chat/with-file (chat_web.py), /v1/compare
(chat_compare.py). chat_stream.py registers no route -- its _chat_stream /
_smart_chat_stream are helpers those routes call *after* their own gates,
so covering the four routes covers streaming too. All four already awaited
one shared gate before opening a reservation, ``_chat_disabled_response``;
that gate is now reached through chat_web.py::_chat_preflight, which is the
single place :func:`moderation_preflight` is called from. Every line of
detection logic lives under this package, because a detector copy-pasted
into four route bodies is how one ends up missed, and that one is the
bypass.

POSITION. _chat_preflight runs BEFORE the free-tier gate and before
``BillingService.reserve()`` -- it is the first thing a route does after
resolving the user. Blocking after a reservation is opened -- worse, after
the upstream call -- spends our money to protect nothing. Note this is why
services/context_injection.py::get_injection_messages is NOT the choke
point even though it is the one helper all six chat call sites share: every
one of those six calls happens AFTER that route's reserve().

FAIL-SAFE = ALLOW + FLAG + ALERT (owner decision). :func:`screen_request`
NEVER raises. Any internal failure -- DB down, Redis down, a rule whose
regex blows the time budget, a model timeout -- returns an *allow* verdict
with ``failed=True``, writes a ``moderation_event`` row and fires a Telegram
alert. A broken detector must never lock a paying user out of chat; it must
instead be loud.

TWO LAYERS, THE SECOND SAMPLED. (1) Deterministic rules
(``moderation_rule``, admin-editable, Persian first) matched against three
normalized forms -- :func:`normalize_variants` -- pure CPU on a bounded
prefix. (2) A model pass for *context*, run ONLY when layer 1 hits or on a
random sample whose rate is an admin setting (default 0): a model call on
every message would roughly double the cost of every request, breaking the
one product rule that never reopens (هیچ درخواستی نباید ضررده باشد). The
model may DOWNGRADE a block to a flag (benign context) but can never block
on its own, so a block always has a nameable rule behind it.

HONEST LABELLING. A blocked user is told in Persian that the request was
blocked for breaking the rules; the model is never made to pretend it does
not know how (the session-7 web-search mistake). The message names neither
the matched rule (harder to game) nor any model/provider/route (users never
see routing). Validating an admin-supplied regex before storing it lives
with the write path, in backend/admin_moderation.py.

FILE LAYOUT (house 500-line cap; this file was 563). The detection logic is
split by concern across three modules and this one is the facade:

  services/moderation_rules.py  pure CPU -- normalization, Rule/Config/
                                Verdict, the compiled patterns, the sweep.
  services/moderation_store.py  everything with an I/O dependency -- config
                                load/cache, event rows, restriction key,
                                Telegram alert, the optional model pass.
  services/moderation.py        this file: screen_request /
                                moderation_preflight, plus the re-exports
                                that keep `from services.moderation import
                                X` working for admin_moderation.py, the
                                chat choke point and the tests.
"""
from __future__ import annotations

import logging
import random
from typing import Any

from fastapi.responses import JSONResponse

from i18n import err_openai
from services.moderation_rules import (  # noqa: F401 -- re-exported facade
    BLOCK_MESSAGE_EN,
    BLOCK_MESSAGE_FA,
    block_message_en_for_category,
    DECISIONS,
    MAX_SCAN_CHARS,
    MAX_SNIPPET_CHARS,
    REGEX_BUDGET_SECONDS,
    SELF_HARM_MESSAGE_FA,
    SEVERITIES,
    Config,
    Rule,
    Verdict,
    _ALLOW,
    _BudgetExceeded,
    _last_user_text,
    _match,
    _rank,
    block_message_for_category,
    normalize_variants,
)
from services.moderation_store import (  # noqa: F401 -- re-exported facade
    RESTRICT_TTL_SECONDS,
    _is_restricted,
    _load_config,
    _model_review,
    _record_event,
    _send_alert,
    invalidate_config_cache,
    set_restricted,
)

logger = logging.getLogger('moderation')

# ── The choke point ───────────────────────────────────────────────────────

async def screen_request(uid: int, messages: Any,
                         conversation_id: int | None = None) -> Verdict:
    """Screen the newest user turn. NEVER raises -- see the module docstring.

    ``conversation_id`` is stored because the frozen admin API exposes it,
    but every call site passes ``None`` today: ``ChatRequest`` carries no
    conversation id, so at pre-flight time there is nothing truthful to
    record, and it is not filled in with a guess."""
    try:
        cfg = await _load_config()
        if not cfg.enabled or (not cfg.rules and cfg.model_sample_rate <= 0):
            return _ALLOW
        text = _last_user_text(messages)
        if not text.strip():
            return _ALLOW

        hit = _match(text, cfg.rules)

        if hit is None:
            # Sampled context pass on otherwise-clean text. Never blocks: a
            # block always needs a deterministic rule behind it.
            if cfg.model and cfg.model_sample_rate > 0 \
                    and random.random() < cfg.model_sample_rate:
                if await _model_review(text, cfg.model) in ('block', 'flag'):
                    v = Verdict(decision='flag', category='model_sample',
                                severity='low',
                                snippet=normalize_variants(text)[0][:MAX_SNIPPET_CHARS])
                    await _record_event(uid, conversation_id, v, cfg.retention_days)
                    await _send_alert(uid, v)
                    return v
            return _ALLOW

        rule, snippet = hit
        restricted = await _is_restricted(uid)
        threshold = 'low' if restricted else cfg.block_severity
        decision = 'block' if _rank(rule.severity) >= _rank(threshold) else 'flag'

        if cfg.model and cfg.model_on_hit and decision == 'block' and not restricted:
            if await _model_review(text, cfg.model) == 'allow':
                decision = 'flag'

        # Both languages resolved at the same point, from the same category.
        # Setting only message_fa here would have left every block falling
        # back to the generic English line and silently losing the
        # per-category wording the Persian side keeps.
        v = Verdict(decision=decision, category=rule.category,
                    severity=rule.severity, rule_id=rule.id, snippet=snippet,
                    message_fa=block_message_for_category(rule.category)
                    if decision == 'block' else None,
                    message_en=block_message_en_for_category(rule.category)
                    if decision == 'block' else None)
        await _record_event(uid, conversation_id, v, cfg.retention_days)
        await _send_alert(uid, v)
        return v

    except Exception as e:
        # Fail-safe (owner decision): the request PASSES, but it is recorded
        # and it is loud. A detector failure must never lock a real user out.
        logger.warning('moderation: screen failed uid=%s: %s', uid, e)
        v = Verdict(decision='allow', category='detector_failure',
                    severity='high', failed=True, detail=str(e))
        try:
            await _record_event(uid, conversation_id, v)
            await _send_alert(uid, v)
        except Exception:
            pass
        return v


async def moderation_preflight(uid: int, messages: Any,
                               conversation_id: int | None = None
                               ) -> JSONResponse | None:
    """What the four chat routes call. ``None`` means "carry on unchanged";
    a 403 carrying :data:`BLOCK_MESSAGE_FA` means a real block."""
    verdict = await screen_request(uid, messages, conversation_id)
    if verdict.decision != 'block':
        return None
    # The one refusal a blocked user actually reads. `message` is unchanged;
    # `message_en` is the sibling every other /v1/* refusal now carries
    # (backend/i18n.py::err_openai). Built here rather than through that
    # helper because the message is per-category and already resolved.
    return err_openai(
        verdict.message_fa or BLOCK_MESSAGE_FA,
        verdict.message_en or BLOCK_MESSAGE_EN,
        403,
        code='content_blocked',
        err_type='content_policy',
    )
