"""Regression tests for POST /admin/plans (admin_create_plan).

Context (see the throwaway-DB proof run separately against a disposable
Postgres, migrated for real via backend/migrate.py -- not reproducible
inside this mocked-session suite since asyncpg/Postgres constraint
enforcement isn't simulated here):

  Bug A -- `plans` has three NOT NULL columns with no default
  (`name`, `price_yearly`, `token_quota_monthly`) that the old INSERT
  branch never set. Creating any new plan through the admin panel raised
  asyncpg.exceptions.NotNullViolationError -> 500.

  Bug B -- `models_allowed` (both branches) and `features` (UPDATE branch
  only) were bound as raw Python lists into a `sqlalchemy.text()` statement
  against jsonb columns. asyncpg's jsonb codec requires already-serialized
  JSON text for a raw bind param; a raw list raised
  asyncpg.exceptions.DataError -> 500.

  Bug C -- `plans` carries BOTH `token_quota_monthly` (NOT NULL) and
  `monthly_token_quota` (nullable, the one the handler actually reads) with
  the same value. The old handler only ever wrote the second, so the first
  edit from the admin UI made them diverge.

Since this suite's DB is a mock (`tests/conftest.py` mocks asyncpg/Redis at
import time -- no live Postgres, no constraint enforcement), these tests
instead capture the exact SQL text and bound parameters admin_create_plan
sends to `session.execute()` and assert on THEM: that every NOT NULL column
is present in the INSERT's column list with a non-null value, that the two
quota columns are always bound from the same parameter, and that
`features`/`models_allowed` are valid JSON strings (not raw Python lists) in
both the INSERT and UPDATE branches -- exactly the shape that would 500
against a real jsonb/NOT NULL-constrained Postgres and does NOT against the
fixed handler. Each test is proven non-hollow by running it against the
pre-fix handler (git-original admin.py) and observing it fail for the
specific reason described above -- see the task report for the red/green
transcript.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import sqlalchemy

from tests.conftest import ADMIN_TOKEN, make_row


def _make_capturing_db(existing: bool):
    """Fake `session.execute` that records every (sql_text, params) call
    and answers the handler's own `SELECT id FROM plans WHERE id = :pid`
    existence check with either a row (UPDATE branch) or None (INSERT
    branch), exactly like a real DB would for a plan that already exists /
    doesn't yet.
    """
    calls: list[tuple[str, dict | None]] = []

    async def fake_execute(query, params=None, *args, **kwargs):
        sql = str(query) if isinstance(query, sqlalchemy.sql.elements.TextClause) else str(query)
        calls.append((sql, params))
        if 'SELECT id FROM plans WHERE id' in sql:
            res = MagicMock()
            res.fetchone.return_value = make_row(id='some-plan') if existing else None
            return res
        return MagicMock()

    return calls, fake_execute


def _find_call(calls, marker: str) -> tuple[str, dict]:
    for sql, params in calls:
        if marker in sql:
            return sql, (params or {})
    raise AssertionError(f'no captured call containing {marker!r} among {[c[0][:60] for c in calls]}')


@pytest.fixture
def admin_headers():
    return {'x-admin-token': ADMIN_TOKEN}


NEW_PLAN_PAYLOAD = {
    'id': 'new_plan',
    'name_fa': 'پلن جدید',
    'name_en': 'New Plan',
    'price_monthly': 100_000,
    'monthly_token_quota': 500_000,
    'daily_token_limit': 10_000,
    'priority_queue': False,
    'active': True,
    'sort_order': 1,
}

NEW_PLAN_WITH_ARRAYS_PAYLOAD = {
    **NEW_PLAN_PAYLOAD,
    'features': ['a', 'b'],
    'models_allowed': ['gpt-x'],
}

UPDATE_PLAN_PAYLOAD = {
    'id': 'existing_plan',
    'name_fa': 'پلن قدیمی',
    'name_en': 'Existing Plan',
    'price_monthly': 200_000,
    'monthly_token_quota': 777_000,
    'daily_token_limit': 20_000,
    'priority_queue': True,
    'active': True,
    'sort_order': 2,
    'features': ['c'],
    'models_allowed': ['gpt-y', 'gpt-z'],
}


class TestCreatePlanSetsNotNullColumns:
    """Bug A: name / price_yearly / token_quota_monthly must all be set on
    INSERT, with no separate yearly-price field in the admin UI, so
    price_yearly needs a sane computed default."""

    def test_create_sets_name_price_yearly_and_legacy_quota_column(
        self, client, mock_async_session, admin_headers,
    ):
        calls, fake_execute = _make_capturing_db(existing=False)
        mock_async_session.execute = fake_execute

        response = client.post('/admin/plans', headers=admin_headers, json=NEW_PLAN_PAYLOAD)
        assert response.status_code == 200, response.text

        sql, params = _find_call(calls, 'INSERT INTO plans')
        assert 'name' in params and params['name'], 'name must be set on INSERT (NOT NULL, no default)'
        assert params['name'] != None  # noqa: E711 -- explicit, readable intent
        assert 'price_yearly' in sql
        assert params.get('price_yearly') is not None, 'price_yearly must be set on INSERT (NOT NULL, no default)'
        assert 'token_quota_monthly' in sql, 'legacy NOT NULL column must appear in the INSERT column list'

    def test_create_computes_price_yearly_default_when_not_supplied(
        self, client, mock_async_session, admin_headers,
    ):
        calls, fake_execute = _make_capturing_db(existing=False)
        mock_async_session.execute = fake_execute

        client.post('/admin/plans', headers=admin_headers, json=NEW_PLAN_PAYLOAD)
        _, params = _find_call(calls, 'INSERT INTO plans')
        assert params['price_yearly'] == NEW_PLAN_PAYLOAD['price_monthly'] * 12


class TestQuotaColumnsNeverDiverge:
    """Bug C: `token_quota_monthly` and `monthly_token_quota` must always be
    written together from the single value the API accepts, on BOTH
    create and update."""

    def test_create_writes_both_quota_columns_from_same_value(
        self, client, mock_async_session, admin_headers,
    ):
        calls, fake_execute = _make_capturing_db(existing=False)
        mock_async_session.execute = fake_execute

        client.post('/admin/plans', headers=admin_headers, json=NEW_PLAN_PAYLOAD)
        sql, params = _find_call(calls, 'INSERT INTO plans')
        assert 'monthly_token_quota' in sql and 'token_quota_monthly' in sql
        # Both columns must be bound from the exact same parameter value --
        # not two independently-sourced numbers that could drift apart.
        assert params['quota'] == NEW_PLAN_PAYLOAD['monthly_token_quota'] == 500_000

    def test_update_writes_both_quota_columns_from_same_value(
        self, client, mock_async_session, admin_headers,
    ):
        calls, fake_execute = _make_capturing_db(existing=True)
        mock_async_session.execute = fake_execute

        response = client.post('/admin/plans', headers=admin_headers, json=UPDATE_PLAN_PAYLOAD)
        assert response.status_code == 200, response.text

        sql, params = _find_call(calls, 'UPDATE plans SET')
        assert 'monthly_token_quota = :quota' in sql
        assert 'token_quota_monthly = :quota' in sql
        assert params['quota'] == UPDATE_PLAN_PAYLOAD['monthly_token_quota'] == 777_000

    def test_update_without_quota_in_payload_does_not_touch_quota_columns(
        self, client, mock_async_session, admin_headers,
    ):
        """Preserves the original conditional-update semantics: if the
        caller doesn't send a quota, an update must not clobber the
        existing value in either column."""
        calls, fake_execute = _make_capturing_db(existing=True)
        mock_async_session.execute = fake_execute

        payload = {k: v for k, v in UPDATE_PLAN_PAYLOAD.items() if k != 'monthly_token_quota'}
        client.post('/admin/plans', headers=admin_headers, json=payload)
        sql, _ = _find_call(calls, 'UPDATE plans SET')
        assert 'monthly_token_quota' not in sql
        assert 'token_quota_monthly' not in sql


class TestFeaturesAndModelsAllowedJsonBinding:
    """Bug B: both jsonb columns must be bound as real JSON text in BOTH
    the INSERT and UPDATE branches -- never a raw Python list/None-as-string."""

    def test_create_encodes_features_and_models_allowed_as_json_text(
        self, client, mock_async_session, admin_headers,
    ):
        calls, fake_execute = _make_capturing_db(existing=False)
        mock_async_session.execute = fake_execute

        client.post('/admin/plans', headers=admin_headers, json=NEW_PLAN_WITH_ARRAYS_PAYLOAD)
        _, params = _find_call(calls, 'INSERT INTO plans')

        assert isinstance(params['features'], str), (
            f"features must be a JSON string, got {type(params['features'])}: {params['features']!r}"
        )
        assert json.loads(params['features']) == ['a', 'b']

        assert isinstance(params['models_allowed'], str), (
            f"models_allowed must be a JSON string, got {type(params['models_allowed'])}: "
            f"{params['models_allowed']!r}"
        )
        assert json.loads(params['models_allowed']) == ['gpt-x']

    def test_create_without_models_allowed_binds_sql_null_not_json_null_string(
        self, client, mock_async_session, admin_headers,
    ):
        """When the caller omits models_allowed, the column must get real
        SQL NULL (the column is nullable), not the JSON text "null"."""
        calls, fake_execute = _make_capturing_db(existing=False)
        mock_async_session.execute = fake_execute

        client.post('/admin/plans', headers=admin_headers, json=NEW_PLAN_PAYLOAD)
        _, params = _find_call(calls, 'INSERT INTO plans')
        assert params['models_allowed'] is None

    def test_update_encodes_features_and_models_allowed_as_json_text(
        self, client, mock_async_session, admin_headers,
    ):
        calls, fake_execute = _make_capturing_db(existing=True)
        mock_async_session.execute = fake_execute

        client.post('/admin/plans', headers=admin_headers, json=UPDATE_PLAN_PAYLOAD)
        _, params = _find_call(calls, 'UPDATE plans SET')

        assert isinstance(params['features'], str), (
            f"features must be a JSON string on UPDATE too, got {type(params['features'])}: "
            f"{params['features']!r}"
        )
        assert json.loads(params['features']) == ['c']

        assert isinstance(params['models_allowed'], str), (
            f"models_allowed must be a JSON string on UPDATE too, got "
            f"{type(params['models_allowed'])}: {params['models_allowed']!r}"
        )
        assert json.loads(params['models_allowed']) == ['gpt-y', 'gpt-z']


class TestPlansEndpointAuth:
    def test_unauthorized(self, client):
        response = client.post('/admin/plans', json=NEW_PLAN_PAYLOAD)
        assert response.status_code == 401
