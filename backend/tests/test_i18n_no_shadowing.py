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


def test_every_caller_of_err_imports_it():
    """A module that calls err() without importing it raises NameError on the
    branch that calls it -- and `python -c "import hermes_admin"` is perfectly
    happy, because the name is only resolved when the line runs. That is
    exactly how it shipped once during this conversion: twenty call sites were
    added by a batch edit that never touched the import block, and only a test
    that exercised one of those branches caught it.
    """
    offenders = []
    for path in sorted(BACKEND.rglob('*.py')):
        rel = path.relative_to(BACKEND)
        if rel.parts[0] in {'tests', 'migrations', '__pycache__'}:
            continue
        src = path.read_text(encoding='utf-8')
        tree = ast.parse(src)
        calls = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'err'
            for n in ast.walk(tree)
        )
        if not calls:
            continue
        resolvable = any(
            isinstance(n, ast.ImportFrom) and n.module == 'i18n'
            and any(a.name == 'err' for a in n.names)
            for n in ast.walk(tree)
        ) or any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'err'
            for n in ast.walk(tree)
        )
        if not resolvable:
            offenders.append(str(rel))
    assert offenders == [], (
        'These call err() but never import it; the call raises NameError at '
        'runtime:\n  ' + '\n  '.join(offenders)
    )


def test_no_module_uses_a_name_it_never_imported():
    """Catches the class of bug that only appears when a line runs.

    A module can reference `re`, `json` or any other name it forgot to import
    and still compile, still pass `python -c "import it"`, and still be flagged
    green by every type checker -- because the name is resolved at call time,
    on whichever branch touches it. It happened twice during this work: once
    when a batch edit added twenty `err()` calls without the import, and once
    when a helper was split into a new module and left `re` behind.

    This checks the small, high-traffic set of standard modules that are
    actually used inside function bodies here. It is deliberately not a full
    static analyser -- it is the cheap version that would have caught both.
    """
    WATCHED = ('re', 'json', 'math', 'asyncio', 'logging', 'time', 'os')
    offenders = []
    for path in sorted(BACKEND.rglob('*.py')):
        rel = path.relative_to(BACKEND)
        if rel.parts[0] in {'tests', 'migrations', '__pycache__', 'scripts'}:
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'))
        bound = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                bound.update((a.asname or a.name).split('.')[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                bound.update(a.asname or a.name for a in n.names)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                bound.add(n.id)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(n.name)
        for n in ast.walk(tree):
            if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                    and n.value.id in WATCHED and n.value.id not in bound):
                offenders.append(f'{rel}:{n.lineno} uses `{n.value.id}.` without importing it')
    assert offenders == [], (
        'These reference a module they never import; the line raises NameError '
        'when it runs:\n  ' + '\n  '.join(sorted(set(offenders)))
    )


def test_the_scan_actually_reaches_the_backend():
    # A broken path would make the assertion above vacuously pass.
    seen = list(_modules_importing_err())
    assert len(seen) > 5, f'only {len(seen)} modules import err(); scan path wrong?'
