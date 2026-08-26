'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { PRESET_AMOUNTS, MIN_TOPUP, MAX_TOPUP } from '../walletHelpers'
import { topupCardStrings } from './TopupCard.strings'

// ─── Topup Card ─────────────────────────────────────────────────────────────
// All amounts here (preset values, effectiveAmount, MIN_TOPUP) are raw,
// whole tomans passed straight into f.num/f.price -- no arithmetic on any of
// them.
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
  const lang = useLang()
  const s = topupCardStrings(lang)
  const f = fmt(lang)

  return (
    <div className="card wallet-topup-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
        <div className="wallet-topup-icon">
          <Icon name="plus" size={14} className="text-accent" />
        </div>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontWeight: 600 }}>{s.title}</span>
      </div>

      {/* Preset buttons */}
      <div className="wallet-preset-grid">
        {PRESET_AMOUNTS.map((value) => (
          <button
            key={value}
            className={`wallet-preset-btn ${selectedPreset === value ? 'wallet-preset-active' : ''}`}
            onClick={() => onPreset(value)}
          >
            {f.compact(value)}
            <span className="wallet-preset-sub">
              {f.price(value)}
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
          placeholder={s.customAmountPlaceholder}
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
          {s.minAmount(f.num(MIN_TOPUP))}
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
        {busy ? s.processing : s.chargeButton(effectiveAmount > 0 ? f.num(effectiveAmount) : null)}
      </button>
    </div>
  )
}
