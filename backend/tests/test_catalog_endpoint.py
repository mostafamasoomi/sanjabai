"""Contract test: backend /catalog/models must return the agreed shape."""
import pytest
from conftest import client


def test_catalog_models_shape(client):
    """Catalog endpoint returns {data, generatedAt, source} with item fields."""
    resp = client.get('/catalog/models')
    assert resp.status_code == 200
    body = resp.json()
    assert 'data' in body
    assert 'generatedAt' in body
    assert 'source' in body
    assert isinstance(body['data'], list)


def test_catalog_model_item_fields(client):
    """Each catalog item carries the contract fields when present."""
    resp = client.get('/catalog/models')
    body = resp.json()
    if not body['data']:
        pytest.skip('no catalog rows configured; fallback path')
    item = body['data'][0]
    for field in ('id', 'providerModelId', 'provider', 'displayName', 'pricing', 'availability'):
        assert field in item, f'missing {field} in catalog item'
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
