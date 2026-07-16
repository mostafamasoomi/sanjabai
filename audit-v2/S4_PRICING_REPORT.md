# S4: Model Catalog & Pricing Integrity Report

## Summary

| Metric | Value |
|--------|-------|
| Total models | 494 |
| Available (v2) | 10 |
| Disabled (v1) | 482 |
| Disabled (v2 free) | 2 |
| Zero-price models | 27 (all disabled) |
| Empty capabilities | 482 (all v1 disabled) |
| Exchange rate | 180,000 IRT/USD |
| v2 markup | 20% (implied rate 216,000) |
| v1 markup | 50% (implied rate 270,000) |

---

## 1. v2 Active Models — Pricing Verification

All 10 available models use: **IRT = USD × 216,000** (= 180,000 × 1.20 markup).

| Model | USD Input | USD Output | IRT Input | IRT Output | Markup |
|-------|-----------|------------|-----------|------------|--------|
| agnes-2-0-flash | 0.028 | 0.111 | 6,048 | 23,976 | 1.20x ✓ |
| agnes-2-5-flash | 0.055 | 0.277 | 11,880 | 59,832 | 1.20x ✓ |
| gemini-3-5-flash | 1.50 | 9.00 | 324,000 | 1,944,000 | 1.20x ✓ |
| grok-4-5 | 2.00 | 6.00 | 432,000 | 1,296,000 | 1.20x ✓ |
| mimo-v2-5 | 0.14 | 0.28 | 30,240 | 60,480 | 1.20x ✓ |
| mimo-v2-5-pro | 0.435 | 0.87 | 93,960 | 187,920 | 1.20x ✓ |
| mimo-v2-5-pro-ultraspeed | 0.13 | 0.26 | 28,080 | 56,160 | 1.20x ✓ |
| mistral-large | 2.00 | 6.00 | 432,000 | 1,296,000 | 1.20x ✓ |
| mistral-medium-3-5 | 1.50 | 7.50 | 324,000 | 1,620,000 | 1.20x ✓ |
| tencent-hy3 | 0.20 | 0.80 | 43,200 | 172,800 | 1.20x ✓ |

**Verdict: All v2 pricing consistent. Formula verified.**

---

## 2. v1 Disabled Models — Markup Inconsistency

- **482 v1 models** use 50% markup: IRT = USD × 270,000 (= 180,000 × 1.50)
- **10 v2 models** use 20% markup: IRT = USD × 216,000 (= 180,000 × 1.20)

The v1 models were priced with a higher markup. Since they're all `availability=disabled`, this is dormant debt — no active billing impact. If any v1 model is re-enabled, it will charge at the old 50% rate unless pricing is refreshed.

**Impact: LOW (all disabled). Risk: MEDIUM if re-enabled without price refresh.**

---

## 3. Free Models — All Disabled

27 models have zero price. All are `availability=disabled`:
- 2 v2 free models: `glm-5-2-free`, `kimi-k2-7-code-free`
- 25 v1 free models (OpenRouter `:free` tier)

No free models are currently available to users. The `kimi-k2.7-code-free` appears in ledger entries (user 35 charged -1 Tomans), suggesting it was briefly active before being disabled.

**Verdict: No free models available. Intentional or oversight — needs product decision.**

---

## 4. Capabilities Field

- **v2 available (10)**: Capabilities populated correctly (`chat`, `vision`, `reasoning`, `function_calling`)
- **v1 disabled (482)**: All have `capabilities = []`

Empty capabilities on disabled models is expected — they're not served. The `schemas/catalog.py` Pydantic model (`ModelCatalogItem`) requires capabilities as `list[str]` with default `[]`, so validation passes.

**Verdict: No issue. v1 caps are cosmetic since all disabled.**

---

## 5. Billing Pipeline Trace

```
USD price → exchange_rate_overrides (180,000 IRT/USD)
         → content.py refresh_pricing() applies markup: rate × (1 + markup_pct/100)
         → model_catalog.input_per_million (integer IRT)

Request flow:
  chat.py → BillingService.reserve(Money)  [hold estimated cost]
          → upstream call
          → metering.compute_charge(price_dict, tokens)  [exact integer math]
          → BillingService.settle(reservation_id, Money)
          → ledger.append (amount, balance_after, reason)
          → usage_events.append (token breakdown, charged_amount)
```

Key components:
- **money.py**: Immutable `Money(irt: int)` — no float, no currency conversion. Clean.
- **billing.py**: `SqlBillingRepo` with reserve/settle/release + idempotency keys. `credit_wallet` for payment callbacks.
- **metering.py**: `compute_charge()` uses integer half-up rounding: `(tokens * per_million + 500_000) // 1_000_000`. Correct.
- **exchange_rate_overrides**: Single active row, `rate=180000`, source `manual-market-rate`.

**Verdict: Pipeline is sound. Integer-only money math. Idempotent. No float drift risk.**

---

## 6. Findings & Recommendations

### Critical
- None.

### Medium
1. **v1 markup drift**: 482 disabled models at 50% markup vs 20% on v2. If re-enabled, `refresh_pricing()` will fix them (it recalculates from current exchange rate + markup), but only for models in the `OPENROUTER_PRICES` dict. Models outside that dict retain stale prices.

### Low
2. **Free models disabled**: 27 zero-price models all disabled. Product decision needed — enable some as freemium tier or clean up.
3. **Hardcoded exchange rate fallback**: `_get_exchange_rate()` defaults to `126_488` if cache + DB both fail. This is stale (current rate is 180,000). Low risk since DB override exists.
4. **`OPENROUTER_PRICES` dict is source of truth**: 12 models hardcoded. Any new model needs a code change + deploy. Consider DB-driven pricing.

---

## 7. Data Quality

| Check | Status |
|-------|--------|
| All v2 IRT = USD × 216,000 | ✅ PASS |
| All v1 IRT = USD × 270,000 | ✅ PASS (consistent within v1) |
| No negative prices | ✅ PASS |
| No NULL prices on available models | ✅ PASS |
| Exchange rate override active | ✅ PASS (180,000) |
| Billing uses integer Tomans | ✅ PASS |
| Idempotent settlement | ✅ PASS |
| Ledger entries present | ✅ PASS (78 entries) |
