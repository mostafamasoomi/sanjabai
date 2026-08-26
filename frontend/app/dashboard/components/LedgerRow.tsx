'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { ledgerRowStrings } from './LedgerRow.strings'
import type { LedgerEntry } from '../types'

/* ═══════════════════════════════════════════════════════════════
   Ledger Entry Row
   ═══════════════════════════════════════════════════════════════ */

export function LedgerRow({ entry }: { entry: LedgerEntry }) {
  const lang = useLang()
  const s = ledgerRowStrings(lang)
  const f = fmt(lang)
  const isCredit = entry.amount > 0
  return (
    <div className="flex items-center justify-between py-3 border-b border-[var(--border)]">
      <div className="flex items-center gap-3 min-w-0">
        <div
          className="w-8 h-8 rounded-[var(--radius-sm)] flex items-center justify-center shrink-0"
          style={{
            background: isCredit ? 'color-mix(in srgb, var(--positive) 12%, transparent)' : 'color-mix(in srgb, var(--danger) 12%, transparent)',
          }}
        >
          <Icon
            name={isCredit ? 'wallet' : 'payment'}
            size={14}
            className={isCredit ? 'text-[var(--positive)]' : 'text-[var(--danger)]'}
          />
        </div>
        <div className="min-w-0">
          {/* entry.reason is backend-sourced ledger reason text (Persian
              only for now) -- see the i18n handoff report. */}
          <div className="text-[13px] font-medium text-[var(--text-primary)] overflow-hidden text-ellipsis whitespace-nowrap">
            {entry.reason}
          </div>
          <div className="text-[11px] text-[var(--text-muted)] mt-0.5">
            {f.date(entry.created_at)} — {f.time(entry.created_at)}
          </div>
        </div>
      </div>
      <div className="text-end shrink-0 ms-4">
        <div
          className="text-sm font-semibold"
          style={{ color: isCredit ? 'var(--positive)' : 'var(--danger)' }}
        >
          {f.price(entry.amount, { signed: true })}
        </div>
        <div className="text-[10px] text-[var(--text-muted)] text-end">
          {s.balance}: {f.num(entry.balance_after)}
        </div>
      </div>
    </div>
  )
}
