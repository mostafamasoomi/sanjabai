import { Icon } from '@/components/ui/Icon'
import { faNum, faPercent } from '@/lib/format'
import type { BillingSettings } from '../types'

/* ═══════════════════════════════════════════════════════════════
   PAYG Toggle Section
   ═══════════════════════════════════════════════════════════════ */

export function PaygSection({
  billingSettings,
  paygLoading,
  togglePayg,
  showHardLimitInput,
  setShowHardLimitInput,
  hardLimitValue,
  setHardLimitValue,
  hardLimitLoading,
  setHardLimit,
}: {
  billingSettings: BillingSettings
  paygLoading: boolean
  togglePayg: () => void
  showHardLimitInput: boolean
  setShowHardLimitInput: (value: boolean) => void
  hardLimitValue: string
  setHardLimitValue: (value: string) => void
  hardLimitLoading: boolean
  setHardLimit: () => void
}) {
  return (
    <div className="card dash-span-4" id="payg-section">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <span className="text-[var(--accent)]">
          <Icon name="payment" size={18} />
        </span>
        <h2 className="card-title">پرداخت به ازای مصرف</h2>
      </div>

      {/* Toggle row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.75rem 0',
        }}
      >
        <div>
          <div style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text-primary)' }}>
            پرداخت به ازای مصرف (PAYG)
          </div>
          <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            {billingSettings?.payg_enabled ? 'فعال' : 'غیرفعال'}
          </div>
        </div>
        <button
          onClick={togglePayg}
          disabled={paygLoading || !billingSettings}
          style={{
            width: '3rem',
            height: '1.625rem',
            borderRadius: '0.8125rem',
            border: 'none',
            cursor: paygLoading ? 'not-allowed' : 'pointer',
            background: billingSettings?.payg_enabled ? 'var(--accent)' : 'var(--border)',
            position: 'relative',
            transition: 'background 0.2s ease',
            opacity: paygLoading ? 0.6 : 1,
            flexShrink: 0,
          }}
        >
          <div
            style={{
              width: '1.25rem',
              height: '1.25rem',
              borderRadius: '50%',
              background: 'white',
              position: 'absolute',
              top: '0.1875rem',
              right: billingSettings?.payg_enabled ? '0.1875rem' : 'auto',
              left: billingSettings?.payg_enabled ? 'auto' : '0.1875rem',
              transition: 'all 0.2s ease',
              boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
            }}
          />
        </button>
      </div>

      {/* Hard limit display */}
      <div style={{ padding: '0.5rem 0', borderTop: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>سقف هزینه</span>
          <span className="num" style={{ fontSize: 'var(--fs-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>
            {billingSettings?.payg_hard_limit != null
              ? `${faNum(billingSettings.payg_hard_limit)} تومان`
              : 'تعیین نشده'
            }
          </span>
        </div>
        {showHardLimitInput ? (
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
            <input
              type="number"
              value={hardLimitValue}
              onChange={(e) => setHardLimitValue(e.target.value)}
              placeholder="مبلغ (تومان)"
              style={{
                flex: 1,
                padding: '0.5rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border)',
                background: 'var(--bg)',
                color: 'var(--text-primary)',
                fontSize: '0.8125rem',
                fontFeatureSettings: '"tnum"',
                outline: 'none',
              }}
            />
            <button
              className="btn btn-sm shrink-0"
              onClick={setHardLimit}
              disabled={hardLimitLoading}
            >
              {hardLimitLoading ? '...' : 'ذخیره'}
            </button>
            <button
              className="btn btn-sm"
              onClick={() => { setShowHardLimitInput(false); setHardLimitValue('') }}
              style={{ flexShrink: 0, background: 'transparent', border: '1px solid var(--border)' }}
            >
              لغو
            </button>
          </div>
        ) : (
          <button
            className="btn btn-sm"
            onClick={() => setShowHardLimitInput(true)}
            style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.375rem', marginTop: '0.25rem' }}
          >
            <Icon name="settings" size={14} />
            تنظیم سقف هزینه
          </button>
        )}
      </div>

      {/* Notify percentage */}
      {billingSettings?.notify_on_usage_pct != null && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.5rem 0', borderTop: '1px solid var(--border)' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>اعلام درصد مصرف</span>
          <span className="num" style={{ fontSize: 'var(--fs-sm)', fontWeight: 500, color: 'var(--text-primary)' }}>
            {faPercent(billingSettings.notify_on_usage_pct)}
          </span>
        </div>
      )}

      {/* Info text */}
      <div
        style={{
          marginTop: '0.75rem',
          padding: '0.625rem 0.75rem',
          borderRadius: 'var(--radius-sm)',
          background: 'var(--accent-dim)',
          fontSize: '0.6875rem',
          color: 'var(--text-secondary)',
          lineHeight: 1.6,
        }}
      >
        با فعال بودن پرداخت به ازای مصرف، از موجودی کیف پول شما کسر می‌شود
      </div>
    </div>
  )
}
