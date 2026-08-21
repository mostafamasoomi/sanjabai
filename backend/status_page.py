"""
Public status page + incident admin.

Uptime Kuma runs as a container on this same compose network (see
`uptime_kuma` in docker-compose.sanjabai.yml) -- every sanjabai.com component
lives on the deploy server, so the backend reaches it by service name, never
by IP. Nothing here calls Kuma directly from the browser: the frontend hits
`GET /api/status/summary` (via the existing Next.js rewrite) and this module
is the only thing that ever talks to Kuma.

`GET /status/summary` is public, unauthenticated, and MUST NEVER return 500.
An anonymous visitor checking whether the platform is up must not get an
error page for their trouble, so failures degrade in this order:

    fresh Kuma fetch -> 60s Redis cache -> last-known-good snapshot (stale)
    -> empty (`services: []`, `monitoringUp: false`)

A negative cache (`status:kuma:fail`, 60s TTL) means an unreachable Kuma
costs at most one timed-out fetch per minute total, not one per visitor.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session, rds
from dependencies import admin_required, _write_audit_log

logger = logging.getLogger('status_page')

router = APIRouter()

# ── Kuma monitor -> Persian label allowlist ──────────────────────────────
# Deliberately an allowlist, not a passthrough. A monitor whose Kuma name is
# not one of these keys is dropped from the public response entirely -- so a
# monitor someone later names after a hostname, an IP, or anything else
# infra-shaped can never leak onto the public status page just by existing in
# Kuma. Monitor URLs are never included in the response either way.
MONITOR_LABELS: dict[str, str] = {
    'web': 'وب‌سایت',
    'api': 'API',
    'gateway': 'درگاه مدل‌ها',
}

_CACHE_KEY = 'cache:status:kuma'
_CACHE_TTL = 60
_LAST_GOOD_KEY = 'status:kuma:last_good'
_FAIL_KEY = 'status:kuma:fail'
_FAIL_TTL = 60
_BEATS_KEPT = 30
_VALID_SEVERITY = {'info', 'warning', 'critical'}


def _kuma_base_url() -> str:
    return os.getenv('KUMA_BASE_URL', '').strip().rstrip('/')


def _kuma_slug() -> str:
    return os.getenv('KUMA_STATUS_SLUG', 'sanjabai').strip()


def _support_info() -> dict[str, str | None]:
    """Support contacts for the public status page, read from env at request
    time so a redeploy of .env takes effect without a code change. Empty or
    unset values become None so the UI can hide the corresponding link."""
    return {
        'email': os.getenv('SUPPORT_EMAIL', '').strip() or None,
        'telegram': os.getenv('SUPPORT_TELEGRAM', '').strip() or None,
    }


# ── Kuma fetch + defensive parse ─────────────────────────────────────────
# Kuma's status-page JSON shape has drifted between releases (target here is
# 2.5.0); every access below goes through .get() with a default and nothing
# in this section may raise past _fetch_kuma -- a single unexpected field
# must degrade that one monitor, never take down the whole response.

async def _fetch_kuma() -> dict[str, Any] | None:
    base = _kuma_base_url()
    if not base:
        return None
    slug = _kuma_slug()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=3)) as client:
            page_resp = await client.get(f'{base}/api/status-page/{slug}')
            page_resp.raise_for_status()
            hb_resp = await client.get(f'{base}/api/status-page/heartbeat/{slug}')
            hb_resp.raise_for_status()
            page = page_resp.json()
            hb = hb_resp.json()
    except Exception as e:
        logger.warning('kuma fetch failed: %s', e)
        return None

    try:
        return _parse_kuma(page, hb)
    except Exception as e:
        logger.warning('kuma parse failed: %s', e)
        return None


def _parse_beat(raw: dict) -> dict[str, Any] | None:
    try:
        status = raw.get('status')
        ping = raw.get('ping')
        return {
            't': raw.get('time'),
            'ok': status == 1,
            'pingMs': int(ping) if isinstance(ping, (int, float)) else None,
        }
    except Exception:
        return None


def _parse_kuma(page: dict, hb: dict) -> dict[str, Any]:
    id_to_name: dict[str, str] = {}
    for group in (page or {}).get('publicGroupList') or []:
        for mon in (group or {}).get('monitorList') or []:
            mid = mon.get('id') if isinstance(mon, dict) else None
            name = mon.get('name') if isinstance(mon, dict) else None
            if mid is None or not name:
                continue
            id_to_name[str(mid)] = str(name)

    heartbeat_list = (hb or {}).get('heartbeatList') or {}
    uptime_list = (hb or {}).get('uptimeList') or {}

    services: list[dict[str, Any]] = []
    for mid, name in id_to_name.items():
        label = MONITOR_LABELS.get(name)
        if not label:
            continue  # not in the allowlist -- never surface it publicly

        beats_raw = heartbeat_list.get(mid) or []
        beats = [b for b in (_parse_beat(r) for r in beats_raw[-_BEATS_KEPT:]) if b is not None]

        uptime24 = uptime_list.get(f'{mid}_24')
        try:
            uptime24 = float(uptime24) if uptime24 is not None else None
        except (TypeError, ValueError):
            uptime24 = None

        pings = [b['pingMs'] for b in beats if b.get('pingMs') is not None]
        avg_ping = int(sum(pings) / len(pings)) if pings else None

        last_ok = beats[-1]['ok'] if beats else None
        status_str = 'up' if last_ok is True else ('down' if last_ok is False else 'unknown')

        services.append({
            'key': name,
            'label': label,
            'status': status_str,
            'uptime24h': uptime24,
            'avgPingMs': avg_ping,
            'beats': beats,
        })

    return {'services': services, 'monitoringUp': True}


# ── Incident read (public) ───────────────────────────────────────────────

async def _get_active_incident() -> dict[str, Any] | None:
    if async_session is None:
        return None
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text(
                    'SELECT title, body, severity, started_at FROM status_incident '
                    'WHERE active = TRUE ORDER BY started_at DESC LIMIT 1'
                )
            )
            row = res.fetchone()
            if not row:
                return None
            return {
                'title': row.title,
                'body': row.body,
                'severity': row.severity,
                'startedAt': row.started_at,
            }
    except Exception as e:
        logger.warning('status_incident read failed: %s', e)
        return None


# ── Public endpoint ───────────────────────────────────────────────────────

@router.get('/status/summary')
async def status_summary(request: Request) -> JSONResponse:
    """Public, unauthenticated. Delegates to `_build_status_summary`, wrapped
    in a last-resort guard: if anything in the assembly path raises despite
    its own internal handling, this still answers 200 with an empty summary
    rather than propagating a 500 to an anonymous visitor.
    """
    try:
        return await _build_status_summary()
    except Exception as e:
        logger.error('status_summary: unexpected failure, degrading to empty: %s', e)
        payload = jsonable_encoder({
            'services': [], 'monitoringUp': False, 'stale': False, 'incident': None,
            'support': _support_info(),
            'generatedAt': datetime.now(timezone.utc),
        })
        return JSONResponse(payload)


async def _build_status_summary() -> JSONResponse:
    kuma_data: dict[str, Any] | None = None
    stale = False

    try:
        cached = await rds.get(_CACHE_KEY)
    except Exception:
        cached = None
    if cached:
        try:
            kuma_data = json.loads(cached)
        except Exception:
            kuma_data = None

    base = _kuma_base_url()
    if kuma_data is None and base:
        try:
            failing = await rds.get(_FAIL_KEY)
        except Exception:
            failing = None
        if not failing:
            fresh = await _fetch_kuma()
            if fresh is not None:
                kuma_data = fresh
                try:
                    payload = json.dumps(fresh, default=str)
                    await rds.setex(_CACHE_KEY, _CACHE_TTL, payload)
                    await rds.set(_LAST_GOOD_KEY, payload)
                except Exception:
                    pass
            else:
                try:
                    await rds.setex(_FAIL_KEY, _FAIL_TTL, '1')
                except Exception:
                    pass

    if kuma_data is None and base:
        # Fetch failed (or is in negative-cache cooldown): serve the last
        # known-good snapshot, marked stale, instead of an empty page.
        try:
            last_good = await rds.get(_LAST_GOOD_KEY)
        except Exception:
            last_good = None
        if last_good:
            try:
                kuma_data = json.loads(last_good)
                stale = True
            except Exception:
                kuma_data = None

    if kuma_data is None:
        services: list[dict[str, Any]] = []
        monitoring_up = False
    else:
        services = kuma_data.get('services') or []
        monitoring_up = bool(kuma_data.get('monitoringUp'))

    incident = await _get_active_incident()

    payload = jsonable_encoder({
        'services': services,
        'monitoringUp': monitoring_up,
        'stale': stale,
        'incident': incident,
        'support': _support_info(),
        'generatedAt': datetime.now(timezone.utc),
    })
    return JSONResponse(payload)


# ── Admin incident management ────────────────────────────────────────────

@router.post('/admin/status/incident')
async def upsert_incident(request: Request, payload: dict[str, Any]) -> JSONResponse:
    """Create the active incident, or update it if one is already active.

    There is intentionally at most one active incident at a time -- the
    status page shows a single banner, not a feed.
    """
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    title = str(payload.get('title') or '').strip()
    if not title:
        return JSONResponse({'detail': 'عنوان الزامی است'}, status_code=400)
    body = str(payload.get('body') or '')
    severity = str(payload.get('severity') or 'warning')
    if severity not in _VALID_SEVERITY:
        return JSONResponse({'detail': 'سطح اعلان نامعتبر است'}, status_code=400)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                'SELECT id FROM status_incident WHERE active = TRUE '
                'ORDER BY started_at DESC LIMIT 1'
            )
        )
        row = res.fetchone()
        if row:
            incident_id = row.id
            await session.execute(
                sqlalchemy.text(
                    'UPDATE status_incident SET title = :t, body = :b, '
                    'severity = :s, updated_at = now() WHERE id = :id'
                ),
                {'t': title, 'b': body, 's': severity, 'id': incident_id},
            )
            action = 'status_incident.update'
        else:
            ins = await session.execute(
                sqlalchemy.text(
                    'INSERT INTO status_incident (title, body, severity) '
                    'VALUES (:t, :b, :s) RETURNING id'
                ),
                {'t': title, 'b': body, 's': severity},
            )
            incident_id = ins.scalar_one()
            action = 'status_incident.create'
        await session.commit()

    await _write_audit_log(
        action, target_type='status_incident', target_id=incident_id,
        details={'title': title, 'severity': severity}, request=request,
    )
    return JSONResponse({'status': 'ok', 'id': incident_id})


@router.delete('/admin/status/incident')
async def resolve_incident(request: Request) -> JSONResponse:
    """Resolve the currently active incident, if any."""
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)
    if async_session is None:
        return JSONResponse({'detail': 'پایگاه داده در دسترس نیست'}, status_code=500)

    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text(
                "UPDATE status_incident SET active = FALSE, resolved_at = now(), "
                "updated_at = now() WHERE active = TRUE RETURNING id"
            )
        )
        row = res.fetchone()
        await session.commit()

    if row:
        await _write_audit_log(
            'status_incident.resolve', target_type='status_incident',
            target_id=row.id, request=request,
        )
    return JSONResponse({'status': 'ok'})
