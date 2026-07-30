# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Multiai is a Persian-first AI agent platform: a FastAPI backend gateway to AI models (via a self-hosted LiteLLM proxy in front of the "Bynara" provider), a Next.js 15 frontend (RTL Persian UI), a separate admin panel, and a Telegram bot. It provides chat/completions, conversation + assistant + skill + memory management, RAG over user documents, a document generator (PPTX/DOCX/Markdown), wallet/billing with a reservation-and-settle pattern, and subscriptions.

Services (see `docker-compose.multiai.yml`): `multiai_pg` (Postgres 16 + pgvector), `multiai_redis`, `multiai_litellm` (LiteLLM proxy, egresses through `multiai_tunnel` SOCKS5), `multiai_api` (FastAPI backend, port 8001→8000), `multiai_frontend` (Next.js, port 3003→3000), `multiai_bot` (Telegram bot). There is also a standalone `admin/` FastAPI app (separate from `multiai_api`'s built-in `/admin/*` routes) and `infra/` (nginx + tunnel).

## Commands

### Backend (`backend/`, Python 3.11)

```bash
pip install -r backend/requirements.txt

# Run the API locally (expects DATABASE_URL/REDIS_URL/LITELLM_HOST env vars, see below)
cd backend && uvicorn app:app --reload --port 8000

# Run the full test suite
cd backend && python -m pytest tests/ -v --tb=short

# Run a single test file / test
cd backend && python -m pytest tests/test_wallet.py -v
cd backend && python -m pytest tests/test_wallet.py::test_name -v

# Apply SQL migrations manually (also runs automatically on API startup via lifespan)
cd backend && python migrate.py
```

Tests mock Redis/asyncpg/`migrate` at import time in `tests/conftest.py` and drive the app through a `starlette.testclient.TestClient` subclass — no live Postgres/Redis is needed to run `pytest`. `pytest.ini` promotes two specific warning classes (the deprecated httpx `app=` shortcut, and un-awaited `AsyncMock` coroutines) to hard errors, so don't reintroduce either pattern in fixtures.

### Frontend (`frontend/`, Next.js 15 / React 18 / TypeScript)

```bash
cd frontend && npm ci
npm run dev        # dev server on :3003 (see playwright.config.ts baseURL)
npm run build       # next build (standalone output)
npm run lint         # next lint
npm run analyze      # ANALYZE=true next build, opens bundle treemap

# E2E tests (Playwright) — specs mock /api/* via page.route, no live backend needed
npx playwright test
npx playwright test tests/wallet.spec.ts
```

`vitest` is a devDependency (used for `frontend/tests/lib/*.test.ts` unit tests) but there is no `npm test` script defined yet — invoke it directly with `npx vitest run` if needed.

### Full stack (Docker)

```bash
cp .env.example .env   # fill in BYNARA_API_KEY, SOCKS5_PROXY_URL, ADMIN_TOKEN, etc.
docker compose -f docker-compose.multiai.yml up -d
# Frontend: http://localhost:3003  API: http://localhost:8001  Health: /health
```

CI (`.github/workflows/ci.yml`) runs `pytest tests/` for the backend and `npm run build` for the frontend on every push/PR to `main`, then deploys over SSH on push to `main`.

## Architecture

### Backend: router-per-domain FastAPI app

`backend/app.py` is a thin orchestrator only — it builds the `FastAPI` app, wires middleware, runs the lifespan (creates the async engine/session/HTTP client, applies migrations, starts a background pricing-refresh loop), and `include_router()`s one module per domain. Business logic lives in the domain modules themselves (`auth.py`, `chat.py`, `conversations.py`, `memory.py`, `assistants.py`, `skills.py`, `wallet.py`, `admin.py`, `api_keys.py`, `pricing.py`, `payment_endpoints.py`, `notifications.py`, `tasks.py`, `websocket.py`, `rag_endpoints.py`, `document_generator.py`, `content.py`, `health.py`). `app.py` also re-exports models/helpers (e.g. `from app import User, _gen_token`) for backward compatibility with tests and scripts — when adding a new shared symbol other modules import from `app`, add it to that re-export block too.

Route prefix convention (documented inline in `app.py`): `/v1/*` is the public OpenAI-compatible API (models, chat, RAG, documents), `/admin/*` is internal management, `/auth/*` is authentication/profile, `/health/*` is health probes, everything else is app-level (conversations, wallet, etc.).

Cross-cutting pieces:
- `database.py` — engine/session/Redis/HTTP client globals, set via `_db.set_engine()` etc. during lifespan startup (so they can be swapped/mocked).
- `dependencies.py` — session cookie management (`_get_session`, `_rotate_session`), password/API-key hashing, `_get_user_id`/`_get_session_user_id` auth dependencies, `admin_required`, audit logging, notifications, email.
- `models.py` — all SQLAlchemy ORM models (30+ tables: users, wallet/ledger/reservations, subscriptions, conversations, assistants, memory, skills, scheduled tasks, RAG documents/chunks, audit log, etc.).
- `security.py` — `SecurityHeadersMiddleware`, `CsrfMiddleware`, and `RateLimitMiddleware` backed by per-endpoint-class `RateLimiter` instances (sliding window via Redis) — separate limiters exist for login/signup/chat-by-plan-tier/admin/RAG upload vs. query.
- `middleware/` — additional security headers and response compression middleware.
- `services/` — framework-agnostic domain logic: `billing.py` + `reservation.py` (wallet reserve/settle), `money.py` (`Money` value object, integer-toman amounts only, no floats), `metering.py`, `memory_extractor.py` (auto long-term memory extraction from chat), `rag.py` (retrieval/reranking/context building), `chunking.py`, `embeddings.py`, `doc_processor.py`, `context_injection.py`.

Migrations live in `backend/migrations/*.sql`, applied idempotently and in filename order by `migrate.py` (tracked in a `schema_migrations` table); new migrations should be added as a new numbered file (`00NN_description.sql`), never edited after being merged. `migrate.py` also runs automatically on every API startup (with one retry) via the `lifespan` context in `app.py`.

### Billing model

Wallet operations use a reserve → settle pattern (`services/reservation.py`, `services/billing.py`): authorize reserves an upper bound against the wallet before a model call, the actual usage is settled (and the remainder released) after the response, and failures deterministically release/refund. All ledger effects are append-only and idempotent by `idempotency_key`; `balance_after == previous_balance + amount` is an enforced invariant. Money is always an integer number of tomans (`Money.irt`) — never floats.

### Chat / model routing

`chat.py` validates the requested model against an allow-list of currently-working models (`get_working_models`/`is_working_model`, refreshed periodically), checks quota/wallet before calling out, proxies to the LiteLLM host (`LITELLM_HOST` env var) for the actual completion (streaming and non-streaming), then records usage and settles the wallet reservation. `/v1/compare` fans a prompt out to multiple models concurrently.

### RAG

`rag_endpoints.py` + `services/rag.py`: documents are uploaded, chunked (`chunking.py`), embedded (`embeddings.py`) and stored in Postgres via `pgvector` (`RagDocument`/`RagChunk`/`RagEmbeddingUsage` in `models.py`). Query-time retrieval does similarity search plus a keyword-based rerank (`_rerank`, `_keyword_search`) and builds a system prompt from the top context chunks before calling the LLM.

### Document generator

`document_generator.py` builds `.pptx` (`python-pptx`), `.docx` (`python-docx`), and Markdown decks from a single prompt. Generated files are written to a Docker volume (`multiai_docs`, mounted at `/tmp/multiai_docs`); the document registry/metadata is currently **in-memory only** and does not survive an API restart — this is a known gap tracked in the README roadmap (persistent storage via Postgres + object storage is planned, not yet implemented). Don't assume document listing survives across processes/restarts.

### Auth & sessions

Two parallel identity mechanisms: cookie-based server-side sessions in Redis (`SESSION_COOKIE_NAME`, rotated on privilege changes via `_rotate_session`) for the web app, and hashed (SHA256 + `API_KEY_PEPPER`) API keys for developer/API access. The standalone `admin/` app and the backend's own `/admin/*` routes each have their own separate session/CSRF cookie scheme — don't conflate `admin_required` (backend) with the admin panel's session logic in `admin/app.py`.

### Frontend

Next.js App Router under `frontend/app/`, one directory per feature area (`chat`, `admin`, `wallet`, `pricing`, `assistants`, `skills`, `memory`, `tasks`, `api-keys`, `usage`, `compare`, `playground`, `documents`, ...). `next.config.js` rewrites `/api/*` and `/v1/*` to the backend (`NEXT_PUBLIC_API_URL`, defaulting to the Docker service name `multiai-multiai_api-1:8000`) — the frontend never talks to the backend directly by absolute URL in app code, it goes through these rewrites. `lib/auth.tsx` provides an `AuthProvider`/context wrapping token storage (`localStorage` + `/api/auth/me`) — only clears the stored token on a definitive 401/403, not on transient network/5xx errors. `lib/useCatalog.ts` and similar hooks module-cache API responses (e.g. 60s TTL, in-flight request dedup) to avoid redundant fetches across components. UI is RTL Persian by default with an English/Persian language toggle; Playwright specs run against `fa-IR` locale.

### Product/data contract

`docs/product-contract.md` is the authoritative contract for what's in scope: models/prices/claims/wallet/usage/sessions must always be server-authoritative (`GET /catalog/models`, `/catalog/pricing`, `/wallet`, `/usage`, etc.) — the frontend must never be the source of truth for these. Every user-facing factual/numerical marketing claim requires a claim-registry entry (`claim_key`, `claim_type`, `source`, `verified_at`, ...); don't hardcode unverified numeric claims into frontend copy. Team/tenant/org features are explicitly out of scope for the current release — don't build toward multi-tenant assumptions.

## Conventions worth knowing

- **Backup files**: this repo keeps pre-change backups alongside the original as `<file>.bak.before-<change>-<date>` (e.g. `backend/migrate.py.bak.before-sqlsplit-20260712`) rather than relying solely on git history for certain sensitive fixes. These are intentional artifacts, not stray files — don't delete them without checking if they're still referenced/relevant, and follow the same pattern if a similarly risky fix needs an easy rollback reference.
- **Persian in code**: many user-facing strings (error messages, audit log text, rate-limit messages) are Persian literals embedded directly in backend Python files — this is intentional (Persian-first product), not a mistake to "fix" to English.
- Currency values are always integer tomans; never introduce float arithmetic for money.
- SQL migrations are append-only and numbered — never edit a migration that may have already run in any environment.
