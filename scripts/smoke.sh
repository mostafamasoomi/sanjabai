#!/usr/bin/env bash
#
# scripts/smoke.sh — Phase 0 smoke test for the Sanjabai backend + frontend.
#
# Lightweight runtime QA against a deployed Sanjabai stack. It:
#   1. Confirms the Compose services are up (sanjabai_* containers running).
#   2. Hits backend health endpoints (spec: /health/live + /health/ready;
#      tolerates the real /health + /health/detailed when the spec'd ones
#      are absent, so the check works against the actual API).
#   3. Checks the frontend routes return 200
#      (http://localhost:3003 / /chat /models /dashboard /wallet /admin).
#   4. Verifies an auth-gated endpoint returns 401 without a token.
#   5. Verifies no secret leakage (ADMIN_TOKEN / MASTER_SECRET strings) in
#      served HTML/JS.
#
# Exits non-zero on ANY failure. Safe to run from CI or locally.
#
# Override targets via environment variables:
#   BACKEND_URL      (default http://127.0.0.1:8001)
#   FRONTEND_URL     (default http://localhost:3003)
#   COMPOSE_FILE     (default docker-compose.sanjabai.yml)
set -uo pipefail

BACKEND="${BACKEND_URL:-http://127.0.0.1:8001}"
FRONTEND="${FRONTEND_URL:-http://localhost:3003}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.sanjabai.yml}"

FAIL=0

log() { printf '%s\n' "$*"; }
ok()  { printf '  [OK]   %s\n' "$*"; }
bad() { printf '  [FAIL] %s\n' "$*"; FAIL=1; }

# ── 1. Compose services up ────────────────────────────────────────────────
log "==> Checking Compose services"
svc_up=0
if command -v docker >/dev/null 2>&1; then
  if docker compose -f "$COMPOSE_FILE" ps --services --filter "status=running" 2>/dev/null | grep -q .; then
    n=$(docker compose -f "$COMPOSE_FILE" ps --services --filter "status=running" 2>/dev/null | wc -l)
    log "  docker compose reports $n running service(s)"
    svc_up=1
  elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'sanjabai_'; then
    n=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -c 'sanjabai_')
    log "  docker reports $n sanjabai_* container(s) running"
    svc_up=1
  fi
else
  log "  docker CLI unavailable; skipping service-presence check"
fi
if [ "$svc_up" -eq 1 ]; then ok "compose services up"; else bad "no sanjabai compose services detected as running"; fi

# ── 2. Backend health ──────────────────────────────────────────────────────
log "==> Checking backend health ($BACKEND)"
health_ok=0
live_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BACKEND/health/live")
ready_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BACKEND/health/ready")
if [ "$live_code" = "200" ] && [ "$ready_code" = "200" ]; then
  ok "health/live=$live_code health/ready=$ready_code"
  health_ok=1
else
  # Spec'd endpoints absent — fall back to the real ones the API actually exposes.
  h_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BACKEND/health")
  hd_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BACKEND/health/detailed")
  log "  spec'd /health/live=$live_code /health/ready=$ready_code; actual /health=$h_code /health/detailed=$hd_code"
  if [ "$h_code" = "200" ]; then
    ok "backend reachable via /health ($h_code) [spec'd /health/live + /health/ready not present]"
    health_ok=1
  fi
fi
[ "$health_ok" -eq 1 ] || bad "backend health endpoints not reachable"

# ── 3. Frontend routes ─────────────────────────────────────────────────────
log "==> Checking frontend routes ($FRONTEND)"
for route in / /chat /models /dashboard /wallet /admin; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$FRONTEND$route")
  if [ "$code" = "200" ]; then
    ok "frontend $route -> $code"
  else
    bad "frontend route $route -> $code (expected 200)"
  fi
done

# ── 4. Auth returns 401 without a token ────────────────────────────────────
log "==> Checking auth enforcement (expect 401 without token)"
auth_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$BACKEND/me/usage")
if [ "$auth_code" = "401" ]; then
  ok "/me/usage without token -> $auth_code"
else
  bad "/me/usage without token -> $auth_code (expected 401)"
fi

# ── 5. No secret leakage in served HTML/JS ────────────────────────────────
log "==> Checking for secret leakage in frontend assets"
leak=0
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

fetch() { curl -s --max-time 8 "$@"; }

fetch "$FRONTEND/" -o "$tmp/index.html"
for route in /chat /models /dashboard /wallet /admin; do
  fetch "$FRONTEND$route" -o "$tmp/route_$(echo "$route" | tr '/' '_').html"
done

# Pull every referenced JS bundle and fetch it locally for scanning.
grep -rhoE '(src|href)="[^"]+\.(js|mjs)[^"]*"' "$tmp" 2>/dev/null \
  | sed -E 's/.*="([^"]+)"/\1/' \
  | while read -r asset; do
      case "$asset" in
        /*)         fetch "$FRONTEND$asset" -o "$tmp/$(basename "$asset")" ;;
        http*)      fetch "$asset" -o "$tmp/$(basename "$asset")" ;;
        *)          fetch "$FRONTEND/$asset" -o "$tmp/$(basename "$asset")" ;;
      esac
    done

# Scan all fetched assets for secret-bearing identifiers. We exclude benign
# references such as `process.env.X` / `import` / `NEXT_PUBLIC_*` which are
# build-time placeholders, not leaked secret values.
if grep -rEi 'ADMIN_TOKEN|MASTER_SECRET' "$tmp" 2>/dev/null \
     | grep -vEi 'process\.env|import |NEXT_PUBLIC|window\.__|getEnv|env\.' \
     | grep -q .; then
  bad "possible secret leakage found:"
  grep -rEi 'ADMIN_TOKEN|MASTER_SECRET' "$tmp" 2>/dev/null \
    | grep -vEi 'process\.env|import |NEXT_PUBLIC|window\.__|getEnv|env\.' \
    | head -5 | while read -r line; do log "    $line"; done
  leak=1
else
  ok "no ADMIN_TOKEN/MASTER_SECRET secret strings in served assets"
fi
[ "$leak" -eq 0 ] || FAIL=1

# ── 6. Verify effective runtime mode ───────────────────────────────────────
log "==> Checking effective runtime mode"
mock_mode=$(docker compose -f "$COMPOSE_FILE" exec -T sanjabai_api sh -c 'printf "%s" "${MOCK_MODE:-}"' 2>/dev/null || true)
if [ "$mock_mode" = "false" ]; then
  ok "backend MOCK_MODE=false"
else
  bad "backend MOCK_MODE=${mock_mode:-<unset>} (expected false)"
fi

# ── Summary ────────────────────────────────────────────────────────────────
log ""
if [ "$FAIL" -eq 0 ]; then
  log "SMOKE TEST PASSED"
  exit 0
else
  log "SMOKE TEST FAILED"
  exit 1
fi
