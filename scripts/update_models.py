#!/usr/bin/env python3
"""Fetch free models from OpenRouter, update pricing table and litellm config.

Run periodically (e.g. every 15 minutes via cron).  Logs to
/root/sanjhubai/scripts/update_models.log.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
LOG_FILE = SCRIPT_DIR / "update_models.log"
CONFIG_PATH = Path("/root/sanjhubai/backend/litellm_config.yaml")
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://sanjhubai:sanjhubai@127.0.0.1:5432/sanjhubai",
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/USD"
EXCHANGE_RATE_CACHE = SCRIPT_DIR / ".exchange_rate.json"

MARGIN = 1.20  # 20 % margin
TOMAN_PER_USD_DEFAULT = 850_000  # fallback if API fails

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("update_models")

# ── Proxy config ───────────────────────────────────────────────────────────
PROXY = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
NO_PROXY_STR = os.getenv("NO_PROXY", "")
NO_PROXY_SET = {h.strip() for h in NO_PROXY_STR.split(",") if h.strip()}


def _should_proxy(host: str) -> bool:
    """Return True if requests to *host* should go through the proxy."""
    for domain in NO_PROXY_SET:
        if host == domain or host.endswith("." + domain):
            return False
    return bool(PROXY)


def _make_client(host: str) -> httpx.Client:
    kwargs: dict = {"timeout": 30}
    if _should_proxy(host) and PROXY:
        kwargs["proxy"] = PROXY
    return httpx.Client(**kwargs)


# ── Exchange rate ──────────────────────────────────────────────────────────
def get_exchange_rate() -> float:
    """USD → IRR exchange rate."""
    # Try cached (valid 1 hour)
    if EXCHANGE_RATE_CACHE.exists():
        try:
            data = json.loads(EXCHANGE_RATE_CACHE.read_text())
            if time.time() - data.get("ts", 0) < 3600:
                return data["rate"]
        except Exception:
            pass

    try:
        client = _make_client("api.exchangerate-api.com")
        resp = client.get(EXCHANGE_RATE_URL, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["rates"]["IRR"])
        EXCHANGE_RATE_CACHE.write_text(json.dumps({"rate": rate, "ts": time.time()}))
        log.info("Exchange rate fetched: 1 USD = %s IRR", rate)
        return rate
    except Exception as exc:
        log.warning("Failed to fetch exchange rate: %s — using default", exc)
        return TOMAN_PER_USD_DEFAULT * 10  # IRR default


# ── OpenRouter models ─────────────────────────────────────────────────────
def fetch_openrouter_models() -> list[dict]:
    """Return list of model dicts from OpenRouter /models endpoint."""
    if not OPENROUTER_API_KEY:
        log.error("OPENROUTER_API_KEY not set — skipping model fetch")
        return []

    try:
        client = _make_client("openrouter.ai")
        resp = client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            follow_redirects=True,
        )
        resp.raise_for_status()
        models = resp.json().get("data", [])
        log.info("Fetched %d models from OpenRouter", len(models))
        return models
    except Exception as exc:
        log.error("Failed to fetch OpenRouter models: %s", exc)
        return []


def filter_free_models(models: list[dict]) -> list[dict]:
    """Keep only models whose id ends with ':free' or have zero pricing."""
    free = []
    for m in models:
        mid = m.get("id", "")
        pricing = m.get("pricing", {})
        prompt_price = float(pricing.get("prompt", "0") or "0")
        completion_price = float(pricing.get("completion", "0") or "0")
        if mid.endswith(":free") or (prompt_price == 0 and completion_price == 0):
            free.append(m)
    return free


# ── Database operations ───────────────────────────────────────────────────
def get_db_engine():
    """Create a sync SQLAlchemy engine (requires psycopg2-binary or uses asyncpg trick)."""
    from sqlalchemy import create_engine
    sync_url = DB_URL.replace("+asyncpg", "+psycopg2") if "+asyncpg" in DB_URL else DB_URL
    # Fallback: use sqlite for local dev
    try:
        return create_engine(sync_url, pool_pre_ping=True)
    except Exception:
        log.warning("Cannot create sync engine for %s, trying raw asyncpg approach", sync_url)
        return None


def update_pricing_table(models: list[dict], irr_rate: float) -> int:
    """Upsert pricing for each model. Returns count of changed rows."""
    from sqlalchemy import create_engine, text

    # We need psycopg2 for sync; try it, fall back to asyncpg via subprocess
    engine = get_db_engine()
    if engine is None:
        return update_pricing_via_subprocess(models, irr_rate)

    toman_rate = irr_rate / 10  # IRR → Toman
    changed = 0

    with engine.begin() as conn:
        for m in models:
            mid = m["id"]
            pricing = m.get("pricing", {})
            prompt_usd = float(pricing.get("prompt", "0") or "0")
            completion_usd = float(pricing.get("completion", "0") or "0")

            # Convert: USD/token → per-million tokens → Toman with margin
            input_toman = int(prompt_usd * 1_000_000 * toman_rate * MARGIN)
            output_toman = int(completion_usd * 1_000_000 * toman_rate * MARGIN)

            # Check if active price exists and differs
            row = conn.execute(
                text("""
                    SELECT id, input_per_million, output_per_million
                    FROM pricing
                    WHERE model = :model AND effective_to IS NULL
                    ORDER BY effective_from DESC, price_version DESC
                    LIMIT 1
                """),
                {"model": mid},
            ).fetchone()

            if row and row.input_per_million == input_toman and row.output_per_million == output_toman:
                continue  # no change

            # Get next version
            max_ver = conn.execute(
                text("SELECT COALESCE(MAX(price_version), 0) FROM pricing WHERE model = :model"),
                {"model": mid},
            ).scalar() or 0

            # Close old version
            conn.execute(
                text("UPDATE pricing SET effective_to = NOW() WHERE model = :model AND effective_to IS NULL"),
                {"model": mid},
            )

            # Insert new version
            conn.execute(
                text("""
                    INSERT INTO pricing (model, provider, input_per_million, output_per_million, currency, source, price_version, effective_from, effective_to, created_at)
                    VALUES (:model, 'openrouter', :input, :output, 'IRT', 'openrouter_api', :ver, NOW(), NULL, NOW())
                """),
                {"model": mid, "input": input_toman, "output": output_toman, "ver": max_ver + 1},
            )
            changed += 1
            log.info("Updated pricing for %s: input=%d, output=%d Toman (v%d)", mid, input_toman, output_toman, max_ver + 1)

    engine.dispose()
    return changed


def update_pricing_via_subprocess(models: list[dict], irr_rate: float) -> int:
    """Fallback: write a temp SQL file and run it via docker exec."""
    toman_rate = irr_rate / 10
    sql_lines = ["BEGIN;"]
    for m in models:
        mid = m["id"]
        pricing = m.get("pricing", {})
        prompt_usd = float(pricing.get("prompt", "0") or "0")
        completion_usd = float(pricing.get("completion", "0") or "0")
        input_toman = int(prompt_usd * 1_000_000 * toman_rate * MARGIN)
        output_toman = int(completion_usd * 1_000_000 * toman_rate * MARGIN)
        escaped_mid = mid.replace("'", "''")
        sql_lines.append(f"""
            UPDATE pricing SET effective_to = NOW()
            WHERE model = '{escaped_mid}' AND effective_to IS NULL;
            INSERT INTO pricing (model, provider, input_per_million, output_per_million, currency, source, price_version, effective_from, effective_to, created_at)
            SELECT '{escaped_mid}', 'openrouter', {input_toman}, {output_toman}, 'IRT', 'openrouter_api',
                   COALESCE(MAX(price_version), 0) + 1, NOW(), NULL, NOW()
            FROM pricing WHERE model = '{escaped_mid}';
        """)
    sql_lines.append("COMMIT;")
    sql_file = SCRIPT_DIR / "_pricing_update.sql"
    sql_file.write_text("\n".join(sql_lines))
    log.info("Wrote SQL to %s — run manually via: docker exec -i sanjhubai-sanjhubai_pg-1 psql -U sanjhubai < %s", sql_file, sql_file)
    return len(models)


# ── LiteLLM config update ─────────────────────────────────────────────────
def update_litellm_config(free_models: list[dict]) -> bool:
    """Update litellm_config.yaml with free OpenRouter models. Returns True if changed."""
    if not CONFIG_PATH.exists():
        log.warning("Config not found at %s", CONFIG_PATH)
        return False

    config = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    model_list = config.get("model_list", [])

    # Separate Bynara models from OpenRouter models
    bynara_models = [m for m in model_list if "bynara" in str(m.get("litellm_params", {}).get("api_base", ""))]

    # Build new OpenRouter entries
    known_free_ids = {m["id"] for m in free_models}
    or_models = []
    for m in free_models:
        mid = m["id"]  # e.g. "qwen/qwen3-coder:free"
        short = mid.split("/")[1].replace(":free", "").replace(".", "-") if "/" in mid else mid.replace("/", "-").replace(":", "-")
        model_name = f"{short}-free"
        or_models.append({
            "model_name": model_name,
            "litellm_params": {
                "model": f"openrouter/{mid}",
                "api_key": "os.environ/OPENROUTER_API_KEY",
            },
        })

    new_config = {
        "model_list": bynara_models + or_models,
        "litellm_settings": config.get("litellm_settings", {"drop_params": True, "request_timeout": 90}),
    }

    old_yaml = yaml.dump(config, default_flow_style=True, sort_keys=False)
    new_yaml = yaml.dump(new_config, default_flow_style=True, sort_keys=False)

    if old_yaml.strip() == new_yaml.strip():
        log.info("LiteLLM config unchanged")
        return False

    CONFIG_PATH.write_text(new_yaml)
    log.info("LiteLLM config updated: %d bynara + %d openrouter models", len(bynara_models), len(or_models))
    return True


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    log.info("=== Model update started ===")

    # 1. Fetch exchange rate
    irr_rate = get_exchange_rate()
    log.info("Exchange rate: 1 USD = %s IRR (1 USD = %.0f Toman)", irr_rate, irr_rate / 10)

    # 2. Fetch OpenRouter models
    all_models = fetch_openrouter_models()
    if not all_models:
        log.warning("No models fetched — aborting")
        return

    # 3. Filter free models
    free_models = filter_free_models(all_models)
    log.info("Found %d free models out of %d total", len(free_models), len(all_models))

    if not free_models:
        log.warning("No free models found")
        return

    # 4. Update pricing table
    changed = update_pricing_table(free_models, irr_rate)
    log.info("Pricing: %d model(s) updated/inserted", changed)

    # 5. Update litellm config
    config_changed = update_litellm_config(free_models)
    if config_changed:
        log.info("LiteLLM config was updated — consider restarting the container")

    log.info("=== Model update finished ===")


if __name__ == "__main__":
    main()
