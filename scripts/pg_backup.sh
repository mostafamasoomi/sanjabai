#!/bin/bash
# MultiAI PostgreSQL backup — runs on S3. Daily via cron, retain 7 days.
# ponytail: plain pg_dump + gzip + find-delete. Add WAL archiving if RPO<24h needed.
set -euo pipefail

CONTAINER="multiai-multiai_pg-1"
DB_USER="multiai"
DB_NAME="multiai"
DEST="/root/multiai/backups/pg"
RETAIN_DAYS=7
TS="$(date +%Y%m%d_%H%M%S)"
OUT="$DEST/multiai_${TS}.sql.gz"
LOG="$DEST/backup.log"

mkdir -p "$DEST"

echo "[$(date -Is)] start backup -> $OUT" >> "$LOG"

if docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" 2>>"$LOG" | gzip > "$OUT"; then
    SIZE=$(stat -c%s "$OUT")
    if [ "$SIZE" -lt 1000 ]; then
        echo "[$(date -Is)] ERROR: dump too small ($SIZE bytes), removing" >> "$LOG"
        rm -f "$OUT"
        exit 1
    fi
    echo "[$(date -Is)] ok ($SIZE bytes)" >> "$LOG"
else
    echo "[$(date -Is)] ERROR: pg_dump failed" >> "$LOG"
    rm -f "$OUT"
    exit 1
fi

# Prune old backups
find "$DEST" -name 'multiai_*.sql.gz' -mtime +$RETAIN_DAYS -delete
echo "[$(date -Is)] pruned >$RETAIN_DAYS days" >> "$LOG"
