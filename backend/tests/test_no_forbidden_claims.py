"""Guard test: no unsupported marketing claims in production frontend copy.

Scans frontend source for literals that, per the product contract
(docs/product-contract.md), must never appear as hardcoded copy because they
are unverified (uptime %, model counts, gift amounts).
"""
import glob
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FRONTEND = os.path.join(ROOT, 'frontend')

# (pattern, reason) — these literals are forbidden in production copy.
#
# The uptime patterns used to be bare "99.9"/"۹۹.۹", with no requirement for
# a percent sign — matching that raw digit sequence anywhere, including
# inside unrelated numeric data (e.g. SVG path coordinates in
# components/ui/Icon.tsx, which have nothing to do with an uptime claim).
# Anchored to an actual percent sign now, which is what "uptime percentage"
# was always meant to catch.
#
# The gift-amount patterns used to include bare, currency-less versions
# (۱۰,۰۰۰ / ۱۰٬۰۰۰ / ۱۰۰۰۰) alongside the currency-qualified ones below —
# those bare versions matched any occurrence of that digit grouping at all,
# including legitimate rate-limit copy like "۱۰,۰۰۰ توکن/روز" (10,000
# tokens/day, a technical quota figure, not a monetary gift). Removed as
# redundant with (and strictly broader than) the "... تومان" versions, which
# are what actually identifies a currency claim.
FORBIDDEN = [
    (r'۹۹[.,]۹\s*(%|٪)', 'uptime percentage is unverified'),
    (r'99[.,]9\s*%', 'uptime percentage is unverified'),
    (r'۵۰\+', 'model count claim is unverified'),
    (r'50\+', 'model count claim is unverified'),
    (r'ده‌ها مدل', 'model count claim is unverified'),
    (r'دهها مدل', 'model count claim is unverified'),
    (r'۱۰,۰۰۰ تومان', 'gift amount must come from a grant record'),
    (r'۵,۰۰۰ تومان', 'gift amount must come from a grant record'),
    (r'۵٬۰۰۰ تومان', 'gift amount must come from a grant record'),
]

SCAN_DIRS = ['app', 'components', 'lib']
EXCLUDE_DIRS = {'node_modules', '.next'}


def _files():
    out = []
    for d in SCAN_DIRS:
        base = os.path.join(FRONTEND, d)
        if not os.path.isdir(base):
            continue
        for path in glob.glob(os.path.join(base, '**', '*.tsx'), recursive=True):
            out.append(path)
        for path in glob.glob(os.path.join(base, '**', '*.ts'), recursive=True):
            out.append(path)
    return out


def test_no_forbidden_claims():
    failures = []
    for path in _files():
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
        for pattern, reason in FORBIDDEN:
            if re.search(pattern, text):
                failures.append(f'{os.path.relpath(path, ROOT)}: forbidden literal {pattern!r} ({reason})')
    assert not failures, 'Forbidden claims found:\n' + '\n'.join(failures)
