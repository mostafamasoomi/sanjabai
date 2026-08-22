"""Direct assertions on the *literal SQL text* of services/entitlements.py.

test_entitlements.py drives the module against a fake session that
re-implements the WHERE-clause semantics of each query in Python (see its
module docstring). That is necessary because there is no live Postgres in
the default test environment (tests/conftest.py mocks asyncpg at import
time), but it means a regression that silently weakens one of these WHERE
clauses -- e.g. dropping the ``max_cost_per_request_toman IS NOT NULL``
fail-closed guard, or the ``requests_remaining IS NULL OR ... > 0``
exhaustion check -- would NOT be caught by that fake: the fake would keep
enforcing its own Python copy of the old rule regardless of what the real
SQL says.

This file closes that gap the cheapest way that still runs with no DB: it
asserts the exact clause text is present in the compiled ``sqlalchemy.text()``
statements. This is deliberately crude -- it is not a query planner and
can't prove the SQL is semantically equivalent to some *other* correct
phrasing -- but it directly catches the one failure mode that matters here:
someone editing or deleting one of these clauses without deliberately
updating this test to match, which is exactly the kind of change a reviewer
needs surfaced.

A real-Postgres test (following the disposable-database pattern already
established in test_migrations_real.py -- CREATE DATABASE a throwaway
`sanjabai_test_*`, run the real migrate() against it, exercise the real
queries, DROP it afterwards) would be a strictly stronger check than
anything in this file, and is the natural next step. It was deliberately
NOT added here: the task this file was written under explicitly prohibits
running any migration against any database (including a throwaway one),
and backend/migrations/0034_package_entitlements.sql was being edited
concurrently by another change at the time this file was written, so
running migrate() against it here would have been both against the rules
and likely to race a concurrent edit. See test_migrations_real.py for the
pattern to follow when that restriction doesn't apply.
"""
from __future__ import annotations

import functools
from datetime import datetime, timedelta, timezone

import services.entitlements as ent_mod
from tests._entitlements_order_by import compare_by_terms, parse_order_by


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── _FIND_COVERING_SQL ───────────────────────────────────────────────────

_FIND_SQL = str(ent_mod._FIND_COVERING_SQL)


def test_find_covering_sql_orders_soonest_expiry_first():
    """The exact clause an adversarial review proved the old fake-session
    test could not detect being removed or reordered."""
    assert "ORDER BY expires_at ASC NULLS LAST, id ASC" in _FIND_SQL


def test_find_covering_sql_filters_to_the_requesting_user():
    assert "user_id = :uid" in _FIND_SQL


def test_find_covering_sql_requires_active():
    assert "active = true" in _FIND_SQL


def test_find_covering_sql_excludes_expired():
    assert "(expires_at IS NULL OR expires_at > now())" in _FIND_SQL


def test_find_covering_sql_excludes_exhausted_requests():
    assert "(requests_remaining IS NULL OR requests_remaining > 0)" in _FIND_SQL


def test_find_covering_sql_excludes_exhausted_tokens():
    assert "(tokens_remaining IS NULL OR tokens_remaining > 0)" in _FIND_SQL


def test_find_covering_sql_fails_closed_on_null_ceiling():
    """A NULL max_cost_per_request_toman must be excluded outright, never
    treated as 'no ceiling' -- this is the loss-protection rule the whole
    module exists to enforce (see services/entitlements.py module docstring)."""
    assert "max_cost_per_request_toman IS NOT NULL" in _FIND_SQL


def test_find_covering_sql_ceiling_must_cover_the_estimate():
    assert "max_cost_per_request_toman >= :est_cost_toman" in _FIND_SQL


# ── _CONSUME_SQL ─────────────────────────────────────────────────────────

_CONSUME_SQL = str(ent_mod._CONSUME_SQL)


def test_consume_sql_never_decrements_a_null_requests_dimension():
    """NULL requests_remaining means 'not metered' and must stay NULL
    forever -- never drift to a negative number by being decremented."""
    assert "CASE WHEN requests_remaining IS NULL THEN NULL" in _CONSUME_SQL
    assert "ELSE requests_remaining - :requests END" in _CONSUME_SQL


def test_consume_sql_never_decrements_a_null_tokens_dimension():
    assert "CASE WHEN tokens_remaining IS NULL THEN NULL" in _CONSUME_SQL
    assert "ELSE tokens_remaining - :tokens END" in _CONSUME_SQL


def test_consume_sql_guard_is_active_not_expired_and_sufficient():
    """The re-check-everything-in-one-statement guard that makes the
    decrement race-safe (see services/entitlements.py's long comment above
    _CONSUME_SQL): active, not expired, and enough remaining on both
    dimensions, all evaluated against the row's current values under the
    same statement that writes it."""
    assert "active = true" in _CONSUME_SQL
    assert "(expires_at IS NULL OR expires_at > now())" in _CONSUME_SQL
    assert "(requests_remaining IS NULL OR requests_remaining >= :requests)" in _CONSUME_SQL
    assert "(tokens_remaining IS NULL OR tokens_remaining >= :tokens)" in _CONSUME_SQL


def test_consume_sql_returns_id_only_on_success():
    """RETURNING id is what lets consume_entitlement() tell 'the guard
    failed, WHERE matched zero rows' apart from 'it succeeded'."""
    assert "RETURNING id" in _CONSUME_SQL


# ── _LIST_SQL ────────────────────────────────────────────────────────────

_LIST_SQL = str(ent_mod._LIST_SQL)


def test_list_sql_filters_to_active_nonexpired_for_the_user():
    assert "user_id = :uid" in _LIST_SQL
    assert "active = true" in _LIST_SQL
    assert "(expires_at IS NULL OR expires_at > now())" in _LIST_SQL


def test_list_sql_orders_newest_first():
    assert "ORDER BY created_at DESC" in _LIST_SQL


# ── guard the guard ──────────────────────────────────────────────────────
#
# The checks above are plain substring containment, which is only as good
# as the exact strings chosen. These canaries hardcode the actual
# regression an adversarial review used to defeat the old
# test_soonest_expiry_is_preferred (rewriting the ORDER BY to `id DESC`,
# in a throwaway copy of services/entitlements.py) and prove that the exact
# checks above -- and the ORDER BY parser test_entitlements.py's fake now
# depends on -- both visibly notice it. A canary that can't demonstrate its
# own detector failing on bad input is worthless; see test_credit_paths.py
# for the established style this follows.

def test_canary_order_by_string_check_would_have_caught_the_id_desc_regression():
    good = _FIND_SQL
    assert "ORDER BY expires_at ASC NULLS LAST, id ASC" in good

    broken = good.replace(
        "ORDER BY expires_at ASC NULLS LAST, id ASC", "ORDER BY id DESC"
    )
    assert broken != good, "the .replace() above is a no-op -- fix the fixture"
    assert "ORDER BY expires_at ASC NULLS LAST, id ASC" not in broken


def test_canary_null_ceiling_check_would_have_caught_removing_the_fail_closed_guard():
    good = _FIND_SQL
    assert "max_cost_per_request_toman IS NOT NULL" in good

    broken = good.replace("max_cost_per_request_toman IS NOT NULL ", "")
    assert broken != good, "the .replace() above is a no-op -- fix the fixture"
    assert "max_cost_per_request_toman IS NOT NULL" not in broken


def test_canary_consume_case_when_check_would_have_caught_an_unconditional_decrement():
    """If someone 'simplified' the CASE WHEN away to a bare
    `requests_remaining - :requests`, a NULL (unmetered) dimension would
    start drifting negative instead of staying NULL forever. Prove the
    check notices that specific rewrite."""
    good = _CONSUME_SQL
    assert "CASE WHEN requests_remaining IS NULL THEN NULL " in good

    broken = good.replace(
        "requests_remaining = CASE WHEN requests_remaining IS NULL THEN NULL "
        "ELSE requests_remaining - :requests END, ",
        "requests_remaining = requests_remaining - :requests, ",
    )
    assert broken != good, "the .replace() above is a no-op -- fix the fixture"
    assert "CASE WHEN requests_remaining IS NULL THEN NULL " not in broken


def test_canary_order_by_parser_discriminates_real_sql_from_the_id_desc_regression():
    """Guards tests/_entitlements_order_by.py itself (which test_entitlements
    .py's fake session now uses to sort covering-entitlement candidates):
    prove it is genuinely driven by the SQL text, not a disguised hardcoded
    sort that would keep 'passing' no matter what ORDER BY clause it's
    handed -- the exact failure mode this whole file exists to close.

    IDs are deliberately NOT monotonic with expiry order (see
    test_entitlements.py's test_soonest_expiry_is_preferred for why), so an
    id-based ORDER BY picks a visibly different, wrong row instead of
    coincidentally agreeing with the correct answer.
    """
    now = _utcnow()
    rows = [
        {'id': 99, 'expires_at': None},                       # never expires
        {'id': 5, 'expires_at': now + timedelta(days=10)},
        {'id': 42, 'expires_at': now + timedelta(days=1)},    # soonest -- correct winner
    ]

    def winner(sql_fragment: str) -> int:
        terms = parse_order_by(sql_fragment)
        ordered = sorted(rows, key=functools.cmp_to_key(
            lambda a, b: compare_by_terms(a, b, terms)
        ))
        return ordered[0]['id']

    assert winner("... ORDER BY expires_at ASC NULLS LAST, id ASC LIMIT 1") == 42

    # The exact regression the adversarial review introduced:
    assert winner("... ORDER BY id DESC LIMIT 1") == 99
    # A different plausible regression, also caught:
    assert winner("... ORDER BY id ASC LIMIT 1") == 5
