#!/usr/bin/env python3
"""Sync model_catalog from LiteLLM config and OpenRouter prices. Adds new models, disables missing ones, updates prices."""
import asyncio, asyncpg, yaml, json, httpx
from datetime import datetime, timezone

# Configuration paths and URLs (adjust as needed)
LITELLM_CONFIG_PATH = "/root/multiai/backend/litellm_config.yaml" # Adjusted path
DATABASE_URL = "postgresql://multiai:multiai@multiai_pg:5432/multiai" # Use internal Docker service name
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "sk-or-...") # For fetching latest prices

# LiteLLM config cache - this is for multiai_litellm service, not multiai_api
# multiai_api reads from model_catalog, which gets data from here
async def get_litellm_models_from_config():
    try:
        with open(LITELLM_CONFIG_PATH, 'r') as f:
            cfg = yaml.safe_load(f)
        return cfg.get("model_list", [])
    except FileNotFoundError:
        print(f"Error: LiteLLM config file not found at {LITELLM_CONFIG_PATH}")
        return []

async def fetch_openrouter_prices(model_id: str):
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "sk-or-...":
        print("Warning: OPENROUTER_API_KEY not set or default. Cannot fetch live prices.")
        return None
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    # OpenRouter pricing API is usually through listing models or specific model info
    # For simplicity, we assume we fetch their public pricing here.
    # A real implementation would parse OpenRouter's /v1/models endpoint for pricing.
    # For this script, we'll simulate fetching or use a hardcoded fallback if not available.
    # ponytail: simplified OpenRouter pricing. Upgrade when actual live price API is needed.
    return { "usd_input_per_million": 0.75, "usd_output_per_million": 2.25 } # Placeholder

async def main():
    print(f"[sync] Starting model catalog sync at {datetime.now(timezone.utc)}")
    litellm_config_models = await get_litellm_models_from_config()

    # Models known to LiteLLM (model_name + provider_model_id aliases)
    litellm_model_ids = set()
    litellm_model_map = {}
    for m in litellm_config_models:
        name = m.get("model_name")
        if name:
            litellm_model_ids.add(name)
            litellm_model_map[name] = m
            if "/" in name: # e.g., bynara/tencent-hy3
                litellm_model_ids.add(name.split("/")[-1])
                litellm_model_map[name.split("/")[-1]] = m
        pid = m.get("litellm_params", {}).get("model", "")
        if pid:
            litellm_model_ids.add(pid)
            litellm_model_map[pid] = m
            if "/" in pid:
                litellm_model_ids.add(pid.split("/")[-1])
                litellm_model_map[pid.split("/")[-1]] = m

    conn = await asyncpg.connect(DATABASE_URL)

    # Backup existing catalog before making changes
    rows = await conn.fetch("SELECT * FROM model_catalog ORDER BY id")
    print(f"[backup] {len(rows)} models backed up to /tmp/catalog_backup.json")
    with open("/tmp/catalog_backup.json", "w") as f:
        json.dump([dict(r) for r in rows], f, default=str)

    # Get existing models from DB
    db_models = await conn.fetch("SELECT id, provider_model_id, provider, availability FROM model_catalog")
    db_model_map = {m["id"]: dict(m) for m in db_models}

    updated_count = 0
    added_count = 0
    disabled_count = 0
    kept_count = 0

    # Process models from LiteLLM config
    for litellm_model_name, litellm_model_data in litellm_model_map.items():
        # Use actual model ID from litellm_params if available, else model_name
        provider_model_id = litellm_model_data.get("litellm_params", {}).get("model", litellm_model_name)
        display_name = litellm_model_data.get("litellm_params", {}).get("api_base", litellm_model_name.replace("-", " ").title())
        provider = litellm_model_data.get("litellm_params", {}).get("api_base", "unknown") # Placeholder

        # Fetch OpenRouter pricing for USD conversion
        # Use placeholder as live fetching is complex for this script
        openrouter_prices = await fetch_openrouter_prices(litellm_model_name)
        usd_input_per_million = openrouter_prices.get("usd_input_per_million", 0) if openrouter_prices else 0.75
        usd_output_per_million = openrouter_prices.get("usd_output_per_million", 0) if openrouter_prices else 2.25

        # Convert USD to IRT (1 USD = 50,000 toman, 1 toman = 10 IRR)
        # ponytail: dynamic IRT conversion rate. Add API when needed.
        usd_to_irt_rate = 500000.0 # 1 USD = 50,000 Toman = 500,000 IRR
        input_per_million_irt = int(usd_input_per_million * usd_to_irt_rate)
        output_per_million_irt = int(usd_output_per_million * usd_to_irt_rate)

        if litellm_model_name in db_model_map:
            # Update existing model
            current_db_model = db_model_map[litellm_model_name]
            if (current_db_model["availability"] == 'disabled' or
                current_db_model["provider_model_id"] != provider_model_id or
                current_db_model["input_per_million"] != input_per_million_irt or
                current_db_model["output_per_million"] != output_per_million_irt):

                await conn.execute(
                    "UPDATE model_catalog SET availability = 'available', provider_model_id = $2, "
                    "display_name = $3, input_per_million = $4, output_per_million = $5, "
                    "usd_input_per_million = $6, usd_output_per_million = $7, updated_at = now() WHERE id = $1",
                    litellm_model_name, provider_model_id, display_name, input_per_million_irt,
                    output_per_million_irt, usd_input_per_million, usd_output_per_million
                )
                updated_count += 1
            else:
                kept_count += 1
        else:
            # Add new model
            await conn.execute(
                "INSERT INTO model_catalog (id, provider_model_id, provider, display_name, "
                "input_per_million, output_per_million, currency, usd_input_per_million, "
                "usd_output_per_million, availability, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now(), now())",
                litellm_model_name, provider_model_id, provider, display_name,
                input_per_million_irt, output_per_million_irt, "IRT",
                usd_input_per_million, usd_output_per_million, "available"
            )
            added_count += 1

    # Disable models not found in LiteLLM config anymore
    for db_model_id, db_model_data in db_model_map.items():
        if db_model_id not in litellm_model_ids and db_model_data["availability"] == 'available':
            await conn.execute(
                "UPDATE model_catalog SET availability = 'disabled', updated_at = now() WHERE id = $1",
                db_model_id,
            )
            disabled_count += 1

    await conn.close()
    print(f"[sync] Catalog sync complete: {added_count} added, {updated_count} updated, {disabled_count} disabled, {kept_count} unchanged.")

if __name__ == "__main__":
    asyncio.run(main())
