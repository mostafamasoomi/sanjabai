import { describe, it, expect } from 'vitest'

import { classifyFailures, type ErrorClass } from '../../app/admin/sections/BulkTestSummary'
import type { TestResult } from '../../app/admin/sections/BulkLiveTest'

/* Unit tests for classifyFailures — the pure grouping logic behind
 * BulkTestSummary.tsx. Mirrors the exact shapes backend/providers.py
 * (`probe_model`) produces: status_code set + `error === 'http_<code>'` for
 * any 4xx/5xx, status_code null + the exception's class name in `error` for
 * everything else (ReadTimeout, JSONDecodeError, ...). */

const ok = (): TestResult => ({ ok: true, latency_ms: 120, error: null, status_code: 200 })
const http = (code: number): TestResult => ({ ok: false, latency_ms: null, error: `http_${code}`, status_code: code })
const exc = (name: string): TestResult => ({ ok: false, latency_ms: null, error: name, status_code: null })

describe('classifyFailures', () => {
  it('returns every class, at zero, for an empty result map without throwing', () => {
    const groups = classifyFailures({})
    const classes: ErrorClass[] = ['gone', 'rateLimited', 'accessLost', 'noCredit', 'upstreamBroken', 'timeout', 'other']
    for (const c of classes) expect(groups[c]).toEqual([])
  })

  it('maps http_404 to gone', () => {
    const groups = classifyFailures({ m1: http(404) })
    expect(groups.gone).toEqual(['m1'])
  })

  it('maps http_429 to rateLimited', () => {
    const groups = classifyFailures({ m1: http(429) })
    expect(groups.rateLimited).toEqual(['m1'])
  })

  it('maps http_401 and http_403 to accessLost', () => {
    const groups = classifyFailures({ m1: http(401), m2: http(403) })
    expect(groups.accessLost.sort()).toEqual(['m1', 'm2'])
  })

  it('maps http_402 to noCredit', () => {
    const groups = classifyFailures({ m1: http(402) })
    expect(groups.noCredit).toEqual(['m1'])
  })

  it('maps 5xx (500, 502, 503) to upstreamBroken', () => {
    const groups = classifyFailures({ m1: http(500), m2: http(502), m3: http(503) })
    expect(groups.upstreamBroken.sort()).toEqual(['m1', 'm2', 'm3'])
  })

  it('maps a ReadTimeout exception (no status_code) to timeout', () => {
    const groups = classifyFailures({ m1: exc('ReadTimeout') })
    expect(groups.timeout).toEqual(['m1'])
  })

  it('lands an unlisted error (e.g. JSONDecodeError, http_400) in other rather than vanishing', () => {
    const groups = classifyFailures({ m1: exc('JSONDecodeError'), m2: http(400) })
    expect(groups.other.sort()).toEqual(['m1', 'm2'])
  })

  it('ignores ok results — no class receives a successful probe', () => {
    const groups = classifyFailures({ m1: ok(), m2: http(404) })
    expect(groups.gone).toEqual(['m2'])
    for (const c of Object.values(groups)) expect(c).not.toContain('m1')
  })
})
