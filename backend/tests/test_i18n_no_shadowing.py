"""No endpoint may shadow the `err` helper with a local variable.

THE TRAP. Python binds a name assigned ANYWHERE in a function body as local
for the whole body. So this:

    from i18n import err

    async def handler(request):
        if not user:
            return err('...', '...', 401)      # <- UnboundLocalError
        text, err = await extract(file)        # <- makes `err` local

raises `UnboundLocalError: local variable 'err' referenced before assignment`
on the FIRST branch, even though the assignment is further down and may never
execute. Nothing catches it: the module imports fine, `python -c "import
chat_web"` is clean, every type checker is happy, and the endpoint 500s the
moment an unauthenticated request arrives.

It happened twice while converting 568 refusal sites to `err()` -- once in
auth/profile (`valid, err = validate_password(...)`) and once in
`chat_web.chat_with_file` (`text, err = await _extract_file_text(file)`),
which would have broken /chat-with-file for every signed-out caller.

This is a whole-tree AST scan rather than a test of one module, because the
next occurrence will be in whichever file adds an `err` local next.
"""
import ast
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _modules_importing_err():
    for path in sorted(BACKEND.rglob('*.py')):
        rel = path.relative_to(BACKEND)
        if rel.parts[0] in {'tests', 'migrations', '__pycache__'}:
            continue
        src = path.read_text(encoding='utf-8')
        if 'from i18n import' not in src:
            continue
        yield rel, src


def _shadowing_functions(src: str):
    """(name, lineno) for every function that both calls err() and binds it."""
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'err'
            for n in ast.walk(node)
        )
        binds = any(
            isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == 'err'
            for n in ast.walk(node)
        )
        if calls and binds:
            yield node.name, node.lineno


def test_the_trap_is_real_not_theoretical():
    """Pin the language behaviour this whole test file exists for."""
    def err(fa, en, status):
        return status

    def shadowed(authed):
        if not authed:
            return err('...', '...', 401)
        _text, err = ('t', '')   # noqa: F841 -- the point of the test
        return _text

    try:
        shadowed(False)
    except UnboundLocalError:
        return
    raise AssertionError('expected UnboundLocalError; Python scoping changed?')


def test_no_module_shadows_the_err_helper():
    offenders = [
        f'{rel}:{line} {name}()'
        for rel, src in _modules_importing_err()
        for name, line in _shadowing_functions(src)
    ]
    assert offenders == [], (
        'These functions call err() and also assign to `err`, so the call '
        'raises UnboundLocalError at runtime. Rename the local variable:\n  '
        + '\n  '.join(offenders)
    )


def test_no_module_binds_err_as_a_local_at_all():
    """The stricter rule, and the one worth keeping.

    A function that binds `err` but does not (yet) call it is harmless today
    and one line away from being fatal tomorrow -- the failure only appears at
    runtime, on whichever branch returns early. Costing nothing to avoid, the
    rule is simply: in a module that imports `err`, no local may be called
    `err`. `admin_packages.py` already followed this by hand, with a comment
    explaining why.
    """
    offenders = []
    for rel, src in _modules_importing_err():
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for n in ast.walk(node):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == 'err':
                    offenders.append(f'{rel}:{n.lineno} in {node.name}()')
    assert offenders == [], (
        'These bind `err` as a local in a module that imports the err() '
        'helper. Rename the local:\n  ' + '\n  '.join(sorted(set(offenders)))
    )


def test_the_scan_actually_reaches_the_backend():
    # A broken path would make the assertion above vacuously pass.
    seen = list(_modules_importing_err())
    assert len(seen) > 5, f'only {len(seen)} modules import err(); scan path wrong?'
