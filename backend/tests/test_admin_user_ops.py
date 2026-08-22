"""Tests for backend/admin_user_ops.py: admin wallet credit/debit and the
consumer/developer panel move.

Two layers, mirroring this suite's existing conventions:

1. `TestWalletInvariants` drives `credit_wallet` (services.billing, unchanged)
   and `_debit_wallet` (new, admin_user_ops.py) directly against
   `MemoryBillingRepo` -- the same "reference implementation of the contract"
   test_billing.py uses -- to pin down the hard money invariants with no
   database involved at all.

2. `TestWalletAdjustEndpoint` / `TestPanelEndpoint` mount just this module's
   router in a throwaway FastAPI app (admin_user_ops is not registered in
   app.py yet -- that's the coordinator's job) and drive it through a fake
   AsyncSession modelled on test_billing_loss_paths.py's `_FakeSession` /
   test_markup_billing_wire.py's `_PricingSession`, to cover auth, payload
   validation, 404, and the audit-log call at the HTTP layer.
"""
from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from services.billing import MemoryBillingRepo, InsufficientBalanceError, credit_wallet
from services.money import Money

import admin_user_ops
from admin_user_ops import _debit_wallet, router as admin_user_ops_router


def _run(coro):
    return asyncio.run(coro)


# ── Layer 1: pure money-invariant tests (MemoryBillingRepo, no DB) ──────────

class TestWalletInvariants:
    def test_credit_balance_after_equals_previous_plus_amount(self):
        async def run():
            repo = MemoryBillingRepo()
            await repo.create_wallet(1, 10_000)
            await credit_wallet(repo, 1, Money(5_000), "شارژ دستی", idempotency_key="k1",
                                 txn_type="admin_credit")
            entry = repo.ledger[-1]
            assert entry["balance_after"] == 10_000 + entry["amount"]
            assert entry["amount"] == 5_000
            assert entry["txn_type"] == "admin_credit"
        _run(run())

    def test_debit_balance_after_equals_previous_plus_amount(self):
        async def run():
            repo = MemoryBillingRepo()
            await repo.create_wallet(1, 10_000)
            await _debit_wallet(repo, 1, Money(3_000), "کسر دستی", idempotency_key="k1")
            entry = repo.ledger[-1]
            # amount is negative for a debit; the invariant still holds.
            assert entry["amount"] == -3_000
            assert entry["balance_after"] == 10_000 + entry["amount"]
            assert entry["balance_after"] == 7_000
            assert entry["txn_type"] == "admin_debit"
        _run(run())

    def test_credit_wallet_balance_and_ledger_sum_agree(self):
        """Not just the ledger: the wallet table balance and the ledger sum
        must agree after the operation."""
        async def run():
            repo = MemoryBillingRepo()
            await repo.create_wallet(1, 0)
            await credit_wallet(repo, 1, Money(1_000), "r", idempotency_key="c1",
                                 txn_type="admin_credit")
            await credit_wallet(repo, 1, Money(2_500), "r", idempotency_key="c2",
                                 txn_type="admin_credit")
            wallet_balance = repo.wallets[1]["balance"]
            ledger_sum = sum(e["amount"] for e in repo.ledger if e["user_id"] == 1)
            assert wallet_balance == 3_500
            assert ledger_sum == wallet_balance
        _run(run())

    def test_debit_wallet_balance_and_ledger_sum_agree(self):
        """The wallet starts at 0 and is brought to 10,000 via a
        ledger-recorded credit (not a direct dict seed) so that "ledger sum
        == wallet balance" is a meaningful check of the full history, not
        just of the two debits in isolation."""
        async def run():
            repo = MemoryBillingRepo()
            await repo.create_wallet(1, 0)
            await credit_wallet(repo, 1, Money(10_000), "seed", idempotency_key="seed",
                                 txn_type="admin_credit")
            await _debit_wallet(repo, 1, Money(1_500), "r", idempotency_key="d1")
            await _debit_wallet(repo, 1, Money(2_000), "r", idempotency_key="d2")
            wallet_balance = repo.wallets[1]["balance"]
            ledger_sum = sum(e["amount"] for e in repo.ledger if e["user_id"] == 1)
            assert wallet_balance == 10_000 - 1_500 - 2_000
            assert ledger_sum == wallet_balance
        _run(run())

    def test_credit_replayed_idempotency_key_is_a_no_op(self):
        async def run():
            repo = MemoryBillingRepo()
            await repo.create_wallet(1, 1_000)
            await credit_wallet(repo, 1, Money(500), "r", idempotency_key="dup",
                                 txn_type="admin_credit")
            await credit_wallet(repo, 1, Money(500), "r", idempotency_key="dup",
                                 txn_type="admin_credit")
            assert repo.wallets[1]["balance"] == 1_500  # not 2_000
            assert len(repo.ledger) == 1
        _run(run())

    def test_debit_replayed_idempotency_key_is_a_no_op(self):
        async def run():
            repo = MemoryBillingRepo()
            await repo.create_wallet(1, 1_000)
            await _debit_wallet(repo, 1, Money(500), "r", idempotency_key="dup")
            result = await _debit_wallet(repo, 1, Money(500), "r", idempotency_key="dup")
            assert repo.wallets[1]["balance"] == 500  # not 0
            assert len(repo.ledger) == 1
            assert result == 500
        _run(run())

    def test_debit_that_would_go_negative_is_refused(self):
        async def run():
            repo = MemoryBillingRepo()
            await repo.create_wallet(1, 1_000)
            with pytest.raises(InsufficientBalanceError):
                await _debit_wallet(repo, 1, Money(1_001), "r", idempotency_key="k")
            # Nothing moved.
            assert repo.wallets[1]["balance"] == 1_000
            assert repo.ledger == []
        _run(run())

    def test_debit_exactly_to_zero_is_allowed(self):
        async def run():
            repo = MemoryBillingRepo()
            await repo.create_wallet(1, 1_000)
            await _debit_wallet(repo, 1, Money(1_000), "r", idempotency_key="k")
            assert repo.wallets[1]["balance"] == 0
        _run(run())

    def test_debit_on_wallet_with_no_row_is_refused(self):
        """ensure_wallet creates a zero-balance row; any positive debit against
        it must be refused, never taken negative."""
        async def run():
            repo = MemoryBillingRepo()
            with pytest.raises(InsufficientBalanceError):
                await _debit_wallet(repo, 42, Money(1), "r", idempotency_key="k")
        _run(run())

    def test_money_rejects_float_and_negative(self):
        with pytest.raises(TypeError):
            Money(100.5)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            Money(100.0)  # type: ignore[arg-type]  -- even an integral float
        with pytest.raises(ValueError):
            Money(-1)


# ── Layer 2: HTTP endpoint tests ────────────────────────────────────────────

def _table_name(stmt):
    """Same resolution order as test_billing_loss_paths.py's double."""
    try:
        return stmt.table.name
    except AttributeError:
        pass
    try:
        for f in stmt.get_final_froms():
            name = getattr(f, 'name', None)
            if name:
                return name
    except Exception:
        pass
    return None


def _query_string_param(stmt):
    """Pull the single string-valued bound parameter out of a compiled
    statement -- used to read the idempotency_key an equality filter is
    matching against."""
    try:
        params = stmt.compile().params
    except Exception:
        return None
    for v in params.values():
        if isinstance(v, str):
            return v
    return None


class _FakeWalletSession:
    """Minimal AsyncSession double covering exactly the statements
    SqlBillingRepo issues for wallet get/ensure/set + ledger append/has_key,
    plus `session.get(User, uid)` for the existence check and the raw
    `UPDATE users SET preferences ...` text() statement the panel endpoint
    issues."""

    def __init__(self, *, user_exists=True, wallet_balance=0, wallet_reserved=0,
                 wallet_exists=True):
        self.user_exists = user_exists
        self.wallet_exists = wallet_exists
        self.wallet_balance = wallet_balance
        self.wallet_reserved = wallet_reserved
        self.ledger: list = []
        self.committed = False
        self.rolled_back = False

    async def get(self, model, pk):
        if not self.user_exists:
            return None
        return types.SimpleNamespace(id=pk)

    async def execute(self, stmt, params=None, *a, **k):
        result = MagicMock()
        result.fetchone.return_value = None
        tname = _table_name(stmt)

        if tname == 'wallet':
            if type(stmt).__name__ == 'Update':
                p = stmt.compile().params
                if 'balance' in p:
                    self.wallet_balance = p['balance']
                if 'reserved' in p:
                    self.wallet_reserved = p['reserved']
            else:
                if self.wallet_exists:
                    result.fetchone.return_value = (
                        types.SimpleNamespace(
                            balance=self.wallet_balance, reserved=self.wallet_reserved,
                        ),
                    )
            return result

        if tname == 'ledger' and type(stmt).__name__ == 'Select':
            key = _query_string_param(stmt)
            found = any(e.idempotency_key == key for e in self.ledger)
            result.fetchone.return_value = (1,) if found else None
            return result

        # Raw text() UPDATE users SET preferences ... -- nothing to simulate.
        return result

    def add(self, obj):
        cls_name = type(obj).__name__
        if cls_name == 'Wallet':
            self.wallet_exists = True
            self.wallet_balance = obj.balance
            self.wallet_reserved = getattr(obj, 'reserved', 0)
        elif cls_name == 'Ledger':
            self.ledger.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _make_client(session):
    app = FastAPI()
    app.include_router(admin_user_ops_router)

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    maker = MagicMock(return_value=_Ctx())
    return TestClient(app), maker


class TestWalletAdjustEndpoint:
    def test_requires_admin(self):
        session = _FakeWalletSession()
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=False)), \
             patch.object(admin_user_ops, 'async_session', maker):
            resp = client.post('/admin/users/1/wallet-adjust', json={
                'amount_toman': 1000, 'direction': 'credit', 'reason': 'x',
            })
        assert resp.status_code == 401

    def test_credit_happy_path_and_audit_log(self):
        session = _FakeWalletSession(wallet_balance=10_000, wallet_exists=True)
        client, maker = _make_client(session)
        audit = AsyncMock()
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker), \
             patch.object(admin_user_ops, '_write_audit_log', new=audit):
            resp = client.post('/admin/users/1/wallet-adjust', json={
                'amount_toman': 5_000, 'direction': 'credit', 'reason': 'جبران خطا',
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body['balance'] == 15_000
        assert session.committed is True
        audit.assert_awaited_once()
        assert audit.call_args.args[0] == 'admin.user.wallet_credit'
        assert audit.call_args.kwargs['details']['reason'] == 'جبران خطا'

    def test_debit_happy_path(self):
        session = _FakeWalletSession(wallet_balance=10_000, wallet_exists=True)
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker), \
             patch.object(admin_user_ops, '_write_audit_log', new=AsyncMock()):
            resp = client.post('/admin/users/1/wallet-adjust', json={
                'amount_toman': 4_000, 'direction': 'debit', 'reason': 'برداشت اشتباه',
            })
        assert resp.status_code == 200
        assert resp.json()['balance'] == 6_000

    def test_debit_below_zero_refused_and_wallet_unchanged(self):
        session = _FakeWalletSession(wallet_balance=1_000, wallet_exists=True)
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker), \
             patch.object(admin_user_ops, '_write_audit_log', new=AsyncMock()) as audit:
            resp = client.post('/admin/users/1/wallet-adjust', json={
                'amount_toman': 2_000, 'direction': 'debit', 'reason': 'برداشت زیاد',
            })
        assert resp.status_code == 400
        assert session.wallet_balance == 1_000
        assert session.ledger == []
        audit.assert_not_awaited()

    def test_float_amount_rejected(self):
        session = _FakeWalletSession()
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker):
            resp = client.post('/admin/users/1/wallet-adjust', json={
                'amount_toman': 1000.5, 'direction': 'credit', 'reason': 'x',
            })
        assert resp.status_code == 400
        assert session.ledger == []

    def test_integral_float_amount_still_rejected(self):
        """100.0 has no fractional part but is still a float, not an int --
        must not be silently coerced."""
        session = _FakeWalletSession()
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker):
            resp = client.post('/admin/users/1/wallet-adjust', json={
                'amount_toman': 1000.0, 'direction': 'credit', 'reason': 'x',
            })
        assert resp.status_code == 400

    def test_missing_reason_rejected(self):
        session = _FakeWalletSession()
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker):
            resp = client.post('/admin/users/1/wallet-adjust', json={
                'amount_toman': 1000, 'direction': 'credit', 'reason': '   ',
            })
        assert resp.status_code == 400
        assert session.ledger == []

    def test_negative_amount_rejected(self):
        session = _FakeWalletSession()
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker):
            resp = client.post('/admin/users/1/wallet-adjust', json={
                'amount_toman': -500, 'direction': 'credit', 'reason': 'x',
            })
        assert resp.status_code == 400

    def test_invalid_direction_rejected(self):
        session = _FakeWalletSession()
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker):
            resp = client.post('/admin/users/1/wallet-adjust', json={
                'amount_toman': 500, 'direction': 'sideways', 'reason': 'x',
            })
        assert resp.status_code == 400

    def test_unknown_user_404s(self):
        session = _FakeWalletSession(user_exists=False)
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker):
            resp = client.post('/admin/users/999/wallet-adjust', json={
                'amount_toman': 500, 'direction': 'credit', 'reason': 'x',
            })
        assert resp.status_code == 404

    def test_replayed_idempotency_key_over_http_is_a_no_op(self):
        session = _FakeWalletSession(wallet_balance=1_000, wallet_exists=True)
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker), \
             patch.object(admin_user_ops, '_write_audit_log', new=AsyncMock()):
            body = {
                'amount_toman': 500, 'direction': 'credit', 'reason': 'x',
                'idempotency_key': 'fixed-key-1',
            }
            r1 = client.post('/admin/users/1/wallet-adjust', json=body)
            r2 = client.post('/admin/users/1/wallet-adjust', json=body)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()['balance'] == 1_500
        assert r2.json()['balance'] == 1_500  # not 2_000
        assert len(session.ledger) == 1


class TestPanelEndpoint:
    def test_requires_admin(self):
        session = _FakeWalletSession()
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=False)), \
             patch.object(admin_user_ops, 'async_session', maker):
            resp = client.post('/admin/users/1/panel', json={'panel': 'developer'})
        assert resp.status_code == 401

    def test_invalid_panel_rejected(self):
        session = _FakeWalletSession()
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker):
            resp = client.post('/admin/users/1/panel', json={'panel': 'root'})
        assert resp.status_code == 400

    def test_unknown_user_404s(self):
        session = _FakeWalletSession(user_exists=False)
        client, maker = _make_client(session)
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker):
            resp = client.post('/admin/users/1/panel', json={'panel': 'developer'})
        assert resp.status_code == 404

    def test_move_to_developer_writes_audit_log(self):
        session = _FakeWalletSession(user_exists=True)
        client, maker = _make_client(session)
        audit = AsyncMock()
        with patch.object(admin_user_ops, 'admin_required', new=AsyncMock(return_value=True)), \
             patch.object(admin_user_ops, 'async_session', maker), \
             patch.object(admin_user_ops, '_write_audit_log', new=audit):
            resp = client.post('/admin/users/1/panel', json={'panel': 'developer'})
        assert resp.status_code == 200
        assert resp.json()['panel'] == 'developer'
        assert session.committed is True
        audit.assert_awaited_once()
        assert audit.call_args.args[0] == 'admin.user.panel'
        assert audit.call_args.kwargs['details'] == {'panel': 'developer'}
