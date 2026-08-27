"""Which SELECTION STRATEGY /v1/smart-chat runs for one request, i.e. the
`X-Smart-Mode` request header, split out of chat_smart.py (500-line cap;
chat_smart.py owns the request/response cycle, this file owns nothing but
"which of the three selectors picks the model, and what actually ran").

── THE HEADER ─────────────────────────────────────────────────────────────
  absent / `auto`  -> smart_router.select_by_rules (today's behaviour)
  `router`         -> smart_router_llm.llm_route, then the rules
  `combo:<id>`     -> smart_router.select_for_combo, then the rules
  anything else    -> `auto`

MALFORMED IS NEVER AN ERROR. `combo:abc`, `combo:-1`, `combo:` , an empty
value, a 40-digit id, or plain garbage all degrade to `auto` -- this header
is attacker-controllable and unauthenticated in shape, so the only safe
direction to fail in is the default path that every request already takes.
A 400 here would let a stray proxy header take Smart Mode down for a user.

`X-Smart-Mode: router` IS the user's explicit opt-in -- gate 1 of the three
gates services/smart_router_llm.py documents. `auto` and `combo:*` must
therefore never reach `llm_route`: it spends real money on every message it
runs for, and nobody asked for that spend on the default path.

WHAT ACTUALLY RAN is what `select_for_mode` returns as its second value,
never what was asked for: `router` and `combo:<id>` both fall back to the
rules on None (the documented "cannot serve this" answer of both selectors,
neither of which ever raises), and a fallback reports `auto`. A client that
was told `combo:7` when the combo was disabled and the rules picked would
have no way to know its combo is dead.

IMPORT SHAPE, and it is load-bearing -- see chat_smart.py's docstring for
the full cycle. `services.smart_router` is imported as a MODULE here for
the same reason as there. `services.smart_router_llm` is not imported at
module scope AT ALL: it does `from services.smart_router import Candidate`,
and the chain `import services.smart_router` -> `import chat` -> chat.py's
last line -> chat_smart -> here -> smart_router_llm would hit a
services.smart_router that is only initialised as far as its own
`import chat` line, i.e. before `Candidate` is bound -> ImportError at
import time, only in the router-first order. So it is imported INSIDE
`_llm_route`, by which point every module involved has finished executing.
Both orders are covered by tests/test_smart_chat_modes.py.
"""
from __future__ import annotations

import logging
import re

import services.smart_router as smart_router  # module import on purpose -- see docstring

logger = logging.getLogger('chat')  # keep all chat_*.py logs under the pre-split 'chat' logger name

MODE_AUTO = 'auto'
MODE_ROUTER = 'router'
MODE_COMBO = 'combo'

_COMBO_PREFIX = 'combo:'

# ASCII digits only, 1..9 leading, at most 9 of them. Three separate jobs:
#   - `\d` / str.isdigit() would accept Persian and Arabic-Indic digits,
#     which int() happily converts ('۱۲' -> 12) -- a combo id must be the
#     literal ASCII number the client was given, not a lookalike;
#   - a leading 0 ('combo:007') is not the shape combos.py hands out;
#   - 9 digits caps the value at 999,999,999, inside int4: user_model_combo.
#     id is a SERIAL (migration 0050), so a longer number cannot name a real
#     combo and must not be sent to the driver as a bind parameter.
# `combo:-1` fails on the leading '-' and `combo:abc` on the letters; both
# land on MODE_AUTO like every other malformed value.
_COMBO_ID_RE = re.compile(r'[1-9][0-9]{0,8}')


def parse_mode(raw: str | None) -> tuple[str, int | None]:
    """The `X-Smart-Mode` request header turned into `(mode, combo_id)`.

    `mode` is one of MODE_AUTO / MODE_ROUTER / MODE_COMBO and `combo_id` is
    a positive int for MODE_COMBO and None otherwise. Never raises, never
    rejects: anything this function does not recognise is MODE_AUTO.

    Matching is case-insensitive on the whole value (`Combo:7`, `ROUTER`)
    because a header value that only differs in case still names an
    unambiguous mode, and degrading it would be a confusing no-op for the
    caller rather than a safety win.
    """
    if not raw:
        return (MODE_AUTO, None)
    value = raw.strip().lower()
    if value == MODE_ROUTER:
        return (MODE_ROUTER, None)
    if value.startswith(_COMBO_PREFIX):
        if _COMBO_ID_RE.fullmatch(value[len(_COMBO_PREFIX):]):
            return (MODE_COMBO, int(value[len(_COMBO_PREFIX):]))
    return (MODE_AUTO, None)


def mode_label(mode: str, combo_id: int | None) -> str:
    """The wire form of a mode, i.e. what the `X-Smart-Mode` RESPONSE header
    carries: `auto`, `router` or `combo:<id>`."""
    if mode == MODE_COMBO and combo_id is not None:
        return f'{_COMBO_PREFIX}{combo_id}'
    return MODE_ROUTER if mode == MODE_ROUTER else MODE_AUTO


async def _llm_route(message: str, pool: list, balance: int, *, uid: int):
    """`smart_router_llm.llm_route`, imported at CALL TIME (see docstring).

    `uid=uid` is not optional in practice: without it the router's own
    upstream call writes no usage_event (usage_events.user_id is NOT NULL,
    so `_meter` skips the row), and an optional feature that spends money on
    every message would then be invisible in the profit report.

    The try/except covers the import itself only -- `llm_route` is
    documented never to raise and returns None on every doubt -- so that a
    packaging accident cannot turn an optional selector into a failed chat
    request.
    """
    try:
        import services.smart_router_llm as smart_router_llm  # noqa: PLC0415 -- deliberate, see docstring
        return await smart_router_llm.llm_route(message, pool, balance, uid=uid)
    except Exception as e:
        logger.warning(f"llm_route unavailable uid={uid}, falling back to rules: {e}")
        return None


async def select_for_mode(
    mode: str,
    combo_id: int | None,
    *,
    uid: int,
    message: str,
    category: str,
    balance: int,
    pool: list,
) -> tuple[smart_router.Candidate | None, str]:
    """Run the requested selector, then `select_by_rules` if it declined.

    Returns `(pick, used)` where `used` is the mode that ACTUALLY produced
    the pick -- `auto` whenever the rules produced it, including after a
    fallback. `pick` is None only when the rules themselves have nothing,
    which is the empty-pool case the caller answers with its honest 503.

    Never raises: both optional selectors swallow their own errors and
    return None, and `select_by_rules` does the same.
    """
    pick = None
    if mode == MODE_ROUTER:
        # Gate 1 of services/smart_router_llm.py's three gates -- the user's
        # explicit opt-in -- is exactly this branch. Gates 2 (site flag) and
        # 3 (balance floor) are checked inside llm_route.
        pick = await _llm_route(message, pool, balance, uid=uid)
    elif mode == MODE_COMBO and combo_id is not None:
        # Ownership is enforced inside select_for_combo's SQL against THIS
        # uid -- the authenticated one from the session/API key, never
        # anything the client sent. A combo belonging to someone else comes
        # back as None and falls through to the rules below.
        pick = await smart_router.select_for_combo(uid, combo_id, pool)

    if pick is not None:
        return (pick, mode_label(mode, combo_id))
    if mode != MODE_AUTO:
        logger.info(
            f"smart mode {mode_label(mode, combo_id)} declined uid={uid}, "
            f"falling back to the rules"
        )
    return (smart_router.select_by_rules(category, balance, pool), MODE_AUTO)
