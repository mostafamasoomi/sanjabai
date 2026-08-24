import { Icon } from '@/components/ui/Icon'
import { LedgerRow } from './LedgerRow'
import type { LedgerEntry } from '../types'

/* ═══════════════════════════════════════════════════════════════
   Recent Activity / Ledger — the widest card on the page, because it
   is a list of long rows and the only one that benefits from run.
   ═══════════════════════════════════════════════════════════════ */

export function RecentActivityCard({
  recentLedger,
  onViewAll,
  onTopUp,
}: {
  recentLedger: LedgerEntry[]
  onViewAll: () => void
  onTopUp: () => void
}) {
  return (
    <div className="card dash-span-8 overflow-hidden">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <div className="flex items-center gap-2">
          <span className="text-[var(--accent)]">
            <Icon name="history" size={18} />
          </span>
          <h2 className="card-title">فعالیت اخیر</h2>
        </div>
        <button
          className="btn btn-sm"
          onClick={onViewAll}
          style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem' }}
        >
          مشاهده همه
          <Icon name="arrowLeft" size={12} />
        </button>
      </div>

      {recentLedger.length === 0 ? (
        <div className="empty-state">
          <span className="empty-state__icon">
            <Icon name="history" size={22} />
          </span>
          <p className="empty-state__title">هنوز تراکنشی ثبت نشده است</p>
          <p className="empty-state__desc">
            پس از اولین شارژ یا مصرف، تراکنش‌ها اینجا فهرست می‌شوند.
          </p>
          <button className="btn btn-sm btn-secondary" onClick={onTopUp}>
            <Icon name="wallet" size={14} />
            شارژ کیف پول
          </button>
        </div>
      ) : (
        <div className="flex flex-col">
          {recentLedger.map((entry) => (
            <LedgerRow key={entry.id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  )
}
