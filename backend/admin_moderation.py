"""Phase J — the admin surface over content safety.

«اگه یه یوزر چیزای ممنوعه بیاد سرچ کنه ما باید بفهمیم و هشدار بگیریم و
بتونیم جلوشو بگیریم — همه‌شم جزئی از پنل ادمین باید باشه.»

The detector itself is backend/services/moderation.py; this module is only
the panel's read/write surface over its two tables. The contract below was
frozen by the owner so the frontend could be built against it in parallel:

  GET    /admin/moderation/events            {items,total,page,limit}
  GET    /admin/moderation/rules             {items}
  POST   /admin/moderation/rules             {status:'ok', id}
  POST   /admin/moderation/rules/{id}        {status:'ok', id}
  DELETE /admin/moderation/rules/{id}        {status:'deleted'}
  GET    /admin/moderation/users/{uid}       {risk_score,event_count,recent}
  POST   /admin/moderation/users/{uid}/action {status:'ok'}

MONKEYPATCH CONTRACT (admin.py's module docstring): every route below gates
on ``admin.admin_required(request)`` reached through a plain ``import
admin`` at CALL time, never ``from admin import admin_required``. Capturing
the function into this module's namespace would make
``patch('admin.admin_required', ...)`` silently stop gating these routes
while every such test kept passing.

ONE AUDIT TRAIL. Every user action writes through the existing
``dependencies._write_audit_log`` into ``audit_logs``. There is no second
audit table, and ``moderation_event`` is not one -- that table records what
a *user* asked for, this records what an *admin* did about it.

WHAT THE THREE ACTIONS ACTUALLY DO -- no dead buttons:
  warn      one ``notifications`` row for the user + an audit row. Nothing
            else changes; the user can keep chatting.
  restrict  the Redis key services/moderation.py::_is_restricted reads, for
            30 days. While it is set, ANY rule hit blocks that user instead
            of only hits at or above moderation_block_severity. Lifted by
            letting it expire or by deleting the key; the durable record is
            the audit row.
  suspend   ``users.banned = true`` -- the existing, already-enforced ban
            (dependencies.py rejects a banned user's session on every
            request, auth.py refuses login). Lifted with the existing
            POST /admin/users/{uid}/ban toggle in admin_users.py, which is
            deliberately NOT duplicated here.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

import admin
from i18n import err
from database import async_session, rds
from dependencies import _write_audit_log
from services.moderation import (
    DECISIONS,
    MAX_SNIPPET_CHARS,
    SEVERITIES,
    invalidate_config_cache,
    set_restricted,
)

logger = logging.getLogger('admin_moderation')

router = APIRouter()

ACTIONS = ('warn', 'restrict', 'suspend')
MAX_PATTERN_CHARS = 200
MAX_PAGE_LIMIT = 200

def _no_db() -> JSONResponse:
    """A fresh 500 every time -- see :func:`_denied` for why."""
    return err('پایگاه داده در دسترس نیست', 'Database is unavailable.', 500)


def _denied() -> JSONResponse:
    """A FRESH 401 every time, never one shared module-level Response.

    A Response object is mutated in place as it travels back out through the
    middleware stack: app.py wraps every response in GZip -> SecurityHeaders
    -> CSP -> ... , each of which sets headers on the object it is handed.
    Return the same instance twice and the second caller gets the first
    call's accumulated headers -- observed here as `vary: Accept-Encoding,
    Accept-Encoding, Accept-Encoding` and, once GZip has stamped
    `content-encoding: gzip` on it, an UNCOMPRESSED body still labelled
    gzip, which the panel cannot decode at all. So the second and every
    later unauthenticated hit on this section would fail as a decode error
    rather than a clean 401. Cheap to build, so build it per request.
    """
    return err('لطفاً وارد حساب خود شوید', 'Please sign in to your account.', 401)


def _bad(fa: str, en: str) -> JSONResponse:
    return err(fa, en, 400)


# ── Regex safety ──────────────────────────────────────────────────────────
# Two shapes that make catastrophic backtracking easy: a quantified group
# whose body is itself quantified ((a+)+), and stacked quantifiers (a**).
_NESTED_QUANT = re.compile(r'\((?![?]:?[=!<])[^()]*[+*}][^()]*\)\s*[+*{]')
_STACKED_QUANT = re.compile(r'[+*}]\s*[+*]')
_BACKREF = re.compile(r'\\[1-9]')
# Adversarial subject for the store-time smoke test: a long run that ALMOST
# matches, in both scripts.
_REDOS_PROBE = ('a' * 40 + '!') * 2 + 'ا' * 40 + '!'
REDOS_PROBE_BUDGET_SECONDS = 0.025


def _validate_pattern_bi(pattern: Any) -> tuple[str, str] | None:
    """A ``(fa, en)`` error pair for a pattern we refuse to store, or ``None``.

    Bilingual body of :func:`validate_pattern`, split out so that function
    keeps returning a bare Persian string (its tested contract -- see
    tests/test_admin_moderation.py) while the HTTP-facing call sites here
    can still reach the English sibling.

    An admin-supplied regex is untrusted input that then runs on the hot
    path of every chat request, so a catastrophic-backtracking pattern is a
    self-inflicted denial of service. Four gates, cheapest first: length,
    structural shapes known to backtrack, compilability, and finally a real
    timed run against an adversarial subject.
    """
    if not isinstance(pattern, str) or not pattern.strip():
        return 'الگو نمی‌تواند خالی باشد.', 'The pattern cannot be empty.'
    if len(pattern) > MAX_PATTERN_CHARS:
        return (
            f'الگو نباید بیش از {MAX_PATTERN_CHARS} نویسه باشد.',
            f'The pattern must not exceed {MAX_PATTERN_CHARS} characters.',
        )
    if _BACKREF.search(pattern):
        return (
            'استفاده از ارجاع پس‌رو (\\1) در الگو مجاز نیست.',
            'Backreferences (\\1) are not allowed in the pattern.',
        )
    if _NESTED_QUANT.search(pattern) or _STACKED_QUANT.search(pattern):
        return (
            'الگو تکرارگر تودرتو دارد و می‌تواند سرویس را از کار بیندازد؛ ساده‌ترش کنید.',
            'The pattern has a nested quantifier that could take down the service; simplify it.',
        )
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f'الگوی نامعتبر است: {e}', f'Invalid pattern: {e}'
    started = time.monotonic()
    try:
        rx.search(_REDOS_PROBE)
    except Exception as e:  # pragma: no cover
        return f'الگوی نامعتبر است: {e}', f'Invalid pattern: {e}'
    if time.monotonic() - started > REDOS_PROBE_BUDGET_SECONDS:
        return (
            'اجرای الگو بیش از حد طول کشید؛ الگوی ساده‌تری بنویسید.',
            'The pattern took too long to run; write a simpler pattern.',
        )
    return None


def validate_pattern(pattern: Any) -> str | None:
    """Persian error for a pattern we refuse to store, or ``None``.

    Kept returning a bare string -- not the ``(fa, en)`` pair -- because
    tests/test_admin_moderation.py and tests/test_admin_moderation_api.py
    call this directly and assert on a string/``None``; see
    :func:`_validate_pattern_bi` for the bilingual version this wraps.
    """
    pair = _validate_pattern_bi(pattern)
    return pair[0] if pair else None


# ── Events ────────────────────────────────────────────────────────────────

_SQL_EVENTS = sqlalchemy.text(
    'SELECT e.id, e.user_id, u.email AS user_email, e.conversation_id, '
    '       e.category, e.severity, e.rule_id, e.snippet, e.decision, '
    '       e.created_at '
    'FROM moderation_event e LEFT JOIN users u ON u.id = e.user_id '
    'WHERE (CAST(:sev AS TEXT) IS NULL OR e.severity = :sev) '
    '  AND (CAST(:dec AS TEXT) IS NULL OR e.decision = :dec) '
    '  AND (CAST(:q AS TEXT) IS NULL OR e.snippet ILIKE :q '
    '       OR e.category ILIKE :q OR u.email ILIKE :q) '
    'ORDER BY e.created_at DESC, e.id DESC LIMIT :lim OFFSET :off'
)
_SQL_EVENTS_COUNT = sqlalchemy.text(
    'SELECT COUNT(*) AS c '
    'FROM moderation_event e LEFT JOIN users u ON u.id = e.user_id '
    'WHERE (CAST(:sev AS TEXT) IS NULL OR e.severity = :sev) '
    '  AND (CAST(:dec AS TEXT) IS NULL OR e.decision = :dec) '
    '  AND (CAST(:q AS TEXT) IS NULL OR e.snippet ILIKE :q '
    '       OR e.category ILIKE :q OR u.email ILIKE :q)'
)


@router.get('/admin/moderation/events')
async def list_events(request: Request, page: int = 1, limit: int = 50,
                      severity: str = '', decision: str = '',
                      q: str = '') -> JSONResponse:
    """Newest first. An unknown severity/decision is a 400 rather than a
    silently ignored filter -- an admin acting on a list they think is
    filtered is exactly the kind of lie this panel must not tell."""
    if not await admin.admin_required(request):
        return _denied()
    if severity and severity not in SEVERITIES:
        return _bad('شدت نامعتبر است.', 'Invalid severity.')
    if decision and decision not in DECISIONS:
        return _bad('تصمیم نامعتبر است.', 'Invalid decision.')
    page = max(1, int(page))
    limit = max(1, min(MAX_PAGE_LIMIT, int(limit)))
    params = {
        'sev': severity or None,
        'dec': decision or None,
        'q': f'%{q.strip()}%' if q and q.strip() else None,
        'lim': limit,
        'off': (page - 1) * limit,
    }
    if async_session is None:
        return _no_db()
    async with async_session() as session:
        rows = (await session.execute(_SQL_EVENTS, params)).fetchall()
        total = (await session.execute(_SQL_EVENTS_COUNT, params)).fetchone().c
    return JSONResponse(jsonable_encoder({
        'items': [dict(r._mapping) for r in rows],
        'total': total, 'page': page, 'limit': limit,
    }))


# ── Rules ─────────────────────────────────────────────────────────────────

_SQL_RULES = sqlalchemy.text(
    'SELECT id, pattern, category, severity, enabled, notes, updated_at '
    'FROM moderation_rule ORDER BY id'
)
_SQL_RULE_INSERT = sqlalchemy.text(
    'INSERT INTO moderation_rule (pattern, category, severity, enabled, notes) '
    'VALUES (:pattern, :category, :severity, :enabled, :notes) '
    'ON CONFLICT (pattern) DO NOTHING RETURNING id'
)
_SQL_RULE_UPDATE = sqlalchemy.text(
    'UPDATE moderation_rule SET '
    '  pattern  = COALESCE(CAST(:pattern AS TEXT), pattern), '
    '  category = COALESCE(CAST(:category AS TEXT), category), '
    '  severity = COALESCE(CAST(:severity AS TEXT), severity), '
    '  enabled  = COALESCE(CAST(:enabled AS BOOLEAN), enabled), '
    '  notes    = COALESCE(CAST(:notes AS TEXT), notes), '
    '  updated_at = now() '
    'WHERE id = :id RETURNING id'
)
_SQL_RULE_DELETE = sqlalchemy.text(
    'DELETE FROM moderation_rule WHERE id = :id RETURNING id'
)


@router.get('/admin/moderation/rules')
async def list_rules(request: Request) -> JSONResponse:
    if not await admin.admin_required(request):
        return _denied()
    if async_session is None:
        return _no_db()
    async with async_session() as session:
        rows = (await session.execute(_SQL_RULES)).fetchall()
    return JSONResponse(jsonable_encoder(
        {'items': [dict(r._mapping) for r in rows]}))


def _clean_rule_body(body: dict, *, require_pattern: bool) -> tuple[dict, tuple[str, str] | None]:
    """Shared validation for create and update. Returns (params, (fa, en) error)."""
    pattern = body.get('pattern')
    if pattern is None and not require_pattern:
        pat_val = None
    else:
        bad = _validate_pattern_bi(pattern)
        if bad:
            return {}, bad
        pat_val = pattern.strip()

    severity = body.get('severity')
    if severity is not None and severity not in SEVERITIES:
        return {}, ('شدت نامعتبر است؛ یکی از low، medium، high یا critical.',
                     'Invalid severity; must be one of low, medium, high, or critical.')
    category = body.get('category')
    if category is not None and (not isinstance(category, str)
                                 or not category.strip()):
        return {}, ('دسته نمی‌تواند خالی باشد.', 'Category cannot be empty.')
    enabled = body.get('enabled')
    if enabled is not None and not isinstance(enabled, bool):
        return {}, ('مقدار فعال/غیرفعال باید درست یا نادرست باشد.',
                     'The enabled value must be true or false.')
    notes = body.get('notes')
    if notes is not None and not isinstance(notes, str):
        return {}, ('توضیح باید متن باشد.', 'Notes must be text.')
    return {
        'pattern': pat_val,
        'category': category.strip()[:64] if isinstance(category, str) else None,
        'severity': severity,
        'enabled': enabled,
        'notes': notes[:500] if isinstance(notes, str) else None,
    }, None


@router.post('/admin/moderation/rules')
async def create_rule(request: Request) -> JSONResponse:
    if not await admin.admin_required(request):
        return _denied()
    body = await _json_body(request)
    params, bad_msg = _clean_rule_body(body, require_pattern=True)
    if bad_msg:
        return _bad(*bad_msg)
    if async_session is None:
        return _no_db()
    params = {
        'pattern': params['pattern'],
        'category': params['category'] or 'other',
        'severity': params['severity'] or 'medium',
        'enabled': True if params['enabled'] is None else params['enabled'],
        'notes': params['notes'] or '',
    }
    async with async_session() as session:
        row = (await session.execute(_SQL_RULE_INSERT, params)).fetchone()
        await session.commit()
    if row is None:
        return _bad('این الگو از قبل ثبت شده است.', 'This pattern is already registered.')
    await invalidate_config_cache()
    await _write_audit_log('admin.moderation.rule_create',
                           target_type='moderation_rule', target_id=row.id,
                           details=_audit_details(params), request=request)
    return JSONResponse({'status': 'ok', 'id': row.id})


@router.post('/admin/moderation/rules/{rule_id}')
async def update_rule(request: Request, rule_id: int) -> JSONResponse:
    if not await admin.admin_required(request):
        return _denied()
    body = await _json_body(request)
    params, bad_msg = _clean_rule_body(body, require_pattern=False)
    if bad_msg:
        return _bad(*bad_msg)
    if async_session is None:
        return _no_db()
    async with async_session() as session:
        row = (await session.execute(_SQL_RULE_UPDATE,
                                     {**params, 'id': rule_id})).fetchone()
        await session.commit()
    if row is None:
        return err('قاعده پیدا نشد.', 'Rule not found.', 404)
    await invalidate_config_cache()
    await _write_audit_log('admin.moderation.rule_update',
                           target_type='moderation_rule', target_id=rule_id,
                           details=_audit_details(params), request=request)
    return JSONResponse({'status': 'ok', 'id': rule_id})


@router.delete('/admin/moderation/rules/{rule_id}')
async def delete_rule(request: Request, rule_id: int) -> JSONResponse:
    if not await admin.admin_required(request):
        return _denied()
    if async_session is None:
        return _no_db()
    async with async_session() as session:
        row = (await session.execute(_SQL_RULE_DELETE, {'id': rule_id})).fetchone()
        await session.commit()
    if row is None:
        return err('قاعده پیدا نشد.', 'Rule not found.', 404)
    await invalidate_config_cache()
    await _write_audit_log('admin.moderation.rule_delete',
                           target_type='moderation_rule', target_id=rule_id,
                           request=request)
    return JSONResponse({'status': 'deleted'})


# ── Per-user view + actions ───────────────────────────────────────────────

# Risk score, stated so the number in the panel is a claim we can defend
# rather than a vibe: over the last 30 days, each event scores its decision
# weight times its severity weight, and the sum is capped at 100. A single
# critical block therefore already reads 50; two read 100.
_DECISION_WEIGHT = {'block': 10, 'flag': 3, 'allow': 0}
_SEVERITY_WEIGHT = {'low': 1, 'medium': 2, 'high': 3, 'critical': 5}

_SQL_USER_ROLLUP = sqlalchemy.text(
    'SELECT decision, severity, COUNT(*) AS c FROM moderation_event '
    "WHERE user_id = :uid AND created_at > now() - INTERVAL '30 days' "
    'GROUP BY decision, severity'
)
_SQL_USER_TOTAL = sqlalchemy.text(
    'SELECT COUNT(*) AS c FROM moderation_event WHERE user_id = :uid'
)
_SQL_USER_RECENT = sqlalchemy.text(
    'SELECT id, conversation_id, category, severity, rule_id, snippet, '
    '       decision, created_at FROM moderation_event '
    'WHERE user_id = :uid ORDER BY created_at DESC, id DESC LIMIT 20'
)


def _risk_score(rollup_rows) -> int:
    score = 0
    for r in rollup_rows:
        score += (_DECISION_WEIGHT.get(r.decision, 0)
                  * _SEVERITY_WEIGHT.get(r.severity, 1) * int(r.c))
    return min(100, score)


@router.get('/admin/moderation/users/{uid}')
async def user_moderation(request: Request, uid: int) -> JSONResponse:
    if not await admin.admin_required(request):
        return _denied()
    if async_session is None:
        return _no_db()
    async with async_session() as session:
        rollup = (await session.execute(_SQL_USER_ROLLUP, {'uid': uid})).fetchall()
        total = (await session.execute(_SQL_USER_TOTAL, {'uid': uid})).fetchone().c
        recent = (await session.execute(_SQL_USER_RECENT, {'uid': uid})).fetchall()
    return JSONResponse(jsonable_encoder({
        'risk_score': _risk_score(rollup),
        'event_count': total,
        'recent': [dict(r._mapping) for r in recent],
    }))


_SQL_BAN = sqlalchemy.text(
    'UPDATE users SET banned = true WHERE id = :uid RETURNING id'
)
_SQL_NOTIFY = sqlalchemy.text(
    'INSERT INTO notifications (user_id, type, title, body) '
    'VALUES (:uid, :type, :title, :body)'
)

_NOTICE = {
    'warn': ('هشدار درباره رعایت قوانین',
             'یکی از درخواست‌های شما با قوانین استفاده از سرویس مغایرت داشت. '
             'لطفاً قوانین را رعایت کنید؛ در صورت تکرار، دسترسی شما محدود می‌شود.'),
    'restrict': ('محدودیت موقت حساب',
                 'به دلیل مغایرت درخواست‌های شما با قوانین استفاده از سرویس، '
                 'حساب شما به‌مدت ۳۰ روز در وضعیت محدود قرار گرفت. در این مدت '
                 'درخواست‌های مغایر با قوانین مسدود می‌شوند.'),
    'suspend': ('تعلیق حساب',
                'حساب شما به دلیل نقض قوانین استفاده از سرویس تعلیق شد. '
                'برای پیگیری با پشتیبانی تماس بگیرید.'),
}


@router.post('/admin/moderation/users/{uid}/action')
async def user_action(request: Request, uid: int) -> JSONResponse:
    if not await admin.admin_required(request):
        return _denied()
    body = await _json_body(request)
    action = body.get('action')
    if action not in ACTIONS:
        return _bad('اقدام نامعتبر است؛ یکی از warn، restrict یا suspend.',
                    'Invalid action; must be one of warn, restrict, or suspend.')
    reason = body.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        return _bad('دلیل اقدام باید نوشته شود.', 'A reason for the action must be provided.')
    reason = reason.strip()[:500]
    if async_session is None:
        return _no_db()

    title, text = _NOTICE[action]
    async with async_session() as session:
        if action == 'suspend':
            row = (await session.execute(_SQL_BAN, {'uid': uid})).fetchone()
            if row is None:
                return err('کاربر پیدا نشد.', 'User not found.', 404)
        await session.execute(_SQL_NOTIFY, {
            'uid': uid, 'type': 'moderation', 'title': title, 'body': text})
        await session.commit()

    if action == 'restrict':
        await set_restricted(uid, True)

    await _write_audit_log(f'admin.moderation.{action}', target_type='user',
                           target_id=uid, details={'reason': reason},
                           request=request)
    return JSONResponse({'status': 'ok'})


# ── Helpers ───────────────────────────────────────────────────────────────

async def _json_body(request: Request) -> dict:
    """A malformed or absent body is an empty dict, so validation below --
    which produces a Persian 400 -- reports the problem instead of FastAPI
    returning an English 422."""
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _audit_details(params: dict) -> dict:
    """The audit row records WHICH rule changed and how, but truncates the
    pattern: audit_logs is readable in the panel and a full rule list there
    is one more place the blocklist leaks."""
    d = {k: v for k, v in params.items() if v is not None}
    if isinstance(d.get('pattern'), str):
        d['pattern'] = d['pattern'][:MAX_SNIPPET_CHARS]
    return d
