import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

/* The skills screen used to say two different things for one concept:
 * the page called it «اسکیل» (app/skills/page.strings.ts, SkillCard, the
 * detail page, the create/use modals) while SkillActivationPanel — living
 * right below the page header — called the exact same thing «مهارت». The
 * fix (P-TERM) picked «مهارت» everywhere under app/skills and translated
 * every «اسکیل» string by hand. This guard is what stops the old word
 * from quietly coming back through a copy-pasted string or a future PR
 * that doesn't know the decision was already made.
 *
 * «مارکتپلیس» is explicitly out of scope (owned by a different packet) —
 * this guard only flags «اسکیل», never that word.
 */

const ROOT = join(__dirname, '../../app/skills')
const OFFENDING = /اسکیل/

/** Every .strings.ts under app/skills, recursively. */
function skillsStringsFiles(): [string, string][] {
  const out: [string, string][] = []
  const walk = (dir: string, base: string) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const rel = base ? `${base}/${e.name}` : e.name
      if (e.isDirectory()) walk(join(dir, e.name), rel)
      else if (e.name.endsWith('.strings.ts')) out.push([rel, readFileSync(join(dir, e.name), 'utf8')])
    }
  }
  walk(ROOT, '')
  return out
}

describe('skills terminology stays مهارت, never اسکیل', () => {
  const files = skillsStringsFiles()

  it('finds the skills strings files at all', () => {
    // A broken walk path would make the assertion below vacuously pass.
    expect(files.length).toBeGreaterThanOrEqual(5)
  })

  it('no .strings.ts under app/skills contains اسکیل', () => {
    const offenders: string[] = []
    for (const [rel, src] of files) {
      for (const line of src.split('\n')) {
        if (OFFENDING.test(line)) offenders.push(`${rel}: ${line.trim().slice(0, 100)}`)
      }
    }
    expect(offenders).toEqual([])
  })
})
