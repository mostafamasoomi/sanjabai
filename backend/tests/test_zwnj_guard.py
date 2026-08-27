"""Guard against Persian text missing the zero-width non-joiner (ZWNJ,
U+200C) before a plural ها suffix or a verb ending -- the "مدلها" vs.
"مدل‌ها" bug ("نیم‌فاصله").

THE BUG THIS CATCHES: "مدلها" reads correctly to most human eyes and passes
every linter, type checker and import check -- it is a syntactically valid
Python string -- but it is wrong Persian typography. The correct form
inserts a ZWNJ between the noun and the plural suffix ("مدل‌ها"), same as a
present-tense negative/prefix verb needs one between "می"/"نمی" and its stem
("می‌شود", not "میشود"). This session found and fixed four live instances
(admin_catalog.py, init_db.py x2, document_generator_messages.py) that had
been shipping to users since those files were written -- nothing had ever
caught them, because a missing ZWNJ produces neither a build error nor test
failure, only a visibly-wrong word a human has to notice by reading Persian.

SCOPE, DELIBERATELY NARROW: the full "می/نمی + any verb" or "any noun + ها"
space is enormous, and a naive regex over all of it produces false positives
that would block real, correctly-written Persian text -- e.g. "همیشه"
("always") contains the substring "میشه" as a pure coincidence of Persian
spelling, and "آنها"/"اینها" (they/these) are pronouns that legitimately
glue "ها" on with no ZWNJ at all. So this checks only:

  - the three verb families this session actually found broken (شود/کند/دهد,
    each with می/نمی and singular/plural endings), glued with no ZWNJ
  - the specific plural nouns this session's cleanup ticket named
    (مدل، بسته، پلن، کاربر، دسته، اسکیل، رشته) glued to ها with no ZWNJ

A pattern outside this list slipping through is a real gap, but the fix is
to add it here one confirmed instance at a time (as this session did), not
to widen the regex speculatively -- a guard that blocks legitimate copy gets
disabled, not fixed, and this project has already been bitten once by a
check that could never fail (see test_i18n_no_shadowing.py's sibling
`test_the_trap_is_real_not_theoretical`). The red/green proof for this exact
guard is in this session's handoff report, not encoded here, because it
requires temporarily reintroducing a bad string into a real source file.
"""
from __future__ import annotations

import ast
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent

_EXCLUDED_TOP = {'tests', 'migrations', '__pycache__'}

_ZWNJ = '‌'

# می/نمی + one of these verb stems, glued directly (no ZWNJ) -- the exact
# three verbs this session found broken, plus their plural endings.
_VERB_STEMS = ('شود', 'شوند', 'کند', 'کنند', 'دهد', 'دهند')
_BAD_VERBS = tuple(f'{prefix}{stem}' for prefix in ('می', 'نمی') for stem in _VERB_STEMS)
_GOOD_VERBS = tuple(f'{prefix}{_ZWNJ}{stem}' for prefix in ('می', 'نمی') for stem in _VERB_STEMS)

# noun + ها, glued directly (no ZWNJ) -- the specific nouns named in this
# session's cleanup ticket, not "any noun".
_BAD_NOUNS = ('مدل', 'بسته', 'پلن', 'کاربر', 'دسته', 'اسکیل', 'رشته')
_BAD_PLURALS = tuple(f'{noun}ها' for noun in _BAD_NOUNS)
_GOOD_PLURALS = tuple(f'{noun}{_ZWNJ}ها' for noun in _BAD_NOUNS)

_BAD_SUBSTRINGS = _BAD_VERBS + _BAD_PLURALS
_GOOD_FORMS = _GOOD_VERBS + _GOOD_PLURALS


def _iter_backend_py_files():
    for path in sorted(BACKEND.rglob('*.py')):
        rel = path.relative_to(BACKEND)
        if rel.parts[0] in _EXCLUDED_TOP:
            continue
        yield rel, path


def _string_literals(src: str):
    """Every string constant in the module, in source order, with its line."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value, node.lineno


def _zwnj_offenders():
    for rel, path in _iter_backend_py_files():
        src = path.read_text(encoding='utf-8')
        for value, lineno in _string_literals(src):
            for bad in _BAD_SUBSTRINGS:
                if bad in value:
                    yield f'{rel}:{lineno} contains {bad!r} (missing ZWNJ) in: {value[:80]!r}'


def test_no_missing_zwnj_compounds_in_backend_strings():
    offenders = list(_zwnj_offenders())
    assert offenders == [], (
        'Persian string literal(s) missing a ZWNJ (U+200C, نیم‌فاصله) before '
        'a verb ending or a plural ها suffix -- e.g. "مدلها" should read '
        '"مدل‌ها":\n  ' + '\n  '.join(offenders)
    )


def test_the_scan_actually_reaches_the_backend():
    # A broken scan path would make the assertion above vacuously pass.
    seen = list(_iter_backend_py_files())
    assert len(seen) > 20, f'only {len(seen)} backend .py files found; scan path wrong?'


def test_known_good_forms_are_not_flagged():
    """Positive control: the CORRECT (ZWNJ-containing) forms this session's
    fix produced must never trip this guard, or the fix would be
    unrepeatable."""
    for good in _GOOD_FORMS:
        assert good not in _BAD_SUBSTRINGS
        assert not any(bad in good for bad in _BAD_SUBSTRINGS), good


def test_legitimate_words_that_merely_contain_the_prefix_are_not_flagged():
    """"همیشه" ("always") contains the substring "میشه" purely by
    orthographic coincidence and must never be treated as a broken
    "می‌شود". Likewise the pronouns "آنها"/"اینها" glue "ها" on with no
    ZWNJ legitimately."""
    for safe in ('همیشه', 'آنها', 'اینها', 'میلیون', 'میلیارد', 'میدان', 'میهن'):
        assert not any(bad in safe for bad in _BAD_SUBSTRINGS), safe
