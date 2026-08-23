#!/usr/bin/env python3
"""Reverse ORM<->DB audit: EXPLAIN every raw-SQL literal in backend/*.py
against the real Postgres schema.

Why this exists: the pytest suite mocks async_session, so no raw SQL is ever
executed by tests — a misspelled column or an illegal HAVING ships green and
only fails in production. Session 11 found two such 500s this way
(admin_users.py `charge_amount` vs the real `charged_amount`, and
admin_logical.py using HAVING on an ungrouped outer query).

EXPLAIN plans a statement without executing it, so this is read-only; every
statement additionally runs inside BEGIN/ROLLBACK. DDL (CREATE/ALTER/DROP)
cannot be EXPLAINed and is skipped. f-string SQL (dynamic column lists) is
listed for manual review, not silently ignored.

Run from anywhere on the prod box, before every backend deploy:
    python3 scripts/sql_schema_audit.py
Exit code 0 = all clean; 1 = at least one statement failed to plan.
"""
import ast
import json
import pathlib
import re
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1] / 'backend'
PSQL = ['docker', 'exec', '-i', 'sanjabai-sanjabai_pg-1',
        'psql', '-U', 'sanjabai', '-d', 'sanjabai',
        '-v', 'ON_ERROR_STOP=1', '-q', '-o', '/dev/null']
DDL = re.compile(r'^\s*(CREATE|ALTER|DROP|COMMENT)\b', re.I)


def extract(path):
    """Yield (lineno, sql, kind) for sqlalchemy.text(<literal>) calls."""
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if getattr(node.func, 'attr', getattr(node.func, 'id', '')) != 'text':
            continue
        a = node.args[0]
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            yield node.lineno, a.value, 'const'
        elif isinstance(a, ast.JoinedStr):
            yield node.lineno, '', 'fstring'


def prep(sql):
    """Replace :params with NULL so EXPLAIN can plan the statement.
    `IN :x` becomes `IN (NULL)` (bare NULL after IN is a syntax error);
    ::casts survive because the lookbehind refuses a second colon."""
    sql = re.sub(r'\bIN\s+:([a-zA-Z_][a-zA-Z0-9_]*)', 'IN (NULL)', sql)
    return re.sub(r'(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)', 'NULL', sql)


def main():
    checked = failed = 0
    skipped_fstrings, skipped_ddl = [], []
    for path in sorted(BACKEND.glob('*.py')):
        if path.name.startswith('test'):
            continue
        for lineno, sql, kind in extract(path):
            loc = f'{path.name}:{lineno}'
            if kind == 'fstring':
                skipped_fstrings.append(loc)
                continue
            s = sql.strip().rstrip(';')
            if not s:
                continue
            if DDL.match(s):
                skipped_ddl.append(loc)
                continue
            checked += 1
            script = f'BEGIN;\nEXPLAIN {prep(s)};\nROLLBACK;\n'
            r = subprocess.run(PSQL, input=script, capture_output=True, text=True)
            if r.returncode != 0:
                failed += 1
                first_err = next((l for l in r.stderr.splitlines() if 'ERROR' in l), r.stderr[:200])
                print(f'FAIL {loc}\n     {first_err.strip()}')
    print(f'{checked} statements planned, {failed} failed, '
          f'{len(skipped_ddl)} DDL skipped, {len(skipped_fstrings)} f-strings need manual review:')
    for loc in skipped_fstrings:
        print(f'  manual: {loc}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
