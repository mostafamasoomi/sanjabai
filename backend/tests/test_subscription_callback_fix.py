"""Regression tests for the paid-subscription completion branch of
/payment/callback (payment_endpoints.py), which had two separate crash bugs
found while fixing the identical class of issue in the credit_package
branch (see test_credit_package_bonus_fix.py):

1. Plan.id is a string primary key (admin-chosen, e.g. "pro"), but the
   branch did ``Plan.id == int(reference_id)`` -- ValueError for any
   non-numeric plan id, after the user had already been charged.
2. ``Subscription(..., plan_id=plan.id, ...)`` was passed a keyword the
   ORM model never declared (the DB column has existed since
   migrations/0005_pricing_system.sql, but models.py never mapped it) --
   TypeError: 'plan_id' is an invalid keyword argument for Subscription,
   on every successful paid-subscription checkout.

Together these meant a paid subscription could never actually complete.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import make_row


def test_subscription_model_accepts_plan_id():
    """Direct ORM-level check for bug #2: constructing a Subscription with
    plan_id must not raise TypeError."""
    from models import Subscription

    sub = Subscription(user_id=1, plan='pro', plan_id='pro', status='active')
    assert sub.plan_id == 'pro'


class TestSubscriptionCallbackFix:
    def _payment_row(self, *, reference_id='pro', user_id=7):
        payment = make_row(
            id=42, user_id=user_id, amount=150_000, authority='AUTH1',
            status='pending', payment_type='subscription', reference_id=reference_id,
            ref_id=None, verified_at=None,
        )
        return (payment,)

    def _plan_row(self, *, plan_id='pro', monthly_token_quota=1_000_000):
        plan = make_row(
            id=plan_id, name_fa='حرفه‌ای', name_en='Pro',
            price_monthly=150_000, monthly_token_quota=monthly_token_quota,
            active=True,
        )
        return (plan,)

    def test_non_numeric_plan_id_does_not_crash(self, client, mock_async_session):
        """Previously int('pro') raised ValueError -> 500."""
        async def mock_execute(stmt, *a, **k):
            sql = str(stmt)
            result = MagicMock()
            if 'FROM payments' in sql:
                result.fetchone.return_value = self._payment_row(reference_id='pro')
            elif 'FROM plans' in sql:
                result.fetchone.return_value = self._plan_row(plan_id='pro')
            else:
                result.fetchone.return_value = None
            return result

        mock_async_session.execute = mock_execute
        mock_async_session.add = MagicMock()

        from payment import CallbackResult
        fake_result = CallbackResult(ok=True, ref_id='REF1', amount=150_000)
        with patch('payment_endpoints.handle_payment_callback', new=AsyncMock(return_value=fake_result)):
            resp = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'OK'})

        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'ok'
        assert body['subscription'] == 'Pro'

    def test_subscription_row_constructed_with_matching_plan_id(self, client, mock_async_session):
        """Previously Subscription(plan_id=...) raised TypeError -> 500,
        independent of the int() bug."""
        added = []

        async def mock_execute(stmt, *a, **k):
            sql = str(stmt)
            result = MagicMock()
            if 'FROM payments' in sql:
                result.fetchone.return_value = self._payment_row(reference_id='pro')
            elif 'FROM plans' in sql:
                result.fetchone.return_value = self._plan_row(plan_id='pro')
            else:
                result.fetchone.return_value = None
            return result

        mock_async_session.execute = mock_execute
        mock_async_session.add = MagicMock(side_effect=lambda obj: added.append(obj))

        from payment import CallbackResult
        fake_result = CallbackResult(ok=True, ref_id='REF1', amount=150_000)
        with patch('payment_endpoints.handle_payment_callback', new=AsyncMock(return_value=fake_result)):
            resp = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'OK'})

        assert resp.status_code == 200
        from models import Subscription
        subs = [o for o in added if isinstance(o, Subscription)]
        assert len(subs) == 1
        assert subs[0].plan_id == 'pro'
        assert subs[0].status == 'active'
