"""
The public /models/health payload is a *published* document.

The endpoint is anonymous (verified 200 without a cookie or token on
production), so every field it emits is visible to any visitor. Before this
suite existed nothing covered the payload itself, and three product rules were
being broken at once on sanjabai.com/status:

  * 56 of 69 rows carried upstream route prefixes (kr/, cc/, cx/, ag/,
    bynara/, gemini-api/, openrouter/, freellmapi/) — ordinary users must
    never see the provider or the route.
  * 15 rows carried a 'free' label — we sell every model, including the ones
    supplied to us for free.
  * `overall` was computed over all 69 probed rows, 45 of which we do not
    sell, so the page announced 'degraded' while all 24 served models were
    healthy.

These tests pin the *contract*, not the current data: they drive the endpoint
with a catalog that deliberately mixes served and unserved rows.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

import model_health_api


# A catalog shaped like production: two served rows behind ugly route ids,
# plus rows that are parked, disabled, or have no public id. Only the first
# two may ever reach the wire.
SERVED = {
    'cc/claude-sonnet-5': {'publicId': 'sanjab/claude-sonnet-5', 'displayName': 'Claude Sonnet 5'},
    'gemini-api/models/gemini-3-flash': {'publicId': 'sanjab/gemini-3-flash', 'displayName': 'Gemini 3 Flash'},
}

def _s(status, err=None):
    return {
        'status': status, 'successRate': 1.0 if status == 'healthy' else 0.0,
        'latencyP50Ms': 800, 'latencyP95Ms': 900, 'sampleCount': 5,
        'lastOkAt': None, 'lastError': err, 'checkedAt': None,
    }


# The raw health table also holds the rows we do NOT serve.
STATES = {
    'cc/claude-sonnet-5': _s('healthy'),
    'gemini-api/models/gemini-3-flash': _s('healthy'),
    'kr/claude-sonnet-4': _s('down', err='http_402'),
    'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free': _s('down', err='http_429'),
    'bynara/mimo-v2.5-free': _s('degraded'),
    'freellmapi/agnes-1.5-flash': _s('down', err='http_404'),
}


async def _call(served, states):
    """Drive the endpoint with a given catalog + health table."""
    with patch.object(model_health_api, 'health_map', AsyncMock(return_value=states)), \
         patch.object(model_health_api, '_served_models', AsyncMock(return_value=served)), \
         patch.object(model_health_api, 'configured_providers', lambda: []), \
         patch.object(model_health_api.rds, 'get', AsyncMock(return_value=None)), \
         patch.object(model_health_api.rds, 'setex', AsyncMock()):
        res = await model_health_api.models_health(None)
    return json.loads(bytes(res.body))


class TestNoProviderLeak:
    """Rule: an ordinary user never sees the provider or the route."""

    @pytest.mark.asyncio
    async def test_only_served_models_are_published(self):
        body = await _call(SERVED, STATES)
        assert [m['id'] for m in body['models']] == [
            'sanjab/claude-sonnet-5', 'sanjab/gemini-3-flash',
        ]

    @pytest.mark.asyncio
    async def test_no_route_prefix_anywhere_in_the_payload(self):
        body = await _call(SERVED, STATES)
        wire = json.dumps(body)
        for prefix in ('kr/', 'cc/', 'cx/', 'ag/', 'bynara/', 'gemini-api/',
                       'openrouter/', 'freellmapi/', 'nvidia/'):
            assert prefix not in wire, f'route prefix {prefix!r} leaked to the public payload'

    @pytest.mark.asyncio
    async def test_no_free_label_reaches_the_wire(self):
        # "هیچ مدل رایگانی نداریم" — free supply is still sold.
        body = await _call(SERVED, STATES)
        assert 'free' not in json.dumps(body).lower()

    @pytest.mark.asyncio
    async def test_every_published_id_is_a_public_id(self):
        body = await _call(SERVED, STATES)
        assert all(m['id'].startswith('sanjab/') for m in body['models'])


class TestOverallReflectsWhatAUserCanPick:
    """Rule: `overall` is the worst thing a user would actually notice."""

    @pytest.mark.asyncio
    async def test_unserved_wreckage_does_not_make_the_site_degraded(self):
        # Four of six health rows are down/degraded, but none are sold.
        body = await _call(SERVED, STATES)
        assert body['overall'] == 'operational'
        assert body['counts'] == {'healthy': 2, 'degraded': 0, 'down': 0, 'unknown': 0}

    @pytest.mark.asyncio
    async def test_a_sick_served_model_still_degrades(self):
        states = dict(STATES)
        states['cc/claude-sonnet-5'] = _s('down', err='http_500')
        body = await _call(SERVED, states)
        assert body['overall'] == 'degraded'
        assert body['counts']['down'] == 1

    @pytest.mark.asyncio
    async def test_all_served_models_sick_is_down(self):
        states = {k: _s('down') for k in SERVED}
        body = await _call(SERVED, states)
        assert body['overall'] == 'down'


class TestDegradesHonestly:
    @pytest.mark.asyncio
    async def test_served_model_without_a_health_row_is_unknown_not_missing(self):
        # The page promises: if a model is missing here it is missing from the
        # catalog. A freshly deployed model must therefore still be listed.
        body = await _call(SERVED, {})
        assert [m['id'] for m in body['models']] == [
            'sanjab/claude-sonnet-5', 'sanjab/gemini-3-flash',
        ]
        assert {m['status'] for m in body['models']} == {'unknown'}

    @pytest.mark.asyncio
    async def test_unreadable_catalog_publishes_nothing_and_admits_it(self):
        # Must not fall back to dumping the raw health table, and must not
        # claim 'operational' off an empty list.
        body = await _call(None, STATES)
        assert body['models'] == []
        assert body['overall'] == 'degraded'
        assert 'kr/' not in json.dumps(body)


class TestNoGatewayNamesReachTheWire:
    """The same "never the provider" rule, applied to the field where it was
    missed for months.

    This payload used to carry `upstreams`: one entry per configured gateway,
    each with `name` verbatim -- litellm, omniroute, ninerouter -- plus its
    own latency. Verified live on production before this change:

        $ curl -s https://sanjabai.com/api/models/health   # no auth
        upstreams: [{'name': 'litellm', ...}, {'name': 'omniroute', ...},
                    {'name': 'ninerouter', ...}]

    Model ids on this same endpoint had already been rewritten to `sanjab/*`
    for exactly this reason; the gateway list simply was not looked at. The
    named breakdown still exists for admins, behind admin auth, in
    admin_monitoring._upstreams_section.
    """

    def _providers(self, *oks):
        """Fake configured_providers()/upstream_alive() for N gateways with
        the given ok flags. The names are deliberately the REAL ones -- a
        test that used placeholder names could not catch a leak of the real
        ones through a field it forgot to check."""
        from types import SimpleNamespace
        names = ['litellm', 'omniroute', 'ninerouter'][:len(oks)]
        provs = [SimpleNamespace(name=n) for n in names]
        by_name = dict(zip(names, oks))

        async def _alive(p, timeout=None):
            return SimpleNamespace(ok=by_name[p.name], latency_ms=120, error=None)

        return provs, _alive

    async def _call_with_gateways(self, *oks):
        provs, alive = self._providers(*oks)
        with patch.object(model_health_api, 'configured_providers', lambda: provs), \
             patch.object(model_health_api, 'upstream_alive', alive), \
             patch.object(model_health_api, 'health_map', AsyncMock(return_value=STATES)), \
             patch.object(model_health_api, '_served_models', AsyncMock(return_value=SERVED)), \
             patch.object(model_health_api.rds, 'get', AsyncMock(return_value=None)), \
             patch.object(model_health_api.rds, 'setex', AsyncMock()):
            res = await model_health_api.models_health(None)
        return json.loads(bytes(res.body))

    @pytest.mark.asyncio
    async def test_no_gateway_name_appears_anywhere_in_the_payload(self):
        raw = json.dumps(await self._call_with_gateways(True, True, True), ensure_ascii=False)
        for name in ('litellm', 'omniroute', 'ninerouter'):
            assert name not in raw, f'gateway name {name!r} leaked to an anonymous endpoint'

    @pytest.mark.asyncio
    async def test_the_named_upstreams_list_is_gone_entirely(self):
        body = await self._call_with_gateways(True, True, True)
        assert 'upstreams' not in body

    @pytest.mark.asyncio
    async def test_no_per_gateway_count_either(self):
        """How many routers we run is the same fact told more quietly, so
        the aggregate carries a status word and nothing countable."""
        body = await self._call_with_gateways(True, True, True)
        assert body['gateways'] == {'status': 'operational'}

    @pytest.mark.asyncio
    async def test_a_partial_outage_reads_as_degraded(self):
        body = await self._call_with_gateways(True, False, True)
        assert body['gateways']['status'] == 'degraded'

    @pytest.mark.asyncio
    async def test_every_gateway_down_reads_as_down(self):
        body = await self._call_with_gateways(False, False, False)
        assert body['gateways']['status'] == 'down'

    @pytest.mark.asyncio
    async def test_no_configured_gateway_is_unknown_not_operational(self):
        """An empty provider list must not read as "all healthy" -- that is
        the direction that hides an outage."""
        with patch.object(model_health_api, 'configured_providers', lambda: []), \
             patch.object(model_health_api, 'health_map', AsyncMock(return_value=STATES)), \
             patch.object(model_health_api, '_served_models', AsyncMock(return_value=SERVED)), \
             patch.object(model_health_api.rds, 'get', AsyncMock(return_value=None)), \
             patch.object(model_health_api.rds, 'setex', AsyncMock()):
            res = await model_health_api.models_health(None)
        assert json.loads(bytes(res.body))['gateways']['status'] == 'unknown'
