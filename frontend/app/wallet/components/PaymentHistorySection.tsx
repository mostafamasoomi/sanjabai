import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { fmtDate, statusLabel } from '../walletHelpers'
import { EmptyStateIcon } from './WalletEmptyState'
import type { PaymentRecord } from '../walletTypes'

// ─── Payment History Section ────────────────────────────────────────────────
// p.amount is a raw, whole-toman integer straight from the API, passed
// straight into faNum -- no arithmetic.
export function PaymentHistorySection({ payments }: { payments: PaymentRecord[] }) {
  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
        <Icon name="payment" size={16} className="text-accent" />
        <h2 className="card-title">تاریخچه پرداخت‌ها</h2>
      </div>

      {payments.length === 0 ? (
        <EmptyStateIcon icon="payment" title="پرداختی ثبت نشده" desc="هنوز پرداختی انجام نشده است." />
      ) : (
        <div className="wallet-table-wrap">
          <table className="wallet-table">
            <thead>
              <tr>
                <th>تاریخ</th>
                <th>شناسه</th>
                <th style={{ textAlign: 'left' }}>مبلغ</th>
                <th>وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((p, idx) => {
                const st = statusLabel[p.status] || { text: p.status, badge: 'badge-warning' }
                return (
                  <tr key={p.id} className={idx % 2 === 0 ? 'wallet-row-even' : 'wallet-row-odd'}>
                    <td className="wallet-td-date">
                      {fmtDate(p.created_at)}
                    </td>
                    <td style={{ padding: '12px', color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"', fontSize: 12 }}>
                      #{p.id}
                    </td>
                    <td className="wallet-td-amount text-primary">
                      {faNum(p.amount)} <span className="wallet-currency">تومان</span>
                    </td>
                    <td style={{ padding: '12px' }}>
                      <span className={`badge ${st.badge}`}>{st.text}</span>
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
