import { chromium } from '@playwright/test'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const OUT = process.env.OUT || path.join(os.tmpdir(), 'sanjhubai-frontend-audit')
fs.mkdirSync(OUT, { recursive: true })

// Prefer Playwright's own managed browser. This container ships a pinned build
// at a fixed path and no managed one, so fall back to it when it exists —
// but never hard-code it, or the audit only runs on this one machine.
const PINNED_CHROMIUM = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const executablePath =
  process.env.CHROMIUM_PATH ||
  (fs.existsSync(PINNED_CHROMIUM) ? PINNED_CHROMIUM : undefined)
if (process.env.CHROMIUM_PATH && !fs.existsSync(process.env.CHROMIUM_PATH)) {
  throw new Error(`CHROMIUM_PATH is set but does not exist: ${process.env.CHROMIUM_PATH}`)
}

const CATALOG = {
  data: [
    { id: 'deepseek-v4-pro', providerModelId: 'deepseek-v4-pro', provider: 'deepseek', displayName: 'DeepSeek V4 Pro', description: 'مدل استدلال و کدنویسی', modalities: { input: ['text'], output: ['text'] }, capabilities: ['chat', 'code', 'reasoning'], recommendedFor: ['general'], contextWindow: 128000, pricing: { currency: 'IRT', inputPerMillion: 15000, outputPerMillion: 45000, priceVersion: '1', effectiveFrom: '2024-01-01' }, availability: 'available', audience: ['consumer'], lastVerifiedAt: '2024-01-01', provenance: 'provider', health: { status: 'healthy', successRate: 1, latencyP50Ms: 780, latencyP95Ms: 1400, sampleCount: 42, lastOkAt: new Date().toISOString(), lastError: null, checkedAt: new Date().toISOString() } },
    { id: 'mistral-large', providerModelId: 'mistral-large', provider: 'mistral', displayName: 'Mistral Large', description: 'نوشتار عمومی', modalities: { input: ['text'], output: ['text'] }, capabilities: ['chat'], recommendedFor: [], contextWindow: 32000, pricing: { currency: 'IRT', inputPerMillion: 20000, outputPerMillion: 60000, priceVersion: '1', effectiveFrom: '2024-01-01' }, availability: 'available', audience: ['consumer'], lastVerifiedAt: '2024-01-01', provenance: 'provider', health: { status: 'degraded', successRate: 0.7, latencyP50Ms: 3200, latencyP95Ms: 9000, sampleCount: 18, lastOkAt: new Date().toISOString(), lastError: 'timeout', checkedAt: new Date().toISOString() } },
    { id: 'gemini-3.5-flash', providerModelId: 'gemini-3.5-flash', provider: 'google', displayName: 'Gemini 3.5 Flash', description: 'سریع و چندوجهی', modalities: { input: ['text', 'image'], output: ['text'] }, capabilities: ['chat', 'vision'], recommendedFor: ['general'], contextWindow: 1000000, pricing: { currency: 'IRT', inputPerMillion: 5000, outputPerMillion: 15000, priceVersion: '1', effectiveFrom: '2024-01-01' }, availability: 'available', audience: ['consumer'], lastVerifiedAt: '2024-01-01', provenance: 'provider', health: { status: 'unknown', successRate: null, latencyP50Ms: null, latencyP95Ms: null, sampleCount: 0, lastOkAt: null, lastError: null, checkedAt: null } },
  ],
  generatedAt: '2024-01-01T00:00:00Z',
  source: 'approved-catalog',
}

const HEALTH = {
  overall: 'degraded',
  counts: { healthy: 1, degraded: 1, down: 0, unknown: 1 },
  upstreams: [
    { name: 'litellm', ok: true, latencyMs: 42, error: null },
    { name: 'ninerouter', ok: false, latencyMs: 5001, error: 'ConnectError' },
  ],
  windowMinutes: 30,
  generatedAt: new Date().toISOString(),
  models: CATALOG.data.map((m) => ({ id: m.id, displayName: m.displayName, ...m.health })),
}

const J = (b) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(b) })

const HERMES_OFFERINGS = [
  { id: 'hermes-standard', name_fa: 'هرمس استاندارد', name_en: 'Hermes Standard', description_fa: 'حداقل توصیه‌شده برای اجرای هرمس', description_en: 'Recommended minimum', arch: 'amd64', vcpu: 4, ram_mb: 8192, disk_gb: 80, traffic_tb: 20, max_skills: 5, included_credit: 0, setup_price_irt: 0, monthly_price_irt: 610000, currency: 'IRT' },
  { id: 'hermes-pro', name_fa: 'هرمس پرو', name_en: 'Hermes Pro', description_fa: 'برای چند اسکیل هم‌زمان', description_en: 'For several concurrent skills', arch: 'amd64', vcpu: 8, ram_mb: 16384, disk_gb: 160, traffic_tb: 20, max_skills: 10, included_credit: 100000, setup_price_irt: 0, monthly_price_irt: 1470000, currency: 'IRT' },
]
const HERMES_SKILLS = [
  { id: 'coding', name_fa: 'برنامه‌نویسی', name_en: 'Coding', description_fa: 'دستیار کدنویسی با زبان‌های انتخابی', category: 'development', options_schema: { languages: { type: 'multiselect', values: ['python', 'go', 'typescript'], max: 5 } }, requires_cron: false },
  { id: 'news-watch', name_fa: 'رصد اخبار', name_en: 'News Watch', description_fa: 'رصد و خلاصه‌سازی دوره‌ای اخبار', category: 'monitoring', options_schema: { topics: { type: 'tags', max: 10 }, schedule: { type: 'cron', default: '0 9 * * *' } }, requires_cron: true },
]
const HERMES_ORDERS = [
  { id: 1, offering_id: 'hermes-standard', status: 'active', setup_price_irt: 0, monthly_price_irt: 610000, created_at: '2026-07-01T10:00:00Z', delivered_at: '2026-07-02T09:00:00Z' },
  { id: 2, offering_id: 'hermes-pro', status: 'pending_payment', setup_price_irt: 0, monthly_price_irt: 1470000, created_at: '2026-07-20T10:00:00Z', delivered_at: null },
]
const HERMES_SERVERS = [
  { id: 1, hostname: 'hermes-01', ip_address: '203.0.113.10', status: 'active', monthly_price_irt: 610000, in_sync: true, last_heartbeat_at: '2026-07-31T10:00:00Z' },
]

const PAGES = [
  ['landing', '/', false],
  ['models', '/models', false],
  ['pricing', '/pricing', false],
  ['login', '/login', false],
  ['signup', '/signup', false],
  ['status', '/status', false],
  ['developer', '/developer', false],
  ['chat', '/chat', true],
  ['dashboard', '/dashboard', true],
  ['wallet', '/wallet', true],
  ['usage', '/usage', true],
  ['compare', '/compare', true],
  ['skills', '/skills', true],
  ['api-keys', '/api-keys', true],
  ['profile', '/profile', true],
  ['prompts', '/prompts', true],
  ['hermes', '/hermes', false],
  ['hermes-order', '/hermes/order', true],
  ['hermes-orders', '/hermes/orders', true],
  ['hermes-servers', '/hermes/servers', true],
]

const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  mobile: { width: 390, height: 844 },
}

const browser = await chromium.launch({ executablePath })

const findings = []

for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
  for (const theme of vpName === 'desktop' ? ['dark', 'light'] : ['dark']) {
    for (const [name, pagePath, needsAuth] of PAGES) {
      const ctx = await browser.newContext({ viewport, locale: 'fa-IR' })
      try {
      await ctx.addInitScript((t) => localStorage.setItem('theme', t), theme)
      if (needsAuth) {
        await ctx.addInitScript(() => {
          localStorage.setItem('sanjhubai_auth_token', 'test-token')
          localStorage.setItem('sanjhubai_onboarded', '1')
        })
      }
      const page = await ctx.newPage()
      const errs = []
      page.on('pageerror', (e) => errs.push(String(e).slice(0, 120)))

      // Playwright matches the most recently registered route first, so the
      // catch-all has to be registered BEFORE the specific handlers or it
      // swallows all of them and every page renders empty.
      await page.route((u) => u.toString().includes('/api/'), (r) => r.fulfill(J({})))
      await page.route((u) => u.toString().includes('/api/wallet'), (r) => r.fulfill(J({ balance: 1250000 })))
      await page.route((u) => u.toString().includes('/api/wallet/ledger'), (r) => r.fulfill(J([])))
      await page.route((u) => u.toString().includes('/api/conversations'), (r) => r.fulfill(J([{ id: 1, title: 'گفتگوی نمونه', created_at: '2026-07-01T10:00:00Z' }])))
      await page.route((u) => u.toString().includes('/api/auth/me'), (r) => r.fulfill(J({ id: 1, email: 'user@example.com' })))
      await page.route((u) => u.toString().includes('/api/models/health'), (r) => r.fulfill(J(HEALTH)))
      await page.route((u) => u.toString().includes('/api/catalog/models'), (r) => r.fulfill(J(CATALOG)))
      await page.route((u) => u.toString().includes('/api/hermes/offerings'), (r) => r.fulfill(J(HERMES_OFFERINGS)))
      await page.route((u) => u.toString().includes('/api/hermes/skill-catalog'), (r) => r.fulfill(J(HERMES_SKILLS)))
      await page.route((u) => u.toString().includes('/api/hermes/orders'), (r) => r.fulfill(J(HERMES_ORDERS)))
      await page.route((u) => u.toString().includes('/api/hermes/servers'), (r) => r.fulfill(J(HERMES_SERVERS)))

      // 'load', not 'networkidle': anything that polls (the /status page
      // refreshes on a timer) can keep the network busy forever, and a
      // navigation that times out here would be silently reported as a pile of
      // layout problems on a blank page. Settle on idle afterwards on a best
      // effort basis, without letting it fail the render.
      let navError = null
      try {
        await page.goto(`http://localhost:3003${pagePath}`, { waitUntil: 'load', timeout: 20000 })
      } catch (e) {
        navError = String(e).split('\n')[0].slice(0, 140)
      }
      await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => {})
      await page.waitForTimeout(700)

      const metrics = await page.evaluate(() => {
        const de = document.documentElement
        const overflowX = de.scrollWidth - de.clientWidth
        // Elements whose box escapes the viewport horizontally.
        const escaping = []
        for (const el of Array.from(document.querySelectorAll('body *'))) {
          const r = el.getBoundingClientRect()
          if (r.width === 0 || r.height === 0) continue
          if (r.right > de.clientWidth + 2 || r.left < -2) {
            escaping.push(`${el.tagName.toLowerCase()}.${(el.className || '').toString().split(' ')[0]}`)
          }
        }
        // Tap targets below the 24px minimum.
        const small = []
        for (const el of Array.from(document.querySelectorAll('button, a, input, select, [role=button]'))) {
          const r = el.getBoundingClientRect()
          if (r.width === 0 || r.height === 0) continue
          if (r.height < 24 || r.width < 24) {
            small.push(`${el.tagName.toLowerCase()}:${(el.textContent || '').trim().slice(0, 18)}`)
          }
        }
        // Headings out of order (h1 -> h3 skips a level).
        const levels = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).map((h) => +h.tagName[1])
        const skips = []
        for (let i = 1; i < levels.length; i++) {
          if (levels[i] - levels[i - 1] > 1) skips.push(`h${levels[i - 1]}->h${levels[i]}`)
        }
        return {
          overflowX,
          escaping: [...new Set(escaping)].slice(0, 6),
          small: [...new Set(small)].slice(0, 6),
          h1Count: document.querySelectorAll('h1').length,
          headingSkips: skips.slice(0, 4),
          title: document.title,
          bodyText: (document.body.innerText || '').length,
        }
      })

      const key = `${vpName}-${theme}-${name}`
      findings.push({ key, path: pagePath, navError, ...metrics, errors: errs })
      await page.screenshot({ path: `${OUT}/${key}.png`, fullPage: vpName === 'desktop' })
      } catch (e) {
        findings.push({
          key: `${vpName}-${theme}-${name}`,
          path: pagePath,
          navError: `audit-threw: ${String(e).split('\n')[0].slice(0, 140)}`,
          overflowX: 0, escaping: [], small: [], h1Count: 1,
          headingSkips: [], title: '', bodyText: 0, errors: [],
        })
      } finally {
        await ctx.close().catch(() => {})
      }
    }
  }
}

fs.writeFileSync(`${OUT}/findings.json`, JSON.stringify(findings, null, 2))

// Terse console report: only rows with something worth looking at.
for (const f of findings) {
  const problems = []
  if (f.navError) problems.push(`NAV-FAILED(${f.navError})`)
  if (f.overflowX > 0) problems.push(`overflowX=${f.overflowX}`)
  if (f.escaping.length) problems.push(`escaping=[${f.escaping.join(', ')}]`)
  if (f.small.length) problems.push(`tiny-targets=[${f.small.join(', ')}]`)
  if (f.h1Count !== 1) problems.push(`h1Count=${f.h1Count}`)
  if (f.headingSkips.length) problems.push(`headingSkips=[${f.headingSkips.join(',')}]`)
  if (f.errors.length) problems.push(`jsErrors=${f.errors.length}`)
  if (f.bodyText < 200) problems.push(`nearlyEmpty(${f.bodyText}ch)`)
  if (problems.length) console.log(`${f.key.padEnd(34)} ${problems.join('  ')}`)
}
console.log(`\n${findings.length} page renders captured -> ${OUT}`)

await browser.close().catch(() => {})
