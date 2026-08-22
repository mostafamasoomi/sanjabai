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
    columns, shaped like the real seed data (see docstring in
    admin_packages.py for why `credits`/`total_credits` are NOT summed with
    `bonus_credits`)."""
    row = dict(
        id='starter-credits', name='Starter Credits', description='Test credit',
        price=100_000, credits=100_000, bonus_credits=0, active=True,
        created_at='2026-08-17T00:00:00Z', updated_at='2026-08-17T00:00:00Z',
        model_id=None, name_fa='بسته شروع', name_en='Starter', base_amount=100_000,
        bonus_percent=0, total_credits=100_000, sort_order=1,
        request_quota=None, token_quota=None, validity_days=None,
        max_cost_per_request_toman=None,
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
