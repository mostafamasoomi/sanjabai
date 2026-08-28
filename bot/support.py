"""Telegram-side half of the support bridge
(backend/services/support_bridge.py + backend/support.py).

Adds two things bot.py wires in (see bot.py's ``main()``):

  * ``cmd_support`` -- ``/support <text>``, a linked user messaging the
    bot directly to reach admins. Same auth/plumbing shape as bot.py's
    own ``cmd_chat``: requires ``context.user_data['token']`` (set by
    ``/link`` or ``/start`` auto-linking) and calls the backend with it.
  * ``handle_group_reply`` -- an admin's reply in the admin Telegram
    group, forwarded to the backend for delivery back to the user.
    Only fires for a text message that is itself a Telegram *reply* to a
    message THIS bot previously sent, inside a group/supergroup chat --
    everything else (an ordinary conversation between admins, a reply to
    someone else's message, a DM) is left alone. The "is this actually
    the CONFIGURED support group" check happens server-side
    (backend/support.py::admin_reply ->
    services/support_bridge.py::is_configured_group) -- this module has no
    database access and cannot verify that itself.

── Why this module does not `import bot` ─────────────────────────────────
bot.py is executed as ``__main__`` by the container's CMD
(``python bot.py``). If this module did ``import bot`` to reach
``bot.api_request`` / ``bot.BOT_TOKEN``, Python would load a SECOND,
separate copy of bot.py under the module name ``bot`` (a script run
directly is never registered in ``sys.modules`` under its own filename),
re-running bot.py's module-level ``TELEGRAM_BOT_TOKEN`` guard a second
time and doubling every top-level side effect for no benefit. Instead this
module reads what it needs off the ``Update``/``Context`` objects
python-telegram-bot already hands every handler (``context.bot.token``,
``context.user_data``) and keeps its own tiny HTTP helper below --
``API_URL`` is read with the exact same env var and default bot.py:16
uses, so the two never diverge in practice.

This is not "a second Telegram client" (the thing the handoff packet
forbids) -- it never talks to api.telegram.org. It only calls this
project's own backend, the same way every command in bot.py already does.
"""
from __future__ import annotations

import logging
import os

import httpx
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

API_URL = os.getenv('API_URL', 'http://sanjabai_api:8000')


async def _api_call(method: str, path: str, *, token: str = '',
                     headers: dict | None = None, json_data: dict | None = None) -> tuple[int, dict]:
    """Minimal internal API caller -- mirrors bot.py's own ``api_request``
    shape (same timeout, same header/body convention) without importing
    it. See the module docstring for why."""
    all_headers = {'Content-Type': 'application/json'}
    if token:
        all_headers['Authorization'] = f'Bearer {token}'
    if headers:
        all_headers.update(headers)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.request(method, f'{API_URL}{path}', headers=all_headers, json=json_data)
        return r.status_code, (r.json() if r.content else {})


async def cmd_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """``/support <text>`` -- forward a message to admins via
    ``POST /support/messages`` (backend/support.py), which in turn calls
    services/support_bridge.py::send_to_admins. Requires a linked account,
    the same guard bot.py's ``cmd_chat`` uses."""
    token = context.user_data.get('token')
    if not token:
        await update.message.reply_text('❌ ابتدا حساب خود را با /link متصل کنید.')
        return

    text = ' '.join(context.args) if context.args else ''
    if not text:
        await update.message.reply_text('❌ استفاده: /support _متن پیام_', parse_mode=ParseMode.MARKDOWN)
        return

    try:
        status, data = await _api_call(
            'POST', '/support/messages', token=token, json_data={'body': text},
        )
    except Exception as e:
        logger.warning('support: cmd_support failed: %s', e)
        await update.message.reply_text('❌ خطا در ارسال پیام پشتیبانی.')
        return

    if status == 200 and data.get('status') in ('sent', 'failed'):
        await update.message.reply_text(
            '✅ پیام شما برای پشتیبانی ارسال شد. به‌زودی پاسخ داده می‌شود.'
        )
    else:
        await update.message.reply_text(f"❌ خطا: {data.get('detail', 'unknown')}")


async def handle_group_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forward an admin's reply-to-the-bot in a group chat to the backend.

    Silently returns (does not call the API at all) for anything that is
    not a text reply to a message THIS bot itself sent -- an ordinary
    conversation between admins in the same group must never be
    forwarded. The chat-id-matches-the-configured-group check happens
    server-side; see the module docstring.
    """
    message = update.effective_message
    if message is None or not message.text:
        return
    replied = message.reply_to_message
    if replied is None or replied.from_user is None:
        return
    if not replied.from_user.is_bot or replied.from_user.id != context.bot.id:
        return
    chat = update.effective_chat
    if chat is None or chat.type not in ('group', 'supergroup'):
        return

    try:
        status, data = await _api_call(
            'POST', '/support/admin-reply',
            headers={'X-Bot-Token': context.bot.token},
            json_data={
                'chat_id': chat.id,
                'reply_to_message_id': replied.message_id,
                'body': message.text,
            },
        )
    except Exception as e:
        logger.warning('support: admin-reply forward failed: %s', e)
        return

    if status != 200 or not data.get('delivered'):
        logger.info('support: admin reply not delivered (status=%s data=%s)', status, data)
