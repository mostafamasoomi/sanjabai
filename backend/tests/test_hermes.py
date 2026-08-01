"""
Tests for the Hermes server product (backend/hermes.py).

Split into two groups:

1. Pure-Python unit tests (pricing math, options validation, public-shape
   redaction) -- no HTTP, no mocked Redis/DB, deterministic.
2. HTTP-level tests via the shared ``client``/``mock_async_session``
   fixtures, following the same pattern as test_wallet.py / test_admin.py
   (auth via `patch('app.rds.get', ...)`, admin via the `x-admin-token`
   header).
"""
import asyncio
from decimal import Decimal
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from tests.conftest import make_result, make_row, ADMIN_TOKEN

import hermes
from models import HermesOffering, HermesServer


def _offering(**overrides) -> HermesOffering:
    defaults = dict(
        id='hermes-standard', name_fa='استاندارد', name_en='Standard',
        description_fa='', description_en='', hetzner_type='cx32', arch='amd64',
        vcpu=4, ram_mb=8192, disk_gb=80, traffic_tb=20,
        provider_cost_eur=Decimal('6.80'), margin_pct=50, setup_fee_irt=0,
        max_skills=5, included_credit=0, active=True, sort_order=0,
    )
    defaults.update(overrides)
    return HermesOffering(**defaults)


# ══════════════════════════════════════════════════════════════════
# 1. Pure-Python unit tests
# ══════════════════════════════════════════════════════════════════

class TestRounding:
    def test_round_up_1000_exact(self):
        assert hermes._round_up_1000(50000.0) == 50000

    def test_round_up_1000_rounds_up(self):
        assert hermes._round_up_1000(50001.0) == 51000

    def test_round_up_1000_returns_int(self):
        result = hermes._round_up_1000(12345.67)
        assert isinstance(result, int)
        assert result == 13000


class TestPriceOffering:
    def test_formula_and_integer_toman(self):
        """monthly_price_irt = round_up_1000(cost_eur * eur_rate * (1 + margin/100)),
        and it must be a plain int -- no floats leak into the money path."""
        offering = _offering(provider_cost_eur=Decimal('10.00'), margin_pct=50)
        with patch('hermes._get_cached_eur_to_irt', new=AsyncMock(return_value=100_000.0)):
            setup, monthly, rate = asyncio.run(
                hermes._price_offering(offering)
            )
        # 10 EUR * 100,000 IRT/EUR * 1.5 margin = 1,500,000 IRT exactly.
        assert monthly == 1_500_000
        assert isinstance(monthly, int)
        assert isinstance(setup, int)
        assert rate == 100_000.0

    def test_setup_fee_independent_of_rate(self):
        offering = _offering(setup_fee_irt=200_000)
        with patch('hermes._get_cached_eur_to_irt', new=AsyncMock(return_value=999_999.0)):
            setup, _monthly, _rate = asyncio.run(
                hermes._price_offering(offering)
            )
        assert setup == 200_000

    def test_price_locked_against_later_rate_change(self):
        """Simulates the price-lock guarantee: computing twice with two
        different rates must NOT produce the same price, proving the price
        is genuinely rate-dependent at compute time -- callers are
        responsible for freezing the result on the order, which is what
        makes the lock work (see hermes.create_order)."""
        offering = _offering()
        with patch('hermes._get_cached_eur_to_irt', new=AsyncMock(return_value=100_000.0)):
            _setup1, monthly_at_t1, _r1 = asyncio.run(
                hermes._price_offering(offering)
            )
        with patch('hermes._get_cached_eur_to_irt', new=AsyncMock(return_value=200_000.0)):
            _setup2, monthly_at_t2, _r2 = asyncio.run(
                hermes._price_offering(offering)
            )
        assert monthly_at_t1 != monthly_at_t2


class TestOfferingPublicShape:
    def test_no_eur_fields_leak(self):
        offering = _offering()
        public = hermes._offering_public(offering, setup_price_irt=0, monthly_price_irt=1_200_000)
        assert 'provider_cost_eur' not in public
        assert 'margin_pct' not in public
        assert 'hetzner_type' not in public  # internal cost/sourcing detail
        assert public['currency'] == 'IRT'
        assert public['monthly_price_irt'] == 1_200_000


class TestValidateSkillOptions:
    SCHEMA = {
        'languages': {'type': 'multiselect', 'values': ['python', 'go', 'rust'], 'max': 2},
        'topics': {'type': 'tags', 'max': 3},
        'schedule': {'type': 'cron'},
    }

    def test_valid_options_pass(self):
        assert hermes._validate_skill_options(self.SCHEMA, {'languages': ['python', 'go']}) is None

    def test_multiselect_disallowed_value_rejected(self):
        err = hermes._validate_skill_options(self.SCHEMA, {'languages': ['python', 'cobol']})
        assert err is not None

    def test_multiselect_over_max_rejected(self):
        err = hermes._validate_skill_options(self.SCHEMA, {'languages': ['python', 'go', 'rust']})
        assert err is not None

    def test_tags_over_max_rejected(self):
        err = hermes._validate_skill_options(self.SCHEMA, {'topics': ['a', 'b', 'c', 'd']})
        assert err is not None

    def test_cron_empty_rejected(self):
        err = hermes._validate_skill_options(self.SCHEMA, {'schedule': ''})
        assert err is not None

    def test_cron_valid_passes(self):
        assert hermes._validate_skill_options(self.SCHEMA, {'schedule': '0 9 * * *'}) is None

    def test_unknown_keys_ignored(self):
        assert hermes._validate_skill_options(self.SCHEMA, {'nonsense': 123}) is None

    def test_non_dict_options_rejected(self):
        assert hermes._validate_skill_options(self.SCHEMA, ['not', 'a', 'dict']) is not None


# ══════════════════════════════════════════════════════════════════
# 2. HTTP-level tests
# ══════════════════════════════════════════════════════════════════

class TestOrdersAuth:
    def test_create_order_unauthenticated(self, client):
        with patch('app.rds.get', return_value=None):
            response = client.post('/hermes/orders', json={'offering_id': 'hermes-standard', 'config': {'skills': []}})
            assert response.status_code == 401

    def test_list_orders_unauthenticated(self, client):
        with patch('app.rds.get', return_value=None):
            response = client.get('/hermes/orders')
            assert response.status_code == 401

    def test_list_servers_unauthenticated(self, client):
        with patch('app.rds.get', return_value=None):
            response = client.get('/hermes/servers')
            assert response.status_code == 401


class TestOrdersOwnership:
    """Orders/servers loaded by id are checked against the caller's uid in
    Python (see hermes._load_owned_server / get_order) -- a row owned by a
    different user must come back as 404, never leak."""

    def test_get_order_not_owned_returns_404(self, client, mock_async_session):
        other_users_order = make_row(id=5, user_id=999, offering_id='hermes-standard', status='paid')
        mock_async_session._execute_result = make_result(scalar_one_or_none=other_users_order)
        with patch('app.rds.get', return_value='1'), patch('app.rds.expire'):
            response = client.get('/hermes/orders/5', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 404

    def test_get_server_not_owned_returns_404(self, client, mock_async_session):
        other_users_server = make_row(id=7, user_id=999, offering_id='hermes-standard')
        mock_async_session._execute_result = make_result(scalar_one_or_none=other_users_server)
        with patch('app.rds.get', return_value='1'), patch('app.rds.expire'):
            response = client.get('/hermes/servers/7', headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 404


class TestMaxSkillsCap:
    def test_order_rejects_more_skills_than_offering_allows(self, client, mock_async_session):
        offering_row = _offering(max_skills=1)
        mock_async_session._execute_result = make_result(scalar_one_or_none=offering_row)
        with patch('app.rds.get', return_value='1'), patch('app.rds.expire'):
            response = client.post('/hermes/orders', json={
                'offering_id': 'hermes-standard',
                'config': {'skills': [
                    {'skill_id': 'coding', 'options': {}},
                    {'skill_id': 'news-watch', 'options': {}},
                ]},
            }, headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 400

    def test_order_rejects_unknown_offering(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(scalar_one_or_none=None)
        with patch('app.rds.get', return_value='1'), patch('app.rds.expire'):
            response = client.post('/hermes/orders', json={
                'offering_id': 'does-not-exist', 'config': {'skills': []},
            }, headers={'Authorization': 'Bearer valid'})
            assert response.status_code == 404


class TestAgentAuth:
    def test_agent_state_missing_token_rejected(self, client):
        response = client.get('/hermes/agent/state')
        assert response.status_code == 401

    def test_agent_state_malformed_token_rejected(self, client):
        response = client.get('/hermes/agent/state', headers={'Authorization': 'Bearer sk-not-an-agent-token'})
        assert response.status_code == 401

    def test_agent_state_unknown_token_rejected(self, client, mock_async_session):
        mock_async_session._execute_result = make_result(scalar_one_or_none=None)
        response = client.get('/hermes/agent/state', headers={'Authorization': 'Bearer hsa-wrong-token'})
        assert response.status_code == 401

    def test_agent_report_missing_token_rejected(self, client):
        response = client.post('/hermes/agent/report', json={'version': 1, 'results': []})
        assert response.status_code == 401


class TestAdminAuth:
    def test_admin_orders_requires_token(self, client):
        response = client.get('/admin/hermes/orders')
        assert response.status_code == 401

    def test_admin_provision_requires_token(self, client):
        response = client.post('/admin/hermes/orders/1/provision', json={
            'ip_address': '1.2.3.4', 'ssh_port': 22,
        })
        assert response.status_code == 401

    def test_admin_provision_rejects_non_paid_order(self, client, mock_async_session):
        pending_order = make_row(id=1, status='pending_payment', user_id=1, offering_id='hermes-standard', requested_config={})
        mock_async_session._execute_result = make_result(scalar_one_or_none=pending_order)
        response = client.post(
            '/admin/hermes/orders/1/provision',
            json={'ip_address': '1.2.3.4', 'ssh_port': 22},
            headers={'x-admin-token': ADMIN_TOKEN},
        )
        assert response.status_code == 400


class TestDesiredStateVersionBump:
    def test_attach_skill_bumps_desired_version(self, client, mock_async_session):
        server = HermesServer(
            id=3, order_id=1, user_id=1, offering_id='hermes-standard', status='active',
            monthly_price_irt=1_000_000, desired_state_version=2, applied_state_version=2,
        )
        skill = make_row(id='coding', options_schema={}, active=True)
        offering = _offering(max_skills=5)

        # The endpoint issues several sequential queries (server, skill,
        # offering, existing-count, duplicate-check); mock_async_session
        # only supports one fixed result, so drive it with a side-effect
        # queue that returns each in turn.
        results = iter([
            make_result(scalar_one_or_none=server),
            make_result(scalar_one_or_none=skill),
            make_result(scalar_one_or_none=offering),
            make_result(fetchall=[]),
            make_result(scalar_one_or_none=None),
        ])

        async def _execute(*args, **kwargs):
            return next(results)

        mock_async_session.execute = _execute

        with patch('app.rds.get', return_value='1'), patch('app.rds.expire'):
            response = client.post(
                '/hermes/servers/3/skills',
                json={'skill_id': 'coding', 'options': {}},
                headers={'Authorization': 'Bearer valid'},
            )
        assert response.status_code == 200
        assert response.json()['desired_state_version'] == 3
