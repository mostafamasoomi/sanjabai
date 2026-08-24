"""Phase J follow-up -- category-specific block messages.

The generic BLOCK_MESSAGE_FA ("مغایرت با قوانین ... با پشتیبانی تماس
بگیرید") is bureaucratic and wrong for a user in a self-harm crisis. This
file proves: (1) the mapping helper in services/moderation_rules.py picks
the supportive message only for category == 'self_harm' and the generic one
for everything else, and (2) that choice is actually wired into the real
Verdict a block produces via screen_request/moderation_preflight -- not
just available and unused.

Reuses the screen_request-driving pattern from tests/test_moderation.py
(_with_rules patches every side effect so this exercises the real decision
path, no DB/Redis/Telegram).
"""
from __future__ import annotations

import json as _json
from unittest.mock import AsyncMock, patch

import pytest

from services.moderation import (
    BLOCK_MESSAGE_FA,
    Config,
    Rule,
    SELF_HARM_MESSAGE_FA,
    block_message_for_category,
    moderation_preflight,
    screen_request,
)


def _rule(id, category, pattern, severity='high', enabled=True):
    return Rule(id=id, pattern=pattern, category=category, severity=severity,
                enabled=enabled, notes='')


def _msgs(text):
    return [{'role': 'user', 'content': text}]


def _with_rules(rules, **cfg):
    conf = Config(rules=tuple(rules), **cfg)
    return (
        patch('services.moderation._load_config', new=AsyncMock(return_value=conf)),
        patch('services.moderation._record_event', new=AsyncMock()),
        patch('services.moderation._send_alert', new=AsyncMock()),
        patch('services.moderation._is_restricted', new=AsyncMock(return_value=False)),
        patch('services.moderation._model_review', new=AsyncMock(return_value=None)),
    )


# ── The pure mapping helper ─────────────────────────────────────────────────

class TestBlockMessageForCategory:
    def test_self_harm_gets_the_supportive_message(self):
        assert block_message_for_category('self_harm') == SELF_HARM_MESSAGE_FA

    @pytest.mark.parametrize('category', [
        'weapons', 'account_takeover', 'csam', 'drugs', 'malware', 'fraud',
        'sexual', None, 'some_future_category',
    ])
    def test_every_other_category_gets_the_generic_message(self, category):
        assert block_message_for_category(category) == BLOCK_MESSAGE_FA

    def test_self_harm_message_is_not_the_generic_one(self):
        assert SELF_HARM_MESSAGE_FA != BLOCK_MESSAGE_FA

    def test_self_harm_message_contains_the_hotline(self):
        assert '۱۲۳' in SELF_HARM_MESSAGE_FA or '123' in SELF_HARM_MESSAGE_FA

    def test_self_harm_message_does_not_name_a_rule_or_model(self):
        low = SELF_HARM_MESSAGE_FA.lower()
        for leak in ('rule', 'قاعده', 'الگو', 'model', 'مدل', 'provider',
                     'openrouter', '9router', 'litellm', 'gpt', 'claude',
                     'gemini'):
            assert leak not in low, f'self-harm message leaks {leak!r}'

    def test_self_harm_message_avoids_bureaucratic_support_tone(self):
        # The generic message's cold "با پشتیبانی تماس بگیرید" register must
        # not show up verbatim in the crisis-specific message.
        assert 'با پشتیبانی تماس بگیرید' not in SELF_HARM_MESSAGE_FA


# ── Wired into the real Verdict / screen_request path ──────────────────────

class TestScreenRequestUsesCategoryMapping:
    @pytest.mark.asyncio
    async def test_self_harm_block_carries_the_supportive_message(self):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules(
            [_rule(9, 'self_harm', 'خودکشی')])
        with p_rules, p_event, p_alert, p_restr, p_model:
            v = await screen_request(1, _msgs('میخوام خودکشی کنم'))
        assert v.decision == 'block'
        assert v.category == 'self_harm'
        assert v.message_fa == SELF_HARM_MESSAGE_FA
        assert v.message_fa != BLOCK_MESSAGE_FA
        assert '۱۲۳' in v.message_fa or '123' in v.message_fa

    @pytest.mark.asyncio
    @pytest.mark.parametrize('category,pattern,text', [
        ('weapons', 'اسلحه', 'از کجا اسلحه بخرم'),
        ('account_takeover', 'هک اینستاگرام', 'چطور اینستاگرام هک اینستاگرام کنم'),
    ])
    async def test_other_categories_keep_the_generic_message(
            self, category, pattern, text):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules(
            [_rule(3, category, pattern)])
        with p_rules, p_event, p_alert, p_restr, p_model:
            v = await screen_request(1, _msgs(text))
        assert v.decision == 'block'
        assert v.category == category
        assert v.message_fa == BLOCK_MESSAGE_FA

    @pytest.mark.asyncio
    async def test_self_harm_flag_not_block_has_no_message(self):
        # A self_harm rule matched but severity below block_severity ->
        # 'flag', not 'block'; message_fa stays None either way, exactly
        # like every other category (Verdict only carries a message on an
        # actual block).
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules(
            [_rule(9, 'self_harm', 'خودکشی', severity='medium')],
            block_severity='high')
        with p_rules, p_event, p_alert, p_restr, p_model:
            v = await screen_request(1, _msgs('میخوام خودکشی کنم'))
        assert v.decision == 'flag'
        assert v.message_fa is None


class TestPreflightSendsTheCategorySpecificMessage:
    @pytest.mark.asyncio
    async def test_self_harm_block_response_carries_the_hotline(self):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules(
            [_rule(9, 'self_harm', 'خودکشی')])
        with p_rules, p_event, p_alert, p_restr, p_model:
            resp = await moderation_preflight(1, _msgs('میخوام خودکشی کنم'))
        assert resp is not None and resp.status_code == 403
        body = _json.loads(resp.body)
        msg = body['error']['message']
        assert msg == SELF_HARM_MESSAGE_FA
        assert '۱۲۳' in msg or '123' in msg
        assert msg != BLOCK_MESSAGE_FA

    @pytest.mark.asyncio
    async def test_weapons_block_response_keeps_the_generic_message(self):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules(
            [_rule(3, 'weapons', 'اسلحه')])
        with p_rules, p_event, p_alert, p_restr, p_model:
            resp = await moderation_preflight(1, _msgs('از کجا اسلحه بخرم'))
        body = _json.loads(resp.body)
        assert body['error']['message'] == BLOCK_MESSAGE_FA
