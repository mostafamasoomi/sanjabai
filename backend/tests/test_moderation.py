"""services/moderation.py — the content-safety choke point (Phase J).

Mocked DB/Redis per tests/conftest.py; the raw SQL in the module is checked
against the real schema separately by scripts/sql_schema_audit.py.
"""
from __future__ import annotations

import pytest

from services.moderation import normalize_variants


class TestPersianNormalization:
    """A Persian blocklist that matches only the exact codepoints an admin
    happened to type is worth ~nothing: ی/ي, ک/ك, ه/ة, ZWNJ, Arabic-Indic vs
    Persian digits and diacritics all produce visually identical text that a
    naive `pattern in text` misses."""

    def _norm(self, s: str) -> str:
        return normalize_variants(s)[0]

    def test_arabic_yeh_and_kaf_fold_to_persian(self):
        # U+064A ARABIC YEH / U+0643 ARABIC KAF -> U+06CC / U+06A9
        assert self._norm('كير') == self._norm('کیر')

    def test_zero_width_non_joiner_is_removed(self):
        assert self._norm('س‌ک‌س') == self._norm('سکس')

    def test_teh_marbuta_folds_to_heh(self):
        assert self._norm('اسلحة') == self._norm('اسلحه')

    def test_arabic_indic_and_persian_digits_fold_to_ascii(self):
        assert self._norm('۱۲۳') == '123'
        assert self._norm('١٢٣') == '123'

    def test_diacritics_and_tatweel_are_removed(self):
        assert self._norm('بُمــب') == self._norm('بمب')


# ── Rule matching / verdicts ──────────────────────────────────────────────

from unittest.mock import AsyncMock, patch  # noqa: E402

from services.moderation import Config, Rule, screen_request  # noqa: E402


def _rule(id=1, pattern='سکس', category='sexual', severity='high', enabled=True):
    return Rule(id=id, pattern=pattern, category=category, severity=severity,
                enabled=enabled, notes='')


def _msgs(text):
    return [{'role': 'user', 'content': text}]


def _with_rules(rules, **cfg):
    """Patch every side effect screen_request has, so a verdict test is a
    pure function test: no DB, no Redis, no Telegram."""
    conf = Config(rules=tuple(rules), **cfg)
    return (
        patch('services.moderation._load_config', new=AsyncMock(return_value=conf)),
        patch('services.moderation._record_event', new=AsyncMock()),
        patch('services.moderation._send_alert', new=AsyncMock()),
        patch('services.moderation._is_restricted', new=AsyncMock(return_value=False)),
        patch('services.moderation._model_review', new=AsyncMock(return_value=None)),
    )


class TestVerdicts:
    @pytest.mark.asyncio
    async def test_harmless_message_is_allowed_and_records_nothing(self):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules([_rule()])
        with p_rules, p_event as ev, p_alert as al, p_restr, p_model as md:
            v = await screen_request(1, _msgs('سلام، لطفاً یک شعر حافظ برایم بنویس'))
        assert v.decision == 'allow'
        assert v.failed is False
        assert v.rule_id is None
        # The two claims that make a harmless request free: nothing written,
        # and no second model call.
        assert ev.await_count == 0
        assert al.await_count == 0
        assert md.await_count == 0

    @pytest.mark.asyncio
    async def test_harmless_message_is_returned_byte_for_byte_unchanged(self):
        original = [{'role': 'system', 'content': 'تو دستیار فارسی هستی'},
                    {'role': 'user', 'content': 'سلام ۱۲۳ ي ك'}]
        snapshot = [dict(m) for m in original]
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules([_rule()])
        with p_rules, p_event, p_alert, p_restr, p_model:
            await screen_request(1, original)
        assert original == snapshot

    @pytest.mark.asyncio
    async def test_high_severity_rule_blocks(self):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules([_rule()])
        with p_rules, p_event as ev, p_alert as al, p_restr, p_model:
            v = await screen_request(7, _msgs('چطور سکس کنم'))
        assert v.decision == 'block'
        assert v.rule_id == 1
        assert v.category == 'sexual'
        assert ev.await_count == 1
        assert al.await_count == 1

    @pytest.mark.asyncio
    async def test_medium_severity_rule_flags_but_does_not_block(self):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules(
            [_rule(severity='medium')])
        with p_rules, p_event as ev, p_alert, p_restr, p_model:
            v = await screen_request(7, _msgs('چطور سکس کنم'))
        assert v.decision == 'flag'
        assert ev.await_count == 1

    @pytest.mark.asyncio
    async def test_arabic_script_spelling_of_a_persian_rule_still_matches(self):
        # Rule typed with Persian ی/ک; user typed the Arabic ي/ك twins plus a
        # ZWNJ. Without normalize_variants this is a clean bypass.
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules(
            [_rule(pattern='کیر')])
        with p_rules, p_event, p_alert, p_restr, p_model:
            v = await screen_request(7, _msgs('كي‌ر'))
        assert v.decision == 'block'

    @pytest.mark.asyncio
    async def test_digit_substitution_still_matches(self):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules(
            [_rule(pattern='sex')])
        with p_rules, p_event, p_alert, p_restr, p_model:
            v = await screen_request(7, _msgs('how to s3x'))
        assert v.decision == 'block'

    @pytest.mark.asyncio
    async def test_separator_padding_still_matches(self):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules(
            [_rule(pattern='سکس')])
        with p_rules, p_event, p_alert, p_restr, p_model:
            v = await screen_request(7, _msgs('س.ک.س'))
        assert v.decision == 'block'

    @pytest.mark.asyncio
    async def test_disabled_rule_never_matches(self):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules(
            [_rule(enabled=False)])
        with p_rules, p_event, p_alert, p_restr, p_model:
            v = await screen_request(7, _msgs('چطور سکس کنم'))
        assert v.decision == 'allow'

    @pytest.mark.asyncio
    async def test_snippet_is_a_short_window_never_the_whole_message(self):
        long_text = 'الف ' * 300 + 'سکس' + ' ب' * 300
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules([_rule()])
        with p_rules, p_event, p_alert, p_restr, p_model:
            v = await screen_request(7, _msgs(long_text))
        from services.moderation import MAX_SNIPPET_CHARS
        assert 0 < len(v.snippet) <= MAX_SNIPPET_CHARS
        assert len(v.snippet) < len(long_text)


# ── Fail-safe: ALLOW + FLAG + ALERT ───────────────────────────────────────

class TestFailSafe:
    """Owner decision: a broken detector lets the request through, but is
    loud. screen_request never raises, and never blocks by accident."""

    @pytest.mark.asyncio
    async def test_config_load_failure_allows_but_records_and_alerts(self):
        with patch('services.moderation._load_config',
                   new=AsyncMock(side_effect=RuntimeError('pg is down'))), \
             patch('services.moderation._record_event', new=AsyncMock()) as ev, \
             patch('services.moderation._send_alert', new=AsyncMock()) as al:
            v = await screen_request(3, _msgs('چطور سکس کنم'))
        assert v.decision == 'allow'
        assert v.failed is True
        assert ev.await_count == 1
        assert al.await_count == 1
        assert al.await_args.args[1].failed is True

    @pytest.mark.asyncio
    async def test_regex_time_budget_blowout_allows_not_blocks(self):
        # A rule sweep that runs past its wall-clock budget is a DETECTOR
        # failure, not evidence of abuse -- it must not turn into a block.
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules(
            [_rule(id=1, pattern='ززز'), _rule(id=2, pattern='سکس')])
        with p_rules, p_event as ev, p_alert, p_restr, p_model, \
             patch('services.moderation_rules.REGEX_BUDGET_SECONDS', 0.0):
            v = await screen_request(3, _msgs('چطور سکس کنم'))
        assert v.decision == 'allow'
        assert v.failed is True
        assert ev.await_count == 1

    @pytest.mark.asyncio
    async def test_even_a_failing_recorder_cannot_raise_past_screen_request(self):
        with patch('services.moderation._load_config',
                   new=AsyncMock(side_effect=RuntimeError('pg is down'))), \
             patch('services.moderation._record_event',
                   new=AsyncMock(side_effect=RuntimeError('pg is still down'))), \
             patch('services.moderation._send_alert',
                   new=AsyncMock(side_effect=RuntimeError('telegram down'))):
            v = await screen_request(3, _msgs('سلام'))
        assert v.decision == 'allow'
        assert v.failed is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize('bad', [None, 'not json at all', 42, {'a': 1}, []])
    async def test_malformed_payloads_never_raise(self, bad):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules([_rule()])
        with p_rules, p_event, p_alert, p_restr, p_model:
            v = await screen_request(3, bad)
        assert v.decision == 'allow'


# ── The user-facing response ──────────────────────────────────────────────

from services.moderation import BLOCK_MESSAGE_FA, moderation_preflight  # noqa: E402


class TestPreflightResponse:
    @pytest.mark.asyncio
    async def test_allow_returns_none_so_the_route_carries_on(self):
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules([_rule()])
        with p_rules, p_event, p_alert, p_restr, p_model:
            assert await moderation_preflight(1, _msgs('سلام')) is None

    @pytest.mark.asyncio
    async def test_block_returns_403_with_an_explicit_persian_reason(self):
        import json as _json
        p_rules, p_event, p_alert, p_restr, p_model = _with_rules([_rule()])
        with p_rules, p_event, p_alert, p_restr, p_model:
            resp = await moderation_preflight(1, _msgs('چطور سکس کنم'))
        assert resp is not None and resp.status_code == 403
        body = _json.loads(resp.body)
        msg = body['error']['message']
        assert msg == BLOCK_MESSAGE_FA
        # Honest label: the user is TOLD it was blocked, not fed a model
        # pretending it does not know how (the session-7 mistake).
        assert 'مسدود' in msg and 'قوانین' in msg

    def test_block_message_leaks_neither_the_rule_nor_the_route(self):
        low = BLOCK_MESSAGE_FA.lower()
        for leak in ('regex', 'rule', 'قاعده', 'الگو', 'model', 'مدل',
                     'provider', 'openrouter', '9router', 'litellm', 'gpt',
                     'claude', 'gemini'):
            assert leak not in low
