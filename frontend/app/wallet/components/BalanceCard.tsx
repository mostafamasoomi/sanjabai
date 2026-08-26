'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { balanceCardStrings } from './BalanceCard.strings'

// ─── Balance Hero Card ──────────────────────────────────────────────────────
// balance is raw, whole tomans -- straight into f.num, no arithmetic. See
// walletHelpers.ts / page.tsx header comment for why no page-local money
// formatter wraps it here.
export function BalanceCard({ balance, copied, onCopy }: { balance: number | null; copied: boolean; onCopy: () => void }) {
  const lang = useLang()
  const s = balanceCardStrings(lang)
  const f = fmt(lang)

  return (
    <div className="card wallet-balance-card">
      {/* Glow accent */}
      <div className="wallet-balance-glow" />

      <div className="relative">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <Icon name="wallet" size={14} className="text-muted" />
          <span style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 500 }}>{s.currentBalance}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 8, marginBottom: 4 }}>
          <span className="wallet-balance-amount">
            {f.num(balance ?? 0)}
          </span>
          <span style={{ fontSize: 14, color: 'var(--text-muted)', fontWeight: 500 }}>{s.tomanUnit}</span>
        </div>



        <div className="divider" style={{ margin: '12px 0' }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            className={`btn btn-sm btn-secondary ${copied ? 'wallet-copy-success' : ''}`}
            onClick={onCopy}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
          >
            <Icon name={copied ? 'check' : 'copy'} size={14} />
            {copied ? s.copied : s.copy}
          </button>
        </div>
      </div>
    </div>
  )
}
