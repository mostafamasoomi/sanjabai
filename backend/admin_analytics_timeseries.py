"""The admin dashboard's timeseries: money, cost, growth, over a chosen window.

Split out of admin_analytics.py, which sat at 464 lines against the house
500-line cap while this endpoint was about to roughly double. The move is
otherwise faithful: every existing response key keeps its exact name and
shape (tests/test_admin_analytics_naming.py guards that), and the naming
history below is carried over verbatim because it records an incident, not a
preference.

MONKEYPATCH CONTRACT: this module gates on `admin.admin_required(request)`
through a plain `import admin`, never `from admin import admin_required`, and
reaches the database through `from database import async_session` -- a shared
proxy object, which is what tests/conftest.py's `mock_async_session` patches
(at `database._real_async_session`). Both idioms are load-bearing: bind the
name directly instead and the tests silently fall through to a real engine
rather than failing loudly.

── Two money words that are not synonyms ────────────────────────────────
This endpoint once returned a single `daily_revenue` computed as
`SUM(usage_events.charged_amount)` per day. That is *consumption* -- what
users were charged for model usage -- and has nothing to do with money
arriving through the payment gateway. The same mistake in `/admin/stats` and
`/admin/analytics` was fixed in commit 81d8240, "the dashboard reported ten
million toman of revenue from zero sales", after a single admin-seeded ledger
row was reported as income. `daily_gateway_revenue` is computed from
completed payments only, mirroring that commit's query exactly; the old
`daily_revenue` / `revenue_by_model` keys are deliberately NOT kept as
aliases, because an alias would preserve precisely the lie the rename
removed.

── A third word: cost ───────────────────────────────────────────────────
Migration 0048 added what each request cost US upstream. Its comment block
holds the binding read-side contract; the three rules that shape every query
below are:

  * `upstream_cost_toman IS NULL` means UNKNOWN. Nothing here may COALESCE a
    NULL cost to zero. Folding unmeasured rows to zero would draw a
    beautiful, fake-profitable past out of history that predates the column.
  * Coverage is REVENUE-weighted, not row-counted, so one large unmeasured
    request cannot hide behind ninety-nine tiny measured ones. (Where a
    bucket has no revenue at all -- a day of entirely package-covered
    requests, which charge nothing -- it falls back to row-weighting rather
    than declaring a vacuous 100%.)
  * A margin is NULL unless its bucket is fully measured. A partially
    measured day reports no profit number at all, and the UI renders that
    NULL as «اندازه‌گیری‌نشده», never as a figure.

And the naming rule that follows from all of it: `revenue - cost` here is
GROSS MARGIN ON UPSTREAM TOKEN COST. It excludes the fixed monthly cost of
the infrastructure the free upstreams run on, so it is not net profit and no
field is called profit.
"""
from __future__ import annotations

from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session
import admin
from i18n import err

router = APIRouter()


#: Windows the dashboard offers. Whitelisted rather than clamped: `days` is
#: interpolated into an interval, and a whitelist is the difference between
#: "an odd number of days" and an injection surface. Anything else silently
#: becomes the default -- an admin who hand-edits the query string gets the
#: normal view, not an error page.
WINDOW_DAYS = (1, 7, 30, 60, 90)
DEFAULT_WINDOW_DAYS = 30


def resolve_window(raw: Any) -> int:
    """The requested window in days, or the default. Never raises."""
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_DAYS
    return days if days in WINDOW_DAYS else DEFAULT_WINDOW_DAYS


def coverage_of(measured_revenue: int, total_revenue: int,
                measured_events: int, total_events: int) -> float:
    """How much of a bucket actually has a measured cost, from 0.0 to 1.0.

    Revenue-weighted while there is revenue to weight by: a single expensive
    unmeasured request must not be diluted by a hundred trivial measured
    ones, which is exactly what counting rows would do.

    A bucket can have events and no revenue at all -- a day where every
    request was covered by a package charges the user nothing. Declaring that
    day 100% measured on the grounds that 0 of 0 toman is accounted for would
    be a vacuous truth used to hide unmeasured rows, so it falls back to
    row-weighting. Only a genuinely empty bucket is 1.0.
    """
    if total_revenue > 0:
        return min(1.0, measured_revenue / total_revenue)
    if total_events > 0:
        return min(1.0, measured_events / total_events)
    return 1.0


def margin_or_none(revenue: int, known_cost: int, coverage: float) -> int | None:
    """`revenue - known_cost`, but only when the bucket is fully measured.

    Returning a number from a partially measured bucket would silently
    subtract a cost that is missing some of its parts, which always flatters
    the result. There is no honest partial answer here, so there is no
    partial answer.
    """
    return (revenue - known_cost) if coverage >= 1.0 else None


def returning_purchaser_rate_or_none(new_purchasers: int, returning_purchasers: int) -> float | None:
    """`returning / (new + returning)`, or None when the window had no
    purchasers at all.

    0 of 0 is not a 0% returning rate -- it is no data, and reporting 0.0
    would read as "every purchaser churned" on a window nobody bought
    anything in. Same NULL-means-unmeasured discipline as `margin_or_none`;
    the churn-proxy used in place of MRR, retired with subscriptions in 0049.
    """
    total = new_purchasers + returning_purchasers
    return (returning_purchasers / total) if total > 0 else None


@router.get('/admin/analytics/timeseries')
async def admin_analytics_timeseries(request: Request) -> JSONResponse:
    """Timeseries for the admin dashboard over a `days` window.

    Query params: `days` -- one of 1, 7, 30, 60, 90 (default 30). Anything
    else falls back to the default rather than erroring.

    Returns `daily_consumption`, `daily_gateway_revenue`, `daily_users`,
    `daily_tokens`, `daily_cost`, `daily_margin`, `daily_conversations`,
    `daily_purchasers`, `consumption_by_model`, `top_users`, `totals`,
    `cost_cutover_at` and the resolved `days`. Every daily series is
    zero-filled.

    BEHAVIOUR CHANGE (session 23): `consumption_by_model` and `top_users`
    used to be pinned to the current calendar month regardless of what the
    rest of the page showed, so the tables and the charts above them
    described different periods. They now follow the selected window like
    everything else.
    """
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    days = resolve_window(request.query_params.get('days'))
    params = {'days': days}

    async with async_session() as session:
        # 1) Daily consumption -- what users were charged for usage. NOT
        # revenue; see the module docstring.
        res = await session.execute(sqlalchemy.text("""
            WITH dates AS (
                SELECT generate_series(
                    (NOW() - make_interval(days => :days))::date,
                    NOW()::date,
                    '1 day'
                )::date AS day
            )
            SELECT d.day::text AS day,
                   COALESCE(SUM(ue.charged_amount), 0) AS amount
            FROM dates d
            LEFT JOIN usage_events ue ON DATE(ue.created_at) = d.day
            GROUP BY d.day
            ORDER BY d.day
        """), params)
        daily_consumption = [{'day': str(r._mapping['day']), 'amount': int(r._mapping['amount'])}
                             for r in res.fetchall()]

        # 1b) Daily GATEWAY revenue -- actual completed payments, never
        # derived from usage_events. Same union and toman conversion as
        # 81d8240's total_revenue query. `payment_orders.amount_irr` is
        # integer RIAL (the column name says so; it predates the Money/toman
        # refactor and has no active writer left), which is the one
        # legitimate rial conversion outside the gateway adapter.
        res = await session.execute(sqlalchemy.text("""
            WITH dates AS (
                SELECT generate_series(
                    (NOW() - make_interval(days => :days))::date,
                    NOW()::date,
                    '1 day'
                )::date AS day
            ),
            gateway AS (
                SELECT DATE(verified_at) AS day, user_id, amount AS amount_toman
                FROM payments
                WHERE status = 'completed' AND verified_at IS NOT NULL
                UNION ALL
                SELECT DATE(completed_at) AS day, user_id, amount_irr / 10 AS amount_toman
                FROM payment_orders
                WHERE status = 'completed' AND completed_at IS NOT NULL
            )
            SELECT d.day::text AS day,
                   COALESCE(SUM(g.amount_toman), 0) AS amount,
                   COUNT(DISTINCT g.user_id) AS purchasers
            FROM dates d
            LEFT JOIN gateway g ON g.day = d.day
            GROUP BY d.day
            ORDER BY d.day
        """), params)
        gateway_rows = res.fetchall()
        daily_gateway_revenue = [{'day': str(r._mapping['day']), 'amount': int(r._mapping['amount'])}
                                 for r in gateway_rows]
        # Purchasers come from the SAME payments CTE as the revenue above --
        # a "buyer" is someone whose money actually arrived, never someone
        # who merely generated usage.
        daily_purchasers = [{'day': str(r._mapping['day']),
                             'purchasers': int(r._mapping['purchasers'])}
                            for r in gateway_rows]

        # 1c) Purchaser lifecycle -- NEW vs RETURNING, this product's
        # churn-proxy in place of MRR (retired with subscriptions in 0049).
        # Not a UNION ALL like `gateway`: needs each purchaser's FULL
        # history, so two single-table queries merged in Python below.
        res = await session.execute(sqlalchemy.text("""
            SELECT user_id,
                   BOOL_OR(DATE(verified_at) < (NOW() - make_interval(days => :days))::date) AS has_prior,
                   BOOL_OR(DATE(verified_at) >= (NOW() - make_interval(days => :days))::date) AS in_window
            FROM payments
            WHERE status = 'completed' AND verified_at IS NOT NULL
            GROUP BY user_id
        """), params)
        purchaser_rows = [dict(r._mapping) for r in res.fetchall()]
        res = await session.execute(sqlalchemy.text("""
            SELECT user_id,
                   BOOL_OR(DATE(completed_at) < (NOW() - make_interval(days => :days))::date) AS has_prior,
                   BOOL_OR(DATE(completed_at) >= (NOW() - make_interval(days => :days))::date) AS in_window
            FROM payment_orders
            WHERE status = 'completed' AND completed_at IS NOT NULL
            GROUP BY user_id
        """), params)
        purchaser_rows += [dict(r._mapping) for r in res.fetchall()]

        # 2) Daily active + new users
        res = await session.execute(sqlalchemy.text("""
            WITH dates AS (
                SELECT generate_series(
                    (NOW() - make_interval(days => :days))::date,
                    NOW()::date,
                    '1 day'
                )::date AS day
            )
            SELECT d.day::text AS day,
                   COUNT(DISTINCT ue.user_id) AS active_users,
                   COUNT(DISTINCT CASE
                       WHEN DATE(u.created_at) = d.day THEN u.id
                   END) AS new_users
            FROM dates d
            LEFT JOIN usage_events ue ON DATE(ue.created_at) = d.day
            LEFT JOIN users u ON DATE(u.created_at) = d.day
            GROUP BY d.day
            ORDER BY d.day
        """), params)
        daily_users = [{'day': str(r._mapping['day']),
                        'active_users': int(r._mapping['active_users']),
                        'new_users': int(r._mapping['new_users'])}
                       for r in res.fetchall()]

        # 3) Daily token volume
        res = await session.execute(sqlalchemy.text("""
            WITH dates AS (
                SELECT generate_series(
                    (NOW() - make_interval(days => :days))::date,
                    NOW()::date,
                    '1 day'
                )::date AS day
            )
            SELECT d.day::text AS day,
                   COALESCE(SUM(ue.input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(ue.output_tokens), 0) AS output_tokens
            FROM dates d
            LEFT JOIN usage_events ue ON DATE(ue.created_at) = d.day
            GROUP BY d.day
            ORDER BY d.day
        """), params)
        daily_tokens = [{'day': str(r._mapping['day']),
                         'input_tokens': int(r._mapping['input_tokens']),
                         'output_tokens': int(r._mapping['output_tokens'])}
                        for r in res.fetchall()]

        # 3b) Daily upstream COST. Note what is and is not summed: known_cost
        # sums only rows that actually have a cost, and measured_revenue sums
        # the revenue of exactly those same rows. Their ratio against total
        # revenue is the coverage figure -- which is why measured_revenue is
        # selected at all rather than being inferred later.
        res = await session.execute(sqlalchemy.text("""
            WITH dates AS (
                SELECT generate_series(
                    (NOW() - make_interval(days => :days))::date,
                    NOW()::date,
                    '1 day'
                )::date AS day
            )
            SELECT d.day::text AS day,
                   COALESCE(SUM(ue.upstream_cost_toman), 0) AS known_cost,
                   COALESCE(SUM(ue.charged_amount)
                            FILTER (WHERE ue.upstream_cost_toman IS NOT NULL), 0) AS measured_revenue,
                   COALESCE(SUM(ue.charged_amount), 0) AS total_revenue,
                   COUNT(ue.id) FILTER (WHERE ue.upstream_cost_toman IS NOT NULL) AS measured_events,
                   COUNT(ue.id) AS total_events,
                   COUNT(ue.id) FILTER (WHERE ue.upstream_cost_basis = 'unknown') AS unknown_events,
                   COUNT(ue.id) FILTER (WHERE ue.upstream_cost_basis = 'error') AS error_events
            FROM dates d
            LEFT JOIN usage_events ue ON DATE(ue.created_at) = d.day
            GROUP BY d.day
            ORDER BY d.day
        """), params)
        cost_rows = [dict(r._mapping) for r in res.fetchall()]

        # 4) Consumption by model over the window (was: current month).
        res = await session.execute(sqlalchemy.text("""
            SELECT model,
                   SUM(charged_amount) AS consumption,
                   COALESCE(SUM(upstream_cost_toman), 0) AS known_cost,
                   COALESCE(SUM(charged_amount)
                            FILTER (WHERE upstream_cost_toman IS NOT NULL), 0) AS measured_revenue,
                   COUNT(*) FILTER (WHERE upstream_cost_toman IS NOT NULL) AS measured_events,
                   COUNT(DISTINCT user_id) AS users,
                   COUNT(*) AS calls
            FROM usage_events
            WHERE created_at >= NOW() - make_interval(days => :days)
            GROUP BY model
            ORDER BY consumption DESC
            LIMIT 10
        """), params)
        consumption_by_model = [_with_margin(dict(r._mapping), 'consumption')
                                for r in res.fetchall()]

        # 5) Top users by spend over the window (was: current month).
        res = await session.execute(sqlalchemy.text("""
            SELECT ue.user_id,
                   u.email,
                   SUM(ue.charged_amount) AS total_cost,
                   COALESCE(SUM(ue.upstream_cost_toman), 0) AS known_cost,
                   COALESCE(SUM(ue.charged_amount)
                            FILTER (WHERE ue.upstream_cost_toman IS NOT NULL), 0) AS measured_revenue,
                   COUNT(*) FILTER (WHERE ue.upstream_cost_toman IS NOT NULL) AS measured_events,
                   SUM(ue.input_tokens + ue.output_tokens) AS total_tokens,
                   COUNT(*) AS calls
            FROM usage_events ue
            JOIN users u ON ue.user_id = u.id
            WHERE ue.created_at >= NOW() - make_interval(days => :days)
            GROUP BY ue.user_id, u.email
            ORDER BY total_cost DESC
            LIMIT 10
        """), params)
        top_users = [_with_margin(dict(r._mapping), 'total_cost') for r in res.fetchall()]

        # 6) Daily conversations -- chat growth, independent of billing.
        res = await session.execute(sqlalchemy.text("""
            WITH dates AS (
                SELECT generate_series(
                    (NOW() - make_interval(days => :days))::date,
                    NOW()::date,
                    '1 day'
                )::date AS day
            )
            SELECT d.day::text AS day,
                   COUNT(c.id) AS count
            FROM dates d
            LEFT JOIN conversations c ON DATE(c.created_at) = d.day
            GROUP BY d.day
            ORDER BY d.day
        """), params)
        daily_conversations = [{'day': str(r._mapping['day']), 'count': int(r._mapping['count'])}
                               for r in res.fetchall()]

        # 7) When cost capture began. Read from the migration ledger rather
        # than hardcoded, so it stays true if this is ever applied to a
        # database on a different day (a staging restore, a new deployment).
        cutover = None
        try:
            res = await session.execute(sqlalchemy.text(
                "SELECT applied_at FROM schema_migrations WHERE version LIKE '0048%' LIMIT 1"
            ))
            row = res.fetchone()
            if row is not None:
                cutover = row[0]
        except Exception:
            # A missing ledger row is not worth failing the whole dashboard
            # over; the coverage figures already say the same thing.
            cutover = None

    daily_cost = [{
        'day': str(row['day']),
        'known_cost': int(row['known_cost']),
        'cost_coverage': coverage_of(
            int(row['measured_revenue']), int(row['total_revenue']),
            int(row['measured_events']), int(row['total_events']),
        ),
        'unknown_events': int(row['unknown_events']),
        'error_events': int(row['error_events']),
    } for row in cost_rows]

    # Margins are assembled in Python rather than SQL so the gateway CTE
    # stays exactly the query 81d8240 established, untouched and un-joined.
    gateway_by_day = {r['day']: r['amount'] for r in daily_gateway_revenue}
    daily_margin = []
    for row, cost in zip(cost_rows, daily_cost):
        coverage = cost['cost_coverage']
        known = cost['known_cost']
        daily_margin.append({
            'day': cost['day'],
            'usage_margin': margin_or_none(int(row['total_revenue']), known, coverage),
            'net': margin_or_none(gateway_by_day.get(cost['day'], 0), known, coverage),
        })

    # Merge per user: EITHER source having a prior/in-window payment counts,
    # the same OR-across-sources shape `gateway`'s UNION ALL gives above.
    purchaser_state: dict[Any, dict[str, bool]] = {}
    for row in purchaser_rows:
        state = purchaser_state.setdefault(row['user_id'], {'has_prior': False, 'in_window': False})
        state['has_prior'] = state['has_prior'] or bool(row['has_prior'])
        state['in_window'] = state['in_window'] or bool(row['in_window'])
    new_purchasers = sum(1 for s in purchaser_state.values() if s['in_window'] and not s['has_prior'])
    returning_purchasers = sum(1 for s in purchaser_state.values() if s['in_window'] and s['has_prior'])

    totals = _totals(cost_rows, daily_gateway_revenue, new_purchasers, returning_purchasers)

    return JSONResponse(jsonable_encoder({
        'days': days,
        'daily_consumption': daily_consumption,
        'daily_gateway_revenue': daily_gateway_revenue,
        'daily_users': daily_users,
        'daily_tokens': daily_tokens,
        'daily_cost': daily_cost,
        'daily_margin': daily_margin,
        'daily_conversations': daily_conversations,
        'daily_purchasers': daily_purchasers,
        'consumption_by_model': consumption_by_model,
        'top_users': top_users,
        'totals': totals,
        'cost_cutover_at': cutover,
    }))


def _with_margin(row: dict, revenue_key: str) -> dict:
    """Add coverage and margin to a per-model / per-user row.

    Same NULL-margin rule as the daily series: a partially measured row gets
    no margin at all rather than one computed from an incomplete cost.
    """
    revenue = int(row.get(revenue_key) or 0)
    known = int(row.get('known_cost') or 0)
    coverage = coverage_of(
        int(row.get('measured_revenue') or 0), revenue,
        int(row.get('measured_events') or 0), int(row.get('calls') or 0),
    )
    out = {key: value for key, value in row.items()
           if key not in ('measured_revenue', 'measured_events')}
    out[revenue_key] = revenue
    out['known_cost'] = known
    out['cost_coverage'] = coverage
    out['margin'] = margin_or_none(revenue, known, coverage)
    return out


def _totals(cost_rows: list[dict], gateway: list[dict],
            new_purchasers: int = 0, returning_purchasers: int = 0) -> dict:
    """Window-wide roll-up, under exactly the same NULL rules as the days.

    Summed from the per-day rows rather than re-queried: two queries that
    should agree but are written separately eventually stop agreeing, and the
    one nobody is looking at is the one that drifts.

    `new_purchasers`/`returning_purchasers` are pre-classified by the
    purchaser-lifecycle merge above, not summed here: "new" vs "returning"
    is a window-wide property of a user's FULL history, not something day
    rows can be summed into without double-counting a user who bought twice.
    """
    consumption = sum(int(r['total_revenue']) for r in cost_rows)
    known_cost = sum(int(r['known_cost']) for r in cost_rows)
    measured_revenue = sum(int(r['measured_revenue']) for r in cost_rows)
    measured_events = sum(int(r['measured_events']) for r in cost_rows)
    total_events = sum(int(r['total_events']) for r in cost_rows)
    gateway_revenue = sum(int(r['amount']) for r in gateway)
    coverage = coverage_of(measured_revenue, consumption, measured_events, total_events)
    return {
        'consumption': consumption,
        'gateway_revenue': gateway_revenue,
        'known_cost': known_cost,
        'cost_coverage': coverage,
        'usage_margin': margin_or_none(consumption, known_cost, coverage),
        'net': margin_or_none(gateway_revenue, known_cost, coverage),
        'unknown_events': sum(int(r['unknown_events']) for r in cost_rows),
        'error_events': sum(int(r['error_events']) for r in cost_rows),
        'new_purchasers': new_purchasers,
        'returning_purchasers': returning_purchasers,
        'returning_purchaser_rate': returning_purchaser_rate_or_none(new_purchasers, returning_purchasers),
    }
