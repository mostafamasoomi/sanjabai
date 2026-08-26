"""Guardrail: frontend copy must not contain unregistered/unverified claims.

Any user-facing marketing number (model counts, uptime %, gift/credit amounts)
must come from the claim registry (frontend/lib/claims.ts backed by the DB
`claims` table) — never hardcoded in page copy. See docs/claims-policy.md.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# Directories that hold user-facing source (skip build output / deps).
SCAN_DIRS = ["app", "components", "lib"]
# claims.ts is the registry itself; it is allowed to define copy.
#
# content/constants.ts's MIN_TOPUP_LABEL_FA/EN ('10,000 Toman') trips the
# gift/credit-amount pattern below, but it is not a gift claim -- it is the
# wallet's actual minimum top-up requirement, sourced from and documented
# against app/wallet/page.tsx's MIN_TOPUP constant (see that file's own
# comment). The forbidden pattern exists to catch an unverified "you get
# 10,000 Toman free" marketing claim; a required minimum is the opposite
# claim and happens to share the same number.
ALLOWLIST = {"lib/claims.ts", "components/landing/content/constants.ts"}

#: A digit run in either script, optionally with a decimal separator.
_NUM = r"[\d۰-۹]{1,3}(?:[.,٫][\d۰-۹]+)?"
#: An uptime word in either language.
_UPTIME_WORD = r"uptime|آپتایم|آپ\s*تایم"

FORBIDDEN = [
    (re.compile(r"۵۰\s*\+|(?<!\d)50\s*\+"), "unverified model-count claim (50+)"),
    # Anchored to a percent sign — a bare "99[.,]9|۹۹[.,]۹" also matches any
    # coincidental occurrence of that digit sequence in unrelated numeric
    # data, e.g. SVG path coordinates in components/ui/Icon.tsx.
    (re.compile(r"99[.,]9\s*%|۹۹[.,]۹\s*(%|٪)"), "unverified uptime percentage (99.9%)"),
    # An uptime FIGURE hardcoded into copy, in either word order. The earlier
    # version of this rule matched the bare word `uptime` anywhere in a source
    # file, which is not a claim: it fired on the status page's `uptime24h`
    # field name and its `uptimePercent()` helper, neither of which asserts
    # anything — that page renders whatever GET /status/summary reports, which
    # is precisely the server-authoritative sourcing the product contract
    # demands. What must stay forbidden is a *number* presented as uptime
    # without going through the claim registry, so the word now has to appear
    # next to a literal percentage before it counts.
    (
        re.compile(rf"(?:{_UPTIME_WORD})[^\n]{{0,60}}?{_NUM}\s*[%٪]"
                   rf"|{_NUM}\s*[%٪][^\n]{{0,60}}?(?:{_UPTIME_WORD})",
                   re.IGNORECASE),
        "hardcoded uptime percentage in copy",
    ),
    (
        re.compile(r"(۱۰[،,]?۰۰۰|10[,]?000)\s*(تومان|toman)", re.IGNORECASE),
        "unverified gift/credit amount (10,000 Toman)",
    ),
]


class _ModelCountPattern:
    """Matches a bare, hardcoded model-count literal — e.g. ``۲۳ مدل``,
    ``25 models``, ``27 AI models``, ``23 advanced models`` — the exact bug
    class fixed in 7af1293 ("23 models" hardcoded in 8 landing files, drifting
    from the live catalog). See docs/product-contract.md §4: model-count
    claims require a live catalog query.

    Deliberately narrower than "any digit next to the word model(s)/مدل":

    - A hyphenated or comma/٬-grouped number is not matched at its start
      (``(?<!-)``/``(?<![,٬])``) so this can't fire on half of a larger
      figure like a thousands-grouped count.
    - Up to two ordinary words (letters only, no digits) may sit between the
      number and model(s)/مدل, so it still catches "23 advanced models" /
      "27 AI models" — an adjective doesn't launder the claim — without
      matching arbitrary unrelated digits+prose that merely mentions "model"
      within two words of some number.
    - The second number of a written-out range ("2 to 3 models", "۲ تا ۳
        مدل") is excluded via ``_RANGE_PREFIX``: that phrasing instructs the
      user to pick N of M items (see StepModelSelect.strings.ts) — it is not
      a claim about the catalog's total size, so unlike the fixed bug it
      does not drift when the catalog changes.
    - The correct, live-sourced replacement pattern this bug was fixed into
      (``${faNum(count)} مدل`` / ``${count} model${count === 1 ? '' : 's'}``)
      has no literal digit before "model(s)"/"مدل" at all, so it can never
      match — nothing to special-case.
    """

    _NUMBER = r"\d{1,3}"
    _WORD = r"[^\W\d_]+"  # a plain word: letters only, any script, no digits
    _CANDIDATE = re.compile(
        rf"(?<!-)(?<![,٬])(?<!\d){_NUMBER}(?!\d)[ \t]+(?:{_WORD}[ \t]+){{0,2}}(?:models?|مدل)\b",
        re.IGNORECASE,
    )
    _RANGE_PREFIX = re.compile(rf"{_NUMBER}[ \t]+(?:to|تا)[ \t]*\Z", re.IGNORECASE)

    def finditer(self, text: str):
        for m in self._CANDIDATE.finditer(text):
            if self._RANGE_PREFIX.search(text[: m.start()]):
                continue
            yield m


FORBIDDEN.append((_ModelCountPattern(), "unverified/hardcoded model-count claim"))

#: Comments are stripped before scanning. A comment is not copy — nobody sees
#: it — and leaving them in produced pure false positives: the status page's
#: comment explaining why it *floors* a percentage instead of rounding (so it
#: never overstates availability) was itself being reported as an overclaim.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _strip_comments(text: str) -> str:
    """Blank out comments while preserving line numbering.

    Each removed character becomes a space and each newline inside a block
    comment is kept, so a violation's reported line number still points at
    the real line in the file.
    """
    def _blank(m: re.Match) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in m.group(0))

    return _LINE_COMMENT.sub(_blank, _BLOCK_COMMENT.sub(_blank, text))


def _iter_source_files():
    for d in SCAN_DIRS:
        base = FRONTEND / d
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            rel = path.relative_to(FRONTEND).as_posix()
            if rel in ALLOWLIST:
                continue
            yield rel, path


@pytest.mark.skipif(not FRONTEND.exists(), reason="frontend not present")
def test_no_unregistered_claims_in_frontend_copy():
    violations: list[str] = []
    for rel, path in _iter_source_files():
        text = _strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
        for pattern, label in FORBIDDEN:
            for m in pattern.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                violations.append(f"{rel}:{line}: {label} -> '{m.group(0)}'")
    assert not violations, "Unregistered claims found in frontend copy:\n" + "\n".join(violations)


# ── Guard the guard ──────────────────────────────────────────────────────────
# A rule that has been narrowed needs canaries, or the next narrowing turns it
# into a test that passes because it detects nothing.

def _hits(source: str) -> list[str]:
    stripped = _strip_comments(source)
    return [m.group(0) for pattern, _ in FORBIDDEN for m in pattern.finditer(stripped)]


def test_a_hardcoded_uptime_claim_is_still_caught():
    assert _hits('<p>uptime of 99.95%</p>')
    assert _hits('<p>۹۹٫۹۵٪ آپتایم</p>')
    assert _hits('<span>99.9% uptime guaranteed</span>')


def test_server_rendered_uptime_is_not_a_claim():
    """The status page reads its number from GET /status/summary."""
    assert _hits('{uptimePercent(service.uptime24h)}') == []
    assert _hits('uptime24h: number | null') == []


def test_comments_are_not_copy():
    assert _hits('// rounding turns 99.6% uptime into "۱۰۰٪"') == []
    assert _hits('/* we advertise 99.9% uptime */') == []


def test_stripping_comments_keeps_line_numbers():
    src = 'a\n/* two\nlines */\nb\n'
    assert _strip_comments(src).count("\n") == src.count("\n")


def test_the_other_rules_still_fire():
    assert _hits('بیش از ۵۰+ مدل')
    assert _hits('۱۰,۰۰۰ تومان هدیه')


def test_a_hardcoded_model_count_claim_is_still_caught():
    """Positive control for the bug fixed in 7af1293: reintroduce the exact
    literals that used to be hardcoded in Hero.strings.ts et al. and confirm
    the new rule catches them, without editing any real source file."""
    assert _hits("pillText: 'دسترسی مستقیم به ۲۳ مدل پیشرفته'")
    assert _hits("titleHighlight: '۲۳ مدل هوش مصنوعی،'")
    assert _hits("pillText: 'Direct access to 23 advanced models'")
    assert _hits("titleHighlight: '23 AI models,'")
    assert _hits("'25 models'")
    assert _hits("'27 AI models'")


def test_dynamic_live_sourced_model_count_is_not_a_claim():
    """The fixed call sites resolve the count live via faNum(count)/count — a
    template interpolation, not a literal digit — and must not trip the rule."""
    assert _hits("`دسترسی مستقیم به ${faNum(count)} مدل پیشرفته`") == []
    assert _hits("`${faNum(count)} مدل هوش مصنوعی،`") == []
    assert _hits("`Direct access to ${count} advanced model${count === 1 ? '' : 's'}`") == []
    assert _hits("`${count} AI model${count === 1 ? '' : 's'},`") == []
    assert _hits("`${n} مدل انتخاب شده`") == []
    assert _hits("`${n} model${n === '1' ? '' : 's'} selected`") == []


def test_a_pick_n_of_m_range_is_not_a_model_count_claim():
    """StepModelSelect.strings.ts asks the user to pick 2-3 favorites out of
    the catalog -- that is an instruction, not a claim about catalog size,
    and unlike the fixed bug it does not go stale when the catalog grows."""
    assert _hits('از بین مدل‌های موجود، ۲ تا ۳ مدل موردعلاقه‌تان را انتخاب کنید.') == []
    assert _hits('Pick 2-3 favorite models from what is available.') == []
