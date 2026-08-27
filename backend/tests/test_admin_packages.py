"""Tests for the admin credit-package management endpoints
(backend/admin_packages.py).

GapGPT-style packages: a package tops up Toman and, as of migration 0034,
can also grant a request/token quota counted separately from Toman via four
new nullable columns on `credit_packages`
(request_quota, token_quota, validity_days, max_cost_per_request_toman).
That migration is owned by another agent and has not landed in the real DB
yet, but this suite has no live database (Redis/asyncpg are mocked at
import time -- see tests/conftest.py), so the four columns simply need to
exist on the mock rows this file builds.

Style mirrors tests/test_exchange_rate_source.py's HTTP-layer class: a
standalone FastAPI app carries just this router, since admin_packages is
not wired into app.py yet (that include_router line is the coordinator's to
add, outside this agent's file ownership). Money-field validation mirrors
tests/test_admin_image_price.py's float/negative/bool guards -- same
"integer Toman only" rule, applied here to several columns at once.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import admin_packages
from tests.conftest import make_result


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def admin_ok():
    with patch.object(admin_packages, 'admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def admin_denied():
    with patch.object(admin_packages, 'admin_required', new=AsyncMock(return_value=False)):
        yield


@pytest.fixture
def app_client():
    app = FastAPI()
    app.include_router(admin_packages.router)
    return TestClient(app)


class _MappingRow:
    """Minimal stand-in for a SQLAlchemy Row exposing `_mapping` -- same
    helper test_admin_image_price.py and test_markup.py use, since
    `dict(r._mapping)` is what this router calls on the current-row fetch."""

    def __init__(self, **kwargs):
        self._mapping = dict(kwargs)


def _pkg_row(**overrides) -> _MappingRow:
    """A full credit_packages row, including the four migration-0034
    columns, shaped like the real seed data, plus the two migration-0046
    rate-limit columns.

    The legacy `name`/`price`/`credits`/`bonus_credits` columns that used
    to be part of this fixture were dropped by migration 0049
    (plans/subscriptions retired) -- they are gone from the real table now,
    not just unused."""
    row = dict(
        id='starter-credits', description='Test credit',
        active=True,
        created_at='2026-08-17T00:00:00Z', updated_at='2026-08-17T00:00:00Z',
        model_id=None, name_fa='بسته شروع', name_en='Starter', base_amount=100_000,
        bonus_percent=0, total_credits=100_000, sort_order=1,
        request_quota=None, token_quota=None, validity_days=None,
        max_cost_per_request_toman=None,
        rate_limit_per_window=None, premium_rate_limit_per_window=None,
    )
    row.update(overrides)
    return _MappingRow(**row)


# ── GET /admin/packages ──────────────────────────────────────────────────

class TestListPackages:
    def test_requires_admin(self, app_client, admin_denied):
        resp = app_client.get('/admin/packages')
        assert resp.status_code == 401

    def test_returns_all_columns(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[_pkg_row()])
        resp = app_client.get('/admin/packages')
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]['id'] == 'starter-credits'
        assert body[0]['request_quota'] is None
        assert body[0]['max_cost_per_request_toman'] is None


# ── GET /admin/purchases ──────────────────────────────────────────────────

class _CountResult:
    def __init__(self, c: int):
        self.c = c


def _purchase_row(**overrides) -> _MappingRow:
    row = dict(
        id=1, user_id=42, email='buyer@example.com', phone=None,
        package_id='starter-credits', name_fa='بسته شروع',
        name_en='Starter', amount=100_000, total_credits=100_000,
        status='completed',
        created_at='2026-08-17T00:00:00Z', verified_at='2026-08-17T00:01:00Z',
    )
    row.update(overrides)
    return _MappingRow(**row)


class TestListPurchases:
    def test_requires_admin(self, app_client, admin_denied):
        resp = app_client.get('/admin/purchases')
        assert resp.status_code == 401

    def test_returns_paginated_shape(self, app_client, admin_ok, mock_async_session):
        async def mock_execute(stmt, params=None, *a, **k):
            sql = str(stmt)
            if 'COUNT(*)' in sql:
                return make_result(fetchone=_CountResult(1))
            return make_result(fetchall=[_purchase_row()])

        mock_async_session.execute = mock_execute
        resp = app_client.get('/admin/purchases')
        assert resp.status_code == 200
        body = resp.json()
        assert body['total'] == 1
        assert body['page'] == 1
        assert body['limit'] == 50
        assert len(body['purchases']) == 1
        item = body['purchases'][0]
        assert item['user_id'] == 42
        assert item['package_id'] == 'starter-credits'
        assert item['amount'] == 100_000
        assert item['status'] == 'completed'

    def test_limit_capped_at_200(self, app_client, admin_ok, mock_async_session):
        captured = {}

        async def mock_execute(stmt, params=None, *a, **k):
            sql = str(stmt)
            if 'COUNT(*)' in sql:
                return make_result(fetchone=_CountResult(0))
            captured['params'] = params
            return make_result(fetchall=[])

        mock_async_session.execute = mock_execute
        resp = app_client.get('/admin/purchases?limit=9999')
        assert resp.status_code == 200
        assert resp.json()['limit'] == 200
        assert captured['params']['limit'] == 200

    def test_page_offsets_correctly(self, app_client, admin_ok, mock_async_session):
        captured = {}

        async def mock_execute(stmt, params=None, *a, **k):
            sql = str(stmt)
            if 'COUNT(*)' in sql:
                return make_result(fetchone=_CountResult(0))
            captured['params'] = params
            return make_result(fetchall=[])

        mock_async_session.execute = mock_execute
        resp = app_client.get('/admin/purchases?page=3&limit=20')
        assert resp.status_code == 200
        assert captured['params']['offset'] == 40


# ── POST /admin/packages/{package_id} ────────────────────────────────────

class TestUpdatePackage:
    def test_requires_admin(self, app_client, admin_denied):
        resp = app_client.post('/admin/packages/starter-credits', json={'base_amount': 200_000})
        assert resp.status_code == 401

    def test_unknown_package_404s(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        resp = app_client.post('/admin/packages/does-not-exist', json={'base_amount': 200_000})
        assert resp.status_code == 404

    def test_float_price_rejected_even_when_integral(self, app_client, admin_ok, mock_async_session):
        """The core financial guard: a JSON float that happens to be a
        whole number (10.0) must still be rejected -- money is always an
        integer Toman, never multiplied/divided by 10 anywhere."""
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post('/admin/packages/starter-credits', json={'base_amount': 10.0})
        assert resp.status_code == 400

    def test_fractional_float_price_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post('/admin/packages/starter-credits', json={'base_amount': 99.5})
        assert resp.status_code == 400

    def test_negative_value_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post('/admin/packages/starter-credits', json={'base_amount': -1})
        assert resp.status_code == 400

    def test_bool_rejected_not_coerced(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post('/admin/packages/starter-credits', json={'base_amount': True})
        assert resp.status_code == 400

    def test_unknown_field_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post('/admin/packages/starter-credits', json={'not_a_real_field': 1})
        assert resp.status_code == 400

    def test_empty_payload_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post('/admin/packages/starter-credits', json={})
        assert resp.status_code == 400

    def test_quota_without_ceiling_rejected(self, app_client, admin_ok, mock_async_session):
        """🔴 The core loss-protection rule: setting request_quota (or
        token_quota) while max_cost_per_request_toman stays NULL is a loss
        path and must be rejected server-side."""
        mock_async_session._execute_result = make_result(
            fetchone=_pkg_row(request_quota=None, max_cost_per_request_toman=None)
        )
        resp = app_client.post('/admin/packages/starter-credits', json={'request_quota': 500})
        assert resp.status_code == 400
        assert 'ضررده' in resp.json()['detail'] or 'max_cost_per_request_toman' in resp.json()['detail']

    def test_token_quota_without_ceiling_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=_pkg_row(token_quota=None, max_cost_per_request_toman=None)
        )
        resp = app_client.post('/admin/packages/starter-credits', json={'token_quota': 100_000})
        assert resp.status_code == 400

    def test_quota_with_ceiling_in_same_request_accepted(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=_pkg_row(request_quota=None, max_cost_per_request_toman=None)
        )
        resp = app_client.post(
            '/admin/packages/starter-credits',
            json={'request_quota': 500, 'max_cost_per_request_toman': 5_000},
        )
        assert resp.status_code == 200

    def test_quota_with_preexisting_ceiling_accepted(self, app_client, admin_ok, mock_async_session):
        """Setting request_quota when the row ALREADY has a ceiling from a
        previous edit (not re-sent in this payload) must not be rejected --
        the check is against the effective (merged) row, not just the
        payload."""
        mock_async_session._execute_result = make_result(
            fetchone=_pkg_row(request_quota=None, max_cost_per_request_toman=3_000)
        )
        resp = app_client.post('/admin/packages/starter-credits', json={'request_quota': 500})
        assert resp.status_code == 200

    def test_clearing_ceiling_while_quota_still_set_rejected(self, app_client, admin_ok, mock_async_session):
        """Clearing the ceiling back to NULL while a quota from a prior edit
        is still in effect must also be rejected -- same loss path."""
        mock_async_session._execute_result = make_result(
            fetchone=_pkg_row(request_quota=500, max_cost_per_request_toman=3_000)
        )
        resp = app_client.post(
            '/admin/packages/starter-credits', json={'max_cost_per_request_toman': None}
        )
        assert resp.status_code == 400

    def test_positive_quota_and_validity_accepted(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=_pkg_row(max_cost_per_request_toman=5_000)
        )
        resp = app_client.post(
            '/admin/packages/starter-credits',
            json={'request_quota': 200, 'validity_days': 30},
        )
        assert resp.status_code == 200

    def test_zero_quota_rejected(self, app_client, admin_ok, mock_async_session):
        """A zero request quota is meaningless -- should be NULL instead."""
        mock_async_session._execute_result = make_result(
            fetchone=_pkg_row(max_cost_per_request_toman=5_000)
        )
        resp = app_client.post('/admin/packages/starter-credits', json={'request_quota': 0})
        assert resp.status_code == 400

    def test_valid_update_round_trips(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post(
            '/admin/packages/starter-credits',
            json={'name_fa': 'بستهٔ جدید', 'base_amount': 150_000, 'active': False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body['id'] == 'starter-credits'
        assert body['updated']['name_fa'] == 'بستهٔ جدید'
        assert body['updated']['base_amount'] == 150_000
        assert body['updated']['active'] is False

    def test_audit_entry_written(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        with patch.object(admin_packages, '_write_audit_log', new=AsyncMock()) as mock_audit:
            resp = app_client.post(
                '/admin/packages/starter-credits', json={'base_amount': 150_000}
            )
        assert resp.status_code == 200
        mock_audit.assert_awaited_once()
        args, kwargs = mock_audit.call_args
        assert args[0] == 'admin.package.update'
        assert kwargs['target_type'] == 'credit_package'
        assert kwargs['target_id'] == 'starter-credits'
        assert kwargs['details'] == {'base_amount': 150_000}


# ── POST /admin/packages (create) ────────────────────────────────────────

class TestCreatePackage:
    def test_requires_admin(self, app_client, admin_denied):
        resp = app_client.post('/admin/packages', json={'id': 'new-pkg', 'name_fa': 'x', 'name_en': 'x'})
        assert resp.status_code == 401

    def test_missing_id_rejected(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/packages', json={'name_fa': 'x', 'name_en': 'x'})
        assert resp.status_code == 400

    def test_missing_names_rejected(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/packages', json={'id': 'new-pkg'})
        assert resp.status_code == 400

    def test_duplicate_id_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post(
            '/admin/packages',
            json={'id': 'starter-credits', 'name_fa': 'x', 'name_en': 'y', 'base_amount': 1000},
        )
        assert resp.status_code == 400

    def test_quota_without_ceiling_rejected_on_create(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        resp = app_client.post(
            '/admin/packages',
            json={'id': 'new-pkg', 'name_fa': 'x', 'name_en': 'y', 'base_amount': 1000,
                  'request_quota': 100},
        )
        assert resp.status_code == 400

    def test_valid_create_succeeds(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(admin_packages, '_write_audit_log', new=AsyncMock()):
            resp = app_client.post(
                '/admin/packages',
                json={'id': 'new-pkg', 'name_fa': 'بسته جدید', 'name_en': 'New Pkg',
                      'base_amount': 100_000, 'total_credits': 100_000},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body['id'] == 'new-pkg'
        assert body['created']['base_amount'] == 100_000


# ── migration-0046 rate-limit fields (rate_limit_per_window /
#    premium_rate_limit_per_window) ──────────────────────────────────────
#
# Pure rate limits: no `package_entitlement` is created by these, so unlike
# request_quota/token_quota they must NOT be gated by `_check_loss_path`.

class TestRateLimitFields:
    def test_positive_values_accepted_without_ceiling(self, app_client, admin_ok, mock_async_session):
        """The core of this change: setting both new columns with NO
        max_cost_per_request_toman must succeed -- unlike request_quota/
        token_quota, these never create a wallet-bypassing entitlement."""
        mock_async_session._execute_result = make_result(
            fetchone=_pkg_row(max_cost_per_request_toman=None)
        )
        resp = app_client.post(
            '/admin/packages/starter-credits',
            json={'rate_limit_per_window': 40, 'premium_rate_limit_per_window': 5},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body['updated']['rate_limit_per_window'] == 40
        assert body['updated']['premium_rate_limit_per_window'] == 5

    def test_zero_rate_limit_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post('/admin/packages/starter-credits', json={'rate_limit_per_window': 0})
        assert resp.status_code == 400

    def test_negative_premium_rate_limit_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post('/admin/packages/starter-credits', json={'premium_rate_limit_per_window': -5})
        assert resp.status_code == 400

    def test_float_rate_limit_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post('/admin/packages/starter-credits', json={'rate_limit_per_window': 40.0})
        assert resp.status_code == 400

    def test_bool_rate_limit_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_pkg_row())
        resp = app_client.post('/admin/packages/starter-credits', json={'premium_rate_limit_per_window': True})
        assert resp.status_code == 400

    def test_null_clears_rate_limit(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(
            fetchone=_pkg_row(rate_limit_per_window=40)
        )
        resp = app_client.post('/admin/packages/starter-credits', json={'rate_limit_per_window': None})
        assert resp.status_code == 200
        assert resp.json()['updated']['rate_limit_per_window'] is None

    def test_rate_limit_with_quota_but_no_ceiling_still_rejected_for_quota_reason(
        self, app_client, admin_ok, mock_async_session
    ):
        """Adding a rate limit alongside a request_quota does not exempt the
        quota from its own ceiling requirement -- the two fields are
        independent, and _check_loss_path still only cares about
        request_quota/token_quota."""
        mock_async_session._execute_result = make_result(
            fetchone=_pkg_row(request_quota=None, max_cost_per_request_toman=None)
        )
        resp = app_client.post(
            '/admin/packages/starter-credits',
            json={'rate_limit_per_window': 40, 'request_quota': 500},
        )
        assert resp.status_code == 400

    def test_rate_limit_accepted_on_create_without_ceiling(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        with patch.object(admin_packages, '_write_audit_log', new=AsyncMock()):
            resp = app_client.post(
                '/admin/packages',
                json={'id': 'new-pkg', 'name_fa': 'x', 'name_en': 'y',
                      'rate_limit_per_window': 40, 'premium_rate_limit_per_window': 5},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body['created']['rate_limit_per_window'] == 40
        assert body['created']['premium_rate_limit_per_window'] == 5


# ── GET/POST /admin/premium-threshold ────────────────────────────────────

class TestPremiumThreshold:
    def test_get_requires_admin(self, app_client, admin_denied):
        resp = app_client.get('/admin/premium-threshold')
        assert resp.status_code == 401

    def test_post_requires_admin(self, app_client, admin_denied):
        resp = app_client.post('/admin/premium-threshold', json={'value': 200_000})
        assert resp.status_code == 401

    def test_get_missing_row_reports_default(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        resp = app_client.get('/admin/premium-threshold')
        assert resp.status_code == 200
        body = resp.json()
        assert body['row_missing'] is True
        assert body['value'] == admin_packages._PREMIUM_THRESHOLD_DEFAULT
        assert body['default'] == admin_packages._PREMIUM_THRESHOLD_DEFAULT

    def test_get_returns_stored_integer(self, app_client, admin_ok, mock_async_session):
        """The stored app_setting.value must round-trip as a Python int, not
        a numeric string -- a JSONB integer row comes back typed already."""
        mock_async_session._execute_result = make_result(fetchone=_MappingRow(value=200_000))
        resp = app_client.get('/admin/premium-threshold')
        assert resp.status_code == 200
        body = resp.json()
        assert body['row_missing'] is False
        assert body['value'] == 200_000
        assert isinstance(body['value'], int)

    def test_get_coerces_legacy_json_string_row(self, app_client, admin_ok, mock_async_session):
        """A row that (legacy-style) stored a JSON-encoded string still
        coerces to an int rather than being handed back as text."""
        mock_async_session._execute_result = make_result(fetchone=_MappingRow(value='200000'))
        resp = app_client.get('/admin/premium-threshold')
        assert resp.status_code == 200
        assert resp.json()['value'] == 200_000

    def test_post_missing_value_rejected(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/premium-threshold', json={})
        assert resp.status_code == 400

    def test_post_float_rejected(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/premium-threshold', json={'value': 150000.5})
        assert resp.status_code == 400

    def test_post_bool_rejected(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/premium-threshold', json={'value': True})
        assert resp.status_code == 400

    def test_post_negative_rejected(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/premium-threshold', json={'value': -1})
        assert resp.status_code == 400

    def test_post_above_bounds_rejected(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/premium-threshold', json={'value': 100_000_001})
        assert resp.status_code == 400

    def test_post_valid_value_round_trips_as_int(self, app_client, admin_ok, mock_async_session):
        """🔴 The money-typing trap this task calls out explicitly: the value
        this endpoint writes must serialize as a bare JSON integer
        (`json.dumps(200000)` -> the text `200000`), never a quoted JSON
        string -- otherwise every future reader gets the wrong type back."""
        captured = {}

        async def spy_execute(clause, params=None):
            if params and 'v' in params:
                captured['v'] = params['v']
            return mock_async_session._execute_result
        mock_async_session.execute = spy_execute

        with patch.object(admin_packages, '_write_audit_log', new=AsyncMock()) as mock_audit:
            resp = app_client.post('/admin/premium-threshold', json={'value': 200_000})
        assert resp.status_code == 200
        body = resp.json()
        assert body['value'] == 200_000
        # json.dumps(200000) is the bare text "200000", not '"200000"'.
        assert captured['v'] == '200000'
        assert json.loads(captured['v']) == 200_000
        assert isinstance(json.loads(captured['v']), int)
        mock_audit.assert_awaited_once()
        args, kwargs = mock_audit.call_args
        assert args[0] == 'admin.premium_threshold.update'
        assert kwargs['target_id'] == admin_packages._PREMIUM_THRESHOLD_KEY

    def test_post_string_digit_value_accepted(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/premium-threshold', json={'value': '150000'})
        assert resp.status_code == 200
        assert resp.json()['value'] == 150000
