#!/bin/bash
# SanjabAI PostgreSQL backup guard.
#
# Closes the trap found in session 11's restore drill:
# backups/pg/pre-sonnet5-reprice-*.sql.gz passed the old "size > 1000 bytes"
# check but contained a single table's data (COPY, no CREATE TABLE at all) —
# a useless partial dump wearing a full-backup filename.
#
# Usage: verify_backup.sh <path-to-backup.sql.gz> [--min-tables N]
#
#   --min-tables N   Require at least N `CREATE TABLE` statements in the
#                     dump. If omitted, defaults to the size of the
#                     CORE_TABLES list below (a floor, not the live count).
#                     pg_backup.sh passes the *actual* live table count it
#                     measured immediately before dumping, so a fresh backup
#                     is checked against reality, not a hardcoded guess.
#
# Exit 0  = PASS (this is a trustworthy full backup)
# Exit 1  = FAIL (reject it — caller should not keep/rely on this file)
#
# All checks are read-only against the .sql.gz file. No DB access here.

set -euo pipefail

# Core tables a restore is meaningless without. Derived from the live
# production schema on 2026-08-24 (54 tables total in `sanjabai`); this is
# the subset that represents money, identity, and the model catalog — the
# things that must survive a restore for the app to function at all.
CORE_TABLES=(
    users
    wallet
    wallet_reservations
    ledger
    payments
    payment_orders
    model_catalog
    provider
    pricing
    plans
    subscriptions
    sessions
    api_keys
    usage_events
    quota
    schema_migrations
)

FILE="${1:-}"
MIN_TABLES="${#CORE_TABLES[@]}"

if [ -z "$FILE" ]; then
    echo "usage: $0 <backup.sql.gz> [--min-tables N]" >&2
    exit 2
fi
shift || true

while [ $# -gt 0 ]; do
    case "$1" in
        --min-tables)
            MIN_TABLES="$2"
            shift 2
            ;;
        *)
            echo "unknown arg: $1" >&2
            exit 2
            ;;
    esac
done

if [ ! -f "$FILE" ]; then
    echo "FAIL: $FILE does not exist"
    exit 1
fi

FAIL_REASONS=()

# 1. gzip integrity
if ! gzip -t "$FILE" 2>/dev/null; then
    echo "FAIL: $FILE — not a valid gzip stream (gzip -t failed)"
    exit 1
fi

# 2. Minimum byte size (cheap first filter, kept from the old guard)
SIZE=$(stat -c%s "$FILE")
if [ "$SIZE" -lt 1000 ]; then
    FAIL_REASONS+=("file too small ($SIZE bytes)")
fi

DUMP_CONTENT=$(zcat "$FILE")

# 3. Minimum CREATE TABLE count — a real full dump has dozens of tables,
#    not one.
CREATE_COUNT=$(grep -c '^CREATE TABLE' <<< "$DUMP_CONTENT" || true)
if [ "$CREATE_COUNT" -lt "$MIN_TABLES" ]; then
    FAIL_REASONS+=("only $CREATE_COUNT CREATE TABLE statements found, need >= $MIN_TABLES")
fi

# 4. Presence of every core table by name.
MISSING_TABLES=()
for T in "${CORE_TABLES[@]}"; do
    # NOTE: here-string, not a `printf | grep -q` pipe — grep -q exits after
    # the first match and closes the pipe, which SIGPIPEs the upstream
    # command; with `set -o pipefail` that makes bash treat a *found* table
    # as a pipeline failure. A here-string has no upstream process to kill.
    if ! grep -qE "^CREATE TABLE (public\.)?${T} \(" <<< "$DUMP_CONTENT"; then
        MISSING_TABLES+=("$T")
    fi
done
if [ "${#MISSING_TABLES[@]}" -gt 0 ]; then
    FAIL_REASONS+=("missing core tables: ${MISSING_TABLES[*]}")
fi

if [ "${#FAIL_REASONS[@]}" -gt 0 ]; then
    echo "FAIL: $FILE"
    for R in "${FAIL_REASONS[@]}"; do
        echo "  - $R"
    done
    echo "  (found $CREATE_COUNT CREATE TABLE statements, $SIZE bytes)"
    exit 1
fi

echo "PASS: $FILE — $CREATE_COUNT tables, $SIZE bytes, all ${#CORE_TABLES[@]} core tables present"
exit 0
