'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { loadStateStrings } from './LoadState.strings'

/* Load/refresh affordances shared by the self-contained admin sections.
   Each section fetches its own data now, so each one also owns its own
   refresh button — the shell no longer has a global one to offer (it used
   to call a `loadAll()` that most pages had already stopped reading). */

/** A failed load, stated plainly, with the way out. Never a blank table:
    "the request failed" and "there is nothing here" must not look alike. */
export function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  const s = loadStateStrings(useLang())
  return (
    <div className="admin-card" style={{ borderRight: '3px solid var(--danger)' }}>
      <div className="flex items-center gap-3">
        <Icon name="warning" size={18} style={{ color: 'var(--danger)' }} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium" style={{ color: 'var(--danger)' }}>{s.loadFailed}</p>
          <p className="text-xs text-muted mt-1 break-words">{message}</p>
        </div>
        <button className="btn btn-sm" onClick={onRetry}>
          <Icon name="refresh" size={14} />
          <span>{s.retry}</span>
        </button>
      </div>
    </div>
  )
}

export function RefreshButton({ onClick, busy }: { onClick: () => void; busy?: boolean }) {
  const s = loadStateStrings(useLang())
  return (
    <button className="btn btn-sm" onClick={onClick} disabled={busy} title={s.refresh}>
      {busy ? (
        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
      ) : (
        <Icon name="refresh" size={16} />
      )}
    </button>
  )
}

export function CardSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="admin-card">
          <div className="skeleton h-3 w-20 mb-3 rounded" />
          <div className="skeleton h-7 w-16 rounded" />
        </div>
      ))}
    </div>
  )
}
