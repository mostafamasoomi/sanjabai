# Multiai Aurora — Revised Full Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Execute only inside `/root/multiai`; never modify `/root/multiapi`.

**Goal:** Stabilize Multiai, define enforceable product/data/financial contracts, then deliver a fast, premium, Persian-first AI workspace with reliable billing, secure auth, strong accessibility, and measurable performance.

**Architecture:** Keep Next.js 14 App Router + FastAPI + PostgreSQL + Redis + LiteLLM, but establish typed contracts and source-of-truth boundaries before UI redesign. Billing becomes reservation/settlement based; model catalog and claims become API-backed; user/admin auth are separated; every phase has tests and a gate.

**Tech Stack:** Next.js 14, React 18, TypeScript 5.5, Tailwind, Recharts, Playwright, axe, FastAPI, SQLAlchemy async, PostgreSQL, Redis, LiteLLM, pytest/httpx.

**Scope:** `/root/multiai` only. Do not touch `/root/multiapi`, port 3005, or its containers.

---

## 0. Blocking findings from review

The previous plan and `docs/product-contract.md` were incomplete. Before UI work, these blockers must be resolved:

- `pytest`: currently 64 passed with 55 warnings; warnings must be categorized and fixed or explicitly justified.
- Frontend build works after fixes, but must be reproducible with `npm ci` and a pinned TypeScript version.
- Model UI and landing contain static model/claim/pricing data.
- Billing logic is not consistently tied to the pricing table and has no reservation/settlement contract.
- Session/admin tokens use browser storage; this is not acceptable for production.
- Team segment is currently a product promise without implemented tenancy/authorization; define it as Phase 1 scope or explicit non-goal. This plan chooses **Team = documented future/non-goal until tenancy exists**.
- `admin/static/admin.js` and any `NEXT_PUBLIC_*` secret-like value must be audited; browser-visible values are never secrets.
- Existing migration tests mock migrations; add real PostgreSQL migration tests separately.

---

## 1. Source-of-truth matrix

| Domain | Canonical source | Read API | Write path | Cache | Audit owner |
|---|---|---|---|---|---|
| Model catalog | approved DB snapshot + provider verification | `GET /catalog/models` | admin catalog workflow | Redis short TTL | Platform |
| Pricing | versioned DB rows | `GET /catalog/pricing` | admin pricing workflow | Redis short TTL | Finance |
| Claims | claim registry DB/config | `GET /content/claims` | reviewed admin/content workflow | build-safe fallback | Product |
| Wallet | ledger + reservations | `GET /wallet` | service layer only | no authoritative cache | Finance |
| Usage | immutable usage events | `GET /usage` | metering service | aggregate cache | Platform |
| Auth/session | server-side session store | cookie/session endpoints | auth service | Redis session | Security |
| Team | tenant/membership tables (future) | future `/teams/*` | future admin/team owner | tenant-scoped | Security |

Frontend must never be the source of truth for models, prices, balances, credits, claims, or permissions.

---

## 2. Contract decisions

### 2.1 Segments

#### Consumer
- Job: chat, writing, translation, summary, analysis.
- Activation: first successful assistant response.
- Success: response within 90 seconds of signup, understandable cost shown.
- Access: chat, public model catalog, wallet, profile, export.
- Non-goal: raw provider configuration and team administration.
- Billing: pay-as-you-go or approved promotional credit; no hardcoded gift amount.

#### Developer
- Job: OpenAI-compatible API integration.
- Activation: first API key + successful API request.
- Success: quickstart request succeeds with request ID and usage.
- Access: API keys, Playground, request logs, model/pricing metadata.
- Required contract: versioned endpoint, streaming, timeout, rate limit, error schema, request ID, idempotency where applicable.

#### Team
- **Current status: future/non-goal until tenancy is implemented.**
- Do not advertise shared wallets, SSO, team budgets, invitations, or audit logs until tenant isolation and role authorization exist.
- Future roles: owner, admin, member, billing manager; all objects must be tenant-scoped.

#### Anonymous visitor
- Read-only landing/catalog/pricing; no model inference unless an explicit, bounded anonymous trial is implemented with abuse controls and cost policy.

### 2.2 Claim policy

Create a registry with:

```text
claim_key, copy_fa, copy_en, claim_type,
source, verified_at, expires_at, owner,
audience, feature_flag, fallback_copy
```

`claim_type` is one of `fact | estimate | marketing | illustrative`.

Rules:

- No uptime, model count, provider availability, support, privacy, VPN, infrastructure, or gift-credit claim without source and expiry.
- Unverified claims are removed or labeled clearly as illustrative/estimate.
- CI must fail when forbidden literals appear in production landing copy: `۹۹.۹٪`, `۵۰+`, `دهها مدل`, `۱۰,۰۰۰`, `بدون VPN`, `سرور اختصاصی`, and equivalent English variants unless approved in registry.
- “No third-party sharing” is forbidden unless upstream data-processing policy proves it.

### 2.3 Model catalog contract

Canonical response:

```ts
export type ModelCatalogItem = {
  id: string;                 // stable Multiai ID
  providerModelId: string;    // upstream identifier
  provider: string;
  displayName: string;
  description?: string;
  modalities: { input: string[]; output: string[] };
  capabilities: string[];
  recommendedFor: string[];
  contextWindow: number;
  maxOutputTokens?: number;
  pricing: {
    currency: 'IRR' | 'IRT';
    inputPerMillion: number;
    outputPerMillion: number;
    cachedInputPerMillion?: number;
    reasoningPerMillion?: number;
    priceVersion: string;
    effectiveFrom: string;
  };
  availability: 'available' | 'degraded' | 'maintenance' | 'disabled';
  audience: ('consumer' | 'developer' | 'team')[];
  rateLimit?: { requestsPerMinute?: number; concurrency?: number };
  deprecatedAt?: string;
  lastVerifiedAt: string;
  provenance: 'provider' | 'admin-approved' | 'fallback';
};
```

Pydantic backend schema must mirror this contract. `frontend/app/models/page.tsx` and chat picker must consume the API only; no static production model list.

### 2.4 Financial contract

- Canonical storage currency: `IRT` integer minor unit; UI may display تومان with explicit label. Conversion is never implicit.
- `wallet.available`, `wallet.reserved`, and `wallet.promotional` are distinct values.
- Every price row is versioned with `price_version`, `effective_from`, `effective_to`, currency, and source.
- Before upstream request: authorize/reserve an upper bound using the selected price snapshot.
- After response: settle actual usage; release remainder. On upstream failure/cancel: deterministic release/refund policy.
- Usage must record model, price version, input/output/cached/reasoning tokens, request ID, reservation ID, and final charge.
- Free credit is a separate grant with `grant_id`, expiry, source, and remaining amount; it cannot silently become cash.
- Ledger is append-only. Each effect has `event_id`, `idempotency_key`, `currency`, `amount`, `balance_after`, `source_type`, `source_id`, `actor_id`, and metadata redaction rules.
- Invariant: `balance_after = previous_balance + amount`; duplicate business events produce no duplicate effect.
- Payment callback verifies authority, amount, order state, replay protection, and atomically updates order/wallet/ledger.
- Quota reset timezone is explicitly `Asia/Tehran` for local quotas, while timestamps remain UTC.
- Billing model for current release: **pay-as-you-go + promotional credit**. Subscription plans are not shown as active product promises until backed by quota/subscription tables and APIs.

### 2.5 API/error/security contract

Every response includes `X-Request-ID`; structured errors:

```json
{
  "error": {
    "code": "wallet_insufficient_balance",
    "message": "موجودی کافی نیست",
    "request_id": "...",
    "details": {}
  }
}
```

- Session: HttpOnly, Secure in production, SameSite=Lax/Strict, rotation, server-side Redis session, revoke/logout-all.
- Admin: separate origin/shell/session and authorization; never store admin token in localStorage.
- API keys: hash at rest, show secret once, scopes, created/last-used/revoked timestamps, optional expiry.
- Prompt/content logs: redaction, retention, delete/export policy; never log secrets or full prompt by default.

---

# Execution plan

## Phase 0 — Stabilization and reproducibility

### Task 0.1: Pin and verify runtimes

**Files:** `frontend/package.json`, `frontend/package-lock.json`, `backend/requirements.txt`, `.env.example`.

- Pin TypeScript compatible with Next 14.
- Run `npm ci && npm run build`.
- Run `pytest -q`; classify all warnings.
- Ensure `.env.example` contains placeholders only.

**Gate:** build success, tests pass, no unreviewed warnings.

### Task 0.2: Add smoke script

**Create:** `scripts/smoke.sh`.

Check Compose readiness, `/health/live`, `/health/ready`, frontend routes, auth unauthorized behavior, and no secret leakage. Exit nonzero on failure.

### Task 0.3: Real migration test

**Create:** `backend/tests/test_migrations_real.py`.

Run against disposable PostgreSQL service; test fresh migration, rerun idempotency, and existing schema. Keep unit mocks for fast tests but do not treat them as migration proof.

---

## Phase 1 — Product/Data Contract implementation

### Task 1.1: Replace the short product contract

**Modify:** `docs/product-contract.md`.

Add all sections from Contract decisions above, examples, source-of-truth matrix, non-goals, and versioning.

### Task 1.2: Add claim registry

**Create:** `backend/schemas/content.py`, `frontend/lib/claims.ts`, `docs/claims-policy.md`.

Implement typed claim schema and safe fallback copy. Add a test that scans landing/page translations for forbidden unregistered claims.

### Task 1.3: Add catalog schemas

**Create:** `backend/schemas/catalog.py`, `frontend/types/catalog.ts`.

Add validation for positive token/context values, currency, availability, effective dates, and stable IDs.

### Task 1.4: Add catalog endpoint

**Modify/Create:** `backend/app.py` initially or `backend/routers/catalog.py` if extracted; `frontend/app/api/models/route.ts`.

Return catalog items from approved DB data. Add contract tests for schema, disabled models, stale pricing, and no-secret response.

### Task 1.5: Remove static production model data

**Modify:** `frontend/app/models/page.tsx`, `frontend/app/chat/page.tsx`, `frontend/app/compare/page.tsx`, `frontend/components/ModelSelect.tsx`.

Use loading/empty/error states; only allow fallback data in explicit demo mode with visible “نمونه” label.

### Task 1.6: Remove/qualify hardcoded claims

**Modify:** `frontend/app/page.tsx`, `frontend/lib/i18n.tsx`, pricing/dashboard/models pages.

Replace unsupported claims with verified registry data or neutral copy. Remove hardcoded signup gift until backend grant exists.

**Phase 1 Gate:** docs/schema/API/frontend all agree; contract tests pass; no forbidden claims; static model list absent from production paths.

---

## Phase 2 — Financial correctness before visual polish

### Task 2.1: Introduce money/value objects

**Create:** `backend/services/money.py`, tests.

Canonical integer IRT, explicit display conversion, rounding tests, negative/overflow validation.

### Task 2.2: Version pricing

**Modify:** migrations/schema, `backend/payment.py`, pricing admin routes.

Add provider, price version, effective dates, token categories, source. Preserve historical rows.

### Task 2.3: Reservation/settlement service

**Create:** `backend/services/billing.py`, tests.

Implement authorize → reserve → settle/release with row locks and idempotency. No upstream request without successful authorization.

### Task 2.4: Usage event schema

**Create:** migration and `backend/services/metering.py`.

Record request ID, model, price version, token categories, reservation, final charge, upstream status.

### Task 2.5: Payment callback hardening

**Modify:** `backend/payment.py`, callback route, tests.

Verify amount/order/authority, lock order, reject replay, atomically credit wallet and ledger. Add duplicate and concurrency tests.

### Task 2.6: Align UI pricing/wallet

**Modify:** `frontend/app/pricing/page.tsx`, `frontend/app/wallet/page.tsx`, `frontend/app/topup/page.tsx`, API routes.

Show canonical currency and exact source timestamp; remove unsupported subscription/gift promises.

**Phase 2 Gate:** financial invariants, duplicate callback, insufficient balance, upstream failure, cancellation and historical pricing tests pass.

---

## Phase 3 — Secure authentication and authorization

### Task 3.1: Server-side session cookies

**Modify:** `backend/app.py`/auth routes, `frontend/lib/auth.tsx`, Next API routes.

Migrate from localStorage bearer persistence to HttpOnly cookie session. Keep a time-limited migration path and revoke old tokens.

### Task 3.2: Admin session isolation

**Modify:** `admin/static/admin.js`, admin service, Compose.

Separate origin/session, CSRF protection, no browser-stored admin secret, audit admin actions.

### Task 3.3: API key lifecycle

**Modify:** API key route/UI and schemas.

Hash keys, scope, expiry, revoke, last-used, one-time reveal. Add tests.

### Task 3.4: Object ownership tests

**Create:** `backend/tests/test_ownership.py`, `test_auth_security.py`.

Two users cannot read/write each other’s conversations, wallet, ledger, keys, or usage.

**Gate:** no auth/admin secret in localStorage; security tests pass.

---

## Phase 4 — Design system and shell

### Task 4.1: Typed design tokens

**Create:** `frontend/design/tokens.ts`.

**Modify:** `frontend/app/globals.css`, Tailwind config.

Define spacing, surface, text, semantic colors, radius, motion, focus ring, typography.

### Task 4.2: UI primitives

**Create/standardize:** `frontend/components/ui/Icon.tsx`, `Button.tsx`, `Badge.tsx`, `Surface.tsx`, `Modal.tsx`, `Tooltip.tsx`, `Spinner.tsx`, `EmptyState.tsx`, `ErrorState.tsx`.

All icon-only buttons need labels and keyboard focus.

### Task 4.3: Shell/navigation

**Modify:** `frontend/components/AppShell.tsx`, `frontend/app/layout.tsx`.

Desktop collapsible sidebar; mobile bottom nav exactly Chat/Models/Wallet/More; command palette for secondary routes; separate admin shell; focus trap and scroll restoration.

**Gate:** keyboard, 360px mobile, 1440px desktop, RTL/LTR checks pass.

---

## Phase 5 — Landing and onboarding

**Create:** `frontend/components/landing/Hero.tsx`, `LiveModelDemo.tsx`, `UseCases.tsx`, `CostTransparency.tsx`, `TrustSection.tsx`, `FAQ.tsx`, `frontend/app/onboarding/page.tsx`, onboarding components.

**Modify:** `frontend/app/page.tsx`, `frontend/lib/auth.tsx`.

- One primary CTA.
- Live catalog-backed demo or explicit illustrative label.
- Goal → model recommendation → first prompt.
- No unsupported claims.

**Gate:** E2E visitor/signup/onboarding/first successful response; no claim scan violations.

---

## Phase 6 — Chat workspace

**Create:** `ConversationList.tsx`, `Composer.tsx`, `ModelPicker.tsx`, `CostPreview.tsx`, `StreamStatus.tsx`, `MessageActions.tsx`, `CodeBlock.tsx`.

**Modify:** `frontend/app/chat/page.tsx`, `frontend/components/Chat.tsx`, `frontend/lib/sse.ts`.

Implement optimistic messages, cancel/retry/reconnect, draft persistence, search, cost preview, usage, export/share privacy warning, code LTR isolation, shortcuts, offline state.

**Gate:** Playwright stream/cancel/retry/reconnect and accessibility tests.

---

## Phase 7 — Model browser

**Create:** `ModelCard.tsx`, `ModelFilters.tsx`, `ModelCompare.tsx`.

**Modify:** models/compare routes.

Filter task/budget/speed/context/provider; show verified pricing/availability/provenance; compare max three; deep-link to chat.

**Gate:** catalog contract tests and visual responsive checks.

---

## Phase 8 — Usage, wallet, developer experience

**Create:** usage/wallet/developer components and pages.

Show balance, reserved/promotional funds, daily/monthly cost, forecast, ledger filters, request ID and price version. Add curl/Python/JS quickstarts and request logs.

**Gate:** user ownership, payment/billing, API-key and developer E2E tests.

---

## Phase 9 — Backend modularization and observability

Incrementally extract:

```text
backend/app/{main,config,db}.py
backend/app/{routers,services,schemas,models,middleware}/
```

Add request ID, structured errors, latency, first-token latency, upstream error, model and payment events without secrets/content. Add `/health/live`, `/health/ready`, `/health/deep` (admin-only).

**Gate:** behavior unchanged under contract tests; no route regression.

---

## Phase 10 — Performance

- Self-host/subset Vazirmatn; no runtime Google font dependency.
- Dynamic import charts/admin/playground.
- Route-level providers.
- Add Lighthouse mobile and bundle analyzer scripts.
- Budget: LCP <2.5s, INP <200ms, CLS <0.1, landing JS <180KB gzip target.

**Gate:** recorded baseline and no regression beyond budget.

---

## Phase 11 — QA/release

**Create:** `frontend/tests/smoke.spec.ts`, `a11y.spec.ts`, `navigation.spec.ts`, `backend/tests/test_error_contract.py`, `test_payment_concurrency.py`, `test_migrations_real.py`, `test_ownership.py`.

Required scenarios:

- auth/session expiry/logout-all
- onboarding/first response
- stream/cancel/retry/reconnect
- cross-user ownership
- wallet reservation/settlement/refund
- duplicate/concurrent payment callback
- API key one-time reveal/revoke
- admin authorization
- mobile 360px/desktop 1440px
- RTL/LTR code
- keyboard/reduced motion
- fresh/existing DB migration

Release gate command:

```bash
set -e
cd /root/multiai/backend && pytest -q
cd /root/multiai/frontend && npm ci && npm run build
cd /root/multiai && ./scripts/smoke.sh
# Playwright and Lighthouse commands are added in their respective phases.
```

Every phase requires: focused tests, full regression, screenshots/traces for UI work, security review for auth/billing, and a rollback note.

---

## 3. Execution order and delegation rules

1. Phase 0 stabilization
2. Phase 1 contracts/claims/catalog
3. Phase 2 billing correctness
4. Phase 3 auth/security
5. Phase 4 design system/shell
6. Phase 5 landing/onboarding
7. Phase 6 chat
8. Phase 7 models
9. Phase 8 usage/developer
10. Phase 9 backend modularization/observability
11. Phase 10 performance
12. Phase 11 release

Implementation must use fresh workers per bite-sized task, then two reviews:

- spec compliance review
- code quality/security review

Do not start dependent phases while a blocking gate is red. Do not claim completion without real command output.

---


## 4. Status Tracker (updated 2026-07-11 19:30)

### Completed Sprints

| Sprint | Phase | Status | Commit |
|---|---|---|---|
| Sprint 1 | Phase 0 partial | DONE | `74aa1cb` |
| Sprint 2 | Phase 4 partial | DONE | `353dd7e` |
| Sprint 3 | Phase 6 | DONE | `3bb0761` |
| Sprint 4 | Phase 7 | DONE | `531258c` |
| Sprint 5-6 | Phase 8 partial (admin/dashboard/wallet UI) | DONE | `4c748df` |
| Build fix | TypeScript 5.5, standalone output, tailwind content | DONE | `4c748df` |

### Verified Current State (real audit)

- Backend: `/v1/models` endpoint exists, uses DB catalog + LiteLLM fallback
- `backend/services/money.py`: real implementation (76 lines)
- `backend/schemas/catalog.py`: real Pydantic schema (86 lines)
- `backend/schemas/content.py`: claim registry stub (37 lines)
- `frontend/types/catalog.ts`: TypeScript types (37 lines)
- `frontend/lib/claims.ts`: exists, used in landing
- Tests: 74 passed, 2 failed (test_admin pricing mock issue), 57 warnings
- Frontend: chat/models pages STILL use static MODELS list (not catalog API)

### Remaining Work Queue

| Order | Work Item | Maps To | Priority | Status |
|---|---|---|---|---|
| 1 | Fix 2 failing tests + classify warnings | Phase 0.1 | HIGH | TODO |
| 2 | Smoke script + real migration test | Phase 0.2, 0.3 | HIGH | TODO |
| 3 | Wire catalog endpoint to frontend (chat/models/compare) | Phase 1.5 | HIGH | TODO |
| 4 | Money object + versioned pricing + reservation/settlement + usage events | Phase 2 | HIGH | TODO |
| 5 | Server-side sessions + admin isolation + API key lifecycle + ownership tests | Phase 3 | HIGH | TODO |
| 6 | Onboarding page + flow completion | Phase 5 | MEDIUM | TODO |
| 7 | Backend modularization (routers/services/schemas) | Phase 9 | MEDIUM | TODO |
| 8 | Performance: self-host fonts, dynamic imports, Lighthouse | Phase 10 | MEDIUM | TODO |
| 9 | E2E tests (Playwright) + a11y + error contract | Phase 11 | HIGH | TODO |

### Execution Notes

- Items 1, 4, 5 are backend-heavy and can run in parallel subagents
- Items 3, 6, 8 are frontend-heavy
- Item 2, 9 are final QA gate
- Each item: TDD + independent review + real gate output
- All work inside `/root/multiai`; never touch `/root/multiapi`
