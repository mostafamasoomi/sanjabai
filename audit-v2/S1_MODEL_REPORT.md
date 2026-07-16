# S1 Model Reliability & Routing Report — Multiai (VERIFIED RE-RUN)

**Date:** 2026-07-16 (full live verification)
**Tester:** S1 Senior Model Engineer
**Project:** /root/multiai
**Config:** backend/litellm_config.yaml — 354 models (12 Bynara + 342 OpenRouter)
**Auth:** demo@multiai.com / Demo@2026 Bearer token
**Endpoint:** POST /v1/chat/completions (FastAPI to LiteLLM:4000 to Bynara/OpenRouter)

## 1. HEADLINE (verified)
- Total tested: 354 | WORKING: 3 | BROKEN: 351
- HTTP dist: {403:345, 400:3, 429:2, 404:1, 200:3}
- Working (all Bynara): tencent-hy3, mistral-large, mistral-medium-3-5

Corrections vs stale prior report:
- kimi-k2.7-code-free now 429 (free quota) — NOT reliably working (prior said 4 working).
- OPENROUTER_API_KEY now 401 "User not found" (invalid) + IP WAF block (prior said 403 only).

## 2. Bynara (12): 3 work / 9 broken
- 200: tencent-hy3, mistral-large, mistral-medium-3-5
- 429: kimi-k2.7-code-free (free daily quota)
- 403: mimo-v2.5, mimo-v2.5-pro, mimo-v2.5-pro-ultraspeed (plan excludes MiMo family)
- 400: agnes-2.0-flash, gemini-3.5-flash (model rejected payload), grok-4.5 (not available)
- 404: glm-5.2-free (model does not exist)

## 3. OpenRouter (342): 0 work
All 403 via LiteLLM proxy (Access denied by security policy). Direct host test: 401 "User not found" on /api/v1/key. Key invalid AND egress IP WAF-blocked.

## 4. API key validity (verified)
- BYNARA_API_KEY: VALID (len 50). Works for 3 models; plan excludes MiMo.
- OPENROUTER_API_KEY: INVALID (401). Plus IR-IP WAF block. Must rotate + fix egress.

## 5. Catalog cross-reference
- /catalog/models and /v1/models return 4 "available": kimi-k2-7-code-free, mistral-large, mistral-medium-3-5, tencent-hy3.
- INCONSISTENCY: kimi marked available but 429 — should be degraded/disabled.
- Legacy ~144 zenmux rows (disabled) + bynara2 stale pricing refs (see S4).

## 6. Smart routing FIXED and VERIFIED
Deployed backend/chat.py (around lines 596-607):
```
_RELIABLE_MODELS = ('tencent-hy3','mistral-large','mistral-medium-3-5')
_FREE/_CODING/_REASONING/_CREATIVE all use the 3 reliable bynara models.
_DEFAULT_MODEL=tencent-hy3, _ADVANCED_MODEL=mistral-large, _PREMIUM_MODEL=mistral-medium-3-5
```
Added _select_smart_model_safe() guard: falls back to _DEFAULT_MODEL if pick not in _RELIABLE_MODELS. Both call sites use it.
Rebuilt multiai_api image (--no-cache) and recreated container. Verified: grep _select_smart_model_safe = 2.

Live smart-chat verification (all HTTP 200):
- greeting -> tencent-hy3
- code -> tencent-hy3
- reasoning -> mistral-large
- creative -> tencent-hy3
- complex -> mistral-large
- medium -> tencent-hy3
No routing to kimi/mimo/OpenRouter.

## 7. MVP list
Tier 1 SHIP NOW (3): tencent-hy3, mistral-large, mistral-medium-3-5.
Tier 2 AFTER OpenRouter fix (15-20): qwen/qwen3-coder:free, hermes-3-405b:free, gemma-4-31b-it:free, gpt-oss-20b:free, deepseek-v4-flash, gemini-2.5-flash, claude-sonnet-4.5, gpt-5-mini, x-ai/grok-4.5, xiaomi/mimo-v2.5 (openrouter).
Bynara-only: upgrade plan for MiMo; fix agnes/gemini 400; remove glm-5.2-free(404)/grok-4.5(400).

## 8. Action items
P0: [x] routing fixed+verified  [ ] rotate OPENROUTER_API_KEY + non-IR egress  [ ] catalog: kimi->degraded, keep 3 available
P1: Bynara MiMo plan; agnes/gemini 400; remove glm-5.2-free/grok-4.5; prune zenmux; fix bynara2 pricing
P2: LiteLLM health probe to auto-mark availability; num_retries tuning

## 9. Evidence
audit-v2/test_all_results.json, test_all.log, verify_routing.py, keycheck.py, checks.py

## 10. Conclusion
3/354 (0.85%) work, all Bynara. OpenRouter dead (invalid key + IP block). Routing fixed+verified (3 reliable models + guard) so chat works for all categories. MVP of 3 shipable; 15-20 needs OpenRouter key+egress fix (P0) + Bynara plan/payload (P1).
