/* ═══════════════════════════════════════════════════════════════════════════
   Skeleton
   Split out of page.tsx verbatim -- no behaviour change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function Skeleton({ width, height, style }: { width?: number | string; height?: number; style?: React.CSSProperties }) {
  return <div className="skeleton" style={{ width, height, borderRadius: 'var(--radius-sm)', ...style }} />
}
