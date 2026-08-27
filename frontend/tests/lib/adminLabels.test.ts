import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { t, ADMIN_CHROME } from '../../app/admin/adminLabels'
import { MODELS_TABS } from '../../app/admin/sections/modelsTabs'

/* Guards the bilingual admin nav: every label the shell renders must have a
 * real English sibling (not empty, not a copy-paste of the Persian string),
 * and the `t()` helper must default to Persian for anything that isn't the
 * literal 'en' -- matching LanguageToggle's own `getLang()` default.
 *
 * NAV_ITEMS lives inside AdminPanel.tsx, a 'use client' component that
 * statically imports `@/components/ui/Icon` and other app-alias modules
 * vitest's plain Node resolution can't follow (confirmed: `import { NAV_ITEMS }
 * from '../../app/admin/AdminPanel'` fails with "Cannot find package
 * '@/components/ui/Icon'"). Read the source as text instead and extract the
 * label/labelEn pairs by regex -- the same source-scan pattern already used
 * by modelsModuleWiring.test.ts and panel.test.ts for this file. */

const PANEL_SRC = readFileSync(join(__dirname, '../../app/admin/AdminPanel.tsx'), 'utf8')

/** Pulls every `{ key: '...', label: '...', labelEn: '...', icon: '...' }`
 *  entry out of the NAV_ITEMS array literal in AdminPanel.tsx. */
function extractNavItems(src: string): { key: string; label: string; labelEn: string }[] {
  const start = src.indexOf('const NAV_ITEMS')
  const arrayStart = src.indexOf('[', start)
  const arrayEnd = src.indexOf(']\n', arrayStart)
  const block = src.slice(arrayStart, arrayEnd)
  const entries: { key: string; label: string; labelEn: string }[] = []
  const re = /key:\s*'([^']*)',\s*label:\s*'([^']*)',\s*labelEn:\s*'([^']*)'/g
  let m: RegExpExecArray | null
  while ((m = re.exec(block))) {
    entries.push({ key: m[1], label: m[2], labelEn: m[3] })
  }
  return entries
}

const NAV_ITEMS = extractNavItems(PANEL_SRC)

describe('t() helper', () => {
  const pair = { label: 'داشبورد', labelEn: 'Dashboard' }

  it('returns the English label for lang "en"', () => {
    expect(t(pair, 'en')).toBe('Dashboard')
  })

  it('falls back to Persian for Persian, unknown, or absent lang', () => {
    expect(t(pair, 'fa')).toBe('داشبورد')
    expect(t(pair, 'de')).toBe('داشبورد')
    expect(t(pair, undefined)).toBe('داشبورد')
    expect(t(pair, null)).toBe('داشبورد')
  })
})

describe('NAV_ITEMS bilingual labels', () => {
  it('extracted all 14 nav entries from AdminPanel.tsx', () => {
    // A sanity floor on the regex itself: if AdminPanel.tsx's NAV_ITEMS
    // shape changes and the extractor silently matches zero entries, every
    // other assertion in this block would vacuously pass.
    //
    // Was 16 until the «امکانات» and «درباره ما» entries were removed: both
    // sections edited backend content that no public page has ever read
    // (the landing page's features come from the static
    // components/landing/content/features.ts), so they were orphaned admin
    // surface. This number is meant to be updated deliberately when a
    // section is added or removed -- that is the point of the floor.
    expect(NAV_ITEMS.length).toBe(14)
  })

  it('has a non-empty English label for every entry', () => {
    for (const item of NAV_ITEMS) {
      expect(item.labelEn.trim()).not.toBe('')
    }
  })

  it('never leaves the English label equal to the Persian one', () => {
    for (const item of NAV_ITEMS) {
      expect(item.labelEn).not.toBe(item.label)
    }
  })

  it('keeps a unique key per entry (labels are display-only)', () => {
    const keys = NAV_ITEMS.map((n) => n.key)
    expect(new Set(keys).size).toBe(keys.length)
  })
})

describe('MODELS_TABS bilingual labels', () => {
  it('has a non-empty English label for every entry', () => {
    for (const tab of MODELS_TABS) {
      expect(tab.labelEn.trim()).not.toBe('')
    }
  })

  it('never leaves the English label equal to the Persian one', () => {
    for (const tab of MODELS_TABS) {
      expect(tab.labelEn).not.toBe(tab.label)
    }
  })
})

describe('ADMIN_CHROME strings', () => {
  it('has a non-empty, distinct English string for every chrome entry', () => {
    for (const key of Object.keys(ADMIN_CHROME) as (keyof typeof ADMIN_CHROME)[]) {
      const entry = ADMIN_CHROME[key]
      expect(entry.labelEn.trim()).not.toBe('')
      expect(entry.labelEn).not.toBe(entry.label)
    }
  })
})

// ── Wiring: the labels must actually reach the screen ──────────────────────
//
// The dictionary passing its own tests proves nothing about rendering. The
// first pass of this feature added `labelEn` to MODELS_TABS and left
// ModelsModule.tsx rendering `t.label` — correct data, Persian sub-tabs.
// These scan the source, the same way modelsModuleWiring.test.ts does,
// because both components statically import files vitest's plain resolver
// cannot follow.

// Reuses the fs/path imports and the __dirname base at the top of this file.
const src = (p: string) => readFileSync(join(__dirname, '../../', p), 'utf8')

describe('bilingual labels are wired into the rendered chrome', () => {
  it('the models sub-tab bar renders through the label helper, not the raw Persian field', () => {
    const s = src('app/admin/sections/ModelsModule.tsx')
    expect(s).toContain('label(entry, lang)')
    // The old render. Its return would be Persian regardless of language.
    expect(s).not.toMatch(/\{\s*t\.label\s*\}/)
  })

  it('the sidebar nav renders through the label helper', () => {
    const s = src('app/admin/AdminPanel.tsx')
    expect(s).toMatch(/t\(\s*(item|n|nav)[^)]*,\s*lang\s*\)/)
  })

  it('the panel direction follows the language instead of being pinned to rtl', () => {
    const s = src('app/admin/AdminPanel.tsx')
    expect(s).toContain(`dir={lang === 'en' ? 'ltr' : 'rtl'}`)
    // The literal that used to override <html dir> for the whole panel.
    expect(s).not.toContain('className="admin-layout min-h-screen" dir="rtl"')
  })

  it('the language toggle is reachable from inside the panel', () => {
    expect(src('app/admin/AdminPanel.tsx')).toContain('<LanguageToggle />')
  })
})
