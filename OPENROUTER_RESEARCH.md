# OpenRouter API Research & Pricing Analysis

**Date:** 2026-07-15  
**Total Models Available:** 343

---

## 1. Environment Configuration

### OPENROUTER_API_KEY
- **Status:** NOT found in `/root/multiai/.env`
- The `.env` file exists but does not contain `OPENROUTER_API_KEY`
- However, `BYNARA_API_KEY` is used for OpenRouter access via litellm

### Current LiteLLM Configuration (`/app/config.yaml`)

**Bynara-hosted models (via `router.bynara.id`):**
| Model Name | Backend |
|---|---|
| mimo-v2.5 | openai/mimo-v2.5 |
| mimo-v2.5-pro-ultraspeed | openai/mimo-v2.5-pro-ultraspeed |
| mimo-v2.5-pro | openai/mimo-v2.5-pro |
| mistral-medium-3-5 | openai/mistral-medium-3-5 |
| tencent-hy3 | openai/tencent-hy3 |
| gpt-5.6-luna | openai/gpt-5.6-luna |
| kimi-k2.7-code-free | openai/kimi-k2.7-code-free |

**OpenRouter free models:**
| Model Name | OpenRouter ID |
|---|---|
| qwen3-coder-free | qwen/qwen3-coder:free |
| nemotron-3-ultra-550b-free | nvidia/nemotron-3-ultra-550b-a55b:free |
| llama-3-3-70b-free | meta-llama/llama-3.3-70b-instruct:free |
| gemma-4-31b-free | google/gemma-4-31b-it:free |
| hermes-3-405b-free | nousresearch/hermes-3-llama-3.1-405b:free |
| tencent-hy3-free | tencent/hy3:free |

**Settings:** `drop_params: true`, `request_timeout: 90s`

---

## 2. Exchange Rate

| Rate | Value |
|---|---|
| 1 USD → IRR | 1,264,883.75 |
| 1 USD → Toman | ~126,488 |
| **With 20% margin** | **~151,800 Toman/USD** |

---

## 3. OpenRouter Model Pricing — Complete Table with Toman Conversion

> **Note:** Prices are per token. OpenRouter pricing is in USD per token.
> Toman price = USD price × 126,488 × 1.20 (20% margin) = USD price × 151,786

### 3.1 FREE Models (0 cost)

| Model | Context Window | Notes |
|---|---|---|
| tencent/hy3:free | 262K | Tencent Hy3 |
| poolside/laguna-xs-2.1:free | 262K | Poolside coding |
| cohere/north-mini-code:free | 256K | Code-focused |
| nvidia/nemotron-3.5-content-safety:free | 128K | Safety classifier |
| nvidia/nemotron-3-ultra-550b-a55b:free | 1M | Large 550B model |
| nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free | 256K | Reasoning |
| poolside/laguna-m.1:free | 262K | Poolside |
| google/gemma-4-26b-a4b-it:free | 262K | Gemma 4 small |
| google/gemma-4-31b-it:free | 262K | Gemma 4 medium |
| nvidia/nemotron-3-super-120b-a12b:free | 1M | Large reasoning |
| nvidia/nemotron-3-nano-30b-a3b:free | 256K | Lightweight |
| nvidia/nemotron-nano-12b-v2-vl:free | 128K | Vision-Language |
| qwen/qwen3-next-80b-a3b-instruct:free | 262K | Qwen3 Next |
| nvidia/nemotron-nano-9b-v2:free | 128K | Very small |
| openai/gpt-oss-20b:free | 131K | Open source GPT |
| qwen/qwen3-coder:free | 1M | **Best free coder** |
| cognitivecomputations/dolphin-mistral-24b-venice-edition:free | 32K | Uncensored |
| meta-llama/llama-3.3-70b-instruct:free | 131K | Llama 70B |
| meta-llama/llama-3.2-3b-instruct:free | 131K | Tiny Llama |
| nousresearch/hermes-3-llama-3.1-405b:free | 131K | **405B free!** |
| openrouter/free | 200K | Auto-routes to free models |

### 3.2 Budget Models (< $0.50/M input)

| Model | Input $/M | Output $/M | Input Toman/1K | Output Toman/1K | Context |
|---|---|---|---|---|---|
| inclusionai/ling-2.6-flash | $0.01 | $0.03 | 0.015 | 0.046 | 262K |
| ibm-granite/granite-4.0-h-micro | $0.02 | $0.11 | 0.026 | 0.168 | 131K |
| mistralai/mistral-nemo | $0.02 | $0.04 | 0.030 | 0.061 | 131K |
| meta-llama/llama-3.2-1b-instruct | $0.03 | $0.20 | 0.040 | 0.304 | 131K |
| openai/gpt-oss-20b | $0.03 | $0.13 | 0.046 | 0.197 | 131K |
| amazon/nova-micro-v1 | $0.04 | $0.14 | 0.051 | 0.213 | 128K |
| openai/gpt-oss-120b | $0.04 | $0.17 | 0.056 | 0.258 | 131K |
| qwen/qwen-2.5-7b-instruct | $0.04 | $0.10 | 0.061 | 0.152 | 131K |
| nvidia/nemotron-3-nano-30b-a3b | $0.05 | $0.20 | 0.076 | 0.304 | 262K |
| openai/gpt-5-nano | $0.05 | $0.40 | 0.076 | 0.607 | 400K |
| google/gemma-3-4b-it | $0.05 | $0.10 | 0.076 | 0.152 | 131K |
| google/gemma-3-12b-it | $0.05 | $0.15 | 0.076 | 0.228 | 131K |
| amazon/nova-lite-v1 | $0.06 | $0.24 | 0.091 | 0.364 | 300K |
| z-ai/glm-4.7-flash | $0.06 | $0.40 | 0.091 | 0.607 | 200K |
| tencent/hy3-preview | $0.06 | $0.21 | 0.096 | 0.319 | 262K |
| qwen/qwen3.5-flash | $0.07 | $0.26 | $0.10 | $0.39 | 1M |
| qwen/qwen3-coder-30b-a3b | $0.07 | $0.27 | $0.11 | $0.41 | 160K |
| microsoft/phi-4 | $0.07 | $0.14 | $0.11 | $0.21 | 16K |
| qwen/qwen3-32b | $0.08 | $0.28 | $0.12 | $0.42 | 131K |
| google/gemma-3-27b-it | $0.08 | $0.45 | $0.12 | $0.68 | 131K |
| qwen/qwen3-235b-a22b-2507 | $0.09 | $0.55 | $0.14 | $0.83 | 262K |
| deepseek/deepseek-v4-flash | $0.10 | $0.20 | $0.15 | $0.30 | 1M |
| google/gemma-4-26b-a4b-it | $0.10 | $0.30 | $0.15 | $0.46 | 262K |
| openai/gpt-4.1-nano | $0.10 | $0.40 | $0.15 | $0.61 | 1M |
| meta-llama/llama-4-scout | $0.10 | $0.30 | $0.15 | $0.46 | 10M |
| google/gemma-4-31b-it | $0.12 | $0.37 | $0.18 | $0.56 | 262K |
| qwen/qwen3-coder-next | $0.12 | $0.80 | $0.18 | $1.21 | 262K |
| nousresearch/hermes-4-70b | $0.13 | $0.40 | $0.20 | $0.61 | 131K |
| meta-llama/llama-3.3-70b-instruct | $0.13 | $0.40 | $0.20 | $0.61 | 131K |
| xiaomi/mimo-v2.5 | $0.14 | $0.28 | $0.21 | $0.42 | 1M |
| deepseek/deepseek-v4-pro | $0.43 | $0.87 | $0.65 | $1.32 | 1M |
| deepseek/deepseek-chat | $0.20 | $0.80 | $0.30 | $1.21 | 131K |
| openai/gpt-5.4-nano | $0.20 | $1.25 | $0.30 | $1.90 | 400K |
| qwen/qwen3-coder-flash | $0.20 | $0.97 | $0.30 | $1.47 | 1M |
| meta-llama/llama-4-maverick | $0.20 | $0.80 | $0.30 | $1.21 | 1M |
| openai/gpt-5-mini | $0.25 | $2.00 | $0.38 | $3.04 | 400K |
| qwen/qwen3-coder | $0.30 | $1.00 | $0.46 | $1.52 | 1M |
| google/gemini-2.5-flash | $0.30 | $2.50 | $0.46 | $3.80 | 1M |
| google/gemini-2.5-flash-lite | $0.10 | $0.40 | $0.15 | $0.61 | 1M |

### 3.3 Mid-Range Models ($0.50–$2.00/M input)

| Model | Input $/M | Output $/M | Input Toman/1K | Output Toman/1K | Context |
|---|---|---|---|---|---|
| deepseek/deepseek-r1 | $0.70 | $2.50 | $1.06 | $3.80 | 164K |
| deepseek/deepseek-r1-0528 | $0.50 | $2.15 | $0.76 | $3.27 | 164K |
| nvidia/nemotron-3-ultra-550b-a55b | $0.60 | $3.60 | $0.91 | $5.47 | 1M |
| moonshotai/kimi-k2 | $0.57 | $2.30 | $0.87 | $3.49 | 131K |
| moonshotai/kimi-k2-thinking | $0.60 | $2.50 | $0.91 | $3.80 | 262K |
| moonshotai/kimi-k2.5 | $0.57 | $2.85 | $0.87 | $4.33 | 262K |
| moonshotai/kimi-k2.6 | $0.66 | $3.41 | $1.00 | $5.18 | 262K |
| moonshotai/kimi-k2.7-code | $0.72 | $3.49 | $1.09 | $5.30 | 262K |
| mistralai/mistral-medium-3-5 | $1.50 | $7.50 | $2.28 | $11.39 | 262K |
| openai/gpt-5.6-luna | $1.00 | $6.00 | $1.52 | $9.11 | 1.05M |
| openai/gpt-5.1 | $1.25 | $10.00 | $1.90 | $15.18 | 400K |
| openai/gpt-5 | $1.25 | $10.00 | $1.90 | $15.18 | 400K |
| google/gemini-2.5-pro | $1.25 | $10.00 | $1.90 | $15.18 | 1M |
| openai/gpt-4.1 | $2.00 | $8.00 | $3.04 | $12.14 | 1M |
| anthropic/claude-haiku-4.5 | $1.00 | $5.00 | $1.52 | $7.59 | 200K |
| anthropic/claude-sonnet-4.5 | $3.00 | $15.00 | $4.55 | $22.77 | 1M |
| anthropic/claude-sonnet-5 | $2.00 | $10.00 | $3.04 | $15.18 | 1M |
| openai/gpt-5.6-terra | $2.50 | $15.00 | $3.80 | $22.77 | 1.05M |
| openai/gpt-5.4 | $2.50 | $15.00 | $3.80 | $22.77 | 1.05M |
| openai/gpt-5.3-chat | $1.75 | $14.00 | $2.66 | $21.25 | 128K |

### 3.4 Premium Models ($5+/M input)

| Model | Input $/M | Output $/M | Input Toman/1K | Output Toman/1K | Context |
|---|---|---|---|---|---|
| anthropic/claude-opus-4.7 | $5.00 | $25.00 | $7.59 | $37.95 | 1M |
| anthropic/claude-opus-4.8 | $5.00 | $25.00 | $7.59 | $37.95 | 1M |
| openai/gpt-5.6-sol | $5.00 | $30.00 | $7.59 | $45.54 | 1.05M |
| openai/gpt-5.5 | $5.00 | $30.00 | $7.59 | $45.54 | 1.05M |
| anthropic/claude-fable-5 | $10.00 | $50.00 | $15.18 | $75.89 | 1M |
| openai/gpt-5-pro | $15.00 | $120.00 | $22.77 | $181.88 | 400K |
| anthropic/claude-opus-4.1 | $15.00 | $75.00 | $22.77 | $113.68 | 200K |
| openai/o3-pro | $20.00 | $80.00 | $30.36 | $121.43 | 200K |
| openai/gpt-5.5-pro | $30.00 | $180.00 | $45.54 | $273.22 | 1.05M |
| anthropic/claude-opus-4.7-fast | $30.00 | $150.00 | $45.54 | $227.68 | 1M |
| openai/o1-pro | $150.00 | $600.00 | $227.68 | $910.72 | 200K |

---

## 4. Toman Pricing Conversion Formula

```
Toman_per_1K_tokens = USD_per_token × 1,000 × 126,488 × 1.20
                    = USD_per_token × 151,786,000
```

**Quick reference (with 20% margin):**

| USD/M tokens | Toman/1K tokens |
|---|---|
| $0.00 (free) | 0 Toman |
| $0.10/M | 0.15 Toman |
| $0.50/M | 0.76 Toman |
| $1.00/M | 1.52 Toman |
| $2.00/M | 3.04 Toman |
| $5.00/M | 7.59 Toman |
| $10.00/M | 15.18 Toman |
| $15.00/M | 22.77 Toman |
| $30.00/M | 45.54 Toman |
| $100.00/M | 151.79 Toman |

---

## 5. Recommendations for MultiAI Platform

### Best Value Models (recommended for offering):

| Tier | Model | Use Case | Price (with margin) |
|---|---|---|---|
| **Free** | qwen/qwen3-coder:free | Coding | 0 Toman |
| **Free** | nousresearch/hermes-3-llama-3.1-405b:free | General | 0 Toman |
| **Free** | nvidia/nemotron-3-ultra-550b-a55b:free | Reasoning | 0 Toman |
| **Budget** | openai/gpt-5-nano | Fast general | ~0.08 T/1K in |
| **Budget** | deepseek/deepseek-v4-flash | Fast+smart | ~0.15 T/1K in |
| **Budget** | qwen/qwen3-coder | Coding | ~0.46 T/1K in |
| **Mid** | openai/gpt-5.6-luna | Strong general | ~1.52 T/1K in |
| **Mid** | deepseek/deepseek-r1 | Reasoning | ~1.06 T/1K in |
| **Mid** | google/gemini-2.5-flash | Fast multimodal | ~0.46 T/1K in |
| **Mid** | anthropic/claude-sonnet-5 | High quality | ~3.04 T/1K in |
| **Premium** | anthropic/claude-opus-4.8 | Best quality | ~7.59 T/1K in |
| **Premium** | openai/gpt-5.6-sol | Top OpenAI | ~7.59 T/1K in |

### Models Currently in LiteLLM (mapped to OpenRouter pricing):

| LiteLLM Name | OpenRouter Equivalent | Input $/M | Output $/M | Notes |
|---|---|---|---|---|
| mimo-v2.5 | xiaomi/mimo-v2.5 | $0.14 | $0.28 | Via Bynara |
| mistral-medium-3-5 | mistralai/mistral-medium-3-5 | $1.50 | $7.50 | Via Bynara |
| gpt-5.6-luna | openai/gpt-5.6-luna | $1.00 | $6.00 | Via Bynara |
| kimi-k2.7-code-free | moonshotai/kimi-k2.7-code | $0.72 | $3.49 | Via Bynara (free tier) |
| tencent-hy3 | tencent/hy3-preview | $0.06 | $0.21 | Via Bynara |
| qwen3-coder-free | qwen/qwen3-coder:free | $0 | $0 | Free via OpenRouter |
| nemotron-3-ultra-550b-free | nvidia/nemotron-3-ultra-550b-a55b:free | $0 | $0 | Free via OpenRouter |
| llama-3-3-70b-free | meta-llama/llama-3.3-70b-instruct:free | $0 | $0 | Free via OpenRouter |
| gemma-4-31b-free | google/gemma-4-31b-it:free | $0 | $0 | Free via OpenRouter |
| hermes-3-405b-free | nousresearch/hermes-3-llama-3.1-405b:free | $0 | $0 | Free via OpenRouter |

---

## 6. Key Observations

1. **Free tier is generous**: 21+ free models available, including 405B and 550B parameter models
2. **DeepSeek V4 Flash** offers excellent value at $0.10/M input with 1M context
3. **Qwen3 Coder** is free and has 1M context — excellent for coding tasks
4. **Bynara routing** provides access to mimo-v2.5, gpt-5.6-luna, and other models — pricing may differ from OpenRouter direct
5. **Google Gemma 4 31B** is free with 262K context — good for general tasks
6. **No OPENROUTER_API_KEY** found in .env — all OpenRouter access appears to go through BYNARA_API_KEY
7. **Exchange rate** is volatile — 1 USD = ~126,500 Toman currently; should be refreshed periodically
