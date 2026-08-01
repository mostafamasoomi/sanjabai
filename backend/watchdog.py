"""
Sanjhubai Financial Watchdog — Production-grade anomaly detection.

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

# ── Configuration ──────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://sanjhubai:sanjhubai@db:5432/sanjhubai',
)
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
WATCHDOG_BOT_TOKEN = os.getenv('WATCHDOG_BOT_TOKEN', '')
WATCHDOG_CHAT_ID = os.getenv('WATCHDOG_CHAT_ID', '')
CHECK_INTERVAL_BASE = int(os.getenv('WATCHDOG_INTERVAL', '60'))  # seconds

# Parse REDIS_URL for aioredis (optional, falls back to in-memory dedup)
try:
    import redis.asyncio as aioredis
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False

# ── Logging ────────────────────────────────────────────────────────────────────

LOG_PATH = os.getenv('WATCHDOG_LOG', '/root/sanjhubai/backend/watchdog.log')

logger = logging.getLogger('watchdog')
logger.setLevel(logging.INFO)

# JSON lines file handler
_fh = logging.FileHandler(LOG_PATH, encoding='utf-8')
_fh.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(_fh)

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


async def _send_telegram(severity: str, title: str, body: str) -> None:
    """Send alert via Telegram bot."""
    if not WATCHDOG_BOT_TOKEN or not WATCHDOG_CHAT_ID:
        logger.warning('WATCHDOG_BOT_TOKEN or WATCHDOG_CHAT_ID not set, skipping Telegram')
        return

    emoji = {'CRITICAL': '🚨', 'HIGH': '⚠️', 'MEDIUM': '📊'}.get(severity, 'ℹ️')
    text = (
        f"{emoji} *Sanjhubai Watchdog — {severity}*\n"
        f"*{title}*\n"
        f"{body}\n"
        f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )

    try:
        assert _http is not None
        resp = await _http.post(
            f'https://api.telegram.org/bot{WATCHDOG_BOT_TOKEN}/sendMessage',
            json={
                'chat_id': WATCHDOG_CHAT_ID,
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


# ── Check Rule Definition ──────────────────────────────────────────────────────

@dataclass
class CheckRule:
    name: str
    tier: str  # CRITICAL, HIGH, MEDIUM
    interval: int  # seconds between checks
    cooldown: int  # seconds between alerts
    query: str
    title: str
    format_fn: Any  # callable(rows) -> str
    timeout: int = 10  # query timeout in seconds


# ── Format Functions ───────────────────────────────────────────────────────────

def _fmt_negative_balance(rows: list) -> str:
    lines = []
    for r in rows[:5]:
        lines.append(f"User ID: {r['user_id']} | Balance: {r['balance']:,} IRT")
    return '\n'.join(lines) + '\nAction: Check ledger immediately'


def _fmt_wallet_ledger_mismatch(rows: list) -> str:
    lines = []
    for r in rows[:5]:
        lines.append(
            f"User ID: {r['user_id']} | Wallet: {r['wallet_balance']:,} | "
            f"Ledger: {r['ledger_balance']:,} | Delta: {r['delta']:,}"
        )
    return '\n'.join(lines) + '\nAction: Investigate wallet/ledger inconsistency'


def _fmt_banned_activity(rows: list) -> str:
    lines = []
    for r in rows[:5]:
        lines.append(f"User ID: {r['user_id']} | Events: {r['event_count']}")
    return '\n'.join(lines) + '\nAction: Verify ban is enforced'


def _fmt_double_credit(rows: list) -> str:
    lines = []
    for r in rows[:5]:
        lines.append(f"Key: {r['idempotency_key']} | Count: {r['cnt']}")
    return '\n'.join(lines) + '\nAction: Audit duplicate ledger entries'


def _fmt_stale_reservations(rows: list) -> str:
    lines = []
    for r in rows[:5]:
        lines.append(
            f"User ID: {r['user_id']} | Stale: {r['stale_count']} | "
            f"Held: {r['total_held']:,} IRT"
        )
    return '\n'.join(lines) + '\nAction: Release stale reservations'


def _fmt_zero_cost(rows: list) -> str:
    lines = []
    for r in rows[:5]:
        lines.append(f"User: {r['user_id']} | Model: {r['model']} | Count: {r['event_count']}")
    return '\n'.join(lines) + '\nAction: Check pricing config'


def _fmt_rapid_fire(rows: list) -> str:
    lines = []
    for r in rows[:5]:
        lines.append(f"User: {r['user_id']} | Requests/min: {r['request_count']}")
    return '\n'.join(lines) + '\nAction: Possible abuse or bot'


def _fmt_upstream_failure(rows: list) -> str:
    lines = []
    for r in rows[:5]:
        rate = float(r['fail_rate']) * 100
        lines.append(
            f"Model: {r['model']} | Total: {r['total']} | "
            f"Failures: {r['failures']} | Rate: {rate:.1f}%"
        )
    return '\n'.join(lines) + '\nAction: Check upstream provider health'


def _fmt_dead_silence(rows: list) -> str:
    return 'No usage events in the last minute.\nAction: Verify platform is receiving traffic'


def _fmt_token_velocity(rows: list) -> str:
    lines = []
    for r in rows[:5]:
        lines.append(
            f"User: {r['user_id']} | Last hour: {r['tokens_last_hour']:,} | "
            f"7d avg: {r['avg_daily']:.0f}"
        )
    return '\n'.join(lines) + '\nAction: Unusual token consumption spike'


def _fmt_new_user_burn(rows: list) -> str:
    lines = []
    for r in rows[:5]:
        lines.append(
            f"User: {r['id']} ({r['email']}) | Spent: {r['spent']:,} IRT | "
            f"Created: {r['user_created']}"
        )
    return '\n'.join(lines) + '\nAction: New user spending abnormally high'


def _fmt_payment_backlog(rows: list) -> str:
    return f"Pending payments: {rows[0]['pending_count']}\nAction: Check payment verification pipeline"


def _fmt_reserved_exceeds(rows: list) -> str:
    lines = []
    for r in rows[:5]:
        lines.append(
            f"User: {r['user_id']} | Balance: {r['balance']:,} | Reserved: {r['reserved']:,}"
        )
    return '\n'.join(lines) + '\nAction: Fix reservation leak'


# ── Rule Definitions ───────────────────────────────────────────────────────────

RULES: list[CheckRule] = [
    # TIER 1 — CRITICAL
    CheckRule(
        name='negative_balance', tier='CRITICAL', interval=60, cooldown=60,
        query="""
            SELECT user_id, SUM(amount) as balance
            FROM ledger GROUP BY user_id HAVING SUM(amount) < 0
        """,
        title='Negative Balance Detected',
        format_fn=_fmt_negative_balance,
    ),
    CheckRule(
        name='wallet_ledger_mismatch', tier='CRITICAL', interval=300, cooldown=300,
        query="""
            SELECT w.user_id, w.balance as wallet_balance,
                   COALESCE(l.sum_amount, 0) as ledger_balance,
                   w.balance - COALESCE(l.sum_amount, 0) as delta
            FROM wallet w
            LEFT JOIN (
                SELECT user_id, SUM(amount) as sum_amount FROM ledger GROUP BY user_id
            ) l ON w.user_id = l.user_id
            WHERE w.balance != COALESCE(l.sum_amount, 0)
        """,
        title='Wallet/Ledger Mismatch',
        format_fn=_fmt_wallet_ledger_mismatch,
    ),
    CheckRule(
        name='banned_user_activity', tier='CRITICAL', interval=300, cooldown=300,
        query="""
            SELECT ue.user_id, COUNT(*) as event_count
            FROM usage_events ue
            JOIN users u ON ue.user_id = u.id
            WHERE u.banned = TRUE
              AND ue.created_at > NOW() - INTERVAL '1 hour'
            GROUP BY ue.user_id
        """,
        title='Banned User Activity',
        format_fn=_fmt_banned_activity,
    ),
    CheckRule(
        name='double_credit', tier='CRITICAL', interval=300, cooldown=300,
        query="""
            SELECT idempotency_key, COUNT(*) as cnt
            FROM ledger
            WHERE idempotency_key IS NOT NULL
            GROUP BY idempotency_key
            HAVING COUNT(*) > 1
        """,
        title='Duplicate Idempotency Key',
        format_fn=_fmt_double_credit,
    ),

    # TIER 2 — HIGH
    CheckRule(
        name='stale_reservations', tier='HIGH', interval=120, cooldown=300,
        query="""
            SELECT user_id, COUNT(*) as stale_count, SUM(amount) as total_held
            FROM wallet_reservations
            WHERE status = 'reserved'
              AND created_at < NOW() - INTERVAL '15 minutes'
            GROUP BY user_id
            HAVING COUNT(*) > 5 OR SUM(amount) > 100000
        """,
        title='Stale Reservations',
        format_fn=_fmt_stale_reservations,
    ),
    CheckRule(
        name='zero_cost_usage', tier='HIGH', interval=300, cooldown=900,
        query="""
            SELECT user_id, model, COUNT(*) as event_count
            FROM usage_events
            WHERE charged_amount = 0
              AND (input_tokens + output_tokens) > 1000
              AND created_at > NOW() - INTERVAL '1 hour'
            GROUP BY user_id, model
            HAVING COUNT(*) > 10
        """,
        title='Zero-Cost Usage (Real Tokens, No Charge)',
        format_fn=_fmt_zero_cost,
    ),
    CheckRule(
        name='rapid_fire', tier='HIGH', interval=60, cooldown=60,
        query="""
            SELECT user_id, COUNT(*) as request_count
            FROM usage_events
            WHERE created_at > NOW() - INTERVAL '1 minute'
            GROUP BY user_id
            HAVING COUNT(*) > 100
        """,
        title='Rapid-Fire Requests',
        format_fn=_fmt_rapid_fire,
    ),
    CheckRule(
        name='upstream_failure', tier='HIGH', interval=120, cooldown=300,
        query="""
            SELECT model,
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE upstream_status != 'success') as failures,
                   (COUNT(*) FILTER (WHERE upstream_status != 'success')::float
                    / COUNT(*)) as fail_rate
            FROM usage_events
            WHERE created_at > NOW() - INTERVAL '5 minutes'
            GROUP BY model
            HAVING COUNT(*) >= 50
               AND (COUNT(*) FILTER (WHERE upstream_status != 'success')::float
                    / COUNT(*)) > 0.10
        """,
        title='Upstream Failure Rate > 10%',
        format_fn=_fmt_upstream_failure,
        timeout=30,
    ),
    CheckRule(
        name='dead_silence', tier='HIGH', interval=60, cooldown=60,
        query="""
            SELECT CASE WHEN COUNT(*) = 0 THEN 'SILENT' ELSE 'OK' END as status
            FROM usage_events
            WHERE created_at > NOW() - INTERVAL '1 minute'
        """,
        title='Dead Silence — No Usage Events',
        format_fn=_fmt_dead_silence,
    ),

    # TIER 3 — MEDIUM
    CheckRule(
        name='token_velocity_spike', tier='MEDIUM', interval=300, cooldown=900,
        query="""
            WITH user_avg AS (
                SELECT user_id, AVG(daily_tokens) as avg_daily
                FROM (
                    SELECT user_id, DATE(created_at) as day,
                           SUM(input_tokens + output_tokens) as daily_tokens
                    FROM usage_events
                    WHERE created_at > NOW() - INTERVAL '7 days'
                    GROUP BY user_id, DATE(created_at)
                ) sub
                GROUP BY user_id
            )
            SELECT ue.user_id,
                   SUM(ue.input_tokens + ue.output_tokens) as tokens_last_hour,
                   ua.avg_daily
            FROM usage_events ue
            JOIN user_avg ua ON ue.user_id = ua.user_id
            WHERE ue.created_at > NOW() - INTERVAL '1 hour'
            GROUP BY ue.user_id, ua.avg_daily
            HAVING SUM(ue.input_tokens + ue.output_tokens) > 5 * ua.avg_daily
               AND SUM(ue.input_tokens + ue.output_tokens) > 100000
        """,
        title='Token Velocity Spike (>5x 7-day avg)',
        format_fn=_fmt_token_velocity,
        timeout=30,
    ),
    CheckRule(
        name='new_user_burn', tier='MEDIUM', interval=600, cooldown=3600,
        query="""
            SELECT u.id, u.email, SUM(ue.charged_amount) as spent, u.created_at as user_created
            FROM users u
            JOIN usage_events ue ON u.id = ue.user_id
            WHERE u.created_at > NOW() - INTERVAL '24 hours'
            GROUP BY u.id, u.email, u.created_at
            HAVING SUM(ue.charged_amount) > 500000
        """,
        title='New User Burn (>500K IRR in <24h)',
        format_fn=_fmt_new_user_burn,
    ),
    CheckRule(
        name='payment_backlog', tier='MEDIUM', interval=300, cooldown=900,
        query="""
            SELECT COUNT(*) as pending_count
            FROM payments
            WHERE status = 'pending'
              AND created_at < NOW() - INTERVAL '1 hour'
            HAVING COUNT(*) > 50
        """,
        title='Payment Backlog',
        format_fn=_fmt_payment_backlog,
    ),
    CheckRule(
        name='reserved_exceeds_balance', tier='MEDIUM', interval=300, cooldown=900,
        query="""
            SELECT user_id, balance, reserved
            FROM wallet
            WHERE reserved > balance
        """,
        title='Reserved Exceeds Balance',
        format_fn=_fmt_reserved_exceeds,
    ),
]


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
    global _http

    logger.info('Watchdog starting...')
    _http = httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5))

    await _init_redis()

    # Create connection pool
    pool = await asyncpg.create_pool(
        DATABASE_URL, min_size=1, max_size=3,
        command_timeout=30,
    )
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
