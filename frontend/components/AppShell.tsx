'use client'

import { useState, useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { AuthProvider, useAuth } from '@/lib/auth'
import { ToastContainer } from '@/components/ui'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Icon, type IconName } from '@/components/ui/Icon'
import { useCommandPalette } from '@/components/CommandPalette'
import { isOnboarded } from '@/lib/onboarding'

/* ═══════════════════════════════════════════════════════════════════════════
   Multiai Aurora — AppShell v2
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
  { href: '/dashboard', label: 'داشبورد', icon: 'dashboard', section: 'tools' },
  { href: '/wallet', label: 'کیف پول', icon: 'wallet', section: 'tools' },
  { href: '/pricing', label: 'تعرفه\u200cها', icon: 'pricing', section: 'tools' },
  { href: '/api-keys', label: 'کلید API', icon: 'key', section: 'tools' },
  { href: '/search', label: 'جستجو', icon: 'search', section: 'tools' },
  { href: '/skills', label: 'اسکیل\u200cها', icon: 'sparkles', section: 'tools' },
  { href: '/assistants', label: 'دستیارها', icon: 'sparkles', section: 'tools' },
  { href: '/memory', label: 'حافظه', icon: 'sparkles', section: 'tools' },
  { href: '/tasks', label: 'تسک\u200cها', icon: 'calendar', section: 'tools' },
  { href: '/developer', label: 'توسعه\u200cدهندگان', icon: 'code', section: 'tools' },
  { href: '/profile', label: 'پروفایل', icon: 'profile', section: 'account' },
  { href: '/referral', label: 'دعوت', icon: 'referral', section: 'account' },
  { href: '/admin', label: 'مدیریت', icon: 'settings', section: 'account', admin: true },
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
    if (pathname === '/onboarding') return
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
  }, [loading, user, token, pathname, router])

  const isActive = (href: string) => pathname === href || pathname?.startsWith(href + '/')

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
    <div className="layout-shell" onClick={() => userMenuOpen && setUserMenuOpen(false)}>
      {/* ── Desktop Sidebar ─────────────────────────────────── */}
      <aside className="layout-sidebar hidden md:flex sidebar-glass">
        <div className="flex items-center gap-2 px-4 py-3.5">
          <div className="w-7 h-7 rounded-lg bg-[var(--accent)] flex items-center justify-center">
            <span className="text-white text-sm font-bold">M</span>
          </div>
          <Link href="/" className="text-base font-bold text-gradient tracking-tight">Multiai</Link>
        </div>
        <div className="divider" />

        <nav className="flex-1 px-3 overflow-y-auto sidebar-nav">
          {sections.map((section) => (
            <div key={section.key} className="mb-4">
              <div className="sidebar-section-label">{section.label}</div>
              {NAV.filter((n) => n.section === section.key).map((item) => (
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
            <Link href="/login" className="btn btn-primary w-full text-sm">ورود / ثبتنام</Link>
          )}
        </div>
      </aside>

      {/* ── Main Area ──────────────────────────────────────── */}
      <div className="layout-main">
        {/* Top bar */}
        <header className="topbar-glass">
          <div className="flex items-center gap-2">
            <button
              className="md:hidden btn btn-ghost btn-icon topbar-menu-btn"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              aria-label="منو"
            >
              <Icon name={sidebarOpen ? 'close' : 'menu'} size={20} />
            </button>
            <Link href="/" className="md:hidden text-base font-bold text-gradient">Multiai</Link>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => openPalette(true)}
              className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-[var(--radius-md)] border border-[var(--border)] text-xs text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text-secondary)] transition-all"
            >
              <Icon name="search" size={14} />
              <span>جستجو</span>
              <kbd className="text-[10px] bg-[var(--bg-surface)] px-1 rounded">⌘K</kbd>
            </button>
            <ThemeToggle />
            {!loading && !user && (
              <Link href="/login" className="btn btn-primary btn-sm">ورود</Link>
            )}
          </div>
        </header>

        {/* Content */}
        <main className="layout-content">{children}</main>

        {/* Mobile bottom nav */}
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
        <div className="md:hidden h-14" />
      </div>

      {/* ── Mobile sidebar overlay ─────────────────────────── */}
      <div className={`mobile-overlay ${sidebarOpen ? 'mobile-overlay--open' : ''}`} onClick={() => setSidebarOpen(false)}>
        <div className="mobile-overlay-bg" />
        <div
          className="mobile-drawer"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between px-4 py-3.5 border-b border-[var(--border)]">
              <span className="font-bold text-gradient">Multiai</span>
              <button onClick={() => setSidebarOpen(false)} className="btn btn-ghost btn-icon topbar-menu-btn">
                <Icon name="close" size={18} />
              </button>
          </div>
          <nav className="p-2">
            {NAV.map((item) => (
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
              <Link href="/login" className="btn btn-primary w-full">ورود / ثبتنام</Link>
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