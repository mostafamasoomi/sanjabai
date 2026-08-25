import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { MODELS_TABS, DEFAULT_MODELS_TAB, tabFromSearch, isModelsTab } from '../../app/admin/sections/modelsTabs'

/* The wiring guard for the models & pricing module.
 *
 * Eight admin screens that used to be their own sidebar entries are now
 * sub-tabs of one module. The failure mode that costs a screen is silent:
 * a tab listed in MODELS_TABS renders the bar button, and if nothing in
 * ModelsModule branches on its key the panel shows an empty page under a
 * live-looking tab. No unit test of the sections themselves catches that --
 * each one still passes in isolation while being unreachable.
 *
 * Same source-scan pattern as auditDetailsWiring.test.ts, for the same
 * reason: the thing being asserted is a call site, not a return value.
 */

const SECTIONS = join(__dirname, '../../app/admin/sections')
const MODULE_SRC = readFileSync(join(SECTIONS, 'ModelsModule.tsx'), 'utf8')
const PANEL_SRC = readFileSync(join(__dirname, '../../app/admin/AdminPanel.tsx'), 'utf8')

describe('models module tab table', () => {
  it('falls back to the default for an unknown or missing ?tab=', () => {
    expect(tabFromSearch('')).toBe(DEFAULT_MODELS_TAB)
    expect(tabFromSearch('?tab=')).toBe(DEFAULT_MODELS_TAB)
    // The seven retired top-level page keys are NOT sub-tab keys; a stale
    // bookmark naming one must not render an empty module body.
    expect(tabFromSearch('?tab=model-ops')).toBe(DEFAULT_MODELS_TAB)
    expect(tabFromSearch('?tab=logical-models')).toBe(DEFAULT_MODELS_TAB)
  })

  it('reads a valid tab back out of the query string', () => {
    for (const t of MODELS_TABS) {
      expect(tabFromSearch(`?page=models&tab=${t.key}`)).toBe(t.key)
      expect(isModelsTab(t.key)).toBe(true)
    }
  })

  it('has a unique key and a Persian label per tab', () => {
    const keys = MODELS_TABS.map((t) => t.key)
    expect(new Set(keys).size).toBe(keys.length)
    for (const t of MODELS_TABS) expect(t.label.trim()).not.toBe('')
  })

  it('lists the default tab', () => {
    expect(MODELS_TABS.some((t) => t.key === DEFAULT_MODELS_TAB)).toBe(true)
  })
})

describe('models module wiring', () => {
  it('renders a section for every tab in the table', () => {
    for (const t of MODELS_TABS) {
      expect(MODULE_SRC).toContain(`active === '${t.key}'`)
    }
  })

  it('mounts every merged section exactly where it used to live', () => {
    // The eight files that were top-level pages before the merge. If one of
    // these stops being imported here it is orphaned -- unreachable from the
    // panel and invisible to `tsc`, which is happy to compile an unused file.
    for (const section of [
      'ModelOpsSection', 'LogicalModelsSection', 'UpstreamOverheadSection', 'ModelsSection',
      'PricingSection', 'ImagePricingSection', 'ExchangeRateSection', 'MarkupSection',
    ]) {
      expect(MODULE_SRC).toContain(`import('./${section}')`)
      expect(MODULE_SRC).toMatch(new RegExp(`<${section}\\b`))
    }
  })
})

describe('admin shell', () => {
  it('reaches the merged sections only through the module', () => {
    expect(PANEL_SRC).toMatch(/<ModelsModule\b/)
    // The retired nav keys must be gone from the shell entirely, not merely
    // hidden: a leftover `page === 'pricing'` branch is dead code that can
    // never fire, since 'pricing' is no longer assignable to Page.
    for (const retired of [
      'logical-models', 'model-ops', 'upstream-overhead',
      'image-pricing', 'exchange-rate',
    ]) {
      expect(PANEL_SRC).not.toContain(`page === '${retired}'`)
      expect(PANEL_SRC).not.toContain(`key: '${retired}'`)
    }
  })

  it('keeps the sub-tab out of the URL on every other page', () => {
    // `?tab=` is the models module's alone. Setting it unconditionally would
    // stamp a stale sub-tab onto every admin link copied from another page.
    expect(PANEL_SRC).toContain("if (page === 'models') sp.set('tab', modelsTab)")
    expect(PANEL_SRC).toContain("else sp.delete('tab')")
  })
})
