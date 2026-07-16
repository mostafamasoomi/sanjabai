# گزارش ممیزی قیمت‌گذاری - Pricing Audit Report
## Multiai Model Catalog — 2026-07-16

---

# خلاصه فارسی (Persian Summary)

## یافته‌های کلیدی
- **قیمت‌گذاری v2 صحیح است**: تمام ۱۰ مدل فعال با فرمول `USD × 180,000 × 1.20` محاسبه شده‌اند و هیچ خطای محاسباتی وجود ندارد.
- **۹۸٪ مدل‌ها غیرفعال هستند**: از ۴۹۴ مدل موجود در کاتالوگ، فقط ۱۰ مدل (۲٪) در دسترس کاربران قرار دارند. ۴۸۴ مدل غیرفعال شده‌اند.
- **نرخ ارز ثابت است**: ۱۸۰,۰۰۰ تومان به ازای هر دلار با ۲۰٪ مارک‌آپ — در تمام سیستم‌ها یکسان.
- **مدل‌های v1 مارک‌آپ ۵۰٪ دارند**: مدل‌های غیرفعال v1 با نرخ ۲۷۰,۰۰۰ (معادل ۵۰٪ مارک‌آپ) قیمت‌گذاری شده‌اند که با استاندارد v2 (۲۰٪) ناسازگار است.
- **OpenRouter و Zenmux کاملاً غیرفعال**: تمام ۳۳۸ مدل OpenRouter و ۱۴۴ مدل Zenmux غیرفعال هستند.
- **مدل‌های رایگان غیرقابل دسترس**: GLM 5.2 Free و Kimi K2.7 Code Free غیرفعال شده‌اند.

## توصیه‌ها
1. افزایش مدل‌های در دسترس از OpenRouter/Zenmux
2. بازنگری در وضعیت مدل‌های رایگان
3. یکسان‌سازی قیمت‌گذاری v1 با استاندارد v2
4. استفاده از وضعیت‌های `degraded` و `maintenance`

---

# 1. Current Pricing State

## 1.1 Exchange Rate & Markup

| Parameter | Value | Source |
|-----------|-------|--------|
| USD→IRT Rate | 180,000 | `exchange_rate_overrides` table (manual-market-rate) |
| Markup | 20% | Hardcoded in `content.py` |
| Effective Rate | 216,000 (= 180,000 × 1.20) | Computed |
| API Endpoint | `/api/exchange-rate` | Returns `usd_to_irt: 180000, markup_pct: 20` |
| Redis Cache TTL | 3600s (1 hour) | `EXCHANGE_RATE_CACHE_TTL` |

**Verification**: The `/api/exchange-rate` endpoint was tested and returns:
```json
{
  "usd_to_irt": 180000,
  "usd_to_irr": 1800000,
  "markup_pct": 20,
  "source": "manual-override"
}
```

## 1.2 Available Models (v2, admin-approved)

All 10 available models use the v2 pricing formula: **IRT = USD × 180,000 × 1.20**

| Model ID | Display Name | USD Input | USD Output | IRT Input | IRT Output | Verified |
|----------|-------------|-----------|------------|-----------|------------|----------|
| agnes-2-0-flash | Agnes 2.0 Flash | $0.028 | $0.111 | 6,048 | 23,976 | ✅ |
| agnes-2-5-flash | Agnes 2.5 Flash | $0.055 | $0.277 | 11,880 | 59,832 | ✅ |
| gemini-3-5-flash | Gemini 3.5 Flash | $1.50 | $9.00 | 324,000 | 1,944,000 | ✅ |
| grok-4-5 | Grok 4.5 | $2.00 | $6.00 | 432,000 | 1,296,000 | ✅ |
| mimo-v2-5 | MiMo V2.5 | $0.14 | $0.28 | 30,240 | 60,480 | ✅ |
| mimo-v2-5-pro | MiMo V2.5 Pro | $0.435 | $0.87 | 93,960 | 187,920 | ✅ |
| mimo-v2-5-pro-ultraspeed | MiMo V2.5 Pro Ultra | $0.13 | $0.26 | 28,080 | 56,160 | ✅ |
| mistral-large | Mistral Large | $2.00 | $6.00 | 432,000 | 1,296,000 | ✅ |
| mistral-medium-3-5 | Mistral Medium 3.5 | $1.50 | $7.50 | 324,000 | 1,620,000 | ✅ |
| tencent-hy3 | Tencent Hy3 | $0.20 | $0.80 | 43,200 | 172,800 | ✅ |

**✅ All v2 pricing is mathematically correct. Zero errors found.**

### Sample Verification:
- Agnes 2.0 Flash: `0.028 × 180,000 × 1.20 = 6,048` ✓
- Grok 4.5: `2.0 × 180,000 × 1.20 = 432,000` ✓
- Gemini 3.5 Flash: `1.5 × 180,000 × 1.20 = 324,000` ✓

---

# 2. Accuracy Issues Found

## 2.1 🔴 CRITICAL: 98% of Models Are Disabled

| Category | Count | % of Total |
|----------|-------|------------|
| Available (v2, admin-approved) | 10 | 2.0% |
| Disabled (v1, provider) | 482 | 97.6% |
| Disabled (v2, admin-approved) | 2 | 0.4% |
| **Total** | **494** | **100%** |

**Breakdown by Provider:**
| Provider | Available | Disabled | Total |
|----------|-----------|----------|-------|
| bynara | 10 | 2 | 12 |
| openrouter | 0 | 338 | 338 |
| zenmux | 0 | 144 | 144 |

**Implication**: Users can only access 10 models from bynara. All 338 OpenRouter models and 144 Zenmux models are completely unavailable. This dramatically limits user choice.

## 2.2 🟡 MEDIUM: v1 Pricing Inconsistency

v1 models (all disabled) use a different effective rate:

| Version | Effective Rate | Effective Markup | Status |
|---------|---------------|------------------|--------|
| v2 | 216,000 (180,000 × 1.20) | **20%** | Available |
| v1 | 270,000 (180,000 × 1.50) | **50%** | Disabled |

If v1 models are ever re-enabled, their pricing would be 25% higher than v2 models for the same USD cost. For example, the same Grok 4.5 model:

| Source | USD Input | IRT Input | Rate |
|--------|-----------|-----------|------|
| bynara (v2, available) | $2.00 | 432,000 | 216,000 |
| zenmux (v1, disabled) | $2.00 | 540,000 | 270,000 |
| openrouter (v1, disabled) | $2.00 | 540,000 | 270,000 |

**All 455 v1 models with non-zero prices consistently use the 270,000 rate.**

## 2.3 🟡 MEDIUM: No Differentiated Cached/Reasoning Token Pricing

All 10 available models have `cached_input_per_million` and `reasoning_per_million` set to `NULL`. This means:
- No discount for cached/prompt-cached inputs
- No differentiated pricing for reasoning tokens (relevant for Grok 4.5, Tencent Hy3, MiMo models which have reasoning capabilities)
- The `compute_charge()` function in `metering.py` supports these fields but they are unused

## 2.4 🟡 MEDIUM: Degraded/Maintenance Status Never Used

The `model_catalog` schema supports 4 availability states:
- `available` — 10 models
- `degraded` — **0 models**
- `maintenance` — **0 models**
- `disabled` — 484 models

The `degraded` and `maintenance` statuses exist but are never used. This means there is no graceful degradation — models are either fully available or completely disabled. There's no way to communicate "this model is slow but working" or "this model is temporarily under maintenance."

## 2.5 🟢 MINOR: Free Models Are Disabled

Two free models from bynara are disabled:
- `glm-5-2-free` (GLM 5.2 Free): USD $0/$0, IRT 0/0, capabilities: chat, reasoning
- `kimi-k2-7-code-free` (Kimi K2.7 Code Free): USD $0/$0, IRT 0/0, capabilities: chat, vision, reasoning, code-generation

These could be useful as free-tier offerings but are currently inaccessible.

---

# 3. Model Availability Issues

## 3.1 Current State

The catalog endpoint `/catalog/models` returns only 10 models (all from bynara, all v2, all admin-approved). The `_load_catalog_rows()` function filters by `WHERE availability = 'available'`.

## 3.2 Missing Provider Coverage

| Provider | Models in DB | Available | Status |
|----------|-------------|-----------|--------|
| bynara | 12 | 10 | ✅ Mostly available |
| openrouter | 338 | 0 | 🔴 Fully disabled |
| zenmux | 144 | 0 | 🔴 Fully disabled |

Notable OpenRouter models that are disabled:
- All OpenAI models (GPT-4, GPT-4o, GPT-3.5, etc.)
- All Anthropic models (Claude Opus, Claude Haiku, etc.)
- All Google models (Gemini variants)
- All Meta Llama models
- All Mistral models
- All Qwen models
- All DeepSeek models

Notable Zenmux models that are disabled:
- DeepSeek models
- xAI Grok models
- StepFun models
- MiniMax models
- Z-AI/GLM models

## 3.3 Capabilities Gap

v2 available models have populated capabilities (chat, vision, reasoning, function_calling, code-generation). v1 disabled models have empty capabilities arrays `[]`. If v1 models are re-enabled, their capabilities metadata would need to be populated.

---

# 4. Billing Pipeline Verification

## 4.1 How Pricing Flows

```
exchange_rate_overrides table (rate: 180,000)
    ↓
_get_exchange_rate() → (180000, 20)
    ↓
_catalog_row_to_item() → API response (includes usd + exchangeRate + markupPct)
    ↓
/chat endpoint → _record_usage()
    ↓
SELECT input_per_million, output_per_million 
FROM model_catalog 
WHERE provider_model_id = :mid AND availability = 'available'
    ↓
cost = int((input_tokens × inp_rate + output_tokens × out_rate + 500,000) // 1,000,000)
    ↓
Ledger entry (amount: -cost)
```

## 4.2 Consistency Check: Catalog vs. Actual Charge

✅ The catalog API and the actual billing code (`chat.py:_record_usage`) both read from the same `model_catalog` table. The pricing shown to users matches what they are charged.

## 4.3 Fallback Behavior

If a model is NOT found in `model_catalog` with `availability = 'available'`:
```python
cost = max(1, total_tokens // 1000)  # ~1 IRT per 1000 tokens
```
This fallback is crude and could lead to undercharging if a model is accidentally used without proper catalog entry.

## 4.4 Billing Activity

- 33 usage events recorded in `usage_events`
- 34 ledger entries in `ledger`
- 14 legacy pricing entries in `pricing` table (superseded by `model_catalog`)

---

# 5. Recommendations

## 5.1 🔴 Immediate Priority

1. **Enable key OpenRouter models**: At minimum, enable the most popular models from OpenRouter (GPT-4o, Claude, Gemini variants, Llama models). This would immediately expand the catalog from 10 to 50+ useful models.

2. **Recalculate v1 pricing**: Before enabling any v1 models, recalculate their IRT prices using the v2 standard formula (USD × 180,000 × 1.20). The current v1 models use a 50% markup which is inconsistent.

3. **Enable free models**: Re-enable `glm-5-2-free` and `kimi-k2-7-code-free` as free-tier offerings. If they are broken, use `degraded` status instead of `disabled`.

## 5.2 🟡 Short-term Improvements

4. **Add cached input pricing**: For models that support prompt caching, add `cached_input_per_million` rates (typically 50% of input rate).

5. **Add reasoning token pricing**: For reasoning models (Grok 4.5, Tencent Hy3, MiMo), differentiate reasoning token pricing.

6. **Use degraded/maintenance statuses**: Implement a model health check that sets models to `degraded` when they're slow or experiencing issues, rather than fully disabling them.

7. **Capabilities audit**: Populate capabilities for all v1 models before enabling them.

## 5.3 🟢 Long-term Strategy

8. **Automated pricing sync**: Build a pipeline that fetches provider pricing (USD) and automatically recomputes IRT prices using the current exchange rate and markup.

9. **Multi-currency support**: Consider storing prices in USD as the source of truth and computing IRT dynamically, rather than storing both.

10. **Pricing version history**: Add a `pricing_history` table to track changes over time for audit trails.

11. **Model health monitoring**: Implement automated health checks that update availability flags based on actual model responsiveness.

---

# 6. Technical Details

## 6.1 Database Schema (model_catalog)

Key columns verified:
- `usd_input_per_million`, `usd_output_per_million`: Present and populated for all models
- `input_per_million`, `output_per_million`: IRT prices (post-conversion)
- `price_version`: v1 (provider) or v2 (admin-approved)
- `provenance`: provider, admin-approved, or fallback
- `availability`: available, degraded, maintenance, or disabled

## 6.2 Pricing Formula

**v2 (correct):**
```
IRT = USD × exchange_rate × (1 + markup_pct/100)
IRT = USD × 180,000 × 1.20
IRT = USD × 216,000
```

**v1 (legacy, inconsistent):**
```
IRT = USD × 270,000  (effectively 50% markup)
```

## 6.3 Charge Computation (metering.py)

```python
def _part(tokens: int, per_million: int) -> int:
    return (tokens * per_million + 500_000) // 1_000_000

def compute_charge(price, *, input_tokens, output_tokens, ...):
    total = _part(input_tokens, price["input_per_million"]) 
          + _part(output_tokens, price["output_per_million"]) 
          + ...
    return Money(total)  # integer tomans
```

✅ Uses integer arithmetic (no floating point), with half-up rounding.

---

# 7. Audit Conclusion

| Area | Status | Issues |
|------|--------|--------|
| v2 Pricing Accuracy | ✅ PASS | All 10 models perfectly correct |
| Exchange Rate | ✅ PASS | 180,000 IRT/USD, consistent everywhere |
| Markup Application | ✅ PASS | 20%, consistently applied to v2 models |
| Catalog↔Billing Consistency | ✅ PASS | Same source (model_catalog) for both |
| Model Availability | 🔴 FAIL | 98% of models disabled |
| v1 Pricing Consistency | 🟡 WARN | 50% markup vs 20% standard |
| Status Granularity | 🟡 WARN | degraded/maintenance never used |
| Token Pricing Detail | 🟡 WARN | No cached/reasoning token differentiation |
| Overall | 🟡 CONDITIONAL PASS | Pricing correct but availability severely limited |

---

*Report generated: 2026-07-16T09:07:00+00:00*
*Auditor: S4 — Senior Pricing & Billing Engineer*
*Data sources: model_catalog table, exchange_rate_overrides table, /catalog/models API, /catalog/pricing API, /api/exchange-rate API, pricing.py, billing.py, metering.py, chat.py, content.py*