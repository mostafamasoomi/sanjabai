import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

/* The completeness guard for the admin panel's translation.
 *
 * `EN: typeof FA` in each *.strings.ts makes tsc catch a key that exists in
 * one language and not the other. It cannot catch the other half of the job:
 * a Persian literal still sitting in a component, never routed through a
 * dictionary at all. That is exactly how a "bilingual" panel ends up being a
 * translated menu on top of a Persian body -- everything compiles, every test
 * passes, and the English reader gets Persian.
 *
 * So this scans the panel's own source for Persian outside the dictionaries.
 * The dictionaries (*.strings.ts) are where Persian belongs; comments are
 * prose and are stripped; and ALLOWED lists the handful of places where a
 * Persian literal is correct on purpose, each with the reason.
 */

const ADMIN = join(__dirname, '../../app/admin')
const PERSIAN = /[؀-ۿ]/

/** Files that may legitimately hold a Persian literal in code. */
const ALLOWED = new Set<string>([
  // The shell's own bilingual tables: Persian and English side by side in
  // `{ label, labelEn }` pairs, read through t(). Not untranslated -- the
  // other shape of the same thing.
  'AdminPanel.tsx',
  'adminLabels.ts',
  'sections/modelsTabs.ts',
  'sections/availability.ts',
  // Both branches of a language ternary live here in full.
  'components/AdminCharts.tsx',
  'apiError.ts',
  'sections/ModelsModule.tsx',
])

function walk(dir: string, base = ''): [string, string][] {
  const out: [string, string][] = []
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const rel = base ? `${base}/${e.name}` : e.name
    if (e.isDirectory()) out.push(...walk(join(dir, e.name), rel))
    else if (/\.tsx?$/.test(e.name)) out.push([rel, readFileSync(join(dir, e.name), 'utf8')])
  }
  return out
}

/** Source with comments and JSX comment expressions removed. */
function stripComments(src: string): string {
  return src
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^[ \t]*\/\/.*$/gm, '')
}

describe('admin panel translation coverage', () => {
  const files = walk(ADMIN)

  it('finds the admin source at all', () => {
    // A broken path would make every assertion below vacuously pass.
    expect(files.length).toBeGreaterThan(30)
  })

  it('keeps Persian literals in dictionaries, not in components', () => {
    const offenders: string[] = []
    for (const [rel, src] of files) {
      if (rel.endsWith('.strings.ts') || rel.endsWith('.strings.more.ts')) continue
      if (ALLOWED.has(rel)) continue
      for (const line of stripComments(src).split('\n')) {
        if (PERSIAN.test(line)) offenders.push(`${rel}: ${line.trim().slice(0, 90)}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('every dictionary annotates EN with typeof FA and leaves FA un-const', () => {
    const dicts = files.filter(([rel]) => rel.endsWith('.strings.ts') || rel.endsWith('.strings.more.ts'))
    expect(dicts.length).toBeGreaterThan(0)
    for (const [rel, src] of dicts) {
      const body = stripComments(src)
      // Without this annotation a missing English key is silent.
      expect(body, `${rel} must annotate EN as typeof FA`).toMatch(/const\s+EN\s*:\s*typeof\s+FA\b/)
      // `as const` on FA turns every value into a literal type, which makes
      // the annotation above unsatisfiable by any real translation.
      expect(body, `${rel} must not mark FA as const`).not.toMatch(/const\s+FA\s*=\s*\{[\s\S]*?\}\s*as\s+const/)
      expect(body, `${rel} must export through dict()`).toMatch(/dict\(\s*FA\s*,\s*EN\s*\)/)
    }
  })

  it('no section pins dir="rtl" now that section bodies are translated', () => {
    // An RTL box full of English text puts labels, icons and table columns on
    // the wrong side. The panel root follows the language; sections inherit.
    const offenders: string[] = []
    for (const [rel, src] of files) {
      for (const line of stripComments(src).split('\n')) {
        if (/dir="rtl"/.test(line)) offenders.push(`${rel}: ${line.trim().slice(0, 90)}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('no admin component formats numbers with the Persian-only helpers', () => {
    // faNum/faPrice always emit Persian digits and «تومان». Left in place they
    // render `۱٬۱۵۳ models` -- half-translated. fmt(lang) is the way.
    const offenders: string[] = []
    for (const [rel, src] of files) {
      if (ALLOWED.has(rel)) continue
      const body = stripComments(src)
      for (const helper of ['faNum', 'faPrice', 'faCompact', 'faPercent', 'faDate', 'faTime']) {
        if (new RegExp(`\\b${helper}\\s*\\(`).test(body)) offenders.push(`${rel}: ${helper}(`)
      }
    }
    expect(offenders).toEqual([])
  })
})
