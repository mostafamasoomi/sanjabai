import { describe, it, expect } from 'vitest'

import { parseOverheadResponse, elapsedParts } from '../../app/admin/sections/upstreamOverheadHelpers'

/**
 * Unit tests for the pure helpers behind UpstreamOverheadSection.tsx.
 *
 * These live in a plain .ts sibling (upstreamOverheadHelpers.ts) rather than
 * the component itself: Vitest here has no vite-react-plugin registered and
 * tsconfig.json sets `"jsx": "preserve"` (correct for Next.js, which
 * transforms JSX itself via SWC), so Vitest's default esbuild transform
 * cannot parse any `.tsx` file at all.
 *
 * The response shape below is pinned against the real
 * `backend/admin_overhead.py` (read directly, not guessed) — an earlier
 * version of this file guessed at several possible envelopes before that
 * backend existed; the coordinator caught that it silently degraded to an
 * empty table on a shape mismatch, which looks identical on screen to "the
 * backend legitimately has nothing measured yet". parseOverheadResponse now
 * validates strictly and throws for anything that isn't the real contract —
 * these tests pin both halves: the real shape parses correctly, and a
 * malformed/changed one throws rather than quietly returning "no data".
 */

const REAL_RESPONSE = {
  stored: {
    version: 1,
    measured_at: '2026-08-23T11:38:00.123456',
    entries: {
      'ninerouter:cc': 2467,
      'litellm:mimo-v2.5-free': 8,
    },
    provider_default: {
      ninerouter: 2467,
      litellm: 8,
    },
    measurements: {
      'ninerouter:cc': {
        overhead: 2467,
        p1: 2475,
        p2: 4900,
        c1: 2,
        c2: 400,
        slope: 6.09,
        sample_model: 'ninerouter/cc/mimo-v2.5-free',
        measured_at: '2026-08-23T11:38:00.123456',
      },
      'litellm:mimo-v2.5-free': {
        overhead: 8,
        p1: 248,
        p2: 2648,
        c1: 2,
        c2: 400,
        slope: 6.03,
        sample_model: 'litellm/mimo-v2.5-free',
        measured_at: '2026-08-23T11:38:00.123456',
      },
    },
  },
  storedUpdatedAt: '2026-08-23T11:38:00.500000',
  perProviderStats7d: [
    { provider: 'ninerouter', requests7d: 412, totalTokensDiscounted7d: 168920 },
    { provider: 'litellm', requests7d: 90, totalTokensDiscounted7d: 720 },
  ],
}

const INERT_DEFAULT_RESPONSE = {
  stored: { version: 1, measured_at: null, entries: {}, provider_default: {} },
  storedUpdatedAt: null,
  perProviderStats7d: [],
}

describe('parseOverheadResponse — real contract', () => {
  it('flattens stored.entries into route rows carrying their own measurement', () => {
    const result = parseOverheadResponse(REAL_RESPONSE)
    expect(result.entries).toHaveLength(2)

    const nine = result.entries.find((r) => r.route_key === 'ninerouter:cc')!
    expect(nine.provider).toBe('ninerouter')
    expect(nine.overhead_tokens).toBe(2467)
    expect(nine.has_measurement).toBe(true)
    expect(nine.p1).toBe(2475)
    expect(nine.p2).toBe(4900)
    expect(nine.c1).toBe(2)
    expect(nine.c2).toBe(400)
    expect(nine.slope).toBeCloseTo(6.09)
    expect(nine.sample_model).toBe('ninerouter/cc/mimo-v2.5-free')
    expect(nine.measured_at).toBe('2026-08-23T11:38:00.123456')
  })

  it('keeps provider_default as a separate list, not merged into entries', () => {
    const result = parseOverheadResponse(REAL_RESPONSE)
    expect(result.providerDefaults).toEqual([
      { provider: 'ninerouter', overhead_tokens: 2467 },
      { provider: 'litellm', overhead_tokens: 8 },
    ])
  })

  it('keeps perProviderStats7d as its own per-provider list, not attached to route rows', () => {
    const result = parseOverheadResponse(REAL_RESPONSE)
    expect(result.providerStats).toEqual([
      { provider: 'ninerouter', requests_7d: 412, tokens_discounted_7d: 168920 },
      { provider: 'litellm', requests_7d: 90, tokens_discounted_7d: 720 },
    ])
    // Route rows themselves must not carry a stats column that implies a
    // per-route count the data doesn't have.
    expect(result.entries[0]).not.toHaveProperty('requests_7d')
  })

  it('reads measured_at and storedUpdatedAt from their real top-level locations', () => {
    const result = parseOverheadResponse(REAL_RESPONSE)
    expect(result.measuredAt).toBe('2026-08-23T11:38:00.123456')
    expect(result.storedUpdatedAt).toBe('2026-08-23T11:38:00.500000')
    expect(result.isInert).toBe(false)
  })

  it('handles slope: null (the c1 == c2 guard in admin_overhead.py)', () => {
    const withNullSlope = {
      stored: {
        version: 1,
        measured_at: '2026-08-23T00:00:00',
        entries: { 'ninerouter:x': 0 },
        provider_default: {},
        measurements: {
          'ninerouter:x': { overhead: 0, p1: 5, p2: 5, c1: 2, c2: 2, slope: null, sample_model: 'x', measured_at: '2026-08-23T00:00:00' },
        },
      },
      storedUpdatedAt: null,
      perProviderStats7d: [],
    }
    expect(parseOverheadResponse(withNullSlope).entries[0].slope).toBeNull()
  })
})

describe('parseOverheadResponse — the shipped inert default', () => {
  it('treats empty entries + null measured_at as inert, not an error', () => {
    const result = parseOverheadResponse(INERT_DEFAULT_RESPONSE)
    expect(result.isInert).toBe(true)
    expect(result.entries).toEqual([])
    expect(result.providerDefaults).toEqual([])
  })

  it('handles a stored object with no `measurements` key at all (the real never-measured default omits it)', () => {
    const noMeasurementsKey = {
      stored: { version: 1, measured_at: null, entries: {}, provider_default: {} },
      storedUpdatedAt: null,
      perProviderStats7d: [],
    }
    expect(() => parseOverheadResponse(noMeasurementsKey)).not.toThrow()
  })
})

describe('parseOverheadResponse — must fail visibly on a malformed/unexpected response', () => {
  it('throws when `stored` is missing entirely, rather than treating it as "no data"', () => {
    expect(() => parseOverheadResponse({ storedUpdatedAt: null, perProviderStats7d: [] })).toThrow(/stored/)
  })

  it('throws when the top-level response is not an object', () => {
    expect(() => parseOverheadResponse(null)).toThrow()
    expect(() => parseOverheadResponse([1, 2, 3])).toThrow()
    expect(() => parseOverheadResponse('oops')).toThrow()
  })

  it('throws when stored.entries is not a map (e.g. an old guessed array shape)', () => {
    expect(() =>
      parseOverheadResponse({
        stored: { version: 1, measured_at: null, entries: [{ route: 'ninerouter' }], provider_default: {} },
        storedUpdatedAt: null,
        perProviderStats7d: [],
      }),
    ).toThrow(/entries/)
  })

  it('throws when stored.provider_default is missing', () => {
    expect(() =>
      parseOverheadResponse({
        stored: { version: 1, measured_at: null, entries: {} },
        storedUpdatedAt: null,
        perProviderStats7d: [],
      }),
    ).toThrow(/provider_default/)
  })

  it('throws when an entry overhead value is not a number', () => {
    expect(() =>
      parseOverheadResponse({
        stored: { version: 1, measured_at: null, entries: { 'ninerouter:cc': 'a lot' }, provider_default: {} },
        storedUpdatedAt: null,
        perProviderStats7d: [],
      }),
    ).toThrow()
  })

  it('never silently returns an empty table for a response shaped like the old three-shape guess', () => {
    // What the pre-contract normalizer used to accept: a bare route-keyed
    // map with no `stored` wrapper at all. The real backend never sends
    // this — it must be rejected, not parsed into an empty (or worse,
    // wrong) table.
    const oldGuessedShape = {
      ninerouter: { overhead: 2467, p1: 14, p2: 2475, c1: 2, c2: 2, slope: 1.0, sample_model: 'x' },
    }
    expect(() => parseOverheadResponse(oldGuessedShape)).toThrow(/stored/)
  })
})

describe('elapsedParts', () => {
  it('splits sub-minute durations as 0 minutes', () => {
    expect(elapsedParts(42_000)).toEqual({ minutes: 0, seconds: 42 })
  })

  it('lands exactly on a minute boundary without a stray leftover second', () => {
    expect(elapsedParts(60_000)).toEqual({ minutes: 1, seconds: 0 })
  })

  it('splits minutes and seconds past a minute', () => {
    expect(elapsedParts(65_000)).toEqual({ minutes: 1, seconds: 5 })
  })

  it('clamps negative durations to zero instead of going negative', () => {
    expect(elapsedParts(-500)).toEqual({ minutes: 0, seconds: 0 })
  })
})
