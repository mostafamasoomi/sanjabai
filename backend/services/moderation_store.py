"""Phase J — content safety, layer 2: everything with an I/O dependency.

Split out of services/moderation.py (563 lines, house cap 500) alongside
services/moderation_rules.py -- see that module's docstring for why the
split is by concern. This half owns the Postgres reads/writes
(``moderation_rule``, ``moderation_event``, ``app_setting``), the Redis
config cache and restriction key, the Telegram alert and the optional model
pass. Every function here is the kind that can fail in production, which is
precisely why they live behind :func:`services.moderation.screen_request`'s
fail-safe: none of them may ever decide a request by raising.

House rule: NEVER SMTP. All four outbound SMTP ports are blocked on this
host, so an email alert would be a silent no-op -- alerts go through the
same Telegram bot security.py's lockout alert and watchdog.py already use.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict
from typing import Any

import sqlalchemy

from database import async_session, rds
from services.moderation_rules import (
    MAX_SNIPPET_CHARS,
    Config,
    Rule,
    Verdict,
)

logger = logging.getLogger('moderation')

_SETTING_KEYS = (
    'moderation_enabled', 'moderation_block_severity',
    'moderation_model_sample_rate', 'moderation_model_on_hit',
    'moderation_model', 'moderation_retention_days',
)
_CONFIG_CACHE_KEY = 'cache:moderation:config'
_CONFIG_TTL_SECONDS = 60
_RESTRICT_KEY = 'moderation:restrict:{}'
RESTRICT_TTL_SECONDS = 30 * 24 * 3600
_PURGE_LOCK_KEY = 'moderation:purge:lock'

def _coerce(value: Any, default: Any) -> Any:
    """``app_setting.value`` is JSONB and arrives either already decoded or
    as a JSON string depending on the driver; accept both, default on the
    unexpected."""
    if value is None:
        return default
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            pass
    try:
        if isinstance(default, bool):
            if not isinstance(value, (bool, int, float)):
                return default
            return bool(value)
        if isinstance(default, float):
            return max(0.0, min(1.0, float(value)))
        if isinstance(default, int):
            return int(value)
        return str(value) if isinstance(value, (str, int, float)) else default
    except Exception:
        return default

_SQL_RULES = sqlalchemy.text(
    'SELECT id, pattern, category, severity, enabled, notes '
    'FROM moderation_rule WHERE enabled = true ORDER BY id'
)
_SQL_SETTINGS = sqlalchemy.text(
    'SELECT key AS setting_key, value FROM app_setting WHERE key = ANY(:keys)'
)


async def _load_config() -> Config:
    """Rules + settings, cached in Redis for 60s. Raises on a real DB
    failure, deliberately: :func:`screen_request` turns that into the
    fail-safe verdict, so an unreadable rule list is loud rather than
    silently behaving like an empty one."""
    try:
        cached = await rds.get(_CONFIG_CACHE_KEY)
    except Exception as e:
        logger.warning('moderation: config cache read failed: %s', e)
        cached = None
    if cached:
        d = json.loads(cached)
        return Config(rules=tuple(Rule(**r) for r in d.pop('rules')), **d)

    if async_session is None:
        raise RuntimeError('moderation: no database session')
    async with async_session() as session:
        s_res = await session.execute(_SQL_SETTINGS, {'keys': list(_SETTING_KEYS)})
        raw = {r.setting_key: r.value for r in s_res.fetchall()}
        enabled = _coerce(raw.get('moderation_enabled'), True)
        rules: tuple[Rule, ...] = ()
        if enabled:
            r_res = await session.execute(_SQL_RULES)
            rules = tuple(
                Rule(id=int(r.id), pattern=r.pattern, category=r.category,
                     severity=r.severity, enabled=bool(r.enabled),
                     notes=r.notes or '')
                for r in r_res.fetchall()
            )
    cfg = Config(
        enabled=enabled, rules=rules,
        block_severity=_coerce(raw.get('moderation_block_severity'), 'high'),
        model_sample_rate=_coerce(raw.get('moderation_model_sample_rate'), 0.0),
        model_on_hit=_coerce(raw.get('moderation_model_on_hit'), True),
        model=_coerce(raw.get('moderation_model'), ''),
        retention_days=_coerce(raw.get('moderation_retention_days'), 90),
    )
    try:
        await rds.setex(_CONFIG_CACHE_KEY, _CONFIG_TTL_SECONDS,
                        json.dumps(asdict(cfg)))
    except Exception as e:
        logger.warning('moderation: config cache write failed: %s', e)
    return cfg


async def invalidate_config_cache() -> None:
    """Called by admin_moderation.py after every rule write so an edit in
    the panel takes effect now, not up to 60 seconds later."""
    try:
        await rds.delete(_CONFIG_CACHE_KEY)
    except Exception as e:
        logger.warning('moderation: config cache invalidate failed: %s', e)

# ── Restriction key (admin `restrict` action) ─────────────────────────────

async def _is_restricted(uid: int) -> bool:
    """True while an admin 'restrict' action is in force. Redis, not a new
    column: the durable record is the ``audit_logs`` row admin_moderation.py
    writes (one audit trail, not two), and if Redis is lost the restriction
    lapses -- the same ALLOW-shaped failure the rest of this module takes.
    Consulted only after a rule hit, so a clean request pays nothing."""
    try:
        return bool(await rds.get(_RESTRICT_KEY.format(int(uid))))
    except Exception as e:
        logger.warning('moderation: restriction lookup failed uid=%s: %s', uid, e)
        return False

async def set_restricted(uid: int, on: bool = True) -> bool:
    """Set (or clear) the restriction key :func:`_is_restricted` reads.

    The write side of the admin panel's `restrict` action
    (admin_moderation.py::user_action). Deliberately Redis and not a new
    users column, for the same reason the read side is: the DURABLE record
    of the action is the ``audit_logs`` row the caller writes, so there is
    exactly one audit trail, and losing Redis lets a restriction lapse --
    the same ALLOW-shaped failure every other path in this feature takes,
    rather than a user stuck in a state nothing can see.

    Best-effort like every other Redis touch here: ``False`` means Redis
    refused. The caller has already written its audit row and notified the
    user, so a False is worth logging, never worth 500-ing an admin action.
    """
    key = _RESTRICT_KEY.format(int(uid))
    try:
        if on:
            await rds.setex(key, RESTRICT_TTL_SECONDS, '1')
        else:
            await rds.delete(key)
        return True
    except Exception as e:
        logger.warning('moderation: restriction write failed uid=%s on=%s: %s',
                       uid, on, e)
        return False


_SQL_INSERT_EVENT = sqlalchemy.text(
    'INSERT INTO moderation_event '
    '(user_id, conversation_id, category, severity, rule_id, snippet, decision) '
    'VALUES (:uid, :cid, :cat, :sev, :rid, :snip, :dec)'
)
_SQL_PURGE_EVENTS = sqlalchemy.text(
    'DELETE FROM moderation_event '
    'WHERE created_at < now() - make_interval(days => :days)'
)


async def _claim_purge() -> bool:
    try:
        return bool(await rds.set(_PURGE_LOCK_KEY, '1', ex=3600, nx=True))
    except Exception:
        return False


async def _record_event(uid: int, conversation_id: int | None, verdict: Verdict,
                        retention_days: int = 90) -> None:
    """Append one ``moderation_event`` row; best-effort, since a logging
    failure must never change what the user gets. Also enforces the
    migrations/0043 retention policy, at most once an hour (Redis-guarded)
    on the already-rare flag/block path -- a retention policy nothing
    executes is not a policy."""
    if async_session is None:
        return
    try:
        async with async_session() as session:
            await session.execute(_SQL_INSERT_EVENT, {
                'uid': int(uid) or None,
                'cid': conversation_id,
                'cat': (verdict.category or 'other')[:64],
                'sev': verdict.severity or 'low',
                'rid': verdict.rule_id,
                'snip': (verdict.snippet or '')[:MAX_SNIPPET_CHARS],
                'dec': verdict.decision,
            })
            if await _claim_purge():
                await session.execute(_SQL_PURGE_EVENTS,
                                      {'days': max(1, int(retention_days))})
            await session.commit()
    except Exception as e:
        logger.warning('moderation: event write failed uid=%s: %s', uid, e)

async def _send_alert(uid: int, verdict: Verdict) -> None:
    """Telegram, never email: all four outbound SMTP ports are blocked on
    this host, so an email alert would be a silent no-op. Reuses the bot the
    stack already alerts through (security.py's lockout alert, watchdog.py)
    -- same WATCHDOG_BOT_TOKEN / WATCHDOG_CHAT_ID pair."""
    bot_token = os.getenv('WATCHDOG_BOT_TOKEN', '')
    chat_id = os.getenv('WATCHDOG_CHAT_ID', '')
    if not bot_token or not chat_id:
        return
    icon = '🛠' if verdict.failed else {'block': '⛔'}.get(verdict.decision, '⚠️')
    lines = [
        f'{icon} Sanjabai moderation — {verdict.decision}',
        f'user: {uid}',
        f'category: {verdict.category or "-"}  severity: {verdict.severity or "-"}',
        f'rule: {verdict.rule_id if verdict.rule_id is not None else "-"}',
    ]
    if verdict.failed:
        lines.append(f'DETECTOR FAILED (request was allowed): {verdict.detail[:200]}')
    if verdict.snippet:
        lines.append(f'snippet: {verdict.snippet[:MAX_SNIPPET_CHARS]}')
    lines.append(time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()))
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f'https://api.telegram.org/bot{bot_token}/sendMessage',
                json={'chat_id': chat_id, 'text': '\n'.join(lines)},
            )
    except Exception as e:
        logger.warning('moderation: telegram alert failed: %s', e)

_MODEL_SYSTEM_FA = (
    'تو یک داور ایمنی محتوا هستی. فقط و فقط یکی از سه کلمهٔ block، flag یا '
    'allow را برگردان و هیچ توضیحی ننویس. block برای درخواست واقعیِ انجام '
    'کار غیرقانونی یا آسیب‌رسان، flag برای موارد مشکوک، و allow برای پرسش '
    'خبری، آموزشی، داستانی یا تاریخی.'
)


async def _model_review(text: str, model: str) -> str | None:
    """Layer 2: ask a model whether the *context* is actually harmful. Called
    only when layer 1 hit, or on the sampled fraction -- never on every
    message. ``'block'``/``'flag'``/``'allow'``, or ``None`` when it could
    not answer, which every caller reads as "no opinion"."""
    if not model:
        return None
    try:
        from chat_models import _resolve_provider
        from database import _http
        provider = await _resolve_provider(model)
        r = await _http.post(
            f'{provider.v1}/chat/completions',
            json={'model': model, 'max_tokens': 5, 'temperature': 0,
                  'messages': [{'role': 'system', 'content': _MODEL_SYSTEM_FA},
                               {'role': 'user', 'content': text[:2000]}]},
            headers={**provider.headers(), 'Accept': 'application/json'},
            timeout=20,
        )
        if r.status_code != 200:
            return None
        out = (r.json()['choices'][0]['message']['content'] or '').strip().lower()
    except Exception as e:
        logger.warning('moderation: model layer failed: %s', e)
        return None
    for word in ('block', 'flag', 'allow'):
        if word in out:
            return word
    return None
