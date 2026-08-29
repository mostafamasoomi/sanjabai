import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { TEMPLATE_ORDER, templateApplyHref } from '@/components/templates/templates'
import { templateStrings } from '@/components/templates/templates.strings'

/* Completeness + product-contract + WIRING guard for the template gallery
 * (14 starter recipes on /guide), same discipline as productTour.test.ts and
 * guideContent.test.ts: content that is perfectly written but never rendered,
 * or an apply target that resolves nowhere, passes a type-check and helps
 * nobody. */

const ROOT = join(__dirname, '../..')
const APP_ROOT = join(ROOT, 'app')
const LANGS = ['fa', 'en'] as const
const DIGIT = /[0-9۰-۹]/

describe('template gallery data', () => {
  it('has at least 12 templates, all unique, matching a non-empty themed set', () => {
    expect(TEMPLATE_ORDER.length).toBeGreaterThanOrEqual(12)
    expect(new Set(TEMPLATE_ORDER).size).toBe(TEMPLATE_ORDER.length)

    const s = templateStrings('fa')
    const themes = new Set(TEMPLATE_ORDER.map((id) => s[id].theme))
    expect(themes.size).toBeGreaterThan(0)
    for (const theme of themes) {
      expect(typeof theme, `theme "${String(theme)}" must be a non-empty string`).toBe('string')
      expect((theme as string).trim().length).toBeGreaterThan(0)
    }
  })

  it('TEMPLATE_ORDER matches the keys of the strings dict exactly, both languages', () => {
    for (const lang of LANGS) {
      const s = templateStrings(lang)
      const keys = Object.keys(s).sort()
      const order = [...TEMPLATE_ORDER].sort()
      expect(keys).toEqual(order)
    }
  })

  it('every template is complete in both languages', () => {
    for (const lang of LANGS) {
      const s = templateStrings(lang)
      for (const id of TEMPLATE_ORDER) {
        const t = s[id]
        expect(t, `${lang}/${id} missing`).toBeTruthy()
        for (const field of ['title', 'tagline', 'applyLabel', 'combo'] as const) {
          expect(typeof t[field], `${lang}/${id}.${field} must be a string`).toBe('string')
          expect((t[field] as string).trim().length, `${lang}/${id}.${field} is empty`).toBeGreaterThan(0)
        }
        expect(Array.isArray(t.ingredients), `${lang}/${id}.ingredients must be an array`).toBe(true)
        expect(t.ingredients.length, `${lang}/${id}.ingredients must have >= 2 steps`).toBeGreaterThanOrEqual(2)
        for (const step of t.ingredients) {
          expect(typeof step).toBe('string')
          expect(step.trim().length).toBeGreaterThan(0)
        }
      }
    }
  })

  it('every navigate apply resolves to a real route under frontend/app/', () => {
    for (const lang of LANGS) {
      const s = templateStrings(lang)
      for (const id of TEMPLATE_ORDER) {
        const apply = s[id].apply
        if (apply.kind !== 'navigate') continue
        expect(apply.href.startsWith('/'), `${lang}/${id}.apply.href "${apply.href}" must start with "/"`).toBe(true)
        const pageFile = join(APP_ROOT, apply.href.slice(1), 'page.tsx')
        expect(existsSync(pageFile), `${lang}/${id}.apply.href -> "${apply.href}" has no app${apply.href}/page.tsx`).toBe(true)
      }
    }
  })

  it('every chat-prefill apply resolves under /chat with a non-empty decoded prompt', () => {
    for (const lang of LANGS) {
      const s = templateStrings(lang)
      for (const id of TEMPLATE_ORDER) {
        const t = s[id]
        if (t.apply.kind !== 'chat-prefill') continue
        const href = templateApplyHref(t)
        expect(href.startsWith('/chat?prompt='), `${lang}/${id} href "${href}" must start with /chat?prompt=`).toBe(true)
        const [pathAndQuery] = href.split('?')
        expect(pathAndQuery).toBe('/chat')
        const pageFile = join(APP_ROOT, 'chat', 'page.tsx')
        expect(existsSync(pageFile), `/chat has no app/chat/page.tsx`).toBe(true)
        const encoded = href.slice('/chat?prompt='.length)
        const decoded = decodeURIComponent(encoded)
        expect(decoded.trim().length, `${lang}/${id} decoded prompt is empty`).toBeGreaterThan(0)
        expect(decoded).toBe(t.apply.prompt)
      }
    }
  })

  it('contains no digit sequence anywhere in template copy, including raw prompts, both languages', () => {
    const offenders: string[] = []
    const scan = (label: string, value: string) => {
      if (DIGIT.test(value)) offenders.push(`${label}: "${value}"`)
    }
    for (const lang of LANGS) {
      const s = templateStrings(lang)
      for (const id of TEMPLATE_ORDER) {
        const t = s[id]
        scan(`${lang}.${id}.combo`, t.combo)
        scan(`${lang}.${id}.title`, t.title)
        scan(`${lang}.${id}.tagline`, t.tagline)
        scan(`${lang}.${id}.applyLabel`, t.applyLabel)
        t.ingredients.forEach((step, i) => scan(`${lang}.${id}.ingredients[${i}]`, step))
        if (t.apply.kind === 'chat-prefill') scan(`${lang}.${id}.apply.prompt`, t.apply.prompt)
        // apply.href (navigate) is a path, not copy -- intentionally excluded.
      }
    }
    expect(offenders).toEqual([])
  })
})

/* The gallery can be flawless while unreachable: if /guide stops importing
 * or mounting it, or the anchor the tour needs to spotlight it disappears,
 * every test above still passes and no user (and no tour step) can reach it.
 * Scanned by source, per the profile's "wiring is part of the work" rule. */
describe('the template gallery is actually wired up', () => {
  const guidePage = readFileSync(join(APP_ROOT, 'guide/page.tsx'), 'utf-8')
  const gallery = readFileSync(join(ROOT, 'components/templates/TemplateGallery.tsx'), 'utf-8')

  it('/guide imports TemplateGallery', () => {
    expect(guidePage).toMatch(/TemplateGallery/)
  })

  it('/guide mounts <TemplateGallery', () => {
    expect(guidePage).toMatch(/<TemplateGallery/)
  })

  it('TemplateGallery carries the guide.templates tour anchor', () => {
    expect(gallery).toMatch(/tourAnchor\('guide\.templates'\)/)
  })
})
