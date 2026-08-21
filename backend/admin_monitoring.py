"""
Operator monitoring dashboard: `GET /admin/monitoring`.

Every number here comes from a real data source already being written
elsewhere in the codebase -- nothing is invented. In particular:

  * Upstream liveness reuses `providers.upstream_alive` (the same check
    `/models/health` uses), run concurrently with a 15s timeout so 9Router's
    legitimate ~11s response time is never mistaken for a dead tunnel.
  * Model status reuses `model_health.health_map()`.
  * Traffic error rate comes from `model_health_event` (source='traffic'),
    NOT `usage_events.upstream_status` -- chat.py only ever writes
    `upstream_status='success'` there (see chat.py, `_record_usage`), so
    computing an error rate from that column would silently read 0% forever.
  * The billing.shortfall and billing.estimated sections surface
    `meta.estimated` / `meta.listed_cost` / `meta.shortfall`, which chat.py
    has been writing on every usage event all along with nothing reading
    them back until now.
  * `wallet.negativeBalances` / `wallet.ledgerMismatches` reuse the exact SQL
    already written and proven in `watchdog.py` (the financial watchdog that
    has never been run in production before this change), with LIMIT 20.
  * `kuma` is read-only from the Redis keys `status_page.py` writes -- this
    endpoint never fetches Kuma itself, so a slow/broken Kuma can only ever
    cost `status_page.py` a timeout, never this dashboard.

Each section is computed independently and swallows its own failure: one
broken sub-query yields that section empty (with an `error: true` flag),
never a 500 for the whole endpoint.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from database import async_session, rds
from dependencies import admin_required
from model_health import health_map
from providers import configured_providers, upstream_alive
from status_page import _CACHE_KEY as _KUMA_CACHE_KEY
from status_page import _FAIL_KEY as _KUMA_FAIL_KEY
from status_page import _LAST_GOOD_KEY as _KUMA_LAST_GOOD_KEY

logger = logging.getLogger('admin_monitoring')

router = APIRouter()

_CACHE_KEY = 'cache:admin:monitoring'
_CACHE_TTL = 30


# ── Sections ──────────────────────────────────────────────────────────────

async def _upstreams_section() -> list[dict[str, Any]]:
    try:
        providers_list = configured_providers()
        alive_results = await asyncio.gather(
            *(upstream_alive(p, timeout=15.0) for p in providers_list),
            return_exceptions=True,
        )
        counts: dict[str, dict[str, int]] = {}
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(sqlalchemy.text(
                    'SELECT provider, status, COUNT(*) AS n FROM model_health_state '
                    'GROUP BY 1, 2'
                ))
                for r in res.fetchall():
                    counts.setdefault(r.provider, {})[r.status] = r.n

        out = []
        for p, r in zip(providers_list, alive_results):
            if isinstance(r, BaseException):
                ok, latency, error = False, None, type(r).__name__
            else:
                ok, latency, error = r.ok, r.latency_ms, r.error
            out.append({
                'name': p.name,
                'alive': ok,
                'latencyMs': latency,
                'error': error,
                'modelStatusCounts': counts.get(p.name, {}),
            })
        return out
    except Exception as e:
        # Re-raise instead of returning []: the caller gathers with
        # return_exceptions=True and needs to tell "no upstreams configured"
        # apart from "the query blew up". A bare [] made those identical and
        # the admin had no way to know the panel was lying.
        logger.warning('admin_monitoring: upstreams section failed: %s', e)
        raise


async def _models_section() -> list[dict[str, Any]]:
    try:
        states = await health_map()
        names: dict[str, str] = {}
        if async_session is not None:
            async with async_session() as session:
                res = await session.execute(sqlalchemy.text(
                    'SELECT id, provider_model_id, display_name, provider FROM model_catalog'
                ))
                for r in res.fetchall():
                    names[str(r.provider_model_id)] = r.display_name
                    names[str(r.id)] = r.display_name
        return [
            {'id': model_id, 'displayName': names.get(model_id, model_id), **state}
            for model_id, state in sorted(states.items())
        ]
    except Exception as e:
        # See _upstreams_section: raise so the failure reaches the response
        # as an explicit flag rather than an empty list.
        logger.warning('admin_monitoring: models section failed: %s', e)
        raise


async def _traffic_section() -> dict[str, Any]:
    if async_session is None:
        return {'hours': []}
    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                """
                SELECT date_trunc('hour', created_at) AS hour,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE NOT ok) AS errors,
                       PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY latency_ms)
                           FILTER (WHERE ok) AS p50,
                       PERCENTILE_DISC(0.95) WITHIN GROUP (ORDER BY latency_ms)
                           FILTER (WHERE ok) AS p95
                  FROM model_health_event
                 WHERE source = 'traffic' AND created_at > now() - interval '24 hours'
                 GROUP BY 1
                 ORDER BY 1
                """
            ))
            hours = [
                {'hour': r.hour, 'total': r.total, 'errors': r.errors,
                 'p50Ms': r.p50, 'p95Ms': r.p95}
                for r in res.fetchall()
            ]
            return {'hours': hours}
    except Exception as e:
        logger.warning('admin_monitoring: traffic section failed: %s', e)
        return {'hours': [], 'error': True}


async def _volume_section() -> dict[str, Any]:
    if async_session is None:
        return {'days': []}
    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                """
                SELECT date_trunc('day', created_at) AS day,
                       COUNT(*) AS requests,
                       COALESCE(SUM(charged_amount), 0) AS revenue
                  FROM usage_events
                 WHERE created_at > now() - interval '7 days'
                 GROUP BY 1
                 ORDER BY 1
                """
            ))
            days = [
                {'day': r.day, 'requests': r.requests, 'revenue': r.revenue}
                for r in res.fetchall()
            ]
            return {'days': days}
    except Exception as e:
        logger.warning('admin_monitoring: volume section failed: %s', e)
        return {'days': [], 'error': True}


async def _billing_section() -> dict[str, Any]:
    out: dict[str, Any] = {
        'shortfall': {'count': 0, 'sum': 0, 'recent': []},
        'estimated': {'count24h': 0, 'count30d': 0, 'recent': []},
    }
    if async_session is None:
        return out

    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                """
                SELECT COUNT(*) AS cnt,
                       COALESCE(SUM((meta->>'shortfall')::bigint), 0) AS total
                  FROM usage_events
                 WHERE meta ? 'shortfall' AND created_at > now() - interval '30 days'
                """
            ))
            row = res.fetchone()
            if row:
                out['shortfall']['count'] = row.cnt
                out['shortfall']['sum'] = row.total

            res2 = await session.execute(sqlalchemy.text(
                """
                SELECT user_id, model, charged_amount,
                       meta->>'listed_cost' AS listed_cost,
                       meta->>'shortfall' AS shortfall,
                       created_at
                  FROM usage_events
                 WHERE meta ? 'shortfall' AND created_at > now() - interval '30 days'
                 ORDER BY created_at DESC
                 LIMIT 50
                """
            ))
            out['shortfall']['recent'] = [
                {'userId': r.user_id, 'model': r.model, 'chargedAmount': r.charged_amount,
                 'listedCost': r.listed_cost, 'shortfall': r.shortfall, 'createdAt': r.created_at}
                for r in res2.fetchall()
            ]
    except Exception as e:
        logger.warning('admin_monitoring: billing.shortfall section failed: %s', e)
        out['shortfall'] = {'count': 0, 'sum': 0, 'recent': [], 'error': True}

    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                """
                SELECT COUNT(*) FILTER (WHERE created_at > now() - interval '24 hours') AS c24,
                       COUNT(*) FILTER (WHERE created_at > now() - interval '30 days') AS c30
                  FROM usage_events
                 WHERE (meta->>'estimated') = 'true' AND created_at > now() - interval '30 days'
                """
            ))
            row = res.fetchone()
            if row:
                out['estimated']['count24h'] = row.c24
                out['estimated']['count30d'] = row.c30

            res2 = await session.execute(sqlalchemy.text(
                """
                SELECT user_id, model, charged_amount, created_at
                  FROM usage_events
                 WHERE (meta->>'estimated') = 'true'
                 ORDER BY created_at DESC
                 LIMIT 50
                """
            ))
            out['estimated']['recent'] = [
                {'userId': r.user_id, 'model': r.model, 'chargedAmount': r.charged_amount,
                 'createdAt': r.created_at}
                for r in res2.fetchall()
            ]
    except Exception as e:
        logger.warning('admin_monitoring: billing.estimated section failed: %s', e)
        out['estimated'] = {'count24h': 0, 'count30d': 0, 'recent': [], 'error': True}

    return out


async def _wallet_section() -> dict[str, Any]:
    out: dict[str, Any] = {'negativeBalances': [], 'ledgerMismatches': []}
    if async_session is None:
        return out

    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                """
                SELECT user_id, SUM(amount) AS balance
                  FROM ledger GROUP BY user_id HAVING SUM(amount) < 0
                 LIMIT 20
                """
            ))
            out['negativeBalances'] = [
                {'userId': r.user_id, 'balance': r.balance} for r in res.fetchall()
            ]
    except Exception as e:
        logger.warning('admin_monitoring: wallet.negativeBalances failed: %s', e)
        out['negativeBalances'] = []
        out['negativeBalancesError'] = True

    try:
        async with async_session() as session:
            res = await session.execute(sqlalchemy.text(
                """
                SELECT w.user_id, w.balance AS wallet_balance,
                       COALESCE(l.sum_amount, 0) AS ledger_balance,
                       w.balance - COALESCE(l.sum_amount, 0) AS delta
                  FROM wallet w
                  LEFT JOIN (
                      SELECT user_id, SUM(amount) AS sum_amount FROM ledger GROUP BY user_id
                  ) l ON w.user_id = l.user_id
                 WHERE w.balance != COALESCE(l.sum_amount, 0)
                 LIMIT 20
                """
            ))
            out['ledgerMismatches'] = [
                {'userId': r.user_id, 'walletBalance': r.wallet_balance,
                 'ledgerBalance': r.ledger_balance, 'delta': r.delta}
                for r in res.fetchall()
            ]
    except Exception as e:
        logger.warning('admin_monitoring: wallet.ledgerMismatches failed: %s', e)
        out['ledgerMismatches'] = []
        out['ledgerMismatchesError'] = True

    return out


async def _kuma_section() -> dict[str, Any]:
    """Read-only from Redis. Never fetches Kuma -- status_page.py owns that."""
    # A Redis failure used to be indistinguishable from "monitoring is really
    # down": both produced monitoringUp=False. Track read failures so the
    # response can say "we could not find out" instead of asserting a state
    # we never observed.
    read_errors = 0

    try:
        cached = await rds.get(_KUMA_CACHE_KEY)
        if cached:
            data = json.loads(cached)
            return {'monitoringUp': bool(data.get('monitoringUp')), 'stale': False, 'source': 'cache'}
    except Exception as e:
        logger.warning('admin_monitoring: kuma cache read failed: %s', e)
        read_errors += 1

    try:
        failing = await rds.get(_KUMA_FAIL_KEY)
    except Exception as e:
        logger.warning('admin_monitoring: kuma failing-flag read failed: %s', e)
        read_errors += 1
        failing = None

    try:
        last_good = await rds.get(_KUMA_LAST_GOOD_KEY)
    except Exception as e:
        logger.warning('admin_monitoring: kuma last-good read failed: %s', e)
        read_errors += 1
        last_good = None

    if last_good:
        try:
            data = json.loads(last_good)
            return {
                'monitoringUp': bool(data.get('monitoringUp')),
                'stale': True,
                'source': 'last_good',
                'failing': bool(failing),
            }
        except Exception:
            pass

    out: dict[str, Any] = {
        'monitoringUp': False, 'stale': False, 'source': None, 'failing': bool(failing),
    }
    # Every Redis read failed -- monitoringUp=False below is "unknown", not
    # an observation. Flag it so the panel does not present it as fact.
    if read_errors >= 3:
        out['error'] = True
    return out


def _safe(value: Any, default: Any, *, name: str = '', failures: list[str] | None = None) -> Any:
    """Substitute ``default`` when a gathered section raised.

    Also records the failure: list-shaped sections cannot carry an ``error``
    key of their own, so the endpoint exposes a top-level ``errors`` list.
    Dict-shaped defaults additionally get ``error: True`` inline, matching the
    convention the traffic/volume/billing sections already use.
    """
    if not isinstance(value, BaseException):
        return value
    logger.warning('admin_monitoring: %s section raised: %r', name or 'unknown', value)
    if failures is not None and name:
        failures.append(name)
    if isinstance(default, dict):
        return {**default, 'error': True}
    return default


def _self_reported_errors(payload: dict[str, Any]) -> list[str]:
    """Section keys that flagged their own failure inline.

    Sections signal trouble in three shapes that predate this helper: a
    top-level ``error``, a ``<field>Error`` marker (wallet), or a nested
    sub-dict carrying ``error`` (billing). Collect all three so the admin has
    one place to look instead of three.
    """
    found: list[str] = []
    for key, value in payload.items():
        if not isinstance(value, dict):
            continue
        if value.get('error') or any(
            k.endswith('Error') and v for k, v in value.items()
        ):
            found.append(key)
            continue
        if any(isinstance(v, dict) and v.get('error') for v in value.values()):
            found.append(key)
    return found


# ── Endpoint ─────────────────────────────────────────────────────────────

@router.get('/admin/monitoring')
async def admin_monitoring(request: Request) -> JSONResponse:
    if not await admin_required(request):
        return JSONResponse({'detail': 'لطفاً وارد حساب خود شوید'}, status_code=401)

    try:
        cached = await rds.get(_CACHE_KEY)
    except Exception:
        cached = None
    if cached:
        try:
            return JSONResponse(json.loads(cached))
        except Exception:
            pass

    upstreams, models, traffic, volume, billing, wallet, kuma = await asyncio.gather(
        _upstreams_section(),
        _models_section(),
        _traffic_section(),
        _volume_section(),
        _billing_section(),
        _wallet_section(),
        _kuma_section(),
        return_exceptions=True,
    )

    failures: list[str] = []
    sections = {
        'upstreams': _safe(upstreams, [], name='upstreams', failures=failures),
        'models': _safe(models, [], name='models', failures=failures),
        'traffic': _safe(traffic, {'hours': []}, name='traffic', failures=failures),
        'volume': _safe(volume, {'days': []}, name='volume', failures=failures),
        'billing': _safe(billing, {
            'shortfall': {'count': 0, 'sum': 0, 'recent': []},
            'estimated': {'count24h': 0, 'count30d': 0, 'recent': []},
        }, name='billing', failures=failures),
        'wallet': _safe(
            wallet, {'negativeBalances': [], 'ledgerMismatches': []},
            name='wallet', failures=failures,
        ),
        'kuma': _safe(
            kuma, {'monitoringUp': False, 'stale': False},
            name='kuma', failures=failures,
        ),
    }

    # `errors` names every section the admin should NOT trust, whether it
    # raised (captured above) or reported trouble inline. Without it, a failed
    # query is served as an empty list and reads as "there is no data".
    errors = sorted(set(failures) | set(_self_reported_errors(sections)))

    payload = jsonable_encoder({
        **sections,
        'errors': errors,
        'generatedAt': datetime.now(timezone.utc),
    })
    try:
        await rds.setex(_CACHE_KEY, _CACHE_TTL, json.dumps(payload, default=str))
    except Exception:
        pass
    return JSONResponse(payload)
