"""Capture the `kiro_credits` cost signal from `kr/` usage (Phase F2).

`kr/` routes report a credit cost alongside the token counts and the
gateway currently throws it away (docs/ROADMAP.md:664). It is a COST
signal for later analysis -- in the upstream's own credit unit, NOT
Toman -- so it is recorded on `usage_events.meta` (already jsonb, already
the carrier for `listed_cost` / `shortfall` / `prompt_tokens_raw`) and
must never touch a charge, a balance, or the ledger.

⚠️ The exact wire shape is UNVERIFIED: a live probe of the upstream was
blocked by this session's permission policy, so the field's real key and
nesting were never observed. The reader is therefore deliberately
defensive -- several plausible spellings and one nested vendor block --
and a response WITHOUT the field is an ordinary silent no-op, not a
warning and not a billing change.
"""
from __future__ import annotations

import pytest

import providers as providers_mod


class TestExtractKiroCredits:
    def test_top_level_snake_case_key(self):
        assert providers_mod.extract_kiro_credits(
            {'prompt_tokens': 10, 'completion_tokens': 2, 'kiro_credits': 3.5},
            model='kr/claude-sonnet-4') == 3.5

    def test_top_level_camel_case_key(self):
        assert providers_mod.extract_kiro_credits(
            {'kiroCredits': 7}, model='kr/claude-sonnet-4') == 7

    def test_nested_vendor_block(self):
        assert providers_mod.extract_kiro_credits(
            {'kiro': {'credits': 2.25}}, model='kr/claude-sonnet-4') == 2.25

    def test_nested_metadata_block(self):
        assert providers_mod.extract_kiro_credits(
            {'metadata': {'kiro_credits': 9}}, model='kr/claude-sonnet-4') == 9

    def test_missing_field_is_a_silent_none(self):
        assert providers_mod.extract_kiro_credits(
            {'prompt_tokens': 10, 'completion_tokens': 2}, model='kr/x') is None

    def test_non_kr_model_is_never_inspected(self):
        """The signal is a `kr/`-route thing; a same-named key on another
        route is not it, and must not be recorded as if it were."""
        assert providers_mod.extract_kiro_credits(
            {'kiro_credits': 3}, model='bynara/gpt-4o') is None

    def test_a_non_numeric_value_is_rejected_not_stored(self):
        assert providers_mod.extract_kiro_credits(
            {'kiro_credits': 'lots'}, model='kr/x') is None

    def test_a_bool_is_not_a_credit_count(self):
        assert providers_mod.extract_kiro_credits(
            {'kiro_credits': True}, model='kr/x') is None

    def test_zero_credits_is_a_real_reading_not_a_missing_one(self):
        assert providers_mod.extract_kiro_credits({'kiro_credits': 0}, model='kr/x') == 0

    def test_a_garbage_usage_block_never_raises(self):
        for junk in (None, [], 'usage', 42):
            assert providers_mod.extract_kiro_credits(junk, model='kr/x') is None

    def test_missing_model_never_raises(self):
        assert providers_mod.extract_kiro_credits({'kiro_credits': 1}, model=None) is None


class TestUnrecognisedShapeLogging:
    """The wire shape is unverified, so an unrecognised `kr/` usage block
    logs its KEYS once per model -- enough to discover the real spelling
    from production without putting a log line on every request."""

    @pytest.fixture(autouse=True)
    def _clean_slate(self):
        providers_mod._kiro_shape_logged.clear()
        yield
        providers_mod._kiro_shape_logged.clear()

    def test_logs_the_usage_keys_once_for_an_unrecognised_kr_response(self, caplog):
        with caplog.at_level('INFO', logger='providers'):
            providers_mod.extract_kiro_credits(
                {'prompt_tokens': 1, 'weird_cost_field': 5}, model='kr/x')
        assert 'weird_cost_field' in caplog.text

    def test_does_not_log_again_for_the_same_model(self, caplog):
        providers_mod.extract_kiro_credits({'weird_cost_field': 5}, model='kr/x')
        with caplog.at_level('INFO', logger='providers'):
            providers_mod.extract_kiro_credits({'weird_cost_field': 5}, model='kr/x')
        assert caplog.text == ''

    def test_never_logs_at_warning_or_above(self, caplog):
        with caplog.at_level('WARNING', logger='providers'):
            providers_mod.extract_kiro_credits({'weird_cost_field': 5}, model='kr/x')
        assert caplog.text == '', 'a kr/ response without the field is normal, not a fault'

    def test_a_recognised_response_logs_nothing(self, caplog):
        with caplog.at_level('INFO', logger='providers'):
            providers_mod.extract_kiro_credits({'kiro_credits': 1}, model='kr/x')
        assert caplog.text == ''

    def test_an_empty_usage_block_logs_nothing(self, caplog):
        """Missing usage is already diagnosed by _track_usage's own log --
        no second line for the same event."""
        with caplog.at_level('INFO', logger='providers'):
            providers_mod.extract_kiro_credits({}, model='kr/x')
        assert caplog.text == ''


# ── Wiring: the signal reaches usage_events.meta and nothing else ───────

import types  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import chat as chat_mod  # noqa: E402


def _table_name(stmt):
    try:
        return stmt.table.name
    except AttributeError:
        pass
    try:
        for f in stmt.get_final_froms():
            if getattr(f, 'name', None):
                return f.name
    except Exception:
        pass
    return None


class _FakeSession:
    """Session double covering the statements _record_usage issues (same
    shape as tests/test_billing_loss_paths.py's)."""

    def __init__(self, wallet_balance=10_000_000, price=None):
        self.wallet = types.SimpleNamespace(user_id=1, balance=wallet_balance, reserved=0)
        self.price = price or types.SimpleNamespace(
            input_per_million=1_000_000, output_per_million=1_000_000)
        self.added = []

    async def execute(self, stmt, params=None, *a, **k):
        result = MagicMock()
        result.fetchone.return_value = None
        text_sql = str(stmt)
        if 'model_catalog' in text_sql:
            result.fetchone.return_value = self.price
            return result
        if _table_name(stmt) == 'wallet' and type(stmt).__name__ != 'Update':
            result.fetchone.return_value = (self.wallet,)
        return result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


async def _record(model, usage):
    """Run _record_usage and return the meta dict handed to record_usage."""
    captured = {}

    async def _fake_record_usage(repo, **kwargs):
        captured.update(kwargs)
        return {}

    with patch('services.metering.record_usage', new=_fake_record_usage):
        result = await chat_mod._record_usage(
            _FakeSession(), uid=1, payload={'model': model}, usage=usage)
    return result, captured.get('meta', {})


@pytest.mark.asyncio
class TestKiroCreditsReachMeta:
    async def test_signal_is_recorded_on_usage_events_meta(self):
        _, meta = await _record('kr/claude-sonnet-4', {
            'prompt_tokens': 50, 'completion_tokens': 100, 'kiro_credits': 4.5})
        assert meta['kiro_credits'] == 4.5

    async def test_absent_signal_adds_no_key_at_all(self):
        """A meta key that is present-but-null on every non-kr row is
        noise in a jsonb column that cost analysis has to filter out."""
        _, meta = await _record('kr/claude-sonnet-4', {
            'prompt_tokens': 50, 'completion_tokens': 100})
        assert 'kiro_credits' not in meta

    async def test_non_kr_model_never_gets_the_key(self):
        _, meta = await _record('bynara/gpt-4o', {
            'prompt_tokens': 50, 'completion_tokens': 100, 'kiro_credits': 4.5})
        assert 'kiro_credits' not in meta

    async def test_the_existing_meta_keys_are_untouched(self):
        _, meta = await _record('kr/claude-sonnet-4', {
            'prompt_tokens': 50, 'completion_tokens': 100, 'kiro_credits': 4.5})
        assert meta['source'] == 'upstream'
        assert meta['prompt_tokens_raw'] == 50

    async def test_the_signal_changes_the_charge_by_not_one_toman(self):
        """kiro_credits is an upstream credit unit, not Toman. It must be
        recorded and otherwise ignored -- comparing the billed cost with
        and without the field present is the whole assertion."""
        with_signal, _ = await _record('kr/claude-sonnet-4', {
            'prompt_tokens': 50, 'completion_tokens': 100, 'kiro_credits': 999_999})
        without, _ = await _record('kr/claude-sonnet-4', {
            'prompt_tokens': 50, 'completion_tokens': 100})
        assert with_signal['cost'] == without['cost'] == 150
        assert with_signal['balance_after'] == without['balance_after']

    async def test_a_malformed_signal_does_not_break_billing(self):
        result, meta = await _record('kr/claude-sonnet-4', {
            'prompt_tokens': 50, 'completion_tokens': 100, 'kiro_credits': {'nope': 1}})
        assert result['cost'] == 150
        assert 'kiro_credits' not in meta


@pytest.mark.asyncio
class TestStreamingPathIsCoveredByTheSameChange:
    """chat_stream.py hands its trailing usage chunk to
    `chat._bill_stream_usage`, which funnels into the very same
    `_record_usage` -- so the streaming path needs NO separate edit. This
    test is the evidence for that claim rather than an assumption about it.
    """

    async def test_a_streamed_kr_usage_chunk_reaches_meta(self):
        captured = {}

        async def _fake_record_usage(repo, **kwargs):
            captured.update(kwargs)
            return {}

        session = _FakeSession()

        class _Ctx:
            async def __aenter__(self_inner):
                return session

            async def __aexit__(self_inner, *a):
                return None

        with patch('services.metering.record_usage', new=_fake_record_usage), \
             patch.object(chat_mod, 'async_session', MagicMock(return_value=_Ctx())):
            await chat_mod._bill_stream_usage(
                uid=1,
                payload={'model': 'kr/claude-sonnet-4'},
                usage={'prompt_tokens': 50, 'completion_tokens': 100, 'kiro_credits': 2.5},
                response_text='hi',
            )
        assert captured['meta']['kiro_credits'] == 2.5
