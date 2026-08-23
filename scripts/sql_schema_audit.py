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
cannot be EXPLAINed and is skipped. Any text() argument that is not a plain
string literal -- an f-string, a name, a concatenation -- is listed for manual
review, not silently ignored.

Run from anywhere on the prod box, before every backend deploy:
    python3 scripts/sql_schema_audit.py
Exit code 0 = all clean; 1 = at least one statement failed to plan.
"""
import ast
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
    """Yield (lineno, sql, kind) for every sqlalchemy.text() call.

    kind is 'const' when the argument is a plain string literal (the only
    shape we can EXPLAIN) and 'opaque' otherwise -- see the else branch.
    """
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        # `sqlalchemy.text(...)` or a bare imported `text(...)` -- and NOT
        # `char_draw.text(...)`, PIL's ImageDraw method in content.py, which a
        # bare attr=='text' match reports as SQL needing review. The opaque
        # branch below made that false positive visible; naming the receiver
        # keeps the manual list worth reading.
        f = node.func
        if isinstance(f, ast.Attribute):
            # Match on the receiver *expression*, not just a Name: embeddings.py
            # calls `__import__('sqlalchemy').text(...)`, whose receiver is a
            # Call. An `f.value.id in (...)` test silently dropped both of its
            # statements from the checked set.
            recv = ast.unparse(f.value)
            if f.attr != 'text' or ('sqlalchemy' not in recv and recv != 'sa'):
                continue
        elif not (isinstance(f, ast.Name) and f.id == 'text'):
            continue
        a = node.args[0]
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            yield node.lineno, a.value, 'const'
        else:
            # Anything not a plain literal -- an f-string, a module-level
            # constant passed by name, a `.format()`, a concatenation. This
            # branch used to be `elif JoinedStr` with no else, so every other
            # shape vanished without a trace: the one failure mode a net is
            # not allowed to have is a hole it does not report. Reported for
            # manual review, never counted as checked.
            yield node.lineno, '', 'opaque'


def prep(sql):
    """Replace :params with NULL so EXPLAIN can plan the statement.
    `IN :x` becomes `IN (NULL)` (bare NULL after IN is a syntax error);
    ::casts survive because the lookbehind refuses a second colon."""
    sql = re.sub(r'\bIN\s+:([a-zA-Z_][a-zA-Z0-9_]*)', 'IN (NULL)', sql)
    return re.sub(r'(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)', 'NULL', sql)


def main():
    checked = failed = 0
    opaque, skipped_ddl = [], []
    # rglob, not glob: services/*.py holds raw SQL in eight modules
    # (entitlements, free_tier, margin, model_resolver, rag, ...) and a
    # top-level-only glob silently skipped every one of them -- a hole in the
    # net this script exists to be. tests/ is excluded below.
    for path in sorted(BACKEND.rglob('*.py')):
        if 'tests' in path.parts or 'migrations' in path.parts:
            continue
        if path.name.startswith('test'):
            continue
        for lineno, sql, kind in extract(path):
            loc = f'{path.relative_to(BACKEND)}:{lineno}'
            if kind == 'opaque':
                opaque.append(loc)
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
          f'{len(skipped_ddl)} DDL skipped, {len(opaque)} not literals '
          f'(need manual review):')
    for loc in opaque:
        print(f'  manual: {loc}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
