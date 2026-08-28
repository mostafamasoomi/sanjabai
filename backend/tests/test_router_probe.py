"""Tests for services/router_probe.py -- the acceptance probe for "being
the router" (see that module's docstring for the full design: two stages,
three outcomes, why the worst failure mode of a broken probe is the
pre-feature status quo).

Stubs the HTTP layer entirely (`router_probe._http`, `router_probe
.get_provider`) -- never hits a live router. Follows test_smart_router_llm
.py's style: small fake doubles, no live Postgres/Redis.
"""
from __future__ import annotations

import ast
import json
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

import chat_smart
import chat_smart_mode
import services.router_probe as rp
import services.smart_router_llm as llm
from services.smart_router import Candidate


# ── doubles ──────────────────────────────────────────────────────────────

def _cand(name: str, blended: int, upstream: str = 'ninerouter') -> Candidate:
    return Candidate(
        provider_model_id=f'up/{name}',
        public_id=f'sanjab/{name}',
        input_per_million=blended // 4,
        output_per_million=blended - 3 * (blended // 4),
        context_window=100_000,
        upstream=upstream,
        blended=blended,
    )


# Three members, evenly priced so band_thresholds/band_of splits them
# cleanly into band 1 / band 2 / band 3 in menu order -- see the band-math
# comment on the discrimination tests below.
_POOL = [_cand('cheap', 10_000), _cand('mid', 20_000), _cand('expensive', 30_000)]
_THREE_BAND_THRESHOLDS = (10_000, 20_000)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fake_provider():
    return SimpleNamespace(v1='http://upstream/v1', headers=lambda: {'Authorization': 'Bearer k'})


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _reply(content):
    return _FakeResponse({'choices': [{'message': {'role': 'assistant', 'content': content}}]})


class _FakeHttp:
    """Consumes one canned response per `.post()` call, in order."""

    def __init__(self, responses=None, raises=None):
        self.responses = list(responses or [])
        self.raises = raises
        self.calls: list[dict] = []

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({'url': url, 'json': json})
        if self.raises is not None:
            raise self.raises
        return self.responses.pop(0)


class _FakeProbeSession:
    """Answers both statements `run_probe_scan` issues: the app_setting
    SELECT (`_load_stored`) and the app_setting upsert (`_persist`)."""

    def __init__(self, stored=None):
        self.stored = stored
        self.written = None
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        text = str(stmt)
        if 'SELECT value' in text:
            row = None if self.stored is None else SimpleNamespace(value=self.stored)
            return SimpleNamespace(fetchone=lambda: row)
        if 'INSERT INTO app_setting' in text:
            self.written = json.loads(params['v'])
            return SimpleNamespace()
        raise AssertionError(f'unexpected statement in _FakeProbeSession: {text}')

    async def commit(self):
        self.commits += 1


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session


class _FakeLLMSession:
    """Answers the two app_setting lookups `smart_router_llm._router_model`
    makes since the fail-closed change: `smart_router_model` (its own
    query) and `smart_router_probe` (via `router_probe.router_eligibility`
    reusing the same session)."""

    def __init__(self, router_model, probe_results, probe_measured_at):
        self.router_model = router_model
        self.probe_results = probe_results
        self.probe_measured_at = probe_measured_at

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        key = (params or {}).get('key')
        if key == rp.SETTING_KEY:
            value = {'version': 1, 'measured_at': self.probe_measured_at, 'results': self.probe_results}
            row = SimpleNamespace(value=value)
            return SimpleNamespace(fetchone=lambda: row)
        row = None if self.router_model is None else SimpleNamespace(value=self.router_model)
        return SimpleNamespace(fetchone=lambda: row)


# ── stage 1: shape ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_reply_that_fails_parse_choice_is_a_permanent_shape_failure(monkeypatch):
    monkeypatch.setattr(rp, 'get_provider', lambda upstream: _fake_provider())
    http = _FakeHttp(responses=[_reply('not a number')])
    monkeypatch.setattr(rp, '_http', http)

    result = await rp._probe_one(
        _POOL[0], rp._synthetic_shape_menu(), _POOL, _THREE_BAND_THRESHOLDS, None, _now_iso(),
    )

    assert result['ok'] is False
    assert result['shape_ok'] is False
    assert result['reason'] == 'bad_shape'
    assert len(http.calls) == 1, 'a shape failure must stop before stage 2 -- no discrimination calls'


# ── stage 2: discrimination ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_reply_that_parses_but_answers_band_three_to_the_greeting_fails_discrimination(monkeypatch):
    """_POOL is 3 members spread so band_of/band_thresholds gives menu
    position 1 -> band 1, position 2 -> band 2, position 3 -> band 3 (see
    _THREE_BAND_THRESHOLDS). Shape passes ('1'), then greeting answers menu
    position 3 (band 3) -- discrimination must fail even though the reply
    was perfectly well-formed."""
    monkeypatch.setattr(rp, 'get_provider', lambda upstream: _fake_provider())
    http = _FakeHttp(responses=[_reply('1'), _reply('3'), _reply('2'), _reply('1')])
    monkeypatch.setattr(rp, '_http', http)

    result = await rp._probe_one(
        _POOL[0], rp._synthetic_shape_menu(), _POOL, _THREE_BAND_THRESHOLDS, None, _now_iso(),
    )

    assert result['ok'] is False
    assert result['shape_ok'] is True
    assert result['discriminates'] is False
    assert result['reason'] == 'no_discrimination'
    assert result['samples']['greeting'] == 3


@pytest.mark.asyncio
async def test_a_correctly_discriminating_reply_is_recorded_ok(monkeypatch):
    """Sanity check for the pass path: greeting -> band 1, reasoning ->
    band 3 (>= 2). Code's band is not checked by the acceptance bar --
    deliberately loose, see module docstring."""
    monkeypatch.setattr(rp, 'get_provider', lambda upstream: _fake_provider())
    http = _FakeHttp(responses=[_reply('1'), _reply('1'), _reply('2'), _reply('3')])
    monkeypatch.setattr(rp, '_http', http)

    result = await rp._probe_one(
        _POOL[0], rp._synthetic_shape_menu(), _POOL, _THREE_BAND_THRESHOLDS, None, _now_iso(),
    )

    assert result['ok'] is True
    assert result['discriminates'] is True
    assert result['samples'] == {'greeting': 1, 'code': 2, 'reasoning': 3}


# ── the three outcomes: transient never erases a prior ok=true ──────────

@pytest.mark.asyncio
async def test_http_429_is_transient_and_does_not_erase_a_prior_ok_true(monkeypatch):
    monkeypatch.setattr(rp, 'get_provider', lambda upstream: _fake_provider())
    http = _FakeHttp(responses=[_FakeResponse({'error': 'rate limited'}, status_code=429)])
    monkeypatch.setattr(rp, '_http', http)
    prev = {
        'ok': True, 'shape_ok': True, 'discriminates': True, 'at': 'old',
        'samples': {'greeting': 1, 'code': 2, 'reasoning': 3},
    }

    result = await rp._probe_one(
        _POOL[0], rp._synthetic_shape_menu(), _POOL, _THREE_BAND_THRESHOLDS, prev, _now_iso(),
    )

    assert result['ok'] is True, 'a 429 must not erase a previous ok=true'
    assert result['reason'] == 'transient_http_429'
    assert 'retry_after' in result
    assert result['samples'] == prev['samples'], 'the old evidence is preserved, not discarded'


@pytest.mark.asyncio
async def test_http_5xx_is_transient(monkeypatch):
    monkeypatch.setattr(rp, 'get_provider', lambda upstream: _fake_provider())
    http = _FakeHttp(responses=[_FakeResponse({'error': 'boom'}, status_code=503)])
    monkeypatch.setattr(rp, '_http', http)

    result = await rp._probe_one(
        _POOL[0], rp._synthetic_shape_menu(), _POOL, _THREE_BAND_THRESHOLDS, None, _now_iso(),
    )

    assert result['ok'] is False, 'no prior good result to preserve, so ok stays false'
    assert result['reason'] == 'transient_http_503'
    assert 'retry_after' in result


@pytest.mark.asyncio
async def test_call_classifies_httpx_timeout_exception_as_transient(monkeypatch):
    """httpx.TimeoutException does NOT subclass the builtin TimeoutError --
    both must be caught (see module docstring)."""
    monkeypatch.setattr(rp, '_http', _FakeHttp(raises=httpx.ReadTimeout('slow')))
    reply, transient = await rp._call(_fake_provider(), 'up/cheap', 'prompt')
    assert reply is None
    assert transient == 'transient_timeout'


@pytest.mark.asyncio
async def test_call_classifies_builtin_timeout_error_as_transient(monkeypatch):
    monkeypatch.setattr(rp, '_http', _FakeHttp(raises=TimeoutError('slow')))
    reply, transient = await rp._call(_fake_provider(), 'up/cheap', 'prompt')
    assert reply is None
    assert transient == 'transient_timeout'


@pytest.mark.asyncio
async def test_call_classifies_a_transport_exception_as_transient(monkeypatch):
    monkeypatch.setattr(rp, '_http', _FakeHttp(raises=RuntimeError('connection reset')))
    reply, transient = await rp._call(_fake_provider(), 'up/cheap', 'prompt')
    assert reply is None
    assert transient == 'transient_exception'


# ── the third outcome: left the catalog ──────────────────────────────────

@pytest.mark.asyncio
async def test_a_model_no_longer_in_the_pool_has_its_row_removed(monkeypatch):
    pool = [_POOL[0], _POOL[1]]

    async def _pool():
        return pool

    monkeypatch.setattr(rp, 'candidate_pool', _pool)
    stored = {
        'version': 1, 'measured_at': 'old',
        'results': {
            'sanjab/withdrawn': {'ok': True, 'at': 'old'},
            _POOL[0].public_id: {'ok': True, 'at': 'old', 'samples': {}},
        },
    }
    session = _FakeProbeSession(stored=stored)
    monkeypatch.setattr(rp, 'async_session', _SessionFactory(session))
    monkeypatch.setattr(rp, 'get_provider', lambda upstream: _fake_provider())
    # Shape stage fails immediately for both scanned models -- one call
    # each, contents irrelevant to this test.
    monkeypatch.setattr(rp, '_http', _FakeHttp(responses=[_reply('nope'), _reply('nope')]))

    value = await rp.run_probe_scan()

    assert 'sanjab/withdrawn' not in value['results'], 'a model gone from the pool must be dropped'
    assert 'sanjab/withdrawn' not in session.written['results']
    assert _POOL[0].public_id in value['results']
    assert _POOL[1].public_id in value['results']


# ── _router_model consulting the stored result ──────────────────────────

@pytest.mark.asyncio
async def test_router_model_refuses_a_permanently_failed_probe_result(monkeypatch):
    session = _FakeLLMSession(
        router_model=_POOL[0].public_id,
        probe_results={_POOL[0].public_id: {'ok': False, 'reason': 'bad_shape'}},
        probe_measured_at=_now_iso(),
    )
    monkeypatch.setattr(llm, 'async_session', lambda: session)

    picked = await llm._router_model([_POOL[0]])

    assert picked is None


@pytest.mark.asyncio
async def test_router_model_accepts_a_stale_probe_result_and_warns(monkeypatch, caplog):
    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    session = _FakeLLMSession(
        router_model=_POOL[0].public_id,
        probe_results={_POOL[0].public_id: {'ok': True}},
        probe_measured_at=old,
    )
    monkeypatch.setattr(llm, 'async_session', lambda: session)

    with caplog.at_level('WARNING'):
        picked = await llm._router_model([_POOL[0]])

    assert picked is not None
    assert picked.public_id == _POOL[0].public_id
    assert any('older than 7 days' in r.message for r in caplog.records), (
        'a stale-but-ok probe result must be accepted with a loud warning, not silently'
    )


@pytest.mark.asyncio
async def test_router_model_refuses_when_the_probe_has_no_result_at_all(monkeypatch):
    session = _FakeLLMSession(
        router_model=_POOL[0].public_id,
        probe_results={},
        probe_measured_at=None,
    )
    monkeypatch.setattr(llm, 'async_session', lambda: session)

    picked = await llm._router_model([_POOL[0]])

    assert picked is None


# ── scan scope ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_scan_covers_at_most_twelve_models(monkeypatch):
    pool = [_cand(f'z{i}', 10_000 * (i + 1)) for i in range(20)]

    async def _pool():
        return pool

    monkeypatch.setattr(rp, 'candidate_pool', _pool)
    monkeypatch.setattr(rp, 'async_session', _SessionFactory(_FakeProbeSession(stored=None)))
    monkeypatch.setattr(rp, 'get_provider', lambda upstream: _fake_provider())
    # One shape-failing reply per model -- exactly SCAN_LIMIT calls if the
    # scan is correctly capped, an IndexError (queue exhausted) if it is not.
    http = _FakeHttp(responses=[_reply('nope') for _ in range(rp.SCAN_LIMIT)])
    monkeypatch.setattr(rp, '_http', http)

    value = await rp.run_probe_scan()

    assert len(value['results']) == rp.SCAN_LIMIT == 12
    assert len(http.calls) == rp.SCAN_LIMIT
    called_models = {c['json']['model'] for c in http.calls}
    assert called_models == {c.provider_model_id for c in pool[:12]}


# ── nothing in the chat path calls the probe ─────────────────────────────

def _referenced_names(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            names.update(a.name.split('.')[-1] for a in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def test_nothing_on_the_chat_path_references_run_probe_scan():
    """`run_probe_scan` is the only function in services/router_probe.py
    that makes a live upstream call or opens a write transaction. It must
    be reachable from exactly one place: admin_smart_router.py's POST
    handler, run by an admin -- NEVER from the hot chat path. AST-walked,
    not grepped for a comment nobody enforces."""
    chat_path_files = [
        pathlib.Path(llm.__file__),
        pathlib.Path(chat_smart.__file__),
        pathlib.Path(chat_smart_mode.__file__),
    ]
    for path in chat_path_files:
        hit = 'run_probe_scan' in _referenced_names(path)
        assert not hit, f'{path} references run_probe_scan -- the probe must never run on the chat path'


def test_router_model_only_imports_the_read_side_of_router_probe():
    """`_router_model` may import `router_eligibility` (a pure read); it
    must never import `run_probe_scan` (the live-measuring write side)."""
    src = pathlib.Path(llm.__file__).read_text()
    assert 'router_eligibility' in src
    assert 'run_probe_scan' not in src


def test_admin_smart_router_is_the_declared_caller_of_run_probe_scan():
    """Floor canary for the AST sweep above: if this ever goes red, the
    sweep's target moved and the negative tests above may be passing
    vacuously."""
    import admin_smart_router
    src = pathlib.Path(admin_smart_router.__file__).read_text()
    assert 'run_probe_scan' in src


# ── file size ────────────────────────────────────────────────────────────

def test_router_probe_module_stays_under_the_five_hundred_line_cap():
    assert len(pathlib.Path(rp.__file__).read_text().splitlines()) < 500
