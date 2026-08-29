'use client'

import { useState, useEffect, useMemo } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { AuthProvider, useAuth } from '@/lib/auth'
import { ToastContainer } from '@/components/ui'
import { ThemeToggle } from '@/components/ThemeToggle'
import { LanguageToggle, useLang, type Lang } from '@/components/LanguageToggle'
import { Icon, type IconName } from '@/components/ui/Icon'
import { useCommandPalette } from '@/components/CommandPalette'
import { useProductTour, tourSeen } from '@/components/ProductTour'
import { tourAnchor } from '@/components/tour/anchors'
import { isOnboarded } from '@/lib/onboarding'
import { getPanelPreference, isNavItemVisibleForPanel } from '@/lib/panel'
import { navIcon } from '@/lib/i18n'
import { usePersistedBoolean } from './usePersistedBoolean'
import { BrandLockup } from './BrandLockup'
import { appShellStrings } from './AppShell.strings'

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

/** Not a component -- takes `lang` as a plain parameter instead of calling
 *  useLang(), since NAV is built once per render inside AppShellInner via
 *  useMemo rather than read from a hook at module scope. */
function getNav(lang: Lang): NavItem[] {
  const n = appShellStrings(lang).nav
  return [
    { href: '/chat', label: n.chat, icon: 'chat', section: 'main' },
    { href: '/models', label: n.models, icon: 'models', section: 'main' },
    { href: '/compare', label: n.compare, icon: 'compare', section: 'main' },
    { href: '/combos', label: n.combos, icon: 'compare', section: 'main' },
    { href: '/status', label: n.status, icon: 'chart', section: 'main' },
    { href: '/dashboard', label: n.dashboard, icon: 'dashboard', section: 'tools' },
    { href: '/wallet', label: n.wallet, icon: 'wallet', section: 'tools' },
    { href: '/pricing', label: n.pricing, icon: 'pricing', section: 'tools' },
    { href: '/usage', label: n.usage, icon: 'chart', section: 'tools' },
    { href: '/api-keys', label: n.apiKeys, icon: 'key', section: 'tools' },
    /* '/search' (standalone conversation search) archived 2026-08-21 — search
       already lives inside chat, so a separate section was redundant. Page
       moved to app/search/page.tsx.bak.before-archive-search-20260821; restore
       by moving it back to app/search/page.tsx and restoring this nav entry:
       { href: '/search', label: 'جستجو', icon: 'search', section: 'tools' }, */
    { href: '/skills', label: n.skills, icon: 'cpu', section: 'tools' },
    { href: '/hermes', label: n.hermes, icon: 'rocket', section: 'tools' },
    { href: '/assistants', label: n.assistants, icon: 'sparkles', section: 'tools' },
    { href: '/memory', label: n.memory, icon: 'clock', section: 'tools' },
    { href: '/tasks', label: n.tasks, icon: 'calendar', section: 'tools' },
    { href: '/documents', label: n.documents, icon: 'file', section: 'tools' },
    /* '/images' is listed even though no image model is servable yet: every
       media row is in maintenance with no price, so the page shows an honest
       "no image model is active" empty state rather than a fake list. Listing
       it means the feature appears the moment an upstream key and a price
       exist, instead of needing a frontend change to become visible. */
    { href: '/images', label: n.images, icon: 'camera', section: 'tools' },
    { href: '/developer', label: n.developer, icon: 'code', section: 'tools' },
    // Last in `tools` on purpose: the guide explains the features above it, so
    // it reads as the footnote to that list rather than as another feature.
    { href: '/guide', label: n.guide, icon: 'info', section: 'tools' },
    { href: '/profile', label: n.profile, icon: 'profile', section: 'account' },
    { href: '/referral', label: n.referral, icon: 'referral', section: 'account' },
    { href: '/admin', label: n.admin, icon: 'settings', section: 'account', admin: true },
  ]
}

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
  const lang = useLang()
  const s = appShellStrings(lang)
  const NAV = useMemo(() => getNav(lang), [lang])
  const { user, loading, logout, token } = useAuth()
  const pathname = usePathname()
  const router = useRouter()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  // Desktop-only collapse of the app sidebar to an icon-only rail. Mobile
  // has its own separate drawer (sidebarOpen above) and never collapses.
  const [collapsed, setCollapsed] = usePersistedBoolean('sanjabai_sidebar_collapsed', false)
  const { CommandPalette, setOpen: openPalette } = useCommandPalette()
  // Interactive product tour — the launch-anytime multi-step popup. Called by
  // the top-bar help button below and by a window event any page can dispatch
  // (see ProductTour.tsx). Hook runs on every route, above the early returns,
  // to keep hook order stable — same rule as useCommandPalette.
  const { ProductTour, openTour, launchLabel: tourLabel } = useProductTour()
  // One-time "new" nudge dot on the launcher until the user opens it once.
  // Read once on mount (post-hydration) so SSR and first client render agree.
  const [tourNudge, setTourNudge] = useState(false)
  useEffect(() => { setTourNudge(!tourSeen()) }, [])

  // Consumer/developer panel preference (lib/panel.ts). This is a UI
  // preference only -- it decides which nav *links* are rendered, not which
  // routes are reachable. /developer, /api-keys and /hermes stay reachable
  // by direct URL for every authenticated user regardless of this value; it
  // is not a permission check and must never be treated as one.
  //
  // No wrong-nav flash while `loading` is true or `user` is null -- but the
  // reason is the default, not the render gating (the mobile bottom nav and
  // drawer are behind `user &&`; the desktop sidebar is not). With no user,
  // `user?.preferences` is undefined and getPanelPreference falls back to
  // 'developer', which hides nothing -- byte-identical to the nav this app
  // rendered before this preference existed. So the pre-auth frame shows the
  // full nav, exactly as it always did, and only narrows once a user who was
  // actually moved to 'consumer' has loaded.
  const panel = getPanelPreference(user?.preferences)

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

  // `title`/`aria-label` carry the name even when the collapsed rail's CSS
  // hides the `<span>` -- a hidden label must not become an unlabelled icon.
  const NavItemLink = ({ item }: { item: NavItem }) => (
    <Link
      key={item.href}
      href={item.href}
      className={`sidebar-nav-item ${isActive(item.href) ? 'sidebar-nav-item--active' : ''}`}
      title={item.label}
      aria-label={item.label}
    >
      {isActive(item.href) && <span className="sidebar-active-bar" />}
      <Icon name={item.icon} size={18} />
      <span>{item.label}</span>
    </Link>
  )

  const sections = [
    { key: 'main', label: s.sections.main },
    { key: 'tools', label: s.sections.tools },
    { key: 'account', label: s.sections.account },
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
      <aside className={`layout-sidebar hidden md:flex sidebar-glass${collapsed ? ' layout-sidebar--collapsed' : ''}`}>
        {/* The lockup already contains the wordmark, so the tinted icon chip
            and the separate "Sanjabai" text next to it are both gone -- side
            by side they printed the name twice. Collapsed to an icon-only
            rail, the wordmark has nowhere to go, so it hides and only the
            collapse/expand toggle remains in this row. */}
        <div className="flex items-center justify-between px-4 py-3.5">
          <Link href="/" aria-label="Sanjabai" className={collapsed ? 'hidden' : undefined}>
            <BrandLockup height={30} />
          </Link>
          <button
            type="button"
            className="btn btn-ghost btn-icon"
            onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? s.expandMenu : s.collapseMenu}
            aria-label={collapsed ? s.expandMenu : s.collapseMenu}
            aria-expanded={!collapsed}
          >
            <Icon name={navIcon(lang, collapsed ? 'forward' : 'back')} size={18} />
          </button>
        </div>
        <div className="divider" />

        <nav className="flex-1 px-3 overflow-y-auto sidebar-nav">
          {sections.map((section) => (
            <div key={section.key} className="mb-4">
              <div className="sidebar-section-label">{section.label}</div>
              {NAV.filter((n) => n.section === section.key && (!n.admin || user?.is_admin) && isNavItemVisibleForPanel(n.href, panel)).map((item) => (
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
                    {s.profile}
                  </Link>
                  <Link href="/dashboard" className="sidebar-user-menu-item">
                    <Icon name="dashboard" size={14} />
                    {s.dashboard}
                  </Link>
                  <div className="divider" style={{ margin: '4px 0' }} />
                  <button onClick={logout} className="sidebar-user-menu-item sidebar-user-menu-item--danger">
                    <Icon name="close" size={14} />
                    {s.logout}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <Link href="/login" className="btn btn-primary w-full text-sm">{s.login}</Link>
              <Link href="/signup" className="btn btn-secondary w-full text-sm">{s.signup}</Link>
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
                aria-label={s.menu}
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
              <BrandLockup height={26} />
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
                aria-label={s.searchMenus}
              >
                <Icon name="search" size={14} />
                <span>{s.search}</span>
                <kbd>⌘K</kbd>
              </button>
            )}

            {/* Public pages get the marketing links inline, since they have no
                sidebar to carry them. */}
            {!loading && !user && (
              <nav className="topbar-public-nav" aria-label={s.publicNavLabel}>
                <Link href="/models">{s.nav.models}</Link>
                <Link href="/pricing">{s.nav.pricing}</Link>
                <Link href="/developer">{s.docs}</Link>
              </nav>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Interactive guide launcher. Always visible (icon-only) for a
                signed-in user, mobile included, so the tour is reachable from
                the top bar on every screen — the owner's explicit ask. The
                nudge dot appears until first open. */}
            {user && (
              <button
                type="button"
                onClick={() => { setTourNudge(false); openTour() }}
                className="btn btn-ghost btn-icon relative"
                title={tourLabel}
                aria-label={tourLabel}
                {...tourAnchor('topbar.help')}
              >
                <Icon name="info" size={18} />
                {tourNudge && (
                  <span
                    aria-hidden
                    className="absolute top-1 rounded-full"
                    style={{ insetInlineEnd: '0.25rem', width: '0.4rem', height: '0.4rem', background: 'var(--accent)' }}
                  />
                )}
              </button>
            )}
            <LanguageToggle />
            <ThemeToggle />
            {!loading && !user && (
              <>
                <Link href="/login" className="btn btn-ghost btn-sm">{s.login}</Link>
                <Link href="/signup" className="btn btn-primary btn-sm">{s.signup}</Link>
              </>
            )}
          </div>
        </header>

        {/* Content */}
        <main className={`layout-content${flush ? ' layout-content--flush' : ''}`}>{children}</main>

        {/* Mobile bottom nav — hidden when not logged in */}
        {user && (
        <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-[var(--bg-surface)]/95 backdrop-blur border-t border-[var(--border)] flex justify-around py-2 z-20 safe-bottom">
          {NAV.filter((n) => n.section === 'main' && isNavItemVisibleForPanel(n.href, panel)).slice(0, 4).map((item) => (
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
            <span className="text-[10px]">{s.more}</span>
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
              <BrandLockup height={24} />
              <button onClick={() => setSidebarOpen(false)} className="btn btn-ghost btn-icon topbar-menu-btn">
                <Icon name="close" size={18} />
              </button>
          </div>
          <nav className="p-2">
            {NAV.filter((n) => (!n.admin || user?.is_admin) && isNavItemVisibleForPanel(n.href, panel)).map((item) => (
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
                <button onClick={logout} className="btn btn-ghost btn-sm w-full text-[var(--danger)]">{s.logout}</button>
              </div>
            ) : (
              <Link href="/login" className="btn btn-primary w-full">{s.loginSignup}</Link>
            )}
          </div>
        </div>
      </div>

      {/* ── Command Palette ────────────────────────────────── */}
      {CommandPalette}

      {/* ── Interactive product tour (multi-step popup) ─────── */}
      {ProductTour}

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