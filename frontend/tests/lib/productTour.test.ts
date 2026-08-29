import { describe, it, expect } from 'vitest'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
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
    // two-step stub — guard the floor so a gutted list is caught. Bumped to 9
    // when the v2 anchored-spotlight tour added the `templates` step.
    expect(TOUR_STEP_ORDER.length).toBeGreaterThanOrEqual(9)
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

/* ═══════════════════════════════════════════════════════════════════════════
   Tour v2 — anchored spotlight. The engine navigates to a step's route,
   waits for its anchor to mount, and spotlights it in place of the plain
   centered popup; the centered card remains the mandatory fallback (never
   logged in, route bounced, element never appeared). Everything below guards
   that contract without depending on the concurrently-landing anchor tagging
   (Packet B) or the /guide templates anchor (Packet C) — see the
   anchor-uniqueness note further down for why existence isn't asserted here.
   ═══════════════════════════════════════════════════════════════════════════ */

describe('anchored steps carry a full, non-dead-end contract', () => {
  const s = productTourStrings('fa')

  it('every step with an anchor also has a route, and that route is a real page', () => {
    for (const id of TOUR_STEP_ORDER) {
      const step = s.steps[id]
      expect(!!step.route, `${id}: anchor set without route`).toBe(!!step.anchor)
      if (!step.route) continue
      expect(step.route.startsWith('/'), `${id}.route "${step.route}" must start with "/"`).toBe(true)
      const pageFile = join(APP_ROOT, step.route.slice(1), 'page.tsx')
      expect(existsSync(pageFile), `${id}.route -> "${step.route}" has no app${step.route}/page.tsx`).toBe(true)
    }
  })

  it('every anchored step still has ctaHref/ctaLabel — the fallback is never a dead end', () => {
    for (const id of TOUR_STEP_ORDER) {
      const step = s.steps[id]
      if (!step.anchor) continue
      expect(!!step.ctaHref, `${id}: anchored step missing ctaHref fallback`).toBe(true)
      expect(!!step.ctaLabel, `${id}: anchored step missing ctaLabel fallback`).toBe(true)
    }
  })

  it('the new templates step exists, targets /guide, and anchors guide.templates', () => {
    expect(TOUR_STEP_ORDER).toContain('templates')
    const step = s.steps.templates
    expect(step.route).toBe('/guide')
    expect(step.anchor).toBe('guide.templates')
  })
})

describe('the engine actually navigates and spotlights (not just centered popups)', () => {
  // A deleted `{ProductTour}` render or a deleted SpotlightOverlay import
  // both make the anchored path silently regress to the old centered-only
  // behaviour while every other test above stays green — so this is a
  // source-level mutation guard, same discipline as the wiring block above.
  const productTourSrc = readFileSync(join(ROOT, 'components/ProductTour.tsx'), 'utf-8')

  it('imports and renders SpotlightOverlay', () => {
    // Matched against the actual import path and JSX tag, not a loose
    // substring — the word "SpotlightOverlay" also appears in this file's
    // own doc comments, so a bare /SpotlightOverlay/ regex would stay green
    // even after the real import/render were deleted.
    expect(productTourSrc).toMatch(/from ['"]\.\/tour\/SpotlightOverlay['"]/)
    expect(productTourSrc).toMatch(/<SpotlightOverlay\b/)
  })

  it('navigates to an anchored step\'s route via router.push', () => {
    expect(productTourSrc).toMatch(/router\.push/)
  })
})

describe('every tourAnchor id is unique across the app (no double-spotlight)', () => {
  // Recursively collect every `tourAnchor('<id>')` literal under app/ and
  // components/. A duplicate would mean two elements share one anchor id, so
  // the spotlight could land on the wrong one depending on DOM order — this
  // does NOT assert every step's anchor exists at least once: the tagging
  // itself (Packet B) and the /guide templates anchor (Packet C) land
  // concurrently with this packet, so full existence is a senior-owned
  // integration check, not this packet's gate. Uniqueness (count <= 1) is
  // safe to assert regardless of landing order.
  function collectSourceFiles(dir: string, out: string[] = []): string[] {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry === '.next' || entry.startsWith('.')) continue
      const full = join(dir, entry)
      const st = statSync(full)
      if (st.isDirectory()) {
        collectSourceFiles(full, out)
      } else if (/\.(tsx|ts)$/.test(entry) && !entry.endsWith('.test.ts')) {
        out.push(full)
      }
    }
    return out
  }

  it('no tourAnchor id is spread onto more than one element', () => {
    const files = [
      ...collectSourceFiles(APP_ROOT),
      ...collectSourceFiles(join(ROOT, 'components')),
    ]
    const counts = new Map<string, number>()
    const CALL = /tourAnchor\(\s*['"]([^'"]+)['"]\s*\)/g
    for (const file of files) {
      // Strip comments before scanning — doc comments reference tourAnchor()
      // by example (anchors.ts's own JSDoc, TemplateGallery.tsx's header)
      // and are not a second call site.
      const src = readFileSync(file, 'utf-8')
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/\/\/.*$/gm, '')
      let m: RegExpExecArray | null
      while ((m = CALL.exec(src))) {
        const id = m[1]
        counts.set(id, (counts.get(id) || 0) + 1)
      }
    }
    const dupes = [...counts.entries()].filter(([, n]) => n > 1)
    expect(dupes, `duplicate tourAnchor ids: ${dupes.map(([id, n]) => `${id}×${n}`).join(', ')}`).toEqual([])
  })
})
