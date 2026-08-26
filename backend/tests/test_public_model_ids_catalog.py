"""content.py + conversations.py side of the public model id indirection
(migrations/0028_public_model_ids.sql).

Split out of the original tests/test_public_model_ids.py (which grew past
the 500-line cap) -- the chat.py resolver/routing/billing side now lives in
tests/test_public_model_ids_chat.py (see that file's docstring for the
`chat.py` half of the background). This file covers the two remaining
halves:

  1. content.py: `/v1/models` and `/catalog/models` (+pricing) serve
     `public_id` instead of `id`/`provider_model_id` -- gated behind
     `PUBLIC_MODEL_IDS_ENABLED` (default off, so today's behavior is
     preserved byte-for-byte until deliberately flipped on). Public model
     ids used to leak the upstream route (bynara/, kr/, cc/, cx/, ag/,
     gemini-api/models/, nvidia/...) and four said "-free", violating two
     product rules ("a user never sees the provider/route", "we have no
     free models") -- this is the no-leak contract that must hold whenever
     the flag is on.

  2. conversations.py: usage_events/ledger/wallet_reservations/conversations
     are append-only and must never be rewritten -- the model string a
     historical row was billed under stays exactly as-is forever.
     Translation for display must happen only at READ time, via a LEFT JOIN
     against model_catalog.

No test in this file makes a real network or DB call: the DB session proxy
is always faked, following this suite's existing conventions (see
conftest.py's `mock_async_session` fixture).
"""
from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

import content as content_mod


# ── 1. No-leak contract on / flag-off byte-for-byte identical ───────────

def _seeded_public_row(**overrides):
    row = dict(
        id='bynara/mistral-large', provider_model_id='bynara/mistral-large',
        public_id='sanjab/mistral-large', display_name='Mistral Large',
        context_window=32000,
    )
    row.update(overrides)
    return row


class TestCatalogRowMappingNoLeak:
    """Unit-tests _catalog_row_to_item directly -- the exact function that
    decides what `id` a normal user sees. WHERE-clause filtering
    (`public_id IS NOT NULL`) is covered separately below
    (TestLoadCatalogRowsFilterSql), so this class covers the id substitution."""

    def test_flag_on_serves_public_id(self, monkeypatch):
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        row = _seeded_public_row()
        item = content_mod._catalog_row_to_item(row)
        assert item['id'] == 'sanjab/mistral-large'
        assert not item['id'].startswith('bynara/')

    def test_flag_off_serves_raw_id_unchanged(self, monkeypatch):
        """This is the rollback guarantee: flag OFF (including simply unset,
        the real default) must reproduce today's exact behavior."""
        monkeypatch.delenv('PUBLIC_MODEL_IDS_ENABLED', raising=False)
        row = _seeded_public_row()
        item = content_mod._catalog_row_to_item(row)
        assert item['id'] == 'bynara/mistral-large'

    def test_flag_on_but_no_public_id_falls_back_to_raw_id(self, monkeypatch):
        """Defense in depth: _load_catalog_rows already filters to
        `public_id IS NOT NULL` when the flag is on, so this row shape isn't
        expected from a real query -- but the mapping function itself must
        not crash or silently serve None if it's ever handed one anyway."""
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        row = _seeded_public_row(public_id=None)
        item = content_mod._catalog_row_to_item(row)
        assert item['id'] == 'bynara/mistral-large'

    def test_no_leaked_ids_have_route_prefix_or_free_when_flag_on(self, monkeypatch):
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        rows = [
            _seeded_public_row(id='bynara/mistral-large', provider_model_id='bynara/mistral-large', public_id='sanjab/mistral-large'),
            _seeded_public_row(id='bynara/mimo-v2.5-free', provider_model_id='bynara/mimo-v2.5-free', public_id='sanjab/mimo-v2.5'),
            _seeded_public_row(id='gemini-api/models/gemini-3-flash-preview', provider_model_id='gemini-api/models/gemini-3-flash-preview', public_id='sanjab/gemini-3-flash-preview'),
        ]
        route_prefixes = ('bynara/', 'kr/', 'cc/', 'cx/', 'ag/', 'gemini-api/models/', 'nvidia/')
        for row in rows:
            item = content_mod._catalog_row_to_item(row)
            assert item['id'].startswith('sanjab/'), item['id']
            assert '-free' not in item['id'], item['id']
            assert not any(item['id'].startswith(p) for p in route_prefixes), item['id']


class TestLoadCatalogRowsFilterSql:
    """_load_catalog_rows must add `AND public_id IS NOT NULL` to its SQL
    only when the flag is on -- flag off must send the exact same query as
    before this migration (the rollback guarantee)."""

    @pytest.mark.asyncio
    async def test_flag_on_adds_public_id_filter(self, monkeypatch, mock_async_session):
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        captured = {}

        async def _execute(stmt, *a, **k):
            captured['sql'] = str(stmt)
            result = MagicMock()
            result.fetchall.return_value = []
            return result

        mock_async_session.execute = _execute
        await content_mod._load_catalog_rows()
        assert 'public_id IS NOT NULL' in captured['sql']

    @pytest.mark.asyncio
    async def test_flag_off_omits_public_id_filter(self, monkeypatch, mock_async_session):
        monkeypatch.delenv('PUBLIC_MODEL_IDS_ENABLED', raising=False)
        captured = {}

        async def _execute(stmt, *a, **k):
            captured['sql'] = str(stmt)
            result = MagicMock()
            result.fetchall.return_value = []
            return result

        mock_async_session.execute = _execute
        await content_mod._load_catalog_rows()
        assert 'public_id IS NOT NULL' not in captured['sql']


class TestListModelsEndpointFlagBehavior:
    """/v1/models: same contract as _load_catalog_rows, exercised through the
    real endpoint via the TestClient."""

    def test_flag_off_v1_models_unchanged(self, client, mock_async_session, monkeypatch):
        from tests.conftest import make_result, make_row
        monkeypatch.delenv('PUBLIC_MODEL_IDS_ENABLED', raising=False)
        mock_async_session._execute_result = make_result(fetchall=[
            make_row(
                id='bynara/mistral-large', provider_model_id='bynara/mistral-large',
                display_name='Mistral Large', context_window=32000, availability='available',
                input_per_million=0, output_per_million=0, currency='IRT',
                usd_input_per_million=0, usd_output_per_million=0,
            )
        ])
        resp = client.get('/v1/models')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data
        assert data[0]['id'] == 'bynara/mistral-large'

    def test_flag_on_v1_models_serves_public_id(self, client, mock_async_session, monkeypatch):
        from tests.conftest import make_result, make_row
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        mock_async_session._execute_result = make_result(fetchall=[
            make_row(
                id='bynara/mistral-large', provider_model_id='bynara/mistral-large',
                public_id='sanjab/mistral-large',
                display_name='Mistral Large', context_window=32000, availability='available',
                input_per_million=0, output_per_million=0, currency='IRT',
                usd_input_per_million=0, usd_output_per_million=0,
            )
        ])
        resp = client.get('/v1/models')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data
        assert data[0]['id'] == 'sanjab/mistral-large'
        assert not data[0]['id'].startswith('bynara/')


# ── 2. conversations.py: historical usage translated at read time only ──

class TestConversationAnalyticsTranslatesAtReadTimeOnly:
    """usage_events/ledger/wallet_reservations/conversations are append-only
    and must never be rewritten -- the model string a historical row was
    billed under stays exactly as-is forever. Translation for display must
    happen only at READ time, via a LEFT JOIN against model_catalog."""

    def _capture_sqls(self, mock_async_session):
        captured: list[str] = []

        async def _execute(stmt, params=None, *a, **k):
            captured.append(str(stmt))
            result = MagicMock()
            result.fetchone.return_value = types.SimpleNamespace(c=0, total_tokens=0, total_cost=0)
            result.fetchall.return_value = []
            return result

        mock_async_session.execute = _execute
        return captured

    def test_flag_off_groups_by_raw_stored_model_no_join(self, client, mock_async_session, auth_headers, monkeypatch):
        monkeypatch.delenv('PUBLIC_MODEL_IDS_ENABLED', raising=False)
        captured = self._capture_sqls(mock_async_session)
        resp = client.get('/conversations/analytics', headers=auth_headers)
        assert resp.status_code == 200, resp.text
        models_sql = next(s for s in captured if 'GROUP BY' in s and 'usage_events' in s)
        assert 'model_catalog' not in models_sql
        assert 'GROUP BY model' in models_sql

    def test_flag_on_joins_model_catalog_never_touches_usage_events_rows(self, client, mock_async_session, auth_headers, monkeypatch):
        monkeypatch.setenv('PUBLIC_MODEL_IDS_ENABLED', 'true')
        captured = self._capture_sqls(mock_async_session)
        resp = client.get('/conversations/analytics', headers=auth_headers)
        assert resp.status_code == 200, resp.text
        models_sql = next(s for s in captured if 'GROUP BY' in s and 'usage_events' in s)
        assert 'LEFT JOIN model_catalog' in models_sql
        assert 'COALESCE(mc.public_id, ue.model)' in models_sql or 'COALESCE(mc.public_id,ue.model)' in models_sql.replace(' ', '')
        # Never an UPDATE/DELETE against the append-only usage_events table.
        assert not any('UPDATE usage_events' in s or 'DELETE FROM usage_events' in s for s in captured)
