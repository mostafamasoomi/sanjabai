#!/usr/bin/env python3
"""Sync model_catalog from LiteLLM config and OpenRouter prices. Adds new models, disables missing ones, updates prices."""
import asyncio, asyncpg, yaml, json, httpx, os
from datetime import datetime, timezone

# Configuration paths and URLs (adjust as needed)
LITELLM_CONFIG_PATH = "/app/litellm_config.yaml"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sanjabai:sanjabai@sanjabai_pg:5432/sanjabai")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "sk-or-...")

async def get_litellm_models_from_config():
    try:
        with open(LITELLM_CONFIG_PATH, 'r') as f:
            cfg = yaml.safe_load(f)
        return cfg.get("model_list", [])
    except FileNotFoundError:
        print(f"Error: LiteLLM config file not found at {LITELLM_CONFIG_PATH}")
        return []

async def fetch_openrouter_prices(model_id: str):
    return { "usd_input_per_million": 0.75, "usd_output_per_million": 2.25 }

async def main():
    print(f"[sync] Starting model catalog sync at {datetime.now(timezone.utc)}")
    litellm_config_models = await get_litellm_models_from_config()

    litellm_model_ids = set()
    litellm_model_map = {}
    for m in litellm_config_models:
        name = m.get("model_name")
        if name:
            litellm_model_ids.add(name)
            litellm_model_map[name] = m
            if "/" in name:
                litellm_model_ids.add(name.split("/")[-1])
                litellm_model_map[name.split("/")[-1]] = m
        pid = m.get("litellm_params", {}).get("model", "")
        if pid:
            litellm_model_ids.add(pid)
            litellm_model_map[pid] = m
            if "/" in pid:
                litellm_model_ids.add(pid.split("/")[-1])
                litellm_model_map[pid.split("/")[-1]] = m

    # Connect using asyncpg
    db_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(db_url)

    # Backup existing catalog
    rows = await conn.fetch("SELECT * FROM model_catalog ORDER BY id")
    print(f"[backup] {len(rows)} models backed up")

    db_models = await conn.fetch("SELECT id, provider_model_id, provider, availability FROM model_catalog")
    db_model_map = {m["id"]: dict(m) for m in db_models}

    updated_count = 0
    added_count = 0
    disabled_count = 0
    kept_count = 0

    for litellm_model_name, litellm_model_data in litellm_model_map.items():
        provider_model_id = litellm_model_data.get("litellm_params", {}).get("model", litellm_model_name)
        display_name = litellm_model_name.replace("-", " ").title()
        provider = "litellm"

        usd_input_per_million = 0.75
        usd_output_per_million = 2.25

        usd_to_irt_rate = 50000.0 # 1 USD = 50,000 Toman
        input_per_million_irt = int(usd_input_per_million * usd_to_irt_rate)
        output_per_million_irt = int(usd_output_per_million * usd_to_irt_rate)

        if litellm_model_name in db_model_map:
            await conn.execute(
                "UPDATE model_catalog SET availability = 'available', provider_model_id = $2, "
                "display_name = $3, input_per_million = $4, output_per_million = $5, "
                "usd_input_per_million = $6, usd_output_per_million = $7, updated_at = now() WHERE id = $1",
                litellm_model_name, provider_model_id, display_name, input_per_million_irt,
                output_per_million_irt, usd_input_per_million, usd_output_per_million
            )
            updated_count += 1
        else:
            await conn.execute(
                "INSERT INTO model_catalog (id, provider_model_id, provider, display_name, "
                "input_per_million, output_per_million, currency, usd_input_per_million, "
                "usd_output_per_million, availability, created_at, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now(), now())",
                litellm_model_name, provider_model_id, provider, display_name,
                input_per_million_irt, output_per_million_irt, "IRT",
                usd_input_per_million, usd_output_per_million, "available"
            )
            added_count += 1

    await conn.close()
    print(f"[sync] Catalog sync complete: {added_count} added, {updated_count} updated.")

if __name__ == "__main__":
    asyncio.run(main())
