import { Icon } from '@/components/ui/Icon'

/* ═══════════════════════════════════════════════════════════════
   Payment-return banner
   ═══════════════════════════════════════════════════════════════ */

export function PaymentBanner({
  banner,
  onClose,
}: {
  banner: { ok: boolean; text: string }
  onClose: () => void
}) {
  return (
    <div
      className="dash-span-12"
      role="status"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        padding: '0.875rem 1rem',
        borderRadius: 'var(--radius-md)',
        border: `1px solid ${banner.ok ? 'var(--positive)' : 'var(--danger)'}`,
        background: banner.ok
          ? 'color-mix(in srgb, var(--positive) 12%, transparent)'
          : 'color-mix(in srgb, var(--danger) 12%, transparent)',
      }}
    >
      <span className={banner.ok ? 'text-[var(--positive)]' : 'text-[var(--danger)]'} style={{ flexShrink: 0 }}>
        <Icon name={banner.ok ? 'check' : 'warning'} size={18} />
      </span>
      <span style={{ flex: 1, fontSize: '0.875rem', color: 'var(--text-primary)' }}>{banner.text}</span>
      <button
        onClick={onClose}
        aria-label="بستن"
        style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4, display: 'inline-flex' }}
      >
        <Icon name="close" size={16} />
      </button>
    </div>
  )
}
