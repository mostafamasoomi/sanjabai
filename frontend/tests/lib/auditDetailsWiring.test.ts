import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

/* The call-site guard, not the helper.
 *
 * auditDetails.test.ts proves formatAuditDetails() handles a jsonb object.
 * It does NOT prove SecuritySection actually calls it -- I reverted line 271
 * to the original `{log.details || '—'}` and every one of those 11 tests
 * stayed green while the panel crashed exactly as before.
 *
 * The crash was real: audit_logs.details is jsonb, the frontend typed it
 * `string | null`, and rendering it straight into JSX threw React error #31
 * ("Objects are not valid as a React child") the moment a row carried
 * {"availability":"disabled"}. That dropped the whole admin panel into its
 * error boundary.
 *
 * So this scans the source of the component that renders the cell. Same
 * pattern the backend uses for controls a mocked unit test cannot reach --
 * see tests/test_credit_paths.py and test_watchdog_settings.py.
 */

const SECTION = join(__dirname, '../../app/admin/sections/SecuritySection.tsx')

describe('audit-log details wiring', () => {
  const src = readFileSync(SECTION, 'utf8')

  it('renders the details cell through formatAuditDetails', () => {
    expect(src).toContain('formatAuditDetails(log.details)')
  })

  it('imports the formatter it renders with', () => {
    expect(src).toMatch(/import\s*\{[^}]*formatAuditDetails[^}]*\}\s*from/)
  })

  it('never renders log.details straight into JSX', () => {
    // Comments are stripped first: this file documents the old crashing
    // expression `{log.details}` in its header comment on purpose, and a
    // naive scan flags that prose as if it were code.
    const code = src
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/(^|[^:])\/\/.*$/gm, '$1')
    // `{log.details}` or `{log.details || '...'}` -- the exact shape that
    // crashed. A cast does not help: the value is an object at runtime.
    expect(code).not.toMatch(/\{\s*(\(\s*)?log\.details\b(?![\w(])/)
  })
})
