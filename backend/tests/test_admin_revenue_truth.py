"""Regression tests for the admin revenue truth-telling fix.

Context: `admin_analytics()` and `admin_stats()` in admin.py used to compute
`total_revenue` as `SELECT COALESCE(SUM(amount), 0) FROM ledger WHERE amount
> 0`. That is not revenue -- it is "every ledger row with a plus sign", and
on production it reported 10,000,000 toman of revenue for a business that
had taken ZERO gateway payments, because the only positive ledger row was a
hand-seeded admin credit (`txn_type='topup'`, reason='initial_credit'). See
the long comment above the fixed query in admin.py::admin_analytics for the
full rationale and evidence.

These tests exercise the real endpoints (`/admin/analytics`, `/admin/stats`)
through the TestClient with a mocked DB session, same as the rest of
test_admin.py. Per this project's test infrastructure (tests/conftest.py),
`session.execute()` never touches a real Postgres -- it returns whatever the
test wires up. So instead of returning canned results *positionally* (which
would silently keep passing if the query order shifted), the fake `execute`
below dispatches on the *SQL text* of each query, exactly mimicking a tiny
fake database:
  - any query mentioning `FROM payments` (the new revenue query, which also
    reads the legacy `payment_orders` table) returns the "gateway payments"
    bucket.
  - any query summing positive ledger amounts (`FROM ledger` ... `amount >
    0`) returns the "ledger positive rows" bucket -- this is deliberately
    the SAME bucket the OLD buggy query used, so if admin.py is ever
    reverted to the old single-query shape, `total_revenue` in these tests
    will resolve to the ledger bucket again and the assertions below will
    fail exactly the way the real bug behaved on production.

This is what makes the "deliberately revert the fix" step in the task
meaningful: reverting admin.py's query text changes which bucket
`total_revenue` reads from in this fake DB, not just how many times
`execute()` is called.
"""
from unittest.mock import MagicMock

import pytest
import sqlalchemy

from tests.conftest import ADMIN_TOKEN


def _row(**kwargs):
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


def _result(c=None, total=None, fetchall=None):
    """Build a fake SQLAlchemy result usable via .fetchone().<attr> or .scalar()."""
    row = _row(c=c, total=total)
    res = MagicMock()
    res.fetchone.return_value = row
    res.fetchall.return_value = fetchall if fetchall is not None else []
    # admin_stats() reads via .scalar(); admin_analytics() reads via
    # .fetchone().total -- support both from the same fake result.
    res.scalar.return_value = total if total is not None else c
    return res


def _make_fake_db(gateway_revenue_toman: int, ledger_positive_sum: int):
    """A tiny fake Postgres: dispatches on SQL text, not call order.

    ``gateway_revenue_toman`` is what a completed-payments query should
    return (the already-toman-converted total across `payments` +
    `payment_orders`). ``ledger_positive_sum`` is what
    `SUM(amount) WHERE amount > 0` over the ledger would return -- this is
    the bucket the OLD buggy query read directly as "revenue", and the
    bucket the NEW `total_admin_credit` query reads as "non-gateway credit".
    """
    async def fake_execute(query, *args, **kwargs):
        if isinstance(query, sqlalchemy.sql.elements.TextClause):
            sql = str(query)
            if 'FROM payments' in sql:
                # New, correct revenue query (reads payments/payment_orders).
                return _result(total=gateway_revenue_toman)
            if 'FROM ledger' in sql and 'amount > 0' in sql:
                # Old buggy revenue query AND the new total_admin_credit
                # query both match this shape -- intentionally, since that
                # is exactly the bucket the bug pulled "revenue" from.
                return _result(total=ledger_positive_sum)
            if 'FROM users' in sql:
                return _result(c=1)
            if 'used_today' in sql and 'SUM' in sql:
                return _result(total=0)
            if 'FROM conversations' in sql:
                return _result(c=0)
            if 'used_today > 0' in sql:
                return _result(c=0)
            if 'api_keys' in sql:
                return _result(c=0)
            if 'usage_events' in sql:
                return _result(c=0)
            if 'model_catalog' in sql:
                return _result(c=0)
            return _result(c=0, total=0)
        # The recent-ledger listing (Ledger.__table__.select()...) is a Core
        # Select, not a text() clause -- irrelevant to revenue truth.
        return _result(fetchall=[])
    return fake_execute


@pytest.fixture
def admin_headers():
    return {'x-admin-token': ADMIN_TOKEN}


class TestAdminRevenueTruth:
    """Direct port of the production bug scenario, plus the boundary cases
    the task calls out explicitly."""

    def test_admin_seeded_topup_with_no_payment_is_not_revenue(self, client, mock_async_session, admin_headers):
        """The exact production scenario: one hand-seeded ledger topup
        (+10,000,000), zero completed gateway payments. total_revenue must
        be 0; the 10,000,000 must show up as total_admin_credit instead."""
        mock_async_session.execute = _make_fake_db(
            gateway_revenue_toman=0,
            ledger_positive_sum=10_000_000,
        )
        response = client.get('/admin/analytics', headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data['total_revenue'] == 0
        assert data['total_admin_credit'] == 10_000_000

    def test_admin_seeded_topup_not_revenue_via_stats_endpoint(self, client, mock_async_session, admin_headers):
        """Same scenario through /admin/stats, which had the identical bug."""
        mock_async_session.execute = _make_fake_db(
            gateway_revenue_toman=0,
            ledger_positive_sum=10_000_000,
        )
        response = client.get('/admin/stats', headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data['total_revenue'] == 0
        assert data['total_admin_credit'] == 10_000_000

    def test_completed_gateway_payment_is_counted(self, client, mock_async_session, admin_headers):
        """A real completed payment must be counted as revenue."""
        mock_async_session.execute = _make_fake_db(
            gateway_revenue_toman=250_000,
            ledger_positive_sum=0,
        )
        response = client.get('/admin/analytics', headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data['total_revenue'] == 250_000
        assert data['total_admin_credit'] == 0

    def test_negative_usage_row_does_not_change_revenue(self, client, mock_async_session, admin_headers):
        """A negative 'usage' ledger row (chat spend) must never move
        total_revenue -- it does not match `amount > 0` in either query, so
        it must be structurally invisible to both buckets. Modelled here by
        a real completed payment coexisting with usage-driven ledger noise:
        the fake DB's ledger-positive-sum bucket stays 0 (usage rows are
        negative, never enter a `WHERE amount > 0` sum) while revenue is
        driven entirely by the payments bucket."""
        mock_async_session.execute = _make_fake_db(
            gateway_revenue_toman=250_000,
            ledger_positive_sum=0,  # usage rows are negative; never sum in here
        )
        response = client.get('/admin/analytics', headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data['total_revenue'] == 250_000

    def test_revenue_is_integer_toman_not_off_by_10x(self, client, mock_async_session, admin_headers):
        """Money is integer toman everywhere. Assert the endpoint returns
        exactly what the (already toman-converted) query produced -- no
        stray *10 or /10 applied anywhere in the Python response path."""
        mock_async_session.execute = _make_fake_db(
            gateway_revenue_toman=1_234_500,
            ledger_positive_sum=0,
        )
        response = client.get('/admin/analytics', headers=admin_headers)
        data = response.json()
        assert data['total_revenue'] == 1_234_500
        assert data['total_revenue'] != 1_234_500 * 10
        assert data['total_revenue'] != 1_234_500 // 10
        assert isinstance(data['total_revenue'], int)

        response2 = client.get('/admin/stats', headers=admin_headers)
        data2 = response2.json()
        assert data2['total_revenue'] == 1_234_500
        assert data2['total_revenue'] != 1_234_500 * 10
        assert data2['total_revenue'] != 1_234_500 // 10
        assert isinstance(data2['total_revenue'], int)
