import { describe, it, expect } from 'vitest'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import {
  guideStrings,
  GUIDE_SECTION_ORDER,
  GUIDE_HINT_IDS,
} from '@/app/guide/guide.strings'

/* Completeness + product-contract guard for /guide and <Hint>, per the
 * P-GUIDE handoff packet (phase 8 پ-۴).
 *
 * Four things checked, matching the packet's acceptance list one-for-one:
 *   1. every section has all four question keys, non-empty, both languages
 *   2. every <Hint id> resolves to real text, and (inverted) no orphan key
 *      sits in the strings file's `hints` map without a declared id
 *   3. no Persian or Latin digit sequence anywhere in the guide COPY
 *   4. every "کجا شروع کنی" link target is a route that actually exists
 */

const APP_ROOT = join(__dirname, '../../app')
const LANGS = ['fa', 'en'] as const
const SECTION_FIELDS = ['title', 'what', 'when', 'cost', 'startLabel', 'startHref'] as const

describe('guide content completeness', () => {
  it('finds the six sections and the hint ids at all', () => {
    // A broken import/path would make every assertion below vacuously pass.
    expect(GUIDE_SECTION_ORDER.length).toBe(6)
    expect(GUIDE_HINT_IDS.length).toBeGreaterThanOrEqual(6)
    expect(GUIDE_HINT_IDS.length).toBeLessThanOrEqual(8)
  })

  it('every section has all four question fields, non-empty, in both languages', () => {
    for (const lang of LANGS) {
      const s = guideStrings(lang)
      for (const key of GUIDE_SECTION_ORDER) {
        const section = s.sections[key]
        expect(section, `${lang}/${key} is missing`).toBeTruthy()
        for (const field of SECTION_FIELDS) {
          const value = section[field]
          expect(typeof value, `${lang}/sections.${key}.${field} must be a string`).toBe('string')
          expect(value.trim().length, `${lang}/sections.${key}.${field} is empty`).toBeGreaterThan(0)
        }
      }
      // The four QUESTIONS themselves (چیست؟ / کِی به‌دردت می‌خورد؟ /
      // هزینه‌اش چقدر است؟ / کجا شروع کنی) are shared labels, not per-section
      // copy -- checked once, not per section.
      for (const [k, v] of Object.entries(s.questionLabels)) {
        expect(v.trim().length, `${lang}/questionLabels.${k} is empty`).toBeGreaterThan(0)
      }
    }
  })

  it('every <Hint id> in GUIDE_HINT_IDS resolves to real, non-empty text in both languages', () => {
    for (const lang of LANGS) {
      const s = guideStrings(lang)
      for (const id of GUIDE_HINT_IDS) {
        const text = s.hints[id]
        expect(typeof text, `${lang}/hints["${id}"] must be a string`).toBe('string')
        expect(text.trim().length, `${lang}/hints["${id}"] is empty`).toBeGreaterThan(0)
      }
    }
  })

  it('has no orphan hint key -- every key in `hints` is a declared GuideHintId', () => {
    const declared: readonly string[] = GUIDE_HINT_IDS
    for (const lang of LANGS) {
      const s = guideStrings(lang)
      for (const key of Object.keys(s.hints)) {
        expect(declared, `${lang}: "${key}" is in guide.strings.ts's hints map but not GUIDE_HINT_IDS`).toContain(key)
      }
    }
  })

  it('every "کجا شروع کنی" link target is a route that exists under frontend/app/', () => {
    const s = guideStrings('fa')
    for (const key of GUIDE_SECTION_ORDER) {
      const href = s.sections[key].startHref
      expect(href.startsWith('/'), `sections.${key}.startHref "${href}" must start with "/"`).toBe(true)
      const pageFile = join(APP_ROOT, href.slice(1), 'page.tsx')
      expect(existsSync(pageFile), `sections.${key}.startHref -> "${href}" has no app${href}/page.tsx`).toBe(true)
    }
  })

  // Product-contract rule (docs/product-contract.md, and see this project's
  // claim registry): no asserted number -- model count, speed, percentage,
  // toman figure -- may be hardcoded into user-facing copy. A stale "۲۳ مدل"
  // is exactly the bug this project already got burned by once, hunted
  // across eight files; this makes it a compile-time... no, a TEST-time
  // impossibility for THIS surface specifically.
  //
  // This scans the RUNTIME string values returned by guideStrings(), not the
  // .ts SOURCE text -- guide.strings.ts embeds ZWNJ as `‌`, which
  // contains the literal digits "200" in source but decodes to a single
  // non-digit character at runtme, so scanning source would false-positive
  // on our own typography. `startHref` is a path (e.g. "/skills"), not
  // copy, and is the only field intentionally excluded, per the packet:
  // "allow digits only inside URLs/paths if you must, and say so explicitly."
  it('contains no Persian or Latin digit sequence in any guide copy (startHref excepted)', () => {
    const DIGIT = /[0-9۰-۹]/
    const offenders: string[] = []
    const scan = (label: string, value: string) => {
      if (DIGIT.test(value)) offenders.push(`${label}: "${value}"`)
    }
    for (const lang of LANGS) {
      const s = guideStrings(lang)
      scan(`${lang}.pageTitle`, s.pageTitle)
      scan(`${lang}.pageSubtitle`, s.pageSubtitle)
      for (const [k, v] of Object.entries(s.questionLabels)) scan(`${lang}.questionLabels.${k}`, v)
      for (const key of GUIDE_SECTION_ORDER) {
        const section = s.sections[key]
        scan(`${lang}.sections.${key}.title`, section.title)
        scan(`${lang}.sections.${key}.what`, section.what)
        scan(`${lang}.sections.${key}.when`, section.when)
        scan(`${lang}.sections.${key}.cost`, section.cost)
        scan(`${lang}.sections.${key}.startLabel`, section.startLabel)
        // section.startHref intentionally NOT scanned.
      }
      for (const id of GUIDE_HINT_IDS) scan(`${lang}.hints["${id}"]`, s.hints[id])
    }
    expect(offenders).toEqual([])
  })
})

/* A hint that exists but is never rendered is dead weight, and a hint that
 * WAS rendered and then quietly dropped in a refactor is worse: the text
 * still passes every check above while no user can reach it. Neither shows
 * up in a type error, so the placement is scanned for directly.
 *
 * Added by the senior when wiring <Hint> into the six pages the P-GUIDE
 * packet recommended -- the packet could not place them itself, which is
 * exactly the moment this kind of link rots. */
describe('every declared hint is actually placed in a page', () => {
  const SCAN_ROOTS = [join(__dirname, '../../app'), join(__dirname, '../../components')]
  const SOURCE_EXT = /\.tsx$/

  const walk = (dir: string, out: string[] = []): string[] => {
    for (const entry of readdirSync(dir)) {
      if (entry === 'node_modules' || entry === '.next') continue
      const full = join(dir, entry)
      if (statSync(full).isDirectory()) walk(full, out)
      else if (SOURCE_EXT.test(entry)) out.push(full)
    }
    return out
  }

  const placed = (() => {
    const found = new Set<string>()
    for (const root of SCAN_ROOTS) {
      if (!existsSync(root)) continue
      for (const file of walk(root)) {
        // Hint.tsx itself declares the prop type; it is not a placement.
        if (file.endsWith(`${'/'}components${'/'}Hint.tsx`)) continue
        const src = readFileSync(file, 'utf-8')
        for (const m of src.matchAll(/<Hint\s+id="([^"]+)"/g)) found.add(m[1])
      }
    }
    return found
  })()

  it.each(GUIDE_HINT_IDS)('hint "%s" is rendered somewhere', (id) => {
    expect([...placed]).toContain(id)
  })

  it('renders no hint id that is not declared', () => {
    const undeclared = [...placed].filter((id) => !(GUIDE_HINT_IDS as readonly string[]).includes(id))
    expect(undeclared).toEqual([])
  })
})
