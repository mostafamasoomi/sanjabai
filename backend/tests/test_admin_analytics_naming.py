"""Regression tests for /admin/analytics/timeseries's naming fix.

Context: this endpoint used to return `daily_revenue` computed as
`SUM(usage_events.charged_amount)` per day, and `revenue_by_model` computed
the same way -- both are *consumption* (what users were charged for model
usage), not revenue. The identical class of mistake in `/admin/stats` and
`/admin/analytics` was fixed in commit 81d8240 ("the dashboard reported ten
million toman of revenue from zero sales"); this endpoint carried the same
lie under a different route and was never touched by that fix.

This module proves three things, each with a dedicated test:
  1. The new key names (`daily_consumption`, `daily_gateway_revenue`,
     `consumption_by_model`) are present.
  2. The old, misleading key names (`daily_revenue`, `revenue_by_model`) are
     NOT present -- keeping them as aliases would perpetuate the exact lie
     this fix removes.
  3. `daily_gateway_revenue` is actually computed from completed gateway
     payments (`payments`/`payment_orders`), never from `usage_events` --
     proven by wiring a fake DB where the two sources return DIFFERENT
     numbers and asserting each response field carries the number from its
     correct source, not the other one's.

Per this project's test infrastructure (tests/conftest.py), `session.
execute()` never touches a real Postgres -- it returns whatever the test
wires up. Like test_admin_revenue_truth.py, the fake `execute` below
dispatches on the *SQL text* of each query (not call order), so a reordering
of the queries inside the endpoint can't produce a false green, and reverting
the endpoint to source `daily_gateway_revenue`-shaped data from
`usage_events` instead of `payments` is exactly the mutation this file's
tests are built to catch.
"""
from unittest.mock import MagicMock

import pytest
import sqlalchemy

from tests.conftest import ADMIN_TOKEN, make_row


def _series_result(day_amount_pairs, amount_key='amount'):
    rows = [MagicMock(_mapping={'day': day, amount_key: amount}) for day, amount in day_amount_pairs]
    res = MagicMock()
    res.fetchall.return_value = rows
    return res


def _empty_result():
    res = MagicMock()
    res.fetchall.return_value = []
    # Explicitly None, not a bare MagicMock: the endpoint's schema_migrations
    # lookup does `row[0]` on whatever fetchone() returns, and a MagicMock
    # would sail through that and then break jsonable_encoder far from the
    # cause.
    res.fetchone.return_value = None
    return res


def _make_fake_db(consumption_days, gateway_days):
    """A tiny fake Postgres dispatching on SQL text, mirroring
    test_admin_revenue_truth.py's approach.

    ``consumption_days`` backs the usage_events-sourced daily series
    (daily_consumption AND consumption_by_model, kept structurally separate
    from gateway money). ``gateway_days`` backs daily_gateway_revenue,
    resolved from payments/payment_orders. The two are deliberately
    different values in the tests below so a query that reads from the
    wrong table is caught immediately.
    """
    async def fake_execute(query, *args, **kwargs):
        if not isinstance(query, sqlalchemy.sql.elements.TextClause):
            return _empty_result()
        sql = str(query)

        # top_users: also contains `ue.charged_amount` (as `total_cost`), so
        # it must be checked BEFORE the generic daily_consumption check below.
        if 'total_cost' in sql:
            return _empty_result()

        # daily_gateway_revenue AND daily_purchasers: reads
        # payments/payment_orders, never usage_events. One query now backs
        # both series -- a "buyer" is someone whose money actually arrived,
        # so the buyer count must come from the same rows as the revenue.
        if 'FROM payments' in sql and 'FROM payment_orders' in sql:
            rows = [make_row(_mapping={'day': day, 'amount': amount, 'purchasers': 1 if amount else 0})
                    for day, amount in gateway_days]
            res = MagicMock()
            res.fetchall.return_value = rows
            return res

        # daily_cost (migration 0048). Must be matched BEFORE the generic
        # `ue.charged_amount` branch below, which its coverage arithmetic
        # also contains. Every row here is fully measured so this fake does
        # not accidentally exercise the NULL-margin path -- that path has
        # its own dedicated tests in test_admin_analytics_window.py.
        if 'unknown_events' in sql:
            rows = [make_row(_mapping={
                'day': day, 'known_cost': 0, 'measured_revenue': amount,
                'total_revenue': amount, 'measured_events': 1, 'total_events': 1,
                'unknown_events': 0, 'error_events': 0,
            }) for day, amount in consumption_days]
            res = MagicMock()
            res.fetchall.return_value = rows
            return res

        # daily_conversations -- chat growth, no billing involvement.
        if 'FROM conversations' in sql:
            return _empty_result()

        # The cost-capture cutover timestamp.
        if 'schema_migrations' in sql:
            return _empty_result()

        # daily_users
        if 'active_users' in sql and 'new_users' in sql:
            return _empty_result()

        # daily_tokens
        if 'ue.input_tokens' in sql and 'ue.output_tokens' in sql:
            return _empty_result()

        # consumption_by_model (current month, grouped by model)
        if 'GROUP BY model' in sql and 'AS consumption' in sql:
            _amount = consumption_days[0][1] if consumption_days else 0
            rows = [make_row(_mapping={'model': 'gpt-x', 'consumption': _amount,
                                       'known_cost': 0, 'measured_revenue': _amount,
                                       'measured_events': 1, 'users': 1, 'calls': 1})]
            res = MagicMock()
            res.fetchall.return_value = rows
            return res

        # daily_consumption: SUM(ue.charged_amount) per day from usage_events.
        # Everything more specific above has already been matched, so this
        # is safe to check last via the broad `ue.charged_amount` substring.
        if 'ue.charged_amount' in sql:
            return _series_result(consumption_days)

        return _empty_result()
    return fake_execute


@pytest.fixture
def admin_headers():
    return {'x-admin-token': ADMIN_TOKEN}


class TestAnalyticsTimeseriesNaming:
    def test_new_key_names_present(self, client, mock_async_session, admin_headers):
        mock_async_session.execute = _make_fake_db(
            consumption_days=[('2026-08-01', 1000)],
            gateway_days=[('2026-08-01', 0)],
        )
        response = client.get('/admin/analytics/timeseries', headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert 'daily_consumption' in data
        assert 'daily_gateway_revenue' in data
        assert 'consumption_by_model' in data
        assert 'daily_users' in data
        assert 'daily_tokens' in data
        assert 'top_users' in data

    def test_old_misleading_key_names_absent(self, client, mock_async_session, admin_headers):
        """The old `daily_revenue`/`revenue_by_model` keys must NOT be kept
        as duplicate aliases -- that would perpetuate the exact naming lie
        this fix exists to remove."""
        mock_async_session.execute = _make_fake_db(
            consumption_days=[('2026-08-01', 1000)],
            gateway_days=[('2026-08-01', 0)],
        )
        response = client.get('/admin/analytics/timeseries', headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert 'daily_revenue' not in data
        assert 'revenue_by_model' not in data

    def test_gateway_revenue_is_not_usage_events_consumption(self, client, mock_async_session, admin_headers):
        """The core claim of this fix: daily_gateway_revenue must come from
        completed gateway payments, never from usage_events -- proven by
        making the two sources disagree and checking each field reflects
        ONLY its own source."""
        mock_async_session.execute = _make_fake_db(
            consumption_days=[('2026-08-01', 999_000), ('2026-08-02', 111_000)],
            gateway_days=[('2026-08-01', 250_000), ('2026-08-02', 0)],
        )
        response = client.get('/admin/analytics/timeseries', headers=admin_headers)
        assert response.status_code == 200
        data = response.json()

        consumption_by_day = {d['day']: d['amount'] for d in data['daily_consumption']}
        gateway_by_day = {d['day']: d['amount'] for d in data['daily_gateway_revenue']}

        assert consumption_by_day['2026-08-01'] == 999_000
        assert gateway_by_day['2026-08-01'] == 250_000
        assert consumption_by_day['2026-08-01'] != gateway_by_day['2026-08-01']

        assert consumption_by_day['2026-08-02'] == 111_000
        assert gateway_by_day['2026-08-02'] == 0

    def test_consumption_by_model_uses_usage_events_not_payments(self, client, mock_async_session, admin_headers):
        """consumption_by_model (renamed from revenue_by_model) must stay
        sourced from usage_events -- it is spend, not gateway revenue."""
        mock_async_session.execute = _make_fake_db(
            consumption_days=[('2026-08-01', 42_000)],
            gateway_days=[('2026-08-01', 0)],
        )
        response = client.get('/admin/analytics/timeseries', headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data['consumption_by_model']) == 1
        assert data['consumption_by_model'][0]['model'] == 'gpt-x'
        assert data['consumption_by_model'][0]['consumption'] == 42_000

    def test_unauthorized(self, client):
        response = client.get('/admin/analytics/timeseries')
        assert response.status_code == 401
