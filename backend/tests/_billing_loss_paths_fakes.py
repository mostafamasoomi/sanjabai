"""Shared fake-session double and pricing/usage builders for the billing
loss-path audit split (test_billing_loss_paths.py /
test_billing_loss_paths_quota.py). Extracted verbatim from
test_billing_loss_paths.py so both halves of the split use the exact same
double -- not a git-tracked convenience, mirrors the existing
`_user_quota_fakes.py` pattern in this suite.
"""
from __future__ import annotations

import types
from unittest.mock import MagicMock


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
    text() pricing lookup, and the wallet select+update pair."""

    def __init__(self, wallet_balance, price=None, quota_row=None):
        self.wallet = types.SimpleNamespace(user_id=1, balance=wallet_balance, reserved=0)
        self.price = price
        self.quota_row = quota_row  # None -> no existing row (the self-heal case)
        self.added = []
        self.wallet_updates = []
        self.quota_updates = []

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
                result.fetchone.return_value = (self.wallet,)
            return result
        if tname == "quota":
            if type(stmt).__name__ == "Update":
                # chat._record_usage's quota update passes values as a
                # separate params dict to execute(), not via .values() on
                # the statement (unlike the wallet update) -- so the values
                # live in `params`, not stmt.compile().params.
                p = params if params is not None else stmt.compile().params
                self.quota_updates.append(p)
                if self.quota_row is not None:
                    if "used_today" in p:
                        self.quota_row.used_today = p["used_today"]
                    if "reset_at" in p:
                        self.quota_row.reset_at = p["reset_at"]
                return result
            # Quota.__table__.select() -- a Core table select, so fetchone()
            # returns a Row with column attributes directly (unlike the
            # wallet's ORM-entity select, which is wrapped in a 1-tuple).
            result.fetchone.return_value = self.quota_row
            return result
        return result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


def _price(inp=1_000_000, out=1_000_000):
    # 1,000,000 IRT per million tokens -> 1 IRT per token, easy to hand-check.
    return types.SimpleNamespace(input_per_million=inp, output_per_million=out)


def _usage(total=1000, prompt=800, completion=200):
    return {"total_tokens": total, "prompt_tokens": prompt, "completion_tokens": completion}
