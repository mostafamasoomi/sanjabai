"""Tests for the optional model_id label on credit packages (used to sell a
package as "N million tokens of <model>" -- see
migrations/0018_credit_package_model_label.sql). Deliberately does not touch
the checkout/charge math, only that the label round-trips through the admin
create/update endpoint.

REPOINTED (migration 0049 / plans-and-subscriptions retirement): this used
to post to admin_plans.py's `/admin/credit-packages`, an unvalidated
create-or-update endpoint that file no longer exists (deleted along with
`/admin/plans` and `/admin/subscriptions` -- see admin.py's module
docstring). The validated equivalent in admin_packages.py splits create
(`POST /admin/packages`) and update (`POST /admin/packages/{id}`) into two
routes and requires both `name_fa` and `name_en` on create -- the old
endpoint didn't. `model_id` itself was NOT previously an editable field on
admin_packages.py/admin_packages_validation.py (only the money/quota/
rate-limit/active fields were); it is added here as a plain nullable text
field (same nullable-text shape as `description`) so the validated endpoint
can actually express what this guard asserts, per this packet's instruction
not to delete a guard to make the suite green.
"""
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


@pytest.fixture
def admin_ok():
    # admin_packages.py imports `admin_required` directly from dependencies
    # (it is not part of admin.py's aggregator, so admin.py's
    # `admin.admin_required` monkeypatch contract does not gate it -- see
    # tests/test_admin_packages.py's identical fixture).
    import admin_packages
    with patch.object(admin_packages, 'admin_required', new=AsyncMock(return_value=True)):
        yield


class _MappingRow:
    """Minimal stand-in for a SQLAlchemy Row exposing `_mapping`, same
    helper tests/test_admin_packages.py uses."""

    def __init__(self, **kwargs):
        self._mapping = dict(kwargs)


class TestCreditPackageModelLabel:
    def test_create_new_package_stores_model_id(self, mock_async_session, admin_ok):
        captured = {}

        async def mock_execute(stmt, params=None, *a, **k):
            sql = str(stmt)
            if 'SELECT id FROM credit_packages' in sql:
                return MagicMock(fetchone=MagicMock(return_value=None))
            if 'INSERT INTO credit_packages' in sql:
                captured['params'] = params
            return MagicMock(fetchone=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

        mock_async_session.execute = mock_execute

        resp = client.post('/admin/packages', json={
            'id': 'pkg_mimo_20m',
            'name_fa': '۲۰ میلیون توکن mimo',
            'name_en': '20M mimo tokens',
            'base_amount': 20000,
            'total_credits': 20000,
            'model_id': 'mimo-v2.5-pro',
            'active': True,
        })
        assert resp.status_code == 201
        assert captured['params']['model_id'] == 'mimo-v2.5-pro'

    def test_update_existing_package_can_set_model_id(self, mock_async_session, admin_ok):
        captured = {}
        current_row = _MappingRow(
            id='pkg_mimo_20m', name_fa='x', name_en='y', base_amount=20000,
            bonus_percent=0, total_credits=20000, model_id=None, active=True,
            sort_order=0, request_quota=None, token_quota=None,
            validity_days=None, max_cost_per_request_toman=None,
            rate_limit_per_window=None, premium_rate_limit_per_window=None,
        )

        async def mock_execute(stmt, params=None, *a, **k):
            sql = str(stmt)
            if sql.startswith('SELECT * FROM credit_packages'):
                return MagicMock(fetchone=MagicMock(return_value=current_row))
            if sql.startswith('UPDATE credit_packages'):
                captured['sql'] = sql
                captured['params'] = params
            return MagicMock(fetchone=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

        mock_async_session.execute = mock_execute

        resp = client.post('/admin/packages/pkg_mimo_20m', json={'model_id': 'gpt-4o-mini'})
        assert resp.status_code == 200
        assert 'model_id = :model_id' in captured['sql']
        assert captured['params']['model_id'] == 'gpt-4o-mini'

    def test_create_without_model_id_is_left_unset(self, mock_async_session, admin_ok):
        """Omitting `model_id` from a create payload must not write any
        value for it -- the column is left to its DB-side NULL default,
        the same as any other field the caller doesn't submit. (Under the
        old unvalidated `/admin/credit-packages` endpoint this was an
        explicit `payload.get('model_id')` defaulting to None on every
        insert; the validated endpoint's create only ever writes fields
        actually present in the payload.)"""
        captured = {}

        async def mock_execute(stmt, params=None, *a, **k):
            sql = str(stmt)
            if 'SELECT id FROM credit_packages' in sql:
                return MagicMock(fetchone=MagicMock(return_value=None))
            if 'INSERT INTO credit_packages' in sql:
                captured['params'] = params
            return MagicMock(fetchone=MagicMock(return_value=None), fetchall=MagicMock(return_value=[]))

        mock_async_session.execute = mock_execute

        resp = client.post('/admin/packages', json={
            'id': 'pkg_generic_100k',
            'name_fa': 'شارژ عمومی', 'name_en': 'Generic Charge',
            'base_amount': 100000, 'total_credits': 100000,
        })
        assert resp.status_code == 201
        assert 'model_id' not in captured['params']
