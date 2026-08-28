import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  parseSmartFeaturePrefs,
  buildSmartFeaturesPayload,
} from '@/app/profile/components/SmartFeaturesSection'

/* P-UI-TOGGLES — mount guard + preference/payload logic for the two smart-
 * feature switches (`smart_router_enabled`, `compression_enabled`).
 *
 * `parseSmartFeaturePrefs`/`buildSmartFeaturesPayload` are exported from the
 * component itself (not reimplemented here) so these tests exercise the
 * exact logic the component runs, the same idiom as
 * tests/lib/referralSignupChain.test.ts importing `buildSignupBody` from
 * lib/auth.tsx -- this repo has no @testing-library/react to render the
 * component directly.
 */

const ROOT = join(__dirname, '../..')
const read = (p: string) => readFileSync(join(ROOT, p), 'utf8')

const PAGE_PATH = 'app/profile/page.tsx'
const PAGE = read(PAGE_PATH)
const STRINGS = read('app/profile/components/SmartFeaturesSection.strings.ts')

describe('mount guard: SmartFeaturesSection is actually mounted on the profile page', () => {
  // A previous session shipped three fully-tested features that ran for
  // nobody because the component was never mounted. This assertion is
  // useless unless it has actually been watched to go RED -- see the
  // mutation-protocol section of the handoff report for the paste of that
  // failure (mount line deleted, test run, restored).
  it('imports and renders <SmartFeaturesSection />', () => {
    expect(PAGE).toContain("import SmartFeaturesSection from './components/SmartFeaturesSection'")
    expect(PAGE).toMatch(/<SmartFeaturesSection\s*\/>/)
  })
})

describe('parseSmartFeaturePrefs: defaults', () => {
  it('defaults smart_router_enabled to true when the key is absent', () => {
    expect(parseSmartFeaturePrefs({}).smartRouterEnabled).toBe(true)
    expect(parseSmartFeaturePrefs(undefined).smartRouterEnabled).toBe(true)
    expect(parseSmartFeaturePrefs(null).smartRouterEnabled).toBe(true)
  })

  it('defaults compression_enabled to false when the key is absent', () => {
    expect(parseSmartFeaturePrefs({}).compressionEnabled).toBe(false)
    expect(parseSmartFeaturePrefs(undefined).compressionEnabled).toBe(false)
    expect(parseSmartFeaturePrefs(null).compressionEnabled).toBe(false)
  })
})

describe('parseSmartFeaturePrefs: an explicit false is not overridden by the default', () => {
  // The classic `value || default` bug: `false || true` evaluates to `true`,
  // silently reverting a user's saved "off" choice back to "on" every time
  // the profile page loads. This must use `??`, not `||`.
  it('keeps smart_router_enabled: false as false, even though the default is true', () => {
    expect(parseSmartFeaturePrefs({ smart_router_enabled: false }).smartRouterEnabled).toBe(false)
  })

  it('keeps compression_enabled: true as true, even though the default is false', () => {
    expect(parseSmartFeaturePrefs({ compression_enabled: true }).compressionEnabled).toBe(true)
  })
})

describe('buildSmartFeaturesPayload: toggling one key leaves the other untouched', () => {
  it('flipping the router on preserves whatever compression currently is', () => {
    const payload = buildSmartFeaturesPayload(true, false)
    expect(payload.preferences.smart_router_enabled).toBe(true)
    expect(payload.preferences.compression_enabled).toBe(false)
  })

  it('flipping compression on preserves whatever the router currently is', () => {
    const payload = buildSmartFeaturesPayload(false, true)
    expect(payload.preferences.smart_router_enabled).toBe(false)
    expect(payload.preferences.compression_enabled).toBe(true)
  })
})

describe('buildSmartFeaturesPayload: sends real booleans, never 1/"true"', () => {
  it('coerces truthy/falsy non-boolean inputs to actual booleans', () => {
    // @ts-expect-error -- deliberately passing non-boolean inputs to prove
    // the payload builder still normalises them, since the backend rejects
    // 1/"true" with a 400.
    const payload = buildSmartFeaturesPayload(1, 'true')
    expect(payload.preferences.smart_router_enabled).toBe(true)
    expect(typeof payload.preferences.smart_router_enabled).toBe('boolean')
    expect(typeof payload.preferences.compression_enabled).toBe('boolean')
  })

  it('never serialises to 1/0 or string "true"/"false"', () => {
    const payload = buildSmartFeaturesPayload(true, false)
    const json = JSON.stringify(payload)
    expect(json).toContain('"smart_router_enabled":true')
    expect(json).toContain('"compression_enabled":false')
    expect(json).not.toMatch(/"smart_router_enabled":(1|0|"true"|"false")/)
    expect(json).not.toMatch(/"compression_enabled":(1|0|"true"|"false")/)
  })
})

describe('both strings files carry Persian for every user-visible key', () => {
  // The page's own dictionary (AUTONOMY_LEVELS in ../types.ts) is the
  // pattern to match: every key that reaches the screen must have a
  // non-empty Persian value, no English leaking into the fa half.
  it('every FA string in SmartFeaturesSection.strings.ts is Persian, non-Latin text', () => {
    const faBlockMatch = STRINGS.match(/const FA = \{([\s\S]*?)\n\}/)
    expect(faBlockMatch, 'FA block not found in SmartFeaturesSection.strings.ts').toBeTruthy()
    const faBlock = faBlockMatch![1]
    // Extract each `key: 'value'` (values may contain escaped quotes; none
    // of this file's strings do, so a simple single-quote match is enough).
    const entries = [...faBlock.matchAll(/(\w+):\s*'([^']*)'/g)]
    expect(entries.length).toBeGreaterThanOrEqual(6) // title, intro, 2 labels, 2 descs, saveError
    // Format names with no Persian equivalent are allowed to appear verbatim
    // -- "JSON" is what the user sees in their own conversation, so
    // transliterating it would be less clear, not more Persian. Keep this
    // list tiny and specific: it is an exception to the rule, not a hole in
    // it. Anything not listed here still fails.
    const TECHNICAL_TERMS = /\b(JSON)\b/g
    const latinLetters = /[A-Za-z]/
    for (const [, key, value] of entries) {
      expect(value.length, `${key} is empty`).toBeGreaterThan(0)
      const stripped = value.replace(TECHNICAL_TERMS, '')
      expect(stripped, `${key} contains Latin letters, not pure Persian: "${value}"`).not.toMatch(latinLetters)
    }
  })

  it('mentions that the router is gated behind a not-yet-enabled admin flag (no overclaim)', () => {
    expect(STRINGS).toMatch(/فعال نشده/)
  })

  /* Anti-overclaim guard for compression, and the reason it is worded the way
     it is.

     Measured on the real library in the live container (2026-08-28): headroom
     protects user messages and recent code BY DESIGN and does nothing at all
     to ordinary prose. Persian prose compressed 0%. Only bulk JSON (-47%) and
     logs (-97%) actually shrink.

     So the honest copy has to admit that a normal conversation will see no
     difference. An earlier draft said older parts "are summarised so the
     conversation uses fewer tokens", which would have been a promise the
     product does not keep. These assertions pin the two halves of the honest
     version: what is never touched, and that a normal chat sees nothing. */
  it('does not overclaim compression: names what is never touched', () => {
    expect(STRINGS).toContain('پیام‌های خودتان هرگز دست نمی‌خورند')
  })

  it('does not overclaim compression: admits a normal chat sees no difference', () => {
    expect(STRINGS).toMatch(/هیچ تفاوتی حس نمی‌کنید/)
  })

  it('the EN block mirrors every FA key (typeof FA contract)', () => {
    expect(STRINGS).toContain('const EN: typeof FA')
  })
})
