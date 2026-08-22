"""Shared helper: parse a real SQL ``ORDER BY`` clause and sort by it.

Not a test file itself (no ``test_`` prefix, so pytest never collects it) --
imported by both ``test_entitlements.py`` (so its fake session's covering-
query dispatch is actually driven by the SQL text handed to it) and
``test_entitlements_sql_contract.py`` (for the "guard the guard" canaries
proving this parsing genuinely discriminates real vs. regressed SQL).

Why this exists: an adversarial review proved that the old fake session in
test_entitlements.py hardcoded its own Python sort key ("soonest expiry
wins") completely independent of whatever ORDER BY clause the real
``services.entitlements._FIND_COVERING_SQL`` actually contained. Rewriting
the production ORDER BY to ``ORDER BY id DESC`` did not fail
``test_soonest_expiry_is_preferred`` -- the fake never looked at the SQL
text at all, so it couldn't have. Parsing the ORDER BY out of the real
compiled SQL and sorting by *that* closes this hole: the test's outcome
now actually depends on what production SQL says.
"""
from __future__ import annotations

import re

_ORDER_BY_RE = re.compile(r'ORDER BY\s+(.+?)(?:\s+LIMIT\b|\Z)', re.IGNORECASE)
_ORDER_TERM_RE = re.compile(
    r'^(\w+)(?:\s+(ASC|DESC))?(?:\s+NULLS\s+(FIRST|LAST))?$', re.IGNORECASE
)


def parse_order_by(sql: str) -> list[tuple[str, bool, bool]]:
    """Parse a plain ``ORDER BY col [ASC|DESC] [NULLS FIRST|LAST], ...``
    clause out of real compiled SQL text into ``(column, descending,
    nulls_last)`` tuples.

    Only handles bare column references -- entitlements.py never orders by
    an expression -- and raises if a term can't be parsed at all: silently
    ignoring an unparseable term would just be a differently-shaped hollow
    guard.
    """
    m = _ORDER_BY_RE.search(sql)
    if not m:
        return []
    terms: list[tuple[str, bool, bool]] = []
    for part in m.group(1).split(','):
        part = part.strip()
        tm = _ORDER_TERM_RE.match(part)
        if not tm:
            raise AssertionError(f"cannot parse ORDER BY term: {part!r}")
        col = tm.group(1)
        desc = (tm.group(2) or 'ASC').upper() == 'DESC'
        # Postgres default when NULLS FIRST/LAST is omitted from the clause:
        # NULLS LAST for ASC, NULLS FIRST for DESC.
        nulls_last = (tm.group(3).upper() == 'LAST') if tm.group(3) else (not desc)
        terms.append((col, desc, nulls_last))
    return terms


def compare_by_terms(row_a: dict, row_b: dict, terms: list[tuple[str, bool, bool]]) -> int:
    """``functools.cmp_to_key``-compatible comparator implementing Postgres
    ASC/DESC + NULLS FIRST/LAST semantics for parsed ORDER BY terms."""
    for col, desc, nulls_last in terms:
        a, b = row_a.get(col), row_b.get(col)
        if a is None and b is None:
            continue
        if a is None:
            return 1 if nulls_last else -1
        if b is None:
            return -1 if nulls_last else 1
        if a == b:
            continue
        smaller_first = 1 if desc else -1
        return smaller_first if a < b else -smaller_first
    return 0
