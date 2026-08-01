"""Regression tests for chat.py routing real completions through the
model's tagged upstream (providers.py / model_catalog.upstream), not just
observing 9Router in health checks. See providers.py's module docstring and
model_discovery.py for how `upstream` gets set on a catalog row.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

import chat as chat_mod
import providers


@pytest.fixture(autouse=True)
def _reset_upstream_cache():
    chat_mod._UPSTREAM_CACHE = {}
    yield
    chat_mod._UPSTREAM_CACHE = {}


class TestResolveProvider:
    @pytest.mark.asyncio
    async def test_unknown_upstream_falls_back_to_chat_provider(self):
        with patch.object(chat_mod, 'async_session', None):
            provider = await chat_mod._resolve_provider('tencent-hy3')
        assert provider.name == 'litellm'

    @pytest.mark.asyncio
    async def test_tagged_ninerouter_model_routes_there_when_configured(self):
        chat_mod._UPSTREAM_CACHE = {'some-model': 'ninerouter'}
        with patch.object(chat_mod, 'async_session', None), \
             patch.dict(os.environ, {'NINEROUTER_URL': 'http://9router:20128'}):
            provider = await chat_mod._resolve_provider('some-model')
        assert provider.name == 'ninerouter'
        assert provider.base_url == 'http://9router:20128'

    @pytest.mark.asyncio
    async def test_tagged_ninerouter_model_falls_back_when_not_configured(self):
        # A model was previously tagged 'ninerouter' but the upstream was
        # since disabled/unconfigured -- must not crash or route nowhere.
        chat_mod._UPSTREAM_CACHE = {'some-model': 'ninerouter'}
        env = {k: v for k, v in os.environ.items() if k not in ('NINEROUTER_URL', 'NINEROUTER_ENABLED')}
        with patch.object(chat_mod, 'async_session', None), \
             patch.dict(os.environ, env, clear=True):
            provider = await chat_mod._resolve_provider('some-model')
        assert provider.name == 'litellm'

    @pytest.mark.asyncio
    async def test_admin_curated_model_with_no_upstream_tag_uses_default(self):
        # The entire pre-9Router catalog has upstream=NULL -- confirms
        # enabling discovery never silently reroutes existing models.
        chat_mod._UPSTREAM_CACHE = {}
        with patch.object(chat_mod, 'async_session', None):
            provider = await chat_mod._resolve_provider('mistral-large')
        assert provider.name == 'litellm'


class TestConfiguredProviders:
    def test_ninerouter_absent_by_default(self):
        env = {k: v for k, v in os.environ.items() if k not in ('NINEROUTER_URL', 'NINEROUTER_ENABLED')}
        with patch.dict(os.environ, env, clear=True):
            names = [p.name for p in providers.configured_providers()]
        assert names == ['litellm']

    def test_ninerouter_present_when_url_set(self):
        with patch.dict(os.environ, {'NINEROUTER_URL': 'http://9router:20128'}):
            names = [p.name for p in providers.configured_providers()]
        assert 'ninerouter' in names
