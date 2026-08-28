"""Compression is opt-in. This file guards the WIRING, not the algorithm.

`middleware/compression.py` has its own suite (`test_compression_real.py`)
proving the compressor is correct and that `compression_enabled_for` defaults
to False. None of that helps if a call site forgets to ask.

That is not a hypothetical. Until 2026-08-28 `compress_messages` was called
unconditionally from all four chat paths and was DEAD: it passed a string
where headroom wants a list, `TypeError` was raised, and a bare
`except Exception` swallowed it. `/health/detailed` reported
`{"enabled": true, "total_calls": 0}` for months and nobody noticed, because
"enabled" only ever meant "the library imports".

Repairing the compressor turned that dead branch into a live one. A live
compression changes how many input tokens we send upstream, which is both what
the user is charged and what the upstream charges us -- so an ungated call site
is a silent money-path change for every user at once. The gate and the fix
landed in the same commit deliberately.

These tests read source, not behaviour, on purpose: an ungated call site is a
structural fact, and a unit test of any single chat handler would happily pass
while another handler leaked. AST over regex, because a mention inside a
docstring or a comment is not a call.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent

# Every module that compresses. Adding a fifth chat path? It belongs here, and
# this list is the reason you will be told about it.
CALL_SITES = [
    'chat.py',
    'chat_stream.py',
    'chat_smart.py',
    'chat_compare.py',
]

GATE = 'compression_enabled_for'
COMPRESS = 'compress_messages'


def _tree(filename: str) -> ast.Module:
    return ast.parse((BACKEND / filename).read_text())


def _enclosing_gate_test(tree: ast.Module, target: ast.AST) -> bool:
    """True if `target` sits (at any depth) inside an `if await GATE(...)`.

    Walks parents rather than eyeballing indentation, so reformatting the file
    cannot quietly disarm this.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if GATE not in ast.dump(node.test):
            continue
        for child in ast.walk(node):
            if child is target:
                return True
    return False


@pytest.mark.parametrize('filename', CALL_SITES)
def test_every_compress_call_sits_behind_the_opt_in_gate(filename: str) -> None:
    tree = _tree(filename)

    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == COMPRESS
    ]
    assert calls, (
        f'{filename} no longer calls {COMPRESS}(). If compression was removed '
        f'from this path on purpose, drop it from CALL_SITES in this file -- '
        f'do not leave a guard pointing at nothing.'
    )

    for call in calls:
        assert _enclosing_gate_test(tree, call), (
            f'{filename}:{call.lineno} calls {COMPRESS}() without an enclosing '
            f'`if await {GATE}(uid):`. Compression is opt-in; an ungated call '
            f'silently changes input token counts -- the money path -- for '
            f'every user at once.'
        )


@pytest.mark.parametrize('filename', CALL_SITES)
def test_the_gate_is_actually_imported(filename: str) -> None:
    """A gate resolved from a stale global instead of the module is a lie.

    Guards against someone satisfying the test above with a local variable that
    happens to be named `compression_enabled_for`.
    """
    tree = _tree(filename)
    imported = any(
        isinstance(n, ast.ImportFrom)
        and n.module == 'middleware.compression'
        and any(a.name == GATE for a in n.names)
        for n in ast.walk(tree)
    )
    assert imported, (
        f'{filename} does not import {GATE} from middleware.compression.'
    )


@pytest.mark.parametrize('filename', CALL_SITES)
def test_the_gate_is_awaited(filename: str) -> None:
    """`if compression_enabled_for(uid):` is always True -- a coroutine object
    is truthy. Forgetting the await turns the gate fully on while looking
    exactly like a working gate, so it gets its own assertion."""
    tree = _tree(filename)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == GATE):
            continue
        parents = [
            p for p in ast.walk(tree)
            if isinstance(p, ast.Await) and p.value is node
        ]
        assert parents, (
            f'{filename}:{node.lineno} calls {GATE}() without awaiting it. '
            f'An un-awaited coroutine is truthy, so the gate would be '
            f'permanently open.'
        )


def test_the_default_is_off() -> None:
    """The opt-in default lives in one place; pin it from the wiring side too.

    If this ever flips to True, every existing user starts compressing without
    having asked -- which is the exact outcome the gate exists to prevent.
    """
    src = (BACKEND / 'middleware' / 'compression.py').read_text()
    assert "prefs.get('compression_enabled', False)" in src, (
        'compression_enabled_for no longer defaults to False. Compression '
        'changes what the user is billed; it must never turn itself on.'
    )
