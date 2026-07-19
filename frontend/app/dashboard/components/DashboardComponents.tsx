import { Icon, type IconName } from '@/components/ui/Icon'

export function StatCardSkeleton() {
  return (
    <div className="card">
      <div className="skeleton" style={{ width: '6rem', height: '0.75rem', marginBottom: '0.75rem' }} />
      <div className="skeleton" style={{ width: '8rem', height: '1.75rem', marginBottom: '0.5rem' }} />
      <div className="skeleton" style={{ width: '4rem', height: '0.625rem' }} />
    </div>
  )
}

export function LedgerSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="skeleton" style={{ width: '2rem', height: '2rem', borderRadius: 'var(--radius-sm)' }} />
            <div>
              <div className="skeleton" style={{ width: '6rem', height: '0.75rem', marginBottom: '0.375rem' }} />
              <div className="skeleton" style={{ width: '4rem', height: '0.625rem' }} />
            </div>
          </div>
          <div className="skeleton" style={{ width: '5rem', height: '0.875rem' }} />
        </div>
      ))}
    </div>
  )
}

export function StatCard({
  icon,
  label,
  value,
  sub,
  accentColor,
}: {
  icon: IconName
  label: string
  value: string
  sub?: string
  accentColor?: string
}) {
  return (
    <div className="card flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--text-secondary)] font-medium">{label}</span>
        <div className="w-8 h-8 rounded-[var(--radius-sm)] flex items-center justify-center" style={{ background: accentColor ? `${accentColor}15` : 'var(--accent-dim)' }}>
          <Icon name={icon} size={16} className="text-[var(--accent)]" />
        </div>
      </div>
      <div className="text-[1.75rem] font-bold text-[var(--text-primary)] tracking-tight">{value}</div>
      {sub && <div className="text-[11px] text-[var(--text-muted)]">{sub}</div>}
    </div>
  )
}

export function QuickAction({
  icon,
  label,
  description,
  onClick,
}: {
  icon: IconName
  label: string
  description: string
  onClick: () => void
}) {
  return (
    <button className="card-interactive" onClick={onClick} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '1rem', textAlign: 'right', width: '100%', cursor: 'pointer', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', background: 'var(--bg-surface)', transition: 'all var(--motion-fast) ease' }}>
      <div style={{ width: '2.5rem', height: '2.5rem', borderRadius: 'var(--radius-sm)', background: 'var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <Icon name={icon} size={18} className="text-[var(--accent)]" />
      </div>
      <div className="flex-1 min-w-0">
        <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.125rem' }}>{description}</div>
      </div>
      <span className="shrink-0 text-[var(--text-muted)]"><Icon name="arrowLeft" size={16} /></span>
    </button>
  )
}

export function LedgerRow({ entry, faDate, faTime, faNum }: { entry: { id: number; amount: number; balance_after: number; reason: string; created_at: string }; faDate: (iso: string) => string; faTime: (iso: string) => string; faNum: (n: number) => string }) {
  const isCredit = entry.amount > 0
  return (
    <div className="flex items-center justify-between py-3 border-b border-[var(--border)]">
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-8 h-8 rounded-[var(--radius-sm)] flex items-center justify-center shrink-0" style={{ background: isCredit ? 'color-mix(in srgb, var(--positive) 12%, transparent)' : 'color-mix(in srgb, var(--danger) 12%, transparent)' }}>
          <Icon name={isCredit ? 'wallet' : 'payment'} size={14} className={isCredit ? 'text-[var(--positive)]' : 'text-[var(--danger)]'} />
        </div>
        <div className="min-w-0">
          <div className="text-[13px] font-medium text-[var(--text-primary)] overflow-hidden text-ellipsis whitespace-nowrap">{entry.reason}</div>
          <div className="text-[11px] text-[var(--text-muted)] mt-0.5">{faDate(entry.created_at)} — {faTime(entry.created_at)}</div>
        </div>
      </div>
      <div className="text-end shrink-0 ms-4">
        <div className="text-sm font-semibold" style={{ color: isCredit ? 'var(--positive)' : 'var(--danger)' }}>
          {isCredit ? '+' : ''}{faNum(entry.amount)} <span className="text-[10px] font-normal">تومان</span>
        </div>
        <div className="text-[10px] text-[var(--text-muted)] text-end">موجودی: {faNum(entry.balance_after)}</div>
      </div>
    </div>
  )
}

export function InfoRow({ icon, label, value }: { icon: IconName; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 min-w-0">
        <span className="shrink-0 text-[var(--text-muted)]"><Icon name={icon} size={14} /></span>
        <span className="text-[13px] text-[var(--text-secondary)]">{label}</span>
      </div>
      <span className="text-[13px] font-semibold text-[var(--text-primary)] text-end">{value}</span>
    </div>
  )
}