"""Tests for skills.py's _render_skill_prompt() -- the {{var}}/{var}
substitution used by POST /skills/{id}/use.

Regression coverage for the bug where the endpoint only handled the legacy
single-brace {var} form via a single `.replace('{' + name + '}', value)`
call. Since "{{name}}" contains "{name}" as a substring, that left the
outer braces stranded: "سلام {{name}}" rendered as "سلام {Bob}" instead of
"سلام Bob", even though frontend/app/skills/page.tsx's own placeholder text
tells authors to write {{variable_name}}.

No DB/session mocking needed -- _render_skill_prompt is a pure string
function, deliberately extracted from the endpoint for this reason.
"""
from skills import _render_skill_prompt


def test_double_brace_documented_form():
    # This is the exact case from the bug report.
    assert _render_skill_prompt('سلام {{name}}', {'name': 'Bob'}) == 'سلام Bob'


def test_old_single_brace_still_broken_without_the_fix():
    # Proves the bug was real: the OLD implementation (single-brace-only
    # replace) on the double-brace template leaves stray outer braces.
    old_rendered = 'سلام {{name}}'.replace('{name}', 'Bob')
    assert old_rendered == 'سلام {Bob}'


def test_single_brace_legacy_form():
    assert _render_skill_prompt('سلام {name}', {'name': 'Bob'}) == 'سلام Bob'


def test_both_forms_in_one_template():
    assert _render_skill_prompt('{{name}} and {name}', {'name': 'Bob'}) == 'Bob and Bob'


def test_variable_appearing_twice():
    assert _render_skill_prompt('{{name}}-{{name}}', {'name': 'Bob'}) == 'Bob-Bob'


def test_missing_variable_left_as_literal_text():
    # Existing behavior: a template placeholder with no matching entry in
    # `variables` is left untouched, not blanked or errored.
    assert _render_skill_prompt('سلام {{missing}}', {'name': 'Bob'}) == 'سلام {{missing}}'
    assert _render_skill_prompt('سلام {missing}', {'name': 'Bob'}) == 'سلام {missing}'


def test_value_containing_braces_is_not_rescanned():
    # str.replace() is a single non-recursive pass -- a substituted value
    # that itself looks like a placeholder must not be substituted again.
    assert _render_skill_prompt('val={{x}}', {'x': '{evil}'}) == 'val={evil}'
    assert _render_skill_prompt('val={{x}}', {'x': '{{evil}}'}) == 'val={{evil}}'


def test_no_variables_supplied_returns_template_unchanged():
    assert _render_skill_prompt('سلام {{name}}', {}) == 'سلام {{name}}'


def test_multiple_distinct_variables():
    tpl = 'سلام {{name}}، سن شما {age} است.'
    out = _render_skill_prompt(tpl, {'name': 'Bob', 'age': '30'})
    assert out == 'سلام Bob، سن شما 30 است.'
