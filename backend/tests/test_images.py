"""Tests for POST /v1/images/generations (backend/images.py).

This endpoint is NOT wired into app.py yet (a separate agent owns app.py
concurrently -- the coordinator adds the include_router line once this is
reviewed), so these tests mount images.router on a throwaway FastAPI app
instead of using the shared `client`/conftest app fixture. That also keeps
this file fully decoupled from chat.py's concurrent edits: every chat.py
symbol images.py imports (_resolve_public_model, _resolve_provider,
_release_reservation) is patched at the images.py call site, never exercised
for real, so nothing here depends on chat.py's current internals -- only on
the three names images.py imports from it.

No live Postgres/Redis/network: `_load_image_model` (the one place images.py
touches model_catalog) and `get_effective_markup_pct` are patched directly
rather than reconstructed with a fake SQLAlchemy session -- there is nothing
DB-shaped left for these tests to fake once that boundary is mocked. The
upstream HTTP call goes through a fake `_http` object with `.post()` swapped
in, same idea as test_public_model_ids.py's `_patched_http` helper.
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import images as images_mod
from content import apply_markup
from services.money import Money


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(images_mod.router)
    return TestClient(app)


def _row(availability='available', price=1000, markup_pct=None):
    return types.SimpleNamespace(
        provider_model_id='pollinations/flux',
        availability=availability,
        image_price_per_unit=price,
        markup_pct=markup_pct,
    )


def _billing_mock():
    """Same shape as test_public_model_ids.py's `_billing_mock()`: a
    BillingService replacement whose reserve/settle/release never touch a
    real DB and can be asserted against directly."""
    instance = MagicMock()
    instance.reserve = AsyncMock(return_value={'reservation_id': 'resv-1', 'hold_amount': 0})
    instance.settle = AsyncMock(return_value=None)
    instance.release = AsyncMock(return_value=None)
    return MagicMock(return_value=instance), instance


def _fake_async_session():
    """A no-op `async with async_session() as s:` -- BillingService itself
    is always mocked in these tests, so the only thing ever actually called
    on the yielded session is `.commit()` (images.py awaits it directly,
    outside of BillingService)."""
    class _Ctx:
        async def __aenter__(self):
            session = MagicMock()
            session.commit = AsyncMock(return_value=None)
            return session

        async def __aexit__(self, *a):
            return None

    return MagicMock(return_value=_Ctx())


def _fake_provider():
    p = MagicMock()
    p.v1 = 'http://fake-upstream/v1'
    p.headers = MagicMock(return_value={'Content-Type': 'application/json'})
    return p


def _upstream_response(status_code=200, body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=body if body is not None else {})
    resp.content = b'{}'
    return resp


class _BasePatches:
    """Bundles the patches every test needs: auth, resolver passthrough,
    provider routing, async_session, and BillingService. Each test layers
    `_load_image_model`, `_http`, and `get_effective_markup_pct` on top for
    its own scenario."""

    def __init__(self, *, row, http_post=None, markup_pct=0):
        self.row = row
        self.billing_cls, self.billing_instance = _billing_mock()
        self.release_spy = AsyncMock(return_value=None)
        self.fake_http = MagicMock()
        self.fake_http.post = http_post or AsyncMock(return_value=_upstream_response())
        self.markup_pct = markup_pct

    def __enter__(self):
        self._patches = [
            patch.object(images_mod, '_get_user_id', AsyncMock(return_value=42)),
            patch.object(images_mod, '_resolve_public_model', AsyncMock(side_effect=lambda m: m)),
            patch.object(images_mod, '_resolve_provider', AsyncMock(return_value=_fake_provider())),
            patch.object(images_mod, '_release_reservation', self.release_spy),
            patch.object(images_mod, '_load_image_model', AsyncMock(return_value=self.row)),
            patch.object(images_mod, 'get_effective_markup_pct', AsyncMock(return_value=self.markup_pct)),
            patch.object(images_mod, 'async_session', _fake_async_session()),
            patch.object(images_mod, 'BillingService', self.billing_cls),
            patch.object(images_mod, '_http', self.fake_http),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self._patches:
            p.stop()


@pytest.fixture
def client():
    return _make_client()


# ── Gate 1: availability ──────────────────────────────────────────────────

class TestAvailabilityGate:
    def test_maintenance_model_refused(self, client):
        """Every image model is 'maintenance' today -- this must refuse the
        request, and it must not touch billing at all."""
        with _BasePatches(row=_row(availability='maintenance')) as p:
            resp = client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': 'a cat'})
        assert resp.status_code == 400
        body = resp.json()
        assert body['error']['code'] == 'model_not_available'
        p.billing_instance.reserve.assert_not_called()
        p.release_spy.assert_not_called()

    def test_unknown_model_refused(self, client):
        with _BasePatches(row=None) as p:
            resp = client.post('/v1/images/generations', json={'model': 'nope/nope', 'prompt': 'a cat'})
        assert resp.status_code == 400
        assert resp.json()['error']['code'] == 'model_not_available'
        p.billing_instance.reserve.assert_not_called()


# ── Gate 2: price ──────────────────────────────────────────────────────────

class TestPriceGate:
    def test_available_model_with_null_price_refused_and_nothing_billed(self, client):
        with _BasePatches(row=_row(availability='available', price=None)) as p:
            resp = client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': 'a cat'})
        assert resp.status_code == 400
        assert resp.json()['error']['code'] == 'price_not_set'
        # Nothing is billed: no reservation is ever opened for this model,
        # and consequently nothing is ever released either.
        p.billing_instance.reserve.assert_not_called()
        p.billing_instance.settle.assert_not_called()
        p.release_spy.assert_not_called()


# ── Gate ordering: resolve runs before the DB gate check ──────────────────

class TestResolveRunsBeforeGates:
    def test_resolve_called_before_availability_lookup(self, client):
        order: list[str] = []

        async def _resolve(m):
            order.append('resolve')
            return m

        async def _load(mid):
            order.append('gate_check')
            return _row(availability='maintenance')

        with patch.object(images_mod, '_get_user_id', AsyncMock(return_value=42)), \
             patch.object(images_mod, '_resolve_public_model', _resolve), \
             patch.object(images_mod, '_load_image_model', _load):
            resp = client.post('/v1/images/generations', json={'model': 'sanjab/flux', 'prompt': 'a cat'})
        assert resp.status_code == 400
        assert order == ['resolve', 'gate_check']


# ── Response shape parsing (both documented OpenAI shapes) ─────────────────

class TestResponseShapeParsing:
    def test_url_shape_bills_and_returns_200(self, client):
        body = {'created': 1, 'data': [{'url': 'https://example.com/a.png'}]}
        with _BasePatches(row=_row(price=1000, markup_pct=0),
                           http_post=AsyncMock(return_value=_upstream_response(body=body))) as p:
            resp = client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': 'a cat', 'n': 1})
        assert resp.status_code == 200, resp.text
        assert resp.json()['billing']['images'] == 1
        p.billing_instance.settle.assert_awaited_once()
        args, _ = p.billing_instance.settle.await_args
        assert args[0] == 'resv-1'
        assert args[1] == Money(1000)

    def test_b64_shape_bills_and_returns_200(self, client):
        body = {'created': 1, 'data': [{'b64_json': 'aGVsbG8='}]}
        with _BasePatches(row=_row(price=1000, markup_pct=0),
                           http_post=AsyncMock(return_value=_upstream_response(body=body))) as p:
            resp = client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': 'a cat', 'n': 1})
        assert resp.status_code == 200, resp.text
        assert resp.json()['billing']['images'] == 1
        p.billing_instance.settle.assert_awaited_once()
        args, _ = p.billing_instance.settle.await_args
        assert args[1] == Money(1000)


# ── Partial delivery: n=2 requested, 1 returned -> bill for 1 ─────────────

class TestPartialDelivery:
    def test_n2_returning_1_image_bills_for_exactly_1(self, client):
        body = {'data': [{'url': 'https://example.com/only-one.png'}]}
        with _BasePatches(row=_row(price=1000, markup_pct=0),
                           http_post=AsyncMock(return_value=_upstream_response(body=body))) as p:
            resp = client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': 'a cat', 'n': 2})
        assert resp.status_code == 200, resp.text
        assert resp.json()['billing']['images'] == 1
        p.billing_instance.settle.assert_awaited_once()
        args, _ = p.billing_instance.settle.await_args
        # 2 requested x 1000 reserved, but only 1 image actually came back --
        # bill for exactly that one, not the reserved upper bound.
        assert args[1] == Money(1000)
        p.billing_instance.reserve.assert_awaited_once()
        reserve_args, _ = p.billing_instance.reserve.await_args
        assert reserve_args[1] == Money(2000)


# ── Upstream failure modes: bill nothing, release the reservation ─────────

class TestUpstreamFailureBillsNothing:
    def test_empty_data_bills_nothing_and_releases(self, client):
        body = {'data': []}
        with _BasePatches(row=_row(price=1000, markup_pct=0),
                           http_post=AsyncMock(return_value=_upstream_response(body=body))) as p:
            resp = client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': 'a cat'})
        assert resp.status_code == 502
        assert resp.json()['error']['code'] == 'no_images'
        p.billing_instance.settle.assert_not_called()
        p.release_spy.assert_awaited_once()
        released_reservation = p.release_spy.await_args[0][0]
        assert released_reservation['reservation_id'] == 'resv-1'

    @pytest.mark.parametrize('status_code', [401, 402])
    def test_upstream_401_402_bills_nothing_and_releases(self, client, status_code):
        with _BasePatches(row=_row(price=1000, markup_pct=0),
                           http_post=AsyncMock(return_value=_upstream_response(status_code=status_code))) as p:
            resp = client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': 'a cat'})
        assert resp.status_code == status_code
        p.billing_instance.settle.assert_not_called()
        p.release_spy.assert_awaited_once()

    def test_upstream_exception_bills_nothing_and_releases(self, client):
        async def _boom(*a, **k):
            raise TimeoutError('upstream took too long')

        with _BasePatches(row=_row(price=1000, markup_pct=0), http_post=_boom) as p:
            resp = client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': 'a cat'})
        assert resp.status_code == 502
        p.billing_instance.settle.assert_not_called()
        p.release_spy.assert_awaited_once()


# ── Markup percentage reaches the billed amount ────────────────────────────

class TestMarkupReachesBilledAmount:
    def test_markup_pct_applied_via_apply_markup(self, client):
        base_price = 1000
        pct = 25
        expected = apply_markup(base_price, pct)  # 1250 -- the single source of truth
        body = {'data': [{'url': 'https://example.com/a.png'}]}
        with _BasePatches(row=_row(price=base_price, markup_pct=None), markup_pct=pct,
                           http_post=AsyncMock(return_value=_upstream_response(body=body))) as p:
            resp = client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': 'a cat', 'n': 1})
        assert resp.status_code == 200, resp.text
        assert resp.json()['billing']['cost'] == expected
        args, _ = p.billing_instance.settle.await_args
        assert args[1] == Money(expected)


# ── Money invariant: integer Toman everywhere ──────────────────────────────

class TestIntegerTomanInvariant:
    def test_charged_amount_is_integer_toman(self, client):
        # A fractional-looking base + a fractional pct exercise apply_markup's
        # rounding; the result reaching Money() must still be a plain int
        # (Money itself raises TypeError on anything else).
        body = {'data': [{'url': 'https://example.com/a.png'}]}
        with _BasePatches(row=_row(price=333, markup_pct=None), markup_pct=7.5,
                           http_post=AsyncMock(return_value=_upstream_response(body=body))) as p:
            resp = client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': 'a cat', 'n': 1})
        assert resp.status_code == 200, resp.text
        cost = resp.json()['billing']['cost']
        assert isinstance(cost, int)
        args, _ = p.billing_instance.settle.await_args
        assert isinstance(args[1].toman, int)


# ── Auth ─────────────────────────────────────────────────────────────────

class TestAuth:
    def test_unauthenticated_rejected(self, client):
        with patch.object(images_mod, '_get_user_id', AsyncMock(return_value=None)):
            resp = client.post('/v1/images/generations', json={'model': 'pollinations/flux', 'prompt': 'a cat'})
        assert resp.status_code == 401
