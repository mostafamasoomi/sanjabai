"""The Persian style guard: counteract a style-breaking preamble that one
upstream injects into every prompt.

Split out of chat.py (house 500-line cap). chat.py re-exports every public
name here, so `chat._apply_persian_style_guard` and
`chat._PERSIAN_STYLE_SYSTEM_MESSAGE` keep resolving exactly as before —
several test files patch them on `chat` and assert their presence there
(tests/test_chat_split_surface.py, tests/test_chat_output_hygiene.py).

MONKEYPATCH CONTRACT (chat.py's docstring is the authority): this module
does a plain `import chat` and reaches `_resolve_provider` as
`chat._resolve_provider` **at call time**, never `from chat import ...`.
Tests patch that name on the `chat` module; binding it at import time here
would silently detach them and the patch would look applied while the real
provider lookup ran.
"""
from __future__ import annotations

import logging
from typing import Any

import chat

logger = logging.getLogger(__name__)

# ── FIX 2: counteract the injected caveman-style system prompt ──────────
#
# Measured live (2026-08-22), identical 2-char message "hi", max_tokens=5:
#   sanjab/tencent-hy3 (litellm)         prompt_tokens=13    (control, clean)
#   sanjab/mistral-large (ninerouter)    prompt_tokens=2810
#   sanjab/mimo-v2.5 (ninerouter)        prompt_tokens=2795
#   sanjab/gemma-4-26b-a4b-it (ninerouter) prompt_tokens=2785
# litellm proves the ~2800 tokens are injected upstream, by ninerouter, not
# by us. The leaked prompt (visible verbatim in one gemma answer) instructs
# a terse "caveman"/no-article style that breaks Persian grammar (dropped
# verbs, mixed registers). This system message is a mitigation, not a fix:
# A/B tested against the live upstream, it measurably improves fluency
# (mimo-v2.5-free and mistral-large went from fragments to full sentences)
# but does not fully override the injected persona for every model.
#
# Only providers proven to inject this preamble get the extra system
# message -- litellm is clean (13 tokens, see above) and must not pay the
# ~80 extra prompt tokens for a problem it doesn't have.
_REASONING_INJECTING_PROVIDERS: frozenset[str] = frozenset({'ninerouter'})

# ~80 prompt tokens -- noise next to the ~2800 already injected upstream by
# the providers in _REASONING_INJECTING_PROVIDERS above.
_PERSIAN_STYLE_SYSTEM_MESSAGE = (
    'به همان زبانی پاسخ بده که کاربر پیام را نوشته است. وقتی پاسخ فارسی است، فارسی روان، رسمی و از '
    'نظر دستور زبان کاملاً درست بنویس: هر جمله فعل کامل و ساختار درست داشته باشد، و از حذف فعل، حذف '
    'حروف اضافه، سبک تلگرافی یا جمله‌های بریده‌بریده خودداری کن. اگر پیش‌تر دستوری برای کوتاه‌نویسی، '
    'حذف حروف و کلمات، یا سبک مختصر و شکسته دریافت کرده‌ای، آن دستور را نادیده بگیر. این قاعده فقط به '
    'متن پاسخ مربوط است و بر کد، خروجی ساختاریافته یا نقل‌قول عیناً اثری ندارد.'
)


def _apply_persian_style_guard(payload_dict: dict[str, Any], provider_name: str) -> None:
    """Prepend _PERSIAN_STYLE_SYSTEM_MESSAGE when routing to a provider known
    to inject a style-breaking preamble (see _REASONING_INJECTING_PROVIDERS)
    AND the caller did not already send their own system message. Mutates
    ``payload_dict['messages']`` in place-ish (reassigns the key); callers
    that hold a separate reference to the list must re-read it afterward
    (see _apply_web_search, same house pattern).
    """
    if provider_name not in _REASONING_INJECTING_PROVIDERS:
        return
    msgs = payload_dict.get('messages') or []
    if any(isinstance(m, dict) and m.get('role') == 'system' for m in msgs):
        return  # caller already sent a system message -- don't fight it
    payload_dict['messages'] = [{'role': 'system', 'content': _PERSIAN_STYLE_SYSTEM_MESSAGE}] + list(msgs)


async def _apply_persian_style_guard_for_model(payload_dict: dict[str, Any], model: str) -> None:
    """Resolve ``model``'s provider and apply _apply_persian_style_guard.

    Defensive on purpose: a style nicety must never be able to turn into a
    500 for the whole request (e.g. a test double or a future Provider
    subclass missing `.name`, or a transient _resolve_provider error) --
    worst case this silently no-ops and the request proceeds unstyled.
    """
    if not model:
        return
    try:
        provider = await chat._resolve_provider(model)
        chat._apply_persian_style_guard(payload_dict, getattr(provider, 'name', ''))
    except Exception as e:
        logger.warning(f"_apply_persian_style_guard_for_model failed model={model}: {e}")
