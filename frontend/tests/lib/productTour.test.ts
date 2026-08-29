import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { productTourStrings, TOUR_STEP_ORDER } from '@/components/ProductTour.strings'
import { TOUR_OPEN_EVENT } from '@/components/ProductTour'

/* Completeness + product-contract + WIRING guard for the interactive product
 * tour (the launch-anytime multi-step popup). Same discipline as
 * guideContent.test.ts: content that is perfectly written but never rendered,
 * or a CTA that points at a dead route, passes a type-check and helps nobody.
 *
 * Checked here, one block each:
 *   1. the step order is non-trivial and every id resolves (a broken import
 *      would make the rest vacuously pass)
 *   2. every step is complete in BOTH languages (chapter/icon/title/body), and
 *      every CTA that exists has both a label and an href
 *   3. every ctaHref is a route that actually exists under frontend/app/
 *   4. no Persian or Latin digit sequence anywhere in the tour COPY
 *      (docs/product-contract.md: no hardcoded numeric claim in user copy)
 *   5. WIRING: the tour is actually mounted and reachable — AppShell renders
 *      it and opens it from a button, and /guide dispatches the open event.
 *      Delete any of that wiring and this block goes red.
 */

const ROOT = join(__dirname, '../..')
const APP_ROOT = join(ROOT, 'app')
const LANGS = ['fa', 'en'] as const

describe('product tour content completeness', () => {
  it('has a non-trivial ordered step list', () => {
    // The owner asked for workflow chapters covering all sections, not a
    // two-step stub — guard the floor so a gutted list is caught.
    expect(TOUR_STEP_ORDER.length).toBeGreaterThanOrEqual(8)
    expect(new Set(TOUR_STEP_ORDER).size).toBe(TOUR_STEP_ORDER.length) // no dupes
  })

  it('every step is complete in both languages', () => {
    for (const lang of LANGS) {
      const s = productTourStrings(lang)
      for (const id of TOUR_STEP_ORDER) {
        const step = s.steps[id]
        expect(step, `${lang}/${id} missing`).toBeTruthy()
        for (const field of ['chapter', 'icon', 'title', 'body'] as const) {
          expect(typeof step[field], `${lang}/${id}.${field} must be a string`).toBe('string')
          expect((step[field] as string).trim().length, `${lang}/${id}.${field} empty`).toBeGreaterThan(0)
        }
        // A CTA is optional (the welcome step has none), but a half-CTA — a
        // label with no destination, or vice versa — is a bug.
        expect(!!step.ctaHref, `${lang}/${id}: ctaLabel/ctaHref must both be set or both absent`).toBe(!!step.ctaLabel)
      }
    }
  })

  it('every ctaHref points at a real route under frontend/app/', () => {
    const s = productTourStrings('fa')
    for (const id of TOUR_STEP_ORDER) {
      const href = s.steps[id].ctaHref
      if (!href) continue
      expect(href.startsWith('/'), `${id}.ctaHref "${href}" must start with "/"`).toBe(true)
      const pageFile = join(APP_ROOT, href.slice(1), 'page.tsx')
      expect(existsSync(pageFile), `${id}.ctaHref -> "${href}" has no app${href}/page.tsx`).toBe(true)
    }
  })

  it('contains no digit sequence in any tour copy (ctaHref excepted)', () => {
    const DIGIT = /[0-9۰-۹]/
    const offenders: string[] = []
    for (const lang of LANGS) {
      const s = productTourStrings(lang)
      for (const id of TOUR_STEP_ORDER) {
        const step = s.steps[id]
        for (const field of ['chapter', 'title', 'body', 'combo'] as const) {
          const v = step[field]
          if (typeof v === 'string' && DIGIT.test(v)) offenders.push(`${lang}.${id}.${field}: "${v}"`)
        }
        // ctaHref (a path) intentionally not scanned; ctaLabel is copy.
        if (step.ctaLabel && DIGIT.test(step.ctaLabel)) offenders.push(`${lang}.${id}.ctaLabel: "${step.ctaLabel}"`)
      }
    }
    expect(offenders).toEqual([])
  })
})

/* The tour data can be flawless while the tour is unreachable: if AppShell
 * stops rendering it, or the launcher button loses its onClick, or /guide's
 * "start" button stops dispatching the event, every test above still passes
 * and no user can open it. This is the exact failure mode this project got
 * burned by (built, green, wired to nothing). So the wiring is asserted by
 * scanning source for the three connection points. */
describe('the tour is actually wired up', () => {
  const appShell = readFileSync(join(ROOT, 'components/AppShell.tsx'), 'utf-8')
  const guidePage = readFileSync(join(APP_ROOT, 'guide/page.tsx'), 'utf-8')

  it('AppShell imports the tour hook', () => {
    expect(appShell).toMatch(/useProductTour/)
  })

  it('AppShell renders the tour element', () => {
    // The rendered element is destructured as `ProductTour` and mounted as
    // `{ProductTour}` — both must be present.
    expect(appShell).toMatch(/\bProductTour\b/)
    expect(appShell).toMatch(/\{ProductTour\}/)
  })

  it('AppShell opens the tour from a control (openTour is called, not just imported)', () => {
    expect(appShell).toMatch(/openTour\(\)/)
  })

  it('/guide dispatches the tour open event', () => {
    // The page references the event via the imported TOUR_OPEN_EVENT symbol,
    // not the raw string literal — assert the symbol is imported AND dispatched
    // (both must be present for the button to actually open the tour). Import
    // the constant here too so a rename of the event breaks this test, not just
    // silently passes.
    expect(TOUR_OPEN_EVENT.length).toBeGreaterThan(0)
    expect(guidePage).toMatch(/TOUR_OPEN_EVENT/)
    expect(guidePage).toMatch(/dispatchEvent/)
  })
})
