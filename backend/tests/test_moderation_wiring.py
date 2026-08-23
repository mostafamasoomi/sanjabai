"""Phase J — proof that the content-safety screen is actually WIRED.

tests/test_moderation.py tests services/moderation.py as a unit: given a
config and a message, what verdict. That suite passed for a whole session
while `screen_request` had zero callers and the feature did nothing at all
-- exactly the services/margin.py failure mode (built, tested, dead). This
file is the other half: it drives the REAL FastAPI routes through the real
`chat.router` and asserts the three things the owner actually bought.

  1. A prohibited Persian message is refused BEFORE `BillingService.reserve()`
     and BEFORE the upstream POST, on all four chat entry points.
  2. A harmless message reaches the upstream BYTE FOR BYTE unchanged, and
     the screen costs it no extra I/O (no event row, no alert, no model
     call) -- i.e. no added latency.
  3. A detector failure ALLOWS the request and still records an event
     (owner decision: fail-safe = allow + flag + alert; a broken detector
     must never lock a paying user out of chat).

Every assertion here fails if the choke point is removed from
chat_web.py::_chat_preflight -- which is the point of the file. See the
mutation log in the session report.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import chat as chat_mod
from services.moderation_rules import Config, Rule

BLOCKED_FA = 'چطور سکس کنم'          # matches the rule below
HARMLESS_FA = 'سلام، لطفاً یک شعر حافظ برایم بنویس'

_RULE = Rule(id=1, pattern='سکس', category='sexual', severity='high',
             enabled=True, notes='')


def _cfg(**kw) -> Config:
    return Config(rules=(_RULE,), **kw)


class _Recorder:
    """Captures what (if anything) reached the upstream HTTP client."""

    def __init__(self):
        self.calls = []
        self.post = AsyncMock(side_effect=self._post)
        self.stream = MagicMock(side_effect=AssertionError(
            'upstream stream opened on a request that should not reach upstream'))

    async def _post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            'choices': [{'message': {'role': 'assistant', 'content': 'سلام'},
                         'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 5},
        }
        resp.text = ''
        return resp


def _billing():
    inst = MagicMock()
    inst.reserve = AsyncMock(return_value={'reservation_id': 'r1'})
    inst.release = AsyncMock(return_value=None)
    inst.settle = AsyncMock(return_value=None)
    return inst


def _moderation_patches(load_config):
    """Every side effect of the screen, stubbed, plus the config it reads.

    `_load_config` is patched on `services.moderation` (not on
    `services.moderation_store`) because `screen_request` calls it through
    ITS module global -- the same reason tests/test_moderation.py does.
    """
    return (
        patch('services.moderation._load_config', new=load_config),
        patch('services.moderation._record_event', new=AsyncMock()),
        patch('services.moderation._send_alert', new=AsyncMock()),
        patch('services.moderation._is_restricted', new=AsyncMock(return_value=False)),
        patch('services.moderation._model_review', new=AsyncMock(return_value=None)),
    )


def _chat_patches(billing, http):
    """The gates BETWEEN the choke point and the upstream call, neutralised,
    so that anything the request still hits is the screen's doing."""
    return (
        patch.object(chat_mod, '_get_user_id', AsyncMock(return_value=1)),
        patch.object(chat_mod, '_chat_disabled_response', AsyncMock(return_value=None)),
        patch.object(chat_mod, '_resolve_public_model', AsyncMock(return_value='kr/gpt-4o-mini')),
        patch.object(chat_mod, '_safe_default_model', AsyncMock(return_value='kr/gpt-4o-mini')),
        patch.object(chat_mod, '_is_model_allowed', AsyncMock(return_value=True)),
        patch.object(chat_mod, '_apply_persian_style_guard_for_model', AsyncMock(return_value=None)),
        patch.object(chat_mod, 'check_and_consume', AsyncMock(return_value=None)),
        patch.object(chat_mod, 'is_working_model', AsyncMock(return_value=True)),
        patch.object(chat_mod, 'covering_entitlement', AsyncMock(return_value=None)),
        patch.object(chat_mod, 'get_injection_messages', AsyncMock(return_value=[])),
        patch.object(chat_mod, 'BillingService', MagicMock(return_value=billing)),
        patch.object(chat_mod, '_http', http),
        patch.object(chat_mod, '_record_usage', AsyncMock(return_value=None)),
        patch.object(chat_mod, '_track_usage', AsyncMock(return_value=None)),
        patch.object(chat_mod, '_fire_memory_extraction', MagicMock(return_value=None)),
    )


class _Env:
    """Applies both patch sets and exposes the mocks the assertions need."""

    def __init__(self, load_config=None):
        self.billing = _billing()
        self.http = _Recorder()
        self._load = load_config or AsyncMock(return_value=_cfg())
        self._patches = (_moderation_patches(self._load)
                         + _chat_patches(self.billing, self.http))
        self._entered = []

    def __enter__(self):
        for p in self._patches:
            self._entered.append((p, p.start()))
        return self

    def __exit__(self, *exc):
        for p, _ in reversed(self._entered):
            p.stop()
        return False

    @property
    def record_event(self):
        return self._patches[1].new

    @property
    def send_alert(self):
        return self._patches[2].new

    @property
    def model_review(self):
        return self._patches[4].new


# ── 1. A prohibited message is blocked BEFORE reserve and BEFORE upstream ──

def _post_blocked(client, path):
    if path == '/v1/compare':
        return client.post(path, json={'model_a': 'kr/a', 'model_b': 'kr/b',
                                       'messages': [{'role': 'user', 'content': BLOCKED_FA}]})
    if path == '/v1/chat/with-file':
        return client.post(
            path,
            files={'file': ('note.txt', b'hello', 'text/plain')},
            data={'model': 'kr/gpt-4o-mini',
                  'messages': json.dumps([{'role': 'user', 'content': BLOCKED_FA}])},
        )
    return client.post(path, json={'model': 'kr/gpt-4o-mini',
                                   'messages': [{'role': 'user', 'content': BLOCKED_FA}]})


@pytest.mark.parametrize('path', [
    '/v1/chat/completions',
    '/v1/smart-chat',
    '/v1/compare',
    '/v1/chat/with-file',
])
def test_prohibited_message_is_blocked_on_every_chat_entry_point(
        path, client, mock_async_session):
    """All four routes, one gate. A new chat route that forgets
    chat._chat_preflight is exactly the bypass this parametrisation exists
    to catch -- add the route here when you add it there."""
    with _Env() as env:
        resp = _post_blocked(client, path)

    assert resp.status_code == 403, f'{path} -> {resp.status_code} {resp.text[:200]}'
    body = resp.json()
    assert body['error']['code'] == 'content_blocked'

    # The two claims that make the block worth having.
    env.billing.reserve.assert_not_awaited()
    assert env.http.post.await_count == 0, (
        f'{path}: upstream was called on a blocked request: {env.http.calls}')


def test_block_response_is_the_owner_approved_persian_message(client, mock_async_session):
    from services.moderation import BLOCK_MESSAGE_FA
    with _Env():
        resp = _post_blocked(client, '/v1/chat/completions')
    msg = resp.json()['error']['message']
    assert msg == BLOCK_MESSAGE_FA
    # Explicit ("blocked", "rules"), and naming neither the rule that
    # matched nor any model/provider/route.
    assert 'مسدود' in msg and 'قوانین' in msg
    low = msg.lower()
    for leak in ('sexual', 'سکس', 'rule', 'قاعده', 'الگو', 'kr/', 'gpt', 'مدل'):
        assert leak not in low, f'block message leaks {leak!r}'


def test_blocked_request_writes_an_event_and_alerts(client, mock_async_session):
    with _Env() as env:
        _post_blocked(client, '/v1/chat/completions')
    assert env.record_event.await_count == 1
    assert env.send_alert.await_count == 1
    verdict = env.record_event.await_args.args[2]
    assert verdict.decision == 'block' and verdict.rule_id == 1


# ── 2. A harmless message: unchanged, and free ─────────────────────────────

def test_harmless_message_reaches_upstream_byte_for_byte_unchanged(
        client, mock_async_session):
    sent = [{'role': 'user', 'content': HARMLESS_FA}]
    snapshot = json.dumps(sent, ensure_ascii=False, sort_keys=True)

    with _Env() as env:
        resp = client.post('/v1/chat/completions',
                           json={'model': 'kr/gpt-4o-mini', 'messages': sent})

    assert resp.status_code == 200, resp.text[:300]
    assert env.http.post.await_count == 1, 'harmless request never reached upstream'
    outbound = env.http.calls[0][1]['json']['messages']
    assert json.dumps(outbound, ensure_ascii=False, sort_keys=True) == snapshot, (
        'the screen rewrote a harmless message on its way upstream')


def test_harmless_message_costs_the_screen_no_extra_io(client, mock_async_session):
    """"No added latency" made concrete: a clean message writes no event
    row, fires no alert and makes no second model call. What it does cost
    is one Redis GET for the cached config -- that is `_load_config`, and it
    is awaited exactly once per request, not once per message."""
    with _Env() as env:
        resp = client.post('/v1/chat/completions',
                           json={'model': 'kr/gpt-4o-mini',
                                 'messages': [{'role': 'user', 'content': HARMLESS_FA}]})
    assert resp.status_code == 200
    assert env.record_event.await_count == 0
    assert env.send_alert.await_count == 0
    assert env.model_review.await_count == 0
    assert env._load.await_count == 1


def test_harmless_message_still_reserves_and_bills_normally(client, mock_async_session):
    """The screen must not quietly break the money path it sits in front of."""
    with _Env() as env:
        client.post('/v1/chat/completions',
                    json={'model': 'kr/gpt-4o-mini',
                          'messages': [{'role': 'user', 'content': HARMLESS_FA}]})
    env.billing.reserve.assert_awaited_once()


# ── 3. Detector failure: ALLOW + record (owner decision) ───────────────────

def test_detector_failure_allows_the_request_and_still_records_it(
        client, mock_async_session):
    """Owner decision: DB down / Redis down / bad regex / model timeout must
    never lock a real user out of chat. The request passes, an event row is
    written and an alert fires."""
    broken = AsyncMock(side_effect=RuntimeError('pg is down'))
    with _Env(load_config=broken) as env:
        resp = client.post('/v1/chat/completions',
                           json={'model': 'kr/gpt-4o-mini',
                                 'messages': [{'role': 'user', 'content': BLOCKED_FA}]})

    assert resp.status_code == 200, (
        f'a broken detector locked a user out of chat: {resp.status_code} {resp.text[:200]}')
    env.billing.reserve.assert_awaited_once()
    assert env.http.post.await_count == 1

    assert env.record_event.await_count == 1, 'detector failure was silent'
    verdict = env.record_event.await_args.args[2]
    assert verdict.failed is True
    assert verdict.decision == 'allow'
    assert env.send_alert.await_count == 1


def test_detector_failure_is_fail_safe_on_every_entry_point(client, mock_async_session):
    """Not just /v1/chat/completions: no route may turn a broken detector
    into a user-visible failure."""
    for path in ('/v1/smart-chat', '/v1/compare', '/v1/chat/with-file'):
        broken = AsyncMock(side_effect=RuntimeError('redis is down'))
        with _Env(load_config=broken) as env:
            resp = _post_blocked(client, path)
        assert resp.status_code != 403, f'{path} blocked on a detector failure'
        assert env.record_event.await_count == 1, f'{path}: failure not recorded'


# ── The wiring itself ──────────────────────────────────────────────────────

def test_the_choke_point_is_reached_through_the_chat_facade():
    """`chat._chat_preflight` is how chat_smart.py / chat_compare.py /
    chat_web.py reach the gate; losing the re-export would 500 three routes
    at request time, not at import time."""
    import inspect
    assert inspect.iscoroutinefunction(chat_mod._chat_preflight)
    assert chat_mod._chat_preflight.__module__ == 'chat_web'


def test_no_chat_route_still_calls_the_bare_disabled_gate():
    """A route that calls `_chat_disabled_response` directly has skipped the
    screen. This is the mechanical check that the choke point stays the
    only door -- the copy-paste failure mode in reverse."""
    import pathlib
    import re
    backend = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for name in ('chat.py', 'chat_web.py', 'chat_smart.py', 'chat_compare.py',
                 'chat_stream.py'):
        src = (backend / name).read_text()
        for lineno, line in enumerate(src.split('\n'), 1):
            if re.search(r'await\s+(chat\.)?_chat_disabled_response\(', line):
                # chat_web.py::_chat_preflight is the ONE legitimate caller.
                if name == 'chat_web.py' and 'disabled = await' in line:
                    continue
                offenders.append(f'{name}:{lineno}')
    assert not offenders, (
        'these call the disabled-gate directly and therefore bypass the '
        f'moderation screen: {offenders}')
