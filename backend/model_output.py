"""
Pure text-cleaning helpers for model output.

Root cause (measured live, 2026-08-22): 9Router-routed models emit their
chain-of-thought inline in ``message.content`` / streaming ``delta.content``
instead of keeping it out of the visible answer. Observed live:
``sanjab/gemma-4-26b-a4b-it``'s entire visible answer to "hi" was the literal
string ``<thought>*   </thought>`` -- the user got an empty reasoning block
instead of a reply. Users must never see this.

Nothing in this module does I/O; it only transforms strings that have
already been read from a response. See chat.py for how it is wired into the
non-streaming and streaming response paths.
"""
from __future__ import annotations

import re

# Tag names (without angle brackets) whose content is model chain-of-thought
# that must never reach a user. Add a newly observed tag here -- everything
# below (both the whole-string cleaner and the streaming filter) derives its
# patterns from this one tuple.
_REASONING_TAGS: tuple[str, ...] = ('thought', 'think')

_REASONING_TAGS_LOWER: tuple[str, ...] = tuple(t.lower() for t in _REASONING_TAGS)

# Longest tag name we know about, used only to size the streaming filter's
# lookahead guard (see _possible_open_prefix/_possible_close_prefix below).
_MAX_TAG_LOOKAHEAD = 64

# One "complete pair, anywhere in the string" pattern per tag name.
# re.DOTALL so a multi-line thought block is matched as a single unit;
# non-greedy .*? so "<thought>a</thought>b<thought>c</thought>" removes both
# blocks rather than everything between the first open and the last close.
_PAIR_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(rf'<{tag}\b[^>]*>.*?</{tag}\s*>', re.IGNORECASE | re.DOTALL)
    for tag in _REASONING_TAGS
)

# An opening tag with no matching close anywhere after it -- the model ran
# out of tokens mid-thought. Anchored to the end of the string (re.DOTALL
# makes '.' match newlines too) so everything from the tag onward is dropped.
_UNCLOSED_OPEN_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(rf'<{tag}\b[^>]*>.*\Z', re.IGNORECASE | re.DOTALL)
    for tag in _REASONING_TAGS
)

# A closing tag with no opener before it in the string -- common when the
# upstream already ate the opening tag itself. Non-greedy from the very
# start of the string up to (and including) the first such closing tag, so
# everything before it -- the leaked reasoning fragment -- is dropped.
_STRAY_CLOSE_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(rf'\A.*?</{tag}\s*>', re.IGNORECASE | re.DOTALL)
    for tag in _REASONING_TAGS
)


def strip_reasoning(text: str) -> str:
    """Remove leaked <thought>/<think> reasoning blocks from ``text``.

    Handles, in order:
      1. one or more complete ``<tag>...</tag>`` pairs anywhere in the text
      2. a stray closing tag with no opener -- drops everything before it
         (inclusive of the tag itself)
      3. an unclosed opening tag -- drops everything from the tag to the end
      4. the whole content being nothing but a thought block -> returns ''

    Content with none of the tags in ``_REASONING_TAGS`` is returned
    byte-identical (no whitespace tidying, no reformatting at all) -- only
    text that actually contained a tag gets its surrounding whitespace
    stripped.
    """
    if not isinstance(text, str) or not text:
        return text

    original = text
    cleaned = text

    # (1) Complete pairs. Loop until stable: removing one tag's pairs can
    # newly expose another tag's pair boundaries (e.g. mixed <think>/
    # <thought> nesting), though in practice one pass per tag is almost
    # always enough.
    changed = True
    while changed:
        changed = False
        for pattern in _PAIR_PATTERNS:
            new_cleaned = pattern.sub('', cleaned)
            if new_cleaned != cleaned:
                cleaned = new_cleaned
                changed = True

    # (2) Stray closing tag, no opener -- drop everything up to and
    # including it. Only the first such tag matters: whatever is left after
    # it is the real visible answer.
    for pattern in _STRAY_CLOSE_PATTERNS:
        cleaned = pattern.sub('', cleaned, count=1)

    # (3) Unclosed opening tag -- drop from the tag to the end.
    for pattern in _UNCLOSED_OPEN_PATTERNS:
        cleaned = pattern.sub('', cleaned, count=1)

    if cleaned == original:
        # No tag matched anything -- true passthrough, not even a .strip().
        return original

    return cleaned.strip()


def clean_response_dict(response_data: dict) -> dict:
    """Strip reasoning blocks from every ``choices[*].message.content`` in a
    parsed (non-streaming) chat/completions response body, in place.

    Returns ``response_data`` for convenient chaining. Tolerates a malformed
    body (missing/non-list ``choices``, non-dict entries, non-string
    content) by leaving anything it cannot safely interpret untouched --
    this must never raise and break an otherwise-good response.
    """
    if not isinstance(response_data, dict):
        return response_data
    choices = response_data.get('choices')
    if not isinstance(choices, list):
        return response_data
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get('message')
        if not isinstance(message, dict):
            continue
        content = message.get('content')
        if isinstance(content, str):
            message['content'] = strip_reasoning(content)
    return response_data


def _tag_name_from_candidate(candidate: str, *, closing: bool) -> str:
    """``candidate`` is a fully-seen ``<...>`` (or ``</...>``) string.
    Returns the lowercased tag name (ignoring any attributes), or '' if it
    doesn't look like a tag at all."""
    inner = candidate[1:-1]
    if closing:
        if not inner.startswith('/'):
            return ''
        inner = inner[1:]
    inner = inner.strip()
    if not inner:
        return ''
    return inner.split()[0].lower().rstrip('/')


def _possible_open_prefix(after_lt: str) -> bool:
    """True if ``after_lt`` (everything buffered so far right after a bare
    '<', with no '>' yet) could still turn into one of our opening reasoning
    tags once more characters arrive."""
    if after_lt == '':
        return True
    s = after_lt.lower()
    for tag in _REASONING_TAGS_LOWER:
        if len(s) <= len(tag):
            if tag.startswith(s):
                return True
        elif s.startswith(tag):
            return True  # tag name matched; rest could be attributes
    return False


def _possible_close_prefix(after_lt: str) -> bool:
    """Same as _possible_open_prefix but for a '</tag' closing sequence."""
    if after_lt == '':
        return True
    if after_lt[0] != '/':
        return False
    return _possible_open_prefix(after_lt[1:])


class ReasoningStreamFilter:
    """Stateful filter that strips <thought>/<think> blocks from a stream of
    text pieces (e.g. successive SSE ``delta.content`` values), where a tag
    can be split across arbitrary piece boundaries.

    Usage::

        f = ReasoningStreamFilter()
        visible = f.feed(piece_1) + f.feed(piece_2) + ... + f.flush()

    Buffers only the minimum needed to disambiguate whether a run of
    characters starting with '<' is one of our tags (at most
    ``_MAX_TAG_LOOKAHEAD`` characters) -- everything else passes straight
    through immediately with no added latency, matching strip_reasoning()
    for the two cases that can actually occur live on an SSE stream:

      - a complete <tag>...</tag> pair, opened and closed anywhere across
        one or more feed() calls
      - an opening tag that is never closed because the stream ends first
        (model ran out of tokens mid-thought) -- flush() discards it

    Deliberately NOT handled: a stray closing tag with no opener, arriving
    mid-stream, where the leaked content before it has *already* been
    emitted to the client by the time the closing tag shows up. Reproducing
    strip_reasoning()'s "drop everything before it" behaviour for that case
    would require buffering the entire response from the start on the
    chance a stray close tag shows up eventually -- i.e. turning the stream
    into a non-stream, which defeats the point. strip_reasoning() itself
    (used on the non-streaming path) still handles it correctly.
    """

    def __init__(self) -> None:
        self._buf = ''
        self._in_tag = False

    def feed(self, piece: str) -> str:
        if not piece:
            return ''
        self._buf += piece
        out: list[str] = []
        while True:
            if not self._in_tag:
                idx = self._buf.find('<')
                if idx == -1:
                    out.append(self._buf)
                    self._buf = ''
                    break
                if idx > 0:
                    out.append(self._buf[:idx])
                    self._buf = self._buf[idx:]
                gt = self._buf.find('>')
                if gt == -1:
                    if len(self._buf) - 1 <= _MAX_TAG_LOOKAHEAD and _possible_open_prefix(self._buf[1:]):
                        break  # ambiguous prefix of a real tag -- wait for more
                    out.append(self._buf[0])
                    self._buf = self._buf[1:]
                    continue
                candidate = self._buf[:gt + 1]
                name = _tag_name_from_candidate(candidate, closing=False)
                if name in _REASONING_TAGS_LOWER:
                    self._in_tag = True
                    self._buf = self._buf[gt + 1:]
                    continue
                out.append(self._buf[0])
                self._buf = self._buf[1:]
                continue
            else:
                idx = self._buf.find('<')
                if idx == -1:
                    self._buf = ''  # all reasoning content -- discard, wait for more
                    break
                if idx > 0:
                    self._buf = self._buf[idx:]  # discard reasoning text before the '<'
                gt = self._buf.find('>')
                if gt == -1:
                    if len(self._buf) - 1 <= _MAX_TAG_LOOKAHEAD and _possible_close_prefix(self._buf[1:]):
                        break  # ambiguous prefix of the closing tag -- wait for more
                    self._buf = self._buf[1:]  # not our closing tag -- still reasoning, discard
                    continue
                candidate = self._buf[:gt + 1]
                name = _tag_name_from_candidate(candidate, closing=True)
                if name in _REASONING_TAGS_LOWER:
                    self._in_tag = False
                    self._buf = self._buf[gt + 1:]
                    continue
                self._buf = self._buf[1:]  # some other tag inside the block -- discard, rescan
                continue
        return ''.join(out)

    def flush(self) -> str:
        """Call once the upstream stream has ended. Returns any safe
        trailing text that was held back pending disambiguation.

        If a reasoning block was opened and never closed, its buffered
        content is discarded (the "ran out of tokens mid-thought" case).
        Otherwise, an ambiguous '<'-prefixed buffer that never resolved into
        a real tag is flushed as ordinary text -- it wasn't actually a tag.
        """
        if self._in_tag:
            self._buf = ''
            return ''
        buf, self._buf = self._buf, ''
        if buf.startswith('<'):
            after = buf[1:].lower()
            if any(after == tag or after.startswith(tag + ' ') for tag in _REASONING_TAGS_LOWER):
                return ''  # a complete-but-unclosed opening tag, e.g. "<thought"
        return buf
