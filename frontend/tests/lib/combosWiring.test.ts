import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

/* The wiring + contract guard for /combos.
 *
 * Same source-scan pattern as modelsModuleWiring.test.ts, for the same
 * reason: everything asserted here is a call site or a shared constant, not
 * a return value, and every one of these failures is silent. The screen
 * compiles, renders, and is wrong.
 *
 * Three failure modes are worth a permanent guard:
 *
 *  1. Sending `providerModelId` instead of the public `sanjab/...` id. The
 *     backend stores the public id on purpose (backend/combos.py header) so
 *     a re-routed model keeps meaning what the user picked, and a normal
 *     user must never see a provider or route at all.
 *  2. Calling the backend by absolute URL. The frontend reaches it only
 *     through the `/api/*` prefix, which app/api/[...path]/route.ts (and,
 *     behind it, the next.config.js rewrite) strips before forwarding.
 *  3. The UI's 2–5 / 10 limits drifting from backend/combos.py. The server
 *     is the enforcement; the UI only removes the surprise, and a stale
 *     copy of the number turns a disabled button into a lie in both
 *     directions -- a blocked action that would have worked, or a Persian
 *     400 the user was told could not happen.
 */

const ROOT = join(__dirname, '../..')
const read = (p: string) => readFileSync(join(ROOT, p), 'utf8')

const PAGE = read('app/combos/page.tsx')
const MANAGER = read('app/combos/components/ComboManager.tsx')
const EDITOR = read('app/combos/components/ComboEditor.tsx')
const STRINGS = read('app/combos/components/ComboManager.strings.ts')
const ALL_TSX = [PAGE, MANAGER, EDITOR].join('\n')

// The backend lives outside frontend/, hence the extra hop up.
const BACKEND = readFileSync(join(ROOT, '../backend/combos.py'), 'utf8')

/** Block and line comments removed, so a path named in prose is never read
 *  as a call site. Crude but sufficient: none of these files contain a
 *  string literal holding `/*` or `//`. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
}

/** Reads `export const NAME = 12` out of the editor's source. */
function uiConst(name: string): number {
  const m = EDITOR.match(new RegExp(`export const ${name} = (\\d+)`))
  expect(m, `${name} is not exported from ComboEditor.tsx`).toBeTruthy()
  return Number(m![1])
}

/** Reads `_NAME = 12` out of backend/combos.py. */
function backendConst(name: string): number {
  const m = BACKEND.match(new RegExp(`^${name} = (\\d+)`, 'm'))
  expect(m, `${name} is not defined in backend/combos.py`).toBeTruthy()
  return Number(m![1])
}

describe('combos page wiring', () => {
  it('mounts the manager, which mounts the editor', () => {
    // A component with no importer is not shipped, however green tsc is.
    expect(PAGE).toContain("import ComboManager from './components/ComboManager'")
    expect(PAGE).toMatch(/<ComboManager\b/)
    expect(MANAGER).toContain("from './ComboEditor'")
    expect(MANAGER).toMatch(/<ComboEditor\b/)
  })

  it('reads every user-visible string from the co-located dictionary', () => {
    for (const src of [PAGE, MANAGER, EDITOR]) {
      // The page sits one directory up, hence the relaxed path match.
      expect(src).toMatch(/import \{ comboStrings \} from '\.[^']*ComboManager\.strings'/)
      expect(src).toMatch(/comboStrings\(lang\)/)
    }
    expect(STRINGS).toContain('const EN: typeof FA')
  })
})

describe('combos API contract', () => {
  it('never sends a provider route -- only the public model id', () => {
    expect(ALL_TSX).not.toContain('providerModelId')
    expect(MANAGER).toContain('model_public_id')
  })

  it('reaches the backend only through the /api prefix', () => {
    // Only the manager talks to the API.
    const urls = stripComments(MANAGER).match(/['"`][^'"`\n]*me\/combos[^'"`\n]*['"`]/g) || []
    expect(urls.length).toBeGreaterThan(0)
    for (const u of urls) {
      expect(u).toMatch(/^['"`]\/api\/me\/combos/)
      expect(u).not.toMatch(/https?:/)
    }
  })

  it('sends mutations through apiFetch so the CSRF header is set', () => {
    expect(MANAGER).toContain("import { apiFetch } from '@/lib/apiFetch'")
    for (const method of ['POST', 'PUT', 'DELETE']) {
      expect(MANAGER).toContain(`'${method}'`)
    }
    // The only bare `fetch(` left is the safe GET of the list.
    expect((MANAGER.match(/[^i]fetch\(/g) || []).length).toBe(1)
  })

  it('surfaces the server\'s own Persian refusal rather than inventing one', () => {
    expect(MANAGER).toContain('detailFor(')
  })
})

describe('combos limits match the backend', () => {
  it('uses the same 2-5 item bounds as backend/combos.py', () => {
    expect(uiConst('MIN_ITEMS')).toBe(backendConst('_MIN_ITEMS'))
    expect(uiConst('MAX_ITEMS')).toBe(backendConst('_MAX_ITEMS'))
  })

  it('uses the same 10-combo-per-user cap as backend/combos.py', () => {
    expect(uiConst('MAX_COMBOS')).toBe(backendConst('_MAX_COMBOS_PER_USER'))
  })

  it('offers exactly the policies the backend accepts', () => {
    const m = BACKEND.match(/_VALID_POLICIES = \(([^)]*)\)/)
    expect(m).toBeTruthy()
    const backendPolicies = (m![1].match(/'([a-z_]+)'/g) || []).map((q) => q.slice(1, -1))
    expect(backendPolicies.length).toBeGreaterThan(0)
    const uiPolicies = (
      EDITOR.match(/COMBO_POLICIES: ComboPolicy\[\] = \[([^\]]*)\]/)![1].match(/'([a-z_]+)'/g) || []
    ).map((q) => q.slice(1, -1))
    expect(uiPolicies).toEqual(backendPolicies)
  })

  it('explains both the item range and the combo cap before they bite', () => {
    // Disabled-with-no-reason is the failure this catches: each limit has a
    // Persian sentence attached, not just a greyed-out button.
    expect(EDITOR).toContain('itemsMaxReached')
    expect(EDITOR).toContain('itemsMinNotMet')
    expect(MANAGER).toContain('comboLimitReached')
    for (const key of ['itemsMaxReached', 'itemsMinNotMet', 'comboLimitReached']) {
      expect(STRINGS).toContain(`${key}:`)
    }
  })
})
