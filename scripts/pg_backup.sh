#!/bin/bash
# SanjabAI PostgreSQL backup — runs on S3. Daily via cron, retain 7 days.
# ponytail: plain pg_dump + gzip + find-delete. Add WAL archiving if RPO<24h needed.
set -euo pipefail

CONTAINER="sanjabai-sanjabai_pg-1"
DB_USER="sanjabai"
DB_NAME="sanjabai"
DEST="/root/sanjabai/backups/pg"
RETAIN_DAYS=7
TS="$(date +%Y%m%d_%H%M%S)"
OUT="$DEST/sanjabai_${TS}.sql.gz"
LOG="$DEST/backup.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFY="$SCRIPT_DIR/verify_backup.sh"

mkdir -p "$DEST"

echo "[$(date -Is)] start backup -> $OUT" >> "$LOG"

# Measure the live table count *before* dumping so the guard checks the
# dump against reality, not a hardcoded number. (session 11's restore drill
# found a "backup" that was really a single table's data wearing a full
# backup's filename — the old guard only checked "> 1000 bytes" and missed it.)
LIVE_TABLE_COUNT=$(docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
    "select count(*) from information_schema.tables where table_schema='public' and table_type='BASE TABLE';" \
    2>>"$LOG" | tr -d '[:space:]')

if ! [[ "$LIVE_TABLE_COUNT" =~ ^[0-9]+$ ]]; then
    echo "[$(date -Is)] ERROR: could not measure live table count (got '$LIVE_TABLE_COUNT')" >> "$LOG"
    exit 1
fi

if docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" 2>>"$LOG" | gzip > "$OUT"; then
    echo "[$(date -Is)] dump written, verifying ($LIVE_TABLE_COUNT live tables expected)" >> "$LOG"
    if VERIFY_OUTPUT=$("$VERIFY" "$OUT" --min-tables "$LIVE_TABLE_COUNT" 2>&1); then
        SIZE=$(stat -c%s "$OUT")
        echo "[$(date -Is)] ok ($SIZE bytes) — $VERIFY_OUTPUT" >> "$LOG"
    else
        echo "[$(date -Is)] ERROR: backup failed verification, removing $OUT" >> "$LOG"
        echo "$VERIFY_OUTPUT" >> "$LOG"
        rm -f "$OUT"
        exit 1
    fi
else
    echo "[$(date -Is)] ERROR: pg_dump failed" >> "$LOG"
    rm -f "$OUT"
    exit 1
fi

# Prune old backups
find "$DEST" -name 'sanjabai_*.sql.gz' -mtime +$RETAIN_DAYS -delete
echo "[$(date -Is)] pruned >$RETAIN_DAYS days" >> "$LOG"
