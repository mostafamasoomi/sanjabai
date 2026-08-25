'use client'

import { useEffect, useState } from 'react'
import { Icon, type IconName } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import dynamic from 'next/dynamic'
import { Field } from './sections/shared'
import { api, setAdminToken, setUnauthorizedHandler } from './api'
import DashboardSection from './sections/DashboardSection'
import UsersSection from './sections/UsersSection'
import FeaturesSection from './sections/FeaturesSection'
import DiscountsSection from './sections/DiscountsSection'
import AboutSection from './sections/AboutSection'
import ProxySection from './sections/ProxySection'
import SecuritySection from './sections/SecuritySection'
import { tabFromSearch, type ModelsTab } from './sections/modelsTabs'

const MonitoringTab = dynamic(() => import('./components/MonitoringTab'), { ssr: false })
const PackagesSection = dynamic(() => import('./sections/PackagesSection'), { ssr: false })
const AnalyticsSection = dynamic(() => import('./sections/AnalyticsSection'), { ssr: false })
const PlansSection = dynamic(() => import('./sections/PlansSection'), { ssr: false })
const SiteControlSection = dynamic(() => import('./sections/SiteControlSection'), { ssr: false })
const ModelsModule = dynamic(() => import('./sections/ModelsModule'), { ssr: false })
const ModerationSection = dynamic(() => import('./sections/ModerationSection'), { ssr: false })
const WatchdogSection = dynamic(() => import('./sections/WatchdogSection'), { ssr: false })
const FreeTierSection = dynamic(() => import('./sections/FreeTierSection'), { ssr: false })

/* ═══════════════════════════════════════════════════════════════════════════
   Sanjabai Admin Panel — Aurora Design System
   RTL Persian, dark theme, Stripe/Linear inspired

   This file is the shell and nothing else: auth, the sidebar, and which
   section is mounted. It holds no page data. Every section fetches what it
   renders, keyed off its own mount — the previous `loadAll()` fanned ten
   endpoints out at login, swallowed each rejection, and handed the results
   down as ~40 props, so a failed endpoint was indistinguishable from an
   empty one.

   `api` and the response types are re-exported here because sections written
   before the split import them from '../AdminPanel'; the definitions now live
   in ./api.ts and ./types.ts.
   ═══════════════════════════════════════════════════════════════════════════ */

export { api } from './api'
export type {
  Analytics, PricingRow, ModelTestResult, CreditPackageRow, FeatureRow,
  DiscountRow, ProxyConfig, SecurityStats, SecurityEvent, AuditLog,
  UserRow, UserDetail, UserDetailTab,
} from './types'

type Page = 'dashboard' | 'analytics' | 'site-control' | 'models' | 'packages' | 'plans' | 'features' | 'discounts' | 'about' | 'proxy' | 'users' | 'security' | 'moderation' | 'watchdog' | 'free-tier' | 'monitoring'

/* Eight of these used to be separate entries -- مدل‌ها, عملیات کاتالوگ,
   مدل‌های منطقی, توکن تزریقی بالادست, تعرفه‌ها, قیمت‌گذاری تصویر, نرخ ارز,
   درصد سود -- scattered down the sidebar, each opening its own list of the
   same models from a different endpoint. They are now sub-tabs of one
   ModelsModule entry. */
const NAV_ITEMS: { key: Page; label: string; icon: IconName }[] = [
  { key: 'dashboard', label: 'داشبورد', icon: 'dashboard' },
  { key: 'analytics', label: 'تحلیل و درآمد', icon: 'chart' },
  { key: 'site-control', label: 'کنترل سایت', icon: 'settings' },
  { key: 'models', label: 'مدل‌ها و قیمت‌گذاری', icon: 'code' },
  { key: 'users', label: 'کاربران', icon: 'profile' },
  { key: 'packages', label: 'بسته‌ها', icon: 'wallet' },
  { key: 'plans', label: 'پلن و اشتراک', icon: 'wallet' },
  { key: 'features', label: 'امکانات', icon: 'models' },
  { key: 'discounts', label: 'تخفیف‌ها', icon: 'wallet' },
  { key: 'about', label: 'درباره ما', icon: 'notification' },
  { key: 'proxy', label: 'پروکسی', icon: 'security' },
  { key: 'security', label: 'امنیت', icon: 'lock' },
  { key: 'moderation', label: 'پالایش محتوا', icon: 'warning' },
  { key: 'watchdog', label: 'هشدارهای تلگرام', icon: 'notification' },
  { key: 'free-tier', label: 'حساب رایگان', icon: 'gift' },
  { key: 'monitoring', label: 'پایش', icon: 'chart' },
]

const PAGE_KEYS = new Set<string>(NAV_ITEMS.map((n) => n.key))

function currentSearch(): string {
  return typeof window === 'undefined' ? '' : window.location.search
}

/** The section named by `?page=`, or the dashboard. A URL naming one of the
 *  seven retired top-level keys (`pricing`, `model-ops`, ...) is not a valid
 *  page any more; it falls through to the dashboard rather than rendering
 *  nothing. */
function pageFromSearch(search: string): Page {
  const raw = new URLSearchParams(search).get('page') || ''
  return PAGE_KEYS.has(raw) ? (raw as Page) : 'dashboard'
}

export default function AdminPage() {
  const [authed, setAuthed] = useState(false)
  const [tokenInput, setTokenInput] = useState('')
  const [loggingIn, setLoggingIn] = useState(false)
  // Seeded from the URL, lazily. Safe as an initialiser rather than a mount
  // effect because page.tsx loads this component with `ssr: false` -- it only
  // ever renders on the client, so there is no server pass to mismatch.
  //
  // Worth having even though the admin token deliberately never survives a
  // reload (see api.ts): the URL does. Refresh, retype the token, and you are
  // back on the sub-tab you were working in instead of on the dashboard.
  const [page, setPage] = useState<Page>(() => pageFromSearch(currentSearch()))
  const [modelsTab, setModelsTab] = useState<ModelsTab>(() => tabFromSearch(currentSearch()))
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const sp = new URLSearchParams(window.location.search)
    sp.set('page', page)
    // `tab` belongs to the models module alone; leaving it behind on other
    // pages would put a stale sub-tab in every link the admin copies.
    if (page === 'models') sp.set('tab', modelsTab)
    else sp.delete('tab')
    const next = `${window.location.pathname}?${sp.toString()}`
    if (next !== window.location.pathname + window.location.search) {
      // replaceState, not push: the sidebar is not browser history, and a
      // back button that walks 23 sections one at a time is worse than none.
      window.history.replaceState(null, '', next)
    }
  }, [page, modelsTab])

  // Any 401 from any section drops the whole panel back to the login screen.
  // Before this, `api()` threw the `unauthorized` sentinel and no caller
  // branched on it, so an expired token turned every screen into a wall of
  // failed loads with no explanation and no way back.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setAuthed(false)
      setTokenInput('')
      toast('نشست شما منقضی شد؛ دوباره وارد شوید', 'error')
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  const login = async () => {
    const token = tokenInput.trim()
    if (!token) return
    setLoggingIn(true)
    try {
      const res = await fetch('/api/admin/analytics', { headers: { Authorization: 'Bearer ' + token } })
      if (res.ok) {
        setAdminToken(token)
        setAuthed(true)
        toast('ورود موفقیت‌آمیز بود', 'success')
      } else {
        toast('توکن نامعتبر است', 'error')
      }
    } catch {
      toast('خطا در اتصال به سرور', 'error')
    } finally {
      setLoggingIn(false)
    }
  }

  const logout = () => {
    setAdminToken('')
    setAuthed(false)
    setTokenInput('')
    setPage('dashboard')
  }

  // ═════════════════════════════════════════════════════════════════════════
  // RENDER: Login Screen
  // ═════════════════════════════════════════════════════════════════════════

  if (!authed) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4" style={{ background: 'var(--bg-base)' }}>
        <div className="card w-full max-w-sm">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-4" style={{ background: 'var(--accent-dim)' }}>
              <Icon name="settings" size={28} className="text-accent" />
            </div>
            <h1 className="text-xl font-bold text-primary">پنل مدیریت</h1>
            <p className="text-sm mt-1 text-muted">داشبورد مدیریت Sanjabai</p>
          </div>

          <div className="space-y-4">
            <Field label="توکن ادمین">
              <input
                type="password"
                className="input w-full"
                placeholder="توکن خود را وارد کنید..."
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && login()}
                autoFocus
              />
            </Field>
            <button
              className="btn btn-lg w-full"
              onClick={login}
              disabled={loggingIn || !tokenInput.trim()}
            >
              {loggingIn ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  در حال ورود...
                </span>
              ) : (
                'ورود'
              )}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ═════════════════════════════════════════════════════════════════════════
  // RENDER: Admin Panel
  // ═════════════════════════════════════════════════════════════════════════

  const currentNav = NAV_ITEMS.find((n) => n.key === page)

  return (
    <div className="admin-layout min-h-screen" dir="rtl">
      {/* Mobile Header */}
      <div className="lg:hidden flex items-center justify-between p-4 border-b" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
        <button className="btn btn-icon btn-sm" onClick={() => setSidebarOpen(!sidebarOpen)}>
          <Icon name={sidebarOpen ? 'close' : 'menu'} size={20} />
        </button>
        <span className="text-sm font-bold text-accent">
          {currentNav?.label}
        </span>
        <button className="btn btn-icon btn-sm" onClick={logout}>
          <Icon name="logout" size={18} />
        </button>
      </div>

      <div className="flex">
        {/* ─── Sidebar ─────────────────────────────────────────────────── */}
        <aside
          /* A flex COLUMN, and the aside itself does not scroll -- the nav
             does. It used to be one `overflow-y-auto` box with the logout
             button in an `absolute bottom-0` footer, which resolves against
             the aside's own screen-height box, not its 1067px of content.
             Measured live: the aside was 900 tall with 1067 of content, so
             the button sat at y=848 -- painted on top of the «امنیت» nav
             item at y=847 -- while the last four entries lived below it and
             scrolled underneath. Now the nav is the only scroll container
             and the footer is a normal flow item after it, so the button is
             always genuinely last and never overlaps a menu row. */
          className={`
            fixed lg:sticky top-0 right-0 z-40 h-screen w-64 shrink-0
            border-l flex flex-col transition-transform duration-200
            lg:translate-x-0 ${sidebarOpen ? 'translate-x-0' : 'translate-x-full lg:translate-x-0'}
          `}
          style={{
            background: 'var(--bg-surface)',
            borderColor: 'var(--border)',
          }}
        >
          {/* Logo */}
          <div className="shrink-0 p-5 border-b" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'var(--accent-dim)' }}>
                <Icon name="settings" size={18} className="text-accent" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-primary">Sanjabai</h2>
                <p className="text-[10px] text-muted">Admin Panel</p>
              </div>
            </div>
          </div>

          {/* Navigation — the کاربران/مدل‌ها count badges are gone with the
              shell's data state. They were rendered from `loadAll()`'s copy
              of the user and model lists, and the model one always read
              zero because the endpoint it fanned out to (/api/models) does
              not exist. The counts live in their own sections' headers. */}
          <nav className="flex-1 min-h-0 overflow-y-auto p-3 space-y-0.5">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.key}
                className={`
                  w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150
                  ${page === item.key ? 'font-medium' : 'hover:opacity-80'}
                `}
                style={{
                  background: page === item.key ? 'var(--accent-dim)' : 'transparent',
                  color: page === item.key ? 'var(--accent)' : 'var(--text-secondary)',
                }}
                onClick={() => { setPage(item.key); setSidebarOpen(false) }}
              >
                <Icon name={item.icon} size={18} />
                <span>{item.label}</span>
              </button>
            ))}
          </nav>

          {/* Sidebar Footer -- a normal flow item, not `absolute bottom-0`.
              See the aside's comment for what that cost. */}
          <div className="shrink-0 p-3 border-t" style={{ borderColor: 'var(--border)' }}>
            <button
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors text-muted"
              onClick={logout}
            >
              <Icon name="logout" size={18} />
              <span>خروج</span>
            </button>
          </div>
        </aside>

        {/* Mobile Overlay */}
        {sidebarOpen && (
          <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setSidebarOpen(false)} />
        )}

        {/* ─── Main Content ────────────────────────────────────────────── */}
        <main className="admin-main flex-1 min-w-0 p-4 lg:p-8 overflow-y-auto" style={{ background: 'var(--bg-base)' }}>
          {page === 'dashboard' && <DashboardSection />}
          {page === 'users' && <UsersSection />}
          {page === 'features' && <FeaturesSection />}
          {page === 'discounts' && <DiscountsSection />}
          {page === 'about' && <AboutSection />}
          {page === 'proxy' && <ProxySection />}
          {page === 'models' && <ModelsModule tab={modelsTab} onTabChange={setModelsTab} />}
          {page === 'security' && <SecuritySection />}
          {page === 'moderation' && <ModerationSection />}
          {page === 'packages' && <PackagesSection api={api} />}
          {page === 'analytics' && <AnalyticsSection api={api} />}
          {page === 'site-control' && <SiteControlSection api={api} />}
          {page === 'watchdog' && <WatchdogSection api={api} />}
          {page === 'free-tier' && <FreeTierSection api={api} />}
          {page === 'plans' && <PlansSection api={api} />}
          {page === 'monitoring' && <MonitoringTab api={api} />}
        </main>
      </div>
    </div>
  )
}
