'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { EmptyStateIcon } from './WalletEmptyState'
import { creditPackagesSectionStrings } from './CreditPackagesSection.strings'
import type { CreditPackage } from '../walletTypes'

// ─── Credit Packages Section ────────────────────────────────────────────────
// Every money value here (base_amount, total_credits, the bonus delta) is a
// raw, whole-toman integer straight from the API, passed straight into
// f.num / f.price -- no division, no multiplication, no unit conversion.
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
  const lang = useLang()
  const s = creditPackagesSectionStrings(lang)
  const f = fmt(lang)

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
        <Icon name="gift" size={16} className="text-accent" />
        <h2 className="card-title">{s.title}</h2>
        {creditPackages.length > 0 && (
          <span className="badge badge-accent" style={{ marginLeft: 4 }}>{f.num(creditPackages.length)}</span>
        )}
      </div>

      {creditPackages.length === 0 ? (
        <EmptyStateIcon icon="gift" title={s.noneTitle} desc={s.noneDesc} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
          {creditPackages.map((pkg) => {
            const isPurchasing = purchasingPkgId === pkg.id
            const baseToman = f.num(pkg.base_amount)
            const bonusToman = pkg.bonus_percent > 0
              ? f.num(pkg.total_credits - pkg.base_amount)
              : null
            const outputRate = pkg.model_id ? modelOutputRates[pkg.model_id] : undefined
            const approxTokens = outputRate ? Math.round((pkg.total_credits / outputRate) * 1_000_000) : null
            // The API already sends both names; pick the one that matches
            // the UI language for the headline and keep the other as the
            // smaller subtitle, instead of always showing Persian on top.
            const primaryName = lang === 'fa' ? pkg.name_fa : pkg.name_en
            const secondaryName = lang === 'fa' ? pkg.name_en : pkg.name_fa
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
                    {s.bonus(pkg.bonus_percent)}
                  </span>
                )}

                <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
                  {primaryName}
                </h3>
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: pkg.model_id ? 6 : 16 }}>
                  {secondaryName}
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
                    {/* Unit split into its own smaller/muted span, same as
                        before -- f.price would fold it into the number at
                        the same size and lose that styling. */}
                    {f.num(pkg.total_credits)} <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-muted)' }}>{s.tomanUnit}</span>
                  </div>
                  <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                    {s.youPay(baseToman)}
                  </p>
                  {bonusToman && (
                    <p style={{ fontSize: 12, color: 'var(--positive)', marginBottom: 8 }}>
                      {s.bonusAmount(bonusToman)}
                    </p>
                  )}
                  <p style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    {s.equivalent(f.price(pkg.total_credits))}
                  </p>
                  {approxTokens !== null && (
                    <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                      {s.approxTokens(f.num(Math.round(approxTokens / 1_000_000)), pkg.model_id!)}
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
                  {isPurchasing ? s.processing : s.buyPackage}
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
