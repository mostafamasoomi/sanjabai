"""Regression tests for bot/bot.py's default chat model.

A previous version hardcoded 'gpt-4o' in _do_chat's payload. The catalog has
never offered a chat 'gpt-4o': the only matching rows are *-transcribe
(audio) models, and all of them are `maintenance` -- so every /chat command
and every plain message sent to the bot got a 400 'model_not_available' from
/v1/chat/completions and never reached the AI at all. See
bot.py's `get_default_model()` docstring for the fix (resolves the cheapest
currently-listed `sanjab/*` model from /v1/models instead of hardcoding).

bot/bot.py is a standalone process (python-telegram-bot), not part of the
FastAPI app under test elsewhere in this suite. python-telegram-bot isn't a
backend dependency (see bot/requirements.txt) and isn't installed in the
backend test image/CI job, so importing bot.py requires stubbing the
`telegram` package first -- in the same spirit conftest.py stubs
`redis`/`asyncpg` before importing the FastAPI app. None of the stubbed
names are touched by the pure helper functions under test here
(get_default_model, _do_chat, api_request).
"""
from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _import_bot_module(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'test-token-not-a-placeholder')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'bot'))

    if 'telegram' not in sys.modules:
        fake_telegram = MagicMock()
        fake_telegram_ext = MagicMock()
        fake_telegram_constants = MagicMock()
        fake_telegram_constants.ParseMode = MagicMock(MARKDOWN='Markdown')
        sys.modules['telegram'] = fake_telegram
        sys.modules['telegram.ext'] = fake_telegram_ext
        sys.modules['telegram.constants'] = fake_telegram_constants
        fake_telegram.ext = fake_telegram_ext
        fake_telegram.constants = fake_telegram_constants

    if 'bot' in sys.modules:
        del sys.modules['bot']
    return importlib.import_module('bot')


def test_default_chat_payload_no_longer_hardcodes_gpt4o(monkeypatch):
    """Static regression check: 'gpt-4o' must not appear as the chat
    payload's model anywhere in _do_chat's source."""
    bot_mod = _import_bot_module(monkeypatch)
    source = inspect.getsource(bot_mod._do_chat)
    assert "'model': 'gpt-4o'" not in source
    assert '"model": "gpt-4o"' not in source


@pytest.mark.asyncio
async def test_get_default_model_picks_cheapest_sanjab_model(monkeypatch):
    bot_mod = _import_bot_module(monkeypatch)
    bot_mod._DEFAULT_MODEL_CACHE = None
    bot_mod._DEFAULT_MODEL_CACHE_AT = 0.0

    models_response = {
        'status': 200,
        'data': {
            'data': [
                {'id': 'sanjab/expensive', 'pricing': {'inputPerMillion': 999999, 'outputPerMillion': 999999}},
                {'id': 'sanjab/mimo-v2.5', 'pricing': {'inputPerMillion': 26684, 'outputPerMillion': 53368}},
                {'id': 'not-public/foo', 'pricing': {'inputPerMillion': 1, 'outputPerMillion': 1}},
            ],
        },
    }
    with patch.object(bot_mod, 'api_request', AsyncMock(return_value=models_response)):
        result = await bot_mod.get_default_model()
    assert result == 'sanjab/mimo-v2.5'


@pytest.mark.asyncio
async def test_get_default_model_returns_none_when_api_unreachable_and_uncached(monkeypatch):
    bot_mod = _import_bot_module(monkeypatch)
    bot_mod._DEFAULT_MODEL_CACHE = None
    bot_mod._DEFAULT_MODEL_CACHE_AT = 0.0

    with patch.object(bot_mod, 'api_request', AsyncMock(side_effect=RuntimeError('network down'))):
        result = await bot_mod.get_default_model()
    assert result is None


@pytest.mark.asyncio
async def test_do_chat_never_sends_empty_or_gpt4o_model_when_resolved(monkeypatch):
    bot_mod = _import_bot_module(monkeypatch)

    sent_payload = {}

    async def fake_api_request(method, path, token='', json_data=None):
        if path == '/v1/chat/completions':
            sent_payload.update(json_data or {})
            return {'status': 200, 'data': {'choices': [{'message': {'content': 'پاسخ'}}], 'usage': {}}}
        raise AssertionError(f'unexpected api_request call: {method} {path}')

    fake_update = MagicMock()
    fake_msg = MagicMock()

    async def fake_reply_text(*a, **kw):
        return fake_msg

    async def fake_edit_text(*a, **kw):
        pass

    fake_update.message.reply_text = fake_reply_text
    fake_msg.edit_text = fake_edit_text

    with patch.object(bot_mod, 'get_default_model', AsyncMock(return_value='sanjab/mimo-v2.5')), \
         patch.object(bot_mod, 'api_request', fake_api_request):
        await bot_mod._do_chat(fake_update, MagicMock(), 'سلام', 'test-token')

    assert sent_payload.get('model') == 'sanjab/mimo-v2.5'
    assert sent_payload.get('model') != 'gpt-4o'
    assert sent_payload.get('model')
