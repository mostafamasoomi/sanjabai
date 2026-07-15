# Multiai Pricing System Setup Report

**Date:** 2026-07-15  
**Status:** ✅ Complete

---

## Summary

Set up the pricing system and model management for Multiai. This includes OpenRouter free model integration, pricing API endpoints, automated model updates via cron, and proper proxy configuration.

---

## Files Modified

### 1. `/root/multiai/backend/litellm_config.yaml` (modified)

Updated the LiteLLM proxy config to:
- Keep all existing Bynara proxy models (mimo-v2.5, mistral-medium-3-5, etc.)
- Add 8 OpenRouter free models using `OPENROUTER_API_KEY`:
  - `qwen3-coder-free` → `openrouter/qwen/qwen3-coder:free`
  - `nemotron-3-ultra-550b-free` → `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`
  - `llama-3-3-70b-free` → `openrouter/meta-llama/llama-3.3-70b-instruct:free`
  - `gemma-4-31b-free` → `openrouter/google/gemma-4-31b-it:free`
  - `hermes-3-405b-free` → `openrouter/nousresearch/hermes-3-llama-3.1-405b:free`
  - `tencent-hy3-free` → `openrouter/tencent/hy3:free`
  - `deepseek-r1-free` → `openrouter/deepseek/deepseek-r1:free`
  - `mistral-small-3-2-free` → `openrouter/mistralai/mistral-small-3.2-24b:free`

**Key change:** OpenRouter models now use `os.environ/OPENROUTER_API_KEY` instead of `os.environ/BYNARA_API_KEY`.

### 2. `/root/multiai/docker-compose.multiai.yml` (modified)

Added to `multiai_litellm` service:
- `OPENROUTER_API_KEY` environment variable
- `NO_PROXY=api.exchangerate-api.com,openrouter.ai,api.openrouter.com` — so OpenRouter API calls and exchange rate lookups bypass the SOCKS proxy

Added to `multiai_api` service:
- `OPENROUTER_API_KEY` environment variable
- `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` — matching the litellm service config

### 3. `/root/multiai/backend/app.py` (modified)

Added two new public API endpoints:

#### `GET /api/exchange-rate`
Returns the current USD→IRR exchange rate:
```json
{
  "USD_IRR": 8500000,
  "USD_TOMAN": 850000,
  "source": "exchangerate-api.com",
  "fetchedAt": "2026-07-15T..."
}
```
- Fetches from `api.exchangerate-api.com`
- Cached in Redis for 1 hour
- Falls back to ~8,500,000 IRR/USD if API unreachable

#### `GET /api/pricing`
Returns all active model pricing in Toman:
```json
{
  "data": [
    {
      "model": "qwen/qwen3-coder:free",
      "provider": "openrouter",
      "inputPerMillion": 0,
      "outputPerMillion": 0,
      "currency": "IRT",
      "source": "openrouter_api",
      "priceVersion": 1,
      "effectiveFrom": "2026-07-15T..."
    }
  ],
  "exchangeRate": 850000,
  "margin": 0.20,
  "generatedAt": "2026-07-15T..."
}
```
- Reads from `pricing` table (versioned, active rows only)
- Cached in Redis for 2 minutes
- Free models show 0 Toman for input/output

### 4. `/root/multiai/scripts/update_models.py` (new)

Automated script that:
1. Fetches USD→IRR exchange rate from `api.exchangerate-api.com`
2. Fetches all models from OpenRouter API (`/api/v1/models`)
3. Filters free models (ID ends with `:free` or pricing is 0)
4. Updates the `pricing` table in PostgreSQL:
   - Closes old active prices (`effective_to = NOW()`)
   - Inserts new versioned rows with Toman pricing
   - Formula: `USD_price × 1,000,000 × (IRR/10) × 1.20`
5. Updates `litellm_config.yaml` if models changed
6. Logs everything to `/root/multiai/scripts/update_models.log`

**Proxy-aware:** Respects `HTTP_PROXY`/`NO_PROXY` environment variables. Requests to `openrouter.ai` and `api.exchangerate-api.com` bypass the proxy.

---

## Hermes Cron Job

| Field | Value |
|-------|-------|
| Job ID | `a383da0a3adb` |
| Name | `multiai-update-models` |
| Schedule | Every 15 minutes |
| Script | `/root/multiai/scripts/update_models.py` |
| Toolsets | `terminal`, `file` |

---

## Environment Variables Required

Add to `/root/multiai/.env`:
```bash
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxx
```

The existing `BYNARA_API_KEY` and `BYNARA_API_KEY_2` continue to work for Bynara proxy models.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Hermes Cron (every 15m)                                  │
│   └─ update_models.py                                    │
│       ├─ GET openrouter.ai/api/v1/models                 │
│       ├─ GET api.exchangerate-api.com/v4/latest/USD      │
│       ├─ UPDATE pricing table (PostgreSQL)                │
│       └─ UPDATE litellm_config.yaml (if changed)         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ multiai_api (FastAPI)                                     │
│   ├─ GET /api/pricing      → pricing table + Redis cache  │
│   └─ GET /api/exchange-rate → external API + Redis cache   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ multiai_litellm (LiteLLM proxy)                           │
│   ├─ Bynara models (mimo-v2.5, etc.) via BYNARA_API_KEY   │
│   └─ OpenRouter free models via OPENROUTER_API_KEY         │
└─────────────────────────────────────────────────────────┘
```

---

## Next Steps

1. **Add `OPENROUTER_API_KEY` to `.env`** — required for OpenRouter models to work
2. **Rebuild containers:** `docker compose -f docker-compose.multiai.yml up -d --build`
3. **Verify endpoints:**
   - `curl http://localhost:8081/api/exchange-rate`
   - `curl http://localhost:8081/api/pricing`
4. **Test model availability:** `curl http://localhost:4000/v1/models` (inside litellm network)
5. **Monitor logs:** `tail -f /root/multiai/scripts/update_models.log`
