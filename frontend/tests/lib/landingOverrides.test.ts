import { describe, it, expect, beforeEach, vi } from 'vitest'

import {
  LANDING_MODULE_KEYS,
  LANDING_SCHEMA,
  pathValue,
  setPath,
  applyModuleOverride,
  sanitizeLandingOverrides,
  type LandingOverridesMap,
} from '../../lib/landingOverrides'
import { STATIC_FIXTURES } from './landingOverrides.fixtures'

/**
 * Unit tests for lib/landingOverrides.ts (B-LAND phase 6).
 *
 * The load-bearing property is the first describe block below: with an
 * empty override store (the default -- an empty `landing_content` table),
 * merging must return each of the thirteen modules' resolved static content
 * completely unchanged. That is the only thing standing between this
 * feature and breaking the public landing page.
 *
 * Fixtures (today's real resolved content, copied verbatim from
 * components/landing/content/*.ts) live in ./landingOverrides.fixtures.ts,
 * split out to stay under the 500-line-per-file house rule.
 */

/* ═══════════════════════════════════════════════════════════════════════
   1. Empty override store ⇒ output identical to today's static content,
      for every one of the thirteen modules. The single most important
      property in this file.
   ═══════════════════════════════════════════════════════════════════════ */
describe('applyModuleOverride: empty store is a no-op for every module', () => {
  it('covers all thirteen module keys', () => {
    expect(Object.keys(STATIC_FIXTURES).sort()).toEqual([...LANDING_MODULE_KEYS].sort())
  })

  it.each(LANDING_MODULE_KEYS)('%s: fa output === static fa input (no overrides at all)', (key) => {
    const fixture = STATIC_FIXTURES[key]
    const result = applyModuleOverride(key, 'fa', fixture.fa, undefined)
    expect(result).toBe(fixture.fa) // same reference: nothing was cloned
    expect(result).toEqual(fixture.fa)
  })

  it.each(LANDING_MODULE_KEYS)('%s: en output === static en input (no overrides at all)', (key) => {
    const fixture = STATIC_FIXTURES[key]
    const result = applyModuleOverride(key, 'en', fixture.en, undefined)
    expect(result).toBe(fixture.en)
  })

  it.each(LANDING_MODULE_KEYS)('%s: fa output === static fa input (overrides = {})', (key) => {
    const fixture = STATIC_FIXTURES[key]
    const result = applyModuleOverride(key, 'fa', fixture.fa, {})
    expect(result).toBe(fixture.fa)
  })

  it.each(LANDING_MODULE_KEYS)('%s: an override present for OTHER modules only never touches this one', (key) => {
    const fixture = STATIC_FIXTURES[key]
    const otherKey = LANDING_MODULE_KEYS.find((k) => k !== key)!
    const overrides: LandingOverridesMap = { [otherKey]: { 'some.path': { fa: 'x', en: 'y' } } }
    const result = applyModuleOverride(key, 'fa', fixture.fa, overrides)
    expect(result).toBe(fixture.fa)
  })
})

/* ═══════════════════════════════════════════════════════════════════════
   2. A valid override is applied, per language, without disturbing
      sibling data.
   ═══════════════════════════════════════════════════════════════════════ */
describe('applyModuleOverride: a valid override applies per language', () => {
  it('replaces hero.rotation.0 for fa and en independently', () => {
    const overrides: LandingOverridesMap = {
      hero: { 'rotation.0': { fa: 'با یک اپلیکیشن', en: 'with one app' } },
    }
    const fa = STATIC_FIXTURES.hero.fa as { rotation: string[]; trust: string[] }
    const en = STATIC_FIXTURES.hero.en as { rotation: string[]; trust: string[] }

    const outFa = applyModuleOverride('hero', 'fa', fa, overrides) as typeof fa
    const outEn = applyModuleOverride('hero', 'en', en, overrides) as typeof en

    expect(outFa.rotation[0]).toBe('با یک اپلیکیشن')
    expect(outEn.rotation[0]).toBe('with one app')
    // Untouched sibling entries keep their static value...
    expect(outFa.rotation[1]).toBe(fa.rotation[1])
    // ...and an entirely untouched branch keeps the same object reference
    // (structural sharing -- setPath must not deep-clone the whole tree).
    expect(outFa.trust).toBe(fa.trust)
    // The original fixture itself is never mutated.
    expect(fa.rotation[0]).toBe('با یک کیف پول')
  })

  it('leaves a language untouched when only the other language was stored (contract rule 3)', () => {
    // A malformed/partial override missing `en` should never reach this far
    // in practice (sanitizeLandingOverrides requires both), but the merge
    // function itself must still degrade safely if it ever did.
    const overrides = { steps: { 'items.0.title': { fa: 'یک حساب بسازید' } } } as unknown as LandingOverridesMap
    const fa = STATIC_FIXTURES.steps.fa as { items: { title: string; desc: string }[] }
    const en = STATIC_FIXTURES.steps.en as { items: { title: string; desc: string }[] }
    const outFa = applyModuleOverride('steps', 'fa', fa, overrides) as typeof fa
    const outEn = applyModuleOverride('steps', 'en', en, overrides) as typeof en
    expect(outFa.items[0].title).toBe('یک حساب بسازید')
    expect(outEn.items[0].title).toBe(en.items[0].title) // unchanged, `en` half was missing
  })
})

/* ═══════════════════════════════════════════════════════════════════════
   3. A path outside the schema is ignored, no matter what the stored
      override contains.
   ═══════════════════════════════════════════════════════════════════════ */
describe('applyModuleOverride: paths outside LANDING_SCHEMA are ignored', () => {
  it('ignores an href, never in any module schema', () => {
    const overrides: LandingOverridesMap = {
      nav: { 'links.0.href': { fa: '/evil', en: '/evil' } },
    }
    const fa = STATIC_FIXTURES.nav.fa as { links: { label: string; href: string }[] }
    const out = applyModuleOverride('nav', 'fa', fa, overrides) as typeof fa
    expect(out).toBe(fa) // the only schema-known nav path is `links.N.label`; nothing applied
    expect(out.links[0].href).toBe(fa.links[0].href) // unchanged
  })

  it('ignores a path that does not exist in LANDING_SCHEMA at all', () => {
    const overrides: LandingOverridesMap = {
      steps: { 'items.0.nonexistentField': { fa: 'x', en: 'y' } },
    }
    const fa = STATIC_FIXTURES.steps.fa
    expect(applyModuleOverride('steps', 'fa', fa, overrides)).toBe(fa)
  })
})

/* ═══════════════════════════════════════════════════════════════════════
   4. Frozen (live-count) paths are ignored even when present in the
      response -- matching backend/landing_content.py's FROZEN_PATHS
      one-to-one, plus stats.items.0.label (stricter-than-backend).
   ═══════════════════════════════════════════════════════════════════════ */
describe('applyModuleOverride: frozen / live-count paths never apply', () => {
  it('stats.items.0.value (the live model count) is ignored, items.1.value still applies', () => {
    const overrides: LandingOverridesMap = {
      stats: {
        'items.0.value': { fa: '۹۹۹۹', en: '9999' }, // not in schema -> must be ignored
        'items.1.value': { fa: 'ریال', en: 'Rial' },
      },
    }
    const fa = STATIC_FIXTURES.stats.fa as { items: { value: string; label: string }[] }
    const out = applyModuleOverride('stats', 'fa', fa, overrides) as typeof fa
    expect(out.items[0].value).toBe(fa.items[0].value) // untouched
    expect(out.items[1].value).toBe('ریال') // applied
  })

  it('stats.items.0.label is ALSO excluded (stricter than backend FROZEN_PATHS)', () => {
    expect(LANDING_SCHEMA.stats).not.toContain('items.0.label')
    const overrides: LandingOverridesMap = { stats: { 'items.0.label': { fa: 'مدل رایگان', en: 'free models' } } }
    const fa = STATIC_FIXTURES.stats.fa
    expect(applyModuleOverride('stats', 'fa', fa, overrides)).toBe(fa)
  })

  it('comparison.rows.0.sanjabai (live count restated) is ignored, rows.0.label still applies', () => {
    const overrides: LandingOverridesMap = {
      comparison: {
        'rows.0.sanjabai': { fa: '۹۹۹۹ مدل، با یک حساب', en: '9999 models' },
        'rows.0.label': { fa: 'تعداد مدل‌ها', en: 'Model count' },
      },
    }
    const fa = STATIC_FIXTURES.comparison.fa as { rows: { label: string; sanjabai: string }[] }
    const out = applyModuleOverride('comparison', 'fa', fa, overrides) as typeof fa
    expect(out.rows[0].sanjabai).toBe(fa.rows[0].sanjabai)
    expect(out.rows[0].label).toBe('تعداد مدل‌ها')
  })

  it('pricing.columns.1.features.3 (live count restated) is ignored, features.0 still applies', () => {
    const overrides: LandingOverridesMap = {
      pricing: {
        'columns.1.features.3': { fa: 'دسترسی به همه‌ی مدل‌ها همیشه', en: 'always all models' },
        'columns.1.features.0': { fa: 'قیمت شفاف', en: 'transparent pricing' },
      },
    }
    const fa = STATIC_FIXTURES.pricing.fa as { columns: { features: string[] }[] }
    const out = applyModuleOverride('pricing', 'fa', fa, overrides) as typeof fa
    expect(out.columns[1].features[3]).toBe(fa.columns[1].features[3])
    expect(out.columns[1].features[0]).toBe('قیمت شفاف')
  })

  it('faq.items.0.a (live count restated) is ignored, items.1.a still applies', () => {
    const overrides: LandingOverridesMap = {
      faq: {
        'items.0.a': { fa: 'دروغ زنده', en: 'a live lie' },
        'items.1.a': { fa: 'پاسخ تازه', en: 'fresh answer' },
      },
    }
    const fa = STATIC_FIXTURES.faq.fa as { items: { q: string; a: string }[] }
    const out = applyModuleOverride('faq', 'fa', fa, overrides) as typeof fa
    expect(out.items[0].a).toBe(fa.items[0].a)
    expect(out.items[1].a).toBe('پاسخ تازه')
  })
})

/* ═══════════════════════════════════════════════════════════════════════
   5. Path utilities (pathValue / setPath) -- the walking rules shared with
      backend/landing_content.py's path_value.
   ═══════════════════════════════════════════════════════════════════════ */
describe('pathValue', () => {
  it('walks nested object keys', () => {
    expect(pathValue({ a: { b: { c: 'x' } } }, 'a.b.c')).toEqual({ found: true, value: 'x' })
  })
  it('walks array indices', () => {
    expect(pathValue({ items: [{ v: 1 }, { v: 2 }] }, 'items.1.v')).toEqual({ found: true, value: 2 })
  })
  it('reports missing object key as not found', () => {
    expect(pathValue({ a: 1 }, 'b')).toEqual({ found: false, value: undefined })
  })
  it('reports out-of-range array index as not found', () => {
    expect(pathValue({ items: [1, 2] }, 'items.5')).toEqual({ found: false, value: undefined })
  })
  it('reports a non-numeric segment against an array as not found', () => {
    expect(pathValue({ items: [1, 2] }, 'items.foo')).toEqual({ found: false, value: undefined })
  })
  it('reports indexing into a scalar as not found', () => {
    expect(pathValue({ a: 'x' }, 'a.b')).toEqual({ found: false, value: undefined })
  })
  it('never throws on garbage input', () => {
    expect(() => pathValue(null, 'a.b.c')).not.toThrow()
    expect(() => pathValue(undefined, 'a')).not.toThrow()
    expect(pathValue(null, 'a.b.c').found).toBe(false)
  })
})

describe('setPath', () => {
  it('replaces a nested object leaf without mutating the original', () => {
    const original = { a: { b: 'old' }, c: 'sibling' }
    const next = setPath(original, 'a.b', 'new')
    expect(next).toEqual({ a: { b: 'new' }, c: 'sibling' })
    expect(original.a.b).toBe('old')
  })
  it('replaces an array element without mutating the original array', () => {
    const original = { items: [{ v: 1 }, { v: 2 }] }
    const next = setPath(original, 'items.1.v', 99)
    expect(next.items[1].v).toBe(99)
    expect(original.items[1].v).toBe(2)
    expect(next.items[0]).toBe(original.items[0]) // structural sharing on the untouched sibling
  })
})

/* ═══════════════════════════════════════════════════════════════════════
   6. Response sanitation -- malformed/unknown shapes never survive.
   ═══════════════════════════════════════════════════════════════════════ */
describe('sanitizeLandingOverrides', () => {
  it('drops a non-object payload', () => {
    expect(sanitizeLandingOverrides(null)).toEqual({})
    expect(sanitizeLandingOverrides(undefined)).toEqual({})
    expect(sanitizeLandingOverrides('a string')).toEqual({})
    expect(sanitizeLandingOverrides([1, 2, 3])).toEqual({})
  })

  it('drops an unrecognised module key', () => {
    expect(sanitizeLandingOverrides({ notAModule: { 'a.b': { fa: 'x', en: 'y' } } })).toEqual({})
  })

  it('drops a path not present in LANDING_SCHEMA for that module', () => {
    expect(sanitizeLandingOverrides({ nav: { 'links.0.href': { fa: 'x', en: 'y' } } })).toEqual({})
  })

  it('drops a malformed pair (missing en, non-string, or a nested object)', () => {
    const result = sanitizeLandingOverrides({
      nav: {
        'links.0.label': { fa: 'برچسب' }, // missing en
        'links.1.label': { fa: 1, en: 'x' }, // fa not a string
        'links.2.label': 'not even an object',
      },
    })
    expect(result).toEqual({})
  })

  it('keeps a valid override and drops an invalid sibling in the same module', () => {
    const result = sanitizeLandingOverrides({
      nav: {
        'links.0.label': { fa: 'خانه', en: 'Home' },
        'links.99.label': { fa: 'x', en: 'y' }, // not in schema (only 0-3 exist)
      },
    })
    expect(result).toEqual({ nav: { 'links.0.label': { fa: 'خانه', en: 'Home' } } })
  })

  it('drops a frozen path even though it is not literally in LANDING_SCHEMA (defense in depth)', () => {
    const result = sanitizeLandingOverrides({ stats: { 'items.0.value': { fa: 'x', en: 'y' } } })
    expect(result).toEqual({})
  })
})

/* ═══════════════════════════════════════════════════════════════════════
   7. The loader: network error / 404 / malformed JSON all fail open to
      `{}`, and never throw -- this is what keeps the public landing page
      rendering today's static content when this feature is unreachable
      (true right now: the router isn't registered in app.py yet, so this
      is always a 404 in production today).
   ═══════════════════════════════════════════════════════════════════════ */
describe('loadLandingOverrides: fails open, never throws', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.resetModules() // fresh module-level cache per test
  })

  async function freshLoader() {
    const mod = await import('../../lib/landingOverrides')
    return mod.loadLandingOverrides
  }

  it('resolves to {} on a network error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const loadLandingOverrides = await freshLoader()
    await expect(loadLandingOverrides()).resolves.toEqual({})
  })

  it('resolves to {} on a 404 (today\'s production reality: router not yet mounted)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('not found', { status: 404 })))
    const loadLandingOverrides = await freshLoader()
    await expect(loadLandingOverrides()).resolves.toEqual({})
  })

  it('resolves to {} on malformed JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{not json', { status: 200 })))
    const loadLandingOverrides = await freshLoader()
    await expect(loadLandingOverrides()).resolves.toEqual({})
  })

  it('resolves to {} when the body has the wrong shape (no "data" field)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ oops: true }), { status: 200 })))
    const loadLandingOverrides = await freshLoader()
    await expect(loadLandingOverrides()).resolves.toEqual({})
  })

  it('resolves to a sanitized map on a valid 200 response', async () => {
    const body = { data: { nav: { 'links.0.label': { fa: 'خانه', en: 'Home' }, 'links.0.href': { fa: '/x', en: '/x' } } } }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 })))
    const loadLandingOverrides = await freshLoader()
    await expect(loadLandingOverrides()).resolves.toEqual({ nav: { 'links.0.label': { fa: 'خانه', en: 'Home' } } })
  })
})
