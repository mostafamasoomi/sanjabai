"""No migration may contain a colon followed by a word -- comments included.

`migrate.py` splits each `.sql` file on top-level semicolons and hands every
fragment to SQLAlchemy's `text()`. `text()` treats a colon immediately
followed by an identifier as a bind parameter, and it does not strip SQL
comments first. So a colon sitting in ordinary prose in a header comment is
enough to kill the statement it precedes with:

    A value is required for bind parameter 'free'

which is what happened to `0029_model_health_quarantine.sql` -- its header
mentioned openrouter's free-tier route with a colon before the word, and the
very first statement in the file died. Nothing after it could be recorded in
`schema_migrations` either, so the whole migration chain stalled.

What makes this worth a test rather than a comment: **psql does not
reproduce it.** Applying the same file by hand against a copy of the
production schema succeeds -- three times over, idempotently -- while the
real migration path fails immediately. Hand-testing the SQL gives a false
green, so the guard has to live here.

If a future migration genuinely needs a colon in SQL (a Postgres `::` cast
is fine and is excluded below), escape it as `\\:` or keep it out of prose.
"""
import pathlib
import re

import pytest

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / 'migrations'

#: The pattern SQLAlchemy's text() reads as a bind parameter: a single colon
#: followed by an identifier. `::` (a Postgres cast) and `\:` (an escaped
#: colon) are both legitimate and must not trip this.
_BIND_PARAM = re.compile(r'(?<![:\\]):[a-zA-Z_][a-zA-Z0-9_]*')


def _offenders(text: str) -> list[tuple[int, str]]:
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Skip the `::` cast form wholesale before scanning, so `x::text`
        # cannot leave a bare `:text` behind for the regex to catch.
        for match in _BIND_PARAM.finditer(line.replace('::', '  ')):
            hits.append((lineno, match.group(0)))
    return hits


def _migration_files() -> list[pathlib.Path]:
    return sorted(MIGRATIONS_DIR.glob('*.sql'))


def test_migrations_directory_is_found():
    """Guards the guard: a wrong path would make every test below vacuous."""
    files = _migration_files()
    assert files, f'no .sql files under {MIGRATIONS_DIR}'
    assert len(files) > 20, f'suspiciously few migrations found: {len(files)}'


@pytest.mark.parametrize('path', _migration_files(), ids=lambda p: p.name)
def test_no_accidental_bind_parameters(path):
    offenders = _offenders(path.read_text(encoding='utf-8'))
    assert not offenders, (
        f'{path.name} contains a colon followed by a word, which SQLAlchemy '
        f'text() will treat as a bind parameter and refuse:\n'
        + '\n'.join(f'  line {n}: {tok}' for n, tok in offenders)
        + '\nRephrase it (comments count) or escape the colon as \\:'
    )


def test_the_guard_actually_catches_the_original_bug():
    """A canary: without this, a broken regex would silently pass everything."""
    bad = "-- openrouter/*:free quota exhausted\nALTER TABLE t ADD COLUMN c text;"
    assert _offenders(bad) == [(1, ':free')]


def test_postgres_casts_and_escaped_colons_are_allowed():
    ok = "SELECT (value->>'pct')::numeric FROM app_setting WHERE k = 'a\\:b';"
    assert _offenders(ok) == []
