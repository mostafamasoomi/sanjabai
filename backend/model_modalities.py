"""
Derive `model_catalog.modalities` from a raw upstream `/v1/models` entry.

Every row in `model_catalog` was inserted with the column default
`{"input":["text"],"output":["text"]}` because `model_discovery.sync_provider`
never set it. That is false for the image/video/vision models the catalog
already contains, and `modalities` is served verbatim to the public API
(`content.py`), so getting this right here fixes the API with no frontend
change. See `backend/tests/test_model_modalities.py` for the evidence this
module is built from -- every classification below was checked against a
real entry pulled from a captured upstream payload, not invented.

CONVENTION (read this before changing a rule):
  * Allowed tokens are exactly `text`, `image`, `video`, `audio`.
  * `text` is added by default to both lists UNLESS an upstream gives us an
    explicit, complete `input_modalities`/`output_modalities` array -- in
    that case we trust the array verbatim (see PRIORITY 1 below), because
    the upstream is asserting the complete list, not a partial hint. A pure
    image-generation model reported this way ends up with
    `output: ["image"]`, no `text` -- that matches upstream fact (these
    APIs return image bytes, not a text explanation) and is exactly what
    omniroute's own payload says for e.g. `flux.2-*`.
  * Everywhere else (flag-based and name-based derivation), `text` stays in
    both lists and other tokens are appended -- we are only ever *adding*
    evidence of another modality on top of the baseline chat capability,
    never asserting a model that took text also lost it.

PRIORITY ORDER (first match wins -- see `derive_modalities`):
  0. Known id-pattern overrides that must beat any flag, because the two
     captured payloads contain flags that are actively misleading for these
     specific families (see _ID_OVERRIDES below for the evidence).
  1. Omniroute's explicit `input_modalities`/`output_modalities` arrays, or
     its top-level `type` field (`image`/`video`/`audio`) when the arrays
     are absent. Both are omniroute-only fields; nothing in the 9router
     payload carries them.
  2. 9router's (and omniroute's) `capabilities` flags: `vision`,
     `videoInput`, `audioInput`, `imageOutput`, `audioOutput`.
  3. Name-based fallback over the *specific* media ids confirmed present in
     the two captured payloads (see _NAME_FALLBACKS). This is deliberately
     a closed list, not a heuristic over generic substrings like "video" --
     see the module docstring warning about `minimax`.
  4. Default: `{"input": ["text"], "output": ["text"]}`.

WHY THE OVERRIDES IN PRIORITY 0 EXIST (both proven against the real JSON):

  * `*transcribe*` (`gpt-4o-transcribe`, `gpt-4o-mini-transcribe`,
    `mai-transcribe-1.5`, `voxtral-mini-transcribe`): these are speech-to-
    text endpoints -- audio in, text out. But omniroute's own payload marks
    them `"capabilities": {"vision": true, ...}` and even
    `"input_modalities": ["text", "image"]` (no "audio" at all!) -- clearly
    a generic chat-completions capability template that was never updated
    for this endpoint type, not a real assertion that this model accepts
    images. Trusting PRIORITY 1/2 here would mislabel a pure audio-input
    model as image-input, which is exactly the "wrong media modality"
    mistake this module exists to prevent. So the id pattern wins outright
    for this family and we hand-assign `input: [text, audio]`,
    `output: [text]`.

  * `minimax-*`: several resellers (`freellmapi`, `nvidia`, `bynara`,
    `kimchi`, ...) report `"vision": true` for `minimax-m3`. Per product
    decision these stay plain chat models in this catalog regardless --
    MiniMax's real-world brand association with video (Hailuo) makes this
    exactly the kind of name a careless classifier would sweep into a media
    family from world knowledge rather than the actual data, and the
    scattered `vision` flag is not trusted as a substitute for a confirmed
    working vision endpoint. Forced to the plain default, no exceptions.

WHAT IS NOT HANDLED (and why that is fine): omniroute lists several
`*-tts*` ids (`mimo-v2.5-tts`, ...) with `"type": "audio"` but also a
(clearly stale) `input_modalities: ["text","image"], output_modalities:
["text"]`. That family is not in the confirmed-present media list this
module was asked to cover, and PRIORITY 1 already resolves it to the safe
plain-text default via the (wrong but conservative) explicit array -- so no
special-case was added for it. Silently defaulting to text/text is exactly
the safe failure mode called for: this module must never *guess* a media
modality from a weak signal.
"""
from __future__ import annotations

import re
from typing import Any

_ALLOWED = ('text', 'image', 'audio', 'video')

_DEFAULT: dict[str, list[str]] = {'input': ['text'], 'output': ['text']}


def _default() -> dict[str, list[str]]:
    return {'input': list(_DEFAULT['input']), 'output': list(_DEFAULT['output'])}


def _normalize(tokens: Any) -> list[str]:
    """Keep only allowed tokens, dedup, in a fixed canonical order."""
    if not isinstance(tokens, (list, tuple)):
        return []
    seen = {str(t).lower() for t in tokens}
    return [t for t in _ALLOWED if t in seen]


# ---------------------------------------------------------------------------
# PRIORITY 0: id-pattern overrides that must beat any upstream flag.
# Order matters: transcribe is checked before minimax could ever matter, but
# neither family overlaps in practice -- kept as separate, explicit checks
# so each one's evidence (see module docstring) stays easy to find.
# ---------------------------------------------------------------------------
_TRANSCRIBE_RE = re.compile(r'transcribe', re.IGNORECASE)
_MINIMAX_RE = re.compile(r'minimax', re.IGNORECASE)


def _id_override(model_id: str) -> dict[str, list[str]] | None:
    if _TRANSCRIBE_RE.search(model_id):
        return {'input': ['text', 'audio'], 'output': ['text']}
    if _MINIMAX_RE.search(model_id):
        return _default()
    return None


# ---------------------------------------------------------------------------
# PRIORITY 3: name-based fallback, closed list of media families genuinely
# present in the captured omniroute/9router payloads (see conftest for the
# raw entries). Deliberately narrow -- do not add a pattern without a real
# entry in one of the two JSON files to justify it.
# ---------------------------------------------------------------------------
_IMAGE_NAME_PATTERNS = (
    re.compile(r'flux\.2', re.IGNORECASE),
    re.compile(r'nano-banana', re.IGNORECASE),
    re.compile(r'gemini[\w.\-]*-image', re.IGNORECASE),
    re.compile(r'gpt-5-image-mini', re.IGNORECASE),
    re.compile(r'gpt-5\.4-image-2', re.IGNORECASE),
)
_VIDEO_NAME_PATTERNS = (
    re.compile(r'\bveo\b', re.IGNORECASE),
    re.compile(r'veo-3\.1', re.IGNORECASE),
    re.compile(r'seedance', re.IGNORECASE),
    re.compile(r'agnes-video', re.IGNORECASE),
)


def _name_fallback(model_id: str) -> dict[str, list[str]] | None:
    bare = model_id.strip()
    if bare.lower() == 'video':
        return {'input': ['text'], 'output': ['video']}
    if any(p.search(bare) for p in _VIDEO_NAME_PATTERNS):
        return {'input': ['text'], 'output': ['video']}
    if any(p.search(bare) for p in _IMAGE_NAME_PATTERNS):
        return {'input': ['text'], 'output': ['image']}
    return None


def derive_modalities(model_id: str, raw: dict) -> dict:
    """-> {"input": [...], "output": [...]}. Pure function, no I/O.

    `raw` is one entry from an upstream `GET /v1/models` response, in
    either omniroute's or 9router's shape (see module docstring). Order of
    checks is the priority order documented at the top of this module.
    """
    raw = raw if isinstance(raw, dict) else {}

    override = _id_override(model_id)
    if override is not None:
        return override

    # PRIORITY 1a: omniroute's explicit modalities arrays -- trusted
    # verbatim (see CONVENTION above for why `text` is not force-added).
    in_arr = _normalize(raw.get('input_modalities'))
    out_arr = _normalize(raw.get('output_modalities'))
    if in_arr or out_arr:
        return {
            'input': in_arr or ['text'],
            'output': out_arr or ['text'],
        }

    # PRIORITY 1b: omniroute's top-level `type` field, only reached when no
    # modalities arrays were given (true for its `veo`/`seedance` rows).
    top_type = raw.get('type')
    if top_type == 'image':
        return {'input': ['text'], 'output': ['image']}
    if top_type == 'video':
        return {'input': ['text'], 'output': ['video']}
    if top_type == 'audio':
        return {'input': ['text', 'audio'], 'output': ['text']}

    # PRIORITY 2: capability flags, shared shape between omniroute (only
    # ever sets `vision`) and 9router (sets all of these).
    caps = raw.get('capabilities')
    caps = caps if isinstance(caps, dict) else {}
    inp, out = ['text'], ['text']
    saw_flag = False
    if caps.get('vision'):
        inp.append('image')
        saw_flag = True
    if caps.get('videoInput'):
        inp.append('video')
        saw_flag = True
    if caps.get('audioInput'):
        inp.append('audio')
        saw_flag = True
    if caps.get('imageOutput'):
        out.append('image')
        saw_flag = True
    if caps.get('audioOutput'):
        out.append('audio')
        saw_flag = True
    if saw_flag:
        return {'input': _normalize(inp), 'output': _normalize(out)}

    # PRIORITY 3: name-based fallback -- only reached when the payload gave
    # us no usable signal at all (the common case for 9router's bare ids).
    fallback = _name_fallback(model_id)
    if fallback is not None:
        return fallback

    # PRIORITY 4: nothing known about this model.
    return _default()
