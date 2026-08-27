"""Guard test for the chat.py -> chat_models/chat_web/chat_billing/
chat_stream/chat_compare/chat_smart split.

chat.py used to be one ~2,500-line file; it is now a router plus a
namespace facade re-exporting names physically defined in the sibling
chat_*.py modules. Two very different things can go wrong when a module
like this gets split and this test is the cheap, mechanical check for the
first one:

  1. A name silently stops being an attribute of the `chat` module (e.g. a
     rename, or someone "cleans up" what looks like a dead re-export).
     Every production cross-import (`images.py`, `tasks.py`, `admin.py`,
     `security.py`, `app.py`) and every test that does
     `import chat as chat_mod` then `chat_mod.<name>` (monkeypatch or
     direct read) depends on that attribute existing on THIS module,
     regardless of which file actually defines it now.

  2. A moved function stops honouring monkeypatches on `chat.<name>`
     because it now calls another chat-owned name via a same-module bare
     reference or a `from chat import X`, rather than late-bound through
     `chat.<name>`. This test does NOT catch that class of bug (it only
     checks presence/callability of the facade surface) -- the existing
     billing/routing/web-search test suites (test_stream_billing_neutrality,
     test_provider_routing, test_billing_loss_paths, test_web_search,
     test_with_file_web_search, test_public_model_ids, ...) already cover
     that behaviourally, and continue to since the split didn't change what
     they exercise.
"""
from __future__ import annotations

import inspect

import chat as chat_mod


# Every name that must remain an attribute of the `chat` module after the
# split -- either because production code imports it from `chat` directly
# (see the file:name comments) or because a test monkeypatches / reads it
# via `chat_mod.<name>`.
_REQUIRED_CALLABLES = [
    # app.py wires the router itself.
    'router',
    # chat.py's own endpoint + the ones re-exported from chat_compare.py /
    # chat_smart.py.
    'chat',
    'compare_models',
    'smart_chat',
    # chat_models.py -- model resolution/availability.
    # images.py: _resolve_public_model, _resolve_provider
    # tasks.py: _resolve_public_model
    # admin.py: _resolve_provider
    '_get_model_upstream',
    '_resolve_public_model',
    '_safe_default_model',
    '_resolve_provider',
    'get_working_models',
    'is_working_model',
    '_is_model_allowed',
    # chat_web.py -- file/web-search + /v1/chat/with-file.
    '_apply_web_search',
    '_web_search',
    # images.py: _release_reservation
    '_release_reservation',
    # chat_compare.py.
    '_check_quota_pre',
    # chat_billing.py -- usage estimation / billing.
    '_estimate_tokens_from_chars',
    '_estimate_message_text_chars',
    '_estimate_input_tokens',
    '_estimate_output_tokens',
    '_extract_reasoning_tokens',
    '_usage_idempotency_key',
    '_extract_response_text',
    '_record_usage',
    '_track_usage',
    '_bill_stream_usage',
    # chat_stream.py -- SSE loops.
    '_chat_stream',
    '_smart_chat_stream',
    # chat.py's own shared helpers.
    '_persian_duration',
    '_free_tier_response',
    '_as_naive_utc',
    '_apply_persian_style_guard',
    '_apply_persian_style_guard_for_model',
    '_fire_memory_extraction',
    '_record_model_health',
    # `_get_user_plan` used to be re-exported here for security.py's lazy
    # `from chat import _get_user_plan`. Migration 0049 retired plans and
    # subscriptions; security.py now asks
    # services.user_quota.has_active_package directly, so there is nothing
    # left for chat.py to forward.
    # Re-exported third-party names some tests patch on `chat` directly
    # rather than on the service module that originally defines them.
    'async_session',
    '_get_user_id',
    'BillingService',
    'check_and_consume',
    'get_injection_messages',
]

# Non-callable attributes (classes, constants, mutable cache state) that
# must also remain on the `chat` module.
_REQUIRED_ATTRS = [
    'ChatRequest',
    'CompareRequest',
    # `_HARDCODED_WORKING` / `WORKING_MODELS` were DELETED (not moved) --
    # the fallback set they held was unservable garbage that could route a
    # withdrawn model to a user during a DB blip. See chat_models.py's
    # get_working_models() for the fail-closed replacement. Do not re-add
    # these names here; their absence from the facade is the fix.
    '_PERSIAN_STYLE_SYSTEM_MESSAGE',
    'FALLBACK_PRICE_PER_MILLION_IN',
    'FALLBACK_PRICE_PER_MILLION_OUT',
    'ESTIMATE_CHARS_PER_TOKEN',
    # database.py's lazy HTTP client proxy (not callable itself -- it
    # delegates .post()/.stream()/etc via __getattr__).
    '_http',
    # Mutable cache state tests reset directly via `chat_mod.X = ...`
    # (test_provider_routing.py, test_public_model_ids.py) -- see
    # chat_models.py's module docstring for why these live on `chat`.
    '_WORKING_SET_CACHE',
    '_UPSTREAM_CACHE',
    '_UPSTREAM_CACHE_LOADED_AT',
    '_MODEL_RESOLVE_CACHE',
    '_MODEL_RESOLVE_CACHE_LOADED_AT',
]


def test_all_required_callables_present_and_callable():
    missing = [name for name in _REQUIRED_CALLABLES if not hasattr(chat_mod, name)]
    assert not missing, f"chat module lost these facade names: {missing}"
    not_callable = [
        name for name in _REQUIRED_CALLABLES
        if hasattr(chat_mod, name) and not callable(getattr(chat_mod, name))
    ]
    assert not not_callable, f"chat.{not_callable} should be callable but isn't"


def test_all_required_attrs_present():
    missing = [name for name in _REQUIRED_ATTRS if not hasattr(chat_mod, name)]
    assert not missing, f"chat module lost these facade attributes: {missing}"


def test_router_has_all_four_routes():
    """/v1/chat/completions, /v1/chat/with-file, /v1/compare, /v1/smart-chat
    must all still be registered on the single shared `chat.router` --
    chat_web.py / chat_compare.py / chat_smart.py each register their route
    on `chat.router` via the `@chat.router.post(...)` decorator at their own
    import time, so a broken import chain (e.g. a module failing to import)
    would silently drop a route without failing anything else."""
    paths = {route.path for route in chat_mod.router.routes}
    for expected in (
        '/v1/chat/completions',
        '/v1/chat/with-file',
        '/v1/compare',
        '/v1/smart-chat',
    ):
        assert expected in paths, f"{expected} missing from chat.router (got {sorted(paths)})"


def test_streaming_and_billing_functions_are_coroutine_functions():
    """Cheap sanity check that these weren't accidentally left as sync stubs
    or otherwise mangled during the move (all are `async def` originally)."""
    for name in (
        '_resolve_public_model', '_safe_default_model', '_resolve_provider',
        'get_working_models', 'is_working_model', '_is_model_allowed',
        '_apply_web_search', '_web_search', '_release_reservation',
        '_check_quota_pre', '_track_usage', '_bill_stream_usage',
        '_record_usage', '_chat_stream', '_smart_chat_stream',
        'chat', 'compare_models', 'smart_chat',
    ):
        fn = getattr(chat_mod, name)
        assert inspect.iscoroutinefunction(fn), f"chat.{name} should be an async def"


def test_moved_functions_physically_live_in_the_expected_submodule():
    """Pin down WHERE each name is actually defined (not just that `chat`
    can still see it), so a future accidental duplicate definition (e.g.
    someone pastes a copy back into chat.py instead of importing it) is
    caught even though the facade attribute would still resolve fine."""
    expected_module = {
        '_get_model_upstream': 'chat_models',
        '_resolve_public_model': 'chat_models',
        '_safe_default_model': 'chat_models',
        '_resolve_provider': 'chat_models',
        'get_working_models': 'chat_models',
        'is_working_model': 'chat_models',
        '_is_model_allowed': 'chat_models',
        # Moved chat_web -> chat_search on 2026-08-23. chat_web.py crossed the
        # house 500-line cap when the DuckDuckGo Instant Answer parser was
        # hardened against non-dict JSON, and the cap is fixed by splitting
        # files, never by compressing code. chat_web.py re-exports both names
        # so chat.py's `from chat_web import ...` is unchanged -- which is
        # exactly why this test matters- the facade would still resolve even
        # if the split had gone wrong, so the DEFINITION site is pinned here.
        '_apply_web_search': 'chat_search',
        '_web_search': 'chat_search',
        '_release_reservation': 'chat_web',
        '_check_quota_pre': 'chat_compare',
        '_record_usage': 'chat_billing',
        '_track_usage': 'chat_billing',
        '_bill_stream_usage': 'chat_billing',
        '_chat_stream': 'chat_stream',
        '_smart_chat_stream': 'chat_stream',
        'compare_models': 'chat_compare',
        'smart_chat': 'chat_smart',
    }
    wrong_home = {}
    for name, expected_mod in expected_module.items():
        fn = getattr(chat_mod, name)
        actual_mod = fn.__module__
        if actual_mod != expected_mod:
            wrong_home[name] = actual_mod
    assert not wrong_home, f"names defined in the wrong module: {wrong_home}"


def test_chat_endpoint_still_lives_in_chat_py():
    assert chat_mod.chat.__module__ == 'chat'
