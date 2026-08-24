"""Check-rule definitions and alert-body formatters for backend/watchdog.py.

Split out of watchdog.py purely to stay under the house 500-line cap --
watchdog.py crossed it (624 lines) once the admin-editable Telegram
credential plumbing (migration 0044 / services/watchdog_settings.py) was
added on top of the original 13-rule monitor. Nothing here changed in the
move: the same ``CheckRule`` dataclass, the same 13 rules with their exact
SQL/tier/interval/cooldown/timeout values, and the same format functions,
verbatim.

``watchdog.py`` imports ``CheckRule`` (for the ``rule: CheckRule`` type
hint on ``_run_check``) and ``RULES`` (the list the main loop iterates)
from here. Nothing external imports this module -- it has no monkeypatch
contract of its own; the format functions are only ever reached via
``rule.format_fn(...)`` (an attribute read off a ``CheckRule`` instance),
never via a bare module-level name, so moving them does not change how
they resolve.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
