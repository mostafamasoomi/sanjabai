"""Every backend route registered as `/api/...` needs a bare twin.

The Next proxy at `frontend/app/api/[...path]/route.ts` joins the captured
path segments and forwards them WITHOUT the `/api` prefix:

    /api/catalog/pricing   ->   backend /catalog/pricing

So a backend route whose registered path literally starts with `/api/` can
never be reached from a browser at that URL -- the browser's `/api/pricing`
arrives at the backend as `/pricing`. This is not hypothetical: the public
`https://sanjabai.com/api/pricing` answered 404 for exactly this reason,
while `/api/exchange-rate` worked only because content.py happens to also
register a bare `/exchange-rate` alongside it.

The rule is therefore: if you register `/api/X`, register `/X` too. This test
enforces it, because the failure is invisible from the backend side -- the
route exists, `curl` against the container finds it, and only the public URL
404s.
"""
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent

_ROUTE = re.compile(r"@router\.(?:get|post|put|delete|patch)\(\s*'([^']+)'")


def _registered_paths() -> dict[str, set[str]]:
    """{path: {files that register it}} across every backend module."""
    found: dict[str, set[str]] = {}
    for path in sorted(BACKEND.glob('*.py')):
        for m in _ROUTE.finditer(path.read_text(encoding='utf-8')):
            found.setdefault(m.group(1), set()).add(path.name)
    return found


def test_route_scan_finds_something():
    """Guards the guard: a broken regex would make the test below vacuous."""
    paths = _registered_paths()
    assert len(paths) > 50, f'suspiciously few routes found: {len(paths)}'
    assert '/v1/models' in paths


@pytest.mark.parametrize(
    'api_path',
    sorted(p for p in _registered_paths() if p.startswith('/api/')),
)
def test_api_prefixed_route_has_a_bare_twin(api_path):
    bare = api_path[len('/api'):]
    registered = _registered_paths()
    assert bare in registered, (
        f"{api_path} is registered but {bare} is not. The Next proxy strips "
        f"the /api prefix, so a browser request to {api_path} reaches the "
        f"backend as {bare} and 404s. Register {bare} on the same handler."
    )
