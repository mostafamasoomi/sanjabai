# Multiai Models Setup Report

**Date:** 2026-07-15

## Summary

Successfully configured **31 AI models** across 2 providers in the Multiai platform.

## Models Configured

### Bynara Models (11) — All Free via Bynara

| Model ID | Display Name | Context | Features |
|----------|-------------|---------|----------|
| agnes-2.0-flash | Agnes 2.0 Flash | 512K | Vision |
| agnes-2.5-flash | Agnes 2.5 Flash | 512K | Vision |
| gemini-3.5-flash | Gemini 3.5 Flash | 1M | Vision |
| glm-5.2-free | GLM 5.2 Free | 512K | Reasoning |
| kimi-k2.7-code-free | Kimi K2.7 Code Free | 262K | Vision, Reasoning, Code |
| mimo-v2.5 | MiMo V2.5 | 1M | Vision, Reasoning |
| mimo-v2.5-pro | MiMo V2.5 Pro | 1M | Reasoning |
| mimo-v2.5-pro-ultraspeed | MiMo V2.5 Pro Ultraspeed | 1M | Reasoning |
| mistral-large | Mistral Large | 252K | Function Calling |
| mistral-medium-3-5 | Mistral Medium 3.5 | 256K | Vision, Reasoning |
| tencent-hy3 | Tencent Hy3 | 1M | Reasoning |

### OpenRouter Free Models (20) — All Free

| Model ID | Display Name | Context | Features |
|----------|-------------|---------|----------|
| cohere/north-mini-code:free | Cohere North Mini Code | 256K | Code |
| cognitivecomputations/dolphin-mistral-24b-venice-edition:free | Venice Uncensored 24B | 32K | Chat |
| google/gemma-4-26b-a4b-it:free | Gemma 4 26B A4B | 262K | Vision |
| google/gemma-4-31b-it:free | Gemma 4 31B | 262K | Vision |
| meta-llama/llama-3.2-3b-instruct:free | Llama 3.2 3B | 131K | Chat |
| meta-llama/llama-3.3-70b-instruct:free | Llama 3.3 70B | 131K | Chat |
| nousresearch/hermes-3-llama-3.1-405b:free | Hermes 3 405B | 131K | Chat |
| nvidia/nemotron-3-nano-30b-a3b:free | Nemotron 3 Nano 30B | 256K | Reasoning |
| nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free | Nemotron 3 Nano Omni | 256K | Multimodal, Reasoning |
| nvidia/nemotron-3-super-120b-a12b:free | Nemotron 3 Super 120B | 1M | Reasoning |
| nvidia/nemotron-3-ultra-550b-a55b:free | Nemotron 3 Ultra 550B | 1M | Reasoning |
| nvidia/nemotron-3.5-content-safety:free | Nemotron 3.5 Content Safety | 128K | Moderation |
| nvidia/nemotron-nano-9b-v2:free | Nemotron Nano 9B V2 | 128K | Reasoning |
| nvidia/nemotron-nano-12b-v2-vl:free | Nemotron Nano 12B VL | 128K | Multimodal, Reasoning |
| openai/gpt-oss-20b:free | GPT-OSS 20B | 131K | Reasoning |
| poolside/laguna-m.1:free | Poolside Laguna M.1 | 262K | Code, Reasoning |
| poolside/laguna-xs-2.1:free | Poolside Laguna XS 2.1 | 262K | Code, Reasoning |
| qwen/qwen3-coder:free | Qwen3 Coder 480B | 1M | Code |
| qwen/qwen3-next-80b-a3b-instruct:free | Qwen3 Next 80B | 262K | Chat |
| tencent/hy3:free | Tencent Hy3 (Free) | 262K | Reasoning |

## Pricing

All 31 models are set to **pricing = 0** (free):
- Bynara models: Free through the Bynara proxy
- OpenRouter models: Free tier (`:free` suffix)

## Files Modified

1. **`/root/multiai/backend/litellm_config.yaml`** — Full rewrite with all 31 models
2. **`/root/multiai/docker-compose.multiai.yml`** — Added `LITELLM_HOST`, fixed `NO_PROXY` (added `localhost,127.0.0.1,multiai_litellm`), improved litellm health check

## Database Changes

- Cleared old `model_catalog` entries (13 rows)
- Inserted 31 new entries (11 Bynara + 20 OpenRouter)

## Issues Fixed

1. **Missing `LITELLM_HOST` env var** — API container couldn't reach litellm (defaulted to `127.0.0.1:4000` instead of `multiai_litellm:4000`)
2. **Proxy intercepting localhost** — `HTTP_PROXY` was intercepting health checks and internal container communication; added `localhost,127.0.0.1` to `NO_PROXY`
3. **Missing `wget` for health check** — LiteLLM container doesn't have `wget`; switched to Python-based health check
4. **Stale Bynara models** — Removed `gpt-5.6-luna` (no longer available), added new models `agnes-2.0-flash`, `agnes-2.5-flash`, `gemini-3.5-flash`, `glm-5.2-free`, `mistral-large`
5. **Stale OpenRouter models** — Removed expired/removed free models, added 13 new free models

## Verification

- ✅ `GET /v1/models` returns 31 models
- ✅ `POST /v1/chat/completions` with `mimo-v2.5` returns valid response
- ✅ Chat test: "salam" → "Wa alaikum assalam! 👋 How can I help you today?"
