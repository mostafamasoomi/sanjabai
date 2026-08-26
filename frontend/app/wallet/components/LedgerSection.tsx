'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { fmtDate } from '../walletHelpers'
import { EmptyStateIcon } from './WalletEmptyState'
import { ledgerSectionStrings } from './LedgerSection.strings'
import type { LedgerEntry, LedgerFilter } from '../walletTypes'

// ─── Ledger Section ─────────────────────────────────────────────────────────
// l.amount and l.balance_after are raw, whole-toman integers straight from
// the API, passed straight into f.num -- no arithmetic on either.
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
  const lang = useLang()
  const s = ledgerSectionStrings(lang)
  const f = fmt(lang)

  const FILTERS: { key: LedgerFilter; label: string }[] = [
    { key: 'all', label: s.filterAll },
    { key: 'credit', label: s.filterCredit },
    { key: 'debit', label: s.filterDebit },
  ]

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icon name="history" size={16} className="text-accent" />
          <h2 className="card-title">{s.title}</h2>
          <span className="badge badge-accent" style={{ marginLeft: 4 }}>{f.num(ledger.length)}</span>
        </div>

        {/* Filter tabs */}
        <div className="wallet-filter-tabs">
          {FILTERS.map((flt) => (
            <button
              key={flt.key}
              onClick={() => onFilterChange(flt.key)}
              className={`wallet-filter-tab ${ledgerFilter === flt.key ? 'wallet-filter-active' : ''}`}
            >
              {flt.label}
            </button>
          ))}
        </div>
      </div>

      {filteredLedger.length === 0 ? (
        <EmptyStateIcon
          icon="history"
          title={s.emptyTitle}
          desc={ledgerFilter === 'all' ? s.emptyDescAll : s.emptyDescFiltered}
        />
      ) : (
        <div className="wallet-table-wrap">
          <table className="wallet-table">
            <thead>
              <tr>
                <th>{s.colDate}</th>
                <th>{s.colDescription}</th>
                <th style={{ textAlign: 'left' }}>{s.colAmount}</th>
                <th style={{ textAlign: 'left' }}>{s.colBalance}</th>
              </tr>
            </thead>
            <tbody>
              {filteredLedger.map((l, idx) => {
                const isCredit = l.amount > 0
                return (
                  <tr key={l.id} className={idx % 2 === 0 ? 'wallet-row-even' : 'wallet-row-odd'}>
                    <td className="wallet-td-date">
                      {fmtDate(l.created_at, lang)}
                    </td>
                    <td style={{ padding: '12px', color: 'var(--text-primary)', fontWeight: 500 }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span className={`wallet-amount-dot ${isCredit ? 'positive' : 'negative'}`} />
                        {/* l.reason is backend-authored ledger text (Persian
                            only today) -- rendered as-is, not translated
                            client-side. See return-format report. */}
                        {l.reason}
                      </span>
                    </td>
                    <td
                      className={`wallet-td-amount ${isCredit ? 'positive' : 'negative'}`}
                    >
                      {isCredit ? '+' : ''}{f.num(l.amount)} <span className="wallet-currency">{s.tomanUnit}</span>
                    </td>
                    <td className="wallet-td-balance">
                      {f.num(l.balance_after)}
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
