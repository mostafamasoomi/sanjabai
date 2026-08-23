"""Guard- every /admin/* route must actually check that the caller is an admin.

WHY THIS FILE EXISTS
--------------------
On 2026-08-23 ``GET /admin/test-models`` (content.py) was found reachable by
any anonymous caller on production -- verified live, it returned 200 without
a token. It was not a read-only leak. The handler

  * fires one real upstream chat completion per available model (25 at the
    time) on every single call, so anyone could burn provider money in a
    loop -- squarely against the house rule that no request may be
    loss-making, and
  * then WRITES to the production catalog
    (``UPDATE model_catalog SET recommended_for = ...``), so an anonymous
    request could change which models we recommend to real users.

It sat directly beside ``/admin/refresh-pricing``, which had been gated all
along, so this was an oversight rather than a decision -- exactly the kind
of single missing line that no amount of care catches reliably by review.

So this file does not merely pin that one route. ``test_no_admin_route_is
_ungated`` walks the AST of every backend module and fails on ANY handler
whose path starts with /admin and whose body never consults
``admin_required`` (directly or as ``admin.admin_required``). A future
handler that forgets the check fails here the day it is written, which is
the same "make the next instance structurally impossible" approach
tests/test_schema_drift_all_orm.py takes for missing migrations.

THE ALLOWLIST IS DELIBERATELY TINY. Adding a name to it is a decision to
publish that endpoint to the anonymous internet -- justify it in the
comment beside the entry, never just to make this test pass.
"""
from __future__ import annotations

import ast
import glob
import os
import re

import pytest
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Endpoints that are correctly reachable without already being an admin.
_INTENTIONALLY_OPEN = {
    # The admin login form itself -- it is what MAKES you an admin, so it
    # cannot require being one. It has its own credential check plus the
    # lockout counter in auth.py.
    'admin_login',
    # Logout only clears the caller's own session cookie. Gating it would
    # strand a half-authenticated client with no way to reset.
    'admin_logout',
}


def _admin_handlers():
    """Yield (module, function_name, route_path, body_source) for every
    handler registered on a path beginning with /admin."""
    for path in sorted(glob.glob(os.path.join(_BACKEND, '*.py'))):
        try:
            src = open(path, encoding='utf-8').read()
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        lines = src.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = '\n'.join(
                lines[max(0, node.lineno - 9):node.lineno]
            )
            match = re.search(
                r'@\w+\.(?:get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']',
                decorators,
            )
            if not match or not match.group(1).startswith('/admin'):
                continue
            body = '\n'.join(lines[node.lineno - 1:node.end_lineno])
            yield os.path.basename(path), node.name, match.group(1), body


def test_the_sweep_actually_finds_admin_routes():
    """Floor canary. If a refactor breaks the AST walk or the decorator
    regex, every assertion below would pass vacuously and this file would
    guard nothing while still showing green."""
    found = list(_admin_handlers())
    assert len(found) >= 40, (
        f"only {len(found)} /admin handlers discovered -- the sweep is "
        "probably broken, not the codebase suddenly tiny"
    )


def test_no_admin_route_is_ungated():
    ungated = {
        f'{module}::{name}': route
        for module, name, route, body in _admin_handlers()
        if name not in _INTENTIONALLY_OPEN
        and 'admin_required' not in body
    }
    assert not ungated, (
        "these /admin routes never consult admin_required, so anonymous "
        f"callers can reach them- {ungated}"
    )


def test_admin_test_models_rejects_anonymous_callers():
    """Regression pin for the specific route that was found open. Kept
    separate from the sweep so the incident stays legible in the suite
    output rather than hiding inside a generic assertion."""
    resp = client.get('/admin/test-models')
    assert resp.status_code in (401, 403), (
        f"/admin/test-models answered {resp.status_code} to an "
        "unauthenticated caller -- it triggers a paid upstream probe of "
        "every model and writes model_catalog.recommended_for"
    )
