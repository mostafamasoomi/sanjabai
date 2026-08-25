import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

/* Guards for two bugs that were invisible to every existing test.
 *
 * 1. THE CASCADE TRAP. `.admin-card { flex-direction: column }` is declared
 *    in globals.css AFTER `@tailwind utilities`, at the same specificity as
 *    a utility class. So a card written as `admin-card flex flex-wrap
 *    items-center` gets `display:flex` and `flex-wrap:wrap` from Tailwind and
 *    `flex-direction: column` from `.admin-card` -- and adding `flex-row`
 *    does NOT help, because that utility loses the same way. Seven cards were
 *    written expecting a row and every one rendered as a centred column.
 *    Nothing failed: tsc is happy, the components mount, the tests pass, and
 *    the only symptom is on screen.
 *
 * 2. THE RELOAD LOGOUT. <LanguageToggle> ended `toggle()` with
 *    `window.location.reload()`. The admin bearer token lives in a module
 *    variable and never in localStorage (deliberately -- admin/api.ts), so
 *    that reload logged the admin out every time they switched language.
 *
 * Both are asserted by scanning source, the same pattern as
 * modelsModuleWiring.test.ts: what needs pinning is a declaration and a call
 * site, not a return value, and this project's vitest has no DOM env.
 */

const ROOT = join(__dirname, '../..')

/** Source with comments removed.
 *
 *  These guards assert on CODE, so they have to be blind to prose. Both files
 *  under test carry a comment block naming the very pattern being banned --
 *  "used to end in window.location.reload()" -- and a scan of the raw text
 *  fails on the explanation of the bug rather than on the bug. `//` is only
 *  treated as a comment at the start of a line so a `https://` inside a
 *  string cannot truncate it. */
function code(path: string): string {
  return readFileSync(join(ROOT, path), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^[ \t]*\/\/.*$/gm, '')
}

const GLOBALS = code('app/globals.css')
const TOGGLE = code('components/LanguageToggle.tsx')
const PANEL = code('app/admin/AdminPanel.tsx')
const MODELS_MODULE = code('app/admin/sections/ModelsModule.tsx')

/** Every .tsx under app/ and components/, as [relative path, source]. */
function allTsx(): [string, string][] {
  const out: [string, string][] = []
  const walk = (dir: string) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name)
      if (e.isDirectory()) { if (e.name !== 'node_modules') walk(p) }
      else if (e.name.endsWith('.tsx')) out.push([p.slice(ROOT.length + 1), code(p.slice(ROOT.length + 1))])
    }
  }
  walk(join(ROOT, 'app'))
  walk(join(ROOT, 'components'))
  return out
}

describe('admin card row modifier', () => {
  it('declares .admin-card.admin-row with two classes so it outranks both rules', () => {
    // Two classes = specificity (0,2,0), which beats `.admin-card` (0,1,0)
    // and any Tailwind utility (0,1,0) regardless of source order. A
    // single-class `.admin-row` would be a coin flip decided by position.
    expect(GLOBALS).toMatch(/\.admin-card\.admin-row\s*\{[^}]*flex-direction:\s*row/)
  })

  it('still declares .admin-card as a column — the modifier is opt-in', () => {
    expect(GLOBALS).toMatch(/\.admin-card\s*\{[^}]*flex-direction:\s*column/)
  })

  it('no component pairs admin-card with a flex utility that cannot win', () => {
    // `flex`, `flex-row`, `flex-wrap`, `items-*` on an .admin-card are either
    // redundant (display:flex) or dead (direction/alignment). Either way the
    // author meant `admin-row`, so finding one means the trap was re-entered.
    const offenders: string[] = []
    for (const [path, stripped] of allTsx()) {
      for (const m of stripped.matchAll(/className="([^"]*\badmin-card\b[^"]*)"/g)) {
        const cls = m[1]
        if (cls.includes('admin-row')) continue
        if (/\b(flex|flex-row|flex-wrap|items-(center|start|end|baseline))\b/.test(cls)) {
          offenders.push(`${path}: "${cls}"`)
        }
      }
    }
    expect(offenders).toEqual([])
  })

  it('applies the modifier at the two «عملیات کاتالوگ مدل‌ها» bars', () => {
    const filterBar = code('app/admin/sections/CatalogFilterBar.tsx')
    const ops = code('app/admin/sections/ModelOpsSection.tsx')
    expect(filterBar).toContain('admin-card admin-row')
    expect(ops).toContain('admin-card admin-row')
  })
})

describe('native widget colour scheme', () => {
  it('declares color-scheme for both themes', () => {
    // Without this the UA paints its own widgets light on our dark surface --
    // the pale box around the <input type=number> arrows, and the scrollbars
    // and <select> popups with it.
    expect(GLOBALS).toMatch(/color-scheme:\s*dark/)
    expect(GLOBALS).toMatch(/\[data-theme='light'\]\s*\{[^}]*color-scheme:\s*light/)
  })

  it('dims the number spinner without deleting the arrows', () => {
    expect(GLOBALS).toMatch(/::-webkit-inner-spin-button/)
    // `appearance: none` on the spinner removes the arrows entirely, which is
    // the opposite of what was asked for.
    const spinnerBlock = GLOBALS.slice(GLOBALS.indexOf('::-webkit-inner-spin-button'))
      .slice(0, 400)
    expect(spinnerBlock).not.toMatch(/appearance:\s*none/)
  })
})

describe('language switching does not reload', () => {
  it('LanguageToggle never calls location.reload', () => {
    // This is the whole bug: a reload throws away the in-memory admin token.
    expect(TOGGLE).not.toMatch(/location\.reload/)
  })

  it('publishes the change so subscribers re-render in place', () => {
    expect(TOGGLE).toMatch(/dispatchEvent/)
    expect(TOGGLE).toMatch(/export function useLang/)
    expect(TOGGLE).toMatch(/useSyncExternalStore/)
    // Cross-tab: another tab's flip only reaches us as a `storage` event.
    expect(TOGGLE).toMatch(/'storage'/)
  })

  it('admin surfaces subscribe rather than reading the language once', () => {
    for (const [name, src] of [['AdminPanel', PANEL], ['ModelsModule', MODELS_MODULE]] as const) {
      expect(src, `${name} must subscribe`).toMatch(/=\s*useLang\(\)/)
      // `useState(getLang)` / `useState(() => getLang())` were only correct
      // while the toggle reloaded the page; now they would freeze the
      // language at whatever it was on first mount.
      expect(src, `${name} must not snapshot the language`).not.toMatch(/useState\(\s*\(?\s*\)?\s*=?>?\s*getLang/)
    }
  })
})
