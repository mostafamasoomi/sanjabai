'use client'

import { useState, useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { AuthProvider, useAuth } from '@/lib/auth'
import { ToastContainer } from '@/components/ui'
import { ThemeToggle } from '@/components/ThemeToggle'
import { LanguageToggle } from '@/components/LanguageToggle'
import { Icon, type IconName } from '@/components/ui/Icon'
import { useCommandPalette } from '@/components/CommandPalette'
import { isOnboarded } from '@/lib/onboarding'

/* ═══════════════════════════════════════════════════════════════════════════
   Sanjabai Aurora — AppShell v2
   Premium sidebar, command palette, mobile-first, keyboard shortcuts.
   ═══════════════════════════════════════════════════════════════════════════ */

type NavItem = {
  href: string
  label: string
  icon: IconName
  section?: string
  admin?: boolean
}

const NAV: NavItem[] = [
  { href: '/chat', label: 'چت', icon: 'chat', section: 'main' },
  { href: '/models', label: 'مدل\u200cها', icon: 'models', section: 'main' },
  { href: '/compare', label: 'مقایسه', icon: 'compare', section: 'main' },
  { href: '/status', label: 'وضعیت مدل‌ها', icon: 'chart', section: 'main' },
  { href: '/dashboard', label: 'داشبورد', icon: 'dashboard', section: 'tools' },
  { href: '/wallet', label: 'کیف پول', icon: 'wallet', section: 'tools' },
  { href: '/pricing', label: 'تعرفه\u200cها', icon: 'pricing', section: 'tools' },
  { href: '/usage', label: 'مصرف', icon: 'chart', section: 'tools' },
  { href: '/api-keys', label: 'کلید API', icon: 'key', section: 'tools' },
  { href: '/search', label: 'جستجو', icon: 'search', section: 'tools' },
  { href: '/skills', label: 'اسکیل\u200cها', icon: 'cpu', section: 'tools' },
  { href: '/hermes', label: 'سرور هرمس', icon: 'rocket', section: 'tools' },
  { href: '/assistants', label: 'دستیارها', icon: 'sparkles', section: 'tools' },
  { href: '/memory', label: 'حافظه', icon: 'clock', section: 'tools' },
  { href: '/tasks', label: 'تسک\u200cها', icon: 'calendar', section: 'tools' },
  { href: '/documents', label: 'سندساز', icon: 'file', section: 'tools' },
  { href: '/developer', label: 'توسعه\u200cدهندگان', icon: 'code', section: 'tools' },
  { href: '/profile', label: 'پروفایل', icon: 'profile', section: 'account' },
  { href: '/referral', label: 'دعوت', icon: 'referral', section: 'account' },
  { href: '/admin', label: 'مدیریت', icon: 'settings', section: 'account', admin: true },
]

/**
 * Routes that render without the product sidebar/topbar. The landing page and
 * the auth screens supply their own marketing chrome; wrapping them in the
 * app shell would give them two competing navigations.
 */
const CHROME_LESS_ROUTES = new Set(['/', '/login', '/signup', '/forgot-password', '/admin'])

/**
 * Routes that manage their own vertical space and must not get the shell's
 * gutters or a scrolling document: they size themselves against the viewport
 * minus the chrome (see `.layout-content--flush` in globals.css). /chat is the
 * only one today — a fixed model bar, a scrolling transcript and a composer
 * pinned to the bottom only work if the container is exactly one screen tall.
 */
const FLUSH_ROUTES = new Set(['/chat'])

/** Routes reachable without a session. Everything else redirects to /login. */
const PUBLIC_ROUTES = [
  '/',
  '/login',
  '/signup',
  '/forgot-password',
  '/onboarding',
  '/pricing',
  '/models',
  '/developer',
  '/status',
  // AdminPanel has its own independent admin-token login screen (hits
  // /api/admin/analytics directly) -- a separate auth mechanism from the
  // regular user session on purpose. It must stay reachable without one,
  // otherwise an admin who isn't also a regular logged-in user gets bounced
  // to /login before ever seeing the admin login screen.
  '/admin',
]

/* ═══════════════════════════════════════════════════════════════════════════
   Inner layout
   ═══════════════════════════════════════════════════════════════════════════ */

function AppShellInner({ children }: { children: React.ReactNode }) {
  const { user, loading, logout, token } = useAuth()
  const pathname = usePathname()
  const router = useRouter()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const { CommandPalette, setOpen: openPalette } = useCommandPalette()

  // Routes that bring their own chrome: the landing page and the auth screens
  // carry the marketing header/footer, so the product sidebar would be a
  // second, conflicting navigation. They still need the provider tree above
  // this component, which is why they render through here at all.
  const bare = CHROME_LESS_ROUTES.has(pathname ?? '')
  const flush = FLUSH_ROUTES.has(pathname ?? '')

  useEffect(() => { setSidebarOpen(false) }, [pathname])
  // Close user menu on outside click
  useEffect(() => {
    if (!userMenuOpen) return
    const close = () => setUserMenuOpen(false)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [userMenuOpen])

  // ── First-visit detection ────────────────────────────────────────────────
  // Route authenticated users who have NOT completed onboarding and who have
  // NO conversations yet to /onboarding. Fails open: if the conversations
  // check can't confirm an empty list, we let the user into the app.
  useEffect(() => {
    if (loading || !user) return
    if (pathname === '/onboarding' || bare) return
    if (isOnboarded()) return

    let cancelled = false
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}
    fetch('/api/conversations', { headers })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => {
        if (cancelled) return
        // Backend may return array or paginated {items: [...]} format
        const list = Array.isArray(data) ? data : (data?.items ?? [])
        const hasConversations = list.length > 0
        if (!hasConversations) router.replace('/onboarding')
      })
      .catch(() => {
        /* fail open — never trap a user in onboarding */
      })
    return () => {
      cancelled = true
    }
  }, [loading, user, token, pathname, router, bare])

  // Exact-match only: unlike the PUBLIC_ROUTES entries above (none of which
  // have real sub-routes today), /hermes has auth-gated children
  // (/hermes/order, /hermes/orders, /hermes/servers) that must still bounce
  // to /login -- only the catalog listing itself is browsable before
  // signing up, same as /pricing and /models.
  const isPublic = pathname === '/hermes'
    || PUBLIC_ROUTES.some((p) => pathname === p || pathname?.startsWith(p + '/'))

  // Send signed-out visitors to /login for anything that needs a session.
  // Done in an effect, not during render: calling router.push() while
  // rendering warns in React and can loop.
  useEffect(() => {
    if (loading || user || isPublic) return
    router.push('/login')
  }, [loading, user, isPublic, router])

  const isActive = (href: string) => pathname === href || pathname?.startsWith(href + '/')

  // ── Every hook above this line runs on every route ───────────────────────
  // The early returns below must stay below them, or React sees a different
  // number of hooks between the landing page and the rest of the app.

  if (bare) {
    // The palette hook runs above regardless of route, so rendering it here
    // costs no extra JavaScript and keeps ⌘K working site-wide.
    return (
      <>
        {children}
        {CommandPalette}
        <ToastContainer />
      </>
    )
  }

  if (!loading && !user && !isPublic) return null

  const NavItemLink = ({ item }: { item: NavItem }) => (
    <Link
      key={item.href}
      href={item.href}
      className={`sidebar-nav-item ${isActive(item.href) ? 'sidebar-nav-item--active' : ''}`}
    >
      {isActive(item.href) && <span className="sidebar-active-bar" />}
      <Icon name={item.icon} size={18} />
      <span>{item.label}</span>
    </Link>
  )

  const sections = [
    { key: 'main', label: 'اصلی' },
    { key: 'tools', label: 'ابزارها' },
    { key: 'account', label: 'حساب' },
  ]

  return (
    // Plain container. This used to carry role="button" + tabIndex={0} + an
    // onClick, which made assistive tech announce the entire application as a
    // single button and put it in the tab order. It only existed to dismiss
    // the user menu on an outside click — which the document-level listener in
    // the effect above already does.
    <div className="layout-shell">
      {/* ── Desktop Sidebar — hidden when not logged in ── */}
      {user && (
      <aside className="layout-sidebar hidden md:flex sidebar-glass">
        <div className="flex items-center gap-2 px-4 py-3.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{background: 'var(--accent-dim)'}}>
            <img src="/logo.svg" alt="" width={22} height={22} />
          </div>
          <Link href="/" className="text-lg font-extrabold text-gradient tracking-tight">Sanjabai</Link>
        </div>
        <div className="divider" />

        <nav className="flex-1 px-3 overflow-y-auto sidebar-nav">
          {sections.map((section) => (
            <div key={section.key} className="mb-4">
              <div className="sidebar-section-label">{section.label}</div>
              {NAV.filter((n) => n.section === section.key && (!n.admin || user?.is_admin)).map((item) => (
                <NavItemLink key={item.href} item={item} />
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-user-section">
          {loading ? (
            <div className="skeleton h-8 rounded-lg" />
          ) : user ? (
            <div className="sidebar-user-wrapper">
              <button
                className="sidebar-user-btn"
                onClick={(e) => { e.stopPropagation(); setUserMenuOpen(!userMenuOpen) }}
              >
              <div className="sidebar-user-avatar">
                {user.email?.[0]?.toUpperCase() || '?'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate">{user.email}</div>
              </div>
              </button>
              {userMenuOpen && (
                <div className="sidebar-user-menu fade-in">
                  <Link href="/profile" className="sidebar-user-menu-item">
                    <Icon name="profile" size={14} />
                    پروفایل
                  </Link>
                  <Link href="/dashboard" className="sidebar-user-menu-item">
                    <Icon name="dashboard" size={14} />
                    داشبورد
                  </Link>
                  <div className="divider" style={{ margin: '4px 0' }} />
                  <button onClick={logout} className="sidebar-user-menu-item sidebar-user-menu-item--danger">
                    <Icon name="close" size={14} />
                    خروج
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <Link href="/login" className="btn btn-primary w-full text-sm">ورود</Link>
              <Link href="/signup" className="btn btn-secondary w-full text-sm">ثبت‌نام</Link>
            </div>
          )}
        </div>
      </aside>
      )}

      {/* ── Main Area ──────────────────────────────────────── */}
      <div className={`layout-main${flush ? ' layout-main--flush' : ''}`}>
        {/* Top bar */}
        <header className="topbar-glass">
          <div className="flex items-center gap-2">
            {/* Burger only opens something when there is a sidebar to open. */}
            {user && (
              <button
                className="md:hidden btn btn-ghost btn-icon topbar-menu-btn"
                onClick={() => setSidebarOpen(!sidebarOpen)}
                aria-label="منو"
              >
                <Icon name={sidebarOpen ? 'close' : 'menu'} size={20} />
              </button>
            )}

            {/* The brand used to be `md:hidden`, which left signed-out visitors
                on a desktop with no logo and no way back to the home page —
                /models and /pricing were dead ends. It is now always present
                for them, and stands in for the marketing header.

                For a signed-in user on a wide screen the sidebar carries the
                same lockup ~200px away, so this copy is marked as the
                duplicate and hidden from md up. Below md there is no sidebar,
                so it is the only brand and the only route home. */}
            <Link
              href="/"
              className={`topbar-brand${user ? ' topbar-brand--duplicate' : ''}`}
            >
              <img src="/logo.svg" alt="" width={24} height={24} />
              <span>Sanjabai</span>
            </Link>

            {/* Command palette. It lives at the start of the bar rather than
                the end because that is where the removed duplicate brand left
                a hole, and because it is the only thing in the topbar a user
                reaches for repeatedly — the language and theme toggles are
                set-once controls and belong out of the way. */}
            {user && (
              <button
                onClick={() => openPalette(true)}
                className="topbar-search hidden sm:flex"
                aria-label="جستجو در منوها"
              >
                <Icon name="search" size={14} />
                <span>جستجو</span>
                <kbd>⌘K</kbd>
              </button>
            )}

            {/* Public pages get the marketing links inline, since they have no
                sidebar to carry them. */}
            {!loading && !user && (
              <nav className="topbar-public-nav" aria-label="پیمایش عمومی">
                <Link href="/models">مدل‌ها</Link>
                <Link href="/pricing">تعرفه‌ها</Link>
                <Link href="/developer">مستندات</Link>
              </nav>
            )}
          </div>

          <div className="flex items-center gap-2">
            <LanguageToggle />
            <ThemeToggle />
            {!loading && !user && (
              <>
                <Link href="/login" className="btn btn-ghost btn-sm">ورود</Link>
                <Link href="/signup" className="btn btn-primary btn-sm">ثبت‌نام</Link>
              </>
            )}
          </div>
        </header>

        {/* Content */}
        <main className={`layout-content${flush ? ' layout-content--flush' : ''}`}>{children}</main>

        {/* Mobile bottom nav — hidden when not logged in */}
        {user && (
        <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-[var(--bg-surface)]/95 backdrop-blur border-t border-[var(--border)] flex justify-around py-2 z-20 safe-bottom">
          {NAV.filter((n) => n.section === 'main').slice(0, 4).map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center gap-0.5 text-xs px-2 py-1 rounded-lg transition-colors min-w-0 ${
                isActive(item.href) ? 'text-[var(--accent)]' : 'text-[var(--text-muted)]'
              }`}
            >
              <Icon name={item.icon} size={20} />
              <span className="truncate text-[10px]">{item.label}</span>
            </Link>
          ))}
          <button
            onClick={() => openPalette(true)}
            className="flex flex-col items-center gap-0.5 text-xs px-2 py-1 text-[var(--text-muted)]"
          >
            <Icon name="menu" size={20} />
            <span className="text-[10px]">بیشتر</span>
          </button>
        </nav>
        )}

        {/* Clears the fixed mobile bottom nav. Suppressed on flush routes,
            which already subtract --bottomnav-h from their own height. */}
        <div className="md:hidden h-14 layout-bottomnav-spacer" />
      </div>

      {/* ── Mobile sidebar overlay ─────────────────────────── */}
      <div className={`mobile-overlay ${sidebarOpen ? 'mobile-overlay--open' : ''}`} onClick={() => setSidebarOpen(false)}>
        <div className="mobile-overlay-bg" />
        <div
          className="mobile-drawer"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between px-4 py-3.5 border-b border-[var(--border)]">
              <span className="font-bold text-gradient">Sanjabai</span>
              <button onClick={() => setSidebarOpen(false)} className="btn btn-ghost btn-icon topbar-menu-btn">
                <Icon name="close" size={18} />
              </button>
          </div>
          <nav className="p-2">
            {NAV.filter((n) => !n.admin || user?.is_admin).map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`sidebar-nav-item ${isActive(item.href) ? 'sidebar-nav-item--active' : ''}`}
              >
                {isActive(item.href) && <span className="sidebar-active-bar" />}
                <Icon name={item.icon} size={18} />
                <span>{item.label}</span>
              </Link>
            ))}
          </nav>
          <div className="p-3 border-t border-[var(--border)]">
            {user ? (
              <div>
                <div className="text-xs text-[var(--text-muted)] mb-2">{user.email}</div>
                <button onClick={logout} className="btn btn-ghost btn-sm w-full text-[var(--danger)]">خروج</button>
              </div>
            ) : (
              <Link href="/login" className="btn btn-primary w-full">ورود / ثبت‌نام</Link>
            )}
          </div>
        </div>
      </div>

      {/* ── Command Palette ────────────────────────────────── */}
      {CommandPalette}

      {/* ── Toast ──────────────────────────────────────────── */}
      <ToastContainer />
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════════════════
   Exported wrapper
   ═══════════════════════════════════════════════════════════════════════════ */

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AppShellInner>{children}</AppShellInner>
    </AuthProvider>
  )
}