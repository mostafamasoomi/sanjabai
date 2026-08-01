"""Regression tests for the wallet.balance charge-on-usage fix.

Previously chat._record_usage only ever appended a Ledger row for real
usage — Wallet.balance was written to solely by top-ups and by
BillingService.settle() (which is never called in production), so the
pre-flight balance check in BillingService.reserve() never reflected actual
spend. See migrations/0017_wallet_ledger_reconciliation.sql for the
production-data fix and chat.py::_record_usage for the code fix this test
protects.
"""
from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

import chat as chat_mod
from models import Wallet


def _table_name(stmt):
    try:
        return stmt.table.name
    except AttributeError:
        pass
    try:
        for f in stmt.get_final_froms():
            name = getattr(f, "name", None)
            if name:
                return name
    except Exception:
        pass
    return None


class _FakeSession:
    """Minimal session double covering exactly the statements
    chat._record_usage / SqlBillingRepo issue: quota select/update, a raw
    text() pricing lookup, and the wallet select+update pair (once directly
    via lock_wallet_for_update, once via ensure_wallet, once via
    set_wallet_balance)."""

    def __init__(self, wallet_balance, price=None):
        self.wallet = types.SimpleNamespace(user_id=1, balance=wallet_balance, reserved=0)
        self.price = price
        self.added = []
        self.wallet_updates = []

    async def execute(self, stmt, params=None, *a, **k):
        result = MagicMock()
        result.fetchone.return_value = None
        text_sql = str(stmt)
        if "model_catalog" in text_sql:
            result.fetchone.return_value = self.price
            return result
        tname = _table_name(stmt)
        if tname == "wallet":
            if type(stmt).__name__ == "Update":
                p = stmt.compile().params
                self.wallet_updates.append(p)
                if "balance" in p:
                    self.wallet.balance = p["balance"]
                if "reserved" in p:
                    self.wallet.reserved = p["reserved"]
            else:
                # SqlBillingRepo does `row = res.fetchone(); wallet = row[0]`
                # -- a real Result row is tuple-like, so wrap the entity.
                result.fetchone.return_value = (self.wallet,)
            return result
        if tname == "quota":
            return result  # no quota row -> _record_usage skips quota update
        return result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


def _usage(total=1000, prompt=800, completion=200):
    return {"total_tokens": total, "prompt_tokens": prompt, "completion_tokens": completion}


def _price(inp=1_000_000, out=1_000_000):
    # 1,000,000 IRT per million tokens -> 1 IRT per token, easy to hand-check.
    return types.SimpleNamespace(input_per_million=inp, output_per_million=out)


class TestRecordUsageChargesWallet:
    @pytest.mark.asyncio
    async def test_sufficient_balance_debits_wallet_and_appends_ledger(self):
        session = _FakeSession(wallet_balance=10_000, price=_price())
        result = await chat_mod._record_usage(session, uid=1, payload={"model": "kr/gpt-4o-mini"}, usage=_usage())

        # 800 input + 200 output tokens @ 1 IRT/token (rounded half-up) = 1000
        assert result["cost"] == 1000
        assert session.wallet.balance == 10_000 - 1000
        assert result["balance_after"] == 9000
        assert session.wallet_updates and session.wallet_updates[-1]["balance"] == 9000

        ledger_rows = [o for o in session.added if type(o).__name__ == "Ledger"]
        assert len(ledger_rows) == 1
        assert ledger_rows[0].amount == -1000
        assert ledger_rows[0].balance_after == 9000

    @pytest.mark.asyncio
    async def test_insufficient_balance_does_not_debit_or_go_negative(self):
        session = _FakeSession(wallet_balance=500, price=_price())
        result = await chat_mod._record_usage(session, uid=1, payload={"model": "kr/gpt-4o-mini"}, usage=_usage())

        assert result["cost"] == 1000
        # Balance must never be pushed below zero / left mutated when it
        # can't cover the charge.
        assert session.wallet.balance == 500
        assert result["balance_after"] == 500
        ledger_rows = [o for o in session.added if type(o).__name__ == "Ledger"]
        assert ledger_rows == []

    @pytest.mark.asyncio
    async def test_exact_balance_is_fully_spendable(self):
        session = _FakeSession(wallet_balance=1000, price=_price())
        result = await chat_mod._record_usage(session, uid=1, payload={"model": "kr/gpt-4o-mini"}, usage=_usage())

        assert result["cost"] == 1000
        assert session.wallet.balance == 0
        assert result["balance_after"] == 0
        ledger_rows = [o for o in session.added if type(o).__name__ == "Ledger"]
        assert len(ledger_rows) == 1
