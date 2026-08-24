import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'

// ─── Confirmation Modal ─────────────────────────────────────────────────────
// effectiveAmount is raw, whole tomans -- straight into faNum, no arithmetic.
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
  if (!show) return null
  return (
    <div className="wallet-modal-overlay" onClick={onCancel}>
      <div className="card wallet-modal-card" onClick={(e) => e.stopPropagation()}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <div className="wallet-modal-icon">
            <Icon name="wallet" size={28} className="text-accent" />
          </div>
          <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>تایید شارژ</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginBottom: 4 }}>
            آیا از شارژ حساب به مبلغ
          </p>
          <p className="wallet-modal-amount">
            {faNum(effectiveAmount)} تومان
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>اطمینان دارید؟</p>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn btn-secondary flex-1"
            onClick={onCancel}
          >
            انصراف
          </button>
          <button
            className="btn btn-lg btn-primary"
            onClick={onConfirm}
            disabled={busy}
            style={{ flex: 1, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
          >
            <Icon name="check" size={16} />
            {busy ? 'در حال پردازش...' : 'تایید و پرداخت'}
          </button>
        </div>
      </div>
    </div>
  )
}
