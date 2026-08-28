import { describe, it, expect } from 'vitest'

import { parseRouterProbeResponse, isProbeStale } from '../../app/admin/sections/routerProbeHelpers'

/**
 * Unit tests for the pure helpers behind RouterProbeSection.tsx.
 *
 * These live in a plain .ts sibling (routerProbeHelpers.ts) rather than the
 * component itself, for the same reason upstreamOverheadHelpers.ts's tests
 * do (see that file's own header): this repo's vitest has no jsdom, so a
 * component's JSX cannot be rendered here at all.
 *
 * The response shape below is pinned against the real
 * backend/services/router_probe.py (read directly, not guessed) — its module
 * docstring is the authority on the three-outcome table these tests pin:
 * ok:true is eligible, ok:false with a permanent reason (bad_shape,
 * no_discrimination, provider_not_configured, ...) is a bad router, and
 * ok:false with a `transient_*` reason says nothing about the model at all.
 */

describe('parseRouterProbeResponse — the three outcomes stay distinct', () => {
  const REAL_RESPONSE = {
    stored: {
      version: 1,
      measured_at: '2026-08-28T10:00:00+00:00',
      results: {
        'good/router-model': {
          ok: true,
          shape_ok: true,
          discriminates: true,
          at: '2026-08-28T10:00:00+00:00',
          samples: { greeting: 1, code: 4, reasoning: 6 },
        },
        'bad/no-discrimination': {
          ok: false,
          shape_ok: true,
          discriminates: false,
          reason: 'no_discrimination',
          at: '2026-08-28T10:00:00+00:00',
          samples: { greeting: 5, code: 5, reasoning: 5 },
        },
        'bad/wrong-shape': {
          ok: false,
          shape_ok: false,
          reason: 'bad_shape',
          at: '2026-08-28T10:00:00+00:00',
          sample_reply: 'I am happy to help! The answer is probably 3.',
        },
        'flaky/no-prior-success': {
          ok: false,
          reason: 'transient_http_429',
          at: '2026-08-28T10:00:00+00:00',
          retry_after: '2026-08-28T16:00:00+00:00',
        },
      },
    },
    storedUpdatedAt: '2026-08-28T10:00:05+00:00',
  }

  it('maps ok:true to eligible', () => {
    const result = parseRouterProbeResponse(REAL_RESPONSE)
    const row = result.rows.find((r) => r.publicId === 'good/router-model')!
    expect(row.state).toBe('eligible')
  })

  it('maps a permanent defect (no_discrimination) to ineligiblePermanent, distinct from transient', () => {
    const result = parseRouterProbeResponse(REAL_RESPONSE)
    const row = result.rows.find((r) => r.publicId === 'bad/no-discrimination')!
    expect(row.state).toBe('ineligiblePermanent')
    expect(row.state).not.toBe('ineligibleTransient')
  })

  it('maps a permanent defect (bad_shape) to ineligiblePermanent and keeps the sample reply', () => {
    const result = parseRouterProbeResponse(REAL_RESPONSE)
    const row = result.rows.find((r) => r.publicId === 'bad/wrong-shape')!
    expect(row.state).toBe('ineligiblePermanent')
    expect(row.reason).toBe('bad_shape')
    expect(row.sampleReply).toBe('I am happy to help! The answer is probably 3.')
  })

  it('maps a transient_* reason to ineligibleTransient, distinct from permanent, and surfaces retry_after', () => {
    const result = parseRouterProbeResponse(REAL_RESPONSE)
    const row = result.rows.find((r) => r.publicId === 'flaky/no-prior-success')!
    expect(row.state).toBe('ineligibleTransient')
    expect(row.state).not.toBe('ineligiblePermanent')
    expect(row.retryAfter).toBe('2026-08-28T16:00:00+00:00')
  })

  it('never collapses a transient result into the same state as a permanent one across a whole response', () => {
    const result = parseRouterProbeResponse(REAL_RESPONSE)
    const permanent = result.rows.filter((r) => r.state === 'ineligiblePermanent').map((r) => r.publicId)
    const transient = result.rows.filter((r) => r.state === 'ineligibleTransient').map((r) => r.publicId)
    expect(permanent).toEqual(expect.arrayContaining(['bad/no-discrimination', 'bad/wrong-shape']))
    expect(transient).toEqual(['flaky/no-prior-success'])
    expect(permanent).not.toEqual(expect.arrayContaining(['flaky/no-prior-success']))
  })

  it('a model that already proved itself (ok:true) stays eligible even if a later transient recheck left its old reason on the row', () => {
    // services/router_probe.py's `_merge_transient`: a transient failure on a
    // model that already had ok:true does NOT flip it to false -- it keeps
    // ok:true and only stamps `reason`/`retry_after` as a diagnostic. `ok`
    // must be checked first, unconditionally, or this reads as "not eligible
    // yet" for a model that has already proven itself.
    const response = {
      stored: {
        version: 1,
        measured_at: '2026-08-28T10:00:00+00:00',
        results: {
          'proven/flaked-this-run': {
            ok: true,
            shape_ok: true,
            discriminates: true,
            at: '2026-08-20T10:00:00+00:00',
            reason: 'transient_http_429',
            retry_after: '2026-08-28T16:00:00+00:00',
            transient_at: '2026-08-28T10:00:00+00:00',
            samples: { greeting: 1, code: 4, reasoning: 6 },
          },
        },
      },
      storedUpdatedAt: '2026-08-28T10:00:05+00:00',
    }
    const row = parseRouterProbeResponse(response).rows[0]
    expect(row.state).toBe('eligible')
  })
})

describe('isProbeStale — the 7-day boundary, tested on both sides', () => {
  const NOW = new Date('2026-08-28T12:00:00Z')
  const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000

  it('is not stale well within 7 days', () => {
    const measuredAt = new Date(NOW.getTime() - 24 * 60 * 60 * 1000).toISOString() // 1 day old
    expect(isProbeStale(measuredAt, NOW)).toBe(false)
  })

  it('is not stale exactly at the 7-day boundary', () => {
    const measuredAt = new Date(NOW.getTime() - SEVEN_DAYS_MS).toISOString() // exactly 7d old
    expect(isProbeStale(measuredAt, NOW)).toBe(false)
  })

  it('is stale one millisecond past the 7-day boundary', () => {
    const measuredAt = new Date(NOW.getTime() - SEVEN_DAYS_MS - 1).toISOString()
    expect(isProbeStale(measuredAt, NOW)).toBe(true)
  })

  it('is stale well past 7 days', () => {
    const measuredAt = new Date(NOW.getTime() - 10 * 24 * 60 * 60 * 1000).toISOString() // 10 days old
    expect(isProbeStale(measuredAt, NOW)).toBe(true)
  })

  it('treats a missing measured_at as stale', () => {
    expect(isProbeStale(null, NOW)).toBe(true)
  })

  it('treats an unparsable measured_at as stale', () => {
    expect(isProbeStale('not-a-date', NOW)).toBe(true)
  })
})

describe('parseRouterProbeResponse — the honest "never measured" state', () => {
  it('treats a missing stored value as never measured, not an empty table that reads as "all models failed"', () => {
    const result = parseRouterProbeResponse({ stored: { version: 1, measured_at: null, results: {} }, storedUpdatedAt: null })
    expect(result.neverMeasured).toBe(true)
    expect(result.rows).toEqual([])
  })

  it('treats a response missing `stored` entirely as never measured', () => {
    const result = parseRouterProbeResponse({ storedUpdatedAt: null })
    expect(result.neverMeasured).toBe(true)
    expect(result.rows).toEqual([])
  })

  it('does NOT report never-measured once at least one model has a real result, even if every one of them failed', () => {
    const result = parseRouterProbeResponse({
      stored: {
        version: 1,
        measured_at: '2026-08-28T10:00:00+00:00',
        results: { 'bad/one': { ok: false, reason: 'bad_shape', at: '2026-08-28T10:00:00+00:00' } },
      },
      storedUpdatedAt: '2026-08-28T10:00:05+00:00',
    })
    expect(result.neverMeasured).toBe(false)
    expect(result.rows).toHaveLength(1)
    expect(result.rows[0].state).toBe('ineligiblePermanent')
  })
})

describe('parseRouterProbeResponse — never leaks a provider or upstream name', () => {
  it('exposes only the public_id and the fields router_probe.py stores for a realistic payload', () => {
    const response = {
      stored: {
        version: 1,
        measured_at: '2026-08-28T10:00:00+00:00',
        results: {
          'litellm/cheap-router-candidate': {
            ok: false,
            reason: 'no_discrimination',
            at: '2026-08-28T10:00:00+00:00',
            samples: { greeting: 5, code: 5, reasoning: 5 },
          },
        },
      },
      storedUpdatedAt: '2026-08-28T10:00:05+00:00',
    }
    const row = parseRouterProbeResponse(response).rows[0]
    const rendered = JSON.stringify(row)
    // The stored key is a public_id (may itself look like "prefix/name", per
    // router_probe.py's module docstring) -- what must never appear is a
    // SEPARATE provider/upstream field the parser invented or fetched. The
    // row's own field set is the exhaustive list of what this helper is
    // allowed to expose.
    expect(Object.keys(row).sort()).toEqual(['at', 'publicId', 'reason', 'retryAfter', 'sampleReply', 'state'].sort())
    expect(rendered).not.toMatch(/upstream/i)
    expect(rendered).not.toMatch(/provider/i)
    expect(rendered).not.toMatch(/provider_model_id/i)
  })
})

describe('parseRouterProbeResponse — a malformed stored payload does not throw', () => {
  it('handles a non-object top-level response', () => {
    expect(() => parseRouterProbeResponse(null)).not.toThrow()
    expect(() => parseRouterProbeResponse(undefined)).not.toThrow()
    expect(() => parseRouterProbeResponse('oops')).not.toThrow()
    expect(() => parseRouterProbeResponse([1, 2, 3])).not.toThrow()
    expect(parseRouterProbeResponse('oops').neverMeasured).toBe(true)
  })

  it('handles stored.results not being a map', () => {
    const result = parseRouterProbeResponse({
      stored: { version: 1, measured_at: null, results: [{ ok: true }] },
      storedUpdatedAt: null,
    })
    expect(result.rows).toEqual([])
  })

  it('skips an individual malformed entry instead of throwing or fabricating a row', () => {
    const result = parseRouterProbeResponse({
      stored: {
        version: 1,
        measured_at: '2026-08-28T10:00:00+00:00',
        results: {
          'good/one': { ok: true, at: '2026-08-28T10:00:00+00:00' },
          'malformed/one': 'not an object at all',
          'also-malformed/two': null,
        },
      },
      storedUpdatedAt: null,
    })
    expect(result.rows.map((r) => r.publicId)).toEqual(['good/one'])
  })

  it('handles an entry with no reason/at/retry_after fields at all', () => {
    expect(() =>
      parseRouterProbeResponse({
        stored: { version: 1, measured_at: null, results: { 'bare/one': {} } },
        storedUpdatedAt: null,
      }),
    ).not.toThrow()
  })
})

/* ── Senior mount guard (2026-08-28) ───────────────────────────────────────
 *
 * The whole reason this section exists is that admin_smart_router.py shipped
 * with two routes and nothing that could call them. Building a section that
 * is itself never mounted would reproduce the same bug one layer up -- and
 * every test above would still pass. So the mount is asserted directly.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

describe('the router probe section is actually reachable', () => {
  const tabs = readFileSync(join(__dirname, '../../app/admin/sections/modelsTabs.ts'), 'utf-8')
  const modelsModule = readFileSync(join(__dirname, '../../app/admin/sections/ModelsModule.tsx'), 'utf-8')

  it('is a declared models sub-tab', () => {
    expect(tabs).toContain("key: 'router-probe'")
    expect(tabs).toMatch(/'router-probe'/)
  })

  it('is imported and rendered by ModelsModule', () => {
    expect(modelsModule).toContain("import('./RouterProbeSection')")
    expect(modelsModule).toContain("active === 'router-probe'")
  })
})
