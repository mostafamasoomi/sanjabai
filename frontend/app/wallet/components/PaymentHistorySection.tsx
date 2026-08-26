'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { fmtDate, statusLabel } from '../walletHelpers'
import { EmptyStateIcon } from './WalletEmptyState'
import { paymentHistorySectionStrings } from './PaymentHistorySection.strings'
import type { PaymentRecord } from '../walletTypes'

// ─── Payment History Section ────────────────────────────────────────────────
// p.amount is a raw, whole-toman integer straight from the API, passed
// straight into f.num -- no arithmetic.
export function PaymentHistorySection({ payments }: { payments: PaymentRecord[] }) {
  const lang = useLang()
  const s = paymentHistorySectionStrings(lang)
  const f = fmt(lang)
  const st = statusLabel(lang)

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
        <Icon name="payment" size={16} className="text-accent" />
        <h2 className="card-title">{s.title}</h2>
      </div>

      {payments.length === 0 ? (
        <EmptyStateIcon icon="payment" title={s.emptyTitle} desc={s.emptyDesc} />
      ) : (
        <div className="wallet-table-wrap">
          <table className="wallet-table">
            <thead>
              <tr>
                <th>{s.colDate}</th>
                <th>{s.colId}</th>
                <th style={{ textAlign: 'start' }}>{s.colAmount}</th>
                <th>{s.colStatus}</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((p, idx) => {
                const status = st[p.status] || { text: p.status, badge: 'badge-warning' }
                return (
                  <tr key={p.id} className={idx % 2 === 0 ? 'wallet-row-even' : 'wallet-row-odd'}>
                    <td className="wallet-td-date">
                      {fmtDate(p.created_at, lang)}
                    </td>
                    <td style={{ padding: '12px', color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"', fontSize: 12 }}>
                      #{p.id}
                    </td>
                    <td className="wallet-td-amount text-primary">
                      {f.num(p.amount)} <span className="wallet-currency">{s.tomanUnit}</span>
                    </td>
                    <td style={{ padding: '12px' }}>
                      <span className={`badge ${status.badge}`}>{status.text}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
