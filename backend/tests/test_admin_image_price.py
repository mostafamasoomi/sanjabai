"""Tests for the per-model image pricing admin endpoints (admin_catalog.py).

Migration 0032 added model_catalog.image_price_per_unit (numeric, NULL for
every row). backend/images.py's POST /v1/images/generations hard-refuses
any request for a model whose image_price_per_unit is NULL -- the product
rule that no request may ever be loss-making -- so until an admin can set a
price, image generation cannot serve anything. These endpoints are the only
way to do that.

The DB column is `numeric` with no scale constraint, so the endpoint is the
only guard that keeps money integral -- a float payload (even an
integral-looking one like 10.0) must be rejected outright, per the
project's "money is always an integer Toman" rule.

Modelled directly on tests/test_markup.py's TestAdminMarkupModels, which
covers the sibling markup_pct endpoints in the same file with the same
mocking conventions (admin_ok fixture, mock_async_session, make_result).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import admin_catalog as admin_catalog_mod
from tests.conftest import make_result


@pytest.fixture
def admin_ok():
    with patch('admin_catalog.admin_required', new=AsyncMock(return_value=True)):
        yield


class _MappingRow:
    """Minimal stand-in for a SQLAlchemy Row exposing `_mapping` -- same
    helper test_markup.py and test_catalog_endpoint.py use, since
    `dict(r._mapping)` is what list_media_models() calls on each row."""

    def __init__(self, **kwargs):
        self._mapping = dict(kwargs)


# ── _parse_image_price: pure validation, no DB/HTTP involved ───────────

class TestParseImagePrice:
    def test_none_means_clear_and_is_always_valid(self):
        assert admin_catalog_mod._parse_image_price(None) == (None, None)

    def test_zero_is_a_valid_price(self):
        assert admin_catalog_mod._parse_image_price(0) == (0, None)

    def test_positive_integer_is_valid(self):
        assert admin_catalog_mod._parse_image_price(5000) == (5000, None)

    def test_integer_looking_string_is_accepted(self):
        assert admin_catalog_mod._parse_image_price('5000') == (5000, None)

    def test_negative_integer_is_rejected(self):
        price, err = admin_catalog_mod._parse_image_price(-1)
        assert price is None
        assert err

    def test_float_is_rejected_even_when_integral(self):
        """The core financial guard: a JSON float that happens to be a
        whole number (10.0) must still be rejected, not silently coerced
        to 10 -- the DB column is `numeric` with no scale constraint, so
        this endpoint is the only thing enforcing integer Toman."""
        price, err = admin_catalog_mod._parse_image_price(10.0)
        assert price is None
        assert err

    def test_fractional_float_is_rejected(self):
        price, err = admin_catalog_mod._parse_image_price(10.5)
        assert price is None
        assert err

    def test_fractional_string_is_rejected(self):
        price, err = admin_catalog_mod._parse_image_price('10.5')
        assert price is None
        assert err

    def test_bool_is_rejected_not_coerced_to_zero_or_one(self):
        """bool is a subclass of int in Python -- isinstance(True, int) is
        True -- so True must be explicitly rejected or it would silently
        parse as the price 1."""
        price, err = admin_catalog_mod._parse_image_price(True)
        assert price is None
        assert err

    def test_garbage_string_is_rejected(self):
        price, err = admin_catalog_mod._parse_image_price('not-a-number')
        assert price is None
        assert err


# ── GET /admin/catalog/media-models ─────────────────────────────────────

class TestListMediaModels:
    def test_requires_admin(self, client):
        resp = client.get('/admin/catalog/media-models')
        assert resp.status_code == 401

    def test_returns_media_rows(self, client, admin_ok, mock_async_session):
        mock_async_session._execute_result = make_result(fetchall=[
            _MappingRow(id='openrouter/openai/gpt-image', provider_model_id='openrouter/openai/gpt-image',
                        display_name='GPT Image', availability='maintenance',
                        image_price_per_unit=None, markup_pct=None),
        ])
        resp = client.get('/admin/catalog/media-models')
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]['id'] == 'openrouter/openai/gpt-image'
        assert body[0]['image_price_per_unit'] is None

    def test_query_filters_on_output_modality_containing_image(self, client, admin_ok, mock_async_session):
        """Guards against a regression back to a naive LIKE/id-pattern
        filter -- the endpoint must use the same modalities.output JSONB
        containment check migration 0031 populated, not a heuristic."""
        captured = {}

        async def _execute(stmt, params=None, *a, **k):
            captured['sql'] = str(stmt)
            return make_result(fetchall=[])

        mock_async_session.execute = _execute
        resp = client.get('/admin/catalog/media-models')
        assert resp.status_code == 200
        assert "modalities->'output'" in captured['sql']
        assert 'image' in captured['sql']


# ── POST /admin/catalog/models/{model_id}/image-price ───────────────────

class TestSetModelImagePrice:
    def test_requires_admin(self, client):
        resp = client.post('/admin/catalog/models/m1/image-price', json={'image_price_per_unit': 100})
        assert resp.status_code == 401

    def test_set_price_on_model_with_slash_in_id(self, client, admin_ok, mock_async_session):
        """Most model_catalog ids contain a `/` (e.g.
        openrouter/openai/gpt-image) -- the route must use a `:path`
        converter, or this 404s before ever reaching the handler."""
        async def _execute(stmt, params=None, *a, **k):
            assert params['id'] == 'openrouter/openai/gpt-image'
            assert params['p'] == 5000
            result = make_result(fetchone=None)
            result.rowcount = 1
            return result

        mock_async_session.execute = _execute
        with patch.object(admin_catalog_mod, 'rds', AsyncMock()) as mock_rds:
            resp = client.post(
                '/admin/catalog/models/openrouter/openai/gpt-image/image-price',
                json={'image_price_per_unit': 5000},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body['image_price_per_unit'] == 5000
        mock_rds.delete.assert_awaited_once_with(
            'cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing'
        )

    def test_clear_price_accepts_explicit_null(self, client, admin_ok, mock_async_session):
        async def _execute(stmt, params=None, *a, **k):
            assert params['p'] is None, 'image_price_per_unit: null must clear the price, not reject it'
            result = make_result(fetchone=None)
            result.rowcount = 1
            return result

        mock_async_session.execute = _execute
        resp = client.post('/admin/catalog/models/m1/image-price', json={'image_price_per_unit': None})
        assert resp.status_code == 200
        assert resp.json()['image_price_per_unit'] is None

    def test_404_for_unknown_model(self, client, admin_ok, mock_async_session):
        async def _execute(stmt, params=None, *a, **k):
            result = make_result(fetchone=None)
            result.rowcount = 0
            return result

        mock_async_session.execute = _execute
        resp = client.post('/admin/catalog/models/does-not-exist/image-price', json={'image_price_per_unit': 100})
        assert resp.status_code == 404

    def test_rejects_negative_price(self, client, admin_ok, mock_async_session):
        resp = client.post('/admin/catalog/models/m1/image-price', json={'image_price_per_unit': -100})
        assert resp.status_code == 400

    def test_rejects_float_price(self, client, admin_ok, mock_async_session):
        """The money-integrity rule end-to-end through the HTTP layer, not
        just the pure validator above."""
        resp = client.post('/admin/catalog/models/m1/image-price', json={'image_price_per_unit': 99.9})
        assert resp.status_code == 400

    def test_invalidates_pricing_caches_on_success(self, client, admin_ok, mock_async_session):
        async def _execute(stmt, params=None, *a, **k):
            result = make_result(fetchone=None)
            result.rowcount = 1
            return result

        mock_async_session.execute = _execute
        with patch.object(admin_catalog_mod, 'rds', AsyncMock()) as mock_rds:
            resp = client.post('/admin/catalog/models/m1/image-price', json={'image_price_per_unit': 1000})
        assert resp.status_code == 200
        mock_rds.delete.assert_awaited_once_with(
            'cache:catalog:models', 'cache:catalog:pricing', 'cache:api:pricing'
        )
