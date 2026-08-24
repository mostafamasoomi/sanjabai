"""A user holding wallet credit is never free-tier throttled.

Reported from production: an account with 9,954,787 toman was refused with
"your credit has run out" and sent to the top-up page. The gate consulted
only the payment tables, and that balance had been seeded directly rather
than arriving through the gateway, so `has_paid()` was False and the
five-messages-per-model cap applied to someone who had plenty of money.

The balance is a sound signal now: wallet credit can only be raised by the
payment gateway or by an admin (the signup gift and referral bonus are gone,
and tests/test_credit_paths.py enforces that allowlist), so a positive
balance means someone either paid or was deliberately granted credit.
"""
from unittest.mock import AsyncMock, patch

import pytest

import services.free_tier as ft


def _row(found: bool):
    result = AsyncMock()
    result.fetchone = lambda: (1,) if found else None
    return result


class _Session:
    def __init__(self, found):
        self._found = found

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *a, **k):
        return _row(self._found)


@pytest.mark.asyncio
async def test_a_user_with_balance_is_not_throttled(monkeypatch):
    """The exact reported case: money in the wallet, no gateway payment row."""
    monkeypatch.setattr(ft, 'async_session', lambda: _Session(True))
    with patch.object(ft, 'has_paid', AsyncMock(return_value=False)):
        # rds must never be consulted -- the gate should short-circuit before
        # it ever looks at a message counter.
        monkeypatch.setattr(ft, 'rds', AsyncMock(side_effect=AssertionError))
        assert await ft.check_and_consume(1, ['sanjab/x']) is None


@pytest.mark.asyncio
async def test_a_user_with_no_balance_still_hits_the_gate(monkeypatch):
    """Guard the guard: the free tier must still gate a zero-balance user.
    Here a premium model is refused -- the cheap-model gate is the first of
    the three free-tier checks and needs no counter state to demonstrate."""
    async def _cfg():
        return {'free_hourly_limit': 3, 'free_lifetime_limit': 30,
                'free_tier_max_input_per_million': 60000}
    monkeypatch.setattr(ft, 'get_config', _cfg)
    monkeypatch.setattr(ft, '_model_input_price', AsyncMock(return_value=953000))
    with patch.object(ft, 'has_paid', AsyncMock(return_value=False)), \
         patch.object(ft, 'has_balance', AsyncMock(return_value=False)):
        gate = await ft.check_and_consume(1, ['sanjab/x'])
    assert gate is not None and gate['code'] == 'free_model_not_allowed'


@pytest.mark.asyncio
async def test_has_balance_fails_closed_on_a_db_error(monkeypatch):
    """An unreadable balance must not silently grant unlimited access."""
    class _Boom:
        async def __aenter__(self): raise RuntimeError('db down')
        async def __aexit__(self, *exc): return False
    monkeypatch.setattr(ft, 'async_session', lambda: _Boom())
    assert await ft.has_balance(1) is False
