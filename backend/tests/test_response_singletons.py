"""A route may not hand back a module-level Response object.

A Starlette `Response` is mutated in place on its way out through the
middleware stack. Reuse one across requests and the mutations accumulate:
GZipMiddleware stamps `content-encoding: gzip` on the shared object during the
first response, then hands the *uncompressed* body to every later one, and
`vary` grows another `Accept-Encoding` each time. The client's very next call
raises a decode error instead of reading the status we meant to send.

This was live on production, not theoretical. Four unauthenticated GETs of
/admin/logical-models against the running API returned:

    #1 401  vary='Accept-Encoding'  content-encoding='gzip'
    #2 httpx.DecodingError: incorrect header check
    #3 httpx.DecodingError
    #4 httpx.DecodingError

admin_logical.py held `_UNAUTHORIZED` and `_NO_DB` as module-level singletons
(and admin_moderation.py had the same defect with its 401). Both now build a
fresh Response per call. Nothing caught it because every existing admin test
makes exactly ONE unauthenticated request per test and runs without GZip --
the two conditions the bug needs. So this file asserts on the SECOND call, and
mounts GZipMiddleware, deliberately.

Guarding the *behaviour* rather than the source: a future module that
reintroduces a shared Response fails the last test here without anyone having
to remember this story.
"""
from __future__ import annotations

import importlib
import pathlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response
from starlette.testclient import TestClient

import admin_logical
import admin_moderation

BACKEND = pathlib.Path(__file__).resolve().parents[1]

def _client(router) -> TestClient:
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=1)
    app.include_router(router)
    return TestClient(app)


class TestRepeatedDenialsStayReadable:
    @pytest.mark.parametrize(
        'module, router_owner, path',
        [
            ('admin_logical', admin_logical, '/admin/logical-models'),
            ('admin_moderation', admin_moderation, '/admin/moderation/rules'),
        ],
    )
    def test_the_second_unauthenticated_request_is_still_decodable(
        self, module, router_owner, path,
    ):
        target = 'admin_required' if module == 'admin_logical' else None
        ctx = (
            patch.object(router_owner, 'admin_required', new=AsyncMock(return_value=False))
            if target else
            patch('admin.admin_required', new=AsyncMock(return_value=False))
        )
        with ctx:
            client = _client(router_owner.router)
            seen = []
            for _ in range(4):
                r = client.get(path, headers={'Accept-Encoding': 'gzip'})
                seen.append((r.status_code, r.headers.get('vary'), r.text))

        first = seen[0]
        for i, (status, vary, body) in enumerate(seen[1:], start=2):
            assert status == first[0], f'call #{i} changed status: {status}'
            assert body == first[2], (
                f'call #{i} body differs from call #1 -- a shared Response '
                f'object was mutated on the way out'
            )
            if vary is not None:
                parts = [p.strip() for p in vary.split(',')]
                assert len(parts) == len(set(parts)), (
                    f'call #{i} vary accumulated duplicates: {vary!r}'
                )


class TestNoModuleHoldsAResponse:
    """The general rule, checked over every backend module that imports one."""

    def test_no_backend_module_defines_a_module_level_response(self):
        offenders = []
        for path in sorted(BACKEND.glob('*.py')):
            if path.name.startswith('test') or path.name == 'conftest.py':
                continue
            try:
                mod = importlib.import_module(path.stem)
            except Exception:
                continue  # not importable standalone; other suites cover it
            for name, value in vars(mod).items():
                if name.startswith('__'):
                    continue
                if isinstance(value, Response):
                    offenders.append(f'{path.name}::{name}')
        assert not offenders, (
            'module-level Response objects are reused across requests and are '
            'mutated in place by middleware; build one per call instead: '
            + ', '.join(offenders)
        )
