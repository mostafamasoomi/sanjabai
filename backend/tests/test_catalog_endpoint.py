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
