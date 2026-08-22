"""
Tests for `model_modalities.derive_modalities()`, the two `model_discovery`
helpers it now feeds (`_context_window`, `_max_output_tokens`), and their
agreement with the one-time backfill in `migrations/0031_model_modalities.sql`.

`tests/fixtures/{omni,nine}_models.json` are byte-for-byte copies of the raw
upstream `GET /v1/models` payloads captured for this catalog (287 omniroute
models, 830 9router models) -- the same payloads `model_modalities.py`'s
module docstring cites as evidence for every rule. They live in the repo
(not a session scratch path) specifically so this suite keeps proving
agreement between the migration and the Python classifier long after the
session that captured them is gone.
"""
from __future__ import annotations

import json
import pathlib
import re

from model_discovery import _context_window, _max_output_tokens
from model_modalities import derive_modalities

FIXTURES = pathlib.Path(__file__).parent / 'fixtures'
MIGRATION_PATH = pathlib.Path(__file__).resolve().parent.parent / 'migrations' / '0031_model_modalities.sql'

_OMNI = {m['id']: m for m in json.loads((FIXTURES / 'omni_models.json').read_text())['data']}
_NINE = {m['id']: m for m in json.loads((FIXTURES / 'nine_models.json').read_text())['data']}

DEFAULT = {'input': ['text'], 'output': ['text']}


def omni(model_id: str) -> dict:
    """A real omniroute entry, keyed exactly as sync_provider() would see it."""
    return _OMNI[model_id]


def nine(model_id: str) -> dict:
    """A real 9router entry, keyed exactly as sync_provider() would see it."""
    return _NINE[model_id]


def raw_for(model_id: str) -> dict:
    """Whichever fixture actually has this id -- omniroute checked first.

    Only two ids in the two captured payloads exist in both files at once
    (`mimo/mimo-v2.5`, `mimo/mimo-v2.5-pro`); the live catalog records both
    as upstream = omniroute, so omniroute-first is the correct tie-break.
    Neither id is touched by 0031's backfill, so this only matters for the
    exhaustive migration-agreement tests below staying correct if that ever
    changes.
    """
    if model_id in _OMNI:
        return _OMNI[model_id]
    return _NINE[model_id]


# ---------------------------------------------------------------------------
# Image-generation family
# ---------------------------------------------------------------------------

def test_image_generation_omniroute_explicit_arrays():
    """omniroute's own input_modalities/output_modalities is trusted verbatim."""
    for model_id in (
        'antigravity/gemini-3.1-flash-image',
        'openrouter/black-forest-labs/flux.2-max',
        'openrouter/google/gemini-3.1-flash-image-preview',
        'openrouter/google/gemini-3-pro-image-preview',
        'openrouter/openai/gpt-5-image-mini',
        'openrouter/openai/gpt-5.4-image-2',
    ):
        raw = omni(model_id)
        assert raw.get('type') == 'image'
        assert derive_modalities(model_id, raw) == {'input': ['text'], 'output': ['image']}


def test_image_generation_ninerouter_explicit_flags():
    """9router's own imageOutput/vision flags are honored when both are set."""
    model_id = 'omni/openrouter/google/gemini-3.1-flash-image-preview'
    raw = nine(model_id)
    assert raw['capabilities']['imageOutput'] is True
    assert raw['capabilities']['vision'] is True
    assert derive_modalities(model_id, raw) == {
        'input': ['text', 'image'], 'output': ['text', 'image'],
    }

    # gpt-5-image-mini/gpt-5.4-image-2 report imageOutput true but vision
    # false on the 9router route -- image out, no image in.
    model_id = 'omni/openrouter/openai/gpt-5-image-mini'
    raw = nine(model_id)
    assert raw['capabilities']['imageOutput'] is True
    assert raw['capabilities']['vision'] is False
    assert derive_modalities(model_id, raw) == {
        'input': ['text'], 'output': ['text', 'image'],
    }


def test_image_generation_name_fallback_when_no_flags():
    """flux.2 and nano-banana-pro reach the name-based fallback -- their
    9router capability entries are all false/absent, the common case for
    the bulk of that payload."""
    model_id = 'omni/openrouter/black-forest-labs/flux.2-max'
    raw = nine(model_id)
    caps = raw['capabilities']
    assert not any(caps.get(k) for k in ('vision', 'imageOutput', 'videoInput', 'audioInput', 'audioOutput'))
    assert derive_modalities(model_id, raw) == {'input': ['text'], 'output': ['image']}

    model_id = 'gemini-api/models/nano-banana-pro-preview'
    raw = nine(model_id)
    assert derive_modalities(model_id, raw) == {'input': ['text'], 'output': ['image']}


# ---------------------------------------------------------------------------
# Video-generation family
# ---------------------------------------------------------------------------

def test_video_generation_omniroute_type_field():
    """veo/seedance carry omniroute's top-level type=video with no
    modalities arrays at all -- the only family that actually reaches
    PRIORITY 1b."""
    for model_id in ('veoaifree-web/veo', 'veoaifree-web/seedance', 'veo-free/veo', 'veo-free/seedance'):
        raw = omni(model_id)
        assert raw.get('type') == 'video'
        assert 'input_modalities' not in raw and 'output_modalities' not in raw
        assert derive_modalities(model_id, raw) == {'input': ['text'], 'output': ['video']}


def test_video_generation_ninerouter_name_fallback():
    """9router's capability schema has no field that can express video
    OUTPUT at all (only videoInput), so every video-generation id sourced
    from 9router can only ever be resolved by the name-based fallback."""
    for model_id in (
        'gemini-api/models/veo-3.1-generate-preview',
        'gemini-api/models/veo-3.1-fast-generate-preview',
        'gemini-api/models/veo-3.1-lite-generate-preview',
        'bynara/agnes-video-v2.0',
        'omni/veoaifree-web/veo',
        'omni/veoaifree-web/seedance',
    ):
        raw = nine(model_id)
        assert derive_modalities(model_id, raw) == {'input': ['text'], 'output': ['video']}


def test_bare_video_id_name_fallback():
    raw = nine('Video')
    assert 'capabilities' not in raw
    assert derive_modalities('Video', raw) == {'input': ['text'], 'output': ['video']}


# ---------------------------------------------------------------------------
# Vision (image-input) family -- distinct from image-generation
# ---------------------------------------------------------------------------

def test_vision_input_only_stays_text_output():
    """A model that accepts an image but only ever answers in text is not
    an image-generation model -- output must stay plain text."""
    model_id = 'aug/gemini-3.1-pro-preview'
    raw = omni(model_id)
    assert raw['input_modalities'] == ['text', 'image']
    assert raw['output_modalities'] == ['text']
    assert derive_modalities(model_id, raw) == {'input': ['text', 'image'], 'output': ['text']}

    # The `agy` route for the same underlying model reports the same
    # vision-in/text-out shape via its own explicit arrays.
    model_id = 'agy/gemini-3.1-flash-image'
    raw = omni(model_id)
    assert derive_modalities(model_id, raw) == {'input': ['text', 'image'], 'output': ['text']}


# ---------------------------------------------------------------------------
# False-positive traps
# ---------------------------------------------------------------------------

def test_transcribe_family_is_audio_input_not_image():
    """Both upstreams mark these vision:true (omniroute even claims
    input_modalities include image, no audio at all) -- a stale
    chat-completions capability template, not a real assertion. The
    id-pattern override must win regardless of upstream, provider, or the
    misleading flags."""
    for model_id, src in (
        ('openrouter/openai/gpt-4o-transcribe', omni),
        ('openrouter/openai/gpt-4o-mini-transcribe', omni),
        ('openrouter/microsoft/mai-transcribe-1.5', omni),
        ('openrouter/mistralai/voxtral-mini-transcribe', omni),
        ('omni/openrouter/openai/gpt-4o-transcribe', nine),
        ('omni/openrouter/openai/gpt-4o-mini-transcribe', nine),
    ):
        raw = src(model_id)
        result = derive_modalities(model_id, raw)
        assert result == {'input': ['text', 'audio'], 'output': ['text']}, (model_id, raw, result)


def test_transcribe_flags_really_are_misleading():
    """Guards the guard: prove the omniroute payload for this family truly
    would mislead a naive flag-reader, so the override above is not
    protecting against a strawman."""
    raw = omni('openrouter/openai/gpt-4o-transcribe')
    assert raw['capabilities'].get('vision') is True
    assert raw.get('input_modalities') == ['text', 'image']
    assert 'audio' not in (raw.get('input_modalities') or [])


def test_minimax_family_stays_plain_text_regardless_of_vision_flag():
    """Several resellers report vision:true for minimax-m3 -- per product
    decision this catalog does not expose it as a vision modality (see
    module docstring), so the id-pattern override forces plain text/text
    even though PRIORITY 2 would otherwise fire."""
    raw = nine('freellmapi/minimax-m3')
    assert raw['capabilities'].get('vision') is True
    assert derive_modalities('freellmapi/minimax-m3', raw) == DEFAULT

    raw = nine('nvidia/minimaxai/minimax-m3')
    assert raw['capabilities'].get('vision') is True
    assert derive_modalities('nvidia/minimaxai/minimax-m3', raw) == DEFAULT

    # No vision flag at all for this route -- still must land on default,
    # not get swept into a media family by brand-name association.
    raw = omni('auto/minimax')
    assert derive_modalities('auto/minimax', raw) == DEFAULT


# ---------------------------------------------------------------------------
# Default fallback
# ---------------------------------------------------------------------------

def test_default_when_no_signal_and_unremarkable_name():
    raw = nine('freellmapi/auto')
    caps = raw['capabilities']
    assert not any(caps.get(k) for k in ('vision', 'imageOutput', 'videoInput', 'audioInput', 'audioOutput'))
    assert derive_modalities('freellmapi/auto', raw) == DEFAULT

    raw = omni('auto/best-coding')
    assert 'vision' not in raw['capabilities']
    assert derive_modalities('auto/best-coding', raw) == DEFAULT


def test_default_for_empty_or_missing_raw():
    assert derive_modalities('some-unknown-id', {}) == DEFAULT
    assert derive_modalities('some-unknown-id', None) == DEFAULT  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Migration agreement -- modalities
# ---------------------------------------------------------------------------

_MODALITY_UPDATE_RE = re.compile(
    r"UPDATE model_catalog SET modalities = '(?P<json>\{.*?\})'::jsonb\s*"
    r"WHERE id IN \(\s*(?P<ids>.*?)\s*\)\s*AND modalities",
    re.DOTALL,
)


def _parse_modality_groups() -> list[tuple[list[str], dict]]:
    text = MIGRATION_PATH.read_text(encoding='utf-8')
    groups = []
    for m in _MODALITY_UPDATE_RE.finditer(text):
        expected = json.loads(m.group('json'))
        ids = re.findall(r"'([^']*)'", m.group('ids'))
        groups.append((ids, expected))
    return groups


def test_migration_modalities_groups_are_parseable():
    """Guards the guard below: a broken regex would make it vacuously pass."""
    groups = _parse_modality_groups()
    assert len(groups) == 6
    total_ids = sum(len(ids) for ids, _ in groups)
    assert total_ids == 40


def test_migration_modalities_agree_with_classifier():
    for ids, expected in _parse_modality_groups():
        for model_id in ids:
            actual = derive_modalities(model_id, raw_for(model_id))
            assert actual == expected, f'{model_id}: derive_modalities={actual} migration={expected}'


# ---------------------------------------------------------------------------
# Migration agreement -- context_window / max_output_tokens
# ---------------------------------------------------------------------------

_CTX_VALUES_RE = re.compile(r"FROM \(VALUES\n(?P<body>.*?)\n\) AS v\(id, ctx, max_out\)", re.DOTALL)
_CTX_TUPLE_RE = re.compile(r"\('((?:[^'\\]|\\.)*)',\s*(\d+),\s*(\d+)\)")


def _parse_context_window_rows() -> list[tuple[str, int, int]]:
    text = MIGRATION_PATH.read_text(encoding='utf-8')
    body = _CTX_VALUES_RE.search(text).group('body')
    rows = []
    for raw_id, ctx, max_out in _CTX_TUPLE_RE.findall(body):
        model_id = raw_id.replace("''", "'").replace('\\:', ':')
        rows.append((model_id, int(ctx), int(max_out)))
    return rows


def test_migration_context_window_rows_are_parseable():
    rows = _parse_context_window_rows()
    assert len(rows) == 753
    assert len({model_id for model_id, _, _ in rows}) == 753  # no duplicate ids


def test_migration_context_window_agrees_with_helpers():
    for model_id, ctx, max_out in _parse_context_window_rows():
        raw = raw_for(model_id)
        assert _context_window(raw) == ctx, f'{model_id}: _context_window={_context_window(raw)} migration={ctx}'
        assert _max_output_tokens(raw) == max_out, (
            f'{model_id}: _max_output_tokens={_max_output_tokens(raw)} migration={max_out}'
        )


def test_context_window_fallback_when_nothing_reported():
    assert _context_window({}) == 8192
    assert _max_output_tokens({}) is None


def test_context_window_reads_nested_ninerouter_capabilities():
    """The exact bug report that started this change: these gemini-api
    rows report nothing at the top level, only capabilities.contextWindow
    / capabilities.maxOutput."""
    for model_id in (
        'gemini-api/models/gemini-2.5-flash',
        'gemini-api/models/gemini-3.5-flash',
        'gemini-api/models/gemini-3.6-flash',
        'gemini-api/models/gemini-3.7-flash',
    ):
        raw = nine(model_id)
        assert 'context_window' not in raw and 'context_length' not in raw
        assert _context_window(raw) == 1048576
        assert _max_output_tokens(raw) == 65536


def test_context_window_never_invents_a_value_not_reported():
    """A model with only unrelated flags must still fall back to 8192, not
    a value guessed from the family it belongs to."""
    raw = {'capabilities': {'tool_calling': True}}
    assert _context_window(raw) == 8192
    assert _max_output_tokens(raw) is None
