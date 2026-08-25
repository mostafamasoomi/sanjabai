"""Two guards added to backend/admin_pricing.py after a live-panel audit of
تعرفه‌ها (owner report: "some parts don't work properly").

1. Currency lock (`set_pricing`): the admin panel's «واحد پول» field used to
   be free text that round-tripped straight into `UPDATE model_catalog SET
   currency=:cur`. model_catalog's own CHECK constraint only allows
   'IRR'/'IRT', so anything else 500'd with a bare "Internal Server Error"
   -- reproduced live against production and confirmed the row was left
   untouched (the constraint blocks the write, but the admin got no
   explanation). Even 'IRR' must be refused here: the project's money law
   is that the internal unit is ALWAYS integer Toman and a Rial conversion
   happens only in the payment-gateway adapter -- this admin surface must
   never be the place that mislabels a Toman price as something else.

2. Toggle-state guard (`toggle_model`): model_catalog.availability has four
   values (available/degraded/maintenance/disabled -- see the CHECK
   constraint), but the endpoint's flip was binary: anything that wasn't
   literally 'available' was treated as "should become available". Live
   evidence this already bit someone: audit_logs shows
   bynaraa2/agnes-2.0-flash toggled available->disabled->available->disabled
   in a 9-second span this session, ending on 'disabled' though its sibling
   rows (bynara/agnes-2.0-flash, freellmapi/agnes-2.0-flash) are still
   'maintenance' -- someone tried to toggle a maintenance-status row back to
   its original state and the binary flip made that impossible, because it
   only ever alternates available<->disabled. Promoting a 'maintenance' or
   'degraded' row to 'available' is meant to happen only through a live
   probe (model_health_policy.py) or the bulk-availability endpoint, both of
   which the product's "برچسب صادقانه" rule requires; a misclick on this
   quick single-row button must not bypass that.
"""
from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

import admin_pricing as admin_pricing_mod
from tests.conftest import make_result, make_row


@pytest.fixture
def admin_ok():
    with patch('admin.admin_required', new=AsyncMock(return_value=True)):
        yield


class TestCurrencyIsLockedToToman:
    """POST /admin/pricing -- the «واحد پول» field."""

    def test_irt_is_accepted(self, client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='available'))
        mock_async_session._execute_result.rowcount = 1
        with patch.object(admin_pricing_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/pricing', json={
                'model': 'agnes-2.0-flash', 'input_per_million': 100, 'output_per_million': 200,
                'currency': 'IRT',
            })
        assert resp.status_code == 200

    def test_missing_currency_defaults_to_irt_and_is_accepted(self, client, admin_ok, mock_async_session):
        """Omitting the field (older callers, or a client that never sends
        it) must keep working -- the lock only rejects an explicit non-IRT
        value, it does not make the field newly required."""
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='available'))
        mock_async_session._execute_result.rowcount = 1
        with patch.object(admin_pricing_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/pricing', json={
                'model': 'agnes-2.0-flash', 'input_per_million': 100, 'output_per_million': 200,
            })
        assert resp.status_code == 200

    @pytest.mark.parametrize('bad_currency', ['IRR', 'USD', 'toman', 'تومان', ''])
    def test_any_other_currency_is_refused_with_400_not_500(self, client, admin_ok, mock_async_session, bad_currency):
        resp = client.post('/admin/pricing', json={
            'model': 'agnes-2.0-flash', 'input_per_million': 100, 'output_per_million': 200,
            'currency': bad_currency,
        })
        assert resp.status_code == 400
        assert 'تومان' in resp.json()['detail']

    def test_refused_currency_never_reaches_the_database(self, client, admin_ok, mock_async_session):
        """The bug this closes: model_catalog's CHECK constraint used to be
        the only thing stopping a bad currency, which meant the write was
        already attempted and the failure came back as a raw 500. The
        Python-level guard must refuse before any UPDATE is issued."""
        executed = []

        async def _execute(stmt, params=None, *a, **k):
            executed.append(str(stmt))
            return make_result(fetchone=make_row(availability='available'))

        mock_async_session.execute = _execute
        client.post('/admin/pricing', json={
            'model': 'agnes-2.0-flash', 'input_per_million': 100, 'output_per_million': 200,
            'currency': 'USD',
        })
        assert not any('UPDATE model_catalog' in sql for sql in executed)


class TestToggleRefusesNonBinaryStates:
    """POST /admin/models/{id}/toggle -- must not promote maintenance/degraded."""

    @pytest.mark.parametrize('state', ['maintenance', 'degraded'])
    def test_toggle_on_non_binary_state_is_refused(self, client, admin_ok, mock_async_session, state):
        mock_async_session._execute_result = make_result(fetchone=make_row(availability=state))
        resp = client.post('/admin/models/some/model/toggle')
        assert resp.status_code == 400
        assert 'عملیات کاتالوگ' in resp.json()['detail']

    @pytest.mark.parametrize('state', ['maintenance', 'degraded'])
    def test_toggle_on_non_binary_state_writes_no_update(self, client, admin_ok, mock_async_session, state):
        executed = []

        async def _execute(stmt, params=None, *a, **k):
            executed.append(str(stmt))
            return make_result(fetchone=make_row(availability=state))

        mock_async_session.execute = _execute
        client.post('/admin/models/some/model/toggle')
        assert not any('UPDATE model_catalog' in sql for sql in executed)

    def test_refusal_is_audited(self, client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='maintenance'))
        with patch.object(admin_pricing_mod, '_write_audit_log', new=AsyncMock()) as audit:
            client.post('/admin/models/some/model/toggle')
        audit.assert_awaited()
        assert audit.await_args.args[0] == 'admin.model.toggle_refused'

    def test_available_still_flips_to_disabled(self, client, admin_ok, mock_async_session):
        """Regression guard: the fix must not touch the two states the
        button is actually for."""
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='available'))
        mock_async_session._execute_result.rowcount = 1
        with patch.object(admin_pricing_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/models/some/model/toggle')
        assert resp.status_code == 200
        assert resp.json()['availability'] == 'disabled'

    def test_disabled_still_flips_to_available(self, client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=make_row(availability='disabled'))
        mock_async_session._execute_result.rowcount = 1
        with patch.object(admin_pricing_mod, 'rds', AsyncMock()):
            resp = client.post('/admin/models/some/model/toggle')
        assert resp.status_code == 200
        assert resp.json()['availability'] == 'available'
