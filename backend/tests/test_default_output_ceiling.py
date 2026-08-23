"""DEFAULT_MAX_OUTPUT_TOKENS must leave room for hidden reasoning tokens.

The chat UI never sends max_tokens (frontend/app/chat/page.tsx builds the body
from model/messages/stream only), so resolve_max_tokens' default IS the ceiling
every web user gets. It was 4096.

On reasoning-capable models max_tokens covers the model's hidden thinking
budget as well as the visible answer, so 4096 was spent mostly on tokens the
user never sees. Measured live on this box, same prompt (a 10-chapter Persian
Python guide), only the ceiling varied:

  model                       cap    visible   billed ct   finish_reason
  sanjab/gemini-3-flash       4096    5039ch      1581     max_tokens  ← cut
  sanjab/gemini-3-flash       8192    6891ch      2186     stop
  sanjab/gemini-3-flash      16384    8416ch      2597     stop
  sanjab/gemini-3.1-pro-low   4096     553ch       162     max_tokens  ← cut
  sanjab/gemini-3.1-pro-low   8192    6498ch      1976     stop
  sanjab/gemini-3.1-pro-low  16384    7762ch      2368     stop

The 553-char case cost 10,895 toman for an answer cut mid-sentence, and
sanjab/tencent-hy3 at 4096 returned finish_reason=length with completion_tokens
=4096 and ZERO characters of content -- the user paid in full for nothing.

Raising the ceiling does not multiply cost: the model still stops when it is
done, and only requests that genuinely wanted more output produce more. In the
run above, gemini-3-flash cost LESS at 16384 (8,450) than at 8192 (12,334),
because cost tracks tokens actually generated, not the ceiling.
"""
import importlib

import pytest


class TestDefaultOutputCeiling:
    def test_default_leaves_room_for_reasoning_tokens(self):
        import services.token_budget as tb
        assert tb.DEFAULT_MAX_OUTPUT_TOKENS >= 8192, (
            f'DEFAULT_MAX_OUTPUT_TOKENS={tb.DEFAULT_MAX_OUTPUT_TOKENS}: measured '
            'insufficient -- both Gemini models were cut (finish_reason=max_tokens) '
            'at 4096 and only finished at 8192+'
        )

    def test_default_is_env_overridable(self, monkeypatch):
        """Operators must be able to tune this without a rebuild."""
        monkeypatch.setenv('DEFAULT_MAX_OUTPUT_TOKENS', '2048')
        import services.token_budget as tb
        importlib.reload(tb)
        try:
            assert tb.DEFAULT_MAX_OUTPUT_TOKENS == 2048
        finally:
            monkeypatch.delenv('DEFAULT_MAX_OUTPUT_TOKENS', raising=False)
            importlib.reload(tb)

    @pytest.mark.asyncio
    async def test_client_value_is_still_never_raised(self):
        """A client that asks for less must keep getting less -- the ceiling is
        a default for the absent case, never an override."""
        import services.token_budget as tb
        assert await tb.resolve_max_tokens('sanjab/whatever', 512) == 512

    @pytest.mark.asyncio
    async def test_absent_value_gets_the_default(self):
        import services.token_budget as tb
        for absent in (None, 0, -1, False, 'nonsense'):
            assert await tb.resolve_max_tokens('sanjab/whatever', absent) == \
                tb.DEFAULT_MAX_OUTPUT_TOKENS, f'for requested={absent!r}'
