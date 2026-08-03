# Security & smoke test suite

Black-box tests that run against a **deployed** Sanjabai instance over plain
HTTP(S) — no source checkout, no mocks, no database access required on the
machine running them. They complement (not replace) the source-level test
suites in `backend/tests/` (ownership introspection, migration idempotency,
claims registry, etc.) by checking what an actual client sees over the wire:
status codes, headers, cookie flags, rate limiting, and error-message
hygiene.

This is the suite meant for an external agent (or CI job, or a human) with
only a URL and, optionally, an admin token — not repo access — to run
against staging/production and report back pass/fail.

## Layout

- `smoke_test.py` — is the deployment up and answering on the routes that
  matter (health, public catalog endpoints including Hermes, auth-gated
  endpoints, frontend pages)?
- `security_test.py` — auth enforcement, admin/user session separation,
  security headers, secret leakage, rate limiting, and basic malformed-input
  handling.
- `browser_checks.mjs` — the one thing that needs a real browser instead of
  raw HTTP: confirms the admin panel's independent token-login screen is
  reachable **without** a regular user session (a redirect-before-hydration
  bug wouldn't show up in a plain `curl`/`requests` check, since Next.js
  still serves a 200 HTML shell either way — the redirect happens
  client-side). `run_all.sh` handles running it (see below); if invoking it
  directly, note that Node resolves `@playwright/test` relative to the
  *file's* location, not your cwd, so it must be run from (or copied into)
  `frontend/`, next to its `node_modules` — plain `node security/browser_checks.mjs`
  from the repo root will not find the import.
- `run_all.sh` — runs everything above in order and prints a single
  pass/fail summary with a non-zero exit code on any failure.

## Running it

```bash
cd security
pip install -r requirements.txt
# playwright's Python bindings aren't needed -- browser_checks.mjs runs on
# the frontend's own Node/Playwright install (frontend/node_modules).

export BACKEND_URL=https://api.example.com     # default: http://127.0.0.1:8001
export FRONTEND_URL=https://example.com        # default: http://localhost:3003
export ADMIN_TOKEN=...                          # optional: unlocks the admin-authed checks
export AUTH_TOKEN=...                           # optional: a real user's bearer token, unlocks the authed checks

./run_all.sh
```

Every test that needs a credential you didn't provide **skips** (not fails)
with a clear reason — the suite always finishes and always tells you what it
did and didn't check, rather than requiring full credentials up front.

## What "pass" means

- `smoke_test.py` failing means the deployment is down or a route that used
  to work now 404s/500s — treat as sev1, don't merge/keep deployed.
- `security_test.py` failing means an auth/session boundary that should hold
  doesn't — treat as sev1 regardless of how minor the specific endpoint
  seems, and open a ticket referencing the failing test name.
- `browser_checks.mjs` failing means either the admin login screen genuinely
  regressed back to requiring a user session, or the frontend is
  unreachable — check `FRONTEND_URL` first.

## Reporting back

`run_all.sh` writes JUnit XML per suite (`smoke.xml`, `security.xml`) plus a
plain-text summary to stdout, so a CI system or an agent invoking this
non-interactively has both a machine-readable and a human-readable report
without extra parsing.
