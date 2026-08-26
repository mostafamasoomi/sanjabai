"""The document generator's refusal messages, in both languages.

Split out of document_generator.py, which crossed the project's 500-line cap
when its 25 refusal sites were made bilingual. DATA ONLY -- no function moved.
That distinction is deliberate: tests/test_document_generator_gates.py patches
names ON the document_generator module (`_get_user_id`, `get_site_flag`,
`screen_request`, `check_and_consume`, `_user_quota_check`), so relocating a
function out of it would silently escape those patches. Moving constants
cannot, because document_generator re-imports them and
`document_generator._CHAT_DISABLED_MESSAGE` still resolves.

Each pair is byte-identical Persian plus its English sibling; several English
strings are reused verbatim from the already-converted identical Persian in
chat.py / chat_web.py / images.py so one refusal reads the same wherever the
API raises it.
"""
from __future__ import annotations

_MODEL_NOT_ALLOWED_MESSAGE = 'مدل انتخابی پشتیبانی نمیشود'
_MODEL_NOT_ALLOWED_MESSAGE_EN = 'The selected model is not supported.'
_CHAT_DISABLED_MESSAGE = 'گفتگو موقتاً در دسترس نیست'
# Byte-for-byte the same English chat_web._chat_disabled_response() returns.
_CHAT_DISABLED_MESSAGE_EN = 'Chat is temporarily unavailable.'
_FREE_TIER_MESSAGE = (
    'سقف پیام رایگان این مدل برای اکنون پر شده است؛ کمی بعد دوباره تلاش کنید '
    'یا با شارژ حساب این محدودیت را برای همیشه بردارید.'
)
_FREE_TIER_MESSAGE_EN = (
    'The free-message limit for this model has been reached for now; try '
    'again shortly, or top up your account to remove this limit for good.'
)
_QUOTA_MESSAGE = (
    'سقف پیام بستهٔ شما برای این بازه پر شده است؛ کمی بعد دوباره تلاش کنید '
    'یا بستهٔ بزرگ‌تری تهیه کنید.'
)
_QUOTA_MESSAGE_EN = (
    'Your package message limit for this period has been reached; try '
    'again shortly, or get a bigger package.'
)
_INSUFFICIENT_BALANCE_MESSAGE = 'موجودی کیف پول شما کافی نیست. لطفاً حساب خود را شارژ کنید.'
# Byte-for-byte the same English every other InsufficientBalanceError site
# uses (chat.py, chat_web.py, chat_smart.py, chat_compare.py, images.py).
_INSUFFICIENT_BALANCE_MESSAGE_EN = 'Your wallet balance is not enough. Please top up your account.'
_GATEWAY_ERROR_MESSAGE = 'سرویس موقتاً در دسترس نیست'
# Byte-for-byte the same English chat.py/chat_web.py/images.py's gateway
# err() sites use for this Persian text.
_GATEWAY_ERROR_MESSAGE_EN = 'The service is temporarily unavailable.'


# ── Model resolution/validation ───────────────────────────────────
#
# Late-bound `import chat` inside each function (not at module scope, and
# never `from chat import X`) -- same reasoning as task_execution.py's
# module docstring: chat.py's model-resolution names
# (`_resolve_public_model`, `_safe_default_model`, `_is_model_allowed`) are
# what the test suite monkeypatches directly on the `chat` module, and a
# module-level import would both risk a chat.py <-> document_generator.py
# load-order issue and silently defeat that monkeypatching.
