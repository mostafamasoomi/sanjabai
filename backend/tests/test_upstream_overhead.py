"""Tests for the upstream prompt-overhead discount:
services/upstream_overhead.py (the app_setting-backed lookup +
discounted_input_tokens arithmetic), chat_billing.py's discount block
wired into _record_usage, and migration 0041's seeded (empty/inert) row.

Owner's decision (2026-08-23): the ninerouter route injects a preamble the
user never wrote into the prompt, and the upstream folds that preamble
into `prompt_tokens` -- chat_billing.py:199 used to take that number
straight from the response, so the user was billed for text they never
sent. This suite pins both halves of the fix: the deduction itself
(discounted_input_tokens' arithmetic and the floor that keeps it honest)
and the fact that a lookup failure or an unmeasured route changes nothing
(overhead 0 -- bill the raw number, same as before this feature existed).

Follows test_billing_loss_paths.py's mocking style: a minimal fake
AsyncSession double standing in for the handful of statements
chat_billing._record_usage / SqlBillingRepo issue, no live DB needed. The
`_FakeSession` class below is that same double (quota select/update, a raw
text() pricing lookup, the wallet select+update pair, and now also capturing
the UsageEvent row SqlBillingRepo.append_usage_event() adds -- which is
where this suite reads back `meta['prompt_tokens_raw']` /
`meta['prompt_overhead_discounted']`).
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
from chat_billing import _estimate_input_tokens
from services import upstream_overhead


# ── Fake session (mirrors test_billing_loss_paths.py's double) ────────────

def _table_name(stmt):
    try:
        return stmt.table.name
    except AttributeError:
        pass
    try:
        for f in stmt.get_final_froms():
            name = getattr(f, "name", None)
            if name:
                return name
    except Exception:
        pass
    return None


class _FakeSession:
    def __init__(self, wallet_balance, price=None, quota_row=None):
        self.wallet = types.SimpleNamespace(user_id=1, balance=wallet_balance, reserved=0)
        self.price = price
        self.quota_row = quota_row
        self.added = []

    async def execute(self, stmt, params=None, *a, **k):
        result = MagicMock()
        result.fetchone.return_value = None
        text_sql = str(stmt)
        if "model_catalog" in text_sql:
            result.fetchone.return_value = self.price
            return result
        tname = _table_name(stmt)
        if tname == "wallet":
            if type(stmt).__name__ == "Update":
                p = stmt.compile().params
                if "balance" in p:
                    self.wallet.balance = p["balance"]
                if "reserved" in p:
                    self.wallet.reserved = p["reserved"]
            else:
                result.fetchone.return_value = (self.wallet,)
            return result
        if tname == "quota":
            if type(stmt).__name__ == "Update":
                p = params if params is not None else stmt.compile().params
                if self.quota_row is not None:
                    if "used_today" in p:
                        self.quota_row.used_today = p["used_today"]
                return result
            result.fetchone.return_value = self.quota_row
            return result
        return result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        return None


def _price(inp=1_000_000, out=1_000_000):
    # 1,000,000 IRT per million tokens -> 1 IRT per token, easy to hand-check.
    return types.SimpleNamespace(input_per_million=inp, output_per_million=out)


class _FakeProvider:
    def __init__(self, name):
        self.name = name


def _patch_provider(monkeypatch, name='ninerouter'):
    async def _fake_resolve_provider(model):
        return _FakeProvider(name)
    monkeypatch.setattr(chat_mod, '_resolve_provider', _fake_resolve_provider)


def _usage_event(session):
    rows = [o for o in session.added if type(o).__name__ == "UsageEvent"]
    assert len(rows) == 1, f"expected exactly one UsageEvent, got {len(rows)}"
    return rows[0]


SHORT_MESSAGES = [{"role": "user", "content": "سلام"}]


# ── discounted_input_tokens: pure arithmetic ───────────────────────────────

class TestDiscountedInputTokensArithmetic:
    def test_plain_subtraction(self):
        assert upstream_overhead.discounted_input_tokens(1000, 200, 5) == 800

    def test_no_overhead_is_a_no_op(self):
        assert upstream_overhead.discounted_input_tokens(500, 0, 10) == 500

    def test_floor_wins_when_overhead_would_undercut_it(self):
        # 1000 - 950 = 50, but the local estimate (floor) says the user's
        # real messages were worth at least 800 tokens -- must not bill
        # below that regardless of what the overhead entry says.
        assert upstream_overhead.discounted_input_tokens(1000, 950, 800) == 800

    def test_clamped_to_at_least_one_even_with_zero_floor(self):
        # Overhead wildly exceeds raw and the floor is 0 (e.g. no messages
        # captured) -- must never bill zero or negative tokens.
        assert upstream_overhead.discounted_input_tokens(10, 5000, 0) == 1

    def test_never_returns_less_than_floor_or_less_than_one(self):
        for raw, overhead, floor in [(100, 100, 0), (1, 1, 1), (0, 0, 0)]:
            billed = upstream_overhead.discounted_input_tokens(raw, overhead, floor)
            assert billed >= max(floor, 1)


# ── _record_usage bills the discounted number ──────────────────────────────

class TestRecordUsageBillsDiscountedNumber:
    @pytest.mark.asyncio
    async def test_same_call_with_overhead_bills_less_than_without(self, monkeypatch):
        _patch_provider(monkeypatch)
        usage = {"prompt_tokens": 1000, "completion_tokens": 100}
        payload = {"model": "ninerouter/cc/some-model", "messages": SHORT_MESSAGES}

        # Without an overhead entry (get_prompt_overhead -> 0): bills the
        # raw 1000 + 100 = 1100 tokens at 1 IRT/token.
        session_no_discount = _FakeSession(wallet_balance=10_000_000, price=_price())
        with patch.object(upstream_overhead, 'get_prompt_overhead', new=AsyncMock(return_value=0)):
            result_no_discount = await chat_mod._record_usage(
                session_no_discount, uid=1, payload=payload, usage=usage,
            )
        assert result_no_discount["input_tokens"] == 1000
        assert result_no_discount["cost"] == 1100

        # With a real overhead entry (300) and a tiny local estimate for
        # "سلام" (well under 700), the floor never engages: billed input is
        # exactly 1000 - 300 = 700.
        session_with_discount = _FakeSession(wallet_balance=10_000_000, price=_price())
        with patch.object(upstream_overhead, 'get_prompt_overhead', new=AsyncMock(return_value=300)):
            result_with_discount = await chat_mod._record_usage(
                session_with_discount, uid=1, payload=payload, usage=usage,
            )
        assert result_with_discount["input_tokens"] == 700
        assert result_with_discount["cost"] == 700 + 100

        assert result_with_discount["cost"] < result_no_discount["cost"]

        event = _usage_event(session_with_discount)
        assert event.meta["prompt_tokens_raw"] == 1000
        assert event.meta["prompt_overhead_discounted"] == 300

    @pytest.mark.asyncio
    async def test_zero_overhead_from_lookup_changes_nothing(self, monkeypatch):
        """Pins the seeded/empty migration 0041 row's behaviour end-to-end:
        an overhead lookup that resolves to 0 (empty entries/provider_default
        map, exactly what 0041 seeds) must bill the raw upstream number
        unchanged -- shipping this feature must not itself change anyone's
        bill until an admin measures real numbers."""
        _patch_provider(monkeypatch)
        usage = {"prompt_tokens": 433, "completion_tokens": 3}
        payload = {"model": "ninerouter/bynara/mimo-v2.5-free", "messages": SHORT_MESSAGES}
        session = _FakeSession(wallet_balance=10_000_000, price=_price())
        with patch.object(upstream_overhead, 'get_prompt_overhead', new=AsyncMock(return_value=0)):
            result = await chat_mod._record_usage(session, uid=1, payload=payload, usage=usage)
        assert result["input_tokens"] == 433
        assert result["cost"] == 433 + 3
        event = _usage_event(session)
        assert event.meta["prompt_tokens_raw"] == 433
        assert event.meta["prompt_overhead_discounted"] == 0


# ── The floor: an absurd overhead cannot bill below the local estimate ─────

class TestFloorProtectsAgainstOverDiscount:
    @pytest.mark.asyncio
    async def test_huge_overhead_entry_cannot_undercut_local_estimate(self, monkeypatch):
        _patch_provider(monkeypatch)
        long_content = "این یک پیام نسبتاً طولانی برای اطمینان از عملکرد سقف تخمین محلی است. " * 5
        payload = {"model": "ninerouter/cc/some-model", "messages": [{"role": "user", "content": long_content}]}
        floor = _estimate_input_tokens(payload["messages"])
        assert floor > 1  # sanity: the floor is a real, non-trivial number here

        usage = {"prompt_tokens": 1000, "completion_tokens": 50}
        session = _FakeSession(wallet_balance=10_000_000, price=_price())
        with patch.object(upstream_overhead, 'get_prompt_overhead', new=AsyncMock(return_value=1_000_000)):
            result = await chat_mod._record_usage(session, uid=1, payload=payload, usage=usage)

        assert result["input_tokens"] == floor
        assert result["cost"] == floor + 50


# ── Estimated input is never discounted ─────────────────────────────────────

class TestEstimatedInputIsNotDiscounted:
    @pytest.mark.asyncio
    async def test_fully_missing_usage_skips_the_discount_entirely(self, monkeypatch):
        _patch_provider(monkeypatch)
        overhead_lookup = AsyncMock(return_value=500)
        payload = {"model": "ninerouter/cc/some-model", "messages": SHORT_MESSAGES}
        expected_input = _estimate_input_tokens(payload["messages"])

        session = _FakeSession(wallet_balance=10_000_000, price=_price())
        with patch.object(upstream_overhead, 'get_prompt_overhead', new=overhead_lookup):
            result = await chat_mod._record_usage(
                session, uid=1, payload=payload, usage={}, response_text="پاسخ کوتاه",
            )

        # input_tokens came from _estimate_input_tokens (no injected preamble
        # to strip by construction) -- must equal the raw local estimate,
        # completely untouched by the (mocked, generous) overhead lookup.
        assert result["input_tokens"] == expected_input
        overhead_lookup.assert_not_awaited()

        event = _usage_event(session)
        assert event.meta["prompt_overhead_discounted"] == 0
        assert event.meta["prompt_tokens_raw"] == expected_input
        assert event.meta["estimated"] is True


# ── get_prompt_overhead's fail-safe contract ────────────────────────────────

class TestGetPromptOverheadFailSafe:
    @pytest.mark.asyncio
    async def test_returns_zero_not_exception_or_none_when_redis_and_db_both_fail(self):
        with patch.object(upstream_overhead, 'async_session', None), \
             patch.object(upstream_overhead.rds, 'get', new=AsyncMock(side_effect=Exception('redis down'))):
            value = await upstream_overhead.get_prompt_overhead('ninerouter', 'cc/claude-haiku')
        assert value == 0
        assert value is not None

    @pytest.mark.asyncio
    async def test_no_provider_returns_zero(self):
        assert await upstream_overhead.get_prompt_overhead('', 'cc/claude-haiku') == 0
        assert await upstream_overhead.get_prompt_overhead(None, 'cc/claude-haiku') == 0

    @pytest.mark.asyncio
    async def test_malformed_stored_value_returns_zero_not_exception(self):
        with patch.object(upstream_overhead.rds, 'get', new=AsyncMock(return_value='"not a dict"')):
            value = await upstream_overhead.get_prompt_overhead('ninerouter', 'cc/claude-haiku')
        assert value == 0

    @pytest.mark.asyncio
    async def test_entries_lookup_beats_provider_default(self):
        stored = '{"entries": {"ninerouter:cc": 250}, "provider_default": {"ninerouter": 50}}'
        with patch.object(upstream_overhead.rds, 'get', new=AsyncMock(return_value=stored)):
            value = await upstream_overhead.get_prompt_overhead('ninerouter', 'cc/claude-haiku')
        assert value == 250

    @pytest.mark.asyncio
    async def test_unmeasured_prefix_falls_back_to_provider_default(self):
        stored = '{"entries": {"ninerouter:cc": 250}, "provider_default": {"ninerouter": 50}}'
        with patch.object(upstream_overhead.rds, 'get', new=AsyncMock(return_value=stored)):
            value = await upstream_overhead.get_prompt_overhead('ninerouter', 'unknownprefix/some-model')
        assert value == 50

    @pytest.mark.asyncio
    async def test_unknown_provider_with_no_default_returns_zero(self):
        stored = '{"entries": {"ninerouter:cc": 250}, "provider_default": {"ninerouter": 50}}'
        with patch.object(upstream_overhead.rds, 'get', new=AsyncMock(return_value=stored)):
            value = await upstream_overhead.get_prompt_overhead('litellm', 'tencent-hy3-free')
        assert value == 0


# ── meta merge preserves pre-existing keys (L4 shortfall + discount together) ─

class TestMetaMergePreservesExistingKeys:
    @pytest.mark.asyncio
    async def test_shortfall_keys_and_overhead_keys_coexist_in_meta(self, monkeypatch):
        _patch_provider(monkeypatch)
        # Wallet balance far below the listed cost -> L4 shortfall path also
        # writes meta['listed_cost'] / meta['shortfall']; this must not be
        # clobbered by the overhead keys being added afterwards, and vice
        # versa.
        usage = {"prompt_tokens": 1000, "completion_tokens": 100}
        payload = {"model": "ninerouter/cc/some-model", "messages": SHORT_MESSAGES}
        session = _FakeSession(wallet_balance=10, price=_price())
        with patch.object(upstream_overhead, 'get_prompt_overhead', new=AsyncMock(return_value=300)):
            result = await chat_mod._record_usage(session, uid=1, payload=payload, usage=usage)

        assert result["cost"] == 10  # shortfall: only 10 available
        event = _usage_event(session)
        assert event.meta["listed_cost"] == 700 + 100  # discounted listed cost, not raw
        assert event.meta["shortfall"] == (700 + 100) - 10
        assert event.meta["prompt_tokens_raw"] == 1000
        assert event.meta["prompt_overhead_discounted"] == 300
        assert event.meta["estimated"] is False
        assert event.meta["source"] == "upstream"
