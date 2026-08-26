"""
GET /admin/security/stats -- the data behind the panel's «امنیت» page.

The frontend shipped this page in Phase 8 against an endpoint that never
existed; Promise.allSettled swallowed the 404 and the page showed a loading
skeleton forever (session 11 audit, finding A3). This module supplies the
exact contract SecurityStats (frontend/app/admin/AdminPanel.tsx) already
declares, from data the system genuinely records -- nothing here is
estimated or invented:

  failed logins   -> audit_logs rows with action = 'auth.login_failed'
                     (written by auth.py on every bad password)
  active sessions -> live `session:*` keys in Redis (dependencies.py writes
                     one per logged-in session, TTL-expired automatically)
  banned users    -> users.banned, with banned_at reconstructed from the
                     latest 'admin.user.ban' audit row for that user
  threat level    -> a stated, fixed mapping over failed_logins_24h and
                     active lockout keys; documented here so the panel's
                     badge is a claim we can defend, not a vibe.
"""
from __future__ import annotations

import logging
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

import admin
from database import async_session, rds
from i18n import err

logger = logging.getLogger('admin_security')

router = APIRouter()


async def _count_keys(pattern: str) -> int:
    """SCAN, never KEYS: this runs on the production Redis."""
    n = 0
    try:
        async for _ in rds.scan_iter(match=pattern, count=500):
            n += 1
    except Exception as e:
        logger.warning('scan %s failed: %s', pattern, e)
    return n


def _threat_level(failed_24h: int, active_lockouts: int) -> str:
    # Fixed thresholds, chosen for a site this size (single-digit real users):
    # any burst of failures is worth looking at, a lockout means someone is
    # actively hammering an account.
    if failed_24h >= 100 or active_lockouts >= 5:
        return 'critical'
    if failed_24h >= 30 or active_lockouts >= 1:
        return 'high'
    if failed_24h >= 10:
        return 'medium'
    return 'low'


@router.get('/admin/security/stats')
async def security_stats(request: Request) -> JSONResponse:
    if not await admin.admin_required(request):
        return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'The database is unavailable.', 500)

    async with async_session() as session:
        failed_res = await session.execute(sqlalchemy.text(
            "SELECT COUNT(*) AS c FROM audit_logs "
            "WHERE action = 'auth.login_failed' "
            "AND created_at > now() - INTERVAL '24 hours'"
        ))
        failed_24h = failed_res.fetchone().c

        chart_res = await session.execute(sqlalchemy.text(
            "SELECT to_char(date_trunc('hour', created_at), 'HH24:00') AS hour, "
            "COUNT(*) AS count FROM audit_logs "
            "WHERE action = 'auth.login_failed' "
            "AND created_at > now() - INTERVAL '24 hours' "
            "GROUP BY date_trunc('hour', created_at) "
            "ORDER BY date_trunc('hour', created_at)"
        ))
        chart = [dict(r._mapping) for r in chart_res.fetchall()]

        banned_res = await session.execute(sqlalchemy.text(
            "SELECT u.id, u.email, u.display_name AS username, ban.created_at AS banned_at "
            "FROM users u "
            "LEFT JOIN LATERAL ("
            "  SELECT created_at FROM audit_logs "
            "  WHERE action = 'admin.user.ban' AND target_id = u.id::text "
            "  ORDER BY created_at DESC LIMIT 1"
            ") ban ON true "
            "WHERE u.banned = true ORDER BY u.id"
        ))
        banned = [dict(r._mapping) for r in banned_res.fetchall()]

    active_sessions = await _count_keys('session:*')
    active_lockouts = await _count_keys('lockout:*')

    return JSONResponse(jsonable_encoder({
        'threat_level': _threat_level(failed_24h, active_lockouts),
        'failed_logins_24h': failed_24h,
        'active_sessions': active_sessions,
        'failed_login_chart': chart,
        'banned_users': banned,
    }))
