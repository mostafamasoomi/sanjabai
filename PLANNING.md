# Multiai Pricing System — Implementation Plan

> **Version:** 1.0 · **Date:** 2026-07-13 · **Status:** Draft
> **Author:** Hermes Agent (pricing subagent)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Existing Architecture Summary](#2-existing-architecture-summary)
3. [Database Schema Changes](#3-database-schema-changes)
4. [Backend API Endpoints](#4-backend-api-endpoints)
5. [Billing Flow — Subscription vs PAYG](#5-billing-flow--subscription-vs-payg)
6. [Frontend Pages](#6-frontend-pages)
7. [Edge Cases & Failure Modes](#7-edge-cases--failure-modes)
8. [Migration Strategy](#8-migration-strategy)
9. [Testing Plan](#9-testing-plan)
10. [Implementation Phases](#10-implementation-phases)

---

## 1. Executive Summary

Multiai currently has a simple wallet-based pay-as-you-go model: users top up their wallet via ZarinPal, and token usage is deducted from the ledger balance. There is a `subscriptions` table with plan values `free`/`basic`/`pro`, but it is not wired into the billing pipeline.

This plan introduces a **hybrid billing model**:

| Mode | Description |
|------|-------------|
| **Free Tier** | Default for all new users. 100K tokens/day, limited to small models. |
| **Subscription Plans** | Monthly plans (Basic ₫149K, Pro ₫499K, Unlimited ₫999K) with included token quotas. |
| **Credit Packages** | One-time purchases with bonus credits (50K, 100K+20%, 250K+40%, 500K+50%). |
| **PAYG (Pay-As-You-Go)** | Per-request wallet deduction at published per-million-token rates. |

Users can have **both** a subscription **and** PAYG enabled. Billing priority: subscription quota first → PAYG wallet deduction second.

---

## 2. Existing Architecture Summary

### 2.1 Key Tables (as of baseline + migrations 0001–0004)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `users` | User accounts | `id`, `email`, `phone`, `telegram_id`, `referral_code` |
| `subscriptions` | Plan records | `id`, `user_id`, `plan` (free/basic/pro), `starts_at`, `ends_at` |
| `wallet` | Authoritative balance | `user_id` (PK), `balance`, `reserved` |
| `ledger` | Immutable financial log | `user_id`, `amount`, `balance_after`, `reason`, `idempotency_key` |
| `payments` | ZarinPal payment records | `user_id`, `amount`, `authority`, `ref_id`, `status`, `idempotency_key` |
| `payment_orders` | Legacy payment orders | `id`, `user_id`, `amount_irr`, `status`, `authority` |
| `wallet_reservations` | Pre-call holds | `reservation_id`, `user_id`, `amount`, `status` |
| `usage_events` | Immutable usage records | `request_id`, `user_id`, `model`, `input_tokens`, `output_tokens`, `charged_amount` |
| `model_catalog` | Approved model list | `provider_model_id`, `input_per_million`, `output_per_million`, `availability` |
| `pricing` | Versioned pricing | `model`, `input_per_million`, `output_per_million`, `price_version` |
| `quota` | Daily token limits | `user_id`, `daily_limit`, `used_today`, `reset_at` |

### 2.2 Key Backend Services

| Module | Role |
|--------|------|
| `services/billing.py` | `SqlBillingRepo`, `BillingService` (reserve/settle/release), `credit_wallet` |
| `services/money.py` | `Money` value object (integer Tomans, no floats) |
| `services/metering.py` | `compute_charge`, `record_usage` — per-million token pricing |
| `services/reservation.py` | Pure reservation/settlement primitives |
| `payment.py` | ZarinPal integration (`create_payment`, `verify_payment`, `handle_payment_callback`) |
| `app.py` | All FastAPI routes, ORM models, `_track_usage`, `_bill_stream_usage` |

### 2.3 Existing Billing Pipeline

```
User sends chat request
  → _check_quota_pre(uid)         # daily token limit + wallet balance check
  → call LiteLLM upstream
  → _track_usage / _bill_stream_usage
      → look up model_catalog prices
      → cost = (input_tokens * input_rate + output_tokens * output_rate) rounded
      → deduct from ledger if balance >= cost
      → record usage_events row
```

**Gap:** No subscription quota consumption, no PAYG toggle, no credit packages.

---

## 3. Database Schema Changes

### 3.1 New Migration File: `0005_pricing_system.sql`

#### 3.1.1 Modify `subscriptions` Table

The existing `subscriptions` table has `plan IN ('free','basic','pro')` and `ends_at`. We need to extend it:

```sql
-- Extend plan CHECK to include 'unlimited' and remove the old constraint
ALTER TABLE subscriptions DROP CONSTRAINT IF EXISTS subscriptions_plan_check;

-- Add new columns for subscription lifecycle
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'expired', 'cancelled', 'paused', 'grace_period'));
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS monthly_token_quota BIGINT NOT NULL DEFAULT 0;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS tokens_used_this_period BIGINT NOT NULL DEFAULT 0;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS grace_ends_at TIMESTAMPTZ;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS payment_order_id TEXT;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS price_paid BIGINT NOT NULL DEFAULT 0;  -- Tomans
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Add composite index for fast "current active subscription" lookups
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_active
    ON subscriptions(user_id, status) WHERE status = 'active';
```

#### 3.1.2 New Table: `plans` — Plan Definitions

```sql
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,                          -- 'free', 'basic', 'pro', 'unlimited'
    name_fa TEXT NOT NULL,                        -- 'رایگان', 'پایه', 'حرفه‌ای', 'نامحدود'
    name_en TEXT NOT NULL,                        -- 'Free', 'Basic', 'Pro', 'Unlimited'
    price_monthly BIGINT NOT NULL DEFAULT 0,      -- Tomans (0 for free)
    monthly_token_quota BIGINT NOT NULL DEFAULT 0, -- 0 = unlimited within plan
    daily_token_limit BIGINT NOT NULL DEFAULT 0,   -- 0 = use plan default
    max_context_tokens INT,                        -- NULL = no special limit
    models_allowed TEXT[],                         -- NULL = all models; else list of model IDs
    priority_queue BOOLEAN NOT NULL DEFAULT FALSE, -- priority in inference queue
    features JSONB NOT NULL DEFAULT '[]'::jsonb,   -- list of feature strings for UI
    active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed plan data
INSERT INTO plans (id, name_fa, name_en, price_monthly, monthly_token_quota, daily_token_limit, models_allowed, priority_queue, features, sort_order) VALUES
('free',      'رایگان',    'Free',      0,       3000000,    100000,   NULL, FALSE,
    '["دسترسی به مدل‌های کوچک","روزانه ۱۰۰ هزار توکن"]'::jsonb, 0),
('basic',     'پایه',      'Basic',     149000,  5000000,    500000,   NULL, FALSE,
    '["دسترسی به مدل‌های پیشرفته","ماهانه ۵ میلیون توکن","پشتیبانی ایمیلی"]'::jsonb, 1),
('pro',       'حرفه‌ای',   'Pro',       499000,  20000000,   2000000,  NULL, TRUE,
    '["اولویت در صف","ماهانه ۲۰ میلیون توکن","پشتیبانی اختصاصی","دسترسی به تمام مدل‌ها"]'::jsonb, 2),
('unlimited', 'نامحدود',   'Unlimited', 999000,  0,          0,        NULL, TRUE,
    '["توکن نامحدود","اولویت بالا","پشتیبانی اختصاصی ۲۴/۷","دسترسی زودهنگام به مدل‌های جدید"]'::jsonb, 3)
ON CONFLICT (id) DO UPDATE SET
    name_fa = EXCLUDED.name_fa,
    name_en = EXCLUDED.name_en,
    price_monthly = EXCLUDED.price_monthly,
    monthly_token_quota = EXCLUDED.monthly_token_quota,
    daily_token_limit = EXCLUDED.daily_token_limit,
    features = EXCLUDED.features,
    sort_order = EXCLUDED.sort_order,
    updated_at = now();
```

#### 3.1.3 New Table: `credit_packages` — One-Time Credit Purchases

```sql
CREATE TABLE IF NOT EXISTS credit_packages (
    id TEXT PRIMARY KEY,                            -- 'starter', 'popular', 'mega', 'whale'
    name_fa TEXT NOT NULL,                          -- 'بسته شروع', 'بسته محبوب', ...
    name_en TEXT NOT NULL,
    base_amount BIGINT NOT NULL,                    -- Tomans the user pays
    bonus_percent INT NOT NULL DEFAULT 0,           -- e.g. 20 means +20% bonus
    total_credits BIGINT NOT NULL,                  -- base_amount + bonus (computed, stored for clarity)
    active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed credit packages
INSERT INTO credit_packages (id, name_fa, name_en, base_amount, bonus_percent, total_credits, sort_order) VALUES
('starter', '₨۵۰ هزار',    '₨50K Starter',   50000,   0,  50000,   0),
('popular', '₨۱۰۰ هزار',   '₨100K Popular',  100000,  20, 120000,  1),
('mega',    '₨۲۵۰ هزار',   '₨250K Mega',     250000,  40, 350000,  2),
('whale',   '₨۵۰۰ هزار',   '₨500K Whale',    500000,  50, 750000   3)
ON CONFLICT (id) DO UPDATE SET
    base_amount = EXCLUDED.base_amount,
    bonus_percent = EXCLUDED.bonus_percent,
    total_credits = EXCLUDED.total_credits,
    updated_at = now();
```

#### 3.1.4 New Table: `user_billing_settings` — Per-User PAYG Toggle

```sql
CREATE TABLE IF NOT EXISTS user_billing_settings (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    payg_enabled BOOLEAN NOT NULL DEFAULT TRUE,     -- PAYG toggle (on by default)
    payg_hard_limit BIGINT DEFAULT NULL,             -- optional spending cap per month (Tomans)
    notify_on_usage_pct INT NOT NULL DEFAULT 80,     -- notify when X% of quota/limit used
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### 3.1.5 New Table: `subscription_quota_log` — Monthly Quota Tracking

```sql
CREATE TABLE IF NOT EXISTS subscription_quota_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id BIGINT NOT NULL REFERENCES subscriptions(id),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    token_quota BIGINT NOT NULL,
    tokens_used BIGINT NOT NULL DEFAULT 0,
    overage_tokens BIGINT NOT NULL DEFAULT 0,   -- tokens used beyond quota (billed via PAYG)
    overage_charged BIGINT NOT NULL DEFAULT 0,  -- Tomans charged for overage
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sub_quota_log_user ON subscription_quota_log(user_id, period_start);
```

#### 3.1.6 Extend `usage_events` Table

```sql
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS billing_source TEXT DEFAULT 'wallet'
    CHECK (billing_source IN ('subscription', 'wallet', 'free_tier'));
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS subscription_id BIGINT;
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS credits_charged BIGINT DEFAULT 0;  -- from credit package
ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS payg_charged BIGINT DEFAULT 0;    -- from wallet/PAYG
```

#### 3.1.7 Extend `payments` Table

```sql
ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_type TEXT DEFAULT 'wallet_topup'
    CHECK (payment_type IN ('wallet_topup', 'subscription', 'credit_package'));
ALTER TABLE payments ADD COLUMN IF NOT EXISTS reference_id TEXT;  -- subscription_id or package_id
```

#### 3.1.8 Full ERD (ASCII)

```
┌──────────┐     ┌─────────────────────┐     ┌───────────────┐
│  users   │────▶│ user_billing_settings│     │    plans      │
│          │     │  payg_enabled        │     │  id (PK)      │
│  id (PK) │     │  payg_hard_limit     │     │  price_monthly│
└────┬─────┘     └─────────────────────┘     │  monthly_quota│
     │                                        │  models_allow │
     ├────────────▶┌──────────────────┐       └───────────────┘
     │             │  subscriptions   │◀──────────┘
     │             │  user_id (FK)    │
     │             │  plan            │
     │             │  status          │     ┌──────────────────┐
     │             │  monthly_token_  │     │ credit_packages  │
     │             │    quota         │     │  id (PK)         │
     │             │  tokens_used_    │     │  base_amount     │
     │             │    this_period   │     │  bonus_percent   │
     │             │  auto_renew      │     │  total_credits   │
     │             │  price_paid      │     └──────────────────┘
     │             └──────────────────┘
     │
     ├────────────▶┌──────────────────┐
     │             │     wallet       │
     │             │  user_id (PK)    │
     │             │  balance         │
     │             │  reserved        │
     │             └──────────────────┘
     │
     ├────────────▶┌──────────────────┐
     │             │     ledger       │
     │             │  user_id         │
     │             │  amount          │
     │             │  balance_after   │
     │             │  reason          │
     │             │  idempotency_key │
     │             └──────────────────┘
     │
     ├────────────▶┌──────────────────┐
     │             │   usage_events   │
     │             │  billing_source  │  ◀── NEW: 'subscription'|'wallet'|'free_tier'
     │             │  subscription_id │  ◀── NEW
     │             │  credits_charged │  ◀── NEW
     │             │  payg_charged    │  ◀── NEW
     │             └──────────────────┘
     │
     └────────────▶┌──────────────────┐
                   │    payments      │
                   │  payment_type    │  ◀── NEW: 'wallet_topup'|'subscription'|'credit_package'
                   │  reference_id    │  ◀── NEW
                   └──────────────────┘
```

---

## 4. Backend API Endpoints

### 4.1 Plan Catalog (Public)

#### `GET /plans`
Returns all active plans with features for the pricing page.

```json
// Response 200
{
  "plans": [
    {
      "id": "free",
      "name_fa": "رایگان",
      "name_en": "Free",
      "price_monthly": 0,
      "monthly_token_quota": 3000000,
      "daily_token_limit": 100000,
      "models_allowed": null,
      "priority_queue": false,
      "features": ["دسترسی به مدل‌های کوچک", "روزانه ۱۰۰ هزار توکن"],
      "sort_order": 0
    },
    {
      "id": "basic",
      "name_fa": "پایه",
      "name_en": "Basic",
      "price_monthly": 149000,
      "monthly_token_quota": 5000000,
      "daily_token_limit": 500000,
      "models_allowed": null,
      "priority_queue": false,
      "features": ["..."],
      "sort_order": 1
    }
    // ... pro, unlimited
  ],
  "credit_packages": [
    {
      "id": "starter",
      "name_fa": "₨۵۰ هزار",
      "base_amount": 50000,
      "bonus_percent": 0,
      "total_credits": 50000,
      "sort_order": 0
    },
    {
      "id": "popular",
      "name_fa": "₨۱۰۰ هزار",
      "base_amount": 100000,
      "bonus_percent": 20,
      "total_credits": 120000,
      "sort_order": 1
    }
    // ... mega, whale
  ]
}
```

**Implementation location:** New route in `app.py` (or extract to `routes/plans.py`)

---

### 4.2 Subscription Management (Auth Required)

#### `GET /me/subscription`
Get current user's active subscription and billing status.

```json
// Response 200
{
  "subscription": {
    "id": 42,
    "plan_id": "pro",
    "plan_name_fa": "حرفه‌ای",
    "status": "active",
    "starts_at": "2026-07-01T00:00:00Z",
    "ends_at": "2026-08-01T00:00:00Z",
    "monthly_token_quota": 20000000,
    "tokens_used_this_period": 8500000,
    "tokens_remaining": 11500000,
    "auto_renew": true,
    "price_paid": 499000,
    "days_remaining": 19
  },
  "payg": {
    "enabled": true,
    "wallet_balance": 250000,
    "hard_limit": null
  },
  "usage_this_period": {
    "subscription_tokens": 8500000,
    "payg_tokens": 1200000,
    "payg_charged": 45600,
    "free_tier_tokens": 0
  }
}
```

#### `POST /subscription/checkout`
Start a subscription purchase flow. Creates a ZarinPal payment order of type `subscription`.

```json
// Request
{
  "plan_id": "pro"   // 'basic' | 'pro' | 'unlimited'
}

// Response 200
{
  "payment_url": "https://www.zarinpal.com/pg/StartPay/xxxxx",
  "authority": "xxxxx",
  "amount": 499000,
  "plan_id": "pro"
}

// Response 409 — already has active subscription
{
  "detail": "you already have an active 'basic' subscription. Upgrade instead?",
  "current_plan": "basic",
  "upgrade_url": "/subscription/upgrade"
}
```

**Flow:**
1. Validate user doesn't already have active subscription for same/higher plan.
2. Create `Payment` row with `payment_type='subscription'`, `reference_id=plan_id`.
3. Call ZarinPal `create_payment`.
4. Return redirect URL.

#### `POST /subscription/upgrade`
Upgrade mid-cycle. Prorates remaining value.

```json
// Request
{
  "new_plan_id": "unlimited"
}

// Response 200
{
  "proration_credit": 332667,     // Tomans credited from unused Pro days
  "new_plan_price": 999000,
  "amount_due": 666333,           // new_plan_price - proration_credit
  "payment_url": "https://...",
  "authority": "xxxxx"
}
```

**Proration formula:**
```
days_remaining = (ends_at - now()).days
unused_value = price_paid * (days_remaining / 30)
amount_due = new_plan_price - unused_value
```

#### `POST /subscription/cancel`
Cancel subscription (effective at end of current period).

```json
// Request
{} // no body needed

// Response 200
{
  "status": "cancelled",
  "effective_until": "2026-08-01T00:00:00Z",
  "message": "اشتراک شما تا پایان دوره فعال خواهد بود"
}
```

Sets `auto_renew = FALSE`, `cancelled_at = now()`. The subscription remains `active` until `ends_at`.

#### `POST /subscription/renew`
Manually renew (or re-enable auto-renew).

```json
// Request
{
  "auto_renew": true
}

// Response 200
{
  "status": "ok",
  "auto_renew": true,
  "next_billing_date": "2026-08-01T00:00:00Z"
}
```

---

### 4.3 PAYG Toggle (Auth Required)

#### `GET /me/billing-settings`
```json
// Response 200
{
  "payg_enabled": true,
  "payg_hard_limit": null,
  "notify_on_usage_pct": 80
}
```

#### `PUT /me/billing-settings`
```json
// Request
{
  "payg_enabled": false,          // toggle PAYG on/off
  "payg_hard_limit": 500000,      // optional monthly cap in Tomans
  "notify_on_usage_pct": 70
}

// Response 200
{
  "status": "ok",
  "payg_enabled": false,
  "payg_hard_limit": 500000,
  "notify_on_usage_pct": 70
}
```

**When PAYG is disabled:** If the user runs out of subscription quota, requests are rejected with `429 quota_exceeded` instead of falling back to wallet.

---

### 4.4 Credit Packages (Auth Required)

#### `GET /credit-packages` (alias of `/plans` response `credit_packages` field)
Already included in `GET /plans`.

#### `POST /credit-packages/checkout`
```json
// Request
{
  "package_id": "popular"   // 'starter' | 'popular' | 'mega' | 'whale'
}

// Response 200
{
  "payment_url": "https://...",
  "authority": "xxxxx",
  "amount": 100000,
  "total_credits": 120000,
  "bonus_percent": 20
}
```

**Flow:**
1. Create `Payment` row with `payment_type='credit_package'`, `reference_id=package_id`.
2. Call ZarinPal.
3. On callback success: `credit_wallet(repo, user_id, Money(120000), reason="بسته اعتباری ₫۱۰۰ هزار (+۲۰٪)", idempotency_key="pkg:popular:{payment_id}")`.

---

### 4.5 Modified Payment Callback

The existing `GET /payment/callback` needs to be extended to handle the new `payment_type` values:

```python
# In handle_payment_callback or the callback route handler:

if payment.payment_type == 'subscription':
    # Activate subscription
    plan = await get_plan(session, payment.reference_id)
    subscription = Subscription(
        user_id=payment.user_id,
        plan=plan.id,
        status='active',
        monthly_token_quota=plan.monthly_token_quota,
        tokens_used_this_period=0,
        auto_renew=True,
        price_paid=payment.amount,
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )
    session.add(subscription)
    await credit_wallet(...)  # optional: credit remaining wallet balance

elif payment.payment_type == 'credit_package':
    pkg = await get_credit_package(session, payment.reference_id)
    await credit_wallet(
        repo, payment.user_id, Money(pkg.total_credits),
        reason=f"بسته اعتباری {pkg.name_fa}",
        idempotency_key=f"pkg:{pkg.id}:{payment.id}",
    )

elif payment.payment_type == 'wallet_topup':
    # existing flow (no change)
    await credit_wallet(...)
```

---

### 4.6 Admin Endpoints

#### `GET /admin/plans`
List all plans with subscriber counts.

#### `PUT /admin/plans/{plan_id}`
Update plan pricing, quotas, features.

#### `GET /admin/subscriptions`
List subscriptions with filters (`?status=active&plan=pro&page=1&limit=50`).

```json
{
  "subscriptions": [...],
  "total": 142,
  "page": 1,
  "limit": 50
}
```

#### `POST /admin/subscriptions/{sub_id}/extend`
Admin override: extend a subscription by N days.

#### `POST /admin/users/{uid}/grant-subscription`
Admin grant: give a user a subscription without payment (for support/comps).

#### `GET /admin/credit-packages`
List credit packages with purchase counts.

#### `PUT /admin/credit-packages/{pkg_id}`
Update package pricing/bonus.

---

### 4.7 Billing Status Endpoint (for Chat Pipeline)

#### `GET /me/billing-status` (internal, used by chat pipeline)
Fast check for the billing gate:

```json
{
  "can_chat": true,
  "billing_mode": "subscription",  // 'subscription' | 'payg' | 'free_tier' | 'blocked'
  "subscription": {
    "plan_id": "pro",
    "tokens_remaining": 11500000,
    "quota_pct_used": 42.5
  },
  "payg": {
    "enabled": true,
    "wallet_balance": 250000
  },
  "free_tier": {
    "daily_limit": 100000,
    "used_today": 45000
  }
}
```

---

## 5. Billing Flow — Subscription vs PAYG

### 5.1 Billing Priority Matrix

When a user sends a chat request, the billing pipeline resolves charges in this order:

```
┌─────────────────────────────────────────────────────┐
│              Incoming Chat Request                   │
│                     │                                │
│                     ▼                                │
│         ┌─────────────────────┐                     │
│         │ Has active          │                     │
│         │ subscription?       │                     │
│         └────────┬────────────┘                     │
│            YES   │   NO                             │
│            │     │     │                             │
│            ▼     │     ▼                             │
│  ┌─────────────┐ │  ┌──────────────────┐            │
│  │ Check sub   │ │  │ Is model free?   │            │
│  │ quota       │ │  └───┬─────────┬────┘            │
│  │ remaining   │ │  YES │     NO  │                 │
│  └──┬──────┬───┘ │      ▼         ▼                 │
│  OK │  OUT │     │  ┌────────┐ ┌──────────────┐     │
│     │      │     │  │ Use    │ │ PAYG enabled?│     │
│     ▼      ▼     │  │ free   │ └──┬───────┬───┘     │
│  ┌──────┐ ┌────┐ │  │ tier   │ YES│    NO │         │
│  │Bill  │ │Fall│ │  └────────┘    ▼       ▼         │
│  │to sub│ │back│ │         ┌────────┐ ┌─────────┐   │
│  │quota │ │to  │ │         │Deduct  │ │ 429     │   │
│  └──────┘ │PAYG│ │         │from    │ │ quota   │   │
│           └────┘ │         │wallet  │ │exceeded │   │
│                  │         └────────┘ └─────────┘   │
└──────────────────┴──────────────────────────────────┘
```

### 5.2 Detailed Billing Steps

```python
async def resolve_billing(uid: int, model: str, input_tokens: int, output_tokens: int) -> BillingResult:
    """
    Returns BillingResult with:
      - billing_mode: 'subscription' | 'payg' | 'free_tier' | 'blocked'
      - subscription_charged: int (tokens deducted from sub quota)
      - payg_charged: int (Tomans deducted from wallet)
      - blocked_reason: str | None
    """

    # 1. Look up model price from model_catalog
    price = await get_model_price(model)
    total_cost_tomans = compute_charge(price, input_tokens=input_tokens, output_tokens=output_tokens)

    # 2. Check if model is in free tier (OpenRouter free models)
    if is_free_model(model):
        # Only check daily free-tier token limit
        free_used = await get_free_tier_usage(uid)
        if free_used + total_tokens > FREE_DAILY_LIMIT:
            return BillingResult(billing_mode='blocked', blocked_reason='free_tier_exhausted')
        await record_free_usage(uid, total_tokens)
        return BillingResult(billing_mode='free_tier')

    # 3. Check active subscription
    sub = await get_active_subscription(uid)
    if sub and sub.status == 'active':
        remaining = sub.monthly_token_quota - sub.tokens_used_this_period
        if sub.monthly_token_quota == 0:  # unlimited plan
            await charge_to_subscription(sub, total_tokens, 0)
            return BillingResult(billing_mode='subscription', subscription_charged=total_tokens)

        if remaining >= total_tokens:
            # Fits within subscription quota
            await charge_to_subscription(sub, total_tokens, 0)
            return BillingResult(billing_mode='subscription', subscription_charged=total_tokens)
        else:
            # Partial subscription + overflow to PAYG
            sub_tokens = remaining
            overflow_tokens = total_tokens - remaining
            overflow_cost = compute_charge(price,
                input_tokens=int(input_tokens * overflow_tokens / total_tokens),
                output_tokens=int(output_tokens * overflow_tokens / total_tokens))

            await charge_to_subscription(sub, sub_tokens, overflow_tokens)

            # Check if PAYG is enabled
            billing_settings = await get_billing_settings(uid)
            if not billing_settings.payg_enabled:
                return BillingResult(billing_mode='blocked', blocked_reason='subscription_exhausted_payg_disabled')

            # Fall through to PAYG for overflow
            return await charge_payg(uid, overflow_cost, sub_id=sub.id)

    # 4. No subscription — pure PAYG
    billing_settings = await get_billing_settings(uid)
    if not billing_settings.payg_enabled:
        # Check free tier as last resort
        if await get_free_tier_usage(uid) + total_tokens <= FREE_DAILY_LIMIT:
            await record_free_usage(uid, total_tokens)
            return BillingResult(billing_mode='free_tier')
        return BillingResult(billing_mode='blocked', blocked_reason='no_subscription_no_payg')

    return await charge_payg(uid, total_cost_tomans)


async def charge_payg(uid: int, cost: Money, sub_id=None) -> BillingResult:
    """Deduct from wallet balance."""
    wallet = await get_wallet(uid)
    available = wallet['balance'] - wallet['reserved']
    if cost.irt > available:
        return BillingResult(billing_mode='blocked', blocked_reason='insufficient_balance')

    # Reserve → settle pattern (existing BillingService)
    await billing_service.reserve(uid, cost, idempotency_key=...)
    await billing_service.settle(...)

    return BillingResult(billing_mode='payg', payg_charged=cost.irt)
```

### 5.3 Token Accounting for Subscription

For subscription billing, we track **tokens** not Tomans against the quota:

```python
async def charge_to_subscription(sub, tokens_used: int, overflow_tokens: int):
    """Update subscription usage counter."""
    sub.tokens_used_this_period += tokens_used
    # If overflow, also record in subscription_quota_log
    if overflow_tokens > 0:
        await record_quota_log(sub, overflow_tokens)
```

### 5.4 Modified `_track_usage` and `_bill_stream_usage`

The existing functions in `app.py` need to be refactored to use the new `resolve_billing()`:

```python
async def _track_usage(request, payload, response_data):
    uid = await _get_user_id(request)
    usage = response_data.get('usage', {})
    # ... extract tokens ...
    result = await resolve_billing(uid, model, input_tokens, output_tokens)

    if result.blocked_reason:
        # Log but don't fail (request already completed)
        pass

    # Record usage_event with billing_source
    await record_usage(
        repo,
        billing_source=result.billing_mode,
        subscription_id=result.subscription_id,
        credits_charged=result.subscription_charged,
        payg_charged=result.payg_charged,
        ...
    )
```

---

## 6. Frontend Pages

### 6.1 Pricing Page Redesign — `frontend/app/pricing/page.tsx`

**Current:** Static 3-card layout with hardcoded data.
**New:** Dynamic page fetching from `GET /plans`, with 4 subscription tiers + credit packages section.

#### Component Structure:

```
app/pricing/page.tsx
├── PricingHero                    — headline + toggle (monthly/annual)
├── PlanCards (4-up grid)
│   ├── PlanCard                   — per plan
│   │   ├── PlanBadge              — "محبوب" on Pro
│   │   ├── PlanPrice              — formatted Toman + per-month
│   │   ├── PlanQuota              — token count display
│   │   ├── PlanFeatures           — feature checklist
│   │   └── PlanCTA               — "انتخاب پلن" / "فعال" / "ارتقا"
│   └── ...
├── CreditPackagesSection
│   ├── CreditPackageCard (×4)
│   │   ├── PackageAmount          — ₫100,000
│   │   ├── PackageBonus           — "+20% هدیه" badge
│   │   └── PackageCTA             — "خرید"
│   └── ...
├── FeatureComparisonTable         — detailed feature comparison grid
└── FAQSection                     — common questions
```

#### Key Implementation Details:

```tsx
// app/pricing/page.tsx — 'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import { toast } from '@/components/ui'
import { Icon } from '@/components/ui/Icon'

type Plan = {
  id: string
  name_fa: string
  name_en: string
  price_monthly: number
  monthly_token_quota: number
  daily_token_limit: number
  priority_queue: boolean
  features: string[]
  sort_order: number
}

type CreditPackage = {
  id: string
  name_fa: string
  base_amount: number
  bonus_percent: number
  total_credits: number
}

type UserSubscription = {
  plan_id: string | null
  status: string | null
  tokens_remaining: number | null
}

export default function PricingPage() {
  const { token, user } = useAuth()
  const [plans, setPlans] = useState<Plan[]>([])
  const [packages, setPackages] = useState<CreditPackage[]>([])
  const [userSub, setUserSub] = useState<UserSubscription | null>(null)
  const [busy, setBusy] = useState<string | null>(null)  // plan_id being processed

  useEffect(() => {
    fetch('/api/plans')
      .then(r => r.json())
      .then(d => { setPlans(d.plans); setPackages(d.credit_packages) })

    if (token) {
      fetch('/api/me/subscription', { headers: { Authorization: `Bearer ${token}` } })
        .then(r => r.json())
        .then(d => setUserSub(d.subscription))
    }
  }, [token])

  const handleSelectPlan = async (planId: string) => {
    if (!token) return window.location.href = '/login'
    setBusy(planId)
    try {
      const res = await fetch('/api/subscription/checkout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_id: planId }),
      })
      const data = await res.json()
      if (res.ok && data.payment_url) {
        window.location.href = data.payment_url
      } else {
        toast(data.detail || 'خطا', 'error')
      }
    } finally { setBusy(null) }
  }

  const handleBuyPackage = async (packageId: string) => {
    if (!token) return window.location.href = '/login'
    setBusy(packageId)
    try {
      const res = await fetch('/api/credit-packages/checkout', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ package_id: packageId }),
      })
      const data = await res.json()
      if (res.ok && data.payment_url) {
        window.location.href = data.payment_url
      } else {
        toast(data.detail || 'خطا', 'error')
      }
    } finally { setBusy(null) }
  }

  // ... render plan cards, credit packages, etc.
}
```

---

### 6.2 Billing Dashboard — `frontend/app/billing/page.tsx` (NEW)

A unified billing management page replacing the simple wallet topup.

```
app/billing/page.tsx
├── BillingHeader                  — "مدیریت حساب و پرداخت"
├── CurrentPlanCard
│   ├── PlanName + Status badge
│   ├── TokenQuotaBar             — progress bar (used / total)
│   ├── DaysRemaining
│   └── Actions: Upgrade / Cancel / Renew
├── PAYGToggleCard
│   ├── Toggle switch             — "پرداخت به ازای مصرف"
│   ├── WalletBalance display
│   └── HardLimitInput            — optional monthly cap
├── QuickTopUpCard                — existing wallet topup (compact)
├── UsageChart                    — token usage over time (last 30 days)
└── RecentTransactions            — combined ledger + subscription payments
```

---

### 6.3 Subscription Checkout Flow — `frontend/app/billing/checkout/page.tsx` (NEW)

```
app/billing/checkout/page.tsx
├── PlanSummary                    — selected plan details
├── PriceBreakdown                 — plan price, any proration, total
├── PaymentMethodSelector          — ZarinPal (only option for now)
├── ConfirmButton                  — "پرداخت و فعالسازی"
└── SuccessCallback handling       — on return from ZarinPal
```

---

### 6.4 Modifications to Existing Pages

| Page | Change |
|------|--------|
| `app/wallet/page.tsx` | Add subscription status banner at top. Show billing source in ledger entries. |
| `app/chat/page.tsx` | Show quota remaining indicator in header. Block chat when quota exhausted. |
| `app/profile/page.tsx` | Add "مدیریت اشتراک" link to billing page. |
| `app/layout.tsx` | Add billing nav item. |
| `components/AppShell.tsx` | Add billing icon to sidebar. |
| `components/Chat.tsx` | Display quota warning banner when <10% remaining. |

---

## 7. Edge Cases & Failure Modes

### 7.1 Plan Expiry

**Scenario:** Subscription `ends_at` passes without renewal.

```
Cron job (every hour):
  SELECT * FROM subscriptions
  WHERE status = 'active' AND ends_at < now() AND auto_renew = FALSE

  For each:
    1. SET status = 'expired'
    2. Create notification: "اشراک {plan} شما منقضی شد"
    3. User falls back to free tier or PAYG
```

**Implementation:** Add `check_expired_subscriptions()` to a background task in `app.py` lifespan, or run as a Redis-cron every hour.

```python
# In app.py lifespan:
async def _subscription_expiry_loop():
    while True:
        await asyncio.sleep(3600)  # every hour
        try:
            async with async_session() as session:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                await session.execute(
                    sqlalchemy.text("""
                        UPDATE subscriptions
                        SET status = 'expired', updated_at = :now
                        WHERE status = 'active' AND ends_at < :now AND auto_renew = FALSE
                    """), {'now': now}
                )
                await session.commit()
        except Exception:
            pass
```

### 7.2 Auto-Renewal

**Scenario:** `auto_renew = TRUE` and `ends_at` approaches.

```
Cron job (daily at 00:00 UTC):
  SELECT * FROM subscriptions
  WHERE status = 'active' AND auto_renew = TRUE
    AND ends_at BETWEEN now() AND now() + INTERVAL '3 days'

  For each:
    1. Check wallet balance >= price_paid
    2. If sufficient:
       a. Deduct from wallet via ledger
       b. SET starts_at = ends_at, ends_at = ends_at + 30 days
       c. SET tokens_used_this_period = 0
       d. Create notification: "اشتراک {plan} تمدید شد"
    3. If insufficient:
       a. Enter grace period: SET status = 'grace_period', grace_ends_at = ends_at + 3 days
       b. Create notification: "موجودی کیف پول برای تمدید کافی نیست"
       c. Send email if available
```

### 7.3 Grace Period

**Scenario:** Auto-renewal failed due to insufficient funds.

```
Duration: 3 days after ends_at
During grace:
  - User can still use subscription quota (status = 'grace_period')
  - Notification + email sent daily as reminder
  - If wallet is topped up during grace: auto-renew triggers
  - After grace expires: status → 'expired', fall back to free/PAYG
```

```python
# In the billing pipeline:
if sub.status == 'grace_period':
    if now > sub.grace_ends_at:
        sub.status = 'expired'
        # fall through to free/PAYG
    else:
        # Still treat as active for quota purposes
        pass
```

### 7.4 Mid-Plan Upgrade

**Scenario:** User on Basic (₫149K) wants to upgrade to Pro (₫499K) mid-month.

```
Proration logic:
  days_remaining = max(0, (ends_at - now()).days)
  days_total = 30
  unused_fraction = days_remaining / days_total
  credit_from_old = round(price_paid_old * unused_fraction)
  amount_due = price_paid_new - credit_from_old

  Example:
    Basic ₫149K, 12 days remaining
    credit_from_old = round(149000 * 12/30) = 59600
    amount_due = 499000 - 59600 = 439400

  1. Create Payment with amount = amount_due
  2. On callback success:
     a. Close old subscription: status = 'cancelled'
     b. Create new subscription with new plan
     c. Carry over remaining tokens proportionally:
        carried_tokens = (tokens_remaining / monthly_quota_old) * monthly_quota_new
```

### 7.5 Mid-Plan Downgrade

**Scenario:** User on Pro wants to downgrade to Basic.

```
Option A (recommended): Schedule downgrade for end of period
  1. SET auto_renew = FALSE on current subscription
  2. Create a pending_downgrade record
  3. At expiry: create new Basic subscription

Option B: Immediate downgrade with refund
  1. Prorate refund for unused Pro days
  2. Credit wallet with refund amount
  3. Start Basic subscription immediately
  4. Tokens carried proportionally
```

**Recommendation:** Option A (simpler, no refund complexity).

### 7.6 Refund Logic

**Scenario:** User requests a refund for a subscription.

```
Policy:
  - Within 24 hours of purchase, < 10% quota used → full refund
  - Within 24 hours, > 10% quota used → no refund
  - After 24 hours → no refund (prorated credit on upgrade only)

Implementation:
  POST /admin/subscriptions/{sub_id}/refund
  {
    "reason": "user request",
    "amount": 499000,        // or partial
    "refund_to": "wallet"    // 'wallet' | 'original_payment'
  }

  1. Verify payment was made via ZarinPal (check payments table)
  2. If refund_to = 'wallet': credit_wallet(user_id, Money(amount))
  3. If refund_to = 'original_payment': initiate ZarinPal reverse (if supported)
  4. SET subscription status = 'cancelled'
  5. Audit log
```

### 7.7 Concurrent Usage Race Condition

**Scenario:** Two requests arrive simultaneously, both trying to use the last tokens of subscription quota.

```python
# In resolve_billing():
async with session.begin():
    # Lock subscription row FOR UPDATE
    sub = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == uid, Subscription.status == 'active')
        .with_for_update()
    )
    sub = sub.fetchone()
    # Now safe to check and decrement
    remaining = sub.monthly_token_quota - sub.tokens_used_this_period
    # ... deduct atomically
```

### 7.8 Plan Model Restrictions

**Scenario:** Basic plan restricts access to premium models (gpt-5.6-luna).

```python
# In the billing pipeline, before calling upstream:
plan = await get_user_plan(uid)
if plan and plan.models_allowed is not None:
    if model not in plan.models_allowed:
        return JSONResponse({
            'error': {
                'message': f'مدل {model} در پلن {plan.name_fa} در دسترس نیست. لطفاً ارتقا دهید.',
                'type': 'plan_restriction',
                'code': 'model_not_allowed',
                'upgrade_url': '/pricing'
            }
        }, status_code=403)
```

### 7.9 Free Tier Abuse Prevention

```
Rate limits for free tier:
  - 100K tokens/day
  - Max 50 requests/hour
  - No streaming for premium models
  - IP-based duplicate account detection (admin tooling)
```

---

## 8. Migration Strategy

### 8.1 Migration File: `0005_pricing_system.sql`

All schema changes go in this single migration file. The migration runner (`migrate.py`) will pick it up automatically on startup.

**Order of operations:**
1. Create `plans` table + seed data
2. Create `credit_packages` table + seed data
3. Create `user_billing_settings` table
4. Create `subscription_quota_log` table
5. Alter `subscriptions` (add columns, extend CHECK)
6. Alter `usage_events` (add billing columns)
7. Alter `payments` (add payment_type, reference_id)
8. Backfill existing data:
   - Insert `user_billing_settings` for all existing users (payg_enabled = TRUE)
   - Update existing subscriptions to have status = 'active' where ends_at > now()

### 8.2 ORM Model Updates in `app.py`

```python
class Plan(Base):
    __tablename__ = 'plans'
    id: Mapped[str] = mapped_column(primary_key=True)
    name_fa: Mapped[str]
    name_en: Mapped[str]
    price_monthly: Mapped[int] = mapped_column(default=0)
    monthly_token_quota: Mapped[int] = mapped_column(default=0)
    daily_token_limit: Mapped[int] = mapped_column(default=0)
    models_allowed: Mapped[list | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    priority_queue: Mapped[bool] = mapped_column(default=False)
    features: Mapped[dict] = mapped_column(sqlalchemy.JSON, default=list)
    active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class CreditPackage(Base):
    __tablename__ = 'credit_packages'
    id: Mapped[str] = mapped_column(primary_key=True)
    name_fa: Mapped[str]
    name_en: Mapped[str]
    base_amount: Mapped[int]
    bonus_percent: Mapped[int] = mapped_column(default=0)
    total_credits: Mapped[int]
    active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class UserBillingSettings(Base):
    __tablename__ = 'user_billing_settings'
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), primary_key=True)
    payg_enabled: Mapped[bool] = mapped_column(default=True)
    payg_hard_limit: Mapped[int | None] = mapped_column(nullable=True)
    notify_on_usage_pct: Mapped[int] = mapped_column(default=80)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class SubscriptionQuotaLog(Base):
    __tablename__ = 'subscription_quota_log'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('users.id'), index=True)
    subscription_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey('subscriptions.id'))
    period_start: Mapped[datetime]
    period_end: Mapped[datetime]
    token_quota: Mapped[int]
    tokens_used: Mapped[int] = mapped_column(default=0)
    overage_tokens: Mapped[int] = mapped_column(default=0)
    overage_charged: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
```

### 8.3 Existing Subscription Backfill

```sql
-- Backfill: mark all existing subscriptions with status
UPDATE subscriptions SET status = 'active'
WHERE status IS NULL AND (ends_at IS NULL OR ends_at > now());

UPDATE subscriptions SET status = 'expired'
WHERE status IS NULL AND ends_at IS NOT NULL AND ends_at <= now();

-- Backfill: create billing settings for existing users
INSERT INTO user_billing_settings (user_id, payg_enabled)
SELECT id, TRUE FROM users
ON CONFLICT (user_id) DO NOTHING;
```

---

## 9. Testing Plan

### 9.1 Unit Tests

| Test file | What it tests |
|-----------|---------------|
| `tests/test_plans.py` | Plan CRUD, plan catalog endpoint, credit package CRUD |
| `tests/test_subscription_lifecycle.py` | Subscribe → active, expire, cancel, grace, auto-renew |
| `tests/test_subscription_upgrade.py` | Proration math, mid-cycle upgrade, downgrade scheduling |
| `tests/test_payg_toggle.py` | Toggle on/off, effect on billing pipeline |
| `tests/test_credit_packages.py` | Purchase flow, bonus calculation, wallet credit |
| `tests/test_billing_priority.py` | Subscription-first → PAYG fallback → free tier → block |
| `tests/test_model_restrictions.py` | Plan-based model allowlist enforcement |
| `tests/test_concurrent_billing.py` | FOR UPDATE lock correctness under parallel requests |

### 9.2 Integration Tests

| Test | What it tests |
|------|---------------|
| Full subscription checkout → ZarinPal sandbox → callback → activation | End-to-end flow |
| Credit package purchase → callback → wallet credit with bonus | End-to-end flow |
| Subscription expiry cron → user falls back to PAYG | Background job |
| Auto-renewal → wallet deduction → subscription extension | Background job |

### 9.3 Billing Math Tests

```python
def test_proration_basic_to_pro():
    """Basic ₫149K, 12 days remaining → upgrade to Pro ₫499K"""
    credit = round(149000 * 12 / 30)  # = 59600
    amount_due = 499000 - credit       # = 439400
    assert amount_due == 439400

def test_credit_package_bonus():
    """₨100K package with 20% bonus → ₫120K credits"""
    assert 100000 * 1.20 == 120000

def test_subscription_then_payg():
    """10M tokens on Pro (20M quota) → all subscription"""
    result = resolve_billing(sub_quota=20_000_000, used=0, tokens=10_000_000)
    assert result.billing_mode == 'subscription'
    assert result.subscription_charged == 10_000_000
    assert result.payg_charged == 0

def test_subscription_overflow_to_payg():
    """25M tokens on Pro (20M quota) → 20M sub + 5M PAYG"""
    result = resolve_billing(sub_quota=20_000_000, used=0, tokens=25_000_000)
    assert result.subscription_charged == 20_000_000
    assert result.payg_charged > 0  # 5M tokens worth

def test_payg_disabled_blocks_overflow():
    """PAYG disabled, subscription exhausted → blocked"""
    result = resolve_billing(sub_quota=20_000_000, used=19_000_000, tokens=5_000_000, payg_enabled=False)
    assert result.billing_mode == 'blocked'
```

---

## 10. Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] Create migration `0005_pricing_system.sql`
- [ ] Add ORM models (Plan, CreditPackage, UserBillingSettings, SubscriptionQuotaLog)
- [ ] Update Subscription model with new columns
- [ ] Seed plan data and credit package data
- [ ] Implement `GET /plans` endpoint
- [ ] Implement `GET /me/subscription` endpoint
- [ ] Implement `GET/PUT /me/billing-settings` (PAYG toggle)

### Phase 2: Subscription Purchase (Week 2)
- [ ] Implement `POST /subscription/checkout`
- [ ] Modify `payment_callback` to handle `payment_type='subscription'`
- [ ] Implement `POST /subscription/cancel`
- [ ] Implement `POST /subscription/renew`
- [ ] Frontend: Redesign pricing page with dynamic data
- [ ] Frontend: Subscription checkout flow

### Phase 3: Credit Packages (Week 2-3)
- [ ] Implement `POST /credit-packages/checkout`
- [ ] Modify `payment_callback` for `payment_type='credit_package'`
- [ ] Frontend: Credit package cards on pricing page

### Phase 4: Billing Pipeline Integration (Week 3)
- [ ] Implement `resolve_billing()` function
- [ ] Refactor `_track_usage` and `_bill_stream_usage` to use `resolve_billing()`
- [ ] Implement `GET /me/billing-status`
- [ ] Add model restriction enforcement
- [ ] Frontend: Billing dashboard page
- [ ] Frontend: Quota indicator in chat header

### Phase 5: Background Jobs (Week 4)
- [ ] Subscription expiry cron
- [ ] Auto-renewal cron
- [ ] Grace period handling
- [ ] Usage notification system (80%/90%/100% quota alerts)

### Phase 6: Admin Tooling (Week 4)
- [ ] Admin plan management endpoints
- [ ] Admin subscription management endpoints
- [ ] Admin grant/refund endpoints
- [ ] Admin dashboard: subscription analytics

### Phase 7: Polish & Testing (Week 5)
- [ ] Full test suite
- [ ] Load testing billing pipeline
- [ ] Edge case hardening
- [ ] Documentation

---

## Appendix A: Pricing Reference

### Model Prices (IRT per 1M tokens)

| Model | Input | Output | Cost Basis (USD × ₫180K) | Our Price | Margin |
|-------|-------|--------|--------------------------|-----------|--------|
| mimo-v2.5 | ₫18,900 | ₫50,400 | ₫5,400 / ₫14,400 | ₫18,900 / ₫50,400 | ~71% |
| mimo-v2.5-pro | ₫78,300 | ₫156,600 | ~₫21,600 / ~₫43,200 | ₫78,300 / ₫156,600 | ~72% |
| gpt-5.6-luna | ₫180,000 | ₫1,080,000 | ₫72,000 / ₫432,000 | ₫180,000 / ₫1,080,000 | ~60% |
| Free OpenRouter | ₫3,000-5,000 | ₫8,000-15,000 | ₫0 | ₫3,000-5,000 | 100% |

### Plan Economics

| Plan | Price | Estimated Max Cost (heavy usage) | Margin |
|------|-------|----------------------------------|--------|
| Free | ₫0 | ₫0 (limited models) | N/A |
| Basic ₫149K | ₫149,000 | ~₫95,000 (5M tokens on mimo-v2.5) | ~36% |
| Pro ₫499K | ₫499,000 | ~₫380,000 (20M tokens mixed) | ~24% |
| Unlimited ₫999K | ₫999,000 | Variable (heavy users may cost more) | Risk-managed |

> **Note:** Pro/Unlimited margins are lower because they include premium model access. The PAYG overflow mechanism ensures that heavy users pay for their actual consumption beyond quota, protecting margins.

---

## Appendix B: API Endpoint Summary

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/plans` | No | List plans + credit packages |
| GET | `/me/subscription` | Yes | Current subscription + billing status |
| POST | `/subscription/checkout` | Yes | Start subscription payment |
| POST | `/subscription/upgrade` | Yes | Mid-cycle upgrade with proration |
| POST | `/subscription/cancel` | Yes | Cancel (end of period) |
| POST | `/subscription/renew` | Yes | Re-enable auto-renew |
| GET | `/me/billing-settings` | Yes | PAYG toggle + limits |
| PUT | `/me/billing-settings` | Yes | Update PAYG settings |
| GET | `/credit-packages` | No | List credit packages |
| POST | `/credit-packages/checkout` | Yes | Purchase credit package |
| GET | `/me/billing-status` | Yes | Fast billing status check |
| GET | `/admin/plans` | Admin | List all plans |
| PUT | `/admin/plans/{plan_id}` | Admin | Update plan |
| GET | `/admin/subscriptions` | Admin | List subscriptions |
| POST | `/admin/subscriptions/{id}/extend` | Admin | Extend subscription |
| POST | `/admin/users/{uid}/grant-subscription` | Admin | Grant subscription |
| POST | `/admin/subscriptions/{id}/refund` | Admin | Process refund |
| GET | `/admin/credit-packages` | Admin | List packages |
| PUT | `/admin/credit-packages/{id}` | Admin | Update package |

---

## Appendix C: File Modification Inventory

### New Files
| File | Description |
|------|-------------|
| `backend/migrations/0005_pricing_system.sql` | All schema changes |
| `backend/services/subscription.py` | Subscription lifecycle logic |
| `backend/services/billing_priority.py` | `resolve_billing()` — the billing pipeline |
| `backend/routes/plans.py` | Plan catalog endpoints (optional, could be in app.py) |
| `frontend/app/billing/page.tsx` | Billing dashboard |
| `frontend/app/billing/checkout/page.tsx` | Subscription checkout flow |
| `backend/tests/test_plans.py` | Plan CRUD tests |
| `backend/tests/test_subscription_lifecycle.py` | Subscription lifecycle tests |
| `backend/tests/test_billing_priority.py` | Billing priority tests |
| `backend/tests/test_credit_packages.py` | Credit package tests |

### Modified Files
| File | Changes |
|------|---------|
| `backend/app.py` | Add ORM models, new routes, modify `_check_quota_pre`, `_track_usage`, `_bill_stream_usage`, `payment_callback` |
| `backend/services/billing.py` | Add subscription-aware methods to `SqlBillingRepo` |
| `backend/services/metering.py` | Add `billing_source` to `record_usage` |
| `backend/payment.py` | Handle `payment_type` in `handle_payment_callback` |
| `frontend/app/pricing/page.tsx` | Complete redesign with dynamic data |
| `frontend/app/wallet/page.tsx` | Add subscription status banner |
| `frontend/components/AppShell.tsx` | Add billing nav item |
| `frontend/components/Chat.tsx` | Add quota warning indicator |
