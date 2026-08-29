"""Contract test: backend /catalog/models must return the agreed shape."""
from unittest.mock import AsyncMock, patch

import pytest
from tests.conftest import client, make_result


class _MappingRow:
    """Minimal stand-in for a SQLAlchemy Row exposing `_mapping`.

    `content._load_catalog_rows()` builds each catalog dict via
    `dict(r._mapping)`. conftest's `make_row()` returns a plain `MagicMock`,
    whose auto-mocked `_mapping` attribute is not itself dict-like, so
    `dict(r._mapping)` on it raises — this tiny stand-in gives `_mapping` a
    real dict instead.
    """

    def __init__(self, **kwargs):
        self._mapping = dict(kwargs)


def _catalog_row(**overrides):
    """A full model_catalog row, shaped exactly like the columns
    `_load_catalog_rows()` selects, so `_catalog_row_to_item` never hits a
    missing required key."""
    row = dict(
        id='tencent-hy3',
        provider_model_id='tencent/hy3',
        provider='bynara',
        display_name='Tencent Hy3',
        description=None,
        modalities={'input': ['text'], 'output': ['text']},
        capabilities=['chat'],
        recommended_for=[],
        context_window=32000,
        max_output_tokens=None,
        currency='IRT',
        input_per_million=100,
        output_per_million=200,
        cached_input_per_million=None,
        reasoning_per_million=None,
        price_version='v1',
        effective_from='2026-01-01T00:00:00Z',
        availability='available',
        audience=['consumer', 'developer'],
        rate_limit=None,
        deprecated_at=None,
        last_verified_at='2026-01-01T00:00:00Z',
        provenance='admin-approved',
        usd_input_per_million=0.01,
        usd_output_per_million=0.02,
    )
    row.update(overrides)
    return _MappingRow(**row)


def test_catalog_models_shape(client):
    """Catalog endpoint returns {data, generatedAt, source} with item fields."""
    resp = client.get('/catalog/models')
    assert resp.status_code == 200
    body = resp.json()
    assert 'data' in body
    assert 'generatedAt' in body
    assert 'source' in body
    assert isinstance(body['data'], list)


def test_catalog_model_item_fields(client, mock_async_session):
    """Each catalog item carries the contract fields when present, and NEVER
    leaks `providerModelId` / `provider` — those are admin-only (see
    GET /admin/catalog/models). Seeds a real DB row (same pattern as
    tests/test_auth.py's TestModelsEndpoint) so this exercises the
    `approved-catalog` path instead of skipping on an empty fallback list.
    """
    mock_async_session._execute_result = make_result(fetchall=[_catalog_row()])
    with patch('content._get_exchange_rate', new_callable=AsyncMock, return_value=(126488, 0)):
        resp = client.get('/catalog/models')
    body = resp.json()
    assert body['data'], 'expected a seeded catalog row; got an empty fallback list'
    item = body['data'][0]
    for field in ('id', 'displayName', 'pricing', 'availability'):
        assert field in item, f'missing {field} in catalog item'
    # The leak this test guards against: a normal user must never see the
    # provider or the upstream route id, only the public `id`.
    assert 'providerModelId' not in item, 'providerModelId leaked into the public catalog response'
    assert 'provider' not in item, 'provider leaked into the public catalog response'
    pricing = item['pricing']
    for field in ('currency', 'inputPerMillion', 'outputPerMillion', 'priceVersion', 'effectiveFrom'):
        assert field in pricing, f'missing pricing.{field}'
    assert item['availability'] in ('available', 'degraded', 'maintenance', 'disabled')
    assert item['pricing']['currency'] in ('IRR', 'IRT')


def test_catalog_pricing_shape(client):
    resp = client.get('/catalog/pricing')
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, dict)
    assert 'data' in body
    assert isinstance(body['data'], list)


# ── P2: honest-labelling gate -- serving requires an ever-probed-OK row ──
#
# `availability = 'available'` alone says nothing about whether a row has
# ever actually answered a live probe -- an unpriced-then-priced row, or one
# discovery landed and an admin later approved, could sit at `available`
# with model_health_state.last_ok_at still NULL forever. content_catalog.py
# (_load_catalog_rows, backing /catalog/models; list_models, backing
# /v1/models) and chat_models.py (get_working_models / _is_model_allowed,
# the chat allow-list every chat/compare/smart-chat/document-generator call
# site actually gates on) now all add
# `AND EXISTS (SELECT 1 FROM model_health_state s WHERE ... AND
# s.last_ok_at IS NOT NULL)` to their WHERE clause.
#
# The fakes below do NOT hardcode that filter: they inspect whether
# 'model_health_state' appears in the SQL text the code under test actually
# issues, and only then exclude rows with no recorded OK probe -- the same
# way real Postgres would evaluate the EXISTS subquery. Revert any of the
# three clauses in the source under test and the matching "excluded" test
# below goes red on its own, because the fake stops filtering and serves
# the never-probed-OK row again.

def _gated_catalog_row(**overrides):
    """A full model_catalog row covering every column either
    `_load_catalog_rows()` or `list_models()` selects, as a plain dict (not
    wrapped) so the fakes below can filter on it directly."""
    row = dict(
        id='tencent-hy3', provider_model_id='tencent/hy3', provider='bynara',
        display_name='Tencent Hy3', description=None,
        modalities={'input': ['text'], 'output': ['text']}, capabilities=['chat'],
        recommended_for=[], context_window=32000, max_output_tokens=None,
        currency='IRT', input_per_million=100, output_per_million=200,
        cached_input_per_million=None, reasoning_per_million=None,
        price_version='v1', effective_from='2026-01-01T00:00:00Z',
        availability='available', audience=['consumer', 'developer'],
        rate_limit=None, deprecated_at=None, last_verified_at='2026-01-01T00:00:00Z',
        provenance='admin-approved', usd_input_per_million=0.01,
        usd_output_per_million=0.02, public_id='sanjab/tencent-hy3', markup_pct=None,
    )
    row.update(overrides)
    return row


class _GatedRow:
    """Supports both `row.attr` access (list_models()'s raw-SQL loop) and
    `dict(row._mapping)` (_load_catalog_rows())."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self._mapping = dict(kwargs)


class _FakeQueryResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def _catalog_visible(row, ever_ok_ids, gated):
    if row.get('availability') != 'available':
        return False
    if 'admin' in (row.get('audience') or []):
        return False
    if gated and row['id'] not in ever_ok_ids and row['provider_model_id'] not in ever_ok_ids:
        return False
    return True


def _make_health_gated_execute(catalog_rows, ever_ok_ids):
    """Fake `session.execute` for content_catalog.py's two serving queries.
    Any query that does not select FROM model_catalog (get_global_markup_pct,
    _get_exchange_rate, health_map, ...) gets an empty result rather than
    being force-fit into the catalog row shape."""

    async def execute(stmt, params=None):
        sql = str(stmt)
        if 'FROM model_catalog' not in sql:
            return _FakeQueryResult([])
        gated = 'model_health_state' in sql
        rows = [_GatedRow(**r) for r in catalog_rows if _catalog_visible(r, ever_ok_ids, gated)]
        return _FakeQueryResult(rows)

    return execute


class TestCatalogModelsHonestLabellingGate:
    """/catalog/models (content_catalog._load_catalog_rows)."""

    def _rows(self):
        return [
            _gated_catalog_row(id='ok-model', provider_model_id='prov/ok-model',
                                public_id='sanjab/ok-model'),
            _gated_catalog_row(id='never-probed-model', provider_model_id='prov/never-probed',
                                public_id='sanjab/never-probed'),
        ]

    def test_never_probed_ok_row_excluded_public_row_included(self, client, mock_async_session):
        mock_async_session.execute = _make_health_gated_execute(
            self._rows(), ever_ok_ids={'ok-model', 'prov/ok-model'},
        )
        with patch('content._get_exchange_rate', new_callable=AsyncMock, return_value=(126488, 0)):
            resp = client.get('/catalog/models')
        assert resp.status_code == 200
        # served id is public_id when PUBLIC_MODEL_IDS_ENABLED, else the raw
        # `id` -- assert on whichever this env resolves to, both point at
        # the same two fixture rows.
        ids = {item['id'] for item in resp.json()['data']}
        assert ('ok-model' in ids) or ('sanjab/ok-model' in ids)
        assert 'never-probed-model' not in ids and 'sanjab/never-probed' not in ids, (
            'a model with no recorded successful probe was served on /catalog/models'
        )


class TestV1ModelsHonestLabellingGate:
    """/v1/models (content_catalog.list_models)."""

    def _rows(self):
        return [
            _gated_catalog_row(id='ok-model', provider_model_id='prov/ok-model'),
            _gated_catalog_row(id='never-probed-model', provider_model_id='prov/never-probed'),
        ]

    def test_never_probed_ok_row_excluded_public_row_included(self, client, mock_async_session):
        mock_async_session.execute = _make_health_gated_execute(
            self._rows(), ever_ok_ids={'ok-model', 'prov/ok-model'},
        )
        resp = client.get('/v1/models')
        assert resp.status_code == 200
        ids = {item['id'] for item in resp.json()['data']}
        assert 'prov/ok-model' in ids
        assert 'prov/never-probed' not in ids, (
            'a model with no recorded successful probe was served on /v1/models'
        )


class _ChatModelsGatedSession:
    """Fake session for chat_models.py's get_working_models()/
    _is_model_allowed() -- same non-hardcoded gating approach as
    _make_health_gated_execute above, applied to both of that module's
    queries (the working-set builder AND the per-model DB fallback
    _is_model_allowed() falls through to on a cache miss)."""

    def __init__(self, catalog_rows, ever_ok_ids):
        self._rows = catalog_rows
        self._ever_ok_ids = ever_ok_ids

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        params = params or {}
        gated = 'model_health_state' in sql

        if 'SELECT provider_model_id, id, public_id' in sql:
            rows = [_GatedRow(**r) for r in self._rows if _catalog_visible(r, self._ever_ok_ids, gated)]
            return _FakeQueryResult(rows)
        if 'SELECT 1 FROM model_catalog WHERE' in sql:
            mid = params.get('mid')
            match = next(
                (r for r in self._rows
                 if mid in (r['id'], r['provider_model_id'], r.get('public_id'))
                 and _catalog_visible(r, self._ever_ok_ids, gated)),
                None,
            )
            return _FakeQueryResult([(1,)] if match else [])
        return _FakeQueryResult([])

    async def commit(self):
        pass


class _ChatModelsGatedSessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        pass


class TestChatAllowListHonestLabellingGate:
    """chat_models.py's get_working_models()/_is_model_allowed() -- the
    real-time gate every chat/compare/smart-chat/document-generator call
    site (chat.py, chat_web.py, chat_smart.py, chat_compare.py, combos.py,
    document_generator.py) actually uses before routing a request to a
    model -- must also refuse to serve a row that has never once answered
    a live probe."""

    def _rows(self):
        return [
            dict(id='ok-model', provider_model_id='prov/ok-model', public_id=None,
                 availability='available', audience=[]),
            dict(id='never-probed-model', provider_model_id='prov/never-probed', public_id=None,
                 availability='available', audience=[]),
        ]

    @pytest.mark.asyncio
    async def test_working_set_excludes_the_never_probed_row(self):
        import chat_models
        session = _ChatModelsGatedSession(self._rows(), ever_ok_ids={'ok-model', 'prov/ok-model'})
        with patch.object(chat_models.chat, 'async_session', lambda: _ChatModelsGatedSessionCtx(session)):
            working = await chat_models.get_working_models()
        assert 'ok-model' in working
        assert 'never-probed-model' not in working, (
            'a model with no recorded successful probe was in the working-model set'
        )

    @pytest.mark.asyncio
    async def test_is_model_allowed_rejects_the_never_probed_row(self):
        """The real per-request gate: exercises BOTH the cached working set
        AND the DB fallback _is_model_allowed() falls through to on a
        cache miss, so a gate missing from either query alone turns this
        test red."""
        import chat_models
        session = _ChatModelsGatedSession(self._rows(), ever_ok_ids={'ok-model', 'prov/ok-model'})
        with patch.object(chat_models.chat, 'async_session', lambda: _ChatModelsGatedSessionCtx(session)):
            assert await chat_models._is_model_allowed('ok-model') is True
            assert await chat_models._is_model_allowed('never-probed-model') is False, (
                'a model with no recorded successful probe was allowed onto the chat path'
            )
