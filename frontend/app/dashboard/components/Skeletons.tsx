/* ═══════════════════════════════════════════════════════════════
   Skeleton helpers
   ═══════════════════════════════════════════════════════════════ */

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
