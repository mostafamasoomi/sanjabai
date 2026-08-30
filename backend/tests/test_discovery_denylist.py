"""Owner-banned upstream routes must never re-land in the catalog.

Decision 2026-08-30 (docs/ROADMAP.md): a set of free/reseller upstream routes
were purged from the catalog and are banned for good. `model_discovery`
skips them on every sweep via `_is_denylisted`.

The banned prefixes are supply-chain identifiers and the repo is PUBLIC, so
they live in a gitignored config (`discovery_denylist.txt` / the
DISCOVERY_DENYLIST_PREFIXES env var), never in tracked source -- and therefore
never as literals in this test either. Every case here is derived from the
loaded config and the real captured 9router payload
(`tests/fixtures/nine_models.json`), so the suite proves the ban against the
exact strings the upstream reports without naming them.
"""
from __future__ import annotations

import json
import pathlib

import model_discovery
from model_discovery import _denylist_prefixes, _is_denylisted

_SRC = (pathlib.Path(__file__).resolve().parents[1] / 'model_discovery.py').read_text()
_NINE = [m['id'] for m in json.loads(
    (pathlib.Path(__file__).parent / 'fixtures' / 'nine_models.json').read_text())['data']]


def _prefix(model_id: str) -> str:
    return model_id.split('/', 1)[0].strip().lower()


def _banned_in_fixture(prefixes) -> list[str]:
    return [i for i in _NINE
            if _prefix(i) in prefixes or any(_prefix(i).startswith(b + '-') for b in prefixes)]


def test_config_is_loaded_and_nonempty():
    """The gitignored denylist must actually be present in this environment."""
    assert _denylist_prefixes(), \
        'denylist config is empty -- discovery_denylist.txt / env var not loaded'


def test_fixture_actually_contains_banned_ids():
    """Guard the guard: if the fixture had no banned ids the ban tests are empty."""
    assert _banned_in_fixture(_denylist_prefixes()), 'no banned id present in fixture'


def test_every_banned_fixture_id_is_denylisted():
    prefixes = _denylist_prefixes()
    missed = [i for i in _banned_in_fixture(prefixes) if not _is_denylisted(i)]
    assert not missed, f'banned ids slipped through the denylist: {missed[:10]}'


def test_no_allowed_fixture_id_is_denylisted():
    banned = set(_banned_in_fixture(_denylist_prefixes()))
    caught = [i for i in _NINE if i not in banned and _is_denylisted(i)]
    assert not caught, f'the denylist wrongly caught real models: {caught[:10]}'


def test_exact_prefix_and_shard_suffix_match_but_not_lookalikes():
    for b in _denylist_prefixes():
        assert _is_denylisted(f'{b}/some-model'), f'exact prefix {b} not banned'
        assert _is_denylisted(f'{b}-s9/some-model'), f'shard suffix of {b} not banned'
        assert not _is_denylisted(f'{b}x/some-model'), f'lookalike {b}x wrongly banned'
    assert not _is_denylisted('omni/gpt-oss-120b')
    assert not _is_denylisted('gemini-api/models/gemini-3.6-flash')


def test_prefixes_are_not_hardcoded_in_discovery_source():
    """The banned prefixes must come from config, never a literal in this module.

    (The one exception is `_INFRA_TOKENS`, the display-name stripper, which
    predates this ban and is already public -- so we assert the denylist
    *function* bodies carry no banned literal, not the whole file.)
    """
    start = _SRC.index('def _denylist_prefixes')
    end = _SRC.index('\ndef _display_name')
    denylist_code = _SRC[start:end].lower()
    for b in _denylist_prefixes():
        assert b not in denylist_code, \
            f'banned prefix {b!r} is hardcoded in the denylist code -- must load from config'


def test_denylist_is_wired_into_sync_provider():
    """A revert that drops the `continue` fails here (wiring guard)."""
    assert 'if _is_denylisted(model_id):' in _SRC, 'denylist call removed from discovery'
    idx = _SRC.index('if _is_denylisted(model_id):')
    assert 'continue' in _SRC[idx:idx + 120], 'denylist no longer skips the row'


def test_env_var_overrides_file(monkeypatch):
    """DISCOVERY_DENYLIST_PREFIXES takes precedence and parses comma/newline."""
    _denylist_prefixes.cache_clear()
    monkeypatch.setenv('DISCOVERY_DENYLIST_PREFIXES', 'zzz-fake, yyy-fake\nwww-fake')
    try:
        assert set(model_discovery._denylist_prefixes()) == {'zzz-fake', 'yyy-fake', 'www-fake'}
        assert _is_denylisted('zzz-fake/m') and _is_denylisted('yyy-fake-s2/m')
    finally:
        _denylist_prefixes.cache_clear()
