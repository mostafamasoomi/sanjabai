import { Icon } from '@/components/ui/Icon'
import type { PaymentBannerState } from '../walletTypes'

// ─── Payment-return banner ──────────────────────────────────────────────────
// Renders the banner shown after the gateway callback redirects back with
// ?payment=success|failed|error (see hooks/usePaymentBanner.ts for how the
// state is derived and the URL param stripped). Nothing used to read this
// param, so a real charge landed with no feedback -- keep this exact.
export function PaymentBanner({ banner, onClose }: { banner: PaymentBannerState; onClose: () => void }) {
  if (!banner) return null
  return (
    <div
      role="status"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '14px 16px',
        marginBottom: 24,
        borderRadius: 'var(--radius-md)',
        border: `1px solid ${banner.ok ? 'var(--positive)' : 'var(--danger)'}`,
        background: banner.ok
          ? 'color-mix(in srgb, var(--positive) 12%, transparent)'
          : 'color-mix(in srgb, var(--danger) 12%, transparent)',
      }}
    >
      <span style={{ flexShrink: 0, color: banner.ok ? 'var(--positive)' : 'var(--danger)' }}>
        <Icon name={banner.ok ? 'check' : 'warning'} size={18} />
      </span>
      <span style={{ flex: 1, fontSize: 14, color: 'var(--text-primary)' }}>{banner.text}</span>
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
