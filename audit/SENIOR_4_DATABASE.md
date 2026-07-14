# SENIOR 4 — Database & Migrations Audit

**Auditor**: Senior DB Engineer (Hermes Agent)
**Date**: 2026-07-14
**Database**: PostgreSQL — `multiai` (33 tables)
**ORM**: SQLAlchemy 2.0+ (async, mapped_column style) in `backend/app.py`

---

## 1. Migration Framework & Consistency

### Migration Runner
Custom SQL-based runner in `backend/migrate.py`. Reads `*.sql` files from `backend/db/migrations/`, tracks applied versions in `schema_migrations` table. Runs idempotently at app startup via `lifespan()`.

### Applied Migrations (in `schema_migrations`)
| Version | Applied At |
|---|---|
| 0001_baseline.sql | 2026-07-11 19:13:10 |
| 0002_claims_catalog.sql | 2026-07-11 19:13:10 |
| 0003_api_key_lifecycle.sql | 2026-07-11 19:13:10 |
| 0004_financial_core.sql | 2026-07-11 19:13:10 |
| 0005_pricing_system.sql | 2026-07-13 09:34:53 |
| 0006_memory_system.sql | 2026-07-13 14:54:39 |
| 0007_skills_marketplace.sql | 2026-07-13 15:07:55 |
| 0008_scheduled_tasks.sql | 2026-07-13 15:15:09 |

### Migration Files on Disk
| File | Status |
|---|---|
| `0009_ledger_idempotency.sql` | ⚠️ **NOT YET APPLIED** (not in schema_migrations) |
| `0010_org_default_model.sql` | ⚠️ **NOT YET APPLIED** |
| `0011_assistants.sql` | ⚠️ **NOT YET APPLIED** |

### 🔴 CRITICAL: Migration Files 0001–0008 Missing from Repo
The first 8 migrations (0001–0008) are recorded as applied in `schema_migrations` but **their `.sql` files do not exist** on disk. Only 0009–0011 exist in `/root/multiai/backend/db/migrations/`. This means:
- The baseline schema cannot be reproduced from the migration files alone.
- A fresh `docker-compose up` against an empty DB will fail (0001_baseline.sql missing).
- Disaster recovery requires the `backups/multiai-pre-migration-20260711_224005.dump` file.

**Recommendation**: Extract the baseline DDL from the existing DB (`pg_dump --schema-only`) and save as `0001_baseline.sql` (or similar) so the full migration chain is self-contained.

### Pending Migrations (0009–0011)
These 3 migrations will auto-apply on next app startup. They are safe (`IF NOT EXISTS` guards):
- **0009**: Adds `ledger.idempotency_key` column + partial unique index
- **0010**: Adds `proxy_config.default_model` column
- **0011**: Creates `assistants` table (but this table already exists in DB — the `IF NOT EXISTS` guard will skip it)

---

## 2. Schema vs ORM Model Mismatches

### Tables in DB Without ORM Models (accessed via raw SQL)
| Table | Notes |
|---|---|
| `about` | Singleton row (CHECK id=1). Empty. **Duplicate** of `about_content`. |
| `claims` | Marketing claims table. PK is `key` (text). No ORM model. |
| `model_catalog` | Model catalog with rich metadata. Accessed via raw `text()` SQL. |
| `payment_orders` | Payment order tracking. Accessed via raw SQL. |

### ORM Models in `app.py`
20 mapped classes: `User`, `Subscription`, `Ledger`, `Quota`, `ModelAlias`, `Pricing`, `Feature`, `Discount`, `AboutContent`, `ProxyConfig`, `Assistant`, `Conversation`, `Payment`, `Wallet`, `WalletReservation`, `UsageEvent`, `Notification`, `ApiKey`, `AuditLog`, `Plan`, `CreditPackage`, `UserBillingSetting`, `UserMemory`, `SkillTemplate`, `SkillTemplateRating`, `ScheduledTask`, `TaskExecution`.

### Column Type Mismatches
| Table | Column | ORM Type | DB Type | Risk |
|---|---|---|---|---|
| `conversations` | `id` | `Mapped[int]` (integer) | `bigint` | Low (auto-cast) |
| `conversations` | `user_id` | `Mapped[int]` (integer) | `bigint` | Low |
| `usage_events` | `id` | `Mapped[int]` (integer) | `bigint` | Low |
| `usage_events` | `user_id` | `Mapped[int]` (integer) | `bigint` | Low |
| `sessions` | `id` | N/A (no ORM) | `bigint` | N/A |
| `audit_logs` | `id` | `Mapped[int]` (integer) | `bigint` | Low |

The ORM uses `Mapped[int]` which maps to `INTEGER` (32-bit), but several tables were created with `BIGINT` (64-bit). This works at runtime due to PostgreSQL implicit casting but could cause overflow issues if IDs exceed 2^31 (~2.1B rows). For a user-facing app, this is acceptable.

### Duplicate Table: `about` vs `about_content`
- `about` table: EXISTS in DB, 0 rows, has CHECK constraint (id=1), **no ORM model**.
- `about_content` table: EXISTS in DB, 1 row, **has ORM model** (`AboutContent`).
- Both serve the same purpose. `about` appears to be a legacy table.

**Recommendation**: Drop the `about` table or migrate its data to `about_content` and drop it.

---

## 3. Index Analysis

### Missing Indexes (High Priority)

| Table | Column(s) | Why Needed | Impact |
|---|---|---|---|
| `conversations` | `(user_id, updated_at)` | Every conversation list query does `WHERE user_id = ? ORDER BY updated_at DESC`. Current index is `user_id` only — requires a filesort. | Medium |
| `audit_logs` | `(created_at)` | Time-range queries for audit trail. Only has PK index. | Medium |
| `audit_logs` | `(action)` | Filter by action type in admin views. | Low |
| `payments` | `(status)` | Filter payments by status (pending/verified/failed). | Low |

### Duplicate/Redundant Indexes

| Table | Redundant Index | Covered By |
|---|---|---|
| `ledger` | `ix_ledger_user_id` (user_id) | `idx_ledger_user` (user_id, created_at) — composite covers leading column |
| `api_keys` | `ix_api_keys_user_id` (user_id) | `idx_api_keys_user` (user_id) — exact duplicate |

**Recommendation**: Drop `ix_ledger_user_id` and one of the two `api_keys` user_id indexes to reduce write amplification.

### Well-Indexed Tables
- `users`: email (unique), phone (unique), telegram_id, referral_code (unique) ✅
- `sessions`: token_hash (unique + index), user_id ✅
- `usage_events`: request_id (unique), (user_id, created_at) composite ✅
- `wallet_reservations`: reservation_id (unique), idempotency_key (unique), user_id ✅
- `subscriptions`: (user_id, status) partial index WHERE active ✅

---

## 4. Foreign Key Analysis

### Missing Foreign Keys

| Table | Column | Should Reference | Severity |
|---|---|---|---|
| **`ledger`** | `user_id` | `users(id)` | 🔴 **HIGH** — No FK constraint. Orphaned ledger entries are possible. ORM model also lacks `ForeignKey()`. |
| **`audit_logs`** | `admin_user_id` | `users(id)` | 🟡 Medium — No FK. Admin user could be deleted leaving dangling reference. (Nullable, so less critical.) |
| **`usage_events`** | `subscription_id` | `subscriptions(id)` | 🟡 Medium — No FK. Column exists but no constraint. |

### Tables With Proper FKs (21 constraints total)
All other user_id columns have proper FK constraints with appropriate `ON DELETE` behavior:
- `CASCADE`: sessions, wallet, wallet_reservations, usage_events, user_memories, scheduled_tasks, task_executions, skill_template_ratings, user_billing_settings
- `NO ACTION` (default): api_keys, assistants, conversations, notifications, payment_orders, payments, quota, subscriptions, skill_templates

---

## 5. Orphaned Data Check

| Check | Result |
|---|---|
| Conversations without users | ✅ 0 orphans |
| Ledger entries without users | ✅ 0 orphans |
| Task executions without users | ✅ 0 orphans |
| Usage events without users | ✅ 0 orphans |

No orphaned data currently. However, the `ledger` table lacks a FK constraint, so orphaned entries could appear after user deletion.

---

## 6. Session Management: DB vs Redis

### Finding: `sessions` Table is UNUSED

The `sessions` table exists in the database with proper schema (id, user_id, token_hash, name, revoked, last_used_at, expires_at, created_at) and indexes, but has **0 rows**.

**All session management is done via Redis:**
- `_create_session()` (line 1702): Stores session as `session:{token}` key in Redis with TTL.
- `_get_session()` (line 1711): Reads from Redis `session:{token}` key.
- `_get_session_user_id()` (line 1739): Reads from Redis.
- Admin sessions: Stored as `admin_session:{sid}` in Redis.
- Rate limiting: `security.py` also reads Redis sessions for client identification.

The `sessions` table appears to be a planned but unused feature for persistent session storage (perhaps for session listing/revocation in admin UI). It has proper FK and indexes but no code writes to it.

**Recommendation**: Either:
1. Remove the `sessions` table if Redis sessions are sufficient, OR
2. Implement dual-write to `sessions` table for auditability/revocation capability.

---

## 7. N+1 Query Patterns & Inefficient Queries

### 🔴 HIGH: Wallet Balance Computed from Ledger SUM (3+ locations)

Instead of reading `wallet.balance`, the code computes balance via:
```sql
SELECT COALESCE(SUM(amount), 0) as balance FROM ledger WHERE user_id = :uid
```

This appears at lines **812, 1156, 1235** and likely more. This is an O(n) aggregation over the entire ledger for each user on every request. The `wallet` table already has a `balance` column with a CHECK constraint (`balance >= 0`).

**Impact**: As ledger grows, each balance check becomes slower. With 23 ledger entries now it's fine, but at scale this is a serious bottleneck.

**Recommendation**: Read `wallet.balance` directly; use ledger only for audit trail.

### 🟡 MEDIUM: Admin Users Listing — Correlated Subqueries

The `/admin/users` endpoint (line 3004) uses correlated subqueries:
```sql
SELECT u.*, 
  COALESCE((SELECT SUM(amount) FROM ledger WHERE user_id = u.id), 0) as balance,
  COALESCE((SELECT used_today FROM quota WHERE user_id = u.id), 0) as used_today
FROM users u ORDER BY u.created_at DESC LIMIT :limit OFFSET :offset
```

For a page of 50 users, this executes 100 additional subqueries. With proper indexes this is acceptable for small datasets, but at scale should use JOINs or CTEs.

### 🟡 MEDIUM: Conversation Search — Full JSON Scan in Python

The `/conversations/search` endpoint (line 2260) loads up to 200 conversations with full `messages` JSON into Python, then iterates through every message to search content:
```python
for r in all_rows:
    msgs = r.messages or []
    for msg in msgs:
        if q.lower() in (msg.get('content', '') or '').lower():
```

**Impact**: At scale, loading and parsing JSON blobs in Python is slow. PostgreSQL's `@>` and `jsonb_path_exists` operators could do this server-side.

### 🟢 LOW: No ORM-Level Eager Loading
The app uses raw `Table.select()` queries throughout rather than ORM relationships. This avoids N+1 from lazy loading but means no relationship-level optimizations exist. The pattern is consistent and acceptable.

---

## 8. Data Integrity Concerns

### Ledger Balance vs Wallet Table
The `wallet` table has `balance` and `reserved` columns with CHECK constraints, but the codebase ignores it for balance reads (uses SUM on ledger instead). If the `wallet.balance` is ever out of sync with `SUM(ledger.amount)`, there's no reconciliation mechanism.

### Conversations Store Messages as JSON
The `conversations.messages` column stores the entire message history as a JSON array. This means:
- No referential integrity on individual messages.
- Updating a single message requires rewriting the entire JSON blob.
- Search requires full JSON deserialization.
- No ability to paginate messages independently.

Current sizes are small (52–587 bytes per conversation), but this design won't scale.

### No Soft Deletes on Users
User deletion would cascade-delete sessions, wallet, etc. via FK constraints, but `ledger`, `conversations`, `payments`, `usage_events` use `NO ACTION` (default) FK, meaning user deletion would **fail** if those tables have rows for the user. This is a data integrity concern.

---

## 9. Table Size Summary

| Table | Rows | Size |
|---|---|---|
| ledger | 23 | 88 kB |
| usage_events | 17 | 64 kB |
| users | 16 | 16 kB |
| quota | 15 | 8 kB |
| model_catalog | 13 | 16 kB |
| pricing | 13 | 16 kB |
| audit_logs | 9 | 16 kB |
| conversations | 3 | 48 kB (JSON-heavy) |
| 25 other tables | 0–4 | 0–16 kB |

Database is very small. Performance issues are latent, not current.

---

## 10. Summary of Findings

### 🔴 Critical (3)
1. **Migration files 0001–0008 missing from repo** — baseline schema not reproducible from source.
2. **`ledger.user_id` has no FK constraint** — orphaned financial records possible.
3. **Wallet balance computed via SUM over ledger** instead of reading `wallet.balance` — O(n) per request, will degrade at scale.

### 🟡 Medium (6)
4. **`sessions` table exists but is unused** — dead schema, 0 rows, all auth via Redis.
5. **Duplicate tables**: `about` (empty, no ORM) vs `about_content` (has ORM).
6. **Missing index on `conversations(user_id, updated_at)`** — every list query does filesort.
7. **Missing index on `audit_logs(created_at)`** and `audit_logs(action)`.
8. **`audit_logs.admin_user_id` and `usage_events.subscription_id` have no FK constraints.**
9. **Redundant indexes**: `ix_ledger_user_id` (covered by composite) and duplicate `api_keys` user_id indexes.

### 🟢 Low (4)
10. **Conversation search loads JSON into Python** instead of using PostgreSQL JSON operators.
11. **Admin user listing uses correlated subqueries** instead of JOINs.
12. **Type mismatch**: ORM `int` vs DB `bigint` on several tables (works but imprecise).
13. **No soft deletes** — user deletion blocked by FK constraints on financial tables.

---

*End of audit. No files were modified.*
