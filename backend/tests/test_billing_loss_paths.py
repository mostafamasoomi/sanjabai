"""Regression tests for the billing loss-path audit (L1-L4): the actual
cost-calculation paths inside chat._record_usage.

The owner's hard requirement: "we must be profitable on the price we offer
the user, and must never lose money on any request, in the ratio of the
user's usage of each model against what we pay per token."

Covers:
  L1 - missing/malformed upstream usage -> local estimate, bills > 0
       (chat._record_usage)
  L2 - price-lookup miss bills at the fallback CEILING rate, not the old
       `total_tokens // 1000` guess (chat._record_usage)
  L3 - reasoning tokens are folded into output_tokens exactly once, never
       summed across multiple possible fields (chat._extract_reasoning_tokens,
       chat._record_usage)
  L4 - a settle that exceeds the reservation still charges what's available
       and always writes a ledger row + logs the shortfall
       (chat._record_usage)

L5 (margin guard), the quota self-healing upsert, and the daily-limit-gate
structural check live in test_billing_loss_paths_quota.py -- this file was
split under the 500-line cap; see that file's docstring for the rest of
the audit.

Follows this suite's existing conventions (see test_wallet_balance_charge.py):
a minimal fake AsyncSession double standing in for the handful of statements
chat._record_usage / SqlBillingRepo issue, no live DB needed. The double
itself lives in _billing_loss_paths_fakes.py, shared with the quota half of
this split.
"""
from __future__ import annotations

import logging

import pytest

import chat as chat_mod
# _usage is re-exported here (unused by this file's own L1-L4 tests) because
# test_entitlement_gate.py does `from tests.test_billing_loss_paths import
# _FakeSession, _price, _usage` -- keep that cross-file import working
# without touching a file outside this split's scope.
from tests._billing_loss_paths_fakes import _FakeSession, _price, _usage  # noqa: F401


# ── L1: missing/malformed usage falls back to a local estimate ────────────

class TestL1MissingUsageFallsBackToEstimate:
    @pytest.mark.asyncio
    async def test_fully_missing_usage_bills_greater_than_zero(self, caplog):
        """Upstream omitted `usage` entirely (empty dict) -- previously this
        served the response and billed nothing. Must now bill a positive
        amount derived from a local estimate of the actual messages/response
        text, and must say so out loud (auditability)."""
        session = _FakeSession(wallet_balance=1_000_000, price=_price())
        payload = {
            "model": "some-model",
            "messages": [
                {"role": "user", "content": "سلام، امروز هوا چطور است؟ " * 5},
            ],
        }
        with caplog.at_level(logging.WARNING):
            result = await chat_mod._record_usage(
                session, uid=1, payload=payload, usage={},
                response_text="پاسخ کاملاً معتبر از مدل هوش مصنوعی است.",
            )

        assert result["input_tokens"] > 0
        assert result["output_tokens"] > 0
        assert result["cost"] > 0
        assert session.wallet.balance < 1_000_000
        ledger_rows = [o for o in session.added if type(o).__name__ == "Ledger"]
        assert len(ledger_rows) == 1
        assert ledger_rows[0].amount == -result["cost"]
        assert any("LOCAL ESTIMATE" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_estimate_log_states_it_is_a_known_lower_bound(self, caplog):
        """The estimate fallback cannot see upstream-injected preamble
        tokens (observed live: ~2784-5756 prompt_tokens for a 2-character
        message on some routes, added server-side after our outgoing
        payload leaves us). The same conversation can therefore show wildly
        different input_tokens depending on whether usage came back for a
        given request. The log must say this loudly, not just report a
        number that looks authoritative."""
        session = _FakeSession(wallet_balance=1_000_000, price=_price())
        with caplog.at_level(logging.WARNING):
            await chat_mod._record_usage(
                session, uid=1,
                payload={"model": "some-model", "messages": [{"role": "user", "content": "hello there"}]},
                usage={}, response_text="hi",
            )
        messages = [r.message for r in caplog.records]
        assert any("KNOWN LOWER BOUND" in m for m in messages)
        assert any("do not treat this number as authoritative" in m for m in messages)

    def test_estimate_never_bills_less_than_one_token_per_side_of_real_text(self):
        """Sanity check on the estimate heuristic itself: non-trivial input
        and output text must not round down to zero tokens (that would
        silently reproduce the L1 bug through the back door)."""
        assert chat_mod._estimate_input_tokens([{"role": "user", "content": "متن آزمایشی"}]) > 0
        assert chat_mod._estimate_output_tokens("یک پاسخ کوتاه") > 0
        assert chat_mod._estimate_input_tokens([]) == 0
        assert chat_mod._estimate_output_tokens("") == 0

    @pytest.mark.asyncio
    async def test_no_messages_and_no_response_text_bills_nothing(self):
        """If there is truly nothing to estimate from (no messages, no
        response), nothing was served -- must not fabricate a charge."""
        session = _FakeSession(wallet_balance=1_000_000, price=_price())
        result = await chat_mod._record_usage(
            session, uid=1, payload={"model": "some-model", "messages": []}, usage={},
            response_text="",
        )
        assert result["cost"] == 0
        assert session.added == []
        assert session.wallet.balance == 1_000_000

    @pytest.mark.asyncio
    async def test_partial_usage_missing_output_side_still_estimates_output(self):
        """Upstream reported real prompt_tokens but botched completion_tokens
        (reported as 0/absent) -- must still estimate the missing output
        side rather than billing it as zero."""
        session = _FakeSession(wallet_balance=1_000_000, price=_price())
        usage = {"prompt_tokens": 50, "completion_tokens": 0}
        result = await chat_mod._record_usage(
            session, uid=1, payload={"model": "some-model", "messages": []}, usage=usage,
            response_text="یک پاسخ نسبتاً طولانی برای اطمینان از تخمین درست خروجی.",
        )
        assert result["input_tokens"] == 50
        assert result["output_tokens"] > 0


# ── L2: price-lookup miss bills at the fallback ceiling, not //1000 ───────

class TestL2PriceLookupMissBillsAtFallbackCeiling:
    @pytest.mark.asyncio
    async def test_missing_price_row_uses_fallback_constants_not_floor_division(self, caplog):
        session = _FakeSession(wallet_balance=10_000_000, price=None)
        usage = {"total_tokens": 1000, "prompt_tokens": 800, "completion_tokens": 200}
        with caplog.at_level(logging.ERROR):
            result = await chat_mod._record_usage(
                session, uid=1, payload={"model": "unknown/model"}, usage=usage,
            )

        expected = max(
            1,
            (800 * chat_mod.FALLBACK_PRICE_PER_MILLION_IN
             + 200 * chat_mod.FALLBACK_PRICE_PER_MILLION_OUT + 500_000) // 1_000_000,
        )
        old_buggy_fallback = max(1, 1000 // 1000)  # == 1 -- the bug this replaces

        assert result["cost"] == expected
        # The whole point of L2: never fall back to the old //1000 guess,
        # which would have billed ~238x too little for a model like Gemini
        # 2.5 Pro.
        assert result["cost"] != old_buggy_fallback
        assert result["cost"] > old_buggy_fallback
        assert any("no price row" in r.message for r in caplog.records)

    def test_fallback_constants_are_the_catalog_ceiling(self):
        """Documents the exact numbers chosen and why: as of 2026-08-21 the
        max input/output rate among availability='available' model_catalog
        rows was kr/claude-sonnet-4.5-thinking at 571800 / 2859000 IRT per
        million. Pinning this test to the constant (not a hardcoded number)
        so a deliberate future retune doesn't spuriously fail it, while
        still asserting the values are sane (positive, output > input, as
        every priced model in this catalog has output priced higher)."""
        assert chat_mod.FALLBACK_PRICE_PER_MILLION_IN > 0
        assert chat_mod.FALLBACK_PRICE_PER_MILLION_OUT > 0
        assert chat_mod.FALLBACK_PRICE_PER_MILLION_OUT > chat_mod.FALLBACK_PRICE_PER_MILLION_IN


# ── L3: reasoning tokens counted once, never twice ─────────────────────────

class TestL3ReasoningTokensCountedOnceNotTwice:
    def test_reads_nested_openai_style_field(self):
        usage = {"completion_tokens": 100, "completion_tokens_details": {"reasoning_tokens": 40}}
        assert chat_mod._extract_reasoning_tokens(usage) == 40

    def test_reads_top_level_field_when_nested_absent(self):
        usage = {"completion_tokens": 100, "reasoning_tokens": 40}
        assert chat_mod._extract_reasoning_tokens(usage) == 40

    def test_never_sums_nested_and_top_level_fields(self):
        """If a gateway (mis)reports reasoning tokens in BOTH shapes at
        once, only one value is taken -- never double-counted."""
        usage = {
            "completion_tokens": 100,
            "completion_tokens_details": {"reasoning_tokens": 40},
            "reasoning_tokens": 40,
        }
        assert chat_mod._extract_reasoning_tokens(usage) == 40  # not 80

    def test_no_reasoning_field_returns_zero(self):
        assert chat_mod._extract_reasoning_tokens({"completion_tokens": 100}) == 0

    @pytest.mark.asyncio
    async def test_record_usage_bills_reasoning_tokens_via_output_rate(self):
        """completion_tokens=100 + reasoning_tokens=40 must bill for 140
        output tokens (folded in, billed at the output rate) -- not 100
        (reasoning silently dropped) and not 240 (double-counted)."""
        session = _FakeSession(wallet_balance=10_000_000, price=_price(inp=1_000_000, out=1_000_000))
        usage = {
            "prompt_tokens": 50,
            "completion_tokens": 100,
            "completion_tokens_details": {"reasoning_tokens": 40},
        }
        result = await chat_mod._record_usage(
            session, uid=1, payload={"model": "kr/claude-sonnet-4.5-thinking"}, usage=usage,
        )
        assert result["output_tokens"] == 140
        assert result["cost"] == 50 + 140  # 1 IRT/token at this test's price


# ── L4: shortfall still charges available balance and records it ──────────

class TestL4ShortfallChargesAvailableAndRecords:
    @pytest.mark.asyncio
    async def test_shortfall_writes_ledger_row_and_logs_warning(self, caplog):
        session = _FakeSession(wallet_balance=500, price=_price())
        usage = {"total_tokens": 1000, "prompt_tokens": 800, "completion_tokens": 200}
        with caplog.at_level(logging.WARNING):
            result = await chat_mod._record_usage(
                session, uid=42, payload={"model": "kr/gpt-4o-mini"}, usage=usage,
            )

        # Listed cost is 1000 but only 500 is available.
        assert result["cost"] == 500
        assert session.wallet.balance == 0
        assert result["balance_after"] == 0

        ledger_rows = [o for o in session.added if type(o).__name__ == "Ledger"]
        assert len(ledger_rows) == 1
        assert ledger_rows[0].amount == -500
        assert ledger_rows[0].balance_after == 0

        shortfall_logs = [r.message for r in caplog.records if "L4 shortfall" in r.message]
        assert len(shortfall_logs) == 1
        assert "uid=42" in shortfall_logs[0]
        assert "kr/gpt-4o-mini" in shortfall_logs[0]
        assert "cost=1000" in shortfall_logs[0]
        assert "balance_before=500" in shortfall_logs[0]

    @pytest.mark.asyncio
    async def test_shortfall_never_pushes_balance_negative(self):
        session = _FakeSession(wallet_balance=1, price=_price())
        usage = {"total_tokens": 1000, "prompt_tokens": 800, "completion_tokens": 200}
        result = await chat_mod._record_usage(
            session, uid=1, payload={"model": "kr/gpt-4o-mini"}, usage=usage,
        )
        assert result["cost"] == 1
        assert session.wallet.balance == 0
        assert result["balance_after"] == 0

    @pytest.mark.asyncio
    async def test_full_shortfall_at_zero_balance_writes_no_ledger_row(self, caplog):
        """A zero-balance settlement charges 0, so NO ledger row may be
        written: the ledger_amount_check constraint forbids amount=0, and a
        zero-amount entry would mean "money moved" when none did. Regression
        for the live IntegrityError that crashed usage recording for a
        zero-balance user (charged=0 -> Ledger(amount=0) -> constraint
        violation -> the whole _track_usage aborted, chat still returned 200
        but nothing was recorded and the logs filled with errors)."""
        session = _FakeSession(wallet_balance=0, price=_price())
        usage = {"total_tokens": 1000, "prompt_tokens": 800, "completion_tokens": 200}
        with caplog.at_level(logging.WARNING):
            result = await chat_mod._record_usage(
                session, uid=22, payload={"model": "some-model"}, usage=usage,
            )
        assert result["cost"] == 0
        assert session.wallet.balance == 0
        assert result["balance_after"] == 0
        ledger_rows = [o for o in session.added if type(o).__name__ == "Ledger"]
        # No money moved -> no ledger row at all, and never a zero-amount one.
        assert ledger_rows == []
        assert all(r.amount != 0 for r in ledger_rows)
        # The shortfall is still made visible for reconciliation (the log).
        shortfall_logs = [r.message for r in caplog.records if "L4 shortfall" in r.message]
        assert len(shortfall_logs) == 1
        assert "balance_before=0" in shortfall_logs[0]
