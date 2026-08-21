"""Regression tests for the Zarinpal Rial/Toman currency bug.

Sanjabai's internal unit is integer Toman everywhere (Money.toman). Zarinpal's
v4 API defaults to Rial when the 'currency' field is absent from the payload,
which silently reinterprets a Toman amount as 10x its real value (the user is
charged 1/10 of the intended amount while the wallet is credited in full --
a 90% loss per transaction). Because create_payment and verify_payment used
to send the same bare number with no currency declared, verification passed
cleanly and nothing ever raised.

The fix declares 'currency': 'IRT' (Zarinpal's code for Toman) in BOTH
payloads, with no change to the amount arithmetic anywhere. These tests pin
that down so it cannot regress silently again.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import payment


def _mock_response(payload: dict) -> MagicMock:
    """Build a fake httpx.Response-like object with a synchronous .json()."""
    resp = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


def _patched_async_client(captured_calls: list, response_payload: dict):
    """Return a context manager class standing in for httpx.AsyncClient that
    records every POST payload into `captured_calls` and returns
    `response_payload` as the (mocked) JSON response.
    """

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, **kwargs):
            captured_calls.append({'url': url, 'json': json})
            return _mock_response(response_payload)

    return _FakeAsyncClient


class TestCreatePaymentCurrency:
    @pytest.mark.asyncio
    async def test_create_payment_sends_currency_irt(self):
        captured = []
        fake_client_cls = _patched_async_client(
            captured,
            {'data': {'code': 100, 'authority': 'A123'}},
        )
        with patch.object(payment, 'ZARINPAL_MERCHANT', 'merchant-test'), \
             patch.object(payment.httpx, 'AsyncClient', fake_client_cls):
            result = await payment.create_payment(
                amount=100000,
                description='test top-up',
                callback_url='https://sanjabai.com/callback',
            )

        assert result['status'] == 'ok'
        assert len(captured) == 1
        assert captured[0]['json']['currency'] == 'IRT'


class TestVerifyPaymentCurrency:
    @pytest.mark.asyncio
    async def test_verify_payment_sends_currency_irt(self):
        captured = []
        fake_client_cls = _patched_async_client(
            captured,
            {'data': {'code': 100, 'ref_id': 'REF456'}},
        )
        with patch.object(payment, 'ZARINPAL_MERCHANT', 'merchant-test'), \
             patch.object(payment.httpx, 'AsyncClient', fake_client_cls):
            result = await payment.verify_payment(amount=100000, authority='A123')

        assert result['status'] == 'verified'
        assert len(captured) == 1
        assert captured[0]['json']['currency'] == 'IRT'


class TestAmountIsNotRescaled:
    @pytest.mark.asyncio
    async def test_create_payment_amount_equals_internal_toman_amount(self):
        """The posted amount must be EXACTLY the internal Toman amount --
        no *10, no /10. Declaring the unit correctly (currency='IRT') is the
        whole fix; the number itself must never change."""
        captured = []
        fake_client_cls = _patched_async_client(
            captured,
            {'data': {'code': 100, 'authority': 'A123'}},
        )
        with patch.object(payment, 'ZARINPAL_MERCHANT', 'merchant-test'), \
             patch.object(payment.httpx, 'AsyncClient', fake_client_cls):
            await payment.create_payment(
                amount=100000,
                description='test top-up',
                callback_url='https://sanjabai.com/callback',
            )

        assert captured[0]['json']['amount'] == 100000

    @pytest.mark.asyncio
    async def test_verify_payment_amount_equals_internal_toman_amount(self):
        captured = []
        fake_client_cls = _patched_async_client(
            captured,
            {'data': {'code': 100, 'ref_id': 'REF456'}},
        )
        with patch.object(payment, 'ZARINPAL_MERCHANT', 'merchant-test'), \
             patch.object(payment.httpx, 'AsyncClient', fake_client_cls):
            await payment.verify_payment(amount=100000, authority='A123')

        assert captured[0]['json']['amount'] == 100000


class TestCreateAndVerifyAgree:
    @pytest.mark.asyncio
    async def test_create_and_verify_send_same_amount_and_currency(self):
        """For the same order, create_payment and verify_payment must post
        the identical amount AND the identical currency -- a mismatch here
        is exactly the class of bug that let the original defect hide:
        both legs agreeing (even on the WRONG unit) makes verification look
        clean regardless of what actually happened at the gateway."""
        order_amount = 250000  # Toman

        create_captured = []
        create_client_cls = _patched_async_client(
            create_captured,
            {'data': {'code': 100, 'authority': 'ORDER-XYZ'}},
        )
        with patch.object(payment, 'ZARINPAL_MERCHANT', 'merchant-test'), \
             patch.object(payment.httpx, 'AsyncClient', create_client_cls):
            await payment.create_payment(
                amount=order_amount,
                description='test top-up',
                callback_url='https://sanjabai.com/callback',
            )

        verify_captured = []
        verify_client_cls = _patched_async_client(
            verify_captured,
            {'data': {'code': 100, 'ref_id': 'REF789'}},
        )
        with patch.object(payment, 'ZARINPAL_MERCHANT', 'merchant-test'), \
             patch.object(payment.httpx, 'AsyncClient', verify_client_cls):
            await payment.verify_payment(amount=order_amount, authority='ORDER-XYZ')

        create_payload = create_captured[0]['json']
        verify_payload = verify_captured[0]['json']

        assert create_payload['amount'] == verify_payload['amount'] == order_amount
        assert create_payload['currency'] == verify_payload['currency'] == 'IRT'


class TestGatewayNotConfigured:
    @pytest.mark.asyncio
    async def test_create_payment_503_when_merchant_unset(self):
        with patch.object(payment, 'ZARINPAL_MERCHANT', ''):
            result = await payment.create_payment(
                amount=100000,
                description='test top-up',
                callback_url='https://sanjabai.com/callback',
            )
        assert result['status'] == 503

    @pytest.mark.asyncio
    async def test_verify_payment_503_when_merchant_unset(self):
        with patch.object(payment, 'ZARINPAL_MERCHANT', ''):
            result = await payment.verify_payment(amount=100000, authority='A123')
        assert result['status'] == 503
