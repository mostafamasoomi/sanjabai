import { test, expect } from '@playwright/test'
import { mockCatalog, signIn } from './helpers'

test.describe('a11y', () => {
  test.beforeEach(async ({ page }) => {
    await mockCatalog(page)
  })

  test('document is RTL Persian', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('html')).toHaveAttribute('lang', 'fa')
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  })

  test('no broken images', async ({ page }) => {
    await page.goto('/')
    const broken = await page.evaluate(() => {
      const imgs = Array.from(document.querySelectorAll('img'))
      return imgs.filter((img) => {
        const src = img.getAttribute('src')
        if (!src) return false
        // A broken image has naturalWidth === 0 once loaded.
        return (img as HTMLImageElement).naturalWidth === 0
      }).length
    })
    expect(broken, `${broken} broken <img> found`).toBe(0)
  })

  test('every icon-only button has an accessible name', async ({ page }) => {
    await page.goto('/')
    const missing = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'))
      return buttons
        .filter((b) => {
          const hasSvg = !!b.querySelector('svg')
          const text = (b.textContent || '').trim()
          // Icon-only = renders an svg and has no visible text of its own.
          if (!hasSvg || text.length > 0) return false
          const labelled =
            b.getAttribute('aria-label') || b.getAttribute('aria-labelledby')
          return !labelled
        })
        .map((b) => b.outerHTML.slice(0, 160))
    })
    expect(
      missing,
      `icon-only buttons missing an accessible name:\n${missing.join('\n')}`,
    ).toEqual([])
  })

  test('model identifiers in chat are LTR-isolated', async ({ page }) => {
    await signIn(page)
    await page.goto('/chat')
    const select = page.getByTestId('model-picker-trigger')
    await expect(select).toBeVisible()
    // Latin model names must not be flipped by the RTL document.
    await expect(select).toHaveAttribute('dir', 'ltr')
    // Provider names live inside the picker's dropdown, so open it first.
    await select.click()
    // Provider badge (Latin provider name) is likewise LTR-isolated.
    const badge = page
      .locator('.model-provider-badge')
      .filter({ hasText: /OpenAI|Anthropic/ })
      .first()
    await expect(badge).toHaveAttribute('dir', 'ltr')
  })
})
