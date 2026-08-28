"""User-facing support endpoints, plus the internal admin-reply intake.

``POST /support/messages`` and ``GET /support/messages`` are the
user-facing pair: send a message into the Telegram bridge
(services/support_bridge.py) and read back your own conversation.
Ownership is enforced in the SQL WHERE clause (``WHERE user_id = :uid``),
never filtered in Python after a broader fetch -- the same shape every
other per-user list endpoint in this codebase uses (conversations.py's
``list_conversations`` is the direct precedent this file copies).

``POST /support/admin-reply`` is a third, INTERNAL-only route. Its only
caller is bot/support.py, after it has already confirmed a Telegram group
message is a reply to one the bot itself sent. It lives here (not on some
separate bot-only surface, which does not exist) because the bot process
has no direct database access at all -- it only ever calls out over HTTP,
exactly like it already does for GET /auth/telegram-link and
POST /v1/chat/completions (bot/bot.py's ``api_request``).

── Internal-call auth -- why X-Bot-Token, not INTERNAL_TOKEN ─────────────
``auth_account.py``'s ``POST /auth/telegram-token`` guards an internal
call the same shape as this one, comparing an ``x-internal-token`` header
against ``INTERNAL_TOKEN`` (database.py). Copying that exactly would need
``INTERNAL_TOKEN`` reaching the bot container, which today it does not:
docker-compose.yml's ``sanjabai_bot`` service only maps ``TELEGRAM_BOT_TOKEN``
and ``API_URL`` into its environment (no ``env_file:``), and adding a line
there is a docker-compose.yml edit outside this packet's scope-files.
The bot container already holds ``TELEGRAM_BOT_TOKEN`` as a secret only it
and this API process share (the bot via its explicit `environment:`
mapping, this API via ``env_file: .env`` loading the whole file) -- see
services/support_bridge.py's docstring for why that is also the token the
bridge sends WITH. This endpoint reuses that same value as the shared
secret instead, sent as ``X-Bot-Token`` and compared with
``hmac.compare_digest`` against ``os.getenv('TELEGRAM_BOT_TOKEN', '')``.
Both sides empty is treated as "auth impossible" and rejected, never as
"auth skipped" -- see ``_bot_auth_ok``. If the senior later wires a real
``INTERNAL_TOKEN`` into ``sanjabai_bot``'s environment, swapping the
comparison here is a one-line change; the header name would need to
change to ``x-internal-token`` to match ``auth_account.py``'s convention.

The token itself is never logged -- only whether the check passed.
"""
from __future__ import annotations

import hmac
import logging
import os

import sqlalchemy
from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import async_session
from dependencies import _get_user_id
from i18n import err
from services import support_bridge

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_BODY_LENGTH = support_bridge.MAX_BODY_LENGTH


class SupportMessageCreate(BaseModel):
    body: str


@router.post('/support/messages')
async def create_support_message(request: Request, payload: SupportMessageCreate) -> JSONResponse:
    """Send a support message. Forwarded to the admin Telegram group by
    services/support_bridge.py::send_to_admins; always stored regardless
    of whether the forward succeeds (see that function's docstring)."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    body = (payload.body or '').strip()
    if not body:
        return err('متن پیام نمی‌تواند خالی باشد', 'Message body cannot be empty.', 400)

    user_email = None
    async with async_session() as session:
        res = await session.execute(
            sqlalchemy.text('SELECT email FROM users WHERE id = :uid'), {'uid': uid}
        )
        row = res.fetchone()
        user_email = row.email if row else None

    try:
        tg_message_id = await support_bridge.send_to_admins(uid, body, user_email=user_email)
    except support_bridge.SupportMessageTooLong:
        return err(
            f'پیام نباید بیش از {MAX_BODY_LENGTH} نویسه باشد',
            f'Message must not exceed {MAX_BODY_LENGTH} characters.', 400,
        )
    except support_bridge.SupportRateLimitExceeded:
        return err(
            'تعداد پیام‌های پشتیبانی شما در این ساعت به سقف رسیده است',
            'You have reached the hourly support message limit.', 429,
        )

    return JSONResponse({'status': 'sent' if tg_message_id else 'failed'})


@router.get('/support/messages')
async def list_support_messages(request: Request) -> JSONResponse:
    """The caller's own support conversation, newest first. Ownership is
    enforced in SQL (``WHERE user_id = :uid``) -- never fetch a broader set
    and filter in Python."""
    uid = await _get_user_id(request)
    if not uid:
        return err('لطفاً وارد حساب خود شوید', 'Please sign in.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    page = max(int(request.query_params.get('page', 1)), 1)
    limit = min(max(int(request.query_params.get('limit', 20)), 1), 100)
    offset = (page - 1) * limit

    async with async_session() as session:
        count_res = await session.execute(
            sqlalchemy.text('SELECT COUNT(*) AS c FROM support_message WHERE user_id = :uid'),
            {'uid': uid},
        )
        total = count_res.fetchone().c
        res = await session.execute(
            sqlalchemy.text(
                'SELECT id, direction, body, status, created_at FROM support_message '
                'WHERE user_id = :uid ORDER BY created_at DESC OFFSET :off LIMIT :lim'
            ),
            {'uid': uid, 'off': offset, 'lim': limit},
        )
        rows = [
            {
                'id': r.id, 'direction': r.direction, 'body': r.body,
                'status': r.status, 'created_at': r.created_at,
            }
            for r in res.fetchall()
        ]
    return JSONResponse(jsonable_encoder({'items': rows, 'total': total, 'page': page, 'limit': limit}))


class AdminReplyIn(BaseModel):
    chat_id: int
    reply_to_message_id: int
    body: str


def _bot_auth_ok(request: Request) -> bool:
    """True only when ``X-Bot-Token`` matches a NON-EMPTY
    ``TELEGRAM_BOT_TOKEN``. Both sides empty must fail closed -- an
    unconfigured bot token must not make this endpoint openly callable by
    anyone who can reach the API container on the docker network."""
    expected = (os.getenv('TELEGRAM_BOT_TOKEN', '') or '').strip()
    given = request.headers.get('x-bot-token', '')
    return bool(expected) and bool(given) and hmac.compare_digest(given, expected)


@router.post('/support/admin-reply')
async def admin_reply(request: Request, payload: AdminReplyIn) -> JSONResponse:
    """Internal only -- the sole caller is bot/support.py, immediately
    after it detects a text reply to a message the bot itself sent in a
    group chat. See the module docstring for the auth shape.

    ``chat_id`` is checked against the admin-configured
    ``support_tg_group_id`` HERE (support_bridge.is_configured_group) --
    bot/support.py has no database access and cannot verify this itself;
    see that function's docstring for why the check cannot be skipped."""
    if not _bot_auth_ok(request):
        return err('غیرمجاز', 'Unauthorized.', 401)
    if async_session is None:
        return err('پایگاه داده در دسترس نیست', 'Database unavailable.', 500)

    if not await support_bridge.is_configured_group(payload.chat_id):
        logger.warning(
            'support admin-reply: chat_id %s does not match the configured support group, ignored',
            payload.chat_id,
        )
        return JSONResponse({'delivered': False})

    delivered = await support_bridge.handle_admin_reply(payload.reply_to_message_id, payload.body)
    return JSONResponse({'delivered': delivered})
