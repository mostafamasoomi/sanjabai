#!/usr/bin/env bash
#
# security/run_all.sh — run the full black-box smoke + security suite
# against a deployed Sanjhubai instance and print a single pass/fail
# summary. Meant to be run non-interactively (CI, or an agent given only a
# URL) — every sub-check that's missing a credential skips cleanly instead
# of blocking the rest of the run.
#
# Env vars (all optional, see README.md for defaults):
#   BACKEND_URL   FRONTEND_URL   ADMIN_TOKEN   AUTH_TOKEN
#
# Writes JUnit XML per suite (smoke.xml, security.xml) into this directory
# alongside the human-readable stdout output, then exits non-zero if
# anything failed.
set -uo pipefail

cd "$(dirname "$0")"

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3003}"
export BACKEND_URL FRONTEND_URL

FAIL=0

echo "════════════════════════════════════════════════════════════════"
echo " Sanjhubai security & smoke suite"
echo "   BACKEND_URL=$BACKEND_URL"
echo "   FRONTEND_URL=$FRONTEND_URL"
echo "   ADMIN_TOKEN set: $([ -n "${ADMIN_TOKEN:-}" ] && echo yes || echo no)"
echo "   AUTH_TOKEN set:  $([ -n "${AUTH_TOKEN:-}" ] && echo yes || echo no)"
echo "════════════════════════════════════════════════════════════════"

echo ""
echo "==> smoke_test.py"
python3 -m pytest smoke_test.py -v --tb=short --junitxml=smoke.xml
[ $? -eq 0 ] || FAIL=1

echo ""
echo "==> security_test.py"
python3 -m pytest security_test.py -v --tb=short --junitxml=security.xml
[ $? -eq 0 ] || FAIL=1

echo ""
echo "==> browser_checks.mjs"
SECURITY_DIR="$(pwd)"
FRONTEND_DIR="$(cd .. && pwd)/frontend"
if [ -d "$FRONTEND_DIR/node_modules" ]; then
  # Node resolves bare ESM imports (`@playwright/test`) relative to the
  # importing FILE's own path, not the process's cwd -- NODE_PATH doesn't
  # help for ESM. So the script has to physically live under frontend/ (next
  # to its node_modules) to import Playwright, hence the copy/cleanup.
  TMP_SCRIPT="$FRONTEND_DIR/.security-browser-checks.mjs"
  cp "$SECURITY_DIR/browser_checks.mjs" "$TMP_SCRIPT"
  trap 'rm -f "$TMP_SCRIPT"' EXIT
  (cd "$FRONTEND_DIR" && FRONTEND_URL="$FRONTEND_URL" node "$TMP_SCRIPT")
  [ $? -eq 0 ] || FAIL=1
  rm -f "$TMP_SCRIPT"
  trap - EXIT
else
  echo "  SKIP: $FRONTEND_DIR/node_modules not found (run 'npm ci' in frontend/ first)"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
if [ "$FAIL" -eq 0 ]; then
  echo " RESULT: PASS"
else
  echo " RESULT: FAIL — see smoke.xml / security.xml and the output above"
fi
echo "════════════════════════════════════════════════════════════════"

exit "$FAIL"
