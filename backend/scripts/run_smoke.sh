#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
echo "=== Sanjabai smoke tests ==="
python3 -m pytest smoke_test.py -v --tb=short
echo "=== DONE ==="
