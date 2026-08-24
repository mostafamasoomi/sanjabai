import Link from 'next/link'
import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════════════════
   "Not logged in" state. Split out of page.tsx verbatim -- no behaviour
   change.
   ═══════════════════════════════════════════════════════════════════════════ */

export function UnauthenticatedUsage() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
      <div className="card" style={{ textAlign: 'center', padding: '48px 32px', maxWidth: 400 }}>
        <div style={{ width: 56, height: 56, borderRadius: 'var(--radius-full)', background: 'var(--accent-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
          <Icon name="chart" size={28} className="text-accent" />
        </div>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>گزارش مصرف</h2>
        <p style={{ color: 'var(--text-muted)', marginBottom: 24 }}>برای مشاهده گزارش مصرف، ابتدا وارد حساب خود شوید.</p>
        <Link href="/login" className="btn btn-lg btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          ورود
          <Icon name="arrowLeft" size={16} />
        </Link>
      </div>
    </div>
  )
}
