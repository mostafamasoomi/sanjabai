'use client'

/**
 * Shows the user's package entitlements -- request/token quotas granted by
 * a purchased package, counted separately from the Toman wallet balance.
 *
 * Today no package grants a quota yet, so every user has zero entitlements.
 * That is the expected, common case, not an error -- this panel renders
 * nothing at all when the list is empty (see the empty-state note at the
 * bottom of this file for why). It never blocks or otherwise affects the
 * rest of the wallet page: a failed/slow fetch here just means the section
 * stays hidden, same as the empty case.
 */

import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { Icon, type IconName } from '@/components/ui/Icon'
import { faNum, faPrice, faDate } from '@/lib/format'

type Entitlement = {
  id: number
  package_id: string
  // null on either of these means the package does not meter that
  // dimension at all -- NOT zero. Must never render as "۰ باقی‌مانده".
  requests_remaining: number | null
  tokens_remaining: number | null
  max_cost_per_request_toman: number | null
  expires_at: string | null
}

// An entitlement expiring within this many days is called out visually so a
// user doesn't lose an unused quota to a silent expiry.
const SOON_THRESHOLD_DAYS = 3

function daysUntil(iso: string): number {
  return (new Date(iso).getTime() - Date.now()) / 86_400_000
}

// ─── One metered dimension (requests or tokens) ────────────────────────────
function QuotaRow({
  icon,
  label,
  value,
  unit,
}: {
  icon: IconName
  label: string
  value: number | null
  unit: string
}) {
  const unmetered = value === null
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '6px 0' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--text-secondary)' }}>
        <Icon name={icon} size={14} className={unmetered ? 'text-muted' : 'text-accent'} />
        {label}
      </span>
      {unmetered ? (
        // A null value means this package places no count-based limit on
        // this dimension -- distinct from, and rendered differently than,
        // a genuine zero remaining.
        <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>بدون محدودیت شمارشی</span>
      ) : (
        <span style={{ fontSize: 14, fontWeight: 700, color: value === 0 ? 'var(--danger)' : 'var(--text-primary)' }}>
          {faNum(value)} <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-muted)' }}>{unit}</span>
        </span>
      )}
    </div>
  )
}

// ─── One entitlement card ───────────────────────────────────────────────────
function EntitlementCard({ e }: { e: Entitlement }) {
  const soon = e.expires_at != null && daysUntil(e.expires_at) <= SOON_THRESHOLD_DAYS

  return (
    <div className="card" style={{ padding: 16, borderColor: soon ? 'var(--danger)' : undefined }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
        <span className="badge" style={{ fontFamily: 'monospace', fontSize: 11 }}>{e.package_id}</span>
        {e.expires_at && (
          <span className={`badge ${soon ? 'badge-danger' : 'badge-accent'}`} style={{ fontSize: 11 }}>
            {soon ? 'به‌زودی منقضی می‌شود' : 'انقضا'}: {faDate(e.expires_at)}
          </span>
        )}
      </div>

      <div className="divider" style={{ margin: '4px 0 8px' }} />

      <QuotaRow icon="send" label="درخواست باقی‌مانده" value={e.requests_remaining} unit="درخواست" />
      <QuotaRow icon="cpu" label="توکن باقی‌مانده" value={e.tokens_remaining} unit="توکن" />

      <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border)', fontSize: 11.5, color: 'var(--text-muted)', lineHeight: 1.7 }}>
        {e.max_cost_per_request_toman != null ? (
          <>
            سقف هزینه هر درخواست از این بسته:{' '}
            <strong style={{ color: 'var(--text-secondary)' }}>{faPrice(e.max_cost_per_request_toman)}</strong>.
            درخواست‌های گران‌تر از این سقف، از موجودی کیف پول شما کسر می‌شود، نه از این بسته.
          </>
        ) : (
          // A NULL ceiling is not "no limit" -- the backend never routes a
          // request through an entitlement with no ceiling set for it, so
          // in practice this entitlement's requests are always billed from
          // the wallet, not from this quota. Say that plainly.
          <>برای این بسته سقف هزینه‌ای ثبت نشده؛ در نتیجه هزینه درخواست‌های شما از این سهمیه پوشش داده نمی‌شود و از موجودی کیف پول کسر می‌شود.</>
        )}
      </div>
    </div>
  )
}

// ─── Panel ───────────────────────────────────────────────────────────────
export default function EntitlementPanel() {
  const { token } = useAuth()
  const [entitlements, setEntitlements] = useState<Entitlement[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) {
      setLoading(false)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const res = await apiFetch('/api/entitlements', {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (res.ok) {
          const data = await res.json()
          if (!cancelled) setEntitlements(Array.isArray(data) ? data : [])
        }
      } catch {
        // An optional quota panel failing to load must never surface an
        // error on the wallet page -- it just stays hidden, same as the
        // empty-list case below.
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  // EMPTY-STATE CHOICE: render nothing at all, rather than an empty card or
  // a one-line "no quota yet" message. Reasoning: right now, literally every
  // user has zero entitlements, because no package on this product grants a
  // quota yet -- this is not a temporary loading gap or a personal "you have
  // none, unlike others" state, it is the state of the entire product. An
  // always-empty card (or an always-shown explanatory sentence) would be
  // permanent clutter on a page that already explains everything relevant
  // via the Toman balance and the credit-package list above it, and it
  // risks reading as "this feature is broken" or "you're missing out on
  // something everyone else has" -- neither of which is true. The moment
  // any package actually grants a quota and a user buys one, this panel
  // appears on its own with real numbers. Nothing to show, so show nothing.
  if (loading || entitlements.length === 0) return null

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <Icon name="gift" size={16} className="text-accent" />
        <h2 className="card-title">سهمیه بسته‌های شما</h2>
        <span className="badge badge-accent" style={{ marginLeft: 4 }}>{faNum(entitlements.length)}</span>
      </div>
      <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
        این سهمیه‌ها جدا از موجودی تومانی کیف پول شما شمارش می‌شوند. با تمام یا منقضی شدن سهمیه یک بسته، هزینه درخواست‌های بعدی از موجودی کیف پول کسر خواهد شد.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
        {entitlements.map((e) => (
          <EntitlementCard key={e.id} e={e} />
        ))}
      </div>
    </div>
  )
}
