import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════
   Not authenticated
   ═══════════════════════════════════════════════════════════════ */

export function UnauthenticatedView({ onLogin }: { onLogin: () => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: '1.5rem' }}>
      <Icon name="security" size={48} className="text-[var(--text-muted)]" />
      <div className="text-center">
        {/* h1: this branch replaces the whole page, so it owns the outline. */}
        <h1 className="page-title" style={{ marginBottom: '0.5rem' }}>وارد شوید</h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>برای مشاهده داشبورد، ابتدا وارد حساب کاربری خود شوید.</p>
      </div>
      <button className="btn" onClick={onLogin}>
        <Icon name="profile" size={16} />
        ورود به حساب
      </button>
    </div>
  )
}
