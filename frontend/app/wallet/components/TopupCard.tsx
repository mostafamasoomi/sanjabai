import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { PRESET_AMOUNTS, MIN_TOPUP, MAX_TOPUP } from '../walletHelpers'

// ─── Topup Card ─────────────────────────────────────────────────────────────
// All amounts here (preset values, effectiveAmount, MIN_TOPUP) are raw,
// whole tomans passed straight into faNum -- no arithmetic on any of them.
export function TopupCard({
  topupAmount,
  selectedPreset,
  effectiveAmount,
  busy,
  onPreset,
  onCustomAmount,
  onInitiate,
}: {
  topupAmount: string
  selectedPreset: number | null
  effectiveAmount: number
  busy: boolean
  onPreset: (val: number) => void
  onCustomAmount: (v: string) => void
  onInitiate: () => void
}) {
  return (
    <div className="card wallet-topup-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
        <div className="wallet-topup-icon">
          <Icon name="plus" size={14} className="text-accent" />
        </div>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 600 }}>شارژ حساب</span>
      </div>

      {/* Preset buttons */}
      <div className="wallet-preset-grid">
        {PRESET_AMOUNTS.map((p) => (
          <button
            key={p.value}
            className={`wallet-preset-btn ${selectedPreset === p.value ? 'wallet-preset-active' : ''}`}
            onClick={() => onPreset(p.value)}
          >
            {p.label}
            <span className="wallet-preset-sub">
              {faNum(p.value)} تومان
            </span>
          </button>
        ))}
      </div>

      {/* Custom amount input */}
      <div style={{ position: 'relative', marginBottom: 12 }}>
        <Icon
          name="payment"
          size={16}
          style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}
        />
        <input
          className="input"
          type="number"
          value={topupAmount}
          onChange={(e) => onCustomAmount(e.target.value)}
          placeholder="مبلغ دلخواه (تومان)"
          min={MIN_TOPUP}
          max={MAX_TOPUP}
          style={{
            paddingRight: 36,
            fontFeatureSettings: '"tnum"',
            width: '100%',
          }}
        />
      </div>

      {effectiveAmount > 0 && effectiveAmount < MIN_TOPUP && (
        <p style={{ fontSize: 11, color: 'var(--danger)', marginBottom: 8 }}>
          حداقل مبلغ: {faNum(MIN_TOPUP)} تومان
        </p>
      )}

      <button
        className="btn btn-lg btn-primary wallet-topup-btn"
        onClick={onInitiate}
        disabled={busy || effectiveAmount <= 0}
        style={{
          width: '100%',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          opacity: busy || effectiveAmount <= 0 ? 0.5 : 1,
        }}
      >
        <Icon name="send" size={16} />
        {busy ? 'در حال پردازش...' : `شارژ ${effectiveAmount > 0 ? faNum(effectiveAmount) + ' تومان' : 'حساب'}`}
      </button>
    </div>
  )
}
