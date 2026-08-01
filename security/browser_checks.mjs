// Browser-driven checks that a plain HTTP request can't answer, because the
// behavior they verify happens client-side after hydration (a redirect
// effect, in this case) -- curl/requests would see the same 200 HTML shell
// whether the bug is present or not.
//
// Run from a checkout that has the frontend's node_modules (Playwright is a
// devDependency there) -- this script does not have its own package.json on
// purpose, to avoid a second node_modules to keep in sync. From the repo
// root:
//
//   cd frontend && node ../security/browser_checks.mjs
//
// Exits non-zero if any check fails. Prints one line per check either way.
import { chromium } from '@playwright/test'
import fs from 'node:fs'

const FRONTEND = (process.env.FRONTEND_URL || 'http://localhost:3003').replace(/\/$/, '')
const PINNED_CHROMIUM = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const executablePath =
  process.env.CHROMIUM_PATH ||
  (fs.existsSync(PINNED_CHROMIUM) ? PINNED_CHROMIUM : undefined)

let failures = 0
const ok = (msg) => console.log(`  [OK]   ${msg}`)
const bad = (msg) => { console.log(`  [FAIL] ${msg}`); failures += 1 }

const browser = await chromium.launch({ executablePath })

// ── Check 1: /admin is reachable without a regular user session ──────────
// This is the specific bug the /admin PUBLIC_ROUTES + CHROME_LESS_ROUTES
// fix addresses: an anonymous visitor used to get bounced to /login before
// ever seeing AdminPanel's own independent admin-token login screen.
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'fa-IR' })
  const page = await ctx.newPage()
  try {
    await page.goto(`${FRONTEND}/admin`, { waitUntil: 'networkidle', timeout: 20000 })
    await page.waitForTimeout(1000) // let the redirect effect fire, if it's going to
    const url = page.url()
    if (url.endsWith('/login')) {
      bad(`/admin redirected an anonymous visitor to /login (${url}) -- admin login screen unreachable`)
    } else if (!url.endsWith('/admin')) {
      bad(`/admin navigated somewhere unexpected: ${url}`)
    } else {
      // Confirm the independent admin-token login screen actually rendered,
      // not just that the URL stayed put (e.g. a blank/errored page would
      // also leave the URL alone).
      const hasTokenInput = await page.locator('input[type="password"], input[placeholder*="توکن"]').count() > 0
      if (hasTokenInput) {
        ok('/admin reachable without a user session, admin-token login screen rendered')
      } else {
        bad('/admin stayed on-URL but the admin-token login input was not found -- page may have errored')
      }
    }
  } catch (e) {
    bad(`/admin check threw: ${String(e).split('\n')[0]}`)
  } finally {
    await ctx.close().catch(() => {})
  }
}

// ── Check 2: /hermes catalog is reachable without a session ──────────────
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'fa-IR' })
  const page = await ctx.newPage()
  try {
    await page.goto(`${FRONTEND}/hermes`, { waitUntil: 'networkidle', timeout: 20000 })
    await page.waitForTimeout(1000)
    const url = page.url()
    if (url.endsWith('/login')) {
      bad(`/hermes redirected an anonymous visitor to /login (${url}) -- catalog should be public`)
    } else {
      ok('/hermes catalog reachable without a user session')
    }
  } catch (e) {
    bad(`/hermes check threw: ${String(e).split('\n')[0]}`)
  } finally {
    await ctx.close().catch(() => {})
  }
}

// ── Check 3: auth-gated Hermes pages still redirect anonymous visitors ───
// The flip side of check 2 -- /hermes/orders must NOT have been swept into
// "public" by an overly broad route-matching fix.
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'fa-IR' })
  const page = await ctx.newPage()
  try {
    await page.goto(`${FRONTEND}/hermes/orders`, { waitUntil: 'networkidle', timeout: 20000 })
    await page.waitForTimeout(1000)
    const url = page.url()
    if (url.endsWith('/login')) {
      ok('/hermes/orders still redirects an anonymous visitor to /login (correctly auth-gated)')
    } else {
      bad(`/hermes/orders did NOT redirect an anonymous visitor to /login (${url}) -- auth-gated route leaked public`)
    }
  } catch (e) {
    bad(`/hermes/orders check threw: ${String(e).split('\n')[0]}`)
  } finally {
    await ctx.close().catch(() => {})
  }
}

await browser.close()

console.log(`\n${failures === 0 ? 'PASS' : 'FAIL'}: ${failures} failing check(s)`)
process.exit(failures === 0 ? 0 : 1)
