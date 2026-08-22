"""Wiring tests for services/entitlement_gate.py -- the shared helper that
connects services/entitlements.py (package request/token quotas; NOT
modified here, see its own test_entitlements.py) into:

  1. payment_endpoints.py -- grant a quota entitlement after a completed
     credit_package payment (non-fatal to the callback).
  2. The four reservation sites (chat.py, chat_smart.py, chat_web.py,
     chat_compare.py x2) -- pre-authorize a request against an entitlement
     and skip the wallet reservation when one covers it.
  3. chat_billing.py::_record_usage -- the single real charge point --
     consume the entitlement at the REAL cost, before the wallet is ever
     touched, instead of debiting the wallet.

House convention (see test_entitlements.py, test_billing_loss_paths.py):
assert against what the production code actually does, never against a
Python re-implementation of it. Where a fake DB is needed for
services/entitlements.py's raw SQL, this file reuses the exact fake already
adversarially hardened in test_entitlements.py (imported, not re-derived)
so a regression in the real SQL still shows up here too.
"""
from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
import chat_billing
import chat_compare as chat_compare_mod
import chat_smart as chat_smart_mod
import chat_web as chat_web_mod
import services.entitlement_gate as gate_mod
import services.entitlements as ent_mod
from services.billing import InsufficientBalanceError
from tests.conftest import make_row
from tests.test_billing_loss_paths import _FakeSession as _FakeBillingSession, _price, _usage
from tests.test_entitlements import (
    _FakeEntitlementDB,
    _FakeSession as _FakeEntSession,
    _Ctx as _EntCtx,
    _row as _ent_row,
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


# ═══════════════════════════════════════════════════════════════════════
# Section 3: the four reservation sites skip the wallet when covered
# ═══════════════════════════════════════════════════════════════════════

def _billing_instance(*, raise_on_reserve: bool) -> MagicMock:
    inst = MagicMock()
    if raise_on_reserve:
        # If reserve() is ever actually awaited in the "covered" tests
        # below, this blows up exactly like an empty wallet would -- proof
        # that reserve() was genuinely skipped, not just uninteresting.
        inst.reserve = AsyncMock(side_effect=InsufficientBalanceError('insufficient'))
    else:
        inst.reserve = AsyncMock(return_value={'reservation_id': 'r1'})
    inst.release = AsyncMock(return_value=None)
    return inst


class TestChatCompletionsReserveSite:
    def test_covered_empty_wallet_request_is_not_rejected(self, client, mock_async_session):
        billing_instance = _billing_instance(raise_on_reserve=True)
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='kr/gpt-4o-mini')), \
             patch.object(chat_mod, '_apply_persian_style_guard_for_model', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'covering_entitlement', AsyncMock(return_value={'id': 1})), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing_instance)):
            resp = client.post('/v1/chat/completions', json={
                'model': 'kr/gpt-4o-mini', 'messages': [{'role': 'user', 'content': 'سلام'}],
            })
        billing_instance.reserve.assert_not_awaited()
        assert resp.status_code != 429
        assert 'کافی نیست' not in resp.text

    def test_uncovered_empty_wallet_request_is_still_rejected(self, client, mock_async_session):
        """Baseline, unchanged behavior: no entitlement -> normal 429."""
        billing_instance = _billing_instance(raise_on_reserve=True)
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='kr/gpt-4o-mini')), \
             patch.object(chat_mod, '_apply_persian_style_guard_for_model', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'covering_entitlement', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing_instance)):
            resp = client.post('/v1/chat/completions', json={
                'model': 'kr/gpt-4o-mini', 'messages': [{'role': 'user', 'content': 'سلام'}],
            })
        billing_instance.reserve.assert_awaited_once()
        assert resp.status_code == 429
        assert 'کافی نیست' in resp.text


class TestSmartChatReserveSite:
    def test_covered_empty_wallet_request_is_not_rejected(self, client, mock_async_session):
        billing_instance = _billing_instance(raise_on_reserve=True)
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_smart_mod, '_get_user_balance', AsyncMock(return_value=0)), \
             patch.object(chat_smart_mod, '_get_user_plan', AsyncMock(return_value='free')), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='kr/gpt-4o-mini')), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)), \
             patch.object(chat_mod, '_apply_persian_style_guard_for_model', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)), \
             patch.object(chat_smart_mod, 'covering_entitlement', AsyncMock(return_value={'id': 1})), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing_instance)):
            resp = client.post(
                '/v1/smart-chat',
                json={'messages': [{'role': 'user', 'content': 'سلام'}]},
                headers={'X-Smart-Model': 'kr/gpt-4o-mini'},
            )
        billing_instance.reserve.assert_not_awaited()
        assert resp.status_code != 429
        assert 'کافی نیست' not in resp.text


class TestChatWithFileReserveSite:
    def test_covered_empty_wallet_request_is_not_rejected(self, client, mock_async_session):
        billing_instance = _billing_instance(raise_on_reserve=True)
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='kr/gpt-4o-mini')), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)), \
             patch.object(chat_web_mod, 'covering_entitlement', AsyncMock(return_value={'id': 1})), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing_instance)):
            resp = client.post(
                '/v1/chat/with-file',
                data={
                    'model': 'kr/gpt-4o-mini',
                    'messages': json.dumps([{'role': 'user', 'content': 'سلام'}]),
                    'stream': 'false',
                },
                files={'file': ('note.txt', b'hello world', 'text/plain')},
            )
        billing_instance.reserve.assert_not_awaited()
        assert resp.status_code != 429
        assert 'کافی نیست' not in resp.text


class TestCompareReserveSites:
    """chat_compare.py reserves twice (once per model) -- each check is
    independent and read-only, so both models can be pre-authorized off the
    SAME entitlement (real spend is decided later, atomically, per model,
    at each model's own _record_usage call)."""

    def test_both_models_covered_neither_reserves(self, client, mock_async_session):
        billing_instance = _billing_instance(raise_on_reserve=True)
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(side_effect=lambda m: m)), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_compare_mod, 'covering_entitlement', AsyncMock(return_value={'id': 1})), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing_instance)), \
             patch.object(chat_compare_mod, '_call_model_once',
                           AsyncMock(side_effect=lambda *a, **k: {'content': 'ok', 'model': 'x', 'elapsed': 0.1, 'cost': 0})):
            resp = client.post('/v1/compare', json={
                'model_a': 'model-a', 'model_b': 'model-b',
                'messages': [{'role': 'user', 'content': 'سلام'}],
            })
        billing_instance.reserve.assert_not_awaited()
        assert resp.status_code == 200, resp.text

    def test_only_first_model_covered_second_still_reserves(self, client, mock_async_session):
        """Not an all-or-nothing gate: model_a's check hits, model_b's
        doesn't -- model_b must still go through the normal wallet
        reservation on its own."""
        billing_instance = _billing_instance(raise_on_reserve=False)
        with patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)), \
             patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)), \
             patch.object(chat_mod, '_resolve_public_model', AsyncMock(side_effect=lambda m: m)), \
             patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)), \
             patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)), \
             patch.object(chat_compare_mod, 'covering_entitlement', AsyncMock(side_effect=[{'id': 1}, None])), \
             patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing_instance)), \
             patch.object(chat_compare_mod, '_call_model_once',
                           AsyncMock(side_effect=lambda *a, **k: {'content': 'ok', 'model': 'x', 'elapsed': 0.1, 'cost': 0})):
            resp = client.post('/v1/compare', json={
                'model_a': 'model-a', 'model_b': 'model-b',
                'messages': [{'role': 'user', 'content': 'سلام'}],
            })
        billing_instance.reserve.assert_awaited_once()
        assert resp.status_code == 200, resp.text


# ═══════════════════════════════════════════════════════════════════════
# Section 4: payment_endpoints.py -- grant on a completed credit_package
# ═══════════════════════════════════════════════════════════════════════

def _payment_row(*, authority='AUTH1', reference_id='pkg1', user_id=7):
    payment = make_row(
        id=42, user_id=user_id, amount=100_000, authority=authority,
        status='pending', payment_type='credit_package', reference_id=reference_id,
        ref_id=None, verified_at=None,
    )
    return (payment,)


def _credit_package_row(*, pkg_id='pkg1', total_credits=100_000, base_amount=100_000, bonus_percent=0):
    pkg = make_row(
        id=pkg_id, name_fa='بسته تست', name_en='Test package',
        base_amount=base_amount, bonus_percent=bonus_percent, total_credits=total_credits,
        model_id='mimo-v2.5-pro', active=True,
    )
    return (pkg,)


def _grant_execute(payment_row_tuple, package_row_tuple, ent_db: _FakeEntitlementDB):
    """Dispatches BOTH payment_endpoints.py's ORM queries (payments /
    credit_packages) AND services.entitlements.py's raw-SQL queries
    (credit_packages quota columns, package_entitlement insert + replay
    read-back) against the SAME mocked session -- so these tests exercise
    the REAL grant_entitlement() code, not a stand-in for it."""
    async def mock_execute(stmt, params=None, *a, **k):
        sql = str(stmt)
        params = params or {}
        result = MagicMock()
        result.fetchone.return_value = None

        if 'request_quota' in sql and 'FROM credit_packages' in sql:
            pkg = ent_db.packages.get(params.get('package_id'))
            result.fetchone.return_value = _ent_row(pkg) if pkg is not None else None
            return result

        if sql.strip().startswith('INSERT INTO package_entitlement'):
            pkg_id, spid = params['package_id'], params['source_payment_id']
            dup = spid is not None and any(
                r['package_id'] == pkg_id and r['source_payment_id'] == spid
                for r in ent_db.entitlements.values()
            )
            if dup:
                return result  # ON CONFLICT DO NOTHING
            eid = ent_db.add_entitlement(
                user_id=params['user_id'], package_id=pkg_id,
                requests_remaining=params['requests_remaining'],
                tokens_remaining=params['tokens_remaining'],
                max_cost_per_request_toman=params['max_cost_per_request_toman'],
                expires_at=params['expires_at'], active=True,
                source_payment_id=spid,
            )
            result.fetchone.return_value = _ent_row(ent_db.entitlements[eid])
            return result

        if 'FROM package_entitlement' in sql and 'source_payment_id = :source_payment_id' in sql:
            for row in ent_db.entitlements.values():
                if row['package_id'] == params.get('package_id') and row['source_payment_id'] == params.get('source_payment_id'):
                    result.fetchone.return_value = _ent_row(row)
                    return result
            return result

        if 'FROM payments' in sql:
            result.fetchone.return_value = payment_row_tuple
            return result

        if 'FROM credit_packages' in sql:
            result.fetchone.return_value = package_row_tuple
            return result

        return result
    return mock_execute


class TestPaymentCallbackGrantsEntitlement:
    def test_grant_happens_on_completed_credit_package_payment(self, client, mock_async_session):
        ent_db = _FakeEntitlementDB()
        ent_db.add_package('pkg1', request_quota=500, token_quota=None, validity_days=30, max_cost_per_request_toman=5000)
        mock_async_session.execute = _grant_execute(_payment_row(), _credit_package_row(), ent_db)

        from payment import CallbackResult
        with patch('payment_endpoints.handle_payment_callback', new=AsyncMock(return_value=CallbackResult(ok=True, ref_id='REF1', amount=100_000))):
            resp = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'OK'})

        assert resp.status_code == 200
        body = resp.json()
        assert body['credits_added'] == 100_000  # wallet credit reporting unaffected
        assert body['entitlement']['requests_remaining'] == 500

        assert len(ent_db.entitlements) == 1
        row = next(iter(ent_db.entitlements.values()))
        assert row['user_id'] == 7
        assert row['package_id'] == 'pkg1'
        assert row['source_payment_id'] == 'AUTH1'  # stable across a replay -- see class below
        assert row['requests_remaining'] == 500

    def test_grant_failure_does_not_fail_the_callback(self, client, mock_async_session, caplog):
        """The user already paid and the wallet was already credited by the
        time this code runs -- a quota-row failure must never fail the
        callback or change the redirect/credits_added the user sees."""
        ent_db = _FakeEntitlementDB()
        mock_async_session.execute = _grant_execute(_payment_row(), _credit_package_row(), ent_db)

        from payment import CallbackResult
        with patch('payment_endpoints.handle_payment_callback', new=AsyncMock(return_value=CallbackResult(ok=True, ref_id='REF1', amount=100_000))), \
             patch('services.entitlement_gate.grant_for_payment', new=AsyncMock(side_effect=RuntimeError('boom'))), \
             caplog.at_level(logging.ERROR):
            resp = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'OK'})

        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'ok'
        assert body['credits_added'] == 100_000
        assert 'entitlement' not in body
        assert any('entitlement grant threw' in r.message for r in caplog.records)

    def test_replayed_callback_does_not_grant_twice(self, client, mock_async_session):
        """handle_payment_callback's own payment-row lock is expected to
        reject a genuine replay before this code is even reached -- this
        proves the entitlement layer is ALSO safe if it is ever reached
        twice for the same payment (migration 0034's unique index, see
        services/entitlements.py::grant_entitlement's ON CONFLICT DO
        NOTHING)."""
        ent_db = _FakeEntitlementDB()
        ent_db.add_package('pkg1', request_quota=500, max_cost_per_request_toman=5000)
        mock_async_session.execute = _grant_execute(_payment_row(), _credit_package_row(), ent_db)

        from payment import CallbackResult
        with patch('payment_endpoints.handle_payment_callback', new=AsyncMock(return_value=CallbackResult(ok=True, ref_id='REF1', amount=100_000))):
            resp1 = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'OK'})
            resp2 = client.get('/payment/callback', params={'Authority': 'AUTH1', 'Status': 'OK'})

        assert resp1.status_code == 200 and resp2.status_code == 200
        assert len(ent_db.entitlements) == 1  # not 2
        row = next(iter(ent_db.entitlements.values()))
        assert row['requests_remaining'] == 500  # granting never consumes
        assert resp2.json()['entitlement']['requests_remaining'] == 500
