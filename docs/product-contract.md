# Multiai Aurora — Product, Data, Billing and Security Contract

**Version:** 1.0
**Status:** Implementation baseline
**Owner:** Product + Platform + Finance + Security
**Scope:** `/root/multiai`

## 1. Scope and non-goals

Multiai is a Persian-first AI workspace that provides a unified chat experience, approved multi-provider model catalog, transparent pay-as-you-go usage, wallet/payment operations, and a developer API.

Current release includes:

- Consumer chat and model discovery
- Developer API keys and OpenAI-compatible API workflow
- Pay-as-you-go wallet and approved promotional credit
- Versioned model/pricing metadata

Current release does **not** promise:

- Team workspaces, shared budgets, SSO, invitations, or organization billing
- A guaranteed number of models/providers
- Guaranteed uptime, dedicated servers, VPN availability, or universal provider availability
- “No third-party processing” for prompts sent to upstream providers
- A signup gift unless a published grant record exists for that user
- Subscription plans unless quota/subscription APIs and tables are active

## 2. User segments

| Segment | Job | Activation | Success metric | Current access |
|---|---|---|---|---|
| Consumer | Chat, writing, translation, summary, analysis | First successful assistant response | First success under 90 seconds; cost understandable | Chat, approved catalog, wallet, profile |
| Developer | Integrate through API | First key + successful API request | Request succeeds with request ID and usage | API keys, Playground, catalog, logs |
| Team | Shared organizational usage | **Future/non-goal** until tenancy exists | N/A in current release | Not advertised or enabled |
| Anonymous visitor | Evaluate product | Catalog/landing visit | Understand value without unsupported claims | Read-only public content |

### Consumer rules

- Technical provider settings remain progressive disclosure.
- Cost is shown in canonical currency with an explicit unit.
- Promotional credit is distinct from paid balance.

### Developer rules

- API is versioned and OpenAI-compatible where documented.
- Every request receives a request ID.
- Errors use the structured error contract below.
- API keys are hashed at rest and shown only once.

### Team future contract

When implemented, tenant isolation is mandatory. Roles will be `owner`, `admin`, `billing_manager`, and `member`; all conversations, keys, usage, wallets, and logs must carry a tenant scope. Until then, team language must not appear as a supported feature claim.

## 3. Source of truth

| Domain | Canonical source | Client read path | Write path |
|---|---|---|---|
| Models | Approved catalog DB snapshot | `GET /catalog/models` | Admin catalog workflow |
| Prices | Versioned pricing rows | `GET /catalog/pricing` | Admin pricing workflow |
| Claims | Claim registry | `GET /content/claims` or build-safe copy | Reviewed content workflow |
| Wallet | Append-only ledger + reservations | `GET /wallet`, `GET /wallet/ledger` | Billing service only |
| Usage | Immutable usage events | `GET /usage` | Metering service |
| Sessions | Server-side session store | Cookie/session endpoints | Auth service |

Frontend must never be authoritative for models, prices, balances, quota, credits, claims, or permissions.

## 4. Claim policy

Every factual or numerical marketing claim must have:

```text
claim_key
copy_fa
copy_en
claim_type: fact | estimate | marketing | illustrative
source
verified_at
expires_at
owner
audience
feature_flag
fallback_copy
```

Rules:

1. Unsupported claims are removed or clearly labeled as illustrative/estimate.
2. Uptime claims require measurement source, time window, sample size, and expiry.
3. Model-count claims require a live catalog query.
4. Privacy claims must match actual upstream data processing.
5. Provider, VPN, dedicated-server, support, gift-credit, and “no sharing” claims require explicit evidence.
6. CI must reject forbidden literals in production copy unless they are registered and approved.

## 5. Model catalog contract

```ts
export type ModelCatalogItem = {
  id: string;
  providerModelId: string;
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

Rules:

- `id` is a stable Multiai identifier; upstream ID is separate.
- Prices are snapshots, never overwritten in place.
- Disabled or stale models are not offered to users.
- `last_verified_at` and provenance are visible to admin and available to clients where safe.
- Frontend production paths consume API data only. Demo fixtures must be explicit and labeled.

## 6. Money and currency

- Storage currency: integer `IRT` minor units.
- UI may display تومان, but must label it explicitly; conversion is never implicit.
- All monetary arithmetic is integer arithmetic with deterministic rounding.
- Every price has `price_version`, `effective_from`, optional `effective_to`, and source.
- Historical usage retains the price version used at authorization.

## 7. Wallet, credit and quota

Wallet fields are logically distinct:

```text
available_paid
reserved_paid
promotional_remaining
currency
```

Promotional credit includes `grant_id`, source, issued_at, expires_at, and remaining amount. It cannot silently become paid balance.

Current billing model: **pay-as-you-go + promotional credit**. Subscription plans are not active unless backed by a real subscription/quota contract.

Quota, if enabled, must define:

- token or money basis
- period and reset policy
- timezone (`Asia/Tehran` for local periods; timestamps UTC)
- carry-over/expiry
- hard vs soft limit
- behavior at limit

## 8. Usage, reservation and settlement

Before an upstream request:

1. Select model and price snapshot.
2. Estimate upper bound.
3. Authorize and reserve funds atomically.
4. Reject request if reservation fails.

After the response:

1. Record input/output/cached/reasoning tokens.
2. Calculate actual charge using the snapshot.
3. Settle actual amount.
4. Release unused reservation.

On upstream failure or cancellation, apply the documented deterministic release/refund policy. Tracking errors must not be silently swallowed; the request must surface a reconciliation state.

Usage event minimum fields:

```text
request_id
user_id
model_id
price_version
reservation_id
input_tokens
output_tokens
cached_tokens
reasoning_tokens
amount
currency
upstream_status
created_at
```

## 9. Ledger and payment invariants

Ledger is append-only. Minimum fields:

```text
event_id
idempotency_key
user_id
currency
amount
balance_after
source_type
source_id
actor_id
metadata_redacted
created_at
```

Invariants:

- `balance_after = previous_balance + amount`.
- A business event has at most one financial effect.
- Duplicate payment callbacks are no-ops after the first verified success.
- Callback verifies authority, amount, order state, and replay protection.
- Wallet, order, and ledger changes are one transaction with row locks.
- A user cannot read or mutate another user’s ledger or wallet.

## 10. API and error contract

Every response includes `X-Request-ID`. Structured errors:

```json
{
  "error": {
    "code": "wallet_insufficient_balance",
    "message": "موجودی کافی نیست",
    "request_id": "request-id",
    "details": {}
  }
}
```

Error messages must not expose provider credentials, SQL, internal topology, or raw upstream exceptions.

## 11. Authentication and API keys

- User sessions: server-side session + HttpOnly, Secure production cookie, SameSite policy, rotation and revoke/logout-all.
- No auth or admin secret in `localStorage`.
- Admin has a separate origin/session and CSRF protection.
- API keys are hashed at rest, shown once, scoped, revocable, and optionally expiring.
- `NEXT_PUBLIC_*` values are public configuration, never secrets.

## 12. Privacy and retention

- Prompts/responses are sensitive content.
- Do not log full content or secrets by default.
- Define retention, deletion, export, account closure, and redaction policies before enabling long-term history.
- Upstream provider processing must be disclosed accurately; do not claim zero third-party processing when requests leave Multiai.
- Admin actions and billing changes are auditable without storing secrets.

## 13. Localization and direction

- User-facing Persian is RTL.
- Model IDs, API keys, code, token counts, timestamps, request IDs, and monetary numbers use explicit LTR isolation where needed.
- Currency labels are never omitted.
- Dates sent over APIs are UTC ISO-8601; localized rendering is client-side.

## 14. Versioning and deprecation

- API contracts are versioned.
- Model IDs remain stable while upstream aliases may change.
- Pricing changes create new versions; historical events never mutate.
- Deprecated models expose deprecation and sunset dates before removal.

## 15. Acceptance invariants

- No request runs without successful reservation when billing is enabled.
- No duplicate callback creates duplicate credit.
- No static production model catalog or unsupported claim remains.
- Cross-user ownership tests pass.
- Fresh and existing database migrations are idempotent.
- Build, backend tests, contract tests, smoke tests, and accessibility checks are green.
