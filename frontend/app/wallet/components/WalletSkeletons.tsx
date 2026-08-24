// ─── Skeleton Components ────────────────────────────────────────────────────
export function BalanceSkeleton() {
  return (
    <div className="card wallet-balance-card" style={{ minHeight: 200 }}>
      <div className="skeleton" style={{ width: 100, height: 14, borderRadius: 'var(--radius-sm)', marginBottom: 16 }} />
      <div className="skeleton" style={{ width: 260, height: 48, borderRadius: 'var(--radius-md)', marginBottom: 12 }} />
      <div className="skeleton" style={{ width: 140, height: 14, borderRadius: 'var(--radius-sm)' }} />
    </div>
  )
}

export function TopupSkeleton() {
  return (
    <div className="card" style={{ minHeight: 200 }}>
      <div className="skeleton" style={{ width: 80, height: 14, borderRadius: 'var(--radius-sm)', marginBottom: 16 }} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="skeleton" style={{ height: 48, borderRadius: 'var(--radius-md)' }} />
        ))}
      </div>
      <div className="skeleton" style={{ width: '100%', height: 44, borderRadius: 'var(--radius-md)', marginTop: 12 }} />
    </div>
  )
}

export function TableSkeleton() {
  return (
    <div className="card">
      <div className="skeleton" style={{ width: 120, height: 18, borderRadius: 'var(--radius-sm)', marginBottom: 20 }} />
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
          <div className="skeleton" style={{ flex: 1, height: 16, borderRadius: 'var(--radius-sm)' }} />
          <div className="skeleton" style={{ width: 80, height: 16, borderRadius: 'var(--radius-sm)' }} />
          <div className="skeleton" style={{ width: 100, height: 16, borderRadius: 'var(--radius-sm)' }} />
        </div>
      ))}
    </div>
  )
}

export function PackagesSkeleton() {
  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div className="skeleton" style={{ width: 160, height: 18, borderRadius: 'var(--radius-sm)', marginBottom: 20 }} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="skeleton" style={{ height: 200, borderRadius: 'var(--radius-md)' }} />
        ))}
      </div>
    </div>
  )
}
