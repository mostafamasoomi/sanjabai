"""Tests for the admin logical-model / candidate review endpoints
(backend/admin_logical.py).

Style mirrors tests/test_admin_packages.py: a standalone FastAPI app
carrying just this router (it IS wired into the real app -- app.py:355 --
but a standalone app keeps these tests off the global middleware stack),
admin_required
patched per-test, and `mock_async_session` (tests/conftest.py) for the DB
layer. No live database is used anywhere in this file.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import admin_logical
from tests.conftest import make_result, make_row


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def admin_ok():
    with patch.object(admin_logical, 'admin_required', new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
def admin_denied():
    with patch.object(admin_logical, 'admin_required', new=AsyncMock(return_value=False)):
        yield


@pytest.fixture
def app_client():
    app = FastAPI()
    app.include_router(admin_logical.router)
    return TestClient(app)


class _MappingRow:
    """Minimal stand-in for a SQLAlchemy Row exposing `_mapping`, same
    helper test_admin_packages.py uses."""

    def __init__(self, **kwargs):
        self._mapping = dict(kwargs)


def _lm_row(**overrides) -> _MappingRow:
    row = dict(
        key='gpt-4o', display_name='GPT-4o', description=None, vendor='openai',
        context_window=128000, max_output_tokens=4096, currency='IRT',
        input_per_million=0, output_per_million=0, cached_input_per_million=None,
        usd_input_per_million=None, usd_output_per_million=None,
        availability='maintenance', routing_policy='cheapest_healthy',
        pinned_candidate_id=None,
        created_at='2026-08-17T00:00:00Z', updated_at='2026-08-17T00:00:00Z',
    )
    row.update(overrides)
    return _MappingRow(**row)


def _candidate_row(**overrides) -> _MappingRow:
    """Row shape for the `update_candidate` guard-rail lookup (joins
    logical_model_candidate with logical_model.pinned_candidate_id)."""
    row = dict(
        id=1, catalog_id='openai/gpt-4o-2024', state='proposed', enabled=True,
        pinned_candidate_id=None,
    )
    row.update(overrides)
    return _MappingRow(**row)


def _count_row(c: int):
    """A row shape for `SELECT COUNT(*) AS c ...` -- attribute access
    (`.c`), not `_mapping`, matching how the router reads it."""
    return make_row(c=c)


# ── GET /admin/logical-models ───────────────────────────────────────────

class TestListLogicalModels:
    def test_requires_admin(self, app_client, admin_denied):
        resp = app_client.get('/admin/logical-models')
        assert resp.status_code == 401

    def test_invalid_availability_filter_400s(self, app_client, admin_ok, mock_async_session):
        resp = app_client.get('/admin/logical-models?availability=not-a-real-value')
        assert resp.status_code == 400

    def test_lists_and_paginates(self, app_client, admin_ok, mock_async_session):
        row = dict(
            key='gpt-4o', display_name='GPT-4o', vendor='openai', context_window=128000,
            max_output_tokens=4096, availability='maintenance', routing_policy='cheapest_healthy',
            pinned_candidate_id=None, updated_at='2026-08-17T00:00:00Z',
            candidate_count=3, proposed_count=2, approved_count=1, rejected_count=0,
        )
        calls = []

        async def mock_execute(clause, params=None):
            calls.append(params)
            text = str(clause)
            if 'COUNT(*) AS c FROM' in text:
                return make_result(fetchone=_count_row(1))
            return make_result(fetchall=[_MappingRow(**row)])

        mock_async_session.execute = mock_execute
        resp = app_client.get('/admin/logical-models?page=1&limit=10')
        assert resp.status_code == 200
        body = resp.json()
        assert body['total'] == 1
        assert body['page'] == 1
        assert body['limit'] == 10
        assert len(body['items']) == 1
        item = body['items'][0]
        assert item['key'] == 'gpt-4o'
        assert item['candidate_counts'] == {'total': 3, 'proposed': 2, 'approved': 1, 'rejected': 0}
        # pending_only defaults to false
        assert calls[0]['pending_only'] is False

    def test_pending_only_filter_is_passed_through(self, app_client, admin_ok, mock_async_session):
        calls = []

        async def mock_execute(clause, params=None):
            calls.append(params)
            if 'COUNT(*) AS c FROM' in str(clause):
                return make_result(fetchone=_count_row(0))
            return make_result(fetchall=[])

        mock_async_session.execute = mock_execute
        resp = app_client.get('/admin/logical-models?pending_only=true')
        assert resp.status_code == 200
        assert all(c['pending_only'] is True for c in calls)

    def test_text_search_is_passed_through(self, app_client, admin_ok, mock_async_session):
        calls = []

        async def mock_execute(clause, params=None):
            calls.append(params)
            if 'COUNT(*) AS c FROM' in str(clause):
                return make_result(fetchone=_count_row(0))
            return make_result(fetchall=[])

        mock_async_session.execute = mock_execute
        resp = app_client.get('/admin/logical-models?q=gpt-4o')
        assert resp.status_code == 200
        assert all(c['q'] == 'gpt-4o' and c['qlike'] == '%gpt-4o%' for c in calls)


# ── GET /admin/logical-models/{key} ─────────────────────────────────────

class TestGetLogicalModel:
    def test_requires_admin(self, app_client, admin_denied):
        resp = app_client.get('/admin/logical-models/gpt-4o')
        assert resp.status_code == 401

    def test_unknown_key_404s(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        resp = app_client.get('/admin/logical-models/does-not-exist')
        assert resp.status_code == 404

    def test_returns_model_with_joined_candidates(self, app_client, admin_ok, mock_async_session):
        cand = dict(
            candidate_id=7, catalog_id='openai/gpt-4o-2024', priority=100, enabled=True,
            state='approved', est_cost_usd_input=1.5, est_cost_usd_output=3.0,
            added_by='clusterer', created_at='2026-08-17T00:00:00Z', updated_at='2026-08-17T00:00:00Z',
            catalog_provider='openai', catalog_provider_model_id='gpt-4o-2024',
            catalog_display_name='GPT-4o (2024)', catalog_availability='available',
            catalog_currency='IRT', catalog_input_per_million=50000, catalog_output_per_million=150000,
            catalog_usd_input_per_million=2.5, catalog_usd_output_per_million=10.0,
        )
        results = [make_result(fetchone=_lm_row()), make_result(fetchall=[_MappingRow(**cand)])]

        async def mock_execute(*a, **k):
            return results.pop(0)

        mock_async_session.execute = mock_execute
        resp = app_client.get('/admin/logical-models/gpt-4o')
        assert resp.status_code == 200
        body = resp.json()
        assert body['key'] == 'gpt-4o'
        assert len(body['candidates']) == 1
        c = body['candidates'][0]
        assert c['id'] == 7
        assert c['catalog']['id'] == 'openai/gpt-4o-2024'
        assert c['catalog']['availability'] == 'available'
        # Decimal (NUMERIC) fields must be JSON-serialisable, not raise.
        assert c['est_cost_usd_input'] == 1.5
        assert c['catalog']['usd_input_per_million'] == 2.5


# ── POST /admin/logical-models/{key}/candidates/{id} ────────────────────

class TestUpdateCandidate:
    def test_requires_admin(self, app_client, admin_denied):
        resp = app_client.post('/admin/logical-models/gpt-4o/candidates/1', json={'state': 'approved'})
        assert resp.status_code == 401

    def test_unknown_candidate_404s(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        resp = app_client.post('/admin/logical-models/gpt-4o/candidates/999', json={'state': 'approved'})
        assert resp.status_code == 404

    def test_invalid_state_400s(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_candidate_row())
        resp = app_client.post('/admin/logical-models/gpt-4o/candidates/1', json={'state': 'not-a-state'})
        assert resp.status_code == 400

    def test_bool_priority_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_candidate_row())
        resp = app_client.post('/admin/logical-models/gpt-4o/candidates/1', json={'priority': True})
        assert resp.status_code == 400

    def test_unknown_field_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_candidate_row())
        resp = app_client.post('/admin/logical-models/gpt-4o/candidates/1', json={'bogus': 1})
        assert resp.status_code == 400

    def test_empty_payload_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_candidate_row())
        resp = app_client.post('/admin/logical-models/gpt-4o/candidates/1', json={})
        assert resp.status_code == 400

    def test_approve_succeeds(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_candidate_row(state='proposed'))
        resp = app_client.post('/admin/logical-models/gpt-4o/candidates/1', json={'state': 'approved'})
        assert resp.status_code == 200
        assert resp.json()['updated'] == {'state': 'approved'}

    def test_reject_currently_pinned_candidate_refused(self, app_client, admin_ok, mock_async_session):
        """🔴 Guard rail: rejecting the candidate a logical model currently
        has pinned (matched by catalog_id, per admin_logical.py's docstring
        on what pinned_candidate_id actually stores) must be refused."""
        mock_async_session._execute_result = make_result(fetchone=_candidate_row(
            catalog_id='openai/gpt-4o-2024', state='approved', enabled=True,
            pinned_candidate_id='openai/gpt-4o-2024',
        ))
        resp = app_client.post('/admin/logical-models/gpt-4o/candidates/1', json={'state': 'rejected'})
        assert resp.status_code == 400
        assert 'پین' in resp.json()['detail']

    def test_disable_currently_pinned_candidate_refused(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_candidate_row(
            catalog_id='openai/gpt-4o-2024', state='approved', enabled=True,
            pinned_candidate_id='openai/gpt-4o-2024',
        ))
        resp = app_client.post('/admin/logical-models/gpt-4o/candidates/1', json={'enabled': False})
        assert resp.status_code == 400

    def test_editing_non_pinned_candidate_unaffected(self, app_client, admin_ok, mock_async_session):
        """Some OTHER candidate is pinned (different catalog_id) -- editing
        this one must not be blocked by the pin guard."""
        mock_async_session._execute_result = make_result(fetchone=_candidate_row(
            catalog_id='openai/gpt-4o-mini', state='proposed', enabled=True,
            pinned_candidate_id='openai/gpt-4o-2024',
        ))
        resp = app_client.post('/admin/logical-models/gpt-4o/candidates/1', json={'state': 'rejected'})
        assert resp.status_code == 200

    def test_audit_entry_written(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_candidate_row())
        with patch.object(admin_logical, '_write_audit_log', new=AsyncMock()) as mock_audit:
            resp = app_client.post('/admin/logical-models/gpt-4o/candidates/1', json={'priority': 5})
        assert resp.status_code == 200
        mock_audit.assert_awaited_once()
        args, kwargs = mock_audit.call_args
        assert args[0] == 'admin.logical_candidate.update'
        assert kwargs['target_type'] == 'logical_model_candidate'
        assert kwargs['target_id'] == 1
        assert kwargs['details'] == {'logical_key': 'gpt-4o', 'priority': 5}


# ── POST /admin/logical-models/{key}/routing ────────────────────────────

class TestUpdateRouting:
    def test_requires_admin(self, app_client, admin_denied):
        resp = app_client.post('/admin/logical-models/gpt-4o/routing', json={'routing_policy': 'priority'})
        assert resp.status_code == 401

    def test_unknown_key_404s(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        resp = app_client.post('/admin/logical-models/gpt-4o/routing', json={'routing_policy': 'priority'})
        assert resp.status_code == 404

    def test_invalid_routing_policy_400s(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_lm_row())
        resp = app_client.post('/admin/logical-models/gpt-4o/routing', json={'routing_policy': 'random'})
        assert resp.status_code == 400

    def test_pin_to_non_approved_candidate_refused(self, app_client, admin_ok, mock_async_session):
        """🔴 Core guard rail: pinning a candidate that is not approved+enabled
        for this exact logical_key must be refused."""
        results = [make_result(fetchone=_lm_row()), make_result(fetchone=None)]

        async def mock_execute(*a, **k):
            return results.pop(0)

        mock_async_session.execute = mock_execute
        resp = app_client.post(
            '/admin/logical-models/gpt-4o/routing',
            json={'pinned_candidate_id': 'openai/gpt-4o-rejected'},
        )
        assert resp.status_code == 400
        assert 'approved' in resp.json()['detail'] or 'تأییدشده' in resp.json()['detail']

    def test_pin_to_approved_candidate_accepted(self, app_client, admin_ok, mock_async_session):
        results = [
            make_result(fetchone=_lm_row()),
            make_result(fetchone=_MappingRow(x=1)),  # eligibility check finds a row
        ]

        async def mock_execute(*a, **k):
            return results.pop(0) if results else make_result()

        mock_async_session.execute = mock_execute
        resp = app_client.post(
            '/admin/logical-models/gpt-4o/routing',
            json={'pinned_candidate_id': 'openai/gpt-4o-2024'},
        )
        assert resp.status_code == 200

    def test_pinned_policy_without_pin_refused(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_lm_row(pinned_candidate_id=None))
        resp = app_client.post('/admin/logical-models/gpt-4o/routing', json={'routing_policy': 'pinned'})
        assert resp.status_code == 400

    def test_pinned_policy_with_existing_pin_accepted(self, app_client, admin_ok, mock_async_session):
        """routing_policy=pinned with a pin already on the row (not resent
        in this payload) must use the effective (merged) row, not just the
        payload -- same idiom as admin_packages.py's loss-path check."""
        mock_async_session._execute_result = make_result(
            fetchone=_lm_row(pinned_candidate_id='openai/gpt-4o-2024')
        )
        resp = app_client.post('/admin/logical-models/gpt-4o/routing', json={'routing_policy': 'pinned'})
        assert resp.status_code == 200

    def test_unknown_field_rejected(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_lm_row())
        resp = app_client.post('/admin/logical-models/gpt-4o/routing', json={'bogus': 1})
        assert resp.status_code == 400

    def test_audit_entry_written(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_lm_row())
        with patch.object(admin_logical, '_write_audit_log', new=AsyncMock()) as mock_audit:
            resp = app_client.post(
                '/admin/logical-models/gpt-4o/routing', json={'routing_policy': 'priority'}
            )
        assert resp.status_code == 200
        mock_audit.assert_awaited_once()
        args, kwargs = mock_audit.call_args
        assert args[0] == 'admin.logical_model.routing_update'
        assert kwargs['target_type'] == 'logical_model'
        assert kwargs['target_id'] == 'gpt-4o'


# ── POST /admin/logical-models/{key}/availability ───────────────────────

class TestUpdateAvailability:
    def test_requires_admin(self, app_client, admin_denied):
        resp = app_client.post('/admin/logical-models/gpt-4o/availability', json={'availability': 'disabled'})
        assert resp.status_code == 401

    def test_missing_field_400s(self, app_client, admin_ok, mock_async_session):
        resp = app_client.post('/admin/logical-models/gpt-4o/availability', json={})
        assert resp.status_code == 400

    def test_invalid_value_400s(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_MappingRow(key='gpt-4o'))
        resp = app_client.post('/admin/logical-models/gpt-4o/availability', json={'availability': 'bogus'})
        assert resp.status_code == 400

    def test_unknown_key_404s(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=None)
        resp = app_client.post('/admin/logical-models/gpt-4o/availability', json={'availability': 'disabled'})
        assert resp.status_code == 404

    def test_available_with_no_eligible_candidate_refused(self, app_client, admin_ok, mock_async_session):
        """🔴 Core guard rail: publishing a logical model with zero
        approved+enabled candidates must be refused -- it would have
        nowhere to route a real request."""
        results = [make_result(fetchone=_MappingRow(key='gpt-4o')), make_result(fetchone=_count_row(0))]

        async def mock_execute(*a, **k):
            return results.pop(0)

        mock_async_session.execute = mock_execute
        resp = app_client.post('/admin/logical-models/gpt-4o/availability', json={'availability': 'available'})
        assert resp.status_code == 400
        assert 'گزینه' in resp.json()['detail']

    def test_available_with_eligible_candidate_accepted(self, app_client, admin_ok, mock_async_session):
        results = [make_result(fetchone=_MappingRow(key='gpt-4o')), make_result(fetchone=_count_row(1))]

        async def mock_execute(*a, **k):
            return results.pop(0) if results else make_result()

        mock_async_session.execute = mock_execute
        resp = app_client.post('/admin/logical-models/gpt-4o/availability', json={'availability': 'available'})
        assert resp.status_code == 200

    def test_disabled_does_not_require_eligible_candidate(self, app_client, admin_ok, mock_async_session):
        """Turning a model OFF is always allowed -- only publishing it
        (available) requires an eligible candidate."""
        mock_async_session._execute_result = make_result(fetchone=_MappingRow(key='gpt-4o'))
        resp = app_client.post('/admin/logical-models/gpt-4o/availability', json={'availability': 'disabled'})
        assert resp.status_code == 200

    def test_audit_entry_written(self, app_client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchone=_MappingRow(key='gpt-4o'))
        with patch.object(admin_logical, '_write_audit_log', new=AsyncMock()) as mock_audit:
            resp = app_client.post(
                '/admin/logical-models/gpt-4o/availability', json={'availability': 'disabled'}
            )
        assert resp.status_code == 200
        mock_audit.assert_awaited_once()
        args, kwargs = mock_audit.call_args
        assert args[0] == 'admin.logical_model.availability_update'
        assert kwargs['target_type'] == 'logical_model'
        assert kwargs['target_id'] == 'gpt-4o'
        assert kwargs['details'] == {'availability': 'disabled'}
