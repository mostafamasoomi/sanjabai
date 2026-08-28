"""The developer page's smart-mode documentation must match the backend.

Smart mode has worked for API-key callers since it shipped -- /v1/smart-chat
takes `_get_user_id`, the same dependency that accepts either a session cookie
or an `sk-` key -- but the developer page said nothing about it, so the one
audience that would use it from code could not discover it. Session 26 added
`frontend/app/developer/components/SmartModeSection.tsx`.

Documentation drifts silently: nothing in a frontend build fails when the
backend stops accepting a header value the docs still advertise, and the
product rule here is honest labelling. So the mode names and the header names
are pinned in BOTH directions:

  * every value the docs advertise must be one the parser really accepts
  * every mode the parser really accepts must appear in the docs

The second direction is the one that rots. A future mode added to
chat_smart_mode.py with no doc entry is invisible to API users, which is the
exact bug this page was written to close.
"""
from __future__ import annotations

import re
from pathlib import Path

import chat_smart_mode

_FRONTEND = Path(__file__).resolve().parents[2] / 'frontend'
_DOC = _FRONTEND / 'app' / 'developer' / 'components' / 'SmartModeSection.tsx'
_CHAT_SMART = Path(__file__).resolve().parents[1] / 'chat_smart.py'


def _doc_text() -> str:
    assert _DOC.exists(), f'the smart-mode developer docs are gone: {_DOC}'
    return _DOC.read_text(encoding='utf-8')


def test_every_mode_the_parser_accepts_is_documented():
    """The direction that rots. Add MODE_X to the parser, forget the docs,
    and API users never learn the mode exists."""
    accepted = {
        v for k, v in vars(chat_smart_mode).items()
        if k.startswith('MODE_') and isinstance(v, str)
    }
    assert accepted, 'no MODE_* constants found -- this test has gone blind'
    text = _doc_text()
    missing = sorted(m for m in accepted if m not in text)
    assert not missing, f'accepted smart modes absent from the developer docs: {missing}'


def test_the_documented_combo_form_is_the_prefix_the_parser_looks_for():
    """`combo:<id>` is advertised as the shape. If the parser's prefix ever
    changed, every documented example would be silently wrong."""
    assert chat_smart_mode._COMBO_PREFIX in _doc_text()


def test_the_docs_advertise_no_mode_the_parser_would_reject():
    """A mode named in the docs but unknown to the parser degrades to `auto`
    without an error -- so the user is told it works and it silently does not.
    Only the literal request-header line is scanned; the prose deliberately
    talks about falling back to the rules and must not be parsed as a value."""
    text = _doc_text()
    header_line = next(
        (ln for ln in text.splitlines() if 'X-Smart-Mode:' in ln and 'REQUEST_HEADER' in ln),
        None,
    )
    assert header_line, 'the request-header constant is gone from the docs'
    advertised = {
        tok.strip()
        for tok in header_line.split('X-Smart-Mode:')[1].split("'")[0].split('|')
        if tok.strip()
    }
    accepted = {
        v for k, v in vars(chat_smart_mode).items()
        if k.startswith('MODE_') and isinstance(v, str)
    }
    # `combo:<id>` is the parameterised form of MODE_COMBO.
    normalised = {a.split(':')[0] for a in advertised}
    unknown = sorted(normalised - accepted)
    assert not unknown, f'the developer docs advertise modes the parser rejects: {unknown}'


def test_both_response_headers_the_docs_promise_are_really_set():
    """The docs tell API users to trust the RESPONSE header over their own
    request header. That advice is only safe while the response headers exist."""
    served = _CHAT_SMART.read_text(encoding='utf-8')
    for header in ('X-Smart-Mode', 'X-Smart-Model'):
        assert re.search(
            rf"headers\[\s*['\"]{re.escape(header)}['\"]\s*\]\s*=", served
        ), f'{header} is documented as a response header but chat_smart.py never sets it'
        assert header in _doc_text(), f'{header} is set by the backend but undocumented'


def test_the_docs_name_the_endpoint_that_actually_serves_smart_mode():
    """A correct header on the wrong path is a silent no-op: /v1/chat/completions
    never reads X-Smart-Mode."""
    served = _CHAT_SMART.read_text(encoding='utf-8')
    assert "'/v1/smart-chat'" in served, 'the smart-chat route moved'
    assert '/v1/smart-chat' in _doc_text()
