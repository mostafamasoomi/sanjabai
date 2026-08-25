'use client'

import { useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { useLang } from '@/components/LanguageToggle'
import { fmt, dirFor } from '@/lib/adminI18n'
import { Field } from './shared'
import { api } from '../AdminPanel'
import { userWalletOpsStrings } from './UserWalletOps.strings'

/* ═══════════════════════════════════════════════════════════════════════════
   UserWalletOps — admin wallet credit/debit + consumer/developer panel move.

   Split out of UsersSection.tsx (which was approaching the repo's 500-line
   cap) rather than added there. Deliberately self-contained: it fetches
   nothing from AdminPanel's centralized state and owns its own request
   handling, because AdminPanel.tsx is out of scope for this change (no new
   props/handlers can be threaded through it) -- this component calls the
   backend directly via `api()` (exported from AdminPanel.tsx) the same way
   every other mutating call in this admin panel does: `Authorization: Bearer
   <admin token>`. NOTE: this deliberately does NOT use
   frontend/lib/apiFetch.ts -- that wrapper only adds the `X-Requested-With`
   header the *regular app's* CsrfMiddleware checks for session-cookie
   requests, and security.py's `_CSRF_PROTECTED_PREFIXES` explicitly excludes
   `/admin/*` ("Admin endpoints already have their own CSRF token system").
   This panel authenticates with a bearer token, not a session cookie, so
   apiFetch's header would be a no-op here while silently dropping the
   Authorization header `api()` provides -- which would turn every call
   below into a 401. `api()` is the correct, already-proven transport for
   this specific panel.

   Backend: POST /admin/users/{uid}/wallet-adjust, POST /admin/users/{uid}/panel
   (backend/admin_user_ops.py).
   ═══════════════════════════════════════════════════════════════════════════ */

type Direction = 'credit' | 'debit'

interface UserWalletOpsProps {
  uid: number
  balance: number
  panel: string
  onChanged: () => void
}

function genIdempotencyKey(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
  } catch {
    /* fall through to the manual fallback below */
  }
  return `admin_wallet_${Date.now()}_${Math.random().toString(36).slice(2)}`
}

export default function UserWalletOps({ uid, balance, panel, onChanged }: UserWalletOpsProps) {
  const lang = useLang()
  const s = userWalletOpsStrings(lang)
  const f = fmt(lang)
  const DIRECTION_LABEL: Record<Direction, string> = { credit: s.creditLabel, debit: s.debitLabel }

  const [amountInput, setAmountInput] = useState('')
  const [direction, setDirection] = useState<Direction>('credit')
  const [reason, setReason] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [pendingKey, setPendingKey] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [panelSaving, setPanelSaving] = useState(false)

  // Only whole digits -- no minus sign, no decimal point -- so a float or a
  // negative number can never even reach the confirmation dialog.
  const amountValid = /^[0-9]+$/.test(amountInput.trim()) && Number(amountInput.trim()) > 0
  const reasonValid = reason.trim().length > 0
  const canSubmit = amountValid && reasonValid && !submitting

  const openConfirm = () => {
    if (!canSubmit) {
      if (!amountValid) toast(s.amountInvalid, 'error')
      else if (!reasonValid) toast(s.reasonRequired, 'error')
      return
    }
    setPendingKey(genIdempotencyKey())
    setConfirming(true)
  }

  const submit = async () => {
    const amount = Number(amountInput.trim())
    setSubmitting(true)
    try {
      await api(`/api/admin/users/${uid}/wallet-adjust`, {
        method: 'POST',
        body: JSON.stringify({
          amount_toman: amount,
          direction,
          reason: reason.trim(),
          idempotency_key: pendingKey,
        }),
      })
      toast(direction === 'credit' ? s.creditSuccess : s.debitSuccess, 'success')
      setAmountInput('')
      setReason('')
      setConfirming(false)
      setPendingKey(null)
      onChanged()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : s.walletError, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const setPanel = async (next: 'consumer' | 'developer') => {
    if (next === panel || panelSaving) return
    setPanelSaving(true)
    try {
      await api(`/api/admin/users/${uid}/panel`, {
        method: 'POST',
        body: JSON.stringify({ panel: next }),
      })
      toast(next === 'developer' ? s.toDeveloperSuccess : s.toConsumerSuccess, 'success')
      onChanged()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : s.panelError, 'error')
    } finally {
      setPanelSaving(false)
    }
  }

  return (
    <div className="admin-card space-y-5">
      <div>
        <h3 className="text-sm font-bold text-primary mb-3">{s.sectionTitle}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Field label={s.amountLabel}>
            <input
              className="input w-full"
              inputMode="numeric"
              placeholder={s.amountPlaceholder}
              value={amountInput}
              onChange={(e) => setAmountInput(e.target.value)}
            />
          </Field>
          <Field label={s.txTypeLabel}>
            <select
              className="input w-full"
              value={direction}
              onChange={(e) => setDirection(e.target.value as Direction)}
            >
              <option value="credit">{s.creditLabel}</option>
              <option value="debit">{s.debitLabel}</option>
            </select>
          </Field>
          <Field label={s.reasonLabel}>
            <input
              className="input w-full"
              placeholder={s.reasonPlaceholder}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
        </div>
        <button className="btn btn-sm mt-3" onClick={openConfirm} disabled={submitting}>
          <Icon name="wallet" size={14} /> {s.submitRequest}
        </button>
      </div>

      <div className="pt-4 border-t" style={{ borderColor: 'var(--border)' }}>
        <h3 className="text-sm font-bold text-primary mb-3">{s.panelSectionTitle}</h3>
        <div className="flex items-center gap-2">
          <button
            className="btn btn-sm"
            disabled={panelSaving || panel === 'consumer'}
            style={panel !== 'developer' ? { background: 'var(--accent-dim)', color: 'var(--accent)' } : undefined}
            onClick={() => setPanel('consumer')}
          >
            {s.consumerLabel}
          </button>
          <button
            className="btn btn-sm"
            disabled={panelSaving || panel === 'developer'}
            style={panel === 'developer' ? { background: 'var(--accent-dim)', color: 'var(--accent)' } : undefined}
            onClick={() => setPanel('developer')}
          >
            {s.developerLabel}
          </button>
          <span className="text-xs text-muted">
            {s.currentStatus(panel === 'developer' ? s.developerLabel : s.consumerLabel)}
          </span>
        </div>
      </div>

      {confirming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => !submitting && setConfirming(false)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div className="card relative w-full max-w-md" dir={dirFor(lang)} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-primary">{s.confirmTitle}</h3>
              <button className="btn btn-icon btn-sm" onClick={() => setConfirming(false)} disabled={submitting}>
                <Icon name="close" size={16} />
              </button>
            </div>
            <div className="space-y-2 text-sm">
              <p>
                {s.typeLabel} <span className="font-bold">{DIRECTION_LABEL[direction]}</span>
              </p>
              <p>
                {s.confirmAmountLabel} <span className="font-bold">{f.price(Number(amountInput.trim()))}</span>
              </p>
              <p>
                {s.currentBalanceLabel} <span className="font-bold">{f.price(balance)}</span>
              </p>
              <p className="text-secondary">{s.confirmReasonLabel} {reason.trim()}</p>
            </div>
            <div className="flex gap-2 mt-5">
              <button className="btn flex-1" onClick={submit} disabled={submitting}>
                {submitting ? s.submitting : s.confirmSubmit}
              </button>
              <button
                className="btn btn-sm"
                style={{ background: 'var(--bg-elevated)' }}
                onClick={() => setConfirming(false)}
                disabled={submitting}
              >
                {s.cancel}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
