#!/usr/bin/env bash
set -euo pipefail

echo "[verify] Sanjhubai backend test environment check"

PY_BIN=${PYTHON:-python3}
if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "ERROR: python3 not found"; exit 1
fi
$PY_BIN --version

if ! command -v pytest >/dev/null 2>&1; then
  echo "ERROR: pytest not installed in PATH"; exit 1
fi

# Optional: check venv presence
if [ -d "venv" ]; then
  echo "venv present"
else
  echo "note: venv not present; create with: python3 -m venv venv"
fi

# quick dry-run of pytest availability
pytest --version >/dev/null 2>&1 || { echo "ERROR: pytest not functional"; exit 1; }

echo "[verify] OK: pytest available. Ready to run tests."
