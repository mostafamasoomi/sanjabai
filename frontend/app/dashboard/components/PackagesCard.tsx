'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/lib/auth'
import { apiFetch } from '@/lib/apiFetch'
import { Icon } from '@/components/ui/Icon'
import { useLang } from '@/components/LanguageToggle'
import { fmt } from '@/lib/i18n'
import { packagesCardStrings } from './PackagesCard.strings'

/* ═══════════════════════════════════════════════════════════════
   Packages & balance card -- replaces SubscriptionCard (session 24+).

   The plan/subscription concept is retired: `credit_packages` is the only
   product concept now, and production holds zero live subscriptions (see
   the handoff note this card was built from). This card shows what the
   user actually holds -- active package entitlements plus the wallet
   balance the dashboard already loads -- instead of asking the backend
   about a subscription that no longer exists.

   Entitlements are fetched here, independently of useDashboardData's
   Promise.allSettled batch, deliberately mirroring
   frontend/app/wallet/components/EntitlementPanel.tsx: a slow or failed
   /api/entitlements call is a section-level problem for this one card, not
   a page-level dashboard error, so it must never join the "some data
   failed to load" toast the rest of the dashboard shares. "No active
   package" is the normal state for most users right now (no package grants
   a quota yet) -- it renders as plain, calm text, not an error state, and
   this card never invents a fake plan tier to fill the space.
   ═══════════════════════════════════════════════════════════════ */

type Entitlement = {
  id: number
  package_id: string
  // null means this dimension is not metered at all for this entitlement --
  // must never be treated as zero. Only requests_remaining is surfaced in
  // this compact card; the full breakdown lives on the wallet page.
  requests_remaining: number | null
  tokens_remaining: number | null
  expires_at: string | null
}

export function PackagesCard({
  balance,
  onManagePackages,
}: {
  /** Raw toman wallet balance, already fetched by useDashboardData. */
  balance: number | null
  onManagePackages: () => void
}) {
  const { token } = useAuth()
  const lang = useLang()
  const s = packagesCardStrings(lang)
  const f = fmt(lang)
  const [entitlements, setEntitlements] = useState<Entitlement[]>([])
  const [entitlementsLoading, setEntitlementsLoading] = useState(true)

  useEffect(() => {
    if (!token) {
      setEntitlementsLoading(false)
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
        // Non-fatal: this card just falls back to showing the balance
        // alone, same as an empty entitlements list. See file header.
      } finally {
        if (!cancelled) setEntitlementsLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  const hasPackages = entitlements.length > 0

  return (
    <div className="card dash-span-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 500 }}>{s.title}</span>
        <div
          style={{
            width: '2rem',
            height: '2rem',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--accent-dim)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name="gift" size={16} className="text-[var(--accent)]" />
        </div>
      </div>

      {/* Wallet balance -- raw toman through faPrice (via f.price), never
          multiplied or divided. This is the one number every user has,
          package or not. */}
      <div>
        <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginBottom: '0.125rem' }}>
          {s.balanceLabel}
        </div>
        <div className="num" style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--text-primary)' }}>
          {f.price(balance ?? 0)}
        </div>
      </div>

      <div className="divider" />

      {/* Active packages */}
      {entitlementsLoading ? (
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{s.loading}</div>
      ) : hasPackages ? (
        <div className="flex flex-col gap-2">
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
            {s.activeCountLabel(f.num(entitlements.length))}
          </span>
          {entitlements.slice(0, 3).map((e) => (
            <div key={e.id} className="flex items-center justify-between" style={{ fontSize: '0.75rem' }}>
              <span className="badge" style={{ fontFamily: 'monospace', fontSize: '0.625rem' }}>{e.package_id}</span>
              {e.requests_remaining !== null && (
                <span className="num" style={{ color: 'var(--text-secondary)' }}>
                  {f.num(e.requests_remaining)} {s.requestsRemainingUnit}
                </span>
              )}
            </div>
          ))}
        </div>
      ) : (
        // Normal state for most users, not an error -- and no fake plan
        // tier invented to fill the space. See file header.
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{s.noPackages}</div>
      )}

      <button
        className="btn btn-sm"
        onClick={onManagePackages}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.375rem', marginTop: '0.25rem' }}
      >
        <Icon name="payment" size={14} />
        {s.viewPackages}
      </button>
    </div>
  )
}
