"""Regression tests for the billing loss-path audit (L5) plus the quota
self-healing / daily-limit-gate findings from the same live-verification
pass. Split off test_billing_loss_paths.py under the 500-line cap; see that
file's docstring for L1-L4 (the _record_usage cost-calculation paths).

Covers:
  L5 - the margin guard helper's boundary cases (services.margin)
  Quota - self-healing upsert for the daily-usage counter, and a structural
          check that the daily-limit *enforcement* gate is unreachable on
          the normal request path (found during live verification of the
          L1-L5 audit; see TestQuotaSelfHealingUpsert /
          TestDailyLimitGateStructurallyUnreachableOnHealthyPath below)

Follows this suite's existing conventions (see test_wallet_balance_charge.py):
a minimal fake AsyncSession double standing in for the handful of statements
chat._record_usage / SqlBillingRepo issue, no live DB needed. The double
itself lives in _billing_loss_paths_fakes.py, shared with the L1-L4 half of
this split.
"""
from __future__ import annotations

import types
from datetime import datetime, timedelta, timezone

import pytest

import chat as chat_mod
from services.margin import MIN_MARGIN_PCT, check_margin

from tests._billing_loss_paths_fakes import _FakeSession, _price, _usage


# ── L5: margin guard boundary cases ────────────────────────────────────────

class TestL5MarginGuard:
    def test_free_upstream_always_ok(self):
        check = check_margin(listed_per_million=1, upstream_cost_per_million=0)
        assert check.ok is True
        assert check.margin_pct is None

    def test_listed_below_upstream_cost_is_never_ok(self):
        check = check_margin(listed_per_million=100, upstream_cost_per_million=200)
        assert check.ok is False
        assert 'below upstream cost' in check.reason

    def test_listed_equal_to_upstream_cost_is_not_ok(self):
        """Zero margin does not clear a positive minimum-margin floor."""
        check = check_margin(listed_per_million=100, upstream_cost_per_million=100)
        assert check.ok is False
        assert check.margin_pct == 0.0

    def test_margin_exactly_at_floor_is_ok(self):
        """Boundary is inclusive: margin_pct == min_margin_pct passes."""
        check = check_margin(listed_per_million=120, upstream_cost_per_million=100, min_margin_pct=20)
        assert check.ok is True
        assert check.margin_pct == pytest.approx(20.0)

    def test_margin_just_below_floor_is_not_ok(self):
        check = check_margin(listed_per_million=119, upstream_cost_per_million=100, min_margin_pct=20)
        assert check.ok is False

    def test_margin_comfortably_above_floor_is_ok(self):
        check = check_margin(listed_per_million=1000, upstream_cost_per_million=100, min_margin_pct=20)
        assert check.ok is True
        assert check.margin_pct == pytest.approx(900.0)

    def test_negative_inputs_are_invalid(self):
        assert check_margin(listed_per_million=-1, upstream_cost_per_million=100).ok is False
        assert check_margin(listed_per_million=100, upstream_cost_per_million=-1).ok is False

    def test_default_min_margin_pct_is_twenty(self):
        assert MIN_MARGIN_PCT == 20.0


# ── Quota tracking: self-healing upsert (found during live verification) ──
#
# _record_usage's quota update used to be UPDATE-shaped only: if no `quota`
# row existed for a user, it matched zero rows and silently did nothing --
# auth.py only creates a row for accounts that signed up AFTER that code
# existed, so any earlier account (this deployment's only real user
# included) tracked no usage at all, ever. Fixed to upsert: create the row
# on first use if missing, and roll `used_today` over when `reset_at` has
# passed (previously only the rarely-reached _check_quota_pre fallback did
# that rollover).

class TestUsageIdempotencyKeyIsNotUpstreamDependent:
    """Found live (2026-08-21) while verifying the quota fix: the ledger
    idempotency_key used to be f"usage:{resp_id}" alone. tencent-hy3-free
    and mimo-v2.5-free were both observed returning the IDENTICAL
    completion `id` across genuinely distinct requests -- every billing
    attempt after the first for that model then hit
    uq_ledger_idempotency_key and rolled back the whole transaction
    (ledger + wallet + quota), for a fully served response. The key must
    now be unique regardless of what the upstream sends."""

    def test_same_resp_id_produces_different_keys(self):
        """The exact regression: reusing the same (buggy-upstream) resp_id
        across two calls must not collide."""
        k1 = chat_mod._usage_idempotency_key("chatcmpl-fe76178")
        k2 = chat_mod._usage_idempotency_key("chatcmpl-fe76178")
        assert k1 != k2

    def test_missing_resp_id_still_produces_a_usable_key(self):
        key = chat_mod._usage_idempotency_key(None)
        assert key and key.startswith("usage:")

    def test_resp_id_is_preserved_for_debugging(self):
        key = chat_mod._usage_idempotency_key("chatcmpl-abc123")
        assert "chatcmpl-abc123" in key


class TestAsNaiveUtc:
    """_as_naive_utc: the tz-normalization helper that fixes the live
    'can't compare offset-naive and offset-aware datetimes' crash found
    while verifying the quota upsert (quota.reset_at comes back tz-aware
    from a TIMESTAMPTZ column; this codebase's convention everywhere else
    is naive UTC)."""

    def test_none_passes_through(self):
        assert chat_mod._as_naive_utc(None) is None

    def test_naive_passes_through_unchanged(self):
        dt = datetime(2026, 1, 1, 12, 0, 0)
        assert chat_mod._as_naive_utc(dt) == dt
        assert chat_mod._as_naive_utc(dt).tzinfo is None

    def test_aware_utc_is_stripped_to_naive(self):
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = chat_mod._as_naive_utc(aware)
        assert result.tzinfo is None
        assert result == datetime(2026, 1, 1, 12, 0, 0)

    def test_aware_non_utc_converts_to_utc_before_stripping(self):
        from datetime import timedelta as _td
        tz_plus_3 = timezone(_td(hours=3))
        aware = datetime(2026, 1, 1, 15, 0, 0, tzinfo=tz_plus_3)  # == 12:00 UTC
        result = chat_mod._as_naive_utc(aware)
        assert result.tzinfo is None
        assert result == datetime(2026, 1, 1, 12, 0, 0)

    def test_naive_and_aware_now_can_be_compared_without_raising(self):
        """The actual regression: this must not raise TypeError."""
        aware_past = datetime.now(timezone.utc) - timedelta(hours=1)
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        assert now_naive >= chat_mod._as_naive_utc(aware_past)


class TestQuotaSelfHealingUpsert:
    @pytest.mark.asyncio
    async def test_no_existing_row_creates_one(self):
        session = _FakeSession(wallet_balance=1_000_000, price=_price(), quota_row=None)
        await chat_mod._record_usage(
            session, uid=7, payload={"model": "kr/gpt-4o-mini"}, usage=_usage(),
        )
        quota_rows = [o for o in session.added if type(o).__name__ == "Quota"]
        assert len(quota_rows) == 1
        assert quota_rows[0].user_id == 7
        assert quota_rows[0].used_today == 1000  # _usage() total_tokens
        assert quota_rows[0].daily_limit == 200000
        assert quota_rows[0].reset_at is not None

    @pytest.mark.asyncio
    async def test_existing_row_within_window_increments(self):
        # reset_at is tz-AWARE here on purpose: quota.reset_at is a
        # TIMESTAMPTZ column, and asyncpg/SQLAlchemy hand back a
        # timezone-aware datetime for it in real life. An earlier version
        # of this test used a naive datetime, which passed here but
        # crashed in production with "can't compare offset-naive and
        # offset-aware datetimes" -- exactly because the double didn't
        # match reality. Keep it tz-aware so this test would have caught
        # that regression.
        quota_row = types.SimpleNamespace(
            used_today=500,
            reset_at=datetime.now(timezone.utc) + timedelta(hours=6),
        )
        # Snapshot the expectation BEFORE the call. _record_usage normalizes
        # reset_at in place, so after it returns quota_row.reset_at is already
        # naive-UTC; deriving the expected value from it afterwards then ran
        # .astimezone() on a naive datetime, which Python reads as LOCAL time.
        # That is a no-op on a UTC host (CI, the API container) but shifts by
        # the offset anywhere else, so the test passed in production and failed
        # on a UTC+08:00 dev box. The production code was right both times.
        expected_reset_at = quota_row.reset_at.astimezone(timezone.utc).replace(tzinfo=None)
        session = _FakeSession(wallet_balance=1_000_000, price=_price(), quota_row=quota_row)
        await chat_mod._record_usage(
            session, uid=7, payload={"model": "kr/gpt-4o-mini"}, usage=_usage(total=1000, prompt=800, completion=200),
        )
        assert session.quota_updates
        assert session.quota_updates[-1]["used_today"] == 1500  # 500 + 1000
        # reset_at untouched (still in the future) -- no rollover. Compared
        # as naive-UTC since that's the codebase-wide storage convention
        # (_as_naive_utc normalizes on the way in).
        assert session.quota_updates[-1]["reset_at"] == expected_reset_at
        quota_rows = [o for o in session.added if type(o).__name__ == "Quota"]
        assert quota_rows == []  # updated, not re-created

    @pytest.mark.asyncio
    async def test_existing_row_past_reset_at_rolls_over(self):
        """Previously only _check_quota_pre (a fallback rarely reached on
        the normal request path) rolled used_today over at reset_at --
        _record_usage now does this rollover too. tz-aware reset_at, same
        reasoning as the test above."""
        quota_row = types.SimpleNamespace(
            used_today=199_999,
            reset_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session = _FakeSession(wallet_balance=1_000_000, price=_price(), quota_row=quota_row)
        await chat_mod._record_usage(
            session, uid=7, payload={"model": "kr/gpt-4o-mini"}, usage=_usage(total=1000, prompt=800, completion=200),
        )
        assert session.quota_updates
        # Rolled over: today's usage only, not 199_999 + 1000.
        assert session.quota_updates[-1]["used_today"] == 1000
        assert session.quota_updates[-1]["reset_at"] > datetime.now(timezone.utc).replace(tzinfo=None)


# ── Confirming/refuting the daily-limit ENFORCEMENT gate (coordinator ask) ─
#
# _check_quota_pre is the only place in the codebase that reads
# Quota.daily_limit / used_today for enforcement (the 'quota_exceeded' /
# 'daily_limit' 429). It is called from chat()/chat_with_file()/
# compare_models()/smart_chat() *exclusively* inside the `except Exception`
# fallback after BillingService.reserve() -- i.e. only when reserve() raises
# something other than InsufficientBalanceError. On the normal, healthy
# request path reserve() just succeeds, so _check_quota_pre -- and the
# daily-limit check inside it -- never runs at all. This is verified
# structurally here (all 4 call sites are inside that except block, not
# unconditional) rather than by re-deriving the whole request flow.

class TestDailyLimitGateStructurallyUnreachableOnHealthyPath:
    def test_check_quota_pre_only_called_inside_reserve_except_blocks(self):
        import importlib
        import inspect

        # Every call site must be preceded (within a small window) by the
        # BillingService.reserve() fallback comment/except pattern this
        # audit found -- a crude but effective regression guard: if a
        # future change makes _check_quota_pre part of the normal path
        # (e.g. called unconditionally before reserve()), the surrounding
        # text will no longer match this fallback-only shape and this
        # assertion will need updating (that would be a real behavior
        # change worth reviewing, not a false failure to silence).
        #
        # The scan spans chat.py AND its chat_*.py siblings. It used to read
        # chat.py alone, when all four endpoints lived there; the 2,500-line
        # file was later split, moving /v1/compare and /v1/smart-chat into
        # their own modules and taking two of the four call sites with them.
        # That was a pure relocation -- the try/except shape at each site is
        # unchanged -- so the property below still holds and it is the
        # single-file mechanism that had to follow the code. Reading the
        # whole module family also means the next split cannot quietly
        # shrink this test's coverage without tripping the count.
        # Both spellings count. A module that does not define
        # _check_quota_pre itself must reach it late-bound through the chat
        # namespace (`chat._check_quota_pre`) so the tests' monkeypatching
        # keeps working -- that is the split's own contract, not a second
        # code path.
        forms = (
            'quota_err = await _check_quota_pre(uid)',
            'quota_err = await chat._check_quota_pre(uid)',
        )
        modules = [chat_mod] + [
            importlib.import_module(name)
            for name in ('chat_models', 'chat_web', 'chat_billing',
                         'chat_compare', 'chat_smart', 'chat_stream')
        ]
        call_sites = []
        for mod in modules:
            src = inspect.getsource(mod)
            call_sites += [
                src[max(0, i - 400):i]
                for i in range(len(src))
                if any(src.startswith(f, i) for f in forms)
                # `chat._check_quota_pre(` also starts a match for the bare
                # form five characters later; count each site once.
                and not src.startswith('_check_quota_pre(uid)', i - 5)
            ]
        assert len(call_sites) == 4, (
            f"expected exactly 4 _check_quota_pre call sites across the chat "
            f"modules, found {len(call_sites)}"
        )
        for window in call_sites:
            assert 'except Exception' in window
            assert 'reserve' in window.lower()
