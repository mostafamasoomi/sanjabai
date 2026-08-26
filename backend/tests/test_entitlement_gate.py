"""Unit tests for services/entitlement_gate.py -- the shared helper that
connects services/entitlements.py (package request/token quotas; NOT
modified here, see its own test_entitlements.py) into the actual billing
decision: services/entitlement_gate.py's own fail-safe contract
(covering_entitlement/consume_for_usage/grant_for_payment never raise into
a caller) and chat_billing.py::_record_usage -- the single real charge
point -- consuming the entitlement at the REAL cost, before the wallet is
ever touched, instead of debiting the wallet.

Split out of the original tests/test_entitlement_wiring.py (which grew past
the 500-line cap) -- the HTTP-level tests (the four reservation call sites
in chat.py/chat_smart.py/chat_web.py/chat_compare.py, and the
payment_endpoints.py grant-on-payment-callback wiring) now live in
tests/test_entitlement_reservation_wiring.py. Both files drive their own
tests directly against the real code (this one calls services functions and
chat_billing._record_usage directly; the other goes through the app's
TestClient), never against a Python re-implementation of it.

House convention (see test_entitlements.py, test_billing_loss_paths.py):
assert against what the production code actually does, never against a
Python re-implementation of it. Where a fake DB is needed for
services/entitlements.py's raw SQL, this file reuses the exact fake already
adversarially hardened in test_entitlements.py (imported, not re-derived)
so a regression in the real SQL still shows up here too.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

import chat_billing
import services.entitlement_gate as gate_mod
import services.entitlements as ent_mod
from tests.test_billing_loss_paths import _FakeSession as _FakeBillingSession, _price, _usage
from tests.test_entitlements import (
    _FakeEntitlementDB,
    _FakeSession as _FakeEntSession,
    _Ctx as _EntCtx,
)


# ═══════════════════════════════════════════════════════════════════════
# Section 1: services/entitlement_gate.py unit tests (fail-safe contract)
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def ent_db():
    return _FakeEntitlementDB()


@pytest.fixture
def patched_ent(monkeypatch, ent_db):
    """Point services.entitlements' async_session at the fake DB shared
    with test_entitlements.py -- the SAME fake that exercises the real
    WHERE/UPDATE SQL, not a re-implementation of it."""
    monkeypatch.setattr(ent_mod, 'async_session', lambda: _EntCtx(_FakeEntSession(ent_db)))
    return ent_db


class _RaisingSession:
    """A DB session context manager that blows up on entry -- simulates a
    real outage (connection refused, pool exhausted, ...) at the point
    services/entitlements.py opens its own session."""

    async def __aenter__(self):
        raise RuntimeError('simulated db outage')

    async def __aexit__(self, *exc):
        return False


class TestCoveringEntitlementFailSafe:
    @pytest.mark.asyncio
    async def test_returns_entitlement_dict_when_covered(self, patched_ent):
        patched_ent.add_entitlement(user_id=1, requests_remaining=5, max_cost_per_request_toman=2000)
        found = await gate_mod.covering_entitlement(1, 1000)
        assert found is not None
        assert found['requests_remaining'] == 5

    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_covers(self, patched_ent):
        assert await gate_mod.covering_entitlement(1, 1000) is None

    @pytest.mark.asyncio
    async def test_lookup_exception_returns_none_not_raise(self, monkeypatch, caplog):
        monkeypatch.setattr(ent_mod, 'async_session', lambda: _RaisingSession())
        with caplog.at_level(logging.WARNING):
            result = await gate_mod.covering_entitlement(1, 1000)
        assert result is None
        assert any('covering_entitlement failed' in r.message for r in caplog.records)


class TestConsumeForUsageFailSafe:
    @pytest.mark.asyncio
    async def test_consumes_and_returns_entitlement_on_hit(self, patched_ent):
        eid = patched_ent.add_entitlement(user_id=1, requests_remaining=5, max_cost_per_request_toman=2000)
        found = await gate_mod.consume_for_usage(1, 1500, total_tokens=100)
        assert found is not None and found['id'] == eid
        assert patched_ent.entitlements[eid]['requests_remaining'] == 4

    @pytest.mark.asyncio
    async def test_ceiling_below_real_cost_returns_none(self, patched_ent):
        eid = patched_ent.add_entitlement(user_id=1, requests_remaining=5, max_cost_per_request_toman=500)
        assert await gate_mod.consume_for_usage(1, 1500, total_tokens=100) is None
        assert patched_ent.entitlements[eid]['requests_remaining'] == 5  # untouched

    @pytest.mark.asyncio
    async def test_consume_race_to_zero_returns_none(self, patched_ent, monkeypatch):
        """find_covering_entitlement finds a hit, but consume_entitlement's
        own atomic UPDATE fails (raced to zero by a concurrent request) --
        its documented contract is that the caller falls back to the
        wallet; consume_for_usage must honour that (return None), not
        pretend the entitlement paid."""
        patched_ent.add_entitlement(user_id=1, requests_remaining=5, max_cost_per_request_toman=2000)
        monkeypatch.setattr(gate_mod, 'consume_entitlement', AsyncMock(return_value=False))
        assert await gate_mod.consume_for_usage(1, 1000, total_tokens=10) is None

    @pytest.mark.asyncio
    async def test_exception_anywhere_returns_none_not_raise(self, monkeypatch, caplog):
        monkeypatch.setattr(ent_mod, 'async_session', lambda: _RaisingSession())
        with caplog.at_level(logging.WARNING):
            result = await gate_mod.consume_for_usage(1, 1000, total_tokens=10)
        assert result is None
        assert any('consume_for_usage failed' in r.message for r in caplog.records)


class TestGrantForPaymentFailSafe:
    @pytest.mark.asyncio
    async def test_grants_when_package_has_a_quota(self, patched_ent):
        patched_ent.add_package('pkg-quota', request_quota=500, max_cost_per_request_toman=5000)
        result = await gate_mod.grant_for_payment(1, 'pkg-quota', 'AUTH1')
        assert result is not None
        assert result['requests_remaining'] == 500
        assert result['source_payment_id'] == 'AUTH1'

    @pytest.mark.asyncio
    async def test_quota_less_package_is_a_clean_noop(self, patched_ent):
        patched_ent.add_package('pkg-none')  # all NULL
        assert await gate_mod.grant_for_payment(1, 'pkg-none', 'AUTH1') is None
        assert patched_ent.entitlements == {}

    @pytest.mark.asyncio
    async def test_exception_is_swallowed_and_logged_at_error(self, monkeypatch, caplog):
        monkeypatch.setattr(ent_mod, 'async_session', lambda: _RaisingSession())
        with caplog.at_level(logging.ERROR):
            result = await gate_mod.grant_for_payment(1, 'pkg-quota', 'AUTH1')
        assert result is None
        assert any('grant_for_payment FAILED' in r.message for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════
# Section 2: chat_billing._record_usage -- the single real charge point
# ═══════════════════════════════════════════════════════════════════════

class TestRecordUsageEntitlementWiring:
    @pytest.mark.asyncio
    async def test_covered_request_paid_by_quota_never_touches_wallet(self, patched_ent):
        """The core "never both" guarantee: cost is 0 to the wallet,
        balance_after is the REAL (unmoved) balance, no Ledger row, and the
        entitlement is consumed exactly once."""
        eid = patched_ent.add_entitlement(user_id=1, requests_remaining=10, max_cost_per_request_toman=10_000)
        session = _FakeBillingSession(wallet_balance=1_000_000, price=_price())
        result = await chat_billing._record_usage(
            session, uid=1, payload={'model': 'kr/gpt-4o-mini'}, usage=_usage(),
        )
        assert result['cost'] == 0
        assert result['balance_after'] == 1_000_000
        assert session.wallet.balance == 1_000_000
        assert [o for o in session.added if type(o).__name__ == 'Ledger'] == []
        usage_events = [o for o in session.added if type(o).__name__ == 'UsageEvent']
        assert len(usage_events) == 1
        assert usage_events[0].charged_amount == 0
        assert usage_events[0].meta['billing_source'] == 'entitlement'
        assert usage_events[0].meta['entitlement_id'] == eid
        assert patched_ent.entitlements[eid]['requests_remaining'] == 9

    @pytest.mark.asyncio
    async def test_ceiling_below_real_cost_falls_through_to_wallet(self, patched_ent):
        """Estimate at reserve time can be lower than the real cost; the
        ceiling is re-checked here against what was ACTUALLY served."""
        eid = patched_ent.add_entitlement(user_id=1, requests_remaining=10, max_cost_per_request_toman=500)
        session = _FakeBillingSession(wallet_balance=1_000_000, price=_price())
        result = await chat_billing._record_usage(
            session, uid=1, payload={'model': 'kr/gpt-4o-mini'}, usage=_usage(),
        )
        assert result['cost'] == 1000  # normal wallet-priced cost, unaffected
        assert session.wallet.balance == 1_000_000 - 1000
        ledger_rows = [o for o in session.added if type(o).__name__ == 'Ledger']
        assert len(ledger_rows) == 1
        assert ledger_rows[0].amount == -1000
        assert patched_ent.entitlements[eid]['requests_remaining'] == 10  # untouched

    @pytest.mark.asyncio
    async def test_consume_entitlement_false_falls_through_to_wallet(self, patched_ent, monkeypatch):
        """consume_entitlement racing to zero/expiring between find and
        consume must never leave the request unbilled -- it must land on
        the wallet, same as an uncovered request."""
        eid = patched_ent.add_entitlement(user_id=1, requests_remaining=10, max_cost_per_request_toman=10_000)
        monkeypatch.setattr(gate_mod, 'consume_entitlement', AsyncMock(return_value=False))
        session = _FakeBillingSession(wallet_balance=1_000_000, price=_price())
        result = await chat_billing._record_usage(
            session, uid=1, payload={'model': 'kr/gpt-4o-mini'}, usage=_usage(),
        )
        assert result['cost'] == 1000
        assert session.wallet.balance == 1_000_000 - 1000
        assert len([o for o in session.added if type(o).__name__ == 'Ledger']) == 1
        assert patched_ent.entitlements[eid]['requests_remaining'] == 10  # find hit it, consume never touched it

    @pytest.mark.asyncio
    async def test_entitlement_db_outage_falls_through_to_wallet(self, monkeypatch):
        """An exception anywhere in the entitlement path (here: the DB
        itself failing) must never make the request free and must never
        take billing down -- normal wallet billing keeps working."""
        monkeypatch.setattr(ent_mod, 'async_session', lambda: _RaisingSession())
        session = _FakeBillingSession(wallet_balance=1_000_000, price=_price())
        result = await chat_billing._record_usage(
            session, uid=1, payload={'model': 'kr/gpt-4o-mini'}, usage=_usage(),
        )
        assert result['cost'] == 1000
        assert session.wallet.balance == 1_000_000 - 1000
        assert len([o for o in session.added if type(o).__name__ == 'Ledger']) == 1

    @pytest.mark.asyncio
    async def test_no_entitlement_at_all_bills_wallet_exactly_as_before(self, patched_ent):
        """Baseline: with zero entitlements for this user, behavior must be
        byte-for-byte the old wallet-only path (no entitlement lookup
        should change cost/ledger shape when nothing exists to find)."""
        session = _FakeBillingSession(wallet_balance=1_000_000, price=_price())
        result = await chat_billing._record_usage(
            session, uid=1, payload={'model': 'kr/gpt-4o-mini'}, usage=_usage(),
        )
        assert result['cost'] == 1000
        assert result['balance_after'] == 1_000_000 - 1000
        ledger_rows = [o for o in session.added if type(o).__name__ == 'Ledger']
        assert len(ledger_rows) == 1
        assert ledger_rows[0].amount == -1000
