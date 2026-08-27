"""Regression tests for the plan/subscription retirement (session 23,
migrations/0049_retire_plans_subscriptions.sql). `credit_packages` is now
the only product concept; `plans` and `subscriptions` are gone from the
schema entirely.

Three things this file exists to pin down:

1. Every retired route (backend/pricing.py's `/plans`, `/plans/{id}`,
   `/subscribe`, `/subscription`, `/subscription/cancel`,
   `/subscription/renew`; backend/pricing_billing.py's `/me/subscription`,
   `/subscription/checkout`) is gone -- not disabled, not stubbed, 404 like
   any other undefined path.

2. `/credit-packages` (the surviving product surface) still answers.

3. 🔴 THE MONEY TRAP, and the reason this file exists at all: a Payment
   row created before the retirement can still be sitting `status='pending'`
   with `payment_type='subscription'` when Zarinpal calls back. Naively
   deleting the old subscription-grant branch in
   payment_endpoints.py::payment_callback would let that stale row fall
   through to `handle_payment_callback`'s *default* behaviour -- credit the
   wallet the full charged amount -- for a product that no longer exists.
   The fix is an early guard, before `handle_payment_callback` is ever
   called, that refuses with 410 and credits nothing. The assertion that
   matters here is not the status code (a guard could 410 and still credit
   if placed after the call) -- it's that the sole sanctioned credit path,
   `handle_payment_callback`, was never invoked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import make_row


class TestRetiredRoutesAreGone:
    """Not disabled, not 410, not redirected -- gone, like any other
    undefined path. A 200/401/500 here would mean the route still exists."""

    def test_list_plans_404(self, client):
        assert client.get('/plans').status_code == 404

    def test_get_plan_404(self, client):
        assert client.get('/plans/pro').status_code == 404

    def test_subscribe_404(self, client):
        assert client.post('/subscribe', json={'plan_id': 'pro'}).status_code == 404

    def test_get_subscription_404(self, client):
        assert client.get('/subscription').status_code == 404

    def test_cancel_subscription_404(self, client):
        assert client.post('/subscription/cancel').status_code == 404

    def test_renew_subscription_404(self, client):
        assert client.post('/subscription/renew').status_code == 404

    def test_me_subscription_404(self, client):
        assert client.get('/me/subscription').status_code == 404

    def test_subscription_checkout_404(self, client):
        assert client.post('/subscription/checkout', json={'plan_id': 'pro'}).status_code == 404


class TestCreditPackagesSurvive:
    """The only product concept left must still answer."""

    def test_list_credit_packages_200(self, client, mock_async_session):
        resp = client.get('/credit-packages')
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestStaleSubscriptionCallbackGuard:
    """🔴 The reason this file exists. A pending Payment row with
    payment_type='subscription' -- left over from before the retirement --
    must be refused with 410, and must never reach the wallet-crediting
    path, regardless of what Zarinpal's Status query param says."""

    def _pending_subscription_payment_row(self):
        payment = make_row(
            id=42, user_id=7, amount=150_000, authority='AUTH1',
            status='pending', payment_type='subscription', reference_id='pro',
            ref_id=None, verified_at=None,
        )
        return (payment,)

    def _mock_execute_payments_only(self):
        async def mock_execute(stmt, *a, **k):
            sql = str(stmt)
            result = MagicMock()
            if 'FROM payments' in sql:
                result.fetchone.return_value = self._pending_subscription_payment_row()
            else:
                result.fetchone.return_value = None
                result.scalar_one_or_none.return_value = None
            return result
        return mock_execute

    def test_stale_subscription_callback_returns_410(self, client, mock_async_session):
        mock_async_session.execute = self._mock_execute_payments_only()
        with patch('payment_endpoints.handle_payment_callback', new=AsyncMock()) as mock_callback:
            resp = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'OK'})

        assert resp.status_code == 410
        body = resp.json()
        assert body['detail'], 'err() must carry a Persian detail string'
        assert body['detail_en'], 'err() must carry an English detail_en sibling'
        # The money trap: the guard must sit *before* the only sanctioned
        # credit path is ever reached. A 410 that still calls
        # handle_payment_callback (e.g. after the fact, or on a different
        # branch) is exactly the bug this test exists to catch -- the
        # status code alone would not have caught the original trap
        # (handle_payment_callback defaults to crediting the full charged
        # amount when no credit_amount kwarg is passed).
        mock_callback.assert_not_called()

    def test_stale_subscription_callback_refused_even_on_nok_status(self, client, mock_async_session):
        """The guard reads payment_type off the stored Payment row, not the
        Status query param -- it must refuse a 'subscription' payment
        regardless of what Zarinpal says happened."""
        mock_async_session.execute = self._mock_execute_payments_only()
        with patch('payment_endpoints.handle_payment_callback', new=AsyncMock()) as mock_callback:
            resp = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'NOK'})

        assert resp.status_code == 410
        mock_callback.assert_not_called()
