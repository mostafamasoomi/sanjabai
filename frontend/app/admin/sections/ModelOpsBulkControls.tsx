'use client'

import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { AVAILABILITY_OPTIONS, availabilityLabel, type Availability } from './availability'
import { modelOpsStrings } from './ModelOpsSection.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   The bulk half of «عملیات کاتالوگ مدل‌ها»: select a set of models, choose a
   target availability, confirm, apply.

   Own file because ModelOpsSection.tsx crossed the project's 500-line cap.
   These two pieces are the natural seam — they are one feature (act on a
   selection) and they touch none of the section's loading, filtering,
   pagination or per-row state, so they lift out whole.

   Both read the language themselves rather than taking the resolved strings
   as a prop: they share ModelOpsSection's dictionary, so there is no second
   source of truth to drift, and the alternative was threading `s` and `f`
   through two more prop lists.
   ═══════════════════════════════════════════════════════════════════════════ */

interface BulkActionBarProps {
  selectedCount: number
  filteredCount: number
  pageAllSelected: boolean
  /** Non-null while a bulk live test is running: both actions are disabled. */
  testRunning: boolean
  target: Availability
  onTarget: (a: Availability) => void
  onSelectAllFiltered: () => void
  onTogglePage: () => void
  onClearSelection: () => void
  onOpenConfirm: () => void
  onRunTest: () => void
}

export function BulkActionBar({
  selectedCount, filteredCount, pageAllSelected, testRunning,
  target, onTarget, onSelectAllFiltered, onTogglePage, onClearSelection,
  onOpenConfirm, onRunTest,
}: BulkActionBarProps) {
  const lang = useLang()
  const s = modelOpsStrings(lang)
  const f = fmt(lang)
  const none = selectedCount === 0

  return (
    <div className="admin-card admin-row gap-3">
      <span className="text-sm font-medium text-primary">{s.selectedCount(f.num(selectedCount))}</span>
      <button className="btn btn-sm" onClick={onSelectAllFiltered}>
        {s.selectAllFiltered(f.num(filteredCount))}
      </button>
      <button className="btn btn-sm" onClick={onTogglePage}>
        {pageAllSelected ? s.deselectPage : s.selectPage}
      </button>
      <button className="btn btn-sm" onClick={onClearSelection} disabled={none}>{s.clearSelection}</button>
      <span className="text-xs text-muted">{s.bulkChangeLabel}</span>
      <select
        className="input"
        value={target}
        onChange={(e) => onTarget(e.target.value as Availability)}
        style={{ maxWidth: 160 }}
      >
        {AVAILABILITY_OPTIONS.map((a) => (
          <option key={a} value={a}>{availabilityLabel(a, lang)}</option>
        ))}
      </select>
      <button className="btn btn-sm" onClick={onOpenConfirm} disabled={none || testRunning}>
        <Icon name="check" size={14} /> {s.applyBulk}
      </button>
      <button className="btn btn-sm" onClick={onRunTest} disabled={none || testRunning}>
        <Icon name="refresh" size={14} /> {s.bulkLiveTest}
      </button>
    </div>
  )
}

interface BulkConfirmModalProps {
  count: number
  target: Availability
  submitting: boolean
  onApply: () => void
  onClose: () => void
}

/** Rendered only when open — the caller guards on `bulkConfirming`, so this
 *  component never has to represent a closed state. */
export function BulkConfirmModal({
  count, target, submitting, onApply, onClose,
}: BulkConfirmModalProps) {
  const lang = useLang()
  const s = modelOpsStrings(lang)
  const f = fmt(lang)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={() => !submitting && onClose()}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div className="card relative w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-bold text-primary">{s.confirmModalTitle}</h3>
          <button className="btn btn-icon btn-sm" onClick={onClose} disabled={submitting}>
            <Icon name="close" size={16} />
          </button>
        </div>
        <p className="text-sm">
          {s.confirmModalBody(f.num(count), availabilityLabel(target, lang))}
        </p>
        {/* Only `available` can be refused by the server: it is the one
            transition gated on a confirmed live probe. */}
        {target === 'available' && (
          <p className="text-xs mt-2 flex items-center gap-1" style={{ color: 'var(--warning, #f59e0b)' }}>
            <Icon name="warning" size={12} /> {s.confirmModalWarning}
          </p>
        )}
        <div className="flex gap-2 mt-5">
          <button className="btn flex-1" onClick={onApply} disabled={submitting}>
            {submitting ? s.applying : s.confirmApply}
          </button>
          <button
            className="btn btn-sm"
            style={{ background: 'var(--bg-elevated)' }}
            onClick={onClose}
            disabled={submitting}
          >
            {s.cancel}
          </button>
        </div>
      </div>
    </div>
  )
}
