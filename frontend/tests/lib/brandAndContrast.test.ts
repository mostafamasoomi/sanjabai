import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

/* Two defects that no compiler and no unit test could see, because both are
 * purely geometric/optical and both files were syntactically perfect.
 *
 * 1. THE AMPUTATED SQUIRREL. logo-lockup.svg shipped `viewBox="63 85 1850
 *    538"` while its artwork runs to y=711.5. The bottom 88.5 units — the
 *    squirrel's foot — were cropped away in all nine places the lockup is
 *    rendered, admin and user alike. The crop was introduced to drop the
 *    "Intelligence, Gathered." tagline, but that tagline is not in this file
 *    at all (it lives only in logo-full.svg, y 677–720); the crop removed
 *    nothing but the animal's foot.
 *
 * 2. INVISIBLE THIRD-TIER TEXT. --lp-ink-3 was #645630 on the dark landing
 *    surface: 2.75:1, well under the 4.5:1 floor for normal text. Eighteen
 *    rules take that token, so a whole tier of landing copy — including the
 *    line under the brand lockup in the footer — rendered as almost nothing.
 *
 * Both are pinned numerically here rather than by eye.
 */

const ROOT = join(__dirname, '../..')

/** WCAG 2.1 relative luminance. */
function luminance(hex: string): number {
  let h = hex.replace('#', '')
  if (h.length === 3) h = h.split('').map((c) => c + c).join('')
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
  const f = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

function contrast(a: string, b: string): number {
  const [la, lb] = [luminance(a), luminance(b)]
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

/* Measured in a real browser with getBBox against the uncropped artwork —
   see the session's logo-bbox harness. The lockup's paths occupy
   x 62.5..1912.5, y 84.5..712.5. Any viewBox that does not contain that box
   is cutting part of the mark off. */
const ARTWORK = { left: 62.5, top: 84.5, right: 1912.5, bottom: 712.5 }

describe('brand lockup is not clipped', () => {
  for (const file of ['logo-lockup.svg', 'logo-lockup-dark.svg']) {
    it(`${file} ships a viewBox that contains the whole mark`, () => {
      const svg = readFileSync(join(ROOT, 'public', file), 'utf8')
      const m = svg.match(/viewBox="([^"]+)"/)
      expect(m, `${file} has no viewBox`).toBeTruthy()
      const [x, y, w, h] = m![1].trim().split(/[\s,]+/).map(Number)
      expect([x, y, w, h].every(Number.isFinite), `${file} viewBox is malformed`).toBe(true)

      expect(x, `${file} crops the left edge`).toBeLessThanOrEqual(ARTWORK.left)
      expect(y, `${file} crops the top edge`).toBeLessThanOrEqual(ARTWORK.top)
      expect(x + w, `${file} crops the right edge`).toBeGreaterThanOrEqual(ARTWORK.right)
      // The one that was actually broken.
      expect(y + h, `${file} crops the squirrel's foot`).toBeGreaterThanOrEqual(ARTWORK.bottom)
    })
  }

  it('the two theme variants are still different files', () => {
    // The dark variant exists only to swap the wordmark gradient's stops for
    // the dark theme's ink. If a copy ever overwrites one with the other the
    // wordmark goes invisible on one of the two themes, silently.
    const light = readFileSync(join(ROOT, 'public/logo-lockup.svg'), 'utf8')
    const dark = readFileSync(join(ROOT, 'public/logo-lockup-dark.svg'), 'utf8')
    expect(light).not.toEqual(dark)
  })
})

describe('landing text clears the contrast floor', () => {
  const css = readFileSync(join(ROOT, 'app/landing.css'), 'utf8')
  const lightAt = css.indexOf("[data-theme='light']")
  const blocks = { dark: css.slice(0, lightAt), light: css.slice(lightAt, lightAt + 2500) }

  const token = (block: string, name: string): string => {
    const m = block.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{3,6})\\s*;`))
    expect(m, `${name} not found`).toBeTruthy()
    return m![1]
  }

  /** Tokens used as TEXT colour. --lp-brand-fill is deliberately absent: it
   *  is only ever a background or a shadow, so the 4.5:1 text floor does not
   *  apply to it (white on it is 5.66:1, which is the ratio that matters). */
  const INK = ['--lp-ink', '--lp-ink-2', '--lp-ink-3']

  for (const theme of ['dark', 'light'] as const) {
    const surface = theme === 'dark' ? '#0e0906' : '#fdfaf5'
    for (const name of INK) {
      it(`${name} is readable on the ${theme} surface`, () => {
        const ratio = contrast(token(blocks[theme], name), surface)
        expect(ratio, `${name} is ${ratio.toFixed(2)}:1 on ${surface}`).toBeGreaterThanOrEqual(4.5)
      })
    }
  }

  it('the three ink tiers stay visually distinct', () => {
    // Fixing contrast by dragging ink-3 up to ink-2 would trade one bug for
    // another: a hierarchy that no longer reads as a hierarchy.
    const [i1, i2, i3] = INK.map((n) => luminance(token(blocks.dark, n)))
    expect(i1).toBeGreaterThan(i2)
    expect(i2).toBeGreaterThan(i3)
  })
})
