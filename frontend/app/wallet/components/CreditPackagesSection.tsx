import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { fmtToman } from '../walletHelpers'
import { EmptyStateIcon } from './WalletEmptyState'
import type { CreditPackage } from '../walletTypes'

// ─── Credit Packages Section ────────────────────────────────────────────────
// Every money value here (base_amount, total_credits, the bonus delta) is a
// raw, whole-toman integer straight from the API, passed straight into
// faNum / fmtToman -- no division, no multiplication, no unit conversion.
export function CreditPackagesSection({
  creditPackages,
  purchasingPkgId,
  modelOutputRates,
  onPurchase,
}: {
  creditPackages: CreditPackage[]
  purchasingPkgId: string | null
  modelOutputRates: Record<string, number>
  onPurchase: (pkgId: string) => void
}) {
  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
        <Icon name="gift" size={16} className="text-accent" />
        <h2 className="card-title">بسته‌های اعتباری</h2>
        {creditPackages.length > 0 && (
          <span className="badge badge-accent" style={{ marginLeft: 4 }}>{faNum(creditPackages.length)}</span>
        )}
      </div>

      {creditPackages.length === 0 ? (
        <EmptyStateIcon icon="gift" title="بسته‌ای موجود نیست" desc="در حال حاضر بسته اعتباری برای خرید وجود ندارد." />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
          {creditPackages.map((pkg) => {
            const isPurchasing = purchasingPkgId === pkg.id
            const baseToman = faNum(pkg.base_amount)
            const bonusToman = pkg.bonus_percent > 0
              ? faNum(pkg.total_credits - pkg.base_amount)
              : null
            const outputRate = pkg.model_id ? modelOutputRates[pkg.model_id] : undefined
            const approxTokens = outputRate ? Math.round((pkg.total_credits / outputRate) * 1_000_000) : null
            return (
              <div
                key={pkg.id}
                className="card"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  padding: 20,
                  position: 'relative',
                  overflow: 'hidden',
                  borderColor: pkg.bonus_percent > 0 ? 'var(--accent)' : undefined,
                  borderWidth: pkg.bonus_percent > 0 ? 1.5 : undefined,
                }}
              >
                {pkg.bonus_percent > 0 && (
                  <span
                    style={{
                      position: 'absolute',
                      top: 12,
                      left: 12,
                      background: 'var(--accent)',
                      color: 'var(--text-on-accent)',
                      fontSize: 11,
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: 'var(--radius-sm)',
                    }}
                  >
                    +{pkg.bonus_percent}% بونوس
                  </span>
                )}

                <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
                  {pkg.name_fa}
                </h3>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: pkg.model_id ? 6 : 16 }}>
                  {pkg.name_en}
                </p>
                {pkg.model_id && (
                  <span
                    className="badge"
                    style={{ alignSelf: 'flex-start', marginBottom: 16, fontFamily: 'monospace', fontSize: 11 }}
                  >
                    {pkg.model_id}
                  </span>
                )}

                <div className="flex-1">
                  <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text-primary)', marginBottom: 4, fontFeatureSettings: '"tnum"' }}>
                    {faNum(pkg.total_credits)} <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-muted)' }}>تومان</span>
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                    شما {baseToman} تومان پرداخت می‌کنید
                  </p>
                  {bonusToman && (
                    <p style={{ fontSize: 12, color: 'var(--positive)', marginBottom: 8 }}>
                      + {bonusToman} تومان بونوس
                    </p>
                  )}
                  <p style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    معادل {fmtToman(pkg.total_credits)}
                  </p>
                  {approxTokens !== null && (
                    <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                      ≈ {faNum(Math.round(approxTokens / 1_000_000))} میلیون توکن {pkg.model_id} (بر اساس نرخ خروجی فعلی)
                    </p>
                  )}
                </div>

                <button
                  className={`btn btn-primary`}
                  onClick={() => onPurchase(pkg.id)}
                  disabled={isPurchasing || purchasingPkgId !== null}
                  style={{
                    marginTop: 16,
                    width: '100%',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                    opacity: (isPurchasing || (purchasingPkgId !== null && !isPurchasing)) ? 0.5 : 1,
                  }}
                >
                  <Icon name={isPurchasing ? 'refresh' : 'payment'} size={14} className={isPurchasing ? 'spin' : ''} />
                  {isPurchasing ? 'در حال پردازش...' : 'خرید بسته'}
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
