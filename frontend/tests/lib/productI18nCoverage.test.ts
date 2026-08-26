import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

/* The completeness gate for the USER-FACING app and the landing page.
 *
 * The sibling guard, adminI18nCoverage.test.ts, does the same job for
 * app/admin. This one covers everything else, and it exists for the same
 * reason: `EN: typeof FA` makes tsc catch a key present in one language and
 * missing in the other, but nothing catches a Persian literal that never
 * entered a dictionary at all. That is precisely how a product ends up with a
 * language toggle that flips `dir` and changes not one word — everything
 * compiles, every test passes, and the English reader gets Persian.
 *
 * ALLOWED below is not a list of things nobody got round to. Each entry is a
 * place where a Persian literal in code is the correct answer, with the
 * reason. Adding to it should feel expensive.
 */

const ROOT = join(__dirname, '../..')
const PERSIAN = /[؀-ۿ]/

const ALLOWED = new Map<string, string>([
  // Server-rendered <head>. Next.js metadata is resolved on the server, once,
  // with no access to a per-viewer language; a Persian-first product's SEO
  // description and keywords belong in Persian. Not toggleable by design.
  ['app/layout.tsx', 'SEO metadata, server-resolved'],
  ['app/page.tsx', 'SEO metadata + JSON-LD FAQPage schema, server-resolved'],

  // Prompt LIBRARY content. The template text is what a Persian user sends to
  // a model; translating it would change the artefact, not its label. The UI
  // around it is translated.
  ['app/prompts/page.tsx', 'prompt template bodies are content, not chrome'],

  // Bilingual lookup tables: both languages present side by side, read
  // through a (raw, lang) helper. Same shape as admin/sections/availability.ts.
  ['app/skills/types.tsx', 'bilingual category table'],
  ['lib/useCatalog.ts', 'bilingual price-band table'],
  ['lib/claims.ts', 'claim registry carries copyFa and copyEn together'],

  // Code SAMPLES. The Persian is the message body inside a curl/python/js
  // snippet — it demonstrates a Persian-first API, and an English reader is
  // meant to see exactly the request a real caller sends. Verified line by
  // line before granting these two.
  ['app/api-keys/page.tsx', 'Persian message body inside a code sample'],
  ['app/developer/constants.ts', 'Persian message bodies inside CODE_EXAMPLES'],

  // Bilingual RECORD tables: each row carries its own `_fa` and `_en` fields
  // rather than the file holding two objects. Same guarantee by a different
  // shape — both languages are present and adjacent.
  ['app/profile/types.ts', 'TIMEZONES / AUTONOMY_LEVELS carry label_fa + label_en'],
  ['app/onboarding/constants.ts', 'GOALS carry label_fa + label_en'],

  // A language picker names each language in its own script. «فارسی» is the
  // Persian word for Persian in every UI language, exactly as "English" is.
  ['app/profile/components/AppearanceSection.tsx', 'language names in their own script'],

  // Page metadata, resolved server-side before any language is known.
  ['app/not-found.tsx', 'SEO metadata, server-resolved'],

  // A server route with no access to the viewer's language, so it answers in
  // both — the same `detail` + `detail_en` shape as the Python backend.
  ['app/api/auth/forgot-password/route.ts', 'bilingual error body, server-side'],

  // Bilingual helpers whose two branches are both in the file.
  ['lib/auditDetails.ts', 'both list separators live in one function'],
  ['components/landing/content/constants.ts', 'MIN_TOPUP_LABEL_FA/_EN pair'],

  // Persian numerals, separators and units ARE this file's subject matter.
  ['lib/format.tsx', 'the Persian number/date policy itself'],
  ['lib/i18n.ts', 'the language contract itself'],
  ['components/LanguageToggle.tsx', 'both branches of the toggle label'],
])

/** Every .ts/.tsx outside app/admin (which its own guard covers). */
function productFiles(): [string, string][] {
  const out: [string, string][] = []
  const walk = (dir: string, base: string) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const rel = base ? `${base}/${e.name}` : e.name
      if (rel.startsWith('app/admin')) continue
      if (e.isDirectory()) { if (e.name !== 'node_modules') walk(join(dir, e.name), rel) }
      else if (/\.tsx?$/.test(e.name)) out.push([rel, readFileSync(join(dir, e.name), 'utf8')])
    }
  }
  walk(join(ROOT, 'app'), 'app')
  walk(join(ROOT, 'components'), 'components')
  walk(join(ROOT, 'lib'), 'lib')
  return out
}

/** A file is a dictionary if it has the SHAPE of one, not if it has the name.
 *  The landing page's copy lives in `components/landing/content/*.ts`, which
 *  were converted in place to `dict(FA, EN)` rather than renamed — those are
 *  dictionaries and their Persian half belongs there. Matching on shape also
 *  means a dictionary cannot be smuggled past this guard by being called
 *  something else. */
function isDictionary(src: string): boolean {
  // On STRIPPED source. lib/i18n.ts documents this exact pattern in its own
  // header comment, and matching raw text classified the contract file as one
  // of the dictionaries it defines.
  const body = stripComments(src)
  // The pair does not have to be called FA/EN. walletHelpers.ts names its two
  // halves STATUS_LABEL_FA / STATUS_LABEL_EN, which is clearer at its call
  // site; what matters is the `: typeof` link that makes a missing key a
  // compile error, and that the pair is handed to dict().
  return PAIR.test(body) && /\bdict\(/.test(body)
}

/** `const <something>EN: typeof <something>FA` — the annotation that turns a
 *  missing translation into a build failure. */
const PAIR = /const\s+(\w*)EN\s*:\s*typeof\s+\1?\w*FA\b/

function stripComments(src: string): string {
  return src
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^[ \t]*\/\/.*$/gm, '')
}

describe('user-facing translation coverage', () => {
  const files = productFiles()

  it('finds the product source at all', () => {
    // A broken path would make every assertion below vacuously pass.
    expect(files.length).toBeGreaterThan(80)
  })

  it('keeps Persian literals in dictionaries, not in components', () => {
    const offenders: string[] = []
    for (const [rel, src] of files) {
      if (isDictionary(src)) continue
      if (ALLOWED.has(rel)) continue
      for (const line of stripComments(src).split('\n')) {
        if (PERSIAN.test(line)) offenders.push(`${rel}: ${line.trim().slice(0, 80)}`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('every dictionary annotates EN with typeof FA and leaves FA un-const', () => {
    const dicts = files.filter(([rel, src]) => !ALLOWED.has(rel)
      && (rel.includes('.strings.') || isDictionary(src)))
    expect(dicts.length).toBeGreaterThan(0)
    for (const [rel, src] of dicts) {
      const body = stripComments(src)
      expect(body, `${rel} must link its EN half with \`: typeof\` its FA half`).toMatch(PAIR)
      // `as const` makes every value a literal type, which no real
      // translation can satisfy — it silently disables the check above.
      expect(body, `${rel} must not mark its FA half as const`).not.toMatch(/\w*FA\s*=\s*\{[\s\S]*?\}\s*as\s+const/)
      expect(body, `${rel} must export through dict()`).toMatch(/\bdict\(/)
    }
  })

  it('no translated screen formats numbers with the Persian-only helpers', () => {
    // faNum/faPrice always emit Persian digits and «تومان». Left in place they
    // print `۱٬۱۵۳ tokens` on an English page. fmt(lang) is the way.
    const offenders: string[] = []
    for (const [rel, src] of files) {
      if (ALLOWED.has(rel)) continue
      if (rel.startsWith('lib/')) continue          // lib defines them
      const body = stripComments(src)
      for (const helper of ['faNum', 'faPrice', 'faCompact', 'faPercent', 'faDate', 'faTime']) {
        if (new RegExp(`\\b${helper}\\s*\\(`).test(body)) offenders.push(`${rel}: ${helper}(`)
      }
    }
    expect(offenders).toEqual([])
  })

  it('the language store is the single source of the active language', () => {
    // Before this work several screens each kept their own `language` state
    // and their own `lang === 'fa' ? … : …` ternaries. One store, one hook.
    // Comment-blind: the file carries a comment block explaining the reload
    // bug it fixed, and a raw scan fails on the explanation, not the code.
    const toggle = stripComments(readFileSync(join(ROOT, 'components/LanguageToggle.tsx'), 'utf8'))
    expect(toggle).toMatch(/export function useLang/)
    expect(toggle).not.toMatch(/location\.reload/)
  })

  it('the chat sidebar does not lock itself to one direction', () => {
    // These four rules were `border-left`, `border-right` and `right: 0`, so
    // in English the sidebar's edge, the selected-conversation stripe and the
    // mobile drawer all stayed on the Persian side. Verified in a browser at
    // the time of the change: RTL computes exactly as it did before, LTR
    // mirrors. A physical property reintroduced here silently un-mirrors it.
    const css = stripComments(readFileSync(join(ROOT, 'styles-chat-sidebar.css'), 'utf8'))
    for (const prop of ['border-left', 'border-right', 'margin-left', 'margin-right']) {
      expect(css, `${prop} is direction-locked; use the logical property`).not.toMatch(
        new RegExp(`\\b${prop}\\s*:`),
      )
    }
    // The drawer's LTR mirror must carry its own open-state rule: without it,
    // `[dir='ltr'] .conv-drawer` (0,2,0) outranks `.conv-drawer-open` (0,1,0)
    // and the drawer can never open in English.
    expect(css).toMatch(/\[dir='ltr'\]\s+\.conv-drawer-open/)
  })
})
