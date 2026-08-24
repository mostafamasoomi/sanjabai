import { Skeleton } from './Skeleton'

/* ═══════════════════════════════════════════════════════════════════════════
   Loading skeleton for the summary cards + chart card. Split out of
   page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function UsageLoadingSkeleton() {
  return (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 16 }}>
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="card" style={{ padding: 20 }}>
            <Skeleton width={100} height={12} style={{ marginBottom: 12 }} />
            <Skeleton width={140} height={28} style={{ marginBottom: 8 }} />
            <Skeleton width={80} height={10} />
          </div>
        ))}
      </div>
      <div className="card" style={{ marginBottom: 16 }}>
        <Skeleton width={160} height={18} style={{ margin: 20 }} />
        <Skeleton width="100%" height={200} style={{ margin: '0 20px 20px' }} />
      </div>
    </>
  )
}
