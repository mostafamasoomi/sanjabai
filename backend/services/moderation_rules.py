"""Phase J — content safety, layer 1: the pure-CPU rule engine.

Split out of services/moderation.py (563 lines, house cap 500) exactly the
way model_health.py / model_health_policy.py / model_health_api.py were
split: by concern, not by line count. This half is everything that decides
*what the text says* -- normalization, the compiled rules, the match sweep
and the value types. It touches no database, no Redis, no network and no
environment, so it is testable as a pure function and it cannot be the
thing that fails on the chat hot path.

The other half is services/moderation_store.py (everything with an I/O
dependency); services/moderation.py keeps the entry point,
:func:`~services.moderation.screen_request`, and re-exports both halves so
every existing importer -- the chat choke point, admin_moderation.py and
tests/test_moderation.py -- keeps importing from `services.moderation`.

NOTE for tests: REGEX_BUDGET_SECONDS is read by :func:`_match` in THIS
module, so a test that shortens the budget must patch
``services.moderation_rules.REGEX_BUDGET_SECONDS``; patching the re-export
on ``services.moderation`` rebinds a different name and would silently not
take effect.
"""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

logger = logging.getLogger('moderation')

# Only ever scan a bounded prefix: unbounded input into an admin-authored
# regex is the cheapest self-inflicted DoS there is.
MAX_SCAN_CHARS = 4000
# The most sensitive data this product stores. Never the whole message --
# only the window around what matched. Enforced here AND in _record_event.
MAX_SNIPPET_CHARS = 120
_SNIPPET_PAD = 40
# Wall-clock ceiling for the rule sweep. Python's `re` has no per-match
# timeout, so this is checked between rules; with MAX_SCAN_CHARS and
# admin_moderation.validate_pattern's ReDoS smoke test it is the practical
# mitigation, and blowing it lands on the fail-safe path.
REGEX_BUDGET_SECONDS = 0.05

SEVERITIES = ('low', 'medium', 'high', 'critical')
DECISIONS = ('allow', 'flag', 'block')

# The user-facing text for a real block: explicit, Persian, no rule name,
# no model/provider/route name.
BLOCK_MESSAGE_FA = (
    'این درخواست به دلیل مغایرت با قوانین استفاده از سرویس مسدود شد و برای '
    'شما پردازش نشد. اگر فکر می‌کنید اشتباهی رخ داده، با پشتیبانی تماس بگیرید.'
)

class _BudgetExceeded(Exception):
    """Rule sweep ran past REGEX_BUDGET_SECONDS -- a detector failure, i.e.
    allow + flag + alert, never a silent pass."""

# ── Normalization ─────────────────────────────────────────────────────────
# Zero-width/bidi marks + tatweel are invisible, so a user can write "س‌ک‌س"
# that renders exactly like "سکس" and matches neither.
_INVISIBLE = dict.fromkeys(ord(c) for c in '​‌‍‎‏⁠﻿ـ')
# Harakat (U+064B..U+0652), combining madda/hamza above (U+0653..U+0655) and
# superscript alef (U+0670): optional marks a user can sprinkle anywhere,
# plus what NFKC leaves behind after decomposing forms like ۀ.
_HARAKAT: dict[int, None] = dict.fromkeys(range(0x064B, 0x0656))
_HARAKAT[0x0670] = None
# Arabic vs Persian letter shapes that render (near-)identically.
_LETTER_FOLD = str.maketrans({
    'ي': 'ی', 'ى': 'ی', 'ئ': 'ی', 'ﻱ': 'ی', 'ﻲ': 'ی',
    'ك': 'ک', 'ﻙ': 'ک', 'ﻚ': 'ک',
    'ة': 'ه', 'ۀ': 'ه', 'ۃ': 'ه',
    'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ٲ': 'ا', 'ٳ': 'ا',
    'ؤ': 'و', 'ٶ': 'و', 'ٹ': 'ت', 'ڈ': 'د', 'ڑ': 'ر',
})
# Arabic-Indic (U+0660..) and Persian (U+06F0..) digits -> ASCII.
_DIGIT_FOLD = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
# Letters people substitute digits/symbols for, in finglish and in English.
_LEET_FOLD = str.maketrans({
    '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '8': 'b',
    '@': 'a', '$': 's', '!': 'i', '|': 'i',
})
_NON_WORD = re.compile(r'[^0-9a-z؀-ۿ]+')


def normalize_variants(text: str) -> tuple[str, str, str]:
    """The three forms every rule is matched against: ``(norm, leet, compact)``.

    ``norm`` is NFKC with invisibles/harakat stripped, Arabic letter shapes
    folded to their Persian twin, Arabic-Indic and Persian digits folded to
    ASCII, lowercased -- what a normal Persian rule targets. ``leet`` folds
    digits/symbols back to the letters they stand in for (``s3x`` -> ``sex``,
    ``k1r`` -> ``kir``). ``compact`` strips every separator, so ``س.ک.س`` and
    ``s e x`` collapse onto one string; it is deliberately the last resort,
    since it also joins unrelated words -- which is why a hit alone only
    *flags* and a *block* additionally needs the rule's severity.
    """
    if not text:
        return '', '', ''
    s = unicodedata.normalize('NFKC', text[:MAX_SCAN_CHARS])
    s = s.translate(_INVISIBLE).translate(_HARAKAT)
    s = s.translate(_LETTER_FOLD).translate(_DIGIT_FOLD)
    norm = s.lower()
    leet = norm.translate(_LEET_FOLD)
    return norm, leet, _NON_WORD.sub('', leet)


@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern | None:
    """Compile once per distinct pattern. ``None`` for one that no longer
    compiles (validated at store time, but a row can be edited in psql) --
    a broken rule is skipped, never fatal."""
    try:
        return re.compile(pattern)
    except re.error as e:
        logger.warning('moderation: uncompilable rule pattern %r: %s', pattern, e)
        return None

# ── Value types ───────────────────────────────────────────────────────────
# `Config` is built by services/moderation_store.py::_load_config (one
# Redis-cached read per request) but defined here, with `Rule`, because
# both are plain data the matcher below consumes -- keeping them in the
# I/O module would make this one import it and invert the dependency.

@dataclass(frozen=True)
class Rule:
    id: int
    pattern: str
    category: str
    severity: str
    enabled: bool
    notes: str = ''


@dataclass(frozen=True)
class Config:
    """Everything screen_request needs, as one cached blob, so a harmless
    message costs exactly one local Redis GET and nothing else."""
    enabled: bool = True
    rules: tuple[Rule, ...] = ()
    block_severity: str = 'high'
    model_sample_rate: float = 0.0
    model_on_hit: bool = True
    model: str = ''
    retention_days: int = 90


@dataclass
class Verdict:
    decision: str = 'allow'          # allow | flag | block
    category: str | None = None
    severity: str | None = None
    rule_id: int | None = None
    snippet: str = ''
    failed: bool = False
    message_fa: str | None = None
    detail: str = ''                 # internal only; never sent to a user


_ALLOW = Verdict()

# ── Text extraction / matching ────────────────────────────────────────────

def _last_user_text(messages: Any) -> str:
    """The newest user turn, as plain text; never mutates the input. Accepts
    both call-site shapes: a list of message dicts (chat / smart / compare)
    and the JSON string /v1/chat/with-file gets as a Form field. Multimodal
    content is reduced to its text parts. NOTE: the *file* attached to
    /v1/chat/with-file is not screened, only the message."""
    if isinstance(messages, str):
        try:
            messages = json.loads(messages)
        except Exception:
            return messages[:MAX_SCAN_CHARS]
    if not isinstance(messages, list):
        return ''
    for m in reversed(messages):
        if not isinstance(m, dict) or m.get('role') != 'user':
            continue
        c = m.get('content')
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return ' '.join(p.get('text', '') for p in c
                            if isinstance(p, dict) and isinstance(p.get('text'), str))
        return ''
    return ''


def _match(text: str, rules: tuple[Rule, ...]) -> tuple[Rule, str] | None:
    """First matching enabled rule plus the window it matched in. Raises
    :class:`_BudgetExceeded` if the sweep runs long (fail-safe contract)."""
    if not rules:
        return None
    variants = normalize_variants(text)
    deadline = time.monotonic() + REGEX_BUDGET_SECONDS
    for rule in rules:
        if not rule.enabled:
            continue
        rx = _compile(rule.pattern)
        if rx is None:
            continue
        for form in variants:
            if not form:
                continue
            m = rx.search(form)
            if m:
                lo = max(0, m.start() - _SNIPPET_PAD)
                hi = min(len(form), m.end() + _SNIPPET_PAD)
                return rule, form[lo:hi][:MAX_SNIPPET_CHARS]
        if time.monotonic() > deadline:
            raise _BudgetExceeded(f'rule sweep exceeded budget at rule {rule.id}')
    return None


def _rank(severity: str) -> int:
    try:
        return SEVERITIES.index(severity)
    except ValueError:
        return SEVERITIES.index('medium')
