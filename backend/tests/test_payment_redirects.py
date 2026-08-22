"""Regression tests for backend/payment_endpoints.py's redirect targets.

Two real production bugs, both about `/payment/callback` sending users to
URLs that do not exist in the frontend:

1. On a FAILED payment, the redirect map sent 'subscription' users to
   `/plans?payment=failed` and 'credit_package' users to
   `/credits?payment=failed`. Neither `/plans` nor `/credits` exists as a
   page in `frontend/app/` -- verified against production, both 404. A
   user whose payment failed landed on a dead page with no explanation of
   what happened to their money.

2. On a SUCCESSFUL hermes_order payment, the redirect pointed at
   `/hermes/orders/{id}` -- a per-order detail route that was never built
   (only the list page `frontend/app/hermes/orders/page.tsx` exists;
   verified against production: `/hermes/orders/1` 404s even though
   `/hermes/orders` itself is 200). Every successful Hermes order purchase
   was silently sent to a 404.

The fix points every redirect at a page that actually exists, reusing the
same destinations the (already-correct) success redirects use:
subscription failure -> `/dashboard` (matches the success target,
`/dashboard?subscription=active`); credit_package failure -> `/wallet`
(matches the success target, `/wallet?payment=success`); hermes_order
success -> the `/hermes/orders` list page instead of the missing
per-order route. hermes_order failure was already correct
(`/hermes/order`, the order form) and is pinned down so it cannot regress
while touching the other two.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import make_row


def _payment_row(*, payment_type, reference_id=None, user_id=7, amount=50_000):
    payment = make_row(
        id=1, user_id=user_id, amount=amount, authority='AUTH1',
        status='pending', payment_type=payment_type, reference_id=reference_id,
        ref_id=None, verified_at=None,
    )
    return (payment,)


def _mock_execute_payment_only(payment_type, reference_id=None):
    """session.execute stand-in answering only the `FROM payments` lookup.

    The failure-redirect map depends solely on `payment_type` (read off the
    Payment row before `handle_payment_callback` is even called), so
    leaving `reference_id` unset (falsy) is enough to skip the
    credit_package/hermes_order sub-lookups entirely and keep these tests
    focused on the redirect map itself.
    """
    async def mock_execute(stmt, *a, **k):
        sql = str(stmt)
        result = MagicMock()
        if 'FROM payments' in sql:
            result.fetchone.return_value = _payment_row(
                payment_type=payment_type, reference_id=reference_id,
            )
        else:
            result.fetchone.return_value = None
            result.scalar_one_or_none.return_value = None
        return result
    return mock_execute


class TestFailedPaymentRedirects:
    """Every failure redirect target must be a real, existing frontend
    page (independently verified with curl against production -- see the
    session report)."""

    def _redirect_for(self, client, mock_async_session, payment_type):
        from payment import CallbackResult
        mock_async_session.execute = _mock_execute_payment_only(payment_type)
        fail_result = CallbackResult(ok=False, detail='پرداخت ناموفق بود یا لغو شد', code=402)
        with patch('payment_endpoints.handle_payment_callback', new=AsyncMock(return_value=fail_result)):
            resp = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'NOK'})
        assert resp.status_code == 402
        return resp.json()['redirect']

    def test_subscription_failure_redirects_to_dashboard_not_plans(self, client, mock_async_session):
        redirect = self._redirect_for(client, mock_async_session, 'subscription')
        assert '/plans' not in redirect, f'/plans does not exist in the frontend, got {redirect!r}'
        assert redirect.endswith('/dashboard?payment=failed')

    def test_credit_package_failure_redirects_to_wallet_not_credits(self, client, mock_async_session):
        redirect = self._redirect_for(client, mock_async_session, 'credit_package')
        assert '/credits' not in redirect, f'/credits does not exist in the frontend, got {redirect!r}'
        assert redirect.endswith('/wallet?payment=failed')

    def test_hermes_order_failure_still_redirects_to_order_form(self, client, mock_async_session):
        """Already correct before this fix (/hermes/order, verified 200
        against production) -- pinned so it can't regress."""
        redirect = self._redirect_for(client, mock_async_session, 'hermes_order')
        assert redirect.endswith('/hermes/order?payment=failed')

    def test_unknown_payment_type_falls_back_to_wallet(self, client, mock_async_session):
        redirect = self._redirect_for(client, mock_async_session, 'wallet_topup')
        assert redirect.endswith('/wallet?payment=failed')


class TestHermesOrderSuccessRedirect:
    def test_success_redirects_to_orders_list_not_missing_detail_page(self, client, mock_async_session):
        """`frontend/app/hermes/orders/[id]` does not exist -- only the
        list page `frontend/app/hermes/orders/page.tsx` does (verified: a
        per-order URL 404s on production even though the list page is
        200). The success redirect must land on the list page, never a
        per-order URL."""
        from payment import CallbackResult

        order = make_row(id=99, offering_id=3, status='pending_payment', paid_at=None, updated_at=None)
        offering = make_row(id=3, included_credit=0)

        async def mock_execute(stmt, *a, **k):
            sql = str(stmt)
            result = MagicMock()
            if 'FROM payments' in sql:
                result.fetchone.return_value = _payment_row(payment_type='hermes_order', reference_id='99')
            elif 'FROM hermes_orders' in sql:
                result.scalar_one_or_none.return_value = order
            elif 'FROM hermes_offerings' in sql:
                result.scalar_one_or_none.return_value = offering
            else:
                result.fetchone.return_value = None
                result.scalar_one_or_none.return_value = None
            return result

        mock_async_session.execute = mock_execute
        mock_async_session.add = MagicMock()

        ok_result = CallbackResult(ok=True, ref_id='REF1', amount=50_000)
        with patch('payment_endpoints.handle_payment_callback', new=AsyncMock(return_value=ok_result)):
            resp = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'OK'})

        assert resp.status_code == 200
        body = resp.json()
        assert '/hermes/orders/99' not in body['redirect'], f'per-order route does not exist, got {body["redirect"]!r}'
        assert body['redirect'].endswith('/hermes/orders?payment=success')
        assert body['order_id'] == 99
