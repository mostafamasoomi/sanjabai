# Pricing Source of Truth

**Versioned `pricing` table is the source of truth.**

Per `docs/product-contract.md` §3 and §6:

> "Prices are snapshots, never overwritten in place."
> "The versioned `pricing` rows are the source of truth; `model_catalog` holds a denormalized copy of the currently active price and is updated ONLY via a single unified service."

## Unified Price Service

The write paths are unified under `services/pricing.py` (to be created if not already available, or integrated into `admin_catalog.py` / `model_discovery.py`). Any change to pricing MUST:

1. Create a new row in `pricing` with an incremented `price_version` and updated `effective_from`.
2. Update the denormalized `model_catalog.input_per_million` and `model_catalog.output_per_million` columns to match the new active price.
3. Invalidate cache keys: `cache:catalog:models`, `cache:catalog:pricing`, `cache:api:pricing`.
4. Write an `audit` event: `admin.catalog.price_update`.

## Known Write Paths to Unify

1. `admin.py::set_pricing` (currently raw UPDATE on `model_catalog`)
2. `scripts/update_models.py` (writes to `pricing` but doesn't sync `model_catalog`)
3. `admin/app.py::pricing_update` (raw UPDATE on `model_catalog`)

All of these paths must be modified to use the unified `set_pricing` workflow in `services/pricing.py`.
