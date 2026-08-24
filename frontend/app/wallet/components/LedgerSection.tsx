import { Icon } from '@/components/ui/Icon'
import { faNum } from '@/lib/format'
import { fmtDate } from '../walletHelpers'
import { EmptyStateIcon } from './WalletEmptyState'
import type { LedgerEntry, LedgerFilter } from '../walletTypes'

const FILTERS = [
  { key: 'all', label: 'همه' },
  { key: 'credit', label: 'واریز' },
  { key: 'debit', label: 'برداشت' },
] as const

// ─── Ledger Section ─────────────────────────────────────────────────────────
// l.amount and l.balance_after are raw, whole-toman integers straight from
// the API, passed straight into faNum -- no arithmetic on either.
export function LedgerSection({
  ledger,
  filteredLedger,
  ledgerFilter,
  onFilterChange,
}: {
  ledger: LedgerEntry[]
  filteredLedger: LedgerEntry[]
  ledgerFilter: LedgerFilter
  onFilterChange: (key: LedgerFilter) => void
}) {
  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon name="history" size={16} className="text-accent" />
          <h2 className="card-title">تاریخچه تراکنش‌ها</h2>
          <span className="badge badge-accent" style={{ marginLeft: 4 }}>{faNum(ledger.length)}</span>
        </div>

        {/* Filter tabs */}
        <div className="wallet-filter-tabs">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => onFilterChange(f.key)}
              className={`wallet-filter-tab ${ledgerFilter === f.key ? 'wallet-filter-active' : ''}`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {filteredLedger.length === 0 ? (
        <EmptyStateIcon
          icon="history"
          title="تراکنشی ثبت نشده"
          desc={ledgerFilter === 'all' ? 'هنوز هیچ تراکنشی انجام نشده است.' : 'تراکنشی با این فیلتر یافت نشد.'}
        />
      ) : (
        <div className="wallet-table-wrap">
          <table className="wallet-table">
            <thead>
              <tr>
                <th>تاریخ</th>
                <th>شرح</th>
                <th style={{ textAlign: 'left' }}>مبلغ</th>
                <th style={{ textAlign: 'left' }}>مانده</th>
              </tr>
            </thead>
            <tbody>
              {filteredLedger.map((l, idx) => {
                const isCredit = l.amount > 0
                return (
                  <tr key={l.id} className={idx % 2 === 0 ? 'wallet-row-even' : 'wallet-row-odd'}>
                    <td className="wallet-td-date">
                      {fmtDate(l.created_at)}
                    </td>
                    <td style={{ padding: '12px', color: 'var(--text-primary)', fontWeight: 500 }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span className={`wallet-amount-dot ${isCredit ? 'positive' : 'negative'}`} />
                        {l.reason}
                      </span>
                    </td>
                    <td
                      className={`wallet-td-amount ${isCredit ? 'positive' : 'negative'}`}
                    >
                      {isCredit ? '+' : ''}{faNum(l.amount)} <span className="wallet-currency">تومان</span>
                    </td>
                    <td className="wallet-td-balance">
                      {faNum(l.balance_after)}
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
