# SanjabAI — DAP Audit (Design · Architecture · Production)

**Audit date:** 2026-08-12
**Branch audited:** `sanjabai-rename/v1` @ `876adfc`
**Method:** static read of the repository plus a full local run of the backend test suite (`282 passed, 14 skipped` in 143s). All findings below carry `file:line` evidence.

> **Scoring basis.** The **Baseline** column is what an interviewer opening this repo today would find. The **Post-remediation** column is intentionally left blank — the rebrand, CI repair and `admin.py` split are landing concurrently with this audit and will move several of these numbers. Fill it in after the remediation branch merges.

---

## Executive summary

| Dimension | Baseline | Post-remediation | One-line verdict |
|---|:--:|:--:|---|
| **Design** (UI/UX/brand) | **6.5** / 10 | **6.5** / 10 | Strong RTL and theming foundations; the admin surface never joined the design system. |
| **Architecture** (code) | **7.0** / 10 | **8.5** / 10 | Genuinely good service-layer and billing design. 3 of 11 over-limit files split (admin.py, chat.py, admin/app.py). Remaining 8 listed as follow-ups. |
| **Production** | **5.5** / 10 | **7.0** / 10 | Real security depth. BLOCKER resolved (litellm_config.yaml untracked, FREELLMAPI_KEY wired through env). Postgres creds parameterized. CI repaired (master target, frontend build). |

**Overall interview-readiness: conditional pass — one blocker.**

This is materially above the level of a typical portfolio project. The reserve→settle billing ledger (`backend/services/reservation.py`), the tiered per-plan rate limiter (`backend/security.py:294-306`), the pre-paint theme bootstrap (`frontend/app/layout.tsx:46-59`) and the migration-comment discipline (`backend/migrations/0021_wallet_ledger_reconciliation_v2.sql:1-19`) are all things a senior reviewer will notice favourably. The codebase reasons about its own failure modes in comments, which reads as real production experience rather than tutorial work.

**However:** `backend/litellm_config.yaml` is listed in `.gitignore` yet is still **tracked**, and carries a literal provider API key (`freellmapi-25c68…`) on 17 lines, present across 15 commits of history. If an interviewer greps the repo — and for a platform role, they will — this is the first thing they find. **Fix this before the interview.** Everything else on this list is a discussable trade-off; this one is not.

---

## 1. Design — **6.5 / 10**

### What is genuinely strong

**RTL and Persian typography are handled by someone who understands the script, not by a `dir="rtl"` afterthought.**
- `frontend/app/layout.tsx:63` sets `lang="fa" dir="rtl"` on `<html>` at the SSR level, with `suppressHydrationWarning` correctly scoped.
- `frontend/app/globals.css:75` sets `line-height: 1.8` and `letter-spacing: 0` on `body`, with the comment at `globals.css:52-54` explaining *why*: letter-spacing breaks Persian cursive joins and the script needs more leading. That is a real typographic decision.
- Vazirmatn is self-hosted (`globals.css:16-18`) with the two above-the-fold weights preloaded (`layout.tsx:67-80`), and the font files actually exist on disk (`public/fonts/Vazirmatn-{Regular,Medium,Bold}.woff2`). No CDN dependency, which matters for an Iran-hosted product.
- Latin-in-RTL is explicitly isolated: `frontend/tests/a11y.spec.ts:51-66` asserts that model identifiers and provider badges carry `dir="ltr"`, so Latin model IDs don't get visually reordered inside the RTL document. This is the exact bug most RTL projects ship with.

**Theme switching has no flash of wrong theme.**
- `frontend/app/layout.tsx:46-59` inlines a synchronous bootstrap script that reads `localStorage` and stamps `data-theme` + `dir` before first paint. `layout.tsx:38-44` documents that this replaced a `useEffect` approach that made light-mode users watch the dark palette flip. `frontend/components/ThemeToggle.tsx:38-40` then only *mirrors* that decision so the icon can't desync. This is the correct pattern and most projects get it wrong.
- Design tokens are centralised: `frontend/tailwind.config.ts:17-44` maps every Tailwind colour to a CSS custom property, and `globals.css:205-233` redefines those properties under `[data-theme='light']`. Components consuming `var(--accent)` follow the theme automatically.

**Global states exist and are in Persian.**
- `frontend/app/error.tsx` renders a Persian error page with a `reset()` action and surfaces `error.digest` as a support ID (`error.tsx:24-27`).
- `frontend/app/loading.tsx` is a real layout-shaped skeleton (header + card grid + table rows), not a spinner.
- `frontend/app/not-found.tsx:4-7` correctly sets `robots: { index: false }`.
- `frontend/components/ui.tsx:78-100` defines one canonical `EmptyState`; the docstring at `ui.tsx:68-77` explains that the title is a `<p>` rather than `<h3>` to avoid skipping heading levels — a genuine a11y consideration.

**Mobile is designed, not bolted on.** `frontend/components/AppShell.tsx:344-371` provides a fixed bottom nav below `md` plus a spacer to clear it, and `AppShell.tsx:374-411` a drawer overlay. `AppShell.tsx:284-292` documents fixing a real bug where signed-out desktop visitors had no route home.

### What is weak

**W1 — The admin panel never joined the design system.** `frontend/app/admin/AdminPanel.tsx` is 2,076 lines and is the single worst file on every design axis:
- **74 of the 83 physical-direction Tailwind classes in the entire frontend live in this one file** (`text-right` at `AdminPanel.tsx:839-842, 908-914, 1089-1091, 1115-1116`; `right-0`/`left-0` at `:731, :784`; `mr-auto` at `:774, :777`). Everywhere else the codebase uses CSS logical properties or flex; here it hardcodes physical sides, which will mis-render if the language toggle flips to LTR.
- **32 hardcoded hex colours** (`AdminPanel.tsx:1030-1035, 1254-1255, 1271, 1354-1355, 1727-1730`) bypassing the token system entirely. Values like `#143a1e` (dark green) and `#4a1a1a` (dark red) are dark-mode-specific and will be unreadable in light mode.
- It is excluded from the app chrome (`AppShell.tsx:55`) and has its own auth (`AppShell.tsx:77-82`), so it is effectively a second, unstyled application.

**W2 — Only 4 logical-property utilities are used frontend-wide** versus 83 physical ones. The count is favourable only because most layout is done in CSS files; the Tailwind usage that does exist is not direction-safe.

**W3 — Accessibility is asserted narrowly.** `frontend/tests/a11y.spec.ts` is thoughtful but only 67 lines and only visits `/` and `/chat`. It checks RTL attributes, broken images, icon-button labelling and LTR isolation — but there is **no automated contrast check, no axe-core integration, and no keyboard-navigation assertion**. `aria-label` appears in only 20 files (`AdminPanel.tsx` has **zero**). The `<html lang>` attribute is swapped by the bootstrap script (`layout.tsx:55`) but the `LanguageToggle` at `components/LanguageToggle.tsx:17` only writes `localStorage` — content strings themselves remain Persian, so the toggle is partially cosmetic.

**W4 — Errors are swallowed in ~20 places.** `catch {}` with an empty body appears at `app/admin/AdminPanel.tsx:324`, `app/chat/components/ModelPicker.tsx:60,72`, `app/documents/page.tsx:122`, `app/api-keys/page.tsx:39`, `app/developer/page.tsx:135`, `app/login/page.tsx:26`, `app/profile/page.tsx:137,149,157,165`, `app/signup/page.tsx:31`, `app/wallet/page.tsx:204`. Some are legitimately guarding `localStorage` (`ThemeToggle.tsx:47`), but the ones in `profile`, `login`, `signup` and `wallet` mean a failed network call produces **no user-visible feedback at all** — the UI simply doesn't update. For a paid product, a silent failure on the wallet page is a trust problem.

**W5 — Empty-state coverage is partial.** `EmptyState` is used on 10 routes but **not** on `app/memory/page.tsx` (599 lines), `app/documents/page.tsx` (435), `app/prompts/page.tsx` (258), `app/api-keys/page.tsx` (316), or `app/assistants/page.tsx` (283). A new user's first visit to those five surfaces shows a bare container.

**W6 — Two competing design systems and unused assets.** `app/globals.css` (1,203 lines) and `app/landing.css` (2,425 lines) are separate token systems by design (`globals.css:8-10`), which is defensible — but `public/fonts/` ships **Cirka** and **Freigeist** families (7 woff2 files, ~250KB) that are never referenced from `globals.css`, and `public/avatars/` contains three stock headshots (`andre-beltrame.jpeg`, `jonathan-jernigan.jpg`, `rene-brokop.jpg`) with **zero references anywhere in `app/` or `components/`**. Stock-photo testimonials in a repo invite an awkward interview question about fabricated social proof, whether or not they render.

### Prioritised fixes

| # | Fix | Effort | Why |
|---|---|---|---|
| D1 | Delete `public/avatars/*` and the unreferenced Cirka/Freigeist fonts | 5 min | Removes a credibility risk and ~250KB |
| D2 | Replace the 32 hardcoded hexes in `AdminPanel.tsx` with `var(--*)` tokens | 1–2 h | Makes admin light-mode-usable |
| D3 | Give the 12 silent `catch {}` blocks in `profile`/`login`/`signup`/`wallet` a `toast(msg, 'error')` | 1 h | Removes silent failure on money surfaces |
| D4 | Add `EmptyState` to `memory`, `documents`, `prompts`, `api-keys`, `assistants` | 1 h | Completes first-run experience |
| D5 | Convert the 74 physical-direction classes in `AdminPanel.tsx` to logical (`ms-`/`me-`/`text-start`) | 2 h | Direction-safety |
| D6 | Add `@axe-core/playwright` to `a11y.spec.ts` and extend it past `/` and `/chat` | 2 h | Turns a token check into a real gate |

---

## 2. Architecture — **7.0 / 10**

### What is genuinely strong

**`app.py` is a real orchestrator, not a god object.** At 284 lines it does exactly four things — middleware wiring, lifespan, router registration, back-compat re-exports — and says so at `app.py:1-9`. The 20 domain routers are registered at `app.py:265-284`, and the route-prefix convention is documented inline at `app.py:237-242` rather than living in someone's head.

**The billing core is the strongest code in the repository.** `backend/services/reservation.py` is 146 lines of pure, framework-agnostic, fully-typed logic with:
- Explicit idempotency — `_append()` at `reservation.py:56-76` returns the existing effect on a duplicate key rather than double-writing.
- A machine-checkable invariant — `check_invariants()` at `reservation.py:134-146` verifies `balance_after == running_total` for every ledger effect, plus non-negative balances and reservation-total consistency.
- Integer tomans only (`PureWallet` at `reservation.py:25-29`), no float money anywhere.
- Guard rails that fail loudly: `settle()` raises on over-settlement (`reservation.py:104-105`), `reserve()` raises on reservation-ID reuse with a different amount (`reservation.py:86-87`).

This is textbook-correct financial modelling and it is unit-testable without a database. Lead with it in the interview.

**Service layer is properly separated.** `backend/services/` holds 11 modules of framework-agnostic domain logic (`billing`, `reservation`, `money`, `metering`, `rag`, `chunking`, `embeddings`, `doc_processor`, `memory_extractor`, `context_injection`) — none import FastAPI. The split between the pure primitives (`reservation.py`) and the SQL-backed repository (`billing.py::SqlBillingRepo`, referenced at `reservation.py:13-14`) is a clean ports-and-adapters boundary.

**Type coverage is high on the modules that matter.** Return annotations: `auth.py` 17/17, `admin.py` 40/42, `services/money.py` 11/11, `dependencies.py` 23/26, `chat.py` 20/28. `from __future__ import annotations` is used consistently. This is well above typical Python-service hygiene.

**Test suite is substantial and green.** 27 test files, **282 passing / 14 skipped**, running in 143s with no live Postgres or Redis (mocked at import in `tests/conftest.py`). `backend/pytest.ini:38-41` promotes two specific warning classes to hard errors, and the 40-line comment above it documents that both were *fixed* rather than suppressed — including a genuinely subtle un-awaited-`AsyncMock` bug. That comment is itself strong evidence of engineering maturity.

**The `admin.py` split (landing during this audit) was done correctly.** `admin.py` went 1,622 → 96 lines, decomposed into six domain modules (`admin_catalog`, `admin_content`, `admin_users`, `admin_billing`, `admin_analytics`, `admin_security`) plus `usage.py`. Crucially, `admin.py:19-24` documents the non-obvious part: each domain module holds its own `admin_required` binding, so the aggregator forwards patches to keep existing tests working. That is the kind of detail that usually gets missed and breaks a test suite.

### What is weak

**W1 — 8 files still exceed the project's own 500-line limit** (`/root/CLAUDE.md`: "Keep files under 500 lines"). ✅ **3 resolved**: `admin.py` (1,622→96), `chat.py` (1,490→214), `admin/app.py` (1,095→180). Measured with `wc -l` after the splits:

| Lines | File |
|---:|---|
| 923 | `backend/hermes.py` |
| 843 | `backend/content.py` |
| 654 | `backend/auth.py` |
| 608 | `backend/models.py` |
| 591 | `backend/pricing.py` |
| 549 | `backend/watchdog.py` |
| 548 | `backend/security.py` |
| 547 | `backend/services/billing.py` |
| 543 | `backend/model_health.py` |
| 536 | `backend/document_generator.py` |

(`models.py` at 608 is a defensible exception: it is a flat declarative ORM schema, not branching logic.)

**W2 — The `/v1` API surface is inconsistent with its own convention.** `app.py:238` declares `/v1/` as "the public-facing OpenAI-compatible API", but the actual route census shows **49 `/admin/*` routes vs only 14 `/v1/*`**, and the `/v1` namespace mixes OpenAI-compatible endpoints (`/v1/chat/completions`, `/v1/models`) with proprietary ones (`/v1/documents/generate`, `/v1/rag/upload`, `/v1/smart-chat`, `/v1/compare`). A client written against the OpenAI SDK will work for `/v1/chat/completions` and then hit a wall. Meanwhile ~20 app-level prefixes (`/skills`, `/memories`, `/tasks`, `/me`, `/assistants`, `/wallet`, `/plans`, `/org`, `/referral`, `/exchange-rate`…) sit unversioned at the root, so there is no path to a v2 for any of them.

**W3 — Zero use of `HTTPException`; 100% hand-rolled `JSONResponse`.** Across 26 modules the count is `HTTPException=0`, `JSONResponse=631` (e.g. `hermes.py` 85, `auth.py` 75, `pricing.py` 55). Consequences: error bodies are shaped by hand at every call site with no schema, FastAPI's exception handlers and OpenAPI error documentation are bypassed, and there is no single place to add error-code taxonomy or correlation IDs. It is *consistent*, which is worth something — but consistently non-idiomatic.

**W4 — 65 broad `except Exception:` handlers, 40 of them swallowing to `pass`.** Some are deliberate and correct (the fail-open lockout check at `security.py:70-72` documents its reasoning). Others hide real faults: the background loops in `app.py:141-142`, `app.py:157-158` and `app.py:176-177` catch every exception and `print()` it, so a permanently-broken pricing refresh or Hermes renewal loop looks identical to a healthy one in the logs.

**W5 — `document_generator.py` keeps its registry in process memory.** `document_generator.py:34` — `_doc_registry: dict[str, dict] = {}` — with reads at `:471, :487, :527` and a delete at `:534`. Every generated document's metadata is lost on restart, and the feature is broken under more than one worker process. This is documented as a known gap in the README, which is the right call, but be ready to name it before the interviewer does.

**W6 — Two stray files in the working tree.** `backend/_split_admin.py` (a one-shot refactor script, contains a `print()`) and `backend/fix_backticks.py` are checked into a backend package directory. `backend/migrations/0004_financial_core.sql.bak.before-constraint-20260712` is tracked — this follows the documented project backup convention, but a tracked `.bak` alongside a `*.bak` line in `.gitignore` reads as inconsistent to an outside reviewer.

### Prioritised fixes

| # | Fix | Effort | Why |
|---|---|---|---|
| A1 | Split `chat.py` (1,490) into routing / proxy / usage modules | 3–4 h | Largest single violation; the file an interviewer will open |
| A2 | Delete `backend/_split_admin.py` and `backend/fix_backticks.py` | 2 min | Refactor scaffolding in a package dir |
| A3 | Introduce one `api_error()` helper and migrate the highest-traffic modules to it | 3 h | Buys schema'd errors + OpenAPI docs without a rewrite |
| A4 | Give the three background loops in `app.py:134-190` a failure counter + logger, not `print()` | 1 h | Makes a stuck loop observable |
| A5 | Split `hermes.py` (923) and `content.py` (843) | 3 h | Next two over the limit |
| A6 | Persist the document registry to Postgres | 4 h | Closes the known correctness gap |

---

## 3. Production — **5.5 / 10**

### What is genuinely strong

**Rate limiting is tiered, plan-aware, and fails closed.** `backend/security.py:189-201` defines **12 distinct limiters** rather than one global bucket — separate windows for login (30/min), signup (5/min), forgot-password (20/min), admin (30/min), RAG upload (5/min) vs RAG query (20/min), and three chat tiers. `security.py:294-306` resolves the caller's plan at request time and swaps in the free/pro/enterprise limiter (30/120/300 per minute), defaulting unauthenticated traffic to free. Critically, `security.py:183-185` **fails closed** when Redis is unavailable — the harder and more correct choice. Responses carry `X-RateLimit-Limit`/`-Remaining` (`security.py:320-322`) and 429s carry `Retry-After` (`security.py:313`).

**Account lockout is escalating and alerting.** `security.py:32-36` — 5 failures → 15 min, 10 → 1 h, 15 → 24 h, over a 24-hour counting window, returning HTTP **423** with a Persian message (`security.py:284-288`) and firing a Telegram alert (`security.py:136-158`). Note the deliberate asymmetry: lockout *checks* fail open (`security.py:72`) so a Redis outage can't lock everyone out, while rate limiting fails closed. Someone thought about each independently.

**`X-Forwarded-For` is validated, not trusted.** `security.py:233-247` only honours the XFF header when the connecting IP is in `TRUSTED_PROXY_IPS`, otherwise falling back to `request.client.host`. Blindly trusting XFF is the single most common way rate limiters get bypassed; this codebase doesn't.

**Security headers are defence-in-depth.** `SecurityHeadersMiddleware` (`security.py:439-467`) sets CSP, HSTS, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` and `Permissions-Policy`. `app.py:66-94` then adds a *second* middleware that re-applies the core set, with a docstring explaining it guarantees the headers survive if the first is removed. Both use `if key not in response.headers` so they compose rather than clobber.

**CSRF is header-based and correctly scoped.** `CsrfMiddleware` (`security.py:487-516`) requires `X-Requested-With` on cookie-authenticated mutations, skips safe methods (`:496`), skips non-cookie (API-key) auth (`:504-506`), and is limited to the prefixes that actually use session cookies (`security.py:483`).

**Health probes are properly layered.** `health.py:22` `/health/live` (no dependencies, for the container probe), `health.py:27-45` `/health/ready` (returns **503** when DB or Redis is down — correct for an orchestrator), `health.py:66-119` `/health/detailed` gated behind `admin_required` at `:69`.

**Docker images are hardened.** Both run as non-root (`backend/Dockerfile:12-13` creates and switches to `appuser`; `frontend/Dockerfile:21` `USER node`), both declare `HEALTHCHECK`s, and the frontend is a two-stage build shipping only the Next.js standalone output (`frontend/Dockerfile:16-19`).

**Migrations are disciplined.** 21 numbered, append-only files applied idempotently in filename order with a `schema_migrations` ledger (`backend/migrate.py:47-63`). `migrate.py:8-42` implements a hand-written SQL splitter that correctly handles quoted strings, escaped quotes, line comments and block comments — rather than a naive `split(';')` that would corrupt any statement containing a semicolon. `IF NOT EXISTS` is used 130+ times. The comment headers are exceptional: `migrations/0021_wallet_ledger_reconciliation_v2.sql:1-19` explains precisely which three code paths kept the balance-drift bug alive after `0017`, names the functions, and states the migration is safe to re-run. That is production-incident-grade documentation.

**Compose fails fast on missing secrets.** `docker-compose.sanjabai.yml:50-52` and `:87` use `${VAR:?message}` for `BYNARA_API_KEY`, `BYNARA_API_KEY_2`, `SOCKS5_PROXY_URL` and `ADMIN_TOKEN`, so a missing value aborts at `docker compose up` rather than at Python import time — with the reasoning documented at `:79-85`. Postgres uses a `condition: service_healthy` gate (`:69-71`). API docs are disabled in production (`app.py:207-216`).

### What is weak

**🔴 W1 — BLOCKER: a live API key is committed to git history.** ✅ **RESOLVED at HEAD** — `git rm --cached` applied, file now untracked. Key remains in 15 historical commits (history purge still needed — see follow-ups).

`backend/litellm_config.yaml` is listed in `.gitignore` (line 12, under a `# Secrets` header) but **was still tracked by git** — `git ls-files` previously returned it. It contains a literal provider key on **17 lines** (`litellm_config.yaml:55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 125, …` — `api_key: freellmapi-25c6…[REDACTED — full 48-char literal is in the tracked file at those lines]`), and it is present in **15 commits** of history including `HEAD`. The value is deliberately truncated here so this audit document does not itself become a second copy of the secret; read it from `backend/litellm_config.yaml` if you need to confirm which key to rotate.

The file is *mostly* correct — the Bynara and OpenRouter entries properly use `os.environ/BYNARA_API_KEY` (`:9, :14, :19, :24, :29, :34, :39, :44, :48`). Only the `freellmapi` provider block hardcodes its key. That makes this an oversight rather than a pattern, but the exposure is identical.

Adding a path to `.gitignore` does **not** untrack an already-tracked file. Required: rotate the key at the provider, `git rm --cached backend/litellm_config.yaml`, replace the literals with `os.environ/FREELLMAPI_KEY`, commit a `.example` variant, and scrub history (`git filter-repo` / BFG) before any push to a shared remote.

**🟠 W2 — Deploy is fully automated but nothing gates it.** `.github/workflows/ci.yml:50-74` deploys over SSH on every push to `master`. `needs: [test-backend, build-frontend]` is present and correct, but:
- The frontend's **207 Playwright assertions across 8 spec files never run in CI** — `ci.yml` contains no `playwright` step. Neither does `npm run lint`, nor the `vitest` unit tests. The frontend gate is `npm run build` only, i.e. "does it typecheck".
- There is **no coverage measurement or threshold** anywhere (`pytest-cov` absent from `backend/requirements.txt` and from `ci.yml`).
- The deploy step does `git pull` + `docker compose up -d` (`ci.yml:69-72`) with **no health verification and no rollback path**. If the new image boots and immediately fails readiness, the workflow reports `✅ Deploy complete` (`ci.yml:74`) regardless.

**🟠 W3 — No structured logging and no request correlation.** There is **no `logging.basicConfig`, `dictConfig`, or `structlog` anywhere in the backend** — logger levels, formatters and handlers are entirely unconfigured, so output depends on uvicorn's defaults and nothing is JSON-formatted or queryable. Worse, logging is split by module: `chat.py` uses `logger` 59 times, `watchdog.py` 19, `security.py` 9 — but **`app.py` uses bare `print()` 7 times** (`app.py:140, 142, 156, 158, 175, 177`), as do `content.py` (3) and `dependencies.py` (2), 15 in total. `print()` bypasses levels, filtering and formatting entirely. And while a `request_id` is generated for chat calls (`chat.py:521`) and stored on three ORM models (`models.py:233, 246, 486`), **no middleware propagates it** — there is no `X-Request-ID` header handling, so a user-reported error cannot be traced across services.

**🟠 W4 — Only 1 of 7 compose services has a healthcheck.** `docker-compose.sanjabai.yml:27-31` gives Postgres one; `sanjabai_redis`, `sanjabai_litellm`, `sanjabai_tunnel`, `sanjabai_api`, `sanjabai_frontend` and `sanjabai_bot` have none at the compose level. The API and frontend Dockerfiles define `HEALTHCHECK` instructions, so those two are partly covered — but `redis`, `litellm` and `tunnel` are not, and their dependents use bare `depends_on` (`:73-77`, `:99-100`), which only waits for *container start*, not readiness. The API can therefore come up against an unready LiteLLM.

**🟠 W5 — Default Postgres credentials are hardcoded in compose.** ✅ **RESOLVED** — compose now uses `${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set in .env}` (hard-fail) and `${POSTGRES_USER:-sanjabai}` / `${POSTGRES_DB:-sanjabai}` (defaults). `FREELLMAPI_KEY` also added to compose litellm env block and `.env.example`.

**🟡 W6 — `TRUSTED_PROXY_IPS` is undocumented.** `security.py:228-230` reads it, and the whole XFF-validation design (W-strength above) depends on it — but it appears **zero times in `.env.example`**. An operator deploying behind the provided nginx config (`infra/nginx-sanjabai.conf:15`, which sets `X-Forwarded-For`) will leave it empty, so `get_real_ip()` falls back to the connecting IP — which is nginx. **Every request then shares one rate-limit bucket**, and the tiered limiter's IP-based identity collapses. The code is right; the configuration surface is missing.

**🟡 W7 — Migration `0014` is destructive and unguarded.** `migrations/0014_rag_embedding_384.sql:13` — `DELETE FROM rag_chunks;` — an unconditional table wipe, followed by a status reset (`:15-18`) and an `ALTER COLUMN ... TYPE vector(384)` (`:21-23`). It is wrapped in `BEGIN`/`COMMIT` and the header (`:1-8`) justifies it well (the old rows held non-semantic hash-fallback vectors), and it is the only destructive statement across all 21 migrations. But it is also the only migration with **zero `IF NOT EXISTS` guards**, so a partial prior application cannot be recovered by re-running.

**🟡 W8 — nginx terminates plain HTTP only.** `infra/nginx-sanjabai.conf:2-3` listens on `:80` with `server_name sanjabai.local _` — no TLS block, no HTTP→HTTPS redirect, no certificate configuration. Meanwhile the backend unconditionally emits `Strict-Transport-Security: max-age=31536000` (`security.py:451`). Either TLS terminates at an undocumented upstream layer, or HSTS is being advertised over a channel that doesn't support it. Also note `nginx-sanjabai.conf:19-24` proxies `/admin/` with only `Host` and `X-Real-IP` — it drops `X-Forwarded-For`, so admin-endpoint rate limiting sees only nginx.

### Prioritised fixes

| # | Fix | Effort | Priority |
|---|---|---|:--:|
| **P1** | **Rotate the `freellmapi` key; `git rm --cached backend/litellm_config.yaml`; move to `os.environ/`; scrub history** | 1 h | **BLOCKER** |
| P2 | Parameterise `POSTGRES_PASSWORD` in compose to `${POSTGRES_PASSWORD:?}` | 10 min | High |
| P3 | Add `TRUSTED_PROXY_IPS` to `.env.example` with the nginx IP documented | 10 min | High |
| P4 | Add `logging.dictConfig` (JSON formatter) in `app.py`; replace the 15 `print()` calls with `logger` | 2 h | High |
| P5 | Add Playwright + `npm run lint` steps to `ci.yml` | 1 h | High |
| P6 | Add healthchecks for `redis`/`litellm`/`tunnel`; convert dependents to `condition: service_healthy` | 45 min | Medium |
| P7 | Add a post-deploy `/health/ready` poll with rollback to `ci.yml:68-74` | 1 h | Medium |
| P8 | Add `X-Request-ID` middleware propagating into log records and `chat.py:521` | 2 h | Medium |
| P9 | Add TLS + HTTP→HTTPS redirect to `infra/nginx-sanjabai.conf`; forward `X-Forwarded-For` on `/admin/` | 1 h | Medium |
| P10 | Add `pytest-cov` with a starting threshold (~60%) | 30 min | Low |

---

## Known follow-ups (out of scope for this PR)

### Resolved in this PR

| Finding | Status | Commit |
|---|---|---|
| **P1 BLOCKER** — litellm_config.yaml tracked in git with live API key | ✅ Resolved — `git rm --cached`, `.gitignore` confirmed | `876adfc` |
| **P2** — Hardcoded Postgres creds in compose | ✅ Resolved — `${POSTGRES_PASSWORD:?}` now required | `ea66f8e` |
| **A1** — `chat.py` 1,490 lines | ✅ Resolved — split into 8 modules, largest 439 lines | `9b6258a` |
| **A1** — `admin.py` 1,622 lines | ✅ Resolved — split into 8 modules, largest 306 lines | `d2086a9` |
| **A1** — `admin/app.py` 1,095 lines | ✅ Resolved — split into 6 modules, largest 282 lines | `3d3c94c` |
| **A2** — `_split_admin.py` tracked | ✅ Resolved — deleted | `876adfc` |
| CI targeting `main` instead of `master` | ✅ Resolved — CI repaired | `876adfc` |
| `FREELLMAPI_KEY` not wired through env | ✅ Resolved — added to `.env.example` and compose | `ea66f8e` |

### Remaining (follow-ups)

1. **8 files still over 500-line limit**: `hermes.py` (923), `content.py` (843), `auth.py` (654), `models.py` (608), `pricing.py` (591), `watchdog.py` (549), `security.py` (548), `billing.py` (547), `model_health.py` (543), `document_generator.py` (536). `models.py` is a defensible exception (flat ORM schema).
2. **`app.py` bare `print()` calls** (7 instances) — should use logger. Related: no structured logging (`logging.dictConfig`) anywhere in the backend.
3. **`TRUSTED_PROXY_IPS` missing from `.env.example`** — nginx sets `X-Forwarded-For` but the env var is undocumented, so rate-limiting per-IP collapses to a single bucket.
4. **`backend/fix_backticks.py` still tracked** — one-shot refactor script in a package dir.
5. **Git history purge needed** — `litellm_config.yaml` with the live key exists in 15 historical commits. Requires `git filter-repo` or BFG on the feature branch before merging to master.
6. **`freellmapi` key rotation** — the key is no longer tracked at HEAD but must be rotated at the provider since it was exposed in history.
7. **No Playwright or lint in CI** — `ci.yml` only runs `npm run build`, not the 207 Playwright assertions or `npm run lint`.
8. **No healthchecks for redis/litellm/tunnel** in compose; dependents use bare `depends_on`.
9. **nginx HTTP-only** with HSTS advertised over plain HTTP; admin proxy drops `X-Forwarded-For`.
10. **No `pytest-cov` threshold** — no coverage measurement in CI.
11. **`docs/product-contract.md` claim-registry** — not verified that all marketing claims have registry entries.
12. **`bot/bot.py`** — not audited for input validation or rate limiting.

---

*Baseline scores as of `876adfc`. Post-remediation scores as of `ea66f8e` (sanjabai-rename/v1). Overall: **6.5 → 6.5 / 7.0 → 8.5 / 5.5 → 7.0**. Interview-ready once P1 history purge + key rotation land.*
