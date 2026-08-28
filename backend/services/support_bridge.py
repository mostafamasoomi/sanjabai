"""Telegram support bridge: user support messages <-> the admin Telegram group.

Two directions, backed by the ``support_message`` table (migration
0053_support_messages.sql):

  * :func:`send_to_admins` -- a user's message (POST /support/messages,
    backend/support.py) is stored (``direction='in'``) and posted into the
    admin Telegram group.
  * :func:`handle_admin_reply` -- an admin's Telegram *reply* to that group
    message is matched back by ``tg_message_id``, stored
    (``direction='out'``) and delivered to the user as an in-app
    notification (``models.Notification`` / the ``notifications`` table,
    migration 0038) -- reusing the endpoint the frontend already reads
    (``GET /notifications``), not a new frontend surface.

── PRIVACY -- read this before touching the outbound text below ──────────
What crosses to Telegram in :func:`send_to_admins`: the caller's numeric
``user_id``, their email if one was given, and the message ``body``
VERBATIM. Nothing else is ever interpolated into the Telegram payload --
in particular never a password hash, an API key, or a wallet balance. The
message is sent with no ``parse_mode`` (plain text) specifically so
arbitrary user-supplied text can never be misread as Markdown and fail the
send with a 400 from Telegram.

── Which bot token, and why it is NOT services/watchdog_settings.py ──────
watchdog.py:134 (``_send_telegram``) and security_lockout.py:147
(``_send_lockout_alert``) both resolve their bot token through
``services.watchdog_settings.get_watchdog_credentials()`` (admin-editable
``app_setting`` rows, migration 0044, env fallback). This module
deliberately does NOT reuse that resolver for the bot token, even though
the actual POST to ``api.telegram.org/bot<token>/sendMessage`` below
copies that idiom's *shape* exactly (bare httpx client, no parse_mode
tricks, best-effort). The reason is reply routing: Telegram only ever
delivers "here is a reply to message X" to the ONE bot that sent message
X, over THAT bot's own getUpdates/polling loop -- bot/bot.py:297
(``app.run_polling``), authenticated with ``TELEGRAM_BOT_TOKEN``. If this
module sent the group notification as a DIFFERENT bot (e.g. the watchdog
alert bot), bot/bot.py would never see the admin's reply at all -- the
bridge would be silently one-way. So the credential here has to be
literally the same bot bot/bot.py polls with: ``TELEGRAM_BOT_TOKEN``, read
directly via ``os.getenv`` (the same env var, same access pattern
bot/bot.py:15 uses), not through an app_setting-backed resolver -- this
migration intentionally does not add one; see 0053's header.

── Anti-abuse ─────────────────────────────────────────────────────────────
``support_message_limiter`` reuses ``security.RateLimiter`` (the sliding
window / Redis-backed class every other rate limit in this codebase is
built from -- security.py:66) rather than inventing a second rate-limit
mechanism; it is instantiated here, not added to security.py's module-level
limiter list, because this file is this packet's to own and security.py is
not. ``MAX_BODY_LENGTH`` caps the length independently of the rate limit.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
import sqlalchemy

from database import async_session
from models import Notification
from security import RateLimiter

logger = logging.getLogger(__name__)

SETTING_KEY_GROUP_ID = 'support_tg_group_id'

MAX_BODY_LENGTH = 4000
RATE_LIMIT_WINDOW_SECONDS = 3600
RATE_LIMIT_MAX_MESSAGES = 10

# Reuses the RateLimiter *class* (security.py:66) -- not a second
# implementation -- just a dedicated instance, since security.py is a
# shared file this packet does not own.
support_message_limiter = RateLimiter(
    window_seconds=RATE_LIMIT_WINDOW_SECONDS, max_requests=RATE_LIMIT_MAX_MESSAGES,
)


class SupportMessageTooLong(Exception):
    """Raised by send_to_admins when body exceeds MAX_BODY_LENGTH.

    A caller-input problem, not a bridge failure -- backend/support.py
    turns this into a 400, distinct from the silent 'stored as failed'
    path a misconfigured or unreachable Telegram represents.
    """


class SupportRateLimitExceeded(Exception):
    """Raised by send_to_admins when the caller's hourly cap is hit.

    Also a caller-input problem (backend/support.py turns this into a
    429) -- not stored as a support_message row at all, since accepting
    and immediately failing it would just let the abuse pattern fill the
    table.
    """


def _bot_token() -> str:
    """The bot bot/bot.py itself polls with. See the module docstring's
    'Which bot token' section for why this is not
    services.watchdog_settings.get_watchdog_credentials()."""
    return (os.getenv('TELEGRAM_BOT_TOKEN', '') or '').strip()


async def _read_group_id() -> Optional[str]:
    """The admin-configured target group id, straight from app_setting.

    No cache, no env fallback -- unlike watchdog credentials this value has
    exactly one source, the admin panel; an empty or missing row means the
    bridge is deliberately off, not a fallback situation to resolve.
    Returns None on ANY problem (missing session, DB error, non-string /
    empty row) so every caller -- both the fail-open send path and the
    fail-closed chat-id check below -- can treat "None" as one uniform
    "not configured" signal instead of juggling several failure shapes.
    """
    if not async_session:
        return None
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text('SELECT value FROM app_setting WHERE key = :k'),
                {'k': SETTING_KEY_GROUP_ID},
            )
            row = res.fetchone()
    except Exception as e:
        logger.warning('support_bridge: group id read failed: %s', e)
        return None
    if row is None or not isinstance(row.value, str) or not row.value.strip():
        return None
    return row.value.strip()


async def is_configured_group(chat_id) -> bool:
    """True only when ``chat_id`` matches the admin-configured
    ``support_tg_group_id`` exactly (string compare -- Telegram chat ids
    are transmitted and stored as text, e.g. ``-1001234567890``).

    Called from backend/support.py's ``POST /support/admin-reply`` BEFORE
    ``handle_admin_reply`` -- bot/support.py itself has no database access
    (it only ever talks to this API over HTTP) and so cannot verify the
    group on its own; this is the actual enforcement of "an admin reply
    from an unconfigured/unauthorized chat is ignored", which
    ``tg_message_id`` matching alone cannot guarantee: Telegram
    ``message_id`` values are sequential PER CHAT, not global, so a reply
    to some unrelated message with a colliding id in a different chat the
    bot happens to be a member of could otherwise be mistaken for a real
    admin reply. Fails CLOSED (returns False) on any read problem -- the
    opposite of :func:`_read_group_id`'s fail-open-to-None contract on the
    send side, because here "cannot verify" must mean "reject", not
    "accept from an unverified chat".
    """
    group_id = await _read_group_id()
    if not group_id:
        return False
    return str(chat_id).strip() == group_id


async def _insert_row(session, user_id: int, direction: str, body: str, status: str) -> int:
    res = await session.execute(
        sqlalchemy.text(
            'INSERT INTO support_message (user_id, direction, body, status) '
            'VALUES (:uid, :direction, :body, :status) RETURNING id'
        ),
        {'uid': user_id, 'direction': direction, 'body': body, 'status': status},
    )
    return res.scalar_one()


async def send_to_admins(user_id: int, body: str, user_email: str | None = None) -> Optional[int]:
    """Forward a user's support message to the admin Telegram group.

    See the module docstring for exactly what crosses to Telegram.

    Always creates a ``support_message`` row -- even when the bridge is
    unconfigured or the Telegram call fails -- so a user's message never
    silently vanishes; it shows up via ``GET /support/messages`` with
    ``status='failed'`` either way. Never raises for a bridge/Telegram
    failure (logged as a WARNING instead) -- the only exceptions this
    raises are :class:`SupportMessageTooLong` and
    :class:`SupportRateLimitExceeded`, both caller-input problems the
    endpoint turns into a 400/429 BEFORE anything is stored.

    Returns the Telegram ``message_id`` of the notification posted in the
    group -- the id an admin's reply will target -- or ``None`` if the row
    was stored but never reached Telegram.
    """
    if len(body) > MAX_BODY_LENGTH:
        raise SupportMessageTooLong(f'support message exceeds {MAX_BODY_LENGTH} characters')

    allowed, _remaining = await support_message_limiter.is_allowed(f'support:{user_id}')
    if not allowed:
        raise SupportRateLimitExceeded(f'user {user_id} exceeded the hourly support message limit')

    if not async_session:
        logger.warning('support_bridge: no database session available, message from user %s dropped', user_id)
        return None

    async with async_session() as session:
        row_id = await _insert_row(session, user_id, 'in', body, 'sent')
        await session.commit()

        bot_token = _bot_token()
        group_id = await _read_group_id()
        if not bot_token or not group_id:
            logger.warning(
                'support_bridge: bridge not configured (bot_token_set=%s group_id_set=%s), '
                'support_message %s stored as failed', bool(bot_token), bool(group_id), row_id,
            )
            await session.execute(
                sqlalchemy.text("UPDATE support_message SET status = 'failed' WHERE id = :id"),
                {'id': row_id},
            )
            await session.commit()
            return None

        who = f'#{user_id}' + (f' ({user_email})' if user_email else '')
        text_out = f'\U0001F4E9 پیام پشتیبانی جدید — کاربر {who}\n\n{body}'

        resp = None
        data: dict = {}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f'https://api.telegram.org/bot{bot_token}/sendMessage',
                    json={'chat_id': group_id, 'text': text_out},
                )
            data = resp.json() if resp.content else {}
        except Exception as e:
            logger.warning('support_bridge: telegram send error for row %s: %s', row_id, e)

        if resp is None or resp.status_code != 200 or not data.get('ok'):
            logger.warning(
                'support_bridge: telegram send failed for row %s: status=%s',
                row_id, getattr(resp, 'status_code', None),
            )
            await session.execute(
                sqlalchemy.text("UPDATE support_message SET status = 'failed' WHERE id = :id"),
                {'id': row_id},
            )
            await session.commit()
            return None

        tg_message_id = data.get('result', {}).get('message_id')
        await session.execute(
            sqlalchemy.text('UPDATE support_message SET tg_message_id = :mid WHERE id = :id'),
            {'mid': tg_message_id, 'id': row_id},
        )
        await session.commit()
        return tg_message_id


async def handle_admin_reply(tg_message_id_replied_to: int, body: str) -> bool:
    """Route an admin's Telegram reply back to the user who filed it.

    Looks the original message up by ``tg_message_id`` (the partial index
    ``idx_support_message_tg_id``, only ``direction='in'`` rows carry one),
    creates the ``direction='out'`` row, and files an in-app
    :class:`models.Notification` so the reply surfaces at the existing
    ``GET /notifications`` (notifications.py) -- no new frontend surface.

    The caller (backend/support.py's ``POST /support/admin-reply``,
    reached only from bot/support.py) is responsible for confirming the
    reply arrived in the CONFIGURED admin group (:func:`is_configured_group`)
    before calling this -- this function does not re-check chat_id, it
    only trusts that the ``tg_message_id`` it was given is genuine.

    Returns ``False`` (never raises) when ``tg_message_id_replied_to``
    does not match any stored ``'in'`` row, or on any DB error -- an
    unknown id, a reply to some unrelated message the bot happens to have
    sent, and a DB hiccup all look the same to the caller: nothing was
    delivered.
    """
    if not async_session:
        logger.warning('support_bridge: no database session available, admin reply dropped')
        return False
    try:
        async with async_session() as session:
            res = await session.execute(
                sqlalchemy.text(
                    "SELECT user_id FROM support_message "
                    "WHERE tg_message_id = :mid AND direction = 'in'"
                ),
                {'mid': tg_message_id_replied_to},
            )
            row = res.fetchone()
            if row is None:
                logger.warning(
                    'support_bridge: admin reply to unknown tg_message_id=%s ignored',
                    tg_message_id_replied_to,
                )
                return False
            user_id = row.user_id

            await _insert_row(session, user_id, 'out', body, 'delivered')
            session.add(Notification(
                user_id=user_id, type='support',
                title='پاسخ پشتیبانی',
                body=body,
            ))
            await session.commit()
        return True
    except Exception as e:
        logger.warning('support_bridge: handle_admin_reply failed: %s', e)
        return False
