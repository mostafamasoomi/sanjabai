"""Guards for admin_analytics_timeseries.py -- the window, and the three
rules that stop the dashboard from flattering itself.

Migration 0048 gave usage_events a real upstream cost, but only for requests
made after it landed. Everything before is NULL, and NULL is where every
interesting failure lives: fold it to zero and history becomes a period of
perfect margins; count coverage by row instead of by revenue and one large
unmeasured request hides behind ninety-nine trivial measured ones; report a
margin from a half-measured day and the missing half always makes the number
look better, never worse. None of those crash. All of them produce a
confident chart of something that did not happen.

`resolve_window`, `coverage_of` and `margin_or_none` are exercised directly
because they are the whole contract in three pure functions; the HTTP tests
then prove the endpoint actually routes its data through them, following
test_admin_analytics_naming.py's SQL-text dispatch so a reordering of the
queries inside the endpoint cannot produce a false green.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import sqlalchemy

from admin_analytics_timeseries import (
    DEFAULT_WINDOW_DAYS,
    WINDOW_DAYS,
    coverage_of,
    margin_or_none,
    resolve_window,
)
from tests.conftest import ADMIN_TOKEN, make_row


# ═══════════════════════════════════════════════════════════════════════
# Section 1: the window is a whitelist, not a clamp
# ═══════════════════════════════════════════════════════════════════════

class TestResolveWindow:

    @pytest.mark.parametrize('days', WINDOW_DAYS)
    def test_every_offered_window_is_accepted(self, days):
        assert resolve_window(days) == days
        assert resolve_window(str(days)) == days

    @pytest.mark.parametrize('raw', [
        45, 0, -1, 1000, 'abc', '', None, '30;DROP TABLE users', '30 OR 1=1', 3.7,
    ])
    def test_anything_else_falls_back_instead_of_reaching_sql(self, raw):
        # A whitelist rather than a clamp: this value is interpolated into
        # an interval, and "an odd number of days" and "an injection
        # surface" are the two things a clamp cannot tell apart. Falling
        # back silently is deliberate -- an admin who hand-edits the query
        # string gets the normal view, not an error page.
        assert resolve_window(raw) == DEFAULT_WINDOW_DAYS


# ═══════════════════════════════════════════════════════════════════════
# Section 2: coverage is weighted by money
# ═══════════════════════════════════════════════════════════════════════

class TestCoverage:

    def test_fully_measured_is_one(self):
        assert coverage_of(1_000, 1_000, 10, 10) == 1.0

    def test_nothing_measured_is_zero(self):
        assert coverage_of(0, 1_000, 0, 10) == 0.0

    def test_one_expensive_unmeasured_request_dominates_many_trivial_ones(self):
        # 99 measured requests worth 1 toman each, plus 1 unmeasured request
        # worth 100,000. Counting rows would call this 99% covered and hand
        # the owner a margin computed with almost none of the actual cost in
        # it. Weighted by revenue it is ~1%, and the NULL-margin rule below
        # then refuses to report a margin at all.
        coverage = coverage_of(
            measured_revenue=99, total_revenue=100_099,
            measured_events=99, total_events=100,
        )
        assert coverage < 0.02
        # The row-counted answer, stated explicitly so the difference is not
        # a matter of interpretation: this is what a regression would return.
        assert coverage != pytest.approx(99 / 100)

    def test_a_day_with_events_but_no_revenue_falls_back_to_row_weighting(self):
        # Every request covered by a package charges the user nothing. "0 of
        # 0 toman is accounted for, therefore 100% covered" is a vacuous
        # truth that would hide genuinely unmeasured rows behind it.
        assert coverage_of(0, 0, 1, 2) == 0.5

    def test_a_genuinely_empty_day_is_fully_covered(self):
        # Nothing happened, so nothing is unaccounted for. This is the only
        # case where an all-zero bucket may claim 1.0.
        assert coverage_of(0, 0, 0, 0) == 1.0


class TestMarginNullRule:

    def test_a_fully_measured_bucket_reports_a_number(self):
        assert margin_or_none(1_000, 300, 1.0) == 700

    def test_a_negative_margin_is_reported_not_hidden(self):
        # A loss is a result, not an error. Clamping it at zero would remove
        # the single most important thing this dashboard can tell the owner.
        assert margin_or_none(300, 1_000, 1.0) == -700

    @pytest.mark.parametrize('coverage', [0.0, 0.5, 0.99, 0.999])
    def test_a_partially_measured_bucket_reports_nothing(self, coverage):
        # There is no honest partial answer: subtracting a cost that is
        # missing some of its parts always flatters the result. So there is
        # no partial answer.
        assert margin_or_none(1_000, 300, coverage) is None


# ═══════════════════════════════════════════════════════════════════════
# Section 3: the endpoint actually routes its data through those rules
# ═══════════════════════════════════════════════════════════════════════

def _result(rows):
    res = MagicMock()
    res.fetchall.return_value = rows
    res.fetchone.return_value = None
    return res


def _fake_db(cost_rows, gateway_rows=(), captured_params=None):
    """Fake Postgres dispatching on SQL TEXT, never on call order.

    Order-independent by construction, so reordering the queries inside the
    endpoint cannot silently feed one series another's data.
    """
    async def fake_execute(query, params=None, *args, **kwargs):
        if not isinstance(query, sqlalchemy.sql.elements.TextClause):
            return _result([])
        sql = str(query)
        if captured_params is not None and params:
            captured_params.append(dict(params))
        if 'unknown_events' in sql:
            return _result([make_row(_mapping=row) for row in cost_rows])
        if 'FROM payments' in sql and 'FROM payment_orders' in sql:
            return _result([make_row(_mapping=row) for row in gateway_rows])
        return _result([])
    return fake_execute


def _cost_row(day, *, known_cost, measured_revenue, total_revenue,
              measured_events=1, total_events=1, unknown=0, error=0):
    return {
        'day': day, 'known_cost': known_cost,
        'measured_revenue': measured_revenue, 'total_revenue': total_revenue,
        'measured_events': measured_events, 'total_events': total_events,
        'unknown_events': unknown, 'error_events': error,
    }


@pytest.fixture
def admin_headers():
    return {'x-admin-token': ADMIN_TOKEN}


class TestEndpointWindow:

    def test_the_resolved_window_is_echoed_back(self, client, mock_async_session, admin_headers):
        mock_async_session.execute = _fake_db([])
        for days in WINDOW_DAYS:
            body = client.get(f'/admin/analytics/timeseries?days={days}',
                              headers=admin_headers).json()
            assert body['days'] == days

    def test_a_rejected_window_is_echoed_as_the_default(self, client, mock_async_session, admin_headers):
        mock_async_session.execute = _fake_db([])
        body = client.get('/admin/analytics/timeseries?days=45',
                          headers=admin_headers).json()
        assert body['days'] == DEFAULT_WINDOW_DAYS

    def test_the_window_reaches_sql_as_a_bound_parameter_not_a_literal(
        self, client, mock_async_session, admin_headers,
    ):
        # The value is bound, so even a whitelist bypass could not become
        # SQL. Both defences, not either.
        seen: list[dict] = []
        mock_async_session.execute = _fake_db([], captured_params=seen)
        client.get('/admin/analytics/timeseries?days=90;DROP TABLE users',
                   headers=admin_headers)
        assert seen, 'no query was executed with parameters'
        assert all(p.get('days') == DEFAULT_WINDOW_DAYS for p in seen if 'days' in p)


class TestEndpointHonesty:

    def test_a_day_with_one_unmeasured_row_reports_no_margin(
        self, client, mock_async_session, admin_headers,
    ):
        mock_async_session.execute = _fake_db([
            _cost_row('2026-08-27', known_cost=50, measured_revenue=100,
                      total_revenue=500, measured_events=1, total_events=2),
        ])
        body = client.get('/admin/analytics/timeseries', headers=admin_headers).json()
        assert body['daily_cost'][0]['cost_coverage'] < 1.0
        assert body['daily_margin'][0]['usage_margin'] is None
        assert body['daily_margin'][0]['net'] is None
        assert body['totals']['usage_margin'] is None

    def test_a_fully_measured_day_reports_the_exact_arithmetic(
        self, client, mock_async_session, admin_headers,
    ):
        mock_async_session.execute = _fake_db(
            [_cost_row('2026-08-27', known_cost=300, measured_revenue=1_000,
                       total_revenue=1_000)],
            gateway_rows=[{'day': '2026-08-27', 'amount': 2_000, 'purchasers': 1}],
        )
        body = client.get('/admin/analytics/timeseries', headers=admin_headers).json()
        assert body['daily_cost'][0]['cost_coverage'] == 1.0
        assert body['daily_margin'][0]['usage_margin'] == 700
        # net uses GATEWAY revenue, not consumption -- the 81d8240 rule.
        assert body['daily_margin'][0]['net'] == 1_700
        assert body['totals']['net'] == 1_700

    def test_the_pre_cutover_past_is_unmeasured_rather_than_free(
        self, client, mock_async_session, admin_headers,
    ):
        # Every row written before migration 0048 has NULL cost. This is the
        # shape of the entire existing production history, and reporting it
        # as a 100%-margin golden age is the exact failure this endpoint
        # exists to prevent.
        mock_async_session.execute = _fake_db([
            _cost_row('2026-08-20', known_cost=0, measured_revenue=0,
                      total_revenue=496_867, measured_events=0, total_events=139),
        ])
        body = client.get('/admin/analytics/timeseries', headers=admin_headers).json()
        assert body['daily_cost'][0]['known_cost'] == 0
        assert body['daily_cost'][0]['cost_coverage'] == 0.0
        assert body['daily_margin'][0]['usage_margin'] is None

    def test_error_basis_events_are_surfaced_not_swallowed(
        self, client, mock_async_session, admin_headers,
    ):
        # 'error' means cost capture itself broke. It clusters after a bad
        # deploy and is meant to be loud rather than quietly reducing
        # coverage with no explanation.
        mock_async_session.execute = _fake_db([
            _cost_row('2026-08-27', known_cost=0, measured_revenue=0,
                      total_revenue=100, measured_events=0, total_events=3,
                      unknown=1, error=2),
        ])
        body = client.get('/admin/analytics/timeseries', headers=admin_headers).json()
        assert body['daily_cost'][0]['unknown_events'] == 1
        assert body['daily_cost'][0]['error_events'] == 2
        assert body['totals']['error_events'] == 2

    def test_the_cost_sql_itself_separates_measured_from_unmeasured_rows(self):
        """A source scan, because the tests above cannot reach this.

        Every HTTP test in this file feeds the endpoint pre-built rows
        through a fake `session.execute`, so the SQL is never executed and a
        mutation inside it is invisible to them -- verified: rewriting the
        cost query's FILTER clauses to count every row as measured left all
        of them green. That is precisely the failure the mutation protocol
        exists to surface, so the SQL gets its own guard.

        What is being protected: `measured_revenue` and `measured_events`
        must count only rows that actually carry a cost. Drop the FILTER and
        a day of entirely NULL-cost rows reports 100% coverage, which lets
        the margin rule hand back a number computed with none of the cost in
        it -- and the pre-0048 history is exactly that day, 139 times over.
        """
        import inspect
        import admin_analytics_timeseries as mod

        src = inspect.getsource(mod)
        cost_query = src[src.index('AS known_cost'):src.index('AS error_events')]

        assert cost_query.count('FILTER (WHERE ue.upstream_cost_toman IS NOT NULL)') == 2, (
            'measured_revenue and measured_events must each be filtered to '
            'rows that have a cost'
        )
        # The one COALESCE allowed on the cost column is the known_cost sum,
        # where the zero means "nothing measured here yet", not "free".
        assert 'COALESCE(ue.upstream_cost_toman, 0)' not in src, (
            'a NULL cost folded to zero inside a row-level expression is how '
            'unmeasured history becomes a fake-profitable past'
        )

    def test_purchasers_come_from_payments_not_usage(
        self, client, mock_async_session, admin_headers,
    ):
        # Wired so the two sources return different numbers: a buyer is
        # someone whose money arrived, never someone who merely generated
        # usage. Same proof shape test_admin_analytics_naming.py uses for
        # daily_gateway_revenue itself.
        mock_async_session.execute = _fake_db(
            [_cost_row('2026-08-27', known_cost=0, measured_revenue=0,
                       total_revenue=999_999, measured_events=0, total_events=42)],
            gateway_rows=[{'day': '2026-08-27', 'amount': 5_000, 'purchasers': 2}],
        )
        body = client.get('/admin/analytics/timeseries', headers=admin_headers).json()
        assert body['daily_purchasers'][0]['purchasers'] == 2
        assert body['daily_gateway_revenue'][0]['amount'] == 5_000
