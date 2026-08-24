"""
Sanjabai Financial Watchdog — Production-grade anomaly detection.

Monitors 13 critical checks across 3 tiers and sends Telegram alerts.
Uses asyncpg for fast queries + Redis for dedup/cooldown.

TIER 1 — CRITICAL: Telegram + log, cooldown 1-5 min
TIER 2 — HIGH:     Telegram + log, cooldown 5 min
TIER 3 — MEDIUM:   log only, cooldown 15-60 min
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx

from watchdog_rules import CheckRule, RULES

# ── Configuration ──────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://sanjabai:sanjabai@db:5432/sanjabai',
)
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
CHECK_INTERVAL_BASE = int(os.getenv('WATCHDOG_INTERVAL', '60'))  # seconds

# WATCHDOG_BOT_TOKEN / WATCHDOG_CHAT_ID used to be module-level constants
# read here, once, at import. That made them un-changeable for the life of
# a container even after migration 0044 made them admin-editable -- this
# process runs for weeks (restart: unless-stopped, no HTTP surface), so an
# owner setting the credentials in the panel would have seen nothing happen
# until the next redeploy. They are now resolved on every send by
# services/watchdog_settings.py; see _send_telegram below.

# Parse REDIS_URL for aioredis (optional, falls back to in-memory dedup)
try:
    import redis.asyncio as aioredis
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False

# ── Logging ────────────────────────────────────────────────────────────────────

LOG_PATH = os.getenv('WATCHDOG_LOG', '/tmp/watchdog.log')

logger = logging.getLogger('watchdog')
logger.setLevel(logging.INFO)

# JSON lines file handler. Constructing a FileHandler used to crash at import
# time whenever LOG_PATH's directory did not exist or was not writable — the
# old default (/root/sanjabai/backend/watchdog.log) only ever worked on a
# specific host filesystem and killed the process instantly inside a
# container, before main() even got a chance to run. Guarded here so an
# unwritable/missing path degrades to console-only logging instead of a
# crash loop; WATCHDOG_LOG (above) lets a deployment point it somewhere real.
try:
    _fh = logging.FileHandler(LOG_PATH, encoding='utf-8')
    _fh.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(_fh)
except OSError as e:
    logging.getLogger('watchdog').warning(
        'watchdog: cannot open log file %r (%s); logging to console only', LOG_PATH, e
    )

# Console handler
_ch = logging.StreamHandler()
_ch.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s %(message)s'))
logger.addHandler(_ch)


def _log_json(severity: str, rule: str, rows: int, sample: Any = None) -> None:
    """Write structured JSON-lines log entry."""
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'severity': severity,
        'rule': rule,
        'rows': rows,
    }
    if sample is not None:
        entry['sample'] = sample
    logger.info(json.dumps(entry, ensure_ascii=False, default=str))


# ── Telegram ───────────────────────────────────────────────────────────────────

_http: httpx.AsyncClient | None = None

# Set once in main(). This process is deliberately NOT allowed to import
# backend/database.py -- that module raises at import time when ADMIN_TOKEN
# is unset, and the sanjabai_watchdog service in docker-compose.yml is given
# only DATABASE_URL / REDIS_URL / WATCHDOG_* -- so the credential rows are
# read off the pool this file already owns, via the `reader` hook
# services/watchdog_settings.py exposes for exactly this case.
_pool: asyncpg.Pool | None = None


async def _read_settings(keys: tuple[str, ...]) -> dict[str, Any]:
    """asyncpg-backed reader for services/watchdog_settings.py.

    `app_setting.value` is JSONB, which asyncpg hands back as the raw JSON
    TEXT rather than a decoded Python object (no codec is registered on
    this bare pool), so it is decoded here -- the resolver expects real
    Python values, the same shape SQLAlchemy/asyncpg give the API process.
    A row that will not decode is dropped rather than raised on, which the
    resolver then reads as "unset" and falls back to the environment.
    """
    if _pool is None:
        return {}
    rows = await _pool.fetch(
        'SELECT key, value FROM app_setting WHERE key = ANY($1::text[])',
        list(keys),
    )
    out: dict[str, Any] = {}
    for r in rows:
        raw = r['value']
        if isinstance(raw, (str, bytes)):
            try:
                raw = json.loads(raw)
            except Exception:
                continue
        out[r['key']] = raw
    return out


async def _send_telegram(severity: str, title: str, body: str) -> None:
    """Send alert via Telegram bot.

    Credentials are resolved per send (admin-editable app_setting rows
    first, WATCHDOG_BOT_TOKEN / WATCHDOG_CHAT_ID second) instead of being
    frozen at import. The resolver never raises and falls back to the
    environment on any DB error, so the worst case here is byte-for-byte
    the behaviour this function had before migration 0044.
    """
    # Guarded even though the resolver is documented never to raise: this
    # function is awaited straight from the main loop with no try around
    # it, so anything escaping here would kill the whole watchdog process
    # and silence all 13 rules -- strictly worse than one missed alert.
    try:
        from services.watchdog_settings import get_watchdog_credentials
        bot_token, chat_id = (
            await get_watchdog_credentials(reader=_read_settings)
        ).as_tuple()
    except Exception as e:
        logger.warning(f'Watchdog credential lookup failed, skipping Telegram: {e}')
        return
    if not bot_token or not chat_id:
        logger.warning('WATCHDOG_BOT_TOKEN or WATCHDOG_CHAT_ID not set, skipping Telegram')
        return

    emoji = {'CRITICAL': '🚨', 'HIGH': '⚠️', 'MEDIUM': '📊'}.get(severity, 'ℹ️')
    text = (
        f"{emoji} *Sanjabai Watchdog — {severity}*\n"
        f"*{title}*\n"
        f"{body}\n"
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )

    try:
        assert _http is not None
        resp = await _http.post(
            f'https://api.telegram.org/bot{bot_token}/sendMessage',
            json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'Markdown',
            },
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(f'Telegram send failed: {resp.status_code} {resp.text[:200]}')
    except Exception as e:
        logger.warning(f'Telegram send error: {e}')


# ── Redis Dedup (with in-memory fallback) ──────────────────────────────────────

_rds: Any = None
_memory_dedup: dict[str, float] = {}


async def _init_redis() -> None:
    global _rds
    if _HAS_REDIS:
        try:
            _rds = aioredis.from_url(REDIS_URL, decode_responses=True)
            await _rds.ping()
            logger.info('Redis connected for dedup')
        except Exception as e:
            logger.warning(f'Redis unavailable, using in-memory dedup: {e}')
            _rds = None


async def _is_in_cooldown(rule_name: str, cooldown_seconds: int) -> bool:
    """Check if this rule is in cooldown period."""
    key = f'watchdog:alert:{rule_name}:{int(time.time()) // cooldown_seconds}'
    try:
        if _rds:
            exists = await _rds.get(key)
            if exists:
                return True
            await _rds.setex(key, cooldown_seconds, '1')
            return False
        else:
            # In-memory fallback
            now = time.time()
            bucket = int(now) // cooldown_seconds
            mem_key = f'{rule_name}:{bucket}'
            if mem_key in _memory_dedup:
                return True
            _memory_dedup[mem_key] = now
            # Cleanup old entries
            cutoff = now - cooldown_seconds * 2
            stale = [k for k, v in _memory_dedup.items() if v < cutoff]
            for k in stale:
                del _memory_dedup[k]
            return False
    except Exception:
        return False


# ── Check Rule Definitions & Format Functions ──────────────────────────────────
# Moved to watchdog_rules.py (CheckRule dataclass, the 13 RULES, and their
# _fmt_* formatters) purely to stay under the house 500-line cap; imported
# at the top of this file. Nothing about the rules, SQL, tiers, intervals,
# cooldowns, timeouts, or formatting changed in the move -- see that
# module's docstring.


# ── Main Loop ──────────────────────────────────────────────────────────────────

async def _run_check(pool: asyncpg.Pool, rule: CheckRule) -> None:
    """Execute a single check rule."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(f"SET statement_timeout = '{rule.timeout * 1000}'")
            rows = await conn.fetch(rule.query)
    except Exception as e:
        logger.warning(f'Query failed for {rule.name}: {e}')
        return

    if not rows:
        return

    # Dead silence: only alert if status is SILENT
    if rule.name == 'dead_silence':
        if rows[0]['status'] != 'SILENT':
            return

    # Check cooldown
    if await _is_in_cooldown(rule.name, rule.cooldown):
        return

    # Format alert body
    sample = [dict(r) for r in rows[:5]]
    body = rule.format_fn(sample)

    # Log
    _log_json(rule.tier, rule.name, len(rows), sample)

    # Send Telegram for CRITICAL and HIGH
    if rule.tier in ('CRITICAL', 'HIGH'):
        await _send_telegram(rule.tier, rule.title, body)


async def main() -> None:
    """Main watchdog loop."""
    global _http, _pool

    logger.info('Watchdog starting...')
    _http = httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5))

    await _init_redis()

    # Create connection pool
    pool = await asyncpg.create_pool(
        DATABASE_URL, min_size=1, max_size=3,
        command_timeout=30,
    )
    # Published for _read_settings (the credential reader). Same pool, so
    # the credential lookup costs no extra connection.
    _pool = pool
    logger.info(f'Connected to database, monitoring {len(RULES)} rules')

    last_run: dict[str, float] = {}
    all_ok_counter = 0

    try:
        while True:
            now = time.time()
            for rule in RULES:
                last = last_run.get(rule.name, 0)
                if now - last >= rule.interval:
                    await _run_check(pool, rule)
                    last_run[rule.name] = now

            # Log "all clear" every 5 minutes
            all_ok_counter += 1
            if all_ok_counter >= 300 // CHECK_INTERVAL_BASE:
                _log_json('INFO', 'all_clear', 0)
                logger.info('Watchdog check: all 13 rules passed')
                all_ok_counter = 0

            await asyncio.sleep(CHECK_INTERVAL_BASE)
    except asyncio.CancelledError:
        logger.info('Watchdog shutting down')
    finally:
        await pool.close()
        if _http:
            await _http.aclose()
        if _rds:
            await _rds.close()


if __name__ == '__main__':
    asyncio.run(main())
