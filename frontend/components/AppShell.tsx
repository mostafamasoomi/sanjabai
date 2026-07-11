'use client'

import { useState, useEffect } from 'react'
import { usePathname } from 'next/navigation'
import { AuthProvider, useAuth } from '@/lib/auth'
import { ToastContainer } from '@/components/ui'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Icon, type IconName } from '@/components/ui/Icon'
import { useCommandPalette } from '@/components/CommandPalette'

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
  { href: '/playground', label: 'Playground', icon: 'playground', section: 'main' },
  { href: '/dashboard', label: 'داشبورد', icon: 'dashboard', section: 'tools' },
  { href: '/wallet', label: 'کیف پول', icon: 'wallet', section: 'tools' },
  { href: '/pricing', label: 'تعرفه\u200cها', icon: 'pricing', section: 'tools' },
  { href: '/api-keys', label: 'کلید API', icon: 'key', section: 'tools' },
  { href: '/profile', label: 'پروفایل', icon: 'profile', section: 'account' },
  { href: '/referral', label: 'دعوت', icon: 'referral', section: 'account' },
  { href: '/admin', label: 'مدیریت', icon: 'settings', section: 'account', admin: true },
]

/* ═══════════════════════════════════════════════════════════════════════════
   Inner layout
   ═══════════════════════════════════════════════════════════════════════════ */

function AppShellInner({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth()
  const pathname = usePathname()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { CommandPalette, setOpen: openPalette } = useCommandPalette()

  useEffect(() => { setSidebarOpen(false) }, [pathname])

  const isActive = (href: string) => pathname === href || pathname?.startsWith(href + '/')

  const sections = [
    { key: 'main', label: 'اصلی' },
    { key: 'tools', label: 'ابزارها' },
    { key: 'account', label: 'حساب' },
  ]

  return (
    <div className="layout-shell">
      {/* ── Desktop Sidebar ─────────────────────────────────── */}
      <aside className="layout-sidebar hidden md:flex">
        <div className="flex items-center gap-2 px-4 py-3.5">
          <div className="w-7 h-7 rounded-lg bg-[var(--accent)] flex items-center justify-center">
            <span className="text-white text-sm font-bold">M</span>
          </div>
          <a href="/" className="text-base font-bold text-gradient tracking-tight">Multiai</a>
        </div>
        <div className="divider" />

        <nav className="flex-1 px-2 overflow-y-auto">
          {sections.map((section) => (
            <div key={section.key} className="mb-4">
              <div className="px-3 py-1 text-xs text-[var(--text-muted)] font-medium">{section.label}</div>
              {NAV.filter((n) => n.section === section.key).map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 px-3 py-2 rounded-[var(--radius-md)] text-sm transition-all ${
                    isActive(item.href)
                      ? 'bg-[var(--accent-dim)] text-[var(--accent)] font-medium'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  <Icon name={item.icon} size={18} />
                  <span>{item.label}</span>
                </a>
              ))}
            </div>
          ))}
        </nav>

        <div className="p-3 border-t border-[var(--border)]">
          {loading ? (
            <div className="skeleton h-8 rounded-lg" />
          ) : user ? (
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-[var(--accent-dim)] flex items-center justify-center text-sm font-medium text-[var(--accent)]">
                {user.email?.[0]?.toUpperCase() || '?'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium truncate">{user.email}</div>
                <button onClick={logout} className="text-xs text-[var(--text-muted)] hover:text-[var(--danger)] transition-colors">
                  خروج
                </button>
              </div>
            </div>
          ) : (
            <a href="/login" className="btn btn-primary w-full text-sm">ورود / ثبت‌نام</a>
          )}
        </div>
      </aside>

      {/* ── Main Area ──────────────────────────────────────── */}
      <div className="layout-main">
        {/* Top bar */}
        <header className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--border)] bg-[var(--bg-base)]/80 backdrop-blur sticky top-0 z-20">
          <div className="flex items-center gap-2">
            <button
              className="md:hidden btn btn-ghost btn-icon"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              aria-label="منو"
            >
              <Icon name={sidebarOpen ? 'close' : 'menu'} size={20} />
            </button>
            <a href="/" className="md:hidden text-base font-bold text-gradient">Multiai</a>
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
              <a href="/login" className="btn btn-primary btn-sm">ورود</a>
            )}
          </div>
        </header>

        {/* Content */}
        <main className="layout-content">{children}</main>

        {/* Mobile bottom nav */}
        <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-[var(--bg-surface)]/95 backdrop-blur border-t border-[var(--border)] flex justify-around py-2 z-20 safe-bottom">
          {NAV.filter((n) => n.section === 'main').slice(0, 4).map((item) => (
            <a
              key={item.href}
              href={item.href}
              className={`flex flex-col items-center gap-0.5 text-xs px-2 py-1 rounded-lg transition-colors min-w-0 ${
                isActive(item.href) ? 'text-[var(--accent)]' : 'text-[var(--text-muted)]'
              }`}
            >
              <Icon name={item.icon} size={20} />
              <span className="truncate text-[10px]">{item.label}</span>
            </a>
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
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 md:hidden" onClick={() => setSidebarOpen(false)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div
            className="absolute top-0 right-0 bottom-0 w-72 bg-[var(--bg-surface)] border-l border-[var(--border)] fade-in overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3.5 border-b border-[var(--border)]">
              <span className="font-bold text-gradient">Multiai</span>
              <button onClick={() => setSidebarOpen(false)} className="btn btn-ghost btn-icon">
                <Icon name="close" size={18} />
              </button>
            </div>
            <nav className="p-2">
              {NAV.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] text-sm transition-all ${
                    isActive(item.href)
                      ? 'bg-[var(--accent-dim)] text-[var(--accent)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
                  }`}
                >
                  <Icon name={item.icon} size={18} />
                  <span>{item.label}</span>
                </a>
              ))}
            </nav>
            <div className="p-3 border-t border-[var(--border)]">
              {user ? (
                <div>
                  <div className="text-xs text-[var(--text-muted)] mb-2">{user.email}</div>
                  <button onClick={logout} className="btn btn-ghost btn-sm w-full text-[var(--danger)]">خروج</button>
                </div>
              ) : (
                <a href="/login" className="btn btn-primary w-full">ورود / ثبت‌نام</a>
              )}
            </div>
          </div>
        </div>
      )}

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