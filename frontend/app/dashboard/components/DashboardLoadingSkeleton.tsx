import { StatCardSkeleton, LedgerSkeleton } from './Skeletons'

/* ═══════════════════════════════════════════════════════════════
   Loading state
   ═══════════════════════════════════════════════════════════════ */

export function DashboardLoadingSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      {/* Header skeleton */}
      <div className="flex justify-between items-center">
        <div>
          <div className="skeleton" style={{ width: '12rem', height: '1.75rem', marginBottom: '0.5rem' }} />
          <div className="skeleton" style={{ width: '8rem', height: '0.875rem' }} />
        </div>
        <div className="skeleton" style={{ width: '5rem', height: '1.75rem', borderRadius: 'var(--radius-lg)' }} />
      </div>

      {/* Stat cards skeleton */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-4)' }}>
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
      </div>

      {/* Content skeleton */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1.5rem' }}>
        <div className="card">
          <div className="skeleton" style={{ width: '8rem', height: '1rem', marginBottom: '1rem' }} />
          <LedgerSkeleton />
        </div>
        <div className="card">
          <div className="skeleton" style={{ width: '6rem', height: '1rem', marginBottom: '1rem' }} />
          <div className="skeleton" style={{ width: '100%', height: '6rem' }} />
        </div>
      </div>
    </div>
  )
}
