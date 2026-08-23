'use client'

import { useState } from 'react'
import { Icon } from '@/components/ui/Icon'
import { toast } from '@/components/ui'
import { faPrice } from '@/lib/format'
import { Field } from './shared'
import { api } from '../AdminPanel'

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

const DIRECTION_LABEL: Record<Direction, string> = { credit: 'شارژ (افزایش)', debit: 'کسر (کاهش)' }

export default function UserWalletOps({ uid, balance, panel, onChanged }: UserWalletOpsProps) {
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
      if (!amountValid) toast('مبلغ باید عدد صحیح و بزرگ‌تر از صفر باشد', 'error')
      else if (!reasonValid) toast('ذکر دلیل الزامی است', 'error')
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
      toast(direction === 'credit' ? 'کیف پول شارژ شد' : 'از کیف پول کسر شد', 'success')
      setAmountInput('')
      setReason('')
      setConfirming(false)
      setPendingKey(null)
      onChanged()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : 'خطا در ثبت تراکنش کیف پول', 'error')
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
      toast(next === 'developer' ? 'کاربر به پنل توسعه‌دهنده منتقل شد' : 'کاربر به پنل مصرف‌کننده منتقل شد', 'success')
      onChanged()
    } catch (err) {
      toast(err instanceof Error && err.message !== 'unauthorized' ? err.message : 'خطا در جابه‌جایی پنل', 'error')
    } finally {
      setPanelSaving(false)
    }
  }

  return (
    <div className="admin-card space-y-5" dir="rtl">
      <div>
        <h3 className="text-sm font-bold text-primary mb-3">شارژ / کسر کیف پول</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Field label="مبلغ (تومان)">
            <input
              className="input w-full"
              inputMode="numeric"
              placeholder="مثلاً 50000"
              value={amountInput}
              onChange={(e) => setAmountInput(e.target.value)}
            />
          </Field>
          <Field label="نوع تراکنش">
            <select
              className="input w-full"
              value={direction}
              onChange={(e) => setDirection(e.target.value as Direction)}
            >
              <option value="credit">شارژ (افزایش)</option>
              <option value="debit">کسر (کاهش)</option>
            </select>
          </Field>
          <Field label="دلیل (الزامی)">
            <input
              className="input w-full"
              placeholder="مثلاً جبران خطای فنی"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </Field>
        </div>
        <button className="btn btn-sm mt-3" onClick={openConfirm} disabled={submitting}>
          <Icon name="wallet" size={14} /> ثبت درخواست
        </button>
      </div>

      <div className="pt-4 border-t" style={{ borderColor: 'var(--border)' }}>
        <h3 className="text-sm font-bold text-primary mb-3">پنل کاربر</h3>
        <div className="flex items-center gap-2">
          <button
            className="btn btn-sm"
            disabled={panelSaving || panel === 'consumer'}
            style={panel !== 'developer' ? { background: 'var(--accent-dim)', color: 'var(--accent)' } : undefined}
            onClick={() => setPanel('consumer')}
          >
            مصرف‌کننده
          </button>
          <button
            className="btn btn-sm"
            disabled={panelSaving || panel === 'developer'}
            style={panel === 'developer' ? { background: 'var(--accent-dim)', color: 'var(--accent)' } : undefined}
            onClick={() => setPanel('developer')}
          >
            توسعه‌دهنده
          </button>
          <span className="text-xs text-muted">
            وضعیت فعلی: {panel === 'developer' ? 'توسعه‌دهنده' : 'مصرف‌کننده'}
          </span>
        </div>
      </div>

      {confirming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => !submitting && setConfirming(false)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div className="card relative w-full max-w-md" dir="rtl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-primary">تأیید تراکنش کیف پول</h3>
              <button className="btn btn-icon btn-sm" onClick={() => setConfirming(false)} disabled={submitting}>
                <Icon name="close" size={16} />
              </button>
            </div>
            <div className="space-y-2 text-sm">
              <p>
                نوع: <span className="font-bold">{DIRECTION_LABEL[direction]}</span>
              </p>
              <p>
                مبلغ: <span className="font-bold">{faPrice(Number(amountInput.trim()))}</span>
              </p>
              <p>
                موجودی فعلی: <span className="font-bold">{faPrice(balance)}</span>
              </p>
              <p className="text-secondary">دلیل: {reason.trim()}</p>
            </div>
            <div className="flex gap-2 mt-5">
              <button className="btn flex-1" onClick={submit} disabled={submitting}>
                {submitting ? 'در حال ثبت...' : 'تأیید و اعمال'}
              </button>
              <button
                className="btn btn-sm"
                style={{ background: 'var(--bg-elevated)' }}
                onClick={() => setConfirming(false)}
                disabled={submitting}
              >
                انصراف
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
