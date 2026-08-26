'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { topupConfirmModalStrings } from './TopupConfirmModal.strings'

// ─── Confirmation Modal ─────────────────────────────────────────────────────
// effectiveAmount is raw, whole tomans -- straight into f.price, no arithmetic.
export function TopupConfirmModal({
  show,
  effectiveAmount,
  busy,
  onCancel,
  onConfirm,
}: {
  show: boolean
  effectiveAmount: number
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const lang = useLang()
  const s = topupConfirmModalStrings(lang)
  const f = fmt(lang)
  if (!show) return null
  return (
    <div className="wallet-modal-overlay" onClick={onCancel}>
      <div className="card wallet-modal-card" onClick={(e) => e.stopPropagation()}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <div className="wallet-modal-icon">
            <Icon name="wallet" size={28} className="text-accent" />
          </div>
          <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>{s.title}</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 4 }}>
            {s.confirmQuestion}
          </p>
          <p className="wallet-modal-amount">
            {f.price(effectiveAmount)}
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>{s.areYouSure}</p>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn btn-secondary flex-1"
            onClick={onCancel}
          >
            {s.cancel}
          </button>
          <button
            className="btn btn-lg btn-primary"
            onClick={onConfirm}
            disabled={busy}
            style={{ flex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
          >
            <Icon name="check" size={16} />
            {busy ? s.processing : s.confirmAndPay}
          </button>
        </div>
      </div>
    </div>
  )
}
