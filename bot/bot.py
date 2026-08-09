"""
Sanjabai Telegram Bot — AI chat + wallet + account linking.
Uses python-telegram-bot (v20+ async).
"""
import os
import sys
import signal
import time
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
API_URL = os.getenv('API_URL', 'http://sanjabai_api:8000')

if not BOT_TOKEN or BOT_TOKEN == 'your-bot-token':
    print('⚠️  TELEGRAM_BOT_TOKEN not set or placeholder. Exiting gracefully.')
    sys.exit(0)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

# ── API helpers ────────────────────────────────────────────

async def api_request(method: str, path: str, token: str = '', json_data: dict = None) -> dict:
    """Make authenticated API request to Sanjabai backend"""
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.request(method, f'{API_URL}{path}', headers=headers, json=json_data)
        return {'status': r.status_code, 'data': r.json() if r.content else {}}


# ── Redis helpers (use API's Redis via backend) ────────────

async def get_user_token(telegram_id: int) -> str | None:
    """Get user's API token from their Telegram-linked account"""
    r = await api_request('GET', f'/auth/telegram-link?tg_id={telegram_id}')
    if r['status'] == 200:
        return r['data'].get('token')
    return None


# ── Command handlers ───────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message + account linking"""
    tg_id = update.effective_user.id
    token = await get_user_token(tg_id)

    if token:
        context.user_data['token'] = token
        await update.message.reply_text(
            '👋 *سلام! به Sanjabai Bot خوش آمدید*\n\n'
            '✅ حساب شما قبلاً متصل شده است.\n\n'
            '📋 *دستورات:*\n'
            '/chat _متن_ — گفتگو با هوش مصنوعی\n'
            '/wallet — موجودی کیف پول\n'
            '/models — لیست مدل‌ها\n'
            '/help — راهنما',
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            '👋 *سلام! به Sanjabai Bot خوش آمدید*\n\n'
            'برای استفاده از ربات، ابتدا حساب خود را متصل کنید:\n\n'
            '1️⃣ در سایت [sanjabai.ir](https://sanjabai.ir) ثبت‌نام کنید\n'
            '2️⃣ به بخش *پروفایل* بروید\n'
            '3️⃣ روی *اتصال تلگرام* کلیک کنید\n\n'
            'یا از دستور /link _ایمیل_ _رمزعبور_ استفاده کنید.',
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )


async def cmd_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Link Telegram account: /link email password"""
    args = context.args
    if len(args) < 2:
        await update.message.reply_text('❌ استفاده: /link _ایمیل_ _رمزعبور_', parse_mode=ParseMode.MARKDOWN)
        return

    email, password = args[0], args[1]
    tg_id = update.effective_user.id

    # Login to get token
    r = await api_request('POST', '/auth/login', json_data={'email': email, 'password': password})
    if r['status'] != 200:
        await update.message.reply_text('❌ ایمیل یا رمز عبور اشتباه است.')
        return

    token = r['data']['token']
    context.user_data['token'] = token

    # Link Telegram ID
    await api_request('POST', '/auth/telegram-link', token=token, json_data={'telegram_id': tg_id})

    await update.message.reply_text(
        '✅ *حساب شما با موفقیت متصل شد!*\n\n'
        'حالا می‌توانید از دستورات زیر استفاده کنید:\n'
        '/chat _متن_ — گفتگو با AI\n'
        '/wallet — موجودی',
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chat with AI: /chat your message, or just reply to bot"""
    token = context.user_data.get('token')
    if not token:
        await update.message.reply_text('❌ ابتدا حساب خود را با /link متصل کنید.')
        return

    text = ' '.join(context.args) if context.args else ''
    if not text:
        await update.message.reply_text('❌ استفاده: /chat _متن پیام_', parse_mode=ParseMode.MARKDOWN)
        return

    await _do_chat(update, context, text, token)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages as chat"""
    token = context.user_data.get('token')
    if not token:
        await update.message.reply_text('👋 ابتدا حساب خود را با /link متصل کنید.')
        return

    text = update.message.text
    await _do_chat(update, context, text, token)


async def _do_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, token: str):
    """Send message to AI and return response"""
    msg = await update.message.reply_text('⏳ در حال پردازش...')

    payload = {
        'model': 'gpt-4o',
        'messages': [{'role': 'user', 'content': text}],
    }

    r = await api_request('POST', '/v1/chat/completions', token=token, json_data=payload)

    if r['status'] != 200:
        await msg.edit_text(f'❌ خطا: {r["data"].get("detail", "unknown")}')
        return

    choices = r['data'].get('choices', [])
    if choices:
        response_text = choices[0].get('message', {}).get('content', '')
        usage = r['data'].get('usage', {})
        cost_info = ''
        if usage:
            total = usage.get('total_tokens', 0)
            cost_info = f'\n\n_📊 {total} توکن مصرف شد_'

        # Truncate if too long for Telegram (4096 chars)
        if len(response_text) > 4000:
            response_text = response_text[:4000] + '...'

        await msg.edit_text(response_text + cost_info, parse_mode=ParseMode.MARKDOWN)
    else:
        await msg.edit_text('❌ پاسخی دریافت نشد.')


async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check wallet balance"""
    token = context.user_data.get('token')
    if not token:
        await update.message.reply_text('❌ ابتدا حساب خود را با /link متصل کنید.')
        return

    r = await api_request('GET', '/wallet', token=token)
    if r['status'] != 200:
        await update.message.reply_text('❌ خطا در دریافت موجودی.')
        return

    balance = r['data'].get('balance', 0)
    await update.message.reply_text(
        f'💰 *موجودی کیف پول:* {balance:,} تومان\n\n'
        f'برای شارژ حساب به [sanjabai.ir/wallet](https://sanjabai.ir/wallet) مراجعه کنید.',
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List available models"""
    r = await api_request('GET', '/v1/models')
    if r['status'] != 200:
        await update.message.reply_text('❌ خطا در دریافت مدل‌ها.')
        return

    models = r['data'].get('data', [])
    if not models:
        await update.message.reply_text('❌ مدلی در دسترس نیست.')
        return

    # Show top 10 models
    model_list = '\n'.join(f'• `{m["id"]}`' for m in models[:10])
    await update.message.reply_text(
        f'🧠 *مدل‌های در دسترس:*\n\n{model_list}\n\n'
        f'_و {len(models) - 10} مدل دیگر..._',
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help"""
    await update.message.reply_text(
        '📋 *راهنمای Sanjabai Bot*\n\n'
        '/start — شروع\n'
        '/link _ایمیل_ _رمز_ — اتصال حساب\n'
        '/chat _متن_ — گفتگو با AI\n'
        '/wallet — موجودی کیف پول\n'
        '/models — لیست مدل‌ها\n'
        '/help — این راهنما\n\n'
        '💡 همچنین می‌توانید مستقیماً پیام بفرستید تا AI پاسخ دهد.',
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Main ───────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('link', cmd_link))
    app.add_handler(CommandHandler('chat', cmd_chat))
    app.add_handler(CommandHandler('wallet', cmd_wallet))
    app.add_handler(CommandHandler('models', cmd_models))
    app.add_handler(CommandHandler('help', cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print('🤖 Sanjabai Bot started...')
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()