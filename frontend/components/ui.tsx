'use client'

import { useState, useEffect, useCallback } from 'react'
import { Icon, type IconName } from '@/components/ui/Icon'

/* ═══════════════════════════════
   Toast notification system
   ═══════════════════════════════ */

type ToastType = 'success' | 'error' | 'info'

let toastListeners: ((msg: string, type: ToastType) => void)[] = []

export function toast(msg: string, type: ToastType = 'info') {
  toastListeners.forEach((fn) => fn(msg, type))
}

export function ToastContainer() {
  const [items, setItems] = useState<{ id: number; msg: string; type: ToastType }[]>([])

  const add = useCallback((msg: string, type: ToastType) => {
    const id = Date.now()
    setItems((p) => [...p, { id, msg, type }])
    setTimeout(() => setItems((p) => p.filter((x) => x.id !== id)), 3000)
  }, [])

  useEffect(() => {
    toastListeners.push(add)
    return () => { toastListeners = toastListeners.filter((fn) => fn !== add) }
  }, [add])

  if (items.length === 0) return null

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[9999] flex flex-col gap-2 pointer-events-none">
      {items.map((t) => (
        <div
          key={t.id}
          className={`toast show fade-in ${
            t.type === 'success' ? 'toast-success' : t.type === 'error' ? 'toast-error' : ''
          }`}
          style={{ position: 'static', transform: 'none' }}
        >
          {t.msg}
        </div>
      ))}
    </div>
  )
}

/* ═══════════════════════════════
   Skeleton loader
   ═══════════════════════════════ */

export function Skeleton({ className = '', width, height }: { className?: string; width?: string; height?: string }) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ width: width || '100%', height: height || '1rem' }}
    />
  )
}

/* ═══════════════════════════════
   Empty state
   ═══════════════════════════════ */

export function EmptyState({ icon = 'models', title, description }: { icon?: IconName; title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="mb-3 text-[var(--text-muted)]">
        <Icon name={icon} size={40} />
      </div>
      <h3 className="text-lg font-semibold text-[var(--text-dim)]">{title}</h3>
      {description && <p className="text-sm text-[var(--text-muted)] mt-1 max-w-sm">{description}</p>}
    </div>
  )
}

/* ═══════════════════════════════
   Spinner
   ═══════════════════════════════ */

export function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sizes = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-8 h-8' }
  return (
    <div className={`${sizes[size]} border-2 border-[var(--border)] border-t-[var(--accent)] rounded-full animate-spin`} />
  )
}

/* ═══════════════════════════════
   Modal
   ═══════════════════════════════ */

export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title?: string
  children: React.ReactNode
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative bg-[var(--bg-elev)] border border-[var(--border-strong)] rounded-[var(--radius-xl)] p-6 max-w-lg w-full shadow-[var(--shadow-lg)] fade-in"
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold">{title}</h2>
            <button onClick={onClose} className="btn btn-ghost btn-icon" aria-label="بستن">
              <Icon name="close" size={18} />
            </button>
          </div>
        )}
        {children}
      </div>
    </div>
  )
}

/* ═══════════════════════════════
   Tabs
   ═══════════════════════════════ */

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: string; label: string }[]
  active: string
  onChange: (key: string) => void
}) {
  return (
    <div className="flex gap-1 border-b border-[var(--border)] pb-0">
      {tabs.map((t) => (
        <button
          key={t.key}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors -mb-[1px] border-b-2 ${
            active === t.key
              ? 'text-[var(--accent)] border-[var(--accent)]'
              : 'text-[var(--text-dim)] border-transparent hover:text-[var(--text)]'
          }`}
          onClick={() => onChange(t.key)}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

/* ═══════════════════════════════
   Progress bar
   ═══════════════════════════════ */

export function Progress({ value, max = 100, size = 'md' }: { value: number; max?: number; size?: 'sm' | 'md' | 'lg' }) {
  const pct = Math.min(100, Math.round((value / max) * 100))
  const heights = { sm: 'h-1', md: 'h-2', lg: 'h-3' }
  const color = pct > 90 ? 'var(--danger)' : pct > 70 ? 'var(--warn)' : 'var(--accent)'
  return (
    <div className={`w-full bg-[var(--bg-elev2)] rounded-full ${heights[size]}`}>
      <div
        className={`${heights[size]} rounded-full transition-all duration-500`}
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  )
}