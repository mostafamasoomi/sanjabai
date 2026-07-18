'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { Icon, iconNames, type IconName } from './ui/Icon'

/* ═══════════════════════════════════════════════════════════════════════════
   Command Palette — ⌘K / Ctrl+K to open, keyboard-first navigation.
   Inspired by Linear, Raycast, VS Code.
   ═══════════════════════════════════════════════════════════════════════════ */

interface Command {
  id: string
  label: string
  icon: IconName
  shortcut?: string
  href?: string
  action?: () => void
  category: 'navigation' | 'action' | 'model'
}

export function useCommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const router = useRouter()

  const commands: Command[] = [
    { id: 'chat', label: 'چت', icon: 'chat', href: '/chat', shortcut: '⌘1', category: 'navigation' },
    { id: 'dashboard', label: 'داشبورد', icon: 'dashboard', href: '/dashboard', shortcut: '⌘2', category: 'navigation' },
    { id: 'models', label: 'مدل‌ها', icon: 'models', href: '/models', shortcut: '⌘3', category: 'navigation' },
    { id: 'wallet', label: 'کیف پول', icon: 'wallet', href: '/wallet', shortcut: '⌘4', category: 'navigation' },
    { id: 'pricing', label: 'تعرفه‌ها', icon: 'pricing', href: '/pricing', category: 'navigation' },
    { id: 'playground', label: 'Playground', icon: 'playground', href: '/playground', category: 'navigation' },
    { id: 'compare', label: 'مقایسه مدل‌ها', icon: 'compare', href: '/compare', category: 'navigation' },
    { id: 'profile', label: 'پروفایل', icon: 'profile', href: '/profile', category: 'navigation' },
    { id: 'api-keys', label: 'کلیدهای API', icon: 'key', href: '/api-keys', category: 'navigation' },
    { id: 'admin', label: 'پنل مدیریت', icon: 'settings', href: '/admin', category: 'navigation' },
    { id: 'referral', label: 'دعوت دوستان', icon: 'referral', href: '/referral', category: 'action' },
  ]

  const filtered = query
    ? commands.filter((c) => c.label.includes(query) || c.id.includes(query))
    : commands

  const grouped: Record<string, Command[]> = {}
  for (const cmd of filtered) {
    if (!grouped[cmd.category]) grouped[cmd.category] = []
    grouped[cmd.category].push(cmd)
  }

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', down)
    return () => document.removeEventListener('keydown', down)
  }, [])

  useEffect(() => {
    if (open) {
      setQuery('')
      setActiveIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  const execute = useCallback(
    (cmd: Command) => {
      setOpen(false)
      if (cmd.href) router.push(cmd.href)
      if (cmd.action) cmd.action()
    },
    [router],
  )

  const handleKey = (e: React.KeyboardEvent) => {
    const flat = Object.values(grouped).flat()
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => (i + 1) % flat.length)
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => (i - 1 + flat.length) % flat.length)
    }
    if (e.key === 'Enter' && flat[activeIndex]) {
      execute(flat[activeIndex])
    }
  }

  const categoryLabels: Record<string, string> = {
    navigation: 'ناوبری',
    action: 'عملیات',
    model: 'مدل‌ها',
  }

  const CommandPalette = open ? (
    <div role="button" tabIndex={0} className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]" onClick={() => setOpen(false)}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-lg bg-[var(--bg-elevated)] border border-[var(--border)] rounded-[var(--radius-xl)] shadow-[var(--shadow-lg)] overflow-hidden fade-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border)]">
          <Icon name="search" size={18} className="text-[var(--text-muted)]" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setActiveIndex(0) }}
            onKeyDown={handleKey}
            placeholder="جستجو در منوها..."
            className="flex-1 bg-transparent border-none outline-none text-[var(--text-primary)] text-sm placeholder:text-[var(--text-muted)] font-[var(--font-sans)]"
          />
          <kbd className="text-xs text-[var(--text-muted)] bg-[var(--bg-surface)] px-2 py-0.5 rounded-[var(--radius-sm)] border border-[var(--border)]">
            ESC
          </kbd>
        </div>

        <div className="max-h-[320px] overflow-y-auto p-2">
          {Object.entries(grouped).map(([category, cmds]) => (
            <div key={category} className="mb-3">
              <div className="px-3 py-1 text-xs text-[var(--text-muted)] font-medium">
                {categoryLabels[category] || category}
              </div>
              {cmds.map((cmd) => {
                const flatIndex = Object.values(grouped).flat().indexOf(cmd)
                const isActive = flatIndex === activeIndex
                return (
                  <button
                    key={cmd.id}
                    onClick={() => execute(cmd)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] text-sm transition-all ${
                      isActive
                        ? 'bg-[var(--accent-dim)] text-[var(--accent)]'
                        : 'text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    <Icon name={cmd.icon} size={18} />
                    <span className="flex-1 text-right">{cmd.label}</span>
                    {cmd.shortcut && (
                      <kbd className="text-xs text-[var(--text-muted)] bg-[var(--bg-surface)] px-1.5 py-0.5 rounded-[var(--radius-sm)]">
                        {cmd.shortcut}
                      </kbd>
                    )}
                  </button>
                )
              })}
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="text-center py-8 text-[var(--text-muted)] text-sm">نتیجه‌ای یافت نشد</div>
          )}
        </div>

        <div className="px-4 py-2 border-t border-[var(--border)] flex items-center gap-4 text-xs text-[var(--text-muted)]">
          <span>↑↓ پیمایش</span>
          <span>↵ انتخاب</span>
          <span>ESC بستن</span>
        </div>
      </div>
    </div>
  ) : null

  return { open, setOpen, CommandPalette }
}