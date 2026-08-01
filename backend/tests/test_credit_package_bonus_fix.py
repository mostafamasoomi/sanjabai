"""Endpoint-level tests for the /payment/callback credit_package fix.

Regression coverage for two real bugs found together in
payment_endpoints.py::payment_callback:

1. ``CreditPackage.id`` is a string primary key (e.g. "pkg_mimo_20m"), but
   the credit_package branch did ``CreditPackage.id == int(reference_id)``,
   which raised ValueError (and crashed the callback, after the user had
   already been charged) for any non-numeric package id.
2. The wallet was credited once atomically inside handle_payment_callback
   (via the generic credit_wallet call), then credited *again* with a
   second, manually-inserted Ledger row in this branch -- desyncing
   Wallet.balance from SUM(ledger.amount) on every credit-package purchase.

Both are fixed by resolving the package (by its real string id) before
calling handle_payment_callback and passing total_credits in as
credit_amount, then doing nothing further in this branch.
"""
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import make_row


class TestCreditPackageCallbackFix:
    def _payment_row(self, *, payment_type='credit_package', reference_id='pkg_mimo_20m', user_id=7):
        payment = make_row(
            id=42, user_id=user_id, amount=100_000, authority='AUTH1',
            status='pending', payment_type=payment_type, reference_id=reference_id,
            ref_id=None, verified_at=None,
        )
        return (payment,)

    def _package_row(self, *, pkg_id='pkg_mimo_20m', total_credits=120_000, base_amount=100_000, bonus_percent=20):
        pkg = make_row(
            id=pkg_id, name_fa='بسته تست', name_en='Test package',
            base_amount=base_amount, bonus_percent=bonus_percent, total_credits=total_credits,
            model_id='mimo-v2.5-pro', active=True,
        )
        return (pkg,)

    def test_non_numeric_package_id_does_not_crash(self, client, mock_async_session):
        """Previously int('pkg_mimo_20m') raised ValueError -> 500."""
        async def mock_execute(stmt, *a, **k):
            sql = str(stmt)
            result = MagicMock()
            if 'FROM payments' in sql:
                result.fetchone.return_value = self._payment_row(reference_id='pkg_mimo_20m')
            elif 'FROM credit_packages' in sql:
                result.fetchone.return_value = self._package_row(pkg_id='pkg_mimo_20m')
            else:
                result.fetchone.return_value = None
            return result

        mock_async_session.execute = mock_execute

        from payment import CallbackResult
        fake_result = CallbackResult(ok=True, ref_id='REF1', amount=100_000)
        with patch('payment_endpoints.handle_payment_callback', new=AsyncMock(return_value=fake_result)):
            resp = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'OK'})

        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'ok'
        assert body['credits_added'] == 120_000
        assert body['package'] == 'بسته تست'

    def test_wallet_credited_via_credit_amount_not_a_second_ledger_write(self, client, mock_async_session):
        """The fix passes credit_amount=total_credits into
        handle_payment_callback and does no further DB writes in this
        branch -- session.add must never be called (no duplicate Ledger)."""
        async def mock_execute(stmt, *a, **k):
            sql = str(stmt)
            result = MagicMock()
            if 'FROM payments' in sql:
                result.fetchone.return_value = self._payment_row()
            elif 'FROM credit_packages' in sql:
                result.fetchone.return_value = self._package_row(total_credits=120_000, base_amount=100_000)
            else:
                result.fetchone.return_value = None
            return result

        mock_async_session.execute = mock_execute
        mock_async_session.add = MagicMock()

        from payment import CallbackResult
        callback_mock = AsyncMock(return_value=CallbackResult(ok=True, ref_id='REF1', amount=100_000))
        with patch('payment_endpoints.handle_payment_callback', new=callback_mock):
            resp = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'OK'})

        assert resp.status_code == 200
        # The callback must have been invoked with the bonus-inclusive
        # credit_amount, not the charged amount.
        _, kwargs = callback_mock.call_args
        assert kwargs['credit_amount'].amount == 120_000
        assert 'بسته اعتباری' in kwargs['credit_reason']
        # No manual Ledger (or anything else) inserted in this route branch.
        mock_async_session.add.assert_not_called()

    def test_charge_amount_mismatch_does_not_silently_use_credit_amount(self, client, mock_async_session):
        """Sanity: base_amount (charged) and total_credits (credited) are
        genuinely different values flowing through -- not the same field
        read twice."""
        async def mock_execute(stmt, *a, **k):
            sql = str(stmt)
            result = MagicMock()
            if 'FROM payments' in sql:
                result.fetchone.return_value = self._payment_row()
            elif 'FROM credit_packages' in sql:
                result.fetchone.return_value = self._package_row(base_amount=80_000, total_credits=100_000, bonus_percent=25)
            else:
                result.fetchone.return_value = None
            return result

        mock_async_session.execute = mock_execute

        from payment import CallbackResult
        callback_mock = AsyncMock(return_value=CallbackResult(ok=True, ref_id='REF1', amount=80_000))
        with patch('payment_endpoints.handle_payment_callback', new=callback_mock):
            resp = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'OK'})

        assert resp.status_code == 200
        _, kwargs = callback_mock.call_args
        assert kwargs['credit_amount'].amount == 100_000
        assert resp.json()['credits_added'] == 100_000
