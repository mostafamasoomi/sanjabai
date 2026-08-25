import { describe, it, expect } from 'vitest'

import { formatAuditDetails } from '../../lib/auditDetails'

/**
 * Unit tests for formatAuditDetails (lib/auditDetails.ts).
 *
 * The bug: `audit_logs.details` is jsonb, so GET /api/admin/audit-logs can
 * hand back a real object (e.g. {"availability":"disabled"}), not the
 * `string | null` the frontend type claimed. Rendering it directly with
 * `{log.details}` threw React error #31 ("Objects are not valid as a React
 * child") and dropped the whole admin panel into its error boundary the
 * moment a row like that appeared -- which is exactly what a model-toggle
 * audit entry did in production.
 *
 * These tests pin that every shape jsonb can produce renders as readable
 * text instead of crashing, and that the one shape actually seen in
 * production ({"availability":"disabled"}) reads as "availability: disabled"
 * rather than "[object Object]".
 */

describe('formatAuditDetails', () => {
  it('renders null/undefined as the em dash placeholder', () => {
    expect(formatAuditDetails(null)).toBe('—')
    expect(formatAuditDetails(undefined)).toBe('—')
  })

  it('renders a plain string as-is', () => {
    expect(formatAuditDetails('توضیح متنی')).toBe('توضیح متنی')
  })

  it('renders an empty string as the em dash placeholder', () => {
    expect(formatAuditDetails('')).toBe('—')
  })

  it('renders numbers and booleans as text', () => {
    expect(formatAuditDetails(42)).toBe('42')
    expect(formatAuditDetails(true)).toBe('true')
    expect(formatAuditDetails(false)).toBe('false')
  })

  // ── The exact production payload that crashed the panel ────────────────
  it('renders the real {"availability":"disabled"} row as readable key: value text', () => {
    expect(formatAuditDetails({ availability: 'disabled' })).toBe('availability: disabled')
  })

  it('renders a multi-key object as key: value pairs joined with a Persian comma', () => {
    expect(formatAuditDetails({ from: 'active', to: 'disabled' })).toBe('from: active، to: disabled')
  })

  it('renders an empty object as the em dash placeholder', () => {
    expect(formatAuditDetails({})).toBe('—')
  })

  it('renders an array of primitives joined with a Persian comma', () => {
    expect(formatAuditDetails(['a', 'b', 3])).toBe('a، b، 3')
  })

  it('renders an empty array as the em dash placeholder', () => {
    expect(formatAuditDetails([])).toBe('—')
  })

  it('falls back to JSON for a nested value instead of "[object Object]"', () => {
    expect(formatAuditDetails({ meta: { nested: true } })).toBe('meta: {"nested":true}')
  })

  it('never returns the raw "[object Object]" string for any object input', () => {
    const inputs: unknown[] = [
      { availability: 'disabled' },
      { a: 1, b: { c: 2 } },
      [{ x: 1 }],
      {},
    ]
    for (const input of inputs) {
      expect(formatAuditDetails(input)).not.toContain('[object Object]')
    }
  })
})
