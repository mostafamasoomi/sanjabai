from datetime import datetime, timezone
from decimal import Decimal

import pytest

from schemas.catalog import CatalogPricing, ModelCatalogItem


def valid_item(**overrides):
    item = {
        "id": "deepseek-v3",
        "provider_model_id": "deepseek/deepseek-v3",
        "provider": "deepseek",
        "display_name": "DeepSeek V3",
        "modalities": {"input": ["text"], "output": ["text"]},
        "capabilities": ["chat"],
        "recommended_for": ["coding"],
        "context_window": 32768,
        "pricing": {
            "currency": "IRT",
            "input_per_million": "100",
            "output_per_million": "200",
            "price_version": "v1",
            "effective_from": datetime.now(timezone.utc),
        },
        "availability": "available",
        "audience": ["consumer", "developer"],
        "last_verified_at": datetime.now(timezone.utc),
        "provenance": "admin-approved",
    }
    item.update(overrides)
    return item


def test_catalog_item_accepts_contract():
    item = ModelCatalogItem.model_validate(valid_item())
    assert item.id == "deepseek-v3"
    assert item.pricing.currency == "IRT"


def test_catalog_rejects_zero_context():
    with pytest.raises(ValueError):
        ModelCatalogItem.model_validate(valid_item(context_window=0))


def test_catalog_rejects_unknown_modality_key():
    with pytest.raises(ValueError, match="modalities"):
        ModelCatalogItem.model_validate(valid_item(modalities={"video": ["input"], "output": ["text"]}))


def test_pricing_rejects_negative_amount():
    with pytest.raises(ValueError):
        CatalogPricing.model_validate({
            "currency": "IRT",
            "input_per_million": Decimal("-1"),
            "output_per_million": 1,
            "price_version": "v1",
            "effective_from": datetime.now(timezone.utc),
        })


def test_catalog_rejects_invalid_currency():
    with pytest.raises(ValueError):
        ModelCatalogItem.model_validate(valid_item(pricing={
            "currency": "USD",
            "input_per_million": "1",
            "output_per_million": "1",
            "price_version": "v1",
            "effective_from": datetime.now(timezone.utc),
        }))


def test_catalog_rejects_invalid_availability():
    with pytest.raises(ValueError):
        ModelCatalogItem.model_validate(valid_item(availability="on-fire"))


def test_catalog_rejects_unstable_id():
    with pytest.raises(ValueError, match="stable"):
        ModelCatalogItem.model_validate(valid_item(id="Not A Valid ID!"))


def test_catalog_accepts_provider_scoped_id():
    item = ModelCatalogItem.model_validate(valid_item(id="deepseek/deepseek-v3.1"))
    assert item.id == "deepseek/deepseek-v3.1"


def test_catalog_rejects_deprecated_before_effective():
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="deprecated_at"):
        ModelCatalogItem.model_validate(valid_item(
            deprecated_at=now - timedelta(days=10),
            pricing={
                "currency": "IRT",
                "input_per_million": "1",
                "output_per_million": "1",
                "price_version": "v1",
                "effective_from": now,
            },
        ))


def test_catalog_rejects_negative_max_output_tokens():
    with pytest.raises(ValueError):
        ModelCatalogItem.model_validate(valid_item(max_output_tokens=-5))


def test_catalog_rejects_nonpositive_rate_limit():
    with pytest.raises(ValueError, match="rate limits"):
        ModelCatalogItem.model_validate(valid_item(rate_limit={"requestsPerMinute": 0}))
